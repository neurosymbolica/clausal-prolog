# clausal-yaml

[PyYAML](https://pyyaml.org) predicates for [Clausal Prolog](https://github.com/neurosymbolica/clausal-prolog).

Wraps PyYAML (`safe_load` / `safe_dump`) as Clausal Prolog predicates
for reading and writing YAML text and files. Data is represented as
plain Python values.

## Install

```
pip install clausal-yaml
```

`pyyaml` is pulled in as a dependency. Requires Python 3.13 or later.

## Use

Import the predicates into a seam (`.seam`) module, as the package's own
tests do. A Clausal Prolog (`.clausal`) module reaches Python only through
the seam: put the imports in a `.seam` module and list it under
`[tool.clausal] python_bridges` in your project's `pyproject.toml` (see
[Importing Prolog](https://github.com/neurosymbolica/clausal-prolog/blob/main/docs/importing_prolog.md)).

This test, from [`tests/fixtures/yaml_basic.seam`](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-yaml/tests/fixtures/yaml_basic.seam),
shows the shape of a call:

```seam
-import_from(yaml, [read, get])

test("parse mapping") <- (
    read("name: alice\nage: 30", DATA),
    get(DATA, "name", "alice"),
    get(DATA, "age", 30)
)
```

## Documentation

- [Clausal Prolog — YAML (`yaml` module)](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-yaml/docs/yaml.md)

## License

MIT
