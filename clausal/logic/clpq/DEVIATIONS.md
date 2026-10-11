# Deviations from clp(q,r) 1.3.3

Every difference between the port and 1.3.3 is listed here.  An entry for an
optimisation names the measurement that justifies it.  Names are the
full-word names of `NAMES.md`; the 1.3.3 name follows in parentheses where
it helps.

## D1: rationals are (numerator, denominator) pairs of ints

1.3.3 represents a rational as the term `rat(N, D)` and evaluates arithmetic
through `evaluate_arithmetic/1,2` (`arith_eval`), which `arith_q.pl`
expands at compile time: `compile_rational_normalized` (`compile_Qn`) and
`linearize` in `arith.pl` turn each expression into a sequence of calls to
`addq`, `mulq`, ... (`add_rational`, `multiply_rational`, ... in the reading
copy).

The port has no compile-time goal expansion.  A rational is a
`(numerator, denominator)` pair of Python ints, normalised (denominator
positive, greatest common divisor 1), and the arithmetic is plain functions
in `clausal/logic/clpq/arithmetic.py` that map one-to-one onto C over
PyLong.  `compile_Qn`, `compile_Q`, `compile_R`, `linearize` and the
`specialize_*` predicates are not ported.

The functions and what they replace (`NAMES.md` gives both names; the
module drops the `_rational` suffix):

| 1.3.3 | Port | Difference |
|---|---|---|
| `addq/6`, `subq/6`, `mulq/6`, `divq/6` | `add`, `subtract`, `multiply`, `divide` | Take and return pairs, not four or six integer arguments.  `divide` by zero raises `ZeroDivisionError`, a programming error, never solver failure. |
| `comq/5` | `compare` | Returns -1, 0 or 1 instead of binding `<`, `=` or `>`. |
| `signumq/4` | `sign` | Returns the int sign; 1.3.3 returns it as the rational `S/1`. |
| `putq/3` | `make_rational` | `putq` builds `rat(N, D)` from an already-normal pair; `make_rational` also normalises (sign of the denominator, gcd) and raises `ZeroDivisionError` on a zero denominator. |
| `getq/3` | `from_number` | `getq` accepts an integer, a float (through `float_rat`) or a normal `rat(N, D)`.  `from_number` accepts an `int`, a `Fraction` or a finite `Decimal`, and raises `TypeError` for anything else, including floats, `bool`, subclasses and non-finite Decimals.  Floats are refused because the interface takes exact numbers only. |
| (none) | `to_number` | The way out: an `int` when the denominator is 1, otherwise a `Fraction`, as `present_number` does. |
| (none) | `negate`, `is_zero`, `ZERO`, `ONE` | 1.3.3 writes these inline (`N is -Na`, `N =:= 0`, `0, 1`). |

`minq`, `maxq` and the float-valued functions (`expq`, `sinq`, ...) are not
in this module.  `Fraction` is used only in `from_number` (to accept one) and `to_number`, the
conversion edges; the solver core never sees it.

## D2: `compenv.pl` is not ported

`compenv.pl` set up SICStus's compile environment for `fcompile`.  SICStus
itself marks it obsolete (it begins `end_of_file.`), and nothing in the
solver calls it.

## D3: the unification hook

1.3.3's `verify_attributes/3` (`itf3.pl`, `geler.pl`, `class.pl`) runs
before the binding of X takes effect and returns goals to run afterwards.
Clausal's attribute hook runs after the binding.  Each site in `itf3.pl`
that reads X's attributes or tests `var(X)` expecting X still unbound is
listed here with what the port does instead.

Sites: to be filled in by Task 11.
