import io
import json
import sys

from attrs import frozen, define, field

from pyrinha.nodes import *
from pyrinha.nodes import BinaryOp
from pyrinha.values import *

r"""
No interpreter0, notamos alguns potenciais problemas.

Primeiro: para cada chamada de função da linguagem interpretada, realizamos
uma chamada equivalente em Python. Como essa é uma linguagem dependente de
recursão, qualquer algoritmo que exija mais iterações estará sujeito a um
RecursionError (ou Stack Overflow, como se diz em outras linguagens).

Um problema mais básico é que usar recursão não é uma boa escolha quando não
temos controle sobre a entrada, e um programa de usuário não é confiável.
Mesmo que de alguma forma nós resolvessemos o primeiro problema, ainda
estaríamos sujeitos a um RecursionError se a árvore for muito profunda.
Também vimos esse risco no modo como a função __str__ foi implementada.

Por fim, notamos que a execução de fib(24) demora vários segundos, e de fib(30)
nem esperei pra ver quanto demora. A função de certa forma está "mal escrita",
dado que cada chamada invoca 2 outras sub-chamadas, o que leva a uma
complexidade de tempo exponencial.

                         __________ fib(5) _______
                        /                         \
                  __ fib(4) __                   fib(3)
                 /            \                /       \
              fib(3)         fib(2)         fib(2)    fib(1)
            /       \        /   \          /   \       |
         fib(2)    fib(1) fib(1) fib(0)  fib(1) fib(0)  1
         /   \       |       |     |        |     |
      fib(1) fib(0)  1       1     1        1     1
         |     |
         1     1

Contudo, estamos trabalhando em uma linguagem pura, o que significa que uma
função sempre vai retornar o mesmo valor se forem dados os mesmos parâmetros.
Até a saída padrão deve ser sempre a mesma. Portanto, na árvore acima, seria
possível eliminar todas as chamadas repetidas se guardarmos os resultados das
funções em um cache.

                         __________ fib(5) _______
                        /                         \
                  __ fib(4) __                   fib(3)
                 /            \                    |
              fib(3)         fib(2)               [3]
            /       \          |
         fib(2)    fib(1)     [2]
         /   \       |
      fib(1) fib(0) [1]
         |     |
         1     1

Vamos, nesta segundo implementação corrigir essas falhas e usar um modelo muito
mais eficiente de execução: interpretação de bytecode.
"""

# ---- Stringificação ----

"""
Para começar, vamos reimplementar a função que escreve a saída de cada termo.
Vamos reutilizar os métodos __str__ de Var, Str, Int e Bool, que não fazem
chamada recursiva, mas alterar os dos outros Terms.

O princípio básico em converter um algoritmo recursivo para iterativo é
*introduzir uma pilha* -- porque é isso que o runtime faz quando você executa!
Em Python, a cada chamada de função, o estado intermediário atual é armazenado
em um call frame, que contém todas as variáveis locais. Esses frames são
organizados em uma pilha, ou stack. Você já viu essa pilha: quando ocorre uma
exceção, o runtime mostra todas as funções invocadas até aquele ponto.

Portanto, precisamos avaliar qual o estado intermediário que precisamos guardar
entre cada passo recursivo, e transformá-lo em uma iteração.
"""


