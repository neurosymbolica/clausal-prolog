# `between/3` does not evaluate arithmetic in its bounds — and fails silently

**Filed:** 2026-08-03, from an external authoring harness loop. First measured on
a rolling date-window rule, where a producer wrote `between(0, LENGTH - 1, X)` and the goal
yielded nothing at all — no solutions, no error, no diagnostic. The wrong-value bridge
now at least NAMES the goal, which is how it was finally caught. **Status: OPEN.**

## Repro

```clausal
Test("A: expression inline in between/3's bound") <- (
    LENGTH == 3,
    findall(X, between(0, LENGTH - 1, X), XS),
    XS == [0, 1, 2]
)

Test("B: same bound evaluated with == first") <- (
    LENGTH == 3,
    HIGH == LENGTH - 1,
    findall(X, between(0, HIGH, X), XS),
    XS == [0, 1, 2]
)

Test("C: control — comparison DOES evaluate the same expression") <- (
    LENGTH == 3,
    2 == LENGTH - 1
)
```

    3 tests: 2 passed, 1 failed [FAILED]
    A: goal 3 of 3 failed: XS == [0, 1, 2]
       bindings at failure: LENGTH = 3, XS = []

B and C pass. **A fails, and it fails as an empty solution set** — `findall` collects
nothing, so the caller sees a well-formed `[]` and not a single word about why.

## Cause

`clausal/logic/builtins/arithmetic.py:123` `_between__3_py` (and the C path it mirrors):

```python
low_val = deref(low)
high_val = deref(high)
if is_var(low_val) or is_var(high_val):
    return
if not isinstance(low_val, int) or isinstance(low_val, bool) or \
   not isinstance(high_val, int) or isinstance(high_val, bool):
    return          # <- a Sub/Add/Mul term lands here and vanishes
```

`deref` does not evaluate, so `LENGTH - 1` arrives as the term `Sub(None, 3, 1)`. It is
not a var and not an `int`, so it takes the second bare `return`.

## Why this one is worth fixing

The inconsistency is the trap: **comparison operators evaluate their operands and
`between/3` does not.** A rulebase is full of `FLOORED == FACTOR_BPS * SA_TREA / 10000`
and `LARGEST * 3 > EU_WIDE * 2`, so "arithmetic works in argument position" is exactly
the generalisation the surrounding code teaches. `between/3` is then the one place it
silently isn't.

Silence is the other half. The `is_var` guard above it has the same shape, but an
unbound bound is a mode error the caller can usually see; an unevaluated *expression*
looks like a perfectly ordinary term at every level the author can inspect.

## Fix (options)

1. **Evaluate the bounds** the way the comparison builtins do, so `between(0, N-1, X)`
   means what it reads as. Matches the rest of the arithmetic surface; the only risk is
   an existing caller relying on a non-numeric bound failing rather than raising.
2. **At minimum, stop failing silently:** distinguish "bound is not a number" from
   "bound is a number outside the range". A non-numeric, non-var bound is a type error
   in ISO (`type_error(integer, X)`), not a failure, and `throw/1` is already the
   documented guard idiom here. Even an advisory note naming the unevaluated term would
   have saved the round-trip.

Option 2 is strictly cheaper and catches the whole class; option 1 additionally removes
the surprise. They compose — evaluate, then throw on what still isn't an integer.

## Acceptance

- `between(0, LENGTH - 1, X)` with `LENGTH == 3` enumerates `[0, 1, 2]` (option 1), **or**
  raises a type error naming the unevaluated bound (option 2). Not `[]`.
- `between(0, HIGH, X)` with `HIGH` unbound keeps its current mode-error behaviour.
- The C and Python paths agree — the bool-bound divergence note at A09-F015 says this
  builtin has form here.

## See also

- The same silent-`return`-on-non-numeric shape guards `plus/3`, `max_/3`, `min_/3`
  (`_all_known_numeric`). Those take *values* rather than an idiom that invites an
  expression, so they are lower risk, but the audit is the same one.
