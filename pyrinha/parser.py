from pathlib import Path
from contextlib import contextmanager

from attrs import define, frozen
import regex as re

from pyrinha.nodes import *


@frozen
class ParseError(Exception):
    text: str
    pos: int
    msg: str


@define
class BaseParser:
    text: str
    pos: int = 0

    def is_at_end(self) -> bool:
        "Retorna se alcançamos o final do texto."
        return self.pos >= len(self.text)

    def peek(self) -> "str":
        "Retorna o caractere na posição atual."
        if self.is_at_end():
            return ""
        return self.text[self.pos]

    def lookahead(self, pattern: str) -> re.Match | None:
        "Testa o regex na posição atual do texto."
        return re.match(pattern, self.text[self.pos :])

    def match(self, pattern: str) -> re.Match | None:
        "Testa o regex e avança a posição em caso de match."
        m = self.lookahead(pattern)
        if m:
            self.pos += m.end()
        return m

    def expect(self, pattern: str, msg: str = None) -> re.Match:
        "Consome o regex, ou lança uma exceção caso não dê match."
        m = self.match(pattern)
        if not m:
            self.fail(msg or f"expecting pattern {pattern}")
        return m

    def fail(self, msg: str):
        "Lança uma exceção com informação do contexto."
        raise ParseError(self.text, self.pos, msg)

    def ws(self):
        "Consome espaços em branco, incluindo comentários."
        while True:
            # Ignora espaços em branco.
            self.match(r"\s*")

            # Line comment, começando com '//'.
            #
            # A diretiva '(?m)' ativa a flag MULTILINE, que trata '$' como
            # o caractere LF ('\n') e também como o fim da string.
            if self.match(r"(?m)//.*$"):
                continue

            # Comentários de múltiplas linhas, com '/* ... */'.
            #
            # A diretiva '(?s)' ativa a flag DOTALL, que faz com que o '.'
            # dê match em todos os caracteres, inclusive LF.
            #
            # É necessário escapar o asterisco do delimitador de comentário, e eu
            # acho mais... hm, simétrico... usar '[*]' (uma character class contendo
            # somente o asterisco) do que '\*'
            #
            # Perceba que usei '.*?' para buscar todos os caracteres de forma non-greedy.
            # Sem o '?', na string '1 /* 2 */ 3 /* 4 */ 5', o '/*' entre 1 e 2 iria dar match
            # com o '*/' entre 4 e 5!
            if self.match(r"(?s)/[*].*?[*]/"):
                continue

            # Sem mais comentários.
            break


@define
class OpenLocation:
    filename: str
    start: int
    end: int = None

    @property
    def location(self) -> Loc:
        assert self.end is not None, "location is still open"
        return Loc(self.filename, self.start, self.end)


"""
Expressão com operadores de exemplo:

      1 +  2 * 3   - 4  ==   5 / 6  / 7   ==  8 <= 9   &&  10 > 11   ||  12 != 13

Expressão anterior com a mesma precedência, usando parênteses para indicá-las:

((((((1 + (2 * 3)) - 4) == ((5 / 6) / 7)) == (8 <= 9)) && (10 > 11)) || (12 != 13))

Sequência de leitura dos tokens, com a estrutura e precedência a cada passo.
O operador sendo manipulado está marcado com '
Para melhor legibilidade, alguns operandos são resumidos com .

token | head                           | head prec. | op prec.
------|--------------------------------|------------|---------
1     |  1                             |         99 |       99
+     | '(1 + ø)                       |         30 |       30
2     | '(1 + 2)                       |         30 |       30
*     |  (1 + '(2 * ø))                |         30 |       40
3     |  (1 + '(2 * 3))                |         30 |       40
-     | '((1 + .) - ø)                 |         30 |       30
4     | '((1 + .) - 4)                 |         30 |       30
==    | '((. - 4) == ø)                |         20 |       20
5     | '((. - 4) == 5)                |         20 |       20
/     |  ((. - 4) == '(5 / ø))         |         20 |       40
6     |  ((. - 4) == '(5 / 6))         |         20 |       40
/     |  ((. - 4) == '((5 / 6) / ø))   |         20 |       40
7     |  ((. - 4) == '((5 / 6) / 7))   |         20 |       40
==    | '((. == (. / 7)) == ø)         |         20 |       20
8     | '((. == (. / 7)) == 8)         |         20 |       20
<=    |  ((. == (. / 7)) == '(8 <= ø)) |         20 |       20
9     |  ((. == (. / 7)) == '(8 <= 9)) |         20 |       20
&&    | '((. == (8 <= 9)) && ø)        |         10 |       10
10    | '((. == (8 <= 9)) && 10)       |         10 |       10
>     |  ((. == (8 <= 9) && (10 > ø)   |         10 |       20
11    |  ((. == (8 <= 9) && (10 > 11)  |         10 |       20
||    | '((. && (10 > 11)) || ø)       |          5 |       5
12    | '((. && (10 > 11)) || 12)      |          5 |       5
!=    |  ((. && .) || (12 != ø)        |          5 |       20
13    |  ((. && .) || (12 != 13))      |          5 |       20
''    | end

Pseudo código:

    def read_operation():
        term := read_subterm()
        head := operand := Operand(term, Operator(precedence=99))

        while not is_at_end():
            operator := read_operator()
            term := read_subterm()
            if operator.precedence < operand.precedence:
                operand := operand.rhs := Operand(term, operator)
            else:
                operand.rhs := term
                head := operand := Operand(head, operator)

        return head.to_term()
"""


