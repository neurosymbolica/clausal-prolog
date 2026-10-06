# clausal-spacy

[spaCy](https://spacy.io) predicates for [Clausal Prolog](https://github.com/neurosymbolica/clausal-prolog).

Wraps spaCy's NLP pipeline as Clausal Prolog predicates: model
management, tokenisation, linguistic annotations, named entities,
sentences, noun chunks and vector similarity.

## Install

```
pip install clausal-spacy
```

`spacy` is pulled in as a dependency. Download at least one model,
for example `python -m spacy download en_core_web_sm`. Requires Python 3.13 or later.

## Use

Import the predicates into a seam (`.seam`) module, as the package's own
tests do. A Clausal Prolog (`.clausal`) module reaches Python only through
the seam: put the imports in a `.seam` module and list it under
`[tool.clausal] python_bridges` in your project's `pyproject.toml` (see
[Importing Prolog](https://github.com/neurosymbolica/clausal-prolog/blob/main/docs/importing_prolog.md)).

This test, from [`tests/fixtures/spacy_basic.seam`](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-spacy/tests/fixtures/spacy_basic.seam),
shows the shape of a call:

```seam
-import_from(spacy, [load_model, process, token, token_text])

setup(DOC) <- (load_model("en_core_web_sm", "test") and process("test", "Apple is looking at buying U.K. startup for $1 billion.", DOC))

test("token iteration") <- (setup(DOC) and token(DOC, TOK) and token_text(TOK, "Apple"))
```

## Documentation

- [spaCy NLP Module](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-spacy/docs/spacy.md)
- [Predicate renames (2026-10-02)](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-spacy/docs/RENAMES.md)

## License

MIT
