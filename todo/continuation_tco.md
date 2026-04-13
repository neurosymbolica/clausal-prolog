# Continuation-level TCO for trampoline solution routing

## The issue

When a trampoline-compiled predicate yields a solution, the
`(parent, None)` signal **does not short-circuit** to the top of the
search chain. It traverses level by level:

1. Innermost generator yields `(parent_1, None)`.
2. Trampoline does `parent_1.send(None)`. `parent_1` resumes at its
   suspended `_st_N = yield (child, None)`, runs its own `k_stmts`
   (whatever work was queued after the child's call), eventually
   yields `(parent_2, None)`.
3. Repeat up to the root.

Each hop is O(1) — the trampoline is a flat C `while(1)` loop doing
`gen.send(value)` per iteration, no Python call-stack growth — but
there are O(depth) hops per solution.

For most predicate call shapes this is fine because each level
*does* have work to do (run more goals, update found-flags, undo
trails, etc.). But a class of predicates has **no work after the
sub-call returns a solution**:

```clausal
outer_wrapper(X, Y) <- inner(X, Y)
```

The compiled generator for `outer_wrapper` does:

```python
_gen = StepGenerator(inner_dispatch, this_generator, X, Y, trail)
_st  = yield (_gen, None)
while _st is not _DONE:
    yield (parent, None)      # <-- the ONLY work is forwarding
    _st = yield (_gen, None)
yield (parent, _DONE)
```

When `inner` finds a solution, it yields `(outer_wrapper_gen, None)`.
Trampoline routes to `outer_wrapper_gen`. `outer_wrapper_gen` runs
exactly one statement — `yield (parent, None)` — and suspends.
Trampoline routes to `parent`. *Nothing useful happened at the middle
level.* For a chain N wrappers deep, we pay N trampoline iterations
per solution just to pass through.

## What we want

When `outer_wrapper` has no k_stmts to run between the sub-call and
its own yield, it should pass *its own parent* as the child's parent:

```python
_gen = StepGenerator(inner_dispatch, parent, X, Y, trail)
# no while-loop — just tail-delegate
```

Then `inner` yields `(parent, None)` directly, skipping
`outer_wrapper_gen` entirely. O(1) solution routing regardless of
chain depth.

This is **continuation-level TCO**: the tail-call optimisation at the
continuation-passing protocol, not just at the self-recursive-call
level (which is what TRO — see `compiler/tro.py` — already does).

## Design sketch

A clause body qualifies for continuation-TCO when:

- Its last goal is a predicate call (a `Call` node with a `LoadName`
  or `LoadAttr` func).
- There are no goals after that call (no k_stmts after the yield).
- The call isn't inside a construct that needs to observe each
  solution (not inside `findall`, `count_all`, `catch`, etc.).

For such clauses, emit the trampoline-call pattern with
`parent` passed as the child's parent, and skip the surrounding
`while _st is not _DONE` loop — the child's `(parent, _DONE)`
surfaces directly and we never resume.

This interacts with:
- **TRO** (self-recursive tail calls) — orthogonal; both can apply.
- **Or** (disjunction) — the right disjunct often has nothing after
  it, eligible for TCO.
- **And / TupleLiteral** — the last element can qualify even if
  earlier elements don't.
- **catch** — NOT eligible; catch needs to wrap the child's yields
  with exception handling.
- **once / call_nth** — NOT eligible; these observe solutions.

## Not greenlets

The earlier (wrong) hypothesis was that greenlets are used here.
They aren't — `clausal/logic/continuation_search.py` exists but isn't
wired into the trampoline. The actual implementation is just the
level-by-level hop described above.

Greenlets could theoretically implement continuation-TCO by suspending
the whole chain at once and resuming when Python pulls the next
solution. But we can get the same behaviour with compile-time
rewriting of tail calls, without the greenlet runtime dependency.

## Related

- `clausal/logic/compiler/tro.py` — handles self-recursive tail calls
  (a narrower optimisation).
- `clausal/logic/compiler/README.md` §5 "How solutions reach the caller"
  — describes the current level-by-level routing.
- `todo/inline_body_in_dispatch.md` — a different optimisation that
  also reduces per-call overhead.
