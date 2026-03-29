# Move arithmetic predicates to C

## Context

`clausal/logic/builtins/arithmetic.py` (381 lines) implements 14 ISO Prolog
arithmetic predicates: `between/3`, `succ/2`, `plus/3`, `abs_/2`, `max_/3`,
`min_/3`, `sign/2`, `gcd/3`, `divmod_/4`, `lcm/3`, `exp_mod/4`, `popcount/2`,
`msb/2`, `lsb/2`.

These are standard numerical operations that are straightforward to implement
in C.  Not individually hot in current benchmarks, but `between/3` and `succ/2`
are commonly used for iteration in Prolog programs.

## What to move

```python
between/3      # generate integers in range (non-deterministic)
succ/2         # successor relation (bidirectional)
plus/3         # X + Y = Z (bidirectional, 3 modes)
abs_/2         # absolute value
max_/3         # maximum of two
min_/3         # minimum of two
sign/2         # sign (-1, 0, 1)
gcd/3          # greatest common divisor
divmod_/4      # quotient and remainder
lcm/3          # least common multiple
exp_mod/4      # modular exponentiation
popcount/2     # population count (bit count)
msb/2          # most significant bit
lsb/2          # least significant bit
```

Also the `is/2` evaluation engine, which evaluates arithmetic expressions.
This is currently handled by the compiler emitting inline Python arithmetic,
but runtime `is/2` calls go through `_eval_ground` in clpfd.py.

## Gotchas

1. **`between/3` is non-deterministic** — it generates integers from Lo to Hi.
   Needs to follow the trampoline protocol (yield solutions).

2. **`plus/3` has 3 modes**: `plus(2, 3, Z)` → Z=5, `plus(2, Y, 5)` → Y=3,
   `plus(X, 3, 5)` → X=2.  The C implementation must detect which args are
   bound and compute the missing one.

3. **Python big integers**: Prolog integers are unbounded.  C `int64_t` handles
   most cases but `gcd`, `lcm`, `exp_mod` need arbitrary precision.  Use
   Python's `PyLong` API which handles big integers natively.

4. **Quantity support**: The arithmetic module supports physical dimensions
   (Quantity type) for dimensional analysis.  The C implementation should check
   for Quantity and fall back to Python for those cases.

## Overlaps

- CLP(FD) (`C_clpfd_domains_and_propagation.md`) uses arithmetic comparisons
  internally.  The C CLP(FD) can call C arithmetic directly.

## How to verify

```bash
python -m pytest tests/ -k "arithmetic or between or succ or plus" -x -q
python -m pytest tests/conformity/test_iso_arithmetic.py -x -q
python -m pytest tests/ --ignore=tests/test_trealla_backend.py -x -q
```
