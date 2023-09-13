import json
import sys

from attrs import frozen

from pyrinha.nodes import *
from pyrinha.values import *

# ---- Interpreter ----

"""
Agora chegamos à parte divertida: interpretar o código!

Como a linguagem Rinha é uma linguagem funcional e pura (excetuando 'print'),
vamos usar isso a nosso favor no design do interpretador. Por exemplo, o
interpretador se baseia somente em _calcular valores_, computando uma saída
a partir das entradas.

Vamos escrever primeiro uma função 'evaluate0' que é bem simples e
ineficiente, mas que pelo menos vai servir de padrão para compararmos e validarmos
desenvolvimentos mais complexos posteriores.

Essa função é invocada para um dado 'Term', e por sua vez ela pode ser invocada
novamente para 'Term's filhos do primeiro. Por exemplo, para calcular o valor de
'10 + x*20', invocamos

    evaluate0(Binary(Int(10), ADD, Binary(Var("x"), MUL, Int(20))))

Internamente para calcular o valor de Binary(..., ADD, ...), precisamos calcular
antes

    evaluate0(Int(10))
    evaluate0(Binary(Var("x"), MUL, Int(20)))

Por sua vez, este último ainda precisa calcular

    evaluate0(Var("x"))
    evaluate0(Int(20))

Perceba que essas chamadas recursivas ocorrem para cada nó da árvore de sintaxe
abstrata, o que caracteriza esse interpretador como "tree-walking". Como discutido
anteriormente, não é indicado realizar chamadas recursivas sem ter um limite de
profundidade conhecido, então vamos melhorar isso mais pra frente.
"""


@frozen
class ExecutionError(Exception):
    """Exceção lançada para erros de runtime.

    Poderia se chamar RuntimeError, mas esse já é um tipo de Python.

    Note que podemos usar o mesmo decorator '@frozen' para tipos próprios
    de exceções.
    """

    location: Loc
    msg: str


