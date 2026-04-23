# Move _drive_trampoline inner loop to C

## Context

`_drive_trampoline` in `clausal/logic/solve.py` (lines 71–108) is the main
execution loop — it drives the trampoline protocol that executes all compiled
predicates.  It is the single hottest function in every benchmark:

| Benchmark | Calls to send() | tottime | cumtime |
|-----------|-----------------|---------|---------|
| fib | 485,571 | 0.079s | 1.571s |
| nqueens | 375,889 | 0.072s | 3.085s |
| qsort | 108,600 | 0.020s | 0.571s |
| graph | 86,500 | 0.016s | 0.153s |
| tabling | 599,980 | 0.108s | 1.421s |

The function is a tight Python loop that calls `StepGenerator.send()` (already
C) and dispatches on the return value.  The Python loop overhead (~0.05–0.11s
tottime) comes from:
- Python `while True` loop iteration
- `if gen is None` / `if value is DONE` comparisons
- `try/except StopIteration` exception handling per iteration
- The tabling suspend/resume check (`if value is _TABLING_SUSPEND`)

## Current implementation

```python
def _drive_trampoline(dispatch_fn, trail, *args):
    from clausal.logic.tabling import _TABLING_SUSPEND
    from clausal.logic.exceptions import LogicException

    sg = StepGenerator(dispatch_fn, None, *args, trail)
    try:
        gen, value = sg.send(None)
    except StopIteration:
        return
    while True:
        if gen is None:
            if value is DONE:
                return
            yield trail
            try:
                gen, value = sg.send(None)
            except StopIteration:
                return
        else:
            try:
                if value is _TABLING_SUSPEND:
                    gen, value = gen.send(DONE)
                else:
                    gen, value = gen.send(value)
            except StopIteration:
                return
            except LogicException as exc:
                ...
```

## What to do

Move the inner dispatch loop to C.  The function should still be a Python
generator (it `yield`s trail per solution), but the inner loop between yields
should be a C function that calls `sg.send()` in a tight C loop until either:
- A solution is found (gen is None, value is not DONE) → return to Python to yield
- Done (DONE) → return
- StopIteration → return

### Option A: C helper called from Python generator

```python
def _drive_trampoline(dispatch_fn, trail, *args):
    sg = StepGenerator(dispatch_fn, None, *args, trail)
    while True:
        result = _drive_until_yield(sg, _TABLING_SUSPEND, DONE)
        if result is None:
            return
        yield trail
```

Where `_drive_until_yield` is a C function that runs the send() loop until
a yield point or completion.

### Option B: Full C generator

Implement `_drive_trampoline` as a C iterator type (tp_iter / tp_iternext).
This eliminates all Python frame overhead.  More complex but maximum performance.

**Recommendation:** Option A first (simpler, measurable), Option B later.

## Gotchas

1. **`StepGenerator.send()` is already C** (`_trampoline.c`).  The gain is from
   eliminating the Python loop/dispatch overhead between send() calls, not from
   making send() faster.

2. **Tabling suspend** (`_TABLING_SUSPEND`) requires special handling: when a
   tabled predicate suspends, the trampoline sends DONE to the parent instead of
   the suspend signal.  The C loop must check for this sentinel.

3. **LogicException handling**: compiled predicates can raise `LogicException`
   (e.g., `throw/1`).  The C loop must catch this and propagate it.  Read
   the full exception handling code in `_drive_trampoline` (lines 99–108).

4. **The function is a generator** (it yields).  The C helper approach (Option A)
   keeps the Python generator shell while optimising the inner loop.  The C
   function returns a flag indicating "yield now" vs "done".

5. **`gen.send(value)` calls** are Python method calls on StepGenerator objects.
   These are already fast (C method).  The win is eliminating the Python `while`,
   `if`, and `try/except` wrapping each call.

6. **Measurement**: The 0.05–0.11s tottime is the Python loop overhead.  The
   cumtime includes everything called from the loop (compiled predicates, etc.).
   The C version should reduce tottime to near-zero but cumtime stays similar.

## Overlaps

- `C_tabling_key.md` — tabling suspend handling is part of this loop.
  If tabling key computation is in C, the suspend/resume path also benefits.

## How to verify

```bash
# Before
python benchmarks/workloads.py
python -m benchmarks.run_cprofile 2>&1 | grep _drive_trampoline

# After
pip install -e . && python benchmarks/workloads.py
python -m benchmarks.run_cprofile 2>&1 | grep _drive_trampoline

# Correctness
python -m pytest tests/ --ignore=tests/test_trealla_backend.py -x -q
```

Expected: tottime of _drive_trampoline drops from ~0.07s to ~0.01s.
Wall-clock improvement of ~0.05–0.10s across all benchmarks.
Result values must not change.

## Status: Option A implemented

`_drive_until_yield` is now a C function in `_trampoline.c`, and
`_drive_trampoline` in `solve.py` is a 6-line Python generator shell.
Pure-Python fallback exists in `trampoline.py` for when the C extension
is unavailable.

### Open questions

1. **RuntimeError catch may be too broad.**  `drive_until_yield_func` catches
   both `StopIteration` and `RuntimeError` from `StepGen_send()` and treats
   them as search exhaustion.  The original Python code only caught
   `StopIteration`.  `StepGen_send` raises `RuntimeError` for "generator
   returned unexpectedly (no final yield)" — a protocol violation, not normal
   exhaustion.  Catching it silently could mask bugs in compiled predicates
   that `return` instead of yielding `(parent, DONE)`.  The existing C
   functions (`trampoline_func`, `solutions_func`) catch *neither*
   StopIteration nor RuntimeError — they only handle LogicException and
   propagate everything else.  Consider removing the RuntimeError catch (and
   possibly the StopIteration catch) to match the stricter C convention, once
   we confirm no code path depends on the lenient behavior.

2. **Eager import failure is silently ignored.**  The `(void)get_LogicException()`
   and `(void)get_TABLING_SUSPEND()` calls at the top of `drive_until_yield_func`
   discard the return value.  If the import fails (returns NULL with an exception
   set), the subsequent `StepGen_send` is called with an active exception — which
   is undefined behavior in CPython.  In practice these imports should never fail
   if the package is installed, and the existing lazy-import pattern in
   `solutions_func`/`trampoline_func` has the same latent issue, so this is not a
   regression — but it should be hardened (check return, bail on failure).

3. **Option B (full C iterator) still on the table.**  The current approach
   eliminates the Python dispatch loop but keeps a Python generator frame
   alive across yields.  A `tp_iternext`-based C iterator would remove the
   last Python frame from the hot path.  Worth measuring whether the remaining
   generator overhead is significant after Option A.