@define
class Operand:
    lhs: "Term | Operand"
    op: BinaryOp
    rhs: "Term | Operand | None" = None

    def to_term(self, parser) -> Term:
        inbox: list[Term | Operand | None] = [self]
        output: list[Term] = []
        while inbox:
            arg = inbox.pop()
            match arg:
                case Operand(lhs, op, rhs):
                    inbox += [op, rhs, lhs]
                case Term() as t:
                    output += [t]
                case BinaryOp():
                    rhs = output.pop()
                    lhs = output.pop()
                    loc = Loc(
                        lhs.location.filename, lhs.location.start, rhs.location.end
                    )
                    output += [Binary(loc, lhs, arg, rhs)]
                case None:
                    parser.fail(f"Attempting to convert incomplete operation {self}")
                case _:
                    parser.fail(f"Unexpected argument in {self}")
        assert len(output) == 1, output
        return output[0]


@define
class RinhaParser(BaseParser):
    filename: str = ""

    @classmethod
    def parse_file(cls, path: Path) -> File:
        with path.open() as f:
            text = f.read()

        parser = cls(text, filename=str(path))
        with parser.open_location() as l:
            parser.ws()
            term = parser.term()
            parser.ws()
        return File(l.location, str(path), term)

    @contextmanager
    def open_location(self):
        loc = OpenLocation(self.filename, self.pos)
        yield loc
        loc.end = self.pos

    def term(self) -> Term:
        return self.term2()

    def term2(self) -> Term:
        term = self.term1()

        self.ws()
        operator = self.operator()
        if not operator:
            return term

        operand = Operand(term, operator)
        head = operand

        while not self.is_at_end():
            self.ws()
            term = self.term1()

            self.ws()
            operator = self.operator()
            if not operator:
                operand.rhs = term
                break

            if operator.value.precedence < operand.op.value.precedence:
                # Operador de menor precedência associa o termo a si mesmo e
                # se torna o operando atual. O head permanece o mesmo.
                #
                # head:(1 < operand:(2 + ø)), tokens=[3 *]
                # => head:(1 < (2 + operand:(3 * ø)))
                operand.rhs = Operand(term, operator)
                operand = operand.rhs
            else:
                # Operador de precedência maior ou igual associa o termo ao
                # operando atual, e se torna o novo head.
                #
                # head:(1 < operand:(2 * ø)), tokens=[3 &&]
                # => head:operand:((1 < (2 * 3)) && ø)
                operand.rhs = term
                operand = Operand(head, operator)
                head = operand

        return head.to_term(self)

    def operator(self) -> BinaryOp | None:
        match ch := self.peek():
            case "*":
                self.expect(r"[*]")
                return BinaryOp.MUL
            case "/":
                self.expect(r"/")
                return BinaryOp.DIV
            case "%":
                self.expect(r"%")
                return BinaryOp.REM
            case "+":
                self.expect(r"[+]")
                return BinaryOp.ADD
            case "-":
                self.expect(r"-")
                return BinaryOp.SUB
            case "=":
                self.expect(r"==")
                return BinaryOp.EQ
            case "!":
                self.expect(r"!=")
                return BinaryOp.NEQ
            case "<":
                if self.match(r"<="):
                    return BinaryOp.LTE
                self.expect("<")
                return BinaryOp.LT
            case ">":
                if self.match(r">="):
                    return BinaryOp.GTE
                self.expect(">")
                return BinaryOp.GT
            case "&":
                self.expect("&&")
                return BinaryOp.AND
            case "|":
                self.expect(r"[|][|]")
                return BinaryOp.OR
            case ")" | "," | "}" | ";" | "":
                # End of operation.
                return None
            case _:
                self.fail(f"Unexpected character {ch}, expecting operator.")

    def term1(self) -> Term:
        term = self.term0()
        self.ws()
        while self.peek() == "(":
            # Function call
            args = self.call_args()
            loc = Loc(term.location.filename, term.location.start, self.pos)
            term = Call(loc, term, args)
            self.ws()
        return term

    def term0(self) -> Term:
        match ch := self.peek():
            case "(":
                # Tuple (x, y) or grouping (1 + 2)
                return self.tuple_or_group()
            case '"':
                # String
                return self.string()
            case "+" | "-":
                # Unary plus or minus
                return self.signed_number()
            case "f":
                # First, fn, false
                if self.lookahead(r"first\b"):
                    return self.first()
                if self.lookahead(r"fn\b"):
                    return self.fn()
                if self.lookahead(r"false\b"):
                    return self.false()
            case "i":
                # If
                if self.lookahead(r"if\b"):
                    return self.if_()
            case "l":
                # Let
                if self.lookahead(r"let\b"):
                    return self.let()
            case "p":
                # Print
                if self.lookahead(r"print\b"):
                    return self.print()
            case "s":
                # Second
                if self.lookahead(r"second\b"):
                    return self.second()
            case "t":
                # True
                if self.lookahead(r"true\b"):
                    return self.true()
            case "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9":
                # Number
                return self.number()
            case _:
                pass
        # Variable
        return self.var()

    def call_args(self):
        self.expect(r"[(]")
        args = []
        while self.peek() != ")":
            self.ws()
            args.append(self.term())
            self.ws()
            if not self.match(r","):
                break
        self.expect(r"[)]")

        return args

    def tuple_or_group(self):
        with self.open_location() as l:
            self.expect("[(]")
            first = self.term()
            self.ws()
            if not self.match(r","):
                second = None
            else:
                self.ws()
                second = self.term()
                self.ws()
            self.expect("[)]")

        if not second:
            return first
        return Tuple(l.location, first, second)

    def string(self):
        with self.open_location() as l:
            m = self.expect(r'"([^\"]|\"|\\)*"', "expecting string")
            text = m.group()
            text = text[1:-1]
            text = text.replace(r"\\", "\\")
            text = text.replace(r"\"", '"')
        return Str(l.location, text)

    def signed_number(self):
        with self.open_location() as l:
            m = self.expect(r"[+-]")
            sign = +1 if m.group() == "+" else -1
            self.ws()
            num = self.number_value()

        return Int(l.location, sign * num)

    def number(self):
        with self.open_location() as l:
            num = self.number_value()

        return Int(l.location, num)

    def first(self):
        with self.open_location() as l:
            self.expect("first")
            self.ws()
            arg = self.one_arg()
        return First(l.location, arg)

    def second(self):
        with self.open_location() as l:
            self.expect("second")
            self.ws()
            arg = self.one_arg()
        return Second(l.location, arg)

    def print_(self):
        with self.open_location() as l:
            self.expect("print")
            self.ws()
            arg = self.one_arg()
        return Print(l.location, arg)

    def one_arg(self):
        self.expect("[(]")
        self.ws()
        arg = self.term()
        self.ws()
        self.expect("[)]")
        return arg

    def fn(self):
        with self.open_location() as l:
            self.expect(r"fn")
            self.ws()
            self.expect(r"[(]")
            params = []
            while self.peek() != ")":
                self.ws()
                params.append(self.parameter())
                self.ws()
                if not self.match(r","):
                    break
            self.expect(r"[)]")
            self.ws()
            value = self.block()

        return Function(l.location, value, params)

    def if_(self):
        with self.open_location() as l:
            self.expect(r"if")
            self.ws()
            condition = self.term()
            self.ws()
            then = self.block()
            self.ws()
            self.expect(r"else")
            self.ws()
            otherwise = self.block()

        return If(l.location, condition, then, otherwise)

    def let(self):
        with self.open_location() as l:
            self.expect(r"let")
            self.ws()
            name = self.parameter()
            self.ws()
            self.expect(r"=")
            self.ws()
            value = self.term()
            self.ws()
            self.expect(r";")
            self.ws()
            next_ = self.term()

        return Let(l.location, name, value, next_)

    def block(self):
        self.expect(r"{")
        self.ws()
        term = self.term()
        self.ws()
        self.expect(r"}")

        return term

    def true(self):
        with self.open_location() as l:
            self.expect("true")
        return Bool(l.location, True)

    def false(self):
        with self.open_location() as l:
            self.expect("false")
        return Bool(l.location, False)

    def var(self):
        with self.open_location() as l:
            text = self.symbol()
        return Var(l.location, text)

    def parameter(self):
        with self.open_location() as l:
            text = self.symbol()
        return Parameter(l.location, text)

    def symbol(self) -> str:
        m = self.expect(r"[a-zA-Z_]\w*")
        return m.group()

    def number_value(self) -> int:
        m = self.expect(r"\d+")
        return int(m.group())
