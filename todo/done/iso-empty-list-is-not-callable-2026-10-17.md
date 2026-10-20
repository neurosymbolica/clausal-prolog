# `[]` is not callable as a clause head or goal (ISO: it is an atom)

**Status: FIXED 2026-10-20 (commit e719d761).** A head or body goal `[]` now names the predicate keyed `"[]"` (the native front end, call/N, solve/1, clause/2, the assert/retract head gate, abolish/1, listing/1, current_predicate/1 and the directives' indicators), so `[].`, `'[]'.` and `call([])` work and an undefined `[]` is `existence_error(procedure, []/0)`. Pinned in tests/iso_l3/test_l3_empty_list_callable.py::test_a_text_may_define_and_call_the_empty_list (and the file's other tests, .pl and .clausal).

Filed 2026-10-17 by iso-export-lane, from engine-lane's review of the D70
reader change (option B, `'[]'` and `[]` are one atom).

## The gap

In ISO 13211-1, `[]` is an atom, so it is callable: a Prolog text may
contain the fact `[].`, and `[]` may be called as a goal. Clausal refuses
`[]` as a clause head with "a clause head is not callable: [] (ISO
type_error(callable))". The empty list is carried as the Python empty
list, not as an atom `str`, and the loader's head check accepts only a
`str` or a cell. Since D70, the quoted `'[]'` reads as `[]` too, so it is
refused the same way.

## Measured

Main is 0a812c3e; the branch is D70 option B
(`try/d70-option-b-nil-atom-identity-2026-10-16`). The oracle is
`/workspace/scryer-prolog-clpq/target/release/scryer-prolog`
(v0.10.0-137-g9acba77a). Both `.pl` and `.clausal` were run.

| input | main | D70 branch | Scryer |
|---|---|---|---|
| goal `[] = '[]'` (`-g`) | false | true | yes |
| clause body `X = '[]', X == []` | true | true | yes |
| fact `'[]'.` | loads | refused: not callable | loads; `'[]'` succeeds |
| fact `[].` | refused: not callable | refused: not callable | loads; `[]` succeeds |
| `functor('[]'(1), N, A)` | `[]/1` | `[]/1` | |
| `op(700, xfx, '[]')` | `permission_error(create, operator, [])` | same | |
| `writeq(f('[]', [], '{}'))` | `f([],[],{})` | same | |

There are no uses of `'[]'` or `[].` as a head in the 322 corpus
`.pl`/`.clausal` files.

## Where

The head check is `clausal/tools/iso_l3.py`'s clause lowering
(`LoweringRefused("a clause head is not callable ...")`, near the
control-construct guard). A fix would let an arity-0 head that is the
empty list name the predicate `[]/0`. Goal calls need the same: check how
`call([])` and a body goal `[]` are dispatched (in Clausal a body goal `[]`
may be read as an empty conjunction or list). Priority is low, but it is a
real ISO divergence.
