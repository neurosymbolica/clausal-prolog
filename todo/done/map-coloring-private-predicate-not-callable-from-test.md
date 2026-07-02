# BUG: `-private` predicates return "no solutions" when called directly

**RESOLVED 2026-07-01** (commit `2bc2788e`). Root cause was **not** privacy —
it was first-argument indexing mishandling atom-valued keyword facts. A
keyword-argument fact like `Color(C=Red)` compiles to a Var head plus a body
`Unify(Var, LoadName('Red'))`; the atom sits in the body as an unresolved
`LoadName` reference node. Two indexing sites treated that node as a data term:
(1) `_arg_to_index_key` keyed the clauses as `('LoadName', 2)` instead of the
runtime atom key `('Red', 0)`, so a ground call missed every bucket and fell
through to an empty default set; (2) Phase-8 bucket lifting
(`_lift_clause_at_pos`) lifted the raw `LoadName` into the head, emitting a
`MatchClass(LoadName, ...)` pattern no runtime atom matches. Fix: resolve bare
`LoadName`/`LoadAttr` to `(name, 0)` in key extraction, and skip lifting them
(keep the body `Unify`), mirroring the existing str/bytes skip. Regression tests
in `tests/test_first_arg_index.py`; all 12 `map_coloring.clausal` tests pass.

---

**Found:** 2026-07-01 (while triaging the full `clausal/examples/ + tests/fixtures/`
run — pre-existing, unrelated to the trailing-comma fix in commit `d4d1f7d5`).
**Severity:** medium. Doesn't block real programs (exported entry points still
reach private predicates internally), but the example is misleading and it may
indicate a visibility/dispatch gap.

## Symptom
In `clausal/examples/map_coloring.clausal`, 7 of 12 `Test` clauses fail with
`no solutions`. All 7 call a **`-private`** predicate directly:

```
Test("red is a color")   <- Color(Red)          % FAILS (no solutions)
Test("wa adjacent to nt") <- Adjacent(WesternAustralia, NorthernTerritory)  % FAILS
```

while the exported predicate that *uses* those same private predicates
internally passes:

```
Test("a coloring exists") <- Colorable(_)        % PASSES
```

`Color` and `Adjacent` are declared in the `-private([...])` block. `Colorable`
is the sole export and its body calls `Color(...)` — and it works. So the
clauses exist and dispatch correctly *from inside the module's own exported
predicate*, but a `Test` clause calling the private predicate by name yields
nothing.

## Isolation (what it is / isn't)
- **Not** missing clauses — `Colorable` reaches `Color`/`Adjacent` fine.
- **Not** the fact data — same facts feed the working `Colorable`.
- The 5 passing tests either call the export (`Colorable`) or negate a private
  (`not Color("purple")`, which succeeds vacuously because the inner call finds
  nothing — consistent with the private call returning no solutions).
- **Trigger = a `Test` clause (or any clause) calling a `-private` predicate by
  its bare name.** The `Test` clauses live in the same source file/module as the
  private predicates, so this is *not* cross-module privacy — it's in-module.

## Hypothesis / suggested fix area
`Test/1` is collected and run by `clausal/testing.py::run_test` via
`call("Test", desc, module=logic_module)`. The `Test` clause bodies reference
`Color`/`Adjacent`. Suspects:
- Whether `-private` predicates are registered under a name/namespace that the
  `Test` clause body's call target resolves to (name mangling or a separate
  private table), i.e. the call site in the `Test` body binds to a different
  symbol than the one the private clauses were installed under.
- Whether privacy is (incorrectly) enforced at *call* time for same-module
  callers, silently yielding no solutions instead of dispatching.

Start by dumping the compiled `Test("red is a color")` clause and checking what
global/attribute its `Color(Red)` call resolves to, vs where the private
`Color/1` clauses were installed. Compare against the resolution inside
`Colorable`'s body (which works).

## Repro
```
pytest clausal/examples/map_coloring.clausal -q
# 7 failed, 5 passed  — the 7 are the direct private-predicate calls
```
