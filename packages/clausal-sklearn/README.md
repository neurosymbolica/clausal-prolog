# clausal-sklearn

[scikit-learn](https://scikit-learn.org) predicates for [Clausal Prolog](https://github.com/neurosymbolica/clausal-prolog).

Wraps scikit-learn as Clausal Prolog predicates: load datasets, build
and fit estimators, predict, score and transform. Data flows through
tagged tuples (`est`, `dataset`, `fitted`, `split`).

## Install

```
pip install clausal-sklearn
```

`scikit-learn` is pulled in as a dependency. Requires Python 3.13 or later.

## Use

Import the predicates into a seam (`.seam`) module, as the package's own
tests do. A Clausal Prolog (`.clausal`) module reaches Python only through
the seam: put the imports in a `.seam` module and list it under
`[tool.clausal] python_bridges` in your project's `pyproject.toml` (see
[Importing Prolog](https://github.com/neurosymbolica/clausal-prolog/blob/main/docs/importing_prolog.md)).

This test, from [`tests/fixtures/sklearn_basic.seam`](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-sklearn/tests/fixtures/sklearn_basic.seam),
shows the shape of a call:

```seam
-import_from(sklearn, [algorithm])

test("algorithm random_forest is classifier") <- (
    algorithm("random_forest", "classifier")
)
```

## Documentation

- [Clausal Prolog — scikit-learn (`sklearn` module)](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-sklearn/docs/sklearn.md)
- [Predicate renames (2026-10-02)](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-sklearn/docs/RENAMES.md)

## License

MIT