def run_op(lhs, op, rhs, location):
    def fail():
        raise ExecutionError(
            location, f"Invalid operands for '{op.value.token}': {lhs}, {rhs}"
        )

    match lhs, rhs:
        case Literal(), Literal():
            pass
        case _:
            fail()

    # A saber: eu amo o match-case introduzido no Python 3.10. Ele possui ainda outras
    # capacidades sintáticas para não dar vontade nunca mais de fazer um instanceof().
    # Leia o tutorial completo em https://peps.python.org/pep-0636/
    match op, lhs.x, rhs.x:
        case BinaryOp.ADD, int(), int():
            return Literal(lhs.x + rhs.x)
        case BinaryOp.ADD, str(), int():
            return Literal(lhs.x + str(rhs.x))
        case BinaryOp.ADD, int(), str():
            return Literal(str(lhs.x) + rhs.x)
        case BinaryOp.ADD, str(), str():
            return Literal(lhs.x + rhs.x)
        case BinaryOp.SUB, int(), int():
            return Literal(lhs.x - rhs.x)
        case BinaryOp.MUL, int(), int():
            return Literal(lhs.x * rhs.x)
        case BinaryOp.DIV, int(), int():
            return Literal(lhs.x // rhs.x)
        case BinaryOp.REM, int(), int():
            return Literal(lhs.x % rhs.x)
        case BinaryOp.EQ, _, _:
            if type(lhs.x) != type(rhs.x):
                fail()
            return Literal(lhs == rhs)
        case BinaryOp.NEQ, _, _:
            if type(lhs.x) != type(rhs.x):
                fail()
            return Literal(lhs != rhs)
        case BinaryOp.LT, int(), int():
            return Literal(lhs.x < rhs.x)
        case BinaryOp.GT, int(), int():
            return Literal(lhs.x > rhs.x)
        case BinaryOp.LTE, int(), int():
            return Literal(lhs.x <= rhs.x)
        case BinaryOp.GTE, int(), int():
            return Literal(lhs.x >= rhs.x)
        case BinaryOp.AND, bool(), bool():
            return Literal(lhs.x and rhs.x)
        case BinaryOp.OR, bool(), bool():
            return Literal(lhs.x or rhs.x)
        case _:
            fail()


def run_file0(file: File) -> Value:
    "Executa um arquivo no environment global."

    """
    No momento o environment global contém apenas algumas poucas definições.
    Numa linguagem completa, você iria querer incluir toda a biblioteca
    padrão.
    """
    return evaluate0(Env(), file.expression)


def evaluate0(env: Env, term: Term) -> Value:
    "Obtém o valor de um termo para um dado environment."
    match term:
        # O caso de Int, Str e Bool são os mais simples, retornando um Literal com o
        # mesmo valor presente na AST.
        case Int(value=value):
            return Literal(value)
        case Str(value=value):
            return Literal(value)
        case Bool(value=value):
            return Literal(value)
        case Tuple(first=first, second=second):
            return Literal((first, second))

        # Para obter o valor de Var, consultamos se a variável está definida
        # no environment. Ela pode ter sido definida por um Let anterior, ou como
        # o parâmetro de uma função.
        case Var(location, text):
            if text not in env.values:
                raise ExecutionError(location, f"unknown variable '{text}'")
            return env.values[text]

        # Encontrar uma função anônima não exige nenhuma ação a não ser capturar
        # o environment onde ela é definida para criar sua Closure.
        case Function():
            return Closure(term, env)

        # Para obter o valor de um 'if', precisamos apenas obter o valor de um dos
        # seus branches -- ou 'then', ou 'otherwise'.
        case If(location, condition, then, otherwise):
            cond = evaluate0(env, condition)
            match cond:
                case Literal(True):
                    return evaluate0(env, then)
                case Literal(False):
                    return evaluate0(env, otherwise)
                case _:
                    cond_type = type(cond).__name__
                    raise ExecutionError(
                        location, f"condition in 'if' is {cond_type}, not bool"
                    )

        # Optei que a operação Print retorne o valor passado para ela, além de imprimi-lo pra stdout.
        # O objetivo é poder debugar uma função como
        #
        #     let x = foo(a, b);
        #
        # inserindo prints em cada elemento:
        #
        #     let x = print(foo(print(a), print(b)))
        case Print(value=value):
            val = evaluate0(env, value)
            print(val)
            return val

        # First e Second são bem simples e diretos.
        case First(location, value):
            match value:
                case Literal((first, _)):
                    return first
                case _:
                    val_type = type(value).__name__
                    raise ExecutionError(
                        location, f"argument to 'first' is {val_type}, not a tuple"
                    )

        case Second(location, value):
            match value:
                case Literal((_, second)):
                    return second
                case _:
                    val_type = type(value).__name__
                    raise ExecutionError(
                        location, f"argument to 'second' is {val_type}, not a tuple"
                    )

        # O cálculo de operações binárias é bem direto, mas longo e repetitivo.
        # É possível fazer algo mais sucinto para obter a operação a partir do token, por
        # exemplo, criando um mapa
        #
        # import operator
        #
        # operation_by_token = {"+": operator.add, "-": operator.sub, ...}
        #
        # Ainda assim, eu prefiro ser mais explícito que sucinto. Demora mais pra escrever
        # mas muito menos pra ler, e dar manutenção nisso é muito mais fácil do que se tivesse
        # uma ou duas camadinhas extras de abstração!
        #
        # Também cabe dizer que eu não tenho medo de usar 's/regex/repl/g' no meu editor de texto
        # preferido (Vim), para fazer find-and-replace espertos em várias linhas! Recomendo
        # fortemente que você pratique isso no seu editor de preferência.
        case Binary(location, lhs, op, rhs):
            lhs = evaluate0(env, lhs)
            rhs = evaluate0(env, rhs)
            return run_op(lhs, op, rhs, location)

        # A função principal do Let não é criar um novo valor, mas sim um novo environment.
        # Nós avaliamos 'value' e associamos ao nome 'name' em um novo environment,
        # construído sobre o anterior.
        #
        # A maior diferença está no tratamento do Let de uma função anônima. Para outras
        # variáveis, não faz sentido permitir que uma variável se refira a si mesmo:
        #
        #     let x = f(x + 1);  // Se não existir um x definido anteriormente, isso gera um erro.
        #
        # Mas para funções, queremos poder chamá-las recursivamente (ainda mais em uma linguagem
        # sem loops):
        #
        #     let pot = fn(a, b) {     // pot(a, b) calcula a^b.
        #       let step = fn(i, x) {  // invariante: x = a^i
        #         if i == b { x }
        #         else      { step(i + 1, x * a) }
        #       };
        #       step(0, 1)
        #     }
        #
        # Perceba que 'fn(i, x)' é avaliada no escopo de 'pot', e portanto captura as variáveis 'a' e 'b',
        # que são referenciadas no seu corpo. Contudo, ela também referencia 'step', que _não estaria_ no
        # environment no momento da sua definição. Tratamos as Closures, então, como um caso especial.
        #
        # Note que, com isso, não conseguimos referenciar uma função anterior no corpo de outra com o mesmo
        # nome.
        case Let(name=name, value=value, next=next):
            val = evaluate0(env, value)
            next_env = env.with_values({name.text: val})
            if isinstance(val, Closure):
                # Cria nova Closure contendo a definição de name.
                new_val = Closure(val.function, next_env)
                # Modifica o dicionário do env para usar a nova Closure.
                next_env.values[name.text] = new_val
            return evaluate0(next_env, next)

        # Por fim, implementamos chamadas, ou aplicações, de função.
        #
        # Nós pareamos os parâmetros declarados da função com os argumentos passados.
        # Com isso, construímos um novo environment com base no environment capturado da closure.
        # Pos fim, basta avaliar a função com esse novo environment.
        case Call(location, callee, arguments):
            f = evaluate0(env, callee)
            if not isinstance(f, Closure):
                raise ExecutionError(location, f"'{f}' is not callable")
            if len(arguments) != len(f.function.parameters):
                raise ExecutionError(
                    location,
                    f"'{f.function}' called with {len(arguments)} arguments"
                    f" (expecting {len(f.function.parameters)})",
                )
            values = (evaluate0(env, arg) for arg in arguments)
            params = {
                param.text: value for param, value in zip(f.function.parameters, values)
            }
            call_env = f.env.with_values(params)
            return evaluate0(call_env, f.function.value)

        case _:
            raise ExecutionError(
                term.location, f"Unexpected type {type(term).__name__}"
            )


# ---- Main ----


def main(node: Node):
    print(node)
    print()

    # Executa o arquivo. Note que não estou imprimindo o resultado de run_file, para
    # não confundir com um possível print de dentro da linguagem.
    run_file0(node)


if __name__ == "__main__":
    from argparse import ArgumentParser
    from pathlib import Path

    """
    Eu tenho por hábito sempre usar argparse.ArgumentParser, mesmo que pudesse só ler
    o parâmetro direto de 'sys.argv'. Não custa quase nada, você tem um --help pra se
    lembrar como seu script funciona, e invariavelmente eles só vão acumulando mais
    opções, que ficam difíceis de gerenciar sem um parser de flags de linha de comando.
    """

    p = ArgumentParser()
    p.add_argument("file", type=Path, help="AST file to execute")
    args = p.parse_args()

    # Temporariamente aumenta o limite de recursão para as bibliotecas json e cattrs,
    # que dependem de recursão para construir objetos.
    limit = sys.getrecursionlimit()
    print(f"Default recursion limit: {limit}")
    sys.setrecursionlimit(10000)

    # Aqui finalmente usamos o converter que construímos para os Node da árvore, contendo
    # alguns hooks customizados de desserialização.
    with args.file.open() as f:
        ast = json.load(f)
    node = ast_converter().structure(ast, File)

    # Restaura o limite default.
    sys.setrecursionlimit(limit)
    main(node)
