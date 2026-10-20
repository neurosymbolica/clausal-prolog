# fix(A11-F021): TruncDiv routes through float — precision loss ≥ 2^53

`modules/prolog.py:22-24`: `int(a / b)`. `TruncDiv(10**18+1, 1)` → 10**18.
Prolog integers are unbounded; any translated `//` on big ints silently
returns wrong values.

**Fix**: int-exact truncating division: `q = a // b; if (a % b != 0) and
((a < 0) != (b < 0)): q += 1` (or `-(-a // b)` sign-split). Same treatment
for the rem helper. Preserve float behavior only when an operand is float.

**Test**: test_F021_truncdiv_bignum_exact (xfail).
