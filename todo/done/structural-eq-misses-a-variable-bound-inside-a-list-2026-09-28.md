# `==` does not see through a variable bound inside a list

Found 2026-09-28 (while documenting `map_list_to_pairs/3`).  Pre-existing:
reproduces on main 91ef2a77.

## Repro

```clausal
-allow_singletons
-private([f(_)])
t1(X) <- (X is [Y], Y is 1, X == [1])                  # fails
t2(X) <- (X is ['-'(Y, 2)], Y is 1, X == ['-'(1, 2)])  # fails
t3(X) <- (X is f(Y), Y is 1, X == f(1))                # fails
q1(X) <- (Y is 1, X is [Y], X == [1])                  # fails too
q2(X) <- (X is [Y], Y is 1, X is [1])                  # succeeds (unification)
q3(X) <- (X is [Y], Y is 1, X == [Y])                  # succeeds
w1(X) <- (X is [Y], Y is 1, '=='(X, [1]))              # succeeds (quoted '==')
```

So the bare `==` (the arithmetic-constraint spelling, whose ground fallback
compares structure) fails whenever a list or cell holds a variable that is
BOUND, whatever the binding order: the comparison sees the variable object,
not its value.  It disagrees with unification (t1 vs q2) and with the quoted
standard-order `'=='` (t1 vs w1), which answers correctly.

## What ISO / Scryer give

The ISO equivalent of the ground comparison is the standard-order identity
`==/2` (ISO 8.4.1.1), which dereferences every subterm:

```prolog
?- X = [Y], Y = 1, X == [1].          % true
?- X = [Y-2], Y = 1, X == [1-2].      % true
?- X = f(Y), Y = 1, X == f(1).        % true
```

(Scryer answers `true` for all three.)  As an arithmetic constraint the
closest is clpz's `#=`, which refuses a list (`domain_error(clpz_expression,
[1])`); either way a bound variable inside the term must read as its value.

## Where to look

`clausal/logic/clpfd.py`: the `==` post's ground fallback (Python equality
after `_resolve`) compares a list/cell that still holds a bound `Var`
without walking it (`_both_ground`, `_text_list_eq`); a deep deref
(`_deref_walk`) of both sides before the fallback comparison is the likely
fix.  The quoted `'=='/2` already answers correctly (w1).

## Fixed

2026-09-29, branch fix/batch-e-residual-triage-2026-09-29: `clausal/logic/clpfd.py`
`_walk_compound` deep-derefs a list/cell/dict operand before the ground
fallback of `fd_eq`/`fd_ne` (Python and C-wrapped twins) and reified `==`/`!=`.
Pinned by `tests/test_batch_e_residual_2026_09_29.py::TestStructuralEqSeesABoundVariableInsideATerm`.
