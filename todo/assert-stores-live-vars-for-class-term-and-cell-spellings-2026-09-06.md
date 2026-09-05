# `assertz` stores the caller's LIVE `Var` (class-term spelling; cell spelling fixed)

Found by the P3-3 Task 5 review (F1). The CELL spelling is fixed in Task 5 fix
round 1; the CLASS-TERM spelling is not, and is the remaining half of this.

## The shape

The collect-by-assert idiom — drive a goal, assert one fact per solution —
stores clauses that all share one variable, so every stored fact reads back as
whatever that variable was bound to LAST:

```python
# src(1), src(2)   seen/1 and seenc/1 both -dynamic
X = Var()
for _ in solve(("src", X), m):
    list(pcall("assertz", m.seen(X), module=lm))      # class-term spelling
Y = Var()
[deref(Y) for _ in solve(("seen", Y), lm)]            # → [2, 2]   WRONG
```

The `Compound` spelling has never had this shape, because
`database_ops._normalize_fact_clause` derefs each argument and rebuilds a bound
one as a fresh `Var` plus a `Unify` body goal:

```python
list(pcall("assertz", Compound("seenc", (X,)), module=lm))   # → [1, 2]  right
```

So three spellings of one assert disagreed. As of Task 5 fix round 1 the cell
spelling agrees with `Compound` — `database_ops._freeze_asserted_head_args`
derefs the arguments of a cell-derived head before
`_normalize_fact_clause` sees it. The class-term spelling still does not:
`_normalize_fact_clause` passes a class term through as
`Clause(head=term, body=[])`, untouched, live variable and all.

## Why the class-term half was left

Ruled out of Task 5's scope by the controller: it is a pre-existing defect on a
path Task 5 does not otherwise touch, and changing what
`assertz(<class term>)` stores is a behaviour change with its own blast radius
(every `-dynamic` predicate asserted from `.clausal` source goes through it).

## Residual, both spellings

An UNBOUND argument still comes through as the caller's `Var`, in the cell path
and the `Compound` path alike — `deref` of an unbound variable is that
variable. So `assertz(("p", X))` with `X` unbound stores a clause whose head
holds the caller's `X`, and a later binding of `X` is visible in the stored
clause.

## The fix

ISO `assert/1` copies its argument: the stored clause shares nothing with the
caller. That is the whole fix for all three spellings and the unbound residual
at once — `copy_term` the argument in `_build_clause` before anything else
looks at it — and it belongs with the ISO-surface phase, where `assert/1`'s
contract is being settled anyway. Doing it now would change the class-term path
under every existing `-dynamic` program in the corpus without that phase's
gate.

Note the interaction with `retract/1`, which must keep the OPPOSITE behaviour:
it binds the pattern's variables on the real trail so a retracted clause's
values escape with the solution (A09-F008 / decision A09-D003 a). The freeze
added in fix round 1 is deliberately on the assert path only, in
`_build_clause`, not in the shared `_check_cell_head_permission`.

## Related

- `clausal/logic/builtins/database_ops.py::_freeze_asserted_head_args`
- `tests/test_cell_goals.py::TestCellAssertRetract::test_collect_by_assert_over_a_cell_stores_one_clause_per_solution`
- `.superpowers/sdd/p33-state-relocation/task-5-report.md` §"Fix round 1"
