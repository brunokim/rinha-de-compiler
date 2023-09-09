# PyRinha

Este projeto visa ser mais educativo que pauleira na Rinha... por enquanto.

A ordem de leitura recomendada é:

- [nodes.py](nodes.py) -- Define os nós da AST de Rinha (não podemos usar o nome
    "ast.py" porque isto conflita com um pacote interno do Python...)
- [values.py](values.py) -- Define os valores de runtime de Rinha
- [interpreter0.py](interpreter0.py) -- Primeira implementação de um interpretador,
   com um método de tree walking e totalmente recursivo (e ineficiente).


## Execução

Da pasta raiz do repositório:

    python -m pyrinha.interpreter0 files/fib1.json
