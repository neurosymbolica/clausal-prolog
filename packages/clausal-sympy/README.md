# clausal-sympy

[SymPy](https://www.sympy.org) predicates for [Clausal Prolog](https://github.com/neurosymbolica/clausal-prolog).

Wraps SymPy as Clausal Prolog predicates for symbolic mathematics:
simplify, expand, factor, solve, differentiate, integrate and more.
Logic variables and arithmetic operators convert to SymPy expressions
directly.

## Install

```
pip install clausal-sympy
```

`sympy` is pulled in as a dependency. Requires Python 3.13 or later.

## Use

Import the predicates into a seam (`.seam`) module, as the package's own
tests do. A Clausal Prolog (`.clausal`) module reaches Python only through
the seam: put the imports in a `.seam` module and list it under
`[tool.clausal] python_bridges` in your project's `pyproject.toml` (see
[Importing Prolog](https://github.com/neurosymbolica/clausal-prolog/blob/main/docs/importing_prolog.md)).

This test, from [`tests/fixtures/sympy_algebra.seam`](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-sympy/tests/fixtures/sympy_algebra.seam),
shows the shape of a call:

```seam
-import_from(sympy, [collect, sym_equal])

test("collect by x") <- (
    collect(X**2 + 2*X + X*Y, X, R),
    sym_equal(R, X**2 + X*(Y + 2))
)
```

## Documentation

- [Symbolic Math (`sympy`)](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-sympy/docs/sympy.md)
- [Predicate renames (2026-10-02)](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-sympy/docs/RENAMES.md)

## License

MIT
