# A *failing* `unify()` costs 8× a succeeding one — two `__unify__` AttributeErrors

**Found:** 2026-07-29, while measuring
[`constant-list-membership-compile-to-set.md`](done/constant-list-membership-compile-to-set.md).
Filed separately because it is a much wider win than that todo and lives in C,
not in the compiler.

## Measurement

On this box (pyenv 3.13.3, aarch64), `clausal/logic/variables/_variables.c`:

```
unify(1, 1, trail)   [succeeds]  →   117 ns
unify(1, 2, trail)   [fails]     →   957 ns
unify('a', 'b')      [fails]     →   646 ns
unify(SomeClass, int)[fails]     →   657 ns
```

The failure cost is flat across types, which points at a shared tail rather
than at any one comparison. It is:

```python
# pure Python, same shape as the C code's tail
try: getattr(1, '__unify__')
except AttributeError: pass
try: getattr(2, '__unify__')
except AttributeError: pass
#                                →   792 ns
```

`do_unify` (`_variables.c`, the block above `PyObject_RichCompareBool`) probes
the `__unify__` protocol on **both** operands with `PyObject_GetAttrString` +
`PyErr_Clear()`. For any pair of ordinary terms — two ints, two strings, two
atoms — neither has `__unify__`, so every failing unification raises and
discards two `AttributeError`s. That is ~83% of the 957 ns.

Succeeding unifications are fast because they return from an earlier fast path
and never reach the tail. So the cost falls exactly on failure, which is the
common case in any scan: list membership, `select`/`permutation`, a
non-first-argument-indexed clause sweep, `dif` wakeups.

## Fix options

1. **Type-level lookup with no exception** — replace the two
   `PyObject_GetAttrString` calls with a `_PyObject_LookupSpecial`-style probe
   (`_PyType_Lookup(Py_TYPE(t1), &_Py_ID(__unify__))`), which returns `NULL`
   without setting an exception. Smallest change, keeps the protocol's
   semantics for the types that do define `__unify__` (`DictTerm`, `SetTerm`,
   `SegList`, `Quantity`). **Recommended.**
2. **Negative-cache the probe per type** — a small type→has-`__unify__` table.
   More state, and (1) should already be cheap enough to make it pointless.
3. **Hoist the scalar case above the probe** — if both operands are exact
   `int`/`float`/`str`/`bytes`/`type`, go straight to
   `PyObject_RichCompareBool`. Fixes the measured cases but leaves the tail
   slow for everything else; worth doing *as well as* (1), not instead.

Note `__unify__` is documented as *"Checked BEFORE the mixed list/tuple guard
so that custom types like SegList can unify against plain Python lists"* — any
fix has to keep that ordering, so (1) is the safe shape.

## Acceptance

`unify(1, 2, trail)` within ~2× of `unify(1, 1, trail)`; the `__unify__`
protocol tests still pass (grep `__unify__` under `clausal/terms.py` and
`tests/`); `benchmarks/microbench.py` gains a failing-unify row so the number
does not silently regress.
