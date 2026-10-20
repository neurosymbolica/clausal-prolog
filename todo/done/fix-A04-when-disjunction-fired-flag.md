# fix(A04-F010): when/2 disjunction fired-flag survives backtracking — goal silently skipped

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/04-runtime-tabling/findings.md` A04-F010
**Tests:** `tests/audit_2026_07_05/test_04_runtime_tabling.py::TestF010WhenDisjunctionFiredFlag` (xfail — flip to pass)

## Bug

`coroutining.py:104-121` (`_install_when_disjunction`): the at-most-once
guard is a plain closure cell `fired = [False]`. Firing in a branch that
subsequently FAILS leaves the flag set after the trail unwinds the
bindings and freeze attributes; when the other disjunct's variable is
bound in the surviving branch, `_guarded_thunk` yields success WITHOUT
running the goal:

    w8(R) <- (
        when((nonvar(X) or nonvar(Y)), R is "fired"),
        ((X is 1, 1 == 2) or (Y is 2))
    )

yields one solution with `R` UNBOUND — the when-condition was satisfied
but its goal never ran in the world that survived.

## Fix direction

The flag must be backtrackable. Options:
- Represent it as an unbound Var bound via `unify(flag_var, "fired",
  trail)` inside `_guarded_thunk` — the trail then undoes the "already
  fired" state exactly when the firing branch is undone (cheapest,
  reuses existing machinery);
- or register a trail undo-entry restoring `fired[0] = False`.

Check `_install_when_ground`'s re-install path for the same
pattern-class: `_recheck_ground` re-installs on remaining free vars using
the ORIGINAL captured `trail` (`coroutining.py:90-101`) — verify the
attribute installation is trailed against the trail active AT FIRE TIME,
not the one captured at install time (probe with a bind-undo-rebind
sequence while fixing).

## Acceptance

- `w8(R)` → `R == "fired"` (single solution).
- Fire-then-succeed branch still fires at most once (add a side-effect
  counter guard).
- In-tree `tests/test_coroutining.py` when-disjunction tests stay green.
