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

## 2026-04-15 attempt — stop-the-line, optimisation is unsafe as designed

Tried the natural lowering rewrite (pass `parent` as the child's
parent, drop the leaf `yield (parent, None)` from the resume-loop
body) inside `TrampolineStrategy.emit_sub_call`, gated by a new
`SubCall.tail_position` hint written by an
`optimisations/continuation_tco.py` pass.  Two successive eligibility
rules failed:

1. **Any tail-position `SubCall` (Sequence-last / Alternate-arm)** —
   broke `tests/clausal_modules/exceptions.clausal::parent
   backtracks after catch failure`.  The clause
   ``Parent(R) <- in_(I, [0,1]) and TryRisky(I, R)`` wraps the tail
   SubCall in `MemberIn`'s `for`-loop; when the child yields
   `(parent, _DONE)` directly, the enclosing `MemberIn` iteration
   never runs its next candidate — we lose backtracking.

2. **Only bodies of shape `Sequence([SubCall])`** — still broke
   `tests/clausal_modules/thread_safe_predicates.clausal::transitive
   path`.  Multi-clause predicates are the killer: each predicate's
   dispatch function runs `trail.undo(mark)` + `yield (parent, _DONE)`
   *after* every clause body.  When the TCO'd child yields
   `(parent, _DONE)`, the caller treats the whole predicate as
   exhausted — clause 2 onward never runs, and the clause's own
   `_undo(mark)` is skipped so the trail accumulates junk bindings
   across calls.  This breaks even single-clause predicates (head
   unification always marks the trail).

**Root cause**: the current dispatch protocol puts head-unify
mark/undo *around* the clause body, and the predicate-level
`_DONE` is meant to signal "no more clauses", not "this sub-call is
done".  Continuation-TCO requires the child's `_DONE` to *not* leak
upward — but our frame has real work (trail undo, clause
enumeration) that must run on the `_DONE` path before we in turn
relay DONE to the caller.

Without a runtime-protocol change — e.g. a proxy StepGenerator that
runs our `_undo(mark)` on child DONE before forwarding DONE up, or
moving head-unify outside the clause generator — there is no sound
rewrite at compile time alone.

**Status**: superseded by `../CONTINUATION_TCO_PLAN.md` — and the
revisit did start from the protocol change.  The plan's Phases 1–3
are now implemented: `StepGenerator` carries split
`proceed`/`fail`/`catcher` continuations, and a reimplemented
`optimisations/continuation_tco.py` pass marks `SubCall.tail_position`
for `TrampolineStrategy.emit_sub_call` to consume.  That resolves both
failures above — `fail` still routes through the caller's frame, so
trail undo, next-clause enumeration, and enclosing loops run on child
DONE while only the solution path is redirected.  The 2026-04-15
comment-only groundwork was reverted at the time (see commit history
around that date for the failed single-parent attempt); the current
code is a fresh implementation on the split protocol.  The plan's
`commit`/`FINAL` variant (§3.4) is still unimplemented beyond the
sentinel + root-driver handling.