def node_str(node: Node) -> str:
    "Converte um node da AST para sua representação de string."

    # Vamos usar um StringIO para escrever a string de saída aos poucos,
    # como se escreve em um arquivo.
    buf = io.StringIO()

    # Inicializamos o stack com o node passado como parâmetro.
    # Também incluímos um inteiro que contém o nível na árvore, que será usado para
    # calcular indentação.
    #
    # Python não tem um tipo específico pra stacks, mas podemos usar os
    # uma lista e seus métodos .pop() e .append() para fazer as mesmas
    # operações.
    stack: list[tuple[Node | str, int]] = [(node, 0)]

    # indent retorna a indentação ao inserir uma nova linha, no nível atual.
    def indent(level: int) -> str:
        return "\n" + (level * "  ")

    while stack:
        # A cada iteração, retiramos o elemento do topo. A iteração acaba
        # quando o stack estiver vazio.
        node = stack.pop()

        match node:
            # Caso base: não é necessário recursão, então usamos o método
            # __str__ do node (que é chamado por str()).
            case ((Symbol() | Var() | Str() | Int() | Bool()) as term, _):
                buf.write(str(term))

            # Um File empilha sua expressão para ser processada na próxima
            # iteração.
            case (File(expression=expression), level):
                stack.append((expression, level))

            # Print deve ser escrito como "print (value)\n", onde 'value' pode ser
            # um termo complexo. A estratégia é escrever "print (", então processar
            # 'value' na próxima iteração, e então escrever ")". Para isso, vamos
            # empilhar os elementos da seguinte forma:
            case (Print(value=value), level):
                print_token = "print ("
                value_token = (value, level)
                close_token = ")" + indent(level)

                stack += [close_token, value_token, print_token]
                # Colocamos os elementos ao contrário! Como estamos trabalhando com
                # uma pilha, a sequência de pop() vai desempilhar sempre do topo,
                # de modo que a order será "print (", então 'value', e por fim ")".

            # Já que estamos empilhando strings literais, também precisamos tratá-las
            # em um case.
            case str():
                buf.write(node)

            # No caso mais simples de Binary, poderíamos empilhar apenas
            #
            #    [rhs, op, lhs]
            #
            # Contudo, precisamos também considerar a precedência de operadores,
            # que podem exigir cercar um dos (ou os dois) argumentos com parênteses.
            case (Binary(lhs=lhs, op=op, rhs=rhs), level):
                term_precedence = op.value.precedence
                term_token = op.value.token

                # arg_tokens retorna o argumento (lhs ou rhs) se ele não precisar de
                # parênteses, ou [")", arg, "("] caso precise.
                #
                # Na implementação de Binary.__str__ em nodes.py eu apenas repeti a
                # lógica para lhs e rhs, mas aqui resolvi mostrar como fazer isso sem
                # repetição: basta escrever uma funçãozinha local. Nem sempre é
                # necessário, mas é bom pensar em usar se a lógica não é trivial.
                def arg_tokens(arg: Term) -> list[str]:
                    match arg:
                        case Binary(op=arg_op):
                            if arg_op.value.precedence < term_precedence:
                                return [")", (arg, level), "("]
                            return [(arg, level)]
                        case _:
                            return [(arg, level)]

                stack += arg_tokens(rhs) + [f" {term_token} "] + arg_tokens(lhs)

            # Para um let, queremos escrever
            #
            #     let <name> = <value>;\n<next>
            #
            # O único newline precisa ter a indentação no mesmo nível do let.
            # O next também possui o mesmo nível de indentação.
            case (Let(name=name, value=value, next=next), level):
                # Leia a lista de baixo pra cima que faz mais sentido.
                stack += [
                    (next, level),
                    indent(level),
                    ";",
                    (value, level),
                    " = ",
                    (name, level),
                    "let ",
                ]

            # Para if, queremos escrever
            #
            #     if <condition> {\n<then>\n} else {\n<otherwise>\n}
            #
            # Alguns newlines precisam conter a indentação com 1 nível a mais,
            # assim como os termos 'then' e 'otherwise'.
            case (If(condition=condition, then=then, otherwise=otherwise), level):
                l0 = indent(level)
                l1 = indent(level + 1)

                stack += [
                    l0 + "}",
                    (otherwise, level + 1),
                    l0 + "} else {" + l1,
                    (then, level + 1),
                    " {" + l1,
                    (condition, level),
                    "if ",
                ]

            # Para uma chamada, queremos
            #
            #     <callee>(<arg0>, <arg1>, <arg2>)
            case (Call(callee=callee, arguments=arguments), level):
                stack.append(")")
                # Insere os argumentos (e vírgulas) na ordem reversa.
                for i, arg in enumerate(arguments[::-1]):
                    stack.append((arg, level))
                    if i < len(parameters) - 1:
                        stack.append(", ")
                stack.append("(")
                stack.append((callee, level))

            # Para fn, queremos escrever
            #
            #     fn(<param0>, <param1>, <param2>) {\n<value>\n}
            case (Function(value=value, parameters=parameters), level):
                l0 = indent(level)
                l1 = indent(level + 1)

                # Elementos do corpo da função.
                stack += [
                    l0 + "}",
                    (value, level + 1),
                    ") {" + l1,
                ]

                # Insere os parâmetros (e vírgulas) na ordem reversa.
                for i, param in enumerate(parameters[::-1]):
                    stack.append((param, level))
                    if i < len(parameters) - 1:
                        stack.append(", ")

                # Os últimos serão os primeiros.
                stack.append("fn(")

            case _:
                raise ValueError(f"unhandled case {node!r}")

    # Retorna a string acumulada.
    return buf.getvalue()


"""
Agora, podemos monkeypatch os métodos __str__ dos nodes que alteramos:

No dia-a-dia eu nunca faria isso, e sim iria usar essa função na definição
de classes em nodes.py. Aqui, porém, quero ser didático sem ter que refazer
tudo.
"""

File.__str__ = node_str
Print.__str__ = node_str
Binary.__str__ = node_str
Let.__str__ = node_str
If.__str__ = node_str
Call.__str__ = node_str
Function.__str__ = node_str

"""
Execute este script com

    python -m pyrinha.interpreter1 files/fib1.json
    python -m pyrinha.interpreter1 files/deep_ast.json

para ver o novo formatador em ação. Compare com 

    python -m pyrinha.interpreter0 files/deep_ast.json

que deve falhar com RecursionError.

"""

# ---- Compiler ----


