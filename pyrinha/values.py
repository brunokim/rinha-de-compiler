from attrs import frozen, field, define

from pyrinha.nodes import Function

__all__ = [
    "Value",
    "Literal",
    "Closure",
    "Env",
]

# ---- Values ----

"""
Até agora nós modelamos apenas a representação estática de um programa, na forma de
nós da árvore de sintaxe abstrata. Agora vamos modelar os valores de _runtime_ do
programa, que serão executados pelo interpretador.
"""


@define
class Value:
    pass


@frozen
class Literal(Value):
    "Literal contém um valor de Python wrapped como um valor de interpretador."
    x: int | str | bool | tuple[Value, Value]

    def __str__(self):
        match self.x:
            case int():
                return str(self.x)
            case str():
                return self.x
            case bool():
                return str(self.x).lower()


"""
Durante a execução, nós precisamos manter um registro de quais variáveis já foram
definidas, e associdas a qual valor. Por exemplo,

    let x = 10;
    print (x)

Na linha #2, a variável 'x' precisa estar associada ao valor 10, para sabermos o que
escrever na tela. Este registro se chama "environment", que modelamos no Env abaixo.

Nossa definição de Env copia todos os valores definidos anteriormente para um novo
dicionário e inclui (ou sobrescreve) novas associações. Um novo environment é criado
a cada 'Let', e ao invocar uma função, onde os parâmetros são associados aos valores
concretos dos argumentos. Veremos em mais detalhes no Interpretador.
"""


@frozen
class Env:
    # Apesar da classe ser marcada como 'frozen', ou imutável, isso não se estende
    # aos seus campos. Para garantir que o dict abaixo não seja modificado, precisamos
    # confiar apenas na nossa disciplina.
    values: dict[str, Value] = field(factory=dict, converter=dict)

    def with_values(self, extra: dict[str, Value]) -> Value:
        "Cria um novo Env com base no atual, e contendo as associações em extra"
        values = dict(self.values)
        values.update(extra)
        return Env(values)


"""
Além dos valores atômicos descritos anteriormente, também precisamos modelar uma
função anônima em tempo de execução. Funções podem ser passadas como parâmetros,
associadas a uma variável, e até impressas com 'print'.

Em runtime, uma função captura o environment onde ela foi declarada, para ser
pura e imutável. Considere por exemplo:

    let x = 1;                   // Env: {x: 1}
    let f = fn (a) { a + x };    // Env: {x: 1, f: <#closure>}
    let x = 2;                   // Env: {x: 2, f: <#closure>}
    print(f(10))

Ao chamar a função na linha 4, esperamos que imprima '11', tendo capturado o
valor de x definido na linha 1.
"""


@frozen
class Closure(Value):
    function: Function
    env: Env

    def __str__(self):
        return "<#closure>"
