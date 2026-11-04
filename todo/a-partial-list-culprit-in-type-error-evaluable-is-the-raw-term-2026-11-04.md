# A partial list in an arithmetic expression is named by the term, not Name/Arity

Found 2026-11-04 while adding the cyclic-evaluation rows
(`tests/iso/test_cyclic_eval_scryer.py`). Not about cycles: the acyclic
partial list does it too. ISO's culprit for `type_error(evaluable, _)` is a
`Name/Arity` indicator.

## What / Repro

| goal | Clausal | Scryer (in a clause) |
|---|---|---|
| `_ is [1\|_]` | `type_error(evaluable,[1\|_])` | |
| `X = [1\|X], _ is X` | `type_error(evaluable,[1\|_])` | `type_error(evaluable,'.'/2)` |
| `X = [X\|X], _ is X` | `type_error(evaluable,[...\|...])` | toplevel: `instantiation_error` |
| `_ is [1\|foo]` | `type_error(evaluable,'.'/2)` (right) | |

`iso_compare._evaluable_culprit` passes a shape with no functor/arity
through unchanged, and `_helpers._arity` has no answer for the partial-list
representation. It should be `'.'/2`, as for a proper list.
