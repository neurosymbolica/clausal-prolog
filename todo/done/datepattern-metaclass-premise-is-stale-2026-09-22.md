# `_DatePattern`'s metaclass justification is stale; nothing constructs it any more

Found during W4b-1 Task 2, step 5 (`clausal/modules/py/datetime.py:204`).

## What the docstring claimed

`_DatePattern`'s docstring justified `metaclass=PredicateMeta` (rather than a
plain class) on the grounds that "the engine's clause copier rebuilds *term
instances* with fresh variables on each resolution step, and it recognises
them via PredicateMeta or @dataclass (`c_is_term_instance` in
`logic/variables/_variables.c`)."

## Why that premise no longer holds

W4a (2026-09-22, commit `5879b0be` "delete the C instance arms
(c_is_term_instance, py_/c_term_field_names)") deleted `c_is_term_instance`
and the instance-rebuild machinery it fed. `PredicateMeta.__call__` (P2 Task
3, 2026-09-19, predicate.py:1010-1020) already built a CELL — a
functor-first tuple — instead of an instance for every caller in-tree;
W4a's C deletion removed what was left of the engine-side instance
recognition path. So `_DatePattern(...)` — if anything called it — would now
build a cell like any other PredicateMeta class, not a term instance with
fresh per-resolution-step variables. The stated reason for needing the
metaclass is gone.

## The measurement

`grep -rn "_DatePattern(" --include="*.py" --include="*.clausal"
--include="*.seam" .` (excluding `venv/`) finds exactly one hit: the `class
_DatePattern(metaclass=PredicateMeta):` statement itself. No call site
anywhere in the tree constructs a `_DatePattern` instance. `date/3`
(`clausal/modules/py/datetime.py:254`, function `date`) — the only predicate
that would plausibly need one — already builds a raw cell
(`("date", y, m, d)`) directly; its own comment says so: "No pattern class
any more... _DatePattern existed only because a real datetime.date is a
FOREIGN type that a cell is not." `_DatePattern.__unify__` is still
overridden (`_date_pattern_unify`, datetime.py:234-251) to special-case
unification against a real `datetime.date`, but with no instance ever built,
that hook is dead code too — nothing ever calls it.

`tests/ -k date` (287 tests, `--continue-on-collection-errors
--ignore=tests/test_clportools.py`) is green with the class untouched, which
is consistent with it being unreferenced rather than load-bearing through
some path this grep missed.

## Why this is parked, not fixed here

W4b-1 Task 2's brief is explicit that converting `_DatePattern` away from
`PredicateMeta` is OUT OF SCOPE for that task — only reading it, correcting
its stale docstring, and filing this todo. The class is left exactly as it
was (still declared, still zero-arity-callable, still carrying the
`_date_pattern_unify` override) pending a decision to actually delete or
convert it.

## The fix, when it is in scope

Delete `_DatePattern` entirely (class, `_date_pattern_structural_unify`,
`_date_pattern_unify`, and the `_DatePattern.__unify__ =` rebind) unless a
deeper audit turns up a reflection/registry path that reaches the class
itself (not an instance of it) — e.g. something iterating PredicateMeta
subclasses, or a signature lookup keyed on the class object. That audit
should happen before deletion, not be assumed by this todo.

## Related

- `.superpowers/sdd/2026-09-22-w4b1-term-shape-rehome/task-2-brief.md` — step 5
- `clausal/modules/py/datetime.py:204-251`
- W4a landing: commit `5879b0be`, "W4a: delete the C instance arms"

## Closed 2026-09-26 (W4b-3 slice 7a, `fc4de6a6`)

`_DatePattern` was deleted, with `_date_pattern_structural_unify`,
`_date_pattern_unify` and the `__unify__` rebind. The audit this todo asked
for ran before the deletion: a full-suite census found zero constructions,
zero `__unify__` calls, zero `isinstance` checks and zero attribute reads of
the class (its positive control fired). Date answers were compared before and
after: an 18-query battery, the in-repo date_time modules, and the date test
files all agree.

What the `__unify__` hook claimed (a pattern binding Y/M/D against a raw
`datetime.date`, a raw `datetime.datetime` excluded) was already NOT the
engine's behaviour before the deletion: a pattern is the cell
`("date", Y, M, D)`, which never reached the hook, so a raw Python date does
not unify with it and a goal holding one is refused ("a Python date is not a
term"). Measured the same on 3a8697c2 and after.
`tests/test_date_term.py::TestARawPythonDateIsNotATerm` pins that; the date
TERM's bind / partial / datetime-excluded cases are `TestDecompose`.
