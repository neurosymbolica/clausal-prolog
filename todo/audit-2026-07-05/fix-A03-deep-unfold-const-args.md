# fix(A03-F008): deep unfolding inlines single-clause functors without unifying constant head args

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/03-compiler-goals/findings.md` A03-F008
**Tests:** `tests/audit_2026_07_05/test_03_compiler_goals.py::TestF008DeepUnfoldConstantCheck` (1 xfail — flip to pass)

## Bug

`_try_inline_goal` (`specialization.py:1528-1546`) gates inlining on
`len(first_goal) != len(obj_head)` only, then builds the substitution
exclusively for VAR head args (`if is_var(deref(fresh_head[i]))`).
Constant head args are never compared against the goal's args, and a
goal-side var never receives the head's constant:

    Program: f(1).   g :- f(2).
    -specialize(Solve, ConstProg, alias=ConstDeep, depth=5)
    ConstDeep([["g"]])   # succeeds — f(2) inlined against f(1)'s empty body

Generic `Solve` and depth-0 specialization correctly fail. (Also drops the
`X = const` constraint in the var-goal-arg vs const-head-arg case.)

## Fix direction

Use the module's own `_ast_unify` (`specialization.py:1999` — already
handles constants, vars and list-form terms, and is what the CPD path
uses): `subst = _ast_unify(first_goal, fresh_head)`; abandon inlining when
it returns None; apply the returned substitution to the inlined body AND to
the remaining goal list / clause head (goal-side vars may now be bound).

## Acceptance

- `ConstDeep([["g"]])` fails like generic; in-tree deep fixtures
  (`specialize_deep.clausal` natnum) stay green; memo/embedding behaviour
  unchanged.
