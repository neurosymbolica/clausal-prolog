# Task 7 inversion ledger

Format: `<full test id> | <what changed> | <ruling cited>`

STATUS: EMPTY. No inversions were needed.

Full-suite name-diff vs `baseline-failed-names.txt` (145 names) after this
task's changes (`task7-full-run-1.txt`, 144 failed / 12045 passed / 56
skipped / 37 xfailed / 1 error):

- **New failures: NONE.**
- **Names present in baseline but not here: exactly one** —
  `tests/audit_2026_05_25/test_class_C17_perf_memory.py::test_F026_multi_star_splits_bounded_for_moderate_input`
  — the documented pre-existing C17-perf-flake family (see task-6-report.md
  and earlier task reports for the same observation); it did not flake this
  run. Not caused by this task's changes.

## Why the ledger is empty

Unlike Tasks 2-6, this task did not narrow, rename, or invert the domain of
any existing recognition/construction rule that a test's EXPECTED value
encoded. It:

1. Fixed two display-layer bugs (`term_str`'s cell branch, `io.py`'s
   `_format_term_for_io`) to stop dereferencing slot 0 before the cell-shape
   test, matching the exact-type/raw-slot-0 recognition Task 5 already
   established everywhere else (`_helpers._cell_functor`'s convention). No
   existing test asserted the OLD (dereffed) behavior — grepped for
   `isinstance(deref(` and `deref(t[0])`/`deref(val[0])` patterns in
   `tests/` before starting; the only hits were in this task's own new
   docstrings, added afterward.
2. Added rendering support for shapes that previously had NO handling at
   all and therefore either produced a raw Python tuple repr (`term_str`'s
   `TUPLE_TAG` case, `term_html`'s missing cell branch entirely,
   `_format_clause_term`'s `str(val)` fallback for a cell) or raised
   `RenderError` (`clausal/reflection.py`'s renderer on a `TUPLE_TAG`
   cell). No existing test exercised these previously-unreached shapes with
   an EXPECTED value that could now be "wrong" — confirmed by running the
   full targeted test files for every touched module (`test_terms.py`,
   `test_term_html.py`, `test_io.py`, `test_listing.py`,
   `test_tagged_terms.py`, `test_reflection_render.py`,
   `test_reflection_replace_subterm.py`, `test_reflection_op_node.py`,
   `test_reflection_builtins.py`, `test_funnel_lint.py`,
   `test_funnel_accessors.py`) both before and after, and by the full-suite
   name-diff above.
3. Closed a real (but previously untested) asymmetry in
   `clausal/modules/reflection.py`'s `_rewrites`: a str-functor cell's slot
   0 (the functor) was independently rewritable through the generic tuple
   branch, unlike `Compound.functor`, which `_rewrites` never exposed as a
   rewrite target. This is a genuine BEHAVIOR CHANGE for
   `replace_subterm/4` on a cell whose functor happens to unify with OLD —
   see `tests/test_reflection_replace_subterm.py::TestCellFunctorProtection::
   test_functor_is_not_an_independent_rewrite_target` for a before/after
   demonstration in the report. No test pinned the old (unprotected)
   behavior, so nothing needed inverting — it is a new test, not a changed
   one.

## Sweep (hardcoded `('point'`-style strings)

Grepped `tests/` for `"\('[a-zA-Z_]+'` / `'\('[a-zA-Z_]+'` patterns. Every
hit outside this task's own new tests (`test_io.py`, `test_listing.py`)
checks COMPILED CODEGEN SOURCE TEXT (e.g.
`tests/test_implicit_functors.py::...: assert "('wibble', 1, 2)" in src`,
`tests/test_tagged_terms.py: assert "('point', 1, 2)" in src`) — a Python
tuple LITERAL is exactly what the compiler is supposed to emit as source
for a cell construction; these are unrelated to `term_str`/`write`
DISPLAY of a runtime value and correctly still expect the tuple-literal
spelling. None needed changing.

Also grepped for the specific bug pattern this task fixed
(`isinstance(deref(`, `deref(t[0])`, `deref(val[0])`) across `clausal/` and
`tests/` — no other production call site had it; the only remaining hits
are this task's own explanatory docstrings.
