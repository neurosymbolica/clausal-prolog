# The Scryer oracle: a first-goal arithmetic comparison overwrites a head variable

**Filed:** 2026-11-02. **Status:** open until the oracle build carries the fix.
It's a Scryer defect, with nothing to fix in Clausal, which answers correctly.
**Fixed upstream** in Codeberg commit `d57b6a8849e3403973890ee851e444f794df253e`
("ensure reg allocation for arith ops are never shallow", 2026-10-22), which is
on Codeberg `master` but not on the GitHub mirror. Upstream report: GitHub
mthom/scryer-prolog#3454, so we filed nothing.

## Repro

```prolog
q(Y, Z) :- Y + 1 > 0, Z = Y.
k(Y) :- Y mod 4 =:= 0, Y mod 7 =\= 0.
```

| build | `q(5, Z)` | `k(2024)` |
|---|---|---|
| oracle (scryer-prolog-clpq, v0.10.0-137-g9acba77a) | `Z = 6` | false |
| GitHub master v0.10.0-354-gb7066b41 | `Z = 6` | false |
| v0.10.0-357-g08e0d359 (parent of the fix) | `Z = 6` | false |
| v0.10.0-358-gd57b6a88 (the fix) | `Z = 5` | true |
| Codeberg master v0.10.0-369-g581ac2e5 | `Z = 5` | true |

When the first body goal is an arithmetic comparison whose left or right side
is an expression over a head variable, the comparison leaves that variable
holding the expression's value. Every later goal then sees the wrong value.
`k(2024)` fails because its second goal computes `(2024 mod 4) mod 7`. An
earlier note here said "swapped order is fine". That was a coincidence of
`mod 100`: `(2024 mod 100) mod 4` happens to be 0.

## Do

- Until the oracle carries `d57b6a88`, treat a Clausal-vs-Scryer disagreement
  where a clause starts with an arithmetic comparison over an expression as an
  oracle defect. This affects the differential fuzzer and the `*_scryer`
  oracle tests. Don't "fix" Clausal toward it.
- The patch is one file (`src/arithmetic.rs`) and applies cleanly to the
  oracle's source tree. Alternatively, rebuild the oracle on Codeberg master.
- Workaround in Prolog that must also run on an unpatched Scryer: put any
  goal first, or compute the value with `is/2` first.
- Close this when the oracle answers `q(5, Z)` with `Z = 5`.
