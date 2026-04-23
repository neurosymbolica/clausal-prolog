# Generator reuse — pre-built frame chains

## The idea

Today every sub-call constructs a fresh `StepGenerator` on every
invocation:

```python
_gen = StepGenerator(inner._get_dispatch(), this_generator, X, Y, trail)
_st = yield (_gen, None)
while _st is not _DONE:
    yield (_tramp_parent, None)
    _st = yield (_gen, None)
```

`StepGenerator(...)` calls the generator function, which Python
materialises as a new frame + locals dict.  For a predicate called in
a tight loop (or deep in a recursive chain), this frame-init cost is
paid on every call.

Alternative: build each predicate's generator **once** as a long-lived
coroutine that loops on an entry yield:

```python
def wrap__2(this_generator):
    while True:
        _sol_parent, _done_parent, arg0, arg1, trail = yield ("ready", None)
        _d0 = deref(arg0); _d1 = deref(arg1)
        match (_d0, _d1):
            case [_v0, _v1]:
                _mark = trail.mark()
                try:
                    ...
                finally:
                    trail.undo(_mark)
        yield (_done_parent, _DONE)
        # loop — next iteration's entry yield picks up fresh args
```

The frame is constructed once.  Subsequent calls send a tuple of
(sol_parent, done_parent, args, trail) into the entry yield.  Reuse
flows naturally through `send()`; no re-init of locals.

Tighter: a **pre-built chain of frames** for known call patterns.
When we know a predicate always delegates to its child as its first
action, we can keep the child frame pre-allocated inside the parent's
closure.  The call graph's hot path becomes a standing pipe.

## Sketch

At predicate install time, identify "hot spine" predicates (one or
more clauses that unconditionally call a known sub-predicate).  Emit
a variant that captures the child's generator on first call and
reuses it thereafter.  Trampoline sends args via the entry-yield
protocol instead of `StepGenerator(...)` construction.

## Lifetime / GC

Long-lived generators still live inside the enclosing scope's
closure.  When the top-level search completes or throws, the chain
goes out of scope and GC collects it — nothing to reclaim manually.
Exceptions unwind via the standard `generator.throw()` path that
`trampoline()` already drives, so `try/finally` semantics are
preserved (trail undo still runs).

## Correctness concerns

- **Trail marks** are taken on each entry iteration (`_mark =
  trail.mark()` inside the `while True`), so each fresh call gets a
  correct undo window.  The `try/finally` needs to be *inside* the
  loop so undo runs per-call, not per-frame-lifetime.
- **State leakage between calls**: fresh locals per iteration.  Any
  local name that crosses the entry yield must be a clause-var
  reset on entry, not a carry-over.  Easier to guarantee if the
  compiler emits the loop body as a single clause-scope, fresh each
  time.
- **Tabling / SLG**: tabled predicates hold state across generator
  lifetimes (suspended resumer lists).  Reuse protocol needs to
  integrate with `_TABLING_SUSPEND`.

## Interaction with continuation-TCO

Orthogonal but complementary.  Continuation-TCO reduces per-solution
hop count; generator reuse reduces per-call init cost.  Both apply
to wrapper-heavy code.  Design them together: a pre-built chain where
links are also tail-delegating yields the minimal-work steady state.

## Open questions

- Which predicates qualify?  Probably anything without reflection /
  dynamic dispatch surprises — needs a whitelist or a purity check.
- Does the C trampoline benefit proportionally?  It already optimises
  tuple-steering; generator-init may already be a smaller fraction
  of the cost.  Measure before designing.
- How does this interact with `todo/inline_body_in_dispatch.md`?
  Inlining the body removes the sub-generator entirely for
  short callees; reuse is for the ones that remain.

## Status

Parked.  Related lore: this was considered pre-Clausal as part of the
choicepoint-elimination direction but never specified.  The
continuation-TCO protocol analysis (2026-04-15, see
`todo/continuation_tco.md`) surfaced it again as a natural companion.
