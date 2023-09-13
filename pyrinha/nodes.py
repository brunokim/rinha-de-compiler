"""
Compilador para Rinha, a linguagem funcional da rinha de compiladores.

Vou fazer este projeto buscando ser educativo, como provocado pelo Hillel Wayne
(https://buttondown.email/hillelwayne/archive/educational-codebases/). Seções
como esta são voltadas para explicar a lógica por trás do design.
"""

from enum import Enum
from textwrap import indent

"""
Eu uso _muito_ a biblioteca 'attrs' para definir classes. Ela é a precursora das
dataclasses, e possui mais capacidades além da biblioteca padrão que justificam
usá-la (https://www.attrs.org/en/stable/why.html#data-classes).

A biblioteca 'cattrs' é uma companheira de 'attrs' para conversão de classes para
dicts.
"""

from attrs import field, frozen
from cattrs import Converter

"""
É sempre uma boa prática definir com __all__ tudo que seu módulo exporta quando
fizerem 'import star'

    from pyrinha.ast import *

Isto não impede que acessem outros símbolos, mas no mínimo precisam ser explícitos
sobre isso.
"""

__all__ = [
    "Loc",
    "Node",
    "Term",
    "File",
    "Parameter",
    "Let",
    "Function",
    "If",
    "BinaryOp",
    "Binary",
    "Call",
    "Print",
    "Var",
    "Int",
    "Str",
    "Bool",
    "Tuple",
    "First",
    "Second",
    "ast_converter",
]

"""
Nesta seção, estou definindo classes para representar os atributos de AST da 
linguagem Rinha conforme a especificação:
https://github.com/brunokim/rinha-de-compiler/blob/main/SPECS.md

Cada 'Node' da AST possui um método __str__ para facilitar o debug. Eu quis
que esse método emitisse uma representação mais próxima da linguagem original,
portanto tenho que me preocupar com indentação. Para isso, uso a função
textwrap.indent da biblioteca padrão.

Um defeito deste método de serialização -- e da "desserialização" executada
pela biblioteca cattrs -- é que ela opera por chamadas recursivas, onde uma AST
mais extrema pode causar um RecursionError. Por exemplo, uma operação como

    1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + 1 + ...

Iria produzir uma AST muito profunda:

    Binary(
        Int(1),
        ADD,
        Binary(
            Int(1),
            ADD,
            Binary(
                Int(1),
                ADD,
                ...)))

Temos que pensar que a AST é uma entrada de usuário, e que nosso código pode
ser alvo de agentes maliciosos. Mais para frente irei implementar métodos
iterativos para operar sobre a AST, que são mais robustos.
"""

# ---- AST ----


@frozen
class Loc:
    start: int
    end: int
    filename: str


@frozen
class Node:
    location: Loc


@frozen
class Term(Node):
    pass


@frozen
class File(Node):
    name: str
    expression: Term

    def __str__(self):
        return str(self.expression)


@frozen
class Parameter(Node):
    text: str

    def __str__(self):
        return self.text


@frozen
class Let(Term):
    name: Parameter
    value: Term
    next: Term

    def __str__(self):
        return f"""\
let {self.name} = {self.value};
{self.next}"""


"""
A classe 'Function' usa mais uma feature da biblioteca 'attrs', para
definir propriedades extras de um campo.

Em geral, basta declarar um campo usando a sintaxe de tipos de Python
para que 'attrs' inclua ele no __init__, mas usando field() podemos
especificar um valor default, ou uma factory para gerá-lo. A factory
deve ser uma função com 0 argumentos, então podemos usar as funções
list(), tuple(), dict(), etc.

Podemos também especificar um converter, que nos permite aceitar um
tipo mais genérico no __init__ e garantir que internamente temos o
tipo certo.
"""


@frozen
class Function(Term):
    value: Term
    parameters: tuple[Parameter, ...] = field(factory=tuple, converter=tuple)

    def __str__(self):
        value = indent(str(self.value), "  ")
        params = ", ".join(str(param) for param in self.parameters)
        return f"""\
fn ({params}) => {{
{value}
}}"""


@frozen
class If(Term):
    condition: Term
    then: Term
    otherwise: Term

    def __str__(self):
        then = indent(str(self.then), "  ")
        otherwise = indent(str(self.otherwise), "  ")
        return f"""\
if {self.condition} {{
{then}
}} else {{
{otherwise}
}}"""


"""
A classe 'Operator' descreve um operador binário. O campo 'precedence'
é usado para definir se uma operação precisa ou não de parênteses
ao ser escrita. Por exemplo, a operação

    Binary(Int(1), MUL, Binary(Int(2), ADD, Int(3)))

precisa ser escrita como
    
    1 * (2 + 3)

mas a operação

    Binary(Int(1), ADD, Binary(Int(2), MUL, Int(3)))

pode ser escrita como

    1 + 2 * 3

Portanto, se ao escrever um operador, ele tiver uma precedência menor do
que a do operador atual, devemos usar parênteses.

O campo 'assoc' pretende determinar se operações com operadores de mesma
precedência deve ou não usar parênteses. Para os operadores aritméticos
é esperado que não, mas para operadores lógicos pode ser necessário.
Considere por exemplo, a diferença entre estas expressões:

    Binary(Int(1), EQ, Binary(Int(2), EQ, Var("true")))
    Binary(Binary(Int(1), EQ, Int(2)), EQ, Var("true"))

Eu acho melhor que elas sejam sempre serializadas como

    1 == (2 == true)
    (1 == 2) == true
"""


@frozen
class Operator:
    token: str
    precedence: int
    assoc: bool = True


