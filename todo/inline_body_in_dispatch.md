# Inline clause-body into dispatch wrapper for hot predicates

## Today

`clausal/logic/compiler/arg_index.py` builds a runtime dispatch
wrapper that routes to one of several per-bucket functions. The
wrapper is itself a generator that does:

```python
def dispatch(this_generator, parent, *args, trail):
    _a0 = deref(args[2])
    if is_var(_a0):
        yield from fallback_fn(*args)
    else:
        _k = _runtime_arg_key(_a0)
        _bfn = idx_dict.get(_k)
        if _bfn is not None:
            yield from _bfn(*args)
        else:
            yield from default_fn(*args)
    yield (parent, done)
```

Every call to the predicate goes through this wrapper, which does:
1. Dict lookup on the key.
2. A `yield from` into the selected bucket's generator.
3. A final `yield (parent, DONE)` after the bucket exhausts.

The wrapper itself is another frame in the generator chain (see
`todo/continuation_tco.md` for why that matters). For a cold
predicate this is fine; for a hot one, the dispatch overhead is
worth eliminating.

## Idea

For **hot clauses** (clauses called often enough that compile-time
specialisation pays off), inline the clause body's compiled code
directly into the dispatch wrapper, so there's no separate per-bucket
generator to delegate into.

Concretely: when the indexed-position key is a ground constant at
the call site, the call-site-specialisation pass (Phase 10d) already
emits a direct reference to the bucket function. If we further know
the bucket contains exactly one clause whose body is short, we could
emit the clause body inline — no `StepGenerator(bucket_fn, ...)`
allocation, no extra yield frame, no dispatch overhead.

## When it pays off

- **Single-clause buckets** are already common after deep-structural
  indexing (`list_dispatch.py`). Each bucket is literally one clause.
  Inlining saves one `StepGenerator` allocation + one frame per
  solution.
- **Hot paths** identified by profiling (or JIT — see
  `todo/jit_indexing.md`). Only worth it where the dispatch cost
  dominates.
- **Small bodies**. Inlining a 100-line body into every dispatch
  site would bloat the compiled output. Bodies above some size
  threshold stay as their own function.

## Sketch

Add a `_inline_eligible(bucket)` predicate that returns True when:
- bucket has exactly one clause
- clause body compiles to ≤ N AST statements (say 10)
- clause doesn't contain `catch` / `findall` / any construct that
  needs its own generator frame
- clause doesn't require trail-mark/undo around the whole body
  (already-elided for single-clause buckets via `skip_trail`)

When eligible, compile the clause body directly into the dispatch
function's AST, skipping the intermediate funcdef entirely. This
converts:

```python
dispatch(...): ...; yield from bucket_fn(*args); ...
bucket_fn(...): <body>
```

into:

```python
dispatch(...): ...; <body inlined>; ...
```

## Interaction with other optimisations

- **Continuation-TCO** (`todo/continuation_tco.md`) — both reduce
  per-call overhead; complementary. TCO handles pass-through
  wrappers; inlining handles single-clause buckets.
- **JIT indexing** (`todo/jit_indexing.md`) — once a hot predicate
  is identified, rebuild with both (a) a better index and (b)
  inlined bodies in the dispatch.
- **TRO** (`compiler/tro.py`) — TRO requires the predicate's funcdef
  to wrap its match arms in `while True:`. Inlining a TRO-eligible
  clause into a different function would break this; inlining is
  only eligible when TRO doesn't apply.

## Open questions

- How to measure "hot" without a profiler?  Compile-time heuristics
  (single-clause buckets, short bodies) or runtime counters (needs
  JIT infrastructure).
- How large before we stop inlining?  Needs benchmarking.
- Does inlining hurt debuggability (traceback points into the
  dispatch function, not the bucket function)?  Probably yes;
  worth checking.

## References

- `clausal/logic/compiler/arg_index.py` — dispatch builders that
  would need to accept an inlined-body option.
- `clausal/logic/compiler/predicate.py` — Phase 10d call-site
  specialisation is the closest existing work.
- `clausal/logic/compiler/README.md` §6 — optimisation overview.
