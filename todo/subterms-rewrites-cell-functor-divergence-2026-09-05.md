# `_subterms` walks a cell's functor as a generic element; `_rewrites` protects it — plus a missing renderer integration fixture

Filed at P3-2 Task 7 close-out (ledger: "minor (deferred → T10 todo list)").
Two related, separately-fixable gaps from the same task; filed together
because they were found and reported together
(`.superpowers/sdd/p32-cell-default-flip/task-7-report.md` §Concerns).

## Gap 1: `_subterms`/`_rewrites` cell-functor divergence

`clausal/modules/reflection.py` has two `is_term_instance`/`Compound`-dispatch
functions in the "op_node/3 world": `_subterms` and `_rewrites`
(`replace_subterm/4`'s machinery). Task 7 added a str-functor cell case to
`_rewrites` mirroring its `Compound` case exactly: the functor is carried
through unchanged, only the ARGS are walk/rewrite targets — this closed a
real functor-corruption bug for cells (a rewrite could previously mutate slot
0, breaking the cell's own identity).

`_subterms` did NOT get the same treatment. It still walks a str-functor cell
through its generic `isinstance(term, tuple)` branch, which treats EVERY
element — including slot 0, the functor — as a walkable subterm. So
`_subterms` and `_rewrites` now disagree about whether a cell's functor is a
"subterm" in the op_node sense: `_rewrites` says no (protected, like
`Compound.functor`), `_subterms` says yes (walked, like a list element).

**This divergence is pre-existing in kind**, not new: `clausal/modules/reflection.py`
already documents an analogous `Compound`/`_subterms` divergence for the SAME
reason (`_subterms`'s own docstring frames tuple-walking as deliberate —
"lists, tuples, and dict values"). Task 7 made the divergence concrete for
cells too, by fixing one side (`_rewrites`) and leaving the other
(`_subterms`) as documented, deliberate, generic-tuple behavior. No brief item
or failing test named `_subterms`; the implementer documented the resulting
gap in `_rewrites`'s own docstring rather than silently fixing or leaving it
unrecorded.

**Disposition**: not fixed here — flagged for whoever next touches the
op_node/reflected-term renderer machinery to decide whether `_subterms` should
gain the same functor-protection `_rewrites` got (making the two symmetric)
or whether the existing asymmetry (mirroring the pre-existing `Compound` one)
is acceptable as documented behavior.

## Gap 2: reflection renderer fix lacks a `.clausal`-source integration fixture

Task 7 also fixed `clausal/reflection.py`'s `_ClauseRenderer.term` (the
reified-source renderer used by `op_node/3`): a raw cell used to fall into the
generic `isinstance(value, tuple)` case and render as a Python tuple literal
(`(point, 1, 2)`) instead of Clausal call syntax, and a `TUPLE_TAG` cell tried
to render the `tuple` type object itself and raised `RenderError`. Both are
fixed — a str-functor cell case (`ast.Call`, with the same hidden-atom
demangle the `Atom` case gives a name) and a `TUPLE_TAG` case were added
before the generic tuple case.

The fix is exercised by direct `render_source`/`render_ast` calls on raw
cells (`TestRawCellRendering`), matching how `op_node/3`/`replace_subterm/4`
can produce or consume them at the Python level — but there is no test that
drives a full `.clausal`-source `op_node` construct-mode → `clause_source`
pipeline end-to-end with a raw cell as the NEW argument. That would need a
Clausal-source matcher fixture; the implementer judged it beyond what a
minimal additive fix warranted, and flagged it rather than skip it silently.

**Disposition**: not fixed here — a genuine integration-test gap, worth
closing whenever the op_node/reflection machinery gets its next real feature
work or bug report, so the fix above is exercised by something closer to how
a real program would hit it.

## Where to look

- `clausal/modules/reflection.py` — `_subterms`, `_rewrites` (Task 7's fix is
  in `_rewrites`; `_subterms` is the untouched half).
- `clausal/reflection.py` — `_ClauseRenderer.term` — the `ast.Call`/
  `TUPLE_TAG` cases Task 7 added.
- `tests/` — `TestRawCellRendering` (Task 7's unit-level coverage) — a future
  fixture-driven integration test belongs alongside this.
- `.superpowers/sdd/p32-cell-default-flip/task-7-report.md` §Concerns — the
  implementer's own writeup of both gaps.