"""
Os valores de precedência são arbitrários. Eu comecei com 30 e fui
adicionando os outros pensando se eu gostaria ou não que uma operação
combinada tivesse parênteses.

Usar valores separados por 10 ajuda a enfiar outros valores no meio
depois. Essa técnica vem desde o tempo dos cartões perfurados, quando
cada um era numerado. Se você quisesse adicionar um cartão no meio de
dois que você já tinha, bastava usar um número intermediário aos já
utilizados.
"""


class BinaryOp(Enum):
    ADD = Operator("+", 30)
    SUB = Operator("-", 30)
    MUL = Operator("*", 40)
    DIV = Operator("/", 40)
    REM = Operator("%", 40)
    EQ = Operator("==", 20, assoc=False)
    NEQ = Operator("!=", 20, assoc=False)
    LT = Operator("<", 20)
    GT = Operator(">", 20)
    LTE = Operator("<=", 20)
    GTE = Operator(">=", 20)
    AND = Operator("&&", 10)
    OR = Operator("||", 5)


@frozen
class Binary(Term):
    lhs: Term
    op: BinaryOp
    rhs: Term

    def __str__(self):
        self_precedence = self.op.value.precedence
        lhs_precedence = (
            self.lhs.op.value.precedence if isinstance(self.lhs, Binary) else 99
        )
        rhs_precedence = (
            self.rhs.op.value.precedence if isinstance(self.rhs, Binary) else 99
        )

        lhs = str(self.lhs)
        if lhs_precedence < self_precedence:
            lhs = f"({lhs})"

        rhs = str(self.rhs)
        if rhs_precedence < self_precedence:
            rhs = f"({rhs})"

        return f"{lhs} {self.op.value.token} {rhs}"


@frozen
class Call(Term):
    callee: Term
    arguments: tuple[Term, ...] = field(factory=tuple, converter=tuple)

    def __str__(self):
        callee = str(self.callee)
        if not isinstance(self.callee, Var):
            callee = f"({callee})"
        args = ", ".join(str(arg) for arg in self.arguments)
        return f"{callee}({args})"


@frozen
class Print(Term):
    value: Term

    def __str__(self):
        return f"print ({self.value})"


@frozen
class Var(Term):
    text: str

    def __str__(self):
        return self.text


@frozen
class Int(Term):
    value: int

    def __str__(self):
        return str(self.value)


@frozen
class Str(Term):
    value: str

    def __str__(self):
        return repr(self.value)


@frozen
class Bool(Term):
    value: bool

    def __str__(self):
        return "true" if self.value else "false"


@frozen
class Tuple(Term):
    first: Term
    second: Term

    def __str__(self):
        return f"({self.first}, {self.second})"


@frozen
class First(Term):
    value: Term

    def __str__(self):
        return f"first({self.value})"


@frozen
class Second(Term):
    value: Term

    def __str__(self):
        return f"second({self.value})"


"""
Estas variáveis visam criar uma relação entre (nome da class Term) -> classe.
Isto é útil para podermos converter um objeto serializado da AST, que possui
um membro "kind" descrevendo a classe, para a classe em si.

Talvez fosse possível construir essa lista com alguma mágica de __new__ dentro
de Term, o que garantiria que uma nova classe Term sempre estará presente, mas
preferi fazer desse jeito repetitivo e simples.
"""

term_classes = [Let, Function, If, Binary, Call, Print, Var, Int, Str, Bool]
term_by_kind = {cls.__name__.lower(): cls for cls in term_classes}

# ---- Read AST ----


def ast_converter():
    converter = Converter()

    """
    A biblioteca 'cattrs' precisa de um pouco de customização antes de conseguir
    desserializar ("structure") a AST da Rinha.

    Em geral, ela utiliza os tipos incluídos na definição das classes para determinar
    qual método usar. Por exemplo, considere o dict:

        {
            "kind": "Let",
            "name": {"text": "x"},
            "value": {"kind": "Var", "text": "true"},
        }

    Se já estamos estruturando um Let, ao chegar no campo 'name' sabemos pela anotação
    de tipos que este deve ser um Parameter. Contudo, no campo 'value' a anotação contém
    Term, que é uma classe abstrata. Queremos neste momento ler o campo 'kind' do dict
    para decidir estruturar um Var.

    É isso que a função 'structure_generic_term' faz abaixo, onde usamos o dict
    'term_by_kind' definido anteriormente.
    """

    def structure_generic_term(obj, t):
        cls_name = obj["kind"].lower()
        return converter.structure(obj, term_by_kind[cls_name])

    """
    Ao registrar a função 'structure_generic_term' para conversão de Terms, precisamos
    limitá-la condicionalmente _apenas_ ao tipo Term, sem incluir seus subtipos.

    Isto é necessário porque a função internamente chama structure novamente. Porém, a classe
    passada como parâmetro também é um Term, e 'structure_generic_term' é chamada novamente!
    Para sair do loop infinito, basta passar o predicado 'lambda cls: cls == Term', que
    faz com que o hook só seja invocado quando cls for igual a, e não um subtipo de Term.

    Portanto, a chamada a structure usa uma classe concreta como Let, Binary, etc., que
    irá utilizar o mecanismo interno de 'cattrs' para desserialização.
    """

    converter.register_structure_hook_func(
        lambda cls: cls == Term, structure_generic_term
    )

    """
    Precisamos também customizar a desserialização de BinaryOp, porque por padrão 'cattrs'
    utiliza o _valor_ do Enum como chave para a instância, e nós queremos usar o _nome_.
    """

    converter.register_structure_hook(BinaryOp, lambda obj, t: BinaryOp[obj.upper()])

    return converter
