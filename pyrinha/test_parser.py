import pytest
from unittest.mock import ANY

from pyrinha.nodes import *
from pyrinha.parser import *


int_ = lambda i: Int(ANY, i)
str_ = lambda s: Str(ANY, s)
bool_ = lambda x: Bool(ANY, x)


var = lambda s: Var(ANY, s)
param = lambda s: Parameter(ANY, s)


let = lambda name, value, next_: Let(ANY, param(name), value, next_)
if_ = lambda cond, then, other: If(ANY, cond, then, other)
fn = lambda *args: Function(ANY, [param(p) for p in args[:-1]], args[-1])
call = lambda *args: Function(ANY, args[0], args[1:])


print_ = lambda x: Print(ANY, x)
first = lambda x: First(ANY, x)
second = lambda x: Second(ANY, x)
tuple_ = lambda x, y: Tuple(ANY, x, y)


token_operator = {}
for op in BinaryOp:
    token_operator[op.value.token] = op

op = lambda lhs, token, rhs: Binary(ANY, lhs, token_operator[token], rhs)


@pytest.mark.parametrize(
    "text, ast",
    [
        ("1", int_(1)),
        ('"xyz"', str_("xyz")),
        ("xyz", var("xyz")),
        ("(a, b)", tuple_(var("a"), var("b"))),
        ("(a, (b, c))", tuple_(var("a"), tuple_(var("b"), var("c")))),
        ("true", bool_(True)),
        ("false", bool_(False)),
        ("+123", int_(123)),
        ("+ 123", int_(123)),
        ("- 123", int_(-123)),
        ('""', str_("")),
        ('"\n"', str_("\n")),
        (r'"\""', str_('"')),
        (r'"C:\\Documents"', str_("C:\\Documents")),
        ("lettuce ==iff", op(var("lettuce"), "==", var("iff"))),
        ("1 ++2 --3", op(op(int_(1), "+", int_(2)), "-", int_(-3))),
    ],
)
def test_parse(text, ast):
    assert ast == RinhaParser(text).term()
