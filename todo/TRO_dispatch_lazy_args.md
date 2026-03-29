# Lazy args-list allocation in TRO dispatch closures

## Context

The groundness-keyed dispatch closures with tail-recursion optimization (TRO)
allocate `args_list = list(args)` on every call to create a mutable copy.  TRO
only fires when `tro_state[0]` becomes True (set by inner clause).  In most
calls TRO doesn't fire, so the list copy is wasted.

### Profile data

| Benchmark | Function | Calls | tottime | cumtime |
|-----------|----------|-------|---------|---------|
| qsort | `dispatch` (TRO, line 7730) | 119,060 | 0.052s | 0.497s |

Python-level change (defer list() until TRO fires) showed -0.060s cumtime
improvement in cProfile (-12%), but this was within wall-clock noise on
bench_qsort.  Worth implementing because it's a clean improvement with zero risk.

## What to do

**File:** `clausal/logic/compiler.py`
**Function:** `_make_groundness_dispatch_trampoline` (line ~7757)

There are two TRO dispatch closures to modify:

### Gotchas from prior attempt

We implemented this exact change.  cProfile showed -0.060s cumtime improvement
(-12%) in qsort dispatch, and -0.008s tottime improvement.  However, this did
NOT register in wall-clock bench_qsort (0.322s before, 0.324s after — within
noise).  The improvement is real but small enough to be masked by system jitter.

The change is mechanically simple and safe.  There are no edge cases — the
`_current` variable just selects between the original tuple and the lazily-
created list.  The only thing to be careful about: use `_current` consistently
for ALL reads (the `_a = deref(...)`, the `yield from _bfn(...)`, the
`yield from fallback_fn(...)`, and the `yield from dflt_fn(...)` calls).
Missing one means it reads from `args` on first iteration and `args_list` on
subsequent TRO iterations, which would silently work but lose the optimization.

### 1. Single-plan TRO (line ~7773, `if len(plans) == 1` and `if tro_state is not None`)

Current code:
```python
            def dispatch(*args):
                parent = args[1]
                args_list = list(args)
                while True:
                    tro_state[0] = False
                    _a = deref(args_list[offset])
                    ...
                    if tro_state[0]:
                        for _i in range(arity):
                            args_list[_i + 2] = tro_state[_i + 1]
                        continue
                    break
                yield (parent, done)
```

Change to:
```python
            def dispatch(*args):
                parent = args[1]
                args_list = None
                while True:
                    tro_state[0] = False
                    _current = args_list if args_list is not None else args
                    _a = deref(_current[offset])
                    if is_var(_a):
                        yield from fallback_fn(*_current)
                        break
                    _k = _runtime_arg_key(_a)
                    try:
                        _bfn = idx_dict.get(_k)
                    except TypeError:
                        _bfn = None
                    if _bfn is not None:
                        yield from _bfn(*_current)
                    else:
                        yield from dflt_fn(*_current)
                    if tro_state[0]:
                        if args_list is None:
                            args_list = list(args)
                        for _i in range(arity):
                            args_list[_i + 2] = tro_state[_i + 1]
                        continue
                    break
                yield (parent, done)
```

### 2. Multi-plan TRO (line ~7819, `if tro_state is not None` in the else branch)

Apply the same pattern: `args_list = None`, introduce `_current`, lazy `list(args)`.

The key change in both cases:
- Replace `args_list = list(args)` at function entry with `args_list = None`
- Add `_current = args_list if args_list is not None else args` at loop top
- Use `_current` instead of `args_list` for all reads
- Guard `args_list = list(args)` behind `if args_list is None:` inside the
  `if tro_state[0]:` block

**Why this is safe:** Inner bucket functions (`_bfn`, `dflt_fn`, `fallback_fn`)
receive `*_current` which unpacks into positional args.  They do not mutate the
caller's sequence.  The TRO mechanism writes new args into `tro_state[1..N]`, not
into the args sequence.

## How to verify

```bash
# Before
python benchmarks/workloads.py
python -m benchmarks.run_cprofile 2>&1 | grep dispatch

# After
python benchmarks/workloads.py
python -m benchmarks.run_cprofile 2>&1 | grep dispatch

# Correctness
python -m pytest tests/test_compiler.py -x -q
python -m pytest tests/ --ignore=tests/test_trealla_backend.py -x -q
```

Expected: qsort dispatch cumtime drops ~10%.  Overall bench_qsort may or may not
show measurable wall-clock change.
Result values must not change: qsort=20.