class Compiler:
    chunks: list["Chunk"] = field(converter=list, factory=list)

    def new_chunk(self) -> "Chunk":
        chunk = Chunk()
        self.chunks.append(chunk)
        return chunk

    def compile_file(self, file: File) -> list["Chunk"]:
        self.chunks = []
        chunk = self.new_chunk()
        self.compile(chunk, file.expression)
        chunk.push(Halt())
        return self.chunks

    def compile(self, chunk: "Chunk", term: Term):
        match term:
            case Print(value=value):
                self.compile(chunk, value)
                chunk.push(Write())

            case Var(text=text):
                chunk.push(Get(text))

            case Int(value=value) | Str(value=value) | Bool(value=value):
                chunk.push(Put(value))

            case Let(name=name, value=value, next=next):
                self.compile(chunk, value)
                chunk.push(Allocate([name.text]))
                self.compile(chunk, next)
                chunk.push(Deallocate())

            case Function(value=value, parameters=parameters):
                fn_chunk = self.new_chunk()
                fn_chunk.push(Allocate(param.text for param in parameters))
                self.compile(fn_chunk, value)
                fn_chunk.push(Deallocate())
                fn_chunk.push(Proceed())

                chunk.push(CloseOver(fn_chunk))

            case Binary(lhs=lhs, op=op, rhs=rhs):
                self.compile(chunk, lhs)
                self.compile(chunk, rhs)
                chunk.push(Operation(op))

            case If(condition=condition, then=then, otherwise=otherwise):
                jump_otherwise = JumpIfFalse(InstructionPointer(chunk, -1))
                jump_end = Jump(InstructionPointer(chunk, -1))

                self.compile(chunk, condition)
                chunk.push(jump_otherwise)
                self.compile(chunk, then)
                chunk.push(jump_end)
                jump_otherwise.target.chunk_index = len(chunk.instructions)

                self.compile(chunk, otherwise)
                jump_end.target.chunk_index = len(chunk.instructions)

            case Call(callee=callee, arguments=arguments):
                for arg in arguments:
                    self.compile(chunk, arg)
                self.compile(chunk, callee)
                chunk.push(Invoke())


# ---- Instructions ----


@define
class Instruction:
    def __str__(self):
        name = type(self).__name__.lower()
        if not self._params:
            return name
        return f"{name} {', '.join(self._params)}"

    @property
    def _params(self) -> list[str]:
        return []


@define
class Chunk:
    instructions: list[Instruction] = field(converter=list, factory=list)

    def push(self, instr: Instruction):
        self.instructions.append(instr)

    def id_str(self) -> str:
        ptr = hex(id(self))
        return "#" + ptr[-6:]


@define
class InstructionPointer:
    chunk: Chunk
    chunk_index: int

    def __str__(self):
        return f"{self.chunk.id_str()}:{self.chunk_index:03d}"


@define
class Put(Instruction):
    value: int | str | bool

    @property
    def _params(self) -> list[str]:
        match self.value:
            case int():
                return [str(self.value)]
            case str():
                return [repr(self.value)]
            case True:
                return ["true"]
            case False:
                return ["false"]


@define
class Get(Instruction):
    name: str

    @property
    def _params(self) -> list[str]:
        return [self.name]


@define
class Write(Instruction):
    pass


@define
class JumpIfFalse(Instruction):
    target: InstructionPointer

    @property
    def _params(self) -> list[str]:
        return [str(self.target)]


@define
class Jump(Instruction):
    target: InstructionPointer

    @property
    def _params(self) -> list[str]:
        return [str(self.target)]


@define
class Allocate(Instruction):
    names: list[str] = field(factory=list, converter=list)

    @property
    def _params(self) -> list[str]:
        return self.names


@define
class Deallocate(Instruction):
    pass


@define
class Proceed(Instruction):
    pass


@define
class Invoke(Instruction):
    pass


@define
class Operation(Instruction):
    op: BinaryOp

    @property
    def _params(self) -> list[str]:
        return [self.op.value.token]


@define
class Halt(Instruction):
    pass


@define
class CloseOver(Instruction):
    fn: Chunk

    @property
    def _params(self) -> list[str]:
        return [self.fn.id_str()]


# ---- Main ----


def main(file: File):
    print(file)
    print()

    chunks = Compiler().compile_file(file)
    for chunk in chunks:
        print("% chunk", chunk.id_str())
        for instr in chunk.instructions:
            print(instr)
        print()


if __name__ == "__main__":
    from argparse import ArgumentParser
    from pathlib import Path

    p = ArgumentParser()
    p.add_argument("file", type=Path, help="AST file to execute")
    args = p.parse_args()

    # Temporariamente aumenta o limite de recursão para as bibliotecas json e cattrs,
    # que dependem de recursão para construir objetos.
    limit = sys.getrecursionlimit()
    print(f"Default recursion limit: {limit}")
    sys.setrecursionlimit(10000)

    with args.file.open() as f:
        ast = json.load(f)
    file = ast_converter().structure(ast, File)

    # Restaura o limite default.
    sys.setrecursionlimit(limit)
    main(file)
