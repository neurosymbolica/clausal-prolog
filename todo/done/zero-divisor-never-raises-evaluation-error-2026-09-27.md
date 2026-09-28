# The engine never raises `evaluation_error(zero_divisor)`

**Status: FIXED 2026-09-28 (branch feat/arith-scryer-rulings-2026-09-28, Q4 of
the operator's arithmetic rulings).** Every row below now raises
`error(evaluation_error(zero_divisor), (Op)/2)` naming the operator -- a bare
`//`, `%`, `**` too, and `X == 1 // 0`. Pinned in
tests/iso/test_arith_rulings_scryer.py and tests/test_arith_operator_rulings.py.
One open question moved to
todo/arith-rulings-open-edges-2026-09-28.md: Scryer's clpz FAILS a
constraint whose divisor is zero, where the engine now raises.

**Was: OPEN. Found 2026-09-27 during Compound retirement slice 2.**

## Measured (main 03f70a71)

| goal | Clausal | Scryer |
|---|---|---|
| `'=:='(1, 1/0)` | `error(instantiation_error, is/2)` | `error(evaluation_error(zero_divisor),(/)/2)` |
| `'is'(_, 1/0)` | `error(instantiation_error, is/2)` | `error(evaluation_error(zero_divisor),(/)/2)` |
| `eval_(1/0, _)` | raw Python `ZeroDivisionError('Fraction(1, 0)')` (caught as the ball `('ZeroDivisionError', 'Fraction(1, 0)')`) | n/a |
| `X == 1 // 0` | **succeeds**, X left an attributed CLP(FD) variable | `_ is 1//0`: `error(evaluation_error(zero_divisor),(//)/2)` |

ISO 13211-1 9.1.7 (and the evaluable functor definitions in 9.1) require
`evaluation_error(zero_divisor)` for `/`, `//`, `rem`, `mod` and `div` with a
zero divisor.

## Notes

- The instantiation_error for `=:=` is also wrong in its context: it names
  `is/2` for a `=:=/2` goal.
- `X == 1 // 0` succeeding is the silent case. It posts a CLP(FD) constraint
  that has no solution and never reports it. `tools/division_census/`
  measures which divisions come out uneven, which is the same question.
- The fix belongs in the one evaluator (`clpfd._eval_ground` and the
  `exact_arith.EVALUABLE` table from slice A1), so every entry point
  (`is`, the comparisons, `eval_`, `==`/`#=`) raises the same term.

## Repro

    t_arcmp(R) <- (catch(('=:='(1, 1/0), R is no_error), E, R is E)),
    t_is(R) <- (catch(('is'(_, 1/0), R is no_error), E, R is E)),
    t_eval(R) <- (catch((eval_(1/0, _), R is no_error), E, R is E)),
    t_eqdiv(R) <- (catch((X == 1 // 0, R is [no_error, X]), E, R is E)),
