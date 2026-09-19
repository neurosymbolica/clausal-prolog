# `call/N` resolves a cell goal by name but not a runtime-built class TERM

Found during P3-3 Task 5 (R11, cells as goals). Parked deliberately: closing it
is a behaviour change outside R11's scope.

## What happens

`call/N` decides how to invoke its goal in `clausal/logic/builtins/
higher_order.py` (`_make_call_goal_factory` → `_call_goal_n`):

1. `callable(goal) or hasattr(goal, "_get_dispatch")` → invoke the goal OBJECT;
2. otherwise (Task 5) a CELL `("p", A)` or a bare ATOM `"p"` resolves by NAME
   against the calling module's db;
3. otherwise fail silently (the translator session's pinned §4.2 contract).

A class-term INSTANCE — what `p(X)` evaluates to at runtime when `p/1` HAS
clauses — matches none of them. `_get_dispatch` lives on `PredicateMeta`, i.e.
on the metaclass, so the CLASS answers `hasattr` but an instance of it does
not. So:

```python
list(pcall("cg1", mod.p(X), module=lm))   # []    -- silent failure
list(pcall("cg1", ("p", X), module=lm))   # [1, 2]
```

Pinned as-is by
`tests/test_cell_goals.py::TestCallNOverCells::
test_a_runtime_built_class_TERM_goal_still_fails_silently`.

## Why it matters

Since the P3-2 flip, *which* of the two representations a caller holds is
decided by whether the functor has clauses — a property of the callee, not of
the call site. So the two spellings of the same goal behave differently, and the
one that works is the one whose predicate has NO clauses (a data functor), which
is the one that cannot succeed anyway. That is backwards.

It has always been this way (pre-Task-5 both spellings failed silently), so this
is a gap Task 5 made *visible* rather than one it introduced.

## The fix, when it is in scope

`_resolve_named_goal` already has the shape: add a branch for
`is_term_instance(goal_val)` taking `type(goal_val).__name__` as the functor and
`term_field_names` as the arguments, ahead of the `db is None` bail-out. The
work is not the branch, it is the blast radius: `call(G)` where G is a term
instance currently FAILS, and any program (or test) relying on that failure
would start succeeding. Needs a sweep of `call`/`maplist`/`foldl` call sites
plus a decision on whether the §4.2 silent-fail contract covers class terms.

## Related

- `.superpowers/sdd/p33-state-relocation/task-5-report.md` (the concern list)
- R11 in `implementation_plans/p33-state-relocation.md`

## CLOSED 2026-09-19 (P2 Task 3/4)

Closed at the REPRESENTATION, not at `_resolve_named_goal`, so the blast radius
this note worried about never opened: `PredicateMeta.__call__` builds the cell
now, so `mod.p(X)` from Python IS `("p", X)` and reaches branch 2 — the two
spellings are one term. Branch 3's silent-fail contract is untouched, and no
`call`/`maplist`/`foldl` sweep was needed, because nothing produces a
class-term instance in argument position any more (the clause-HEAD channel,
which still does until P4, never reaches `call/N`).

The pin is flipped, same file, renamed:
`tests/test_cell_goals.py::TestCallNOverCells::
test_a_runtime_built_class_TERM_goal_answers_like_the_cell` — it now asserts
the class-term spelling and the cell spelling answer identically.
