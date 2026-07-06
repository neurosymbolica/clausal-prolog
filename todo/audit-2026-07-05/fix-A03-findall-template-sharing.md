# fix(A03-F006): findall/bagof/setof share free template variables with the caller

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/03-compiler-goals/findings.md` A03-F006
**Design:** A03-D002 (parked — recommendation: ISO copy semantics)
**Tests:** `tests/audit_2026_07_05/test_03_compiler_goals.py::TestF005F006FindallFamily::test_findall_free_vars_are_fresh_per_solution` (xfail — flip to pass)

## Bug

`_compile_find_all_core` (`control_constructs.py:592-595`) collects
`$deref_walk(template)` per solution. `_deref_walk` resolves bindings but
returns UNBOUND vars as-is — every collected row holds the caller's
original Var objects (all rows share ONE var, and a later binding rewrites
the already-collected results):

    fat2(L, Y) <- (findall([X, Y], in_(X, [1,2]), L), Y is 9)
    → L = [[1, 9], [2, 9]]        # ISO: [[1,_G1],[2,_G2]], fresh per row

## Fix direction

Collect a copy with fresh variables per solution — `copy_term`-style
renaming of vars unbound at collection time (`_copy_term` already exists in
`clausal.logic.builtins.inspection` and handles var_map threading). Applies
to findall, bagof, setof (one emission site). Watch attributed vars: decide
whether attrs are copied (SWI: copy_term/2 copies attributes) — follow
whatever `copy_term/2` in Clausal already does for consistency.

## Acceptance

- Rows carry fresh, per-row-distinct vars; later bindings don't mutate L.
- Guards stay green: findall order+dups, bagof dups + empty-fail, setof
  content; no measurable slowdown on ground templates (fast path: if the
  walked template is ground, skip the copy).
