import json
from pathlib import Path
from textwrap import indent, dedent

from attrs import field, define, frozen
from cattrs import structure, unstructure, Converter


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
class Symbol(Node):
    text: str

    def __str__(self):
        return self.text


@frozen
class Let(Term):
    name: Symbol
    value: Term
    next: Term

    def __str__(self):
        return f"""\
let {self.name} = {self.value};
{self.next}"""


@frozen
class Function(Term):
    value: Term
    parameters: tuple[Symbol, ...] = field(factory=tuple, converter=tuple)

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


@frozen
class Binary(Term):
    lhs: Term
    op: str
    rhs: Term

    def __str__(self):
        return f"{self.lhs} {self.op} {self.rhs}"


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


converter = Converter()

term_classes = [Let, Function, If, Binary, Call, Print, Var, Int, Str]
term_by_name = {cls.__name__: cls for cls in term_classes}


def structure_generic_term(obj, t):
    cls_name = obj["kind"]
    return converter.structure(obj, term_by_name[cls_name])


converter.register_structure_hook_func(lambda cls: cls == Term, structure_generic_term)


def main(ast_obj):
    node = converter.structure(ast_obj, File)
    print(node)


if __name__ == "__main__":
    with Path("files/fib.json").open() as f:
        ast = json.load(f)
    main(ast)
