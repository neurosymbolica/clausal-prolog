# clausal-laya

[laya](https://pypi.org/project/laya/) decision predicates for [Clausal Prolog](https://github.com/neurosymbolica/clausal-prolog).

laya is a non-autoregressive "System 1" decision engine: one forward pass
answers a set of typed questions about a text with calibrated probabilities,
in 100+ languages. This package makes those answers relations — neural
predicates whose solutions carry probabilities, for symbolic logic to filter,
rank and combine:

- `choice/4,5` — pick a label; or enumerate every label with its probability
- `noul/3` — the probability that a yes/no answer is yes
- `score/4,5` — a level on a scale; or every level with its probability
- `predict/3,4` — several questions in one forward pass

## Install

```
pip install clausal-laya
```

laya (with torch and transformers) is pulled in as a dependency. Requires
Python 3.13 or later. laya downloads its checkpoint from the Hugging Face Hub
on first use.

## Use

Import the predicates into a seam (`.seam`) module, as the package's own
tests do. A Clausal Prolog (`.clausal`) module reaches Python only through
the seam: put the imports in a `.seam` module and list it under
`[tool.clausal] python_bridges` in your project's `pyproject.toml` (see
[Importing Prolog](https://github.com/neurosymbolica/clausal-prolog/blob/main/docs/importing_prolog.md)).

This example, from [`tests/fixtures/docs/laya_examples.seam`](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-laya/tests/fixtures/docs/laya_examples.seam),
escalates a ticket when the model thinks the customer is leaving:

```seam
-import_from(py.laya, [noul])

escalate(TICKET) <- (
    noul(TICKET, "Does the user threaten to cancel or leave?", P),
    P > 0.5
)

test("a cancellation threat escalates") <- (
    escalate("Refund the duplicate charge today or we will cancel our plan.")
)
```

## Documentation

- [laya — calibrated decisions as relations](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-laya/docs/laya.md)

## License

MIT
