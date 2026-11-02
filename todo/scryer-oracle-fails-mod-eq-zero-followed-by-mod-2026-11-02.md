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

## Don't move the oracle to d57b6a88 or later yet (checked 2026-11-02)

- d57b6a88 brings a regression of its own, still present at Codeberg head
  581ac2e5. A comparison over an expression that follows a goal binding one of
  its variables now throws:

  ```prolog
  q(1).
  p(A) :- q(E), A - 0 < E.
  % ?- p(0).  error(type_error(evaluable,list/0),(is)/2)   (true expected)
  ```

  The oracle (v0.10.0-137) and d57b6a88's parent 08e0d359 both answer
  `true`. In our clpr.pl it breaks `arith_eval(A =< B)`, so
  `{X >= 3}, {X = 3}`, `minimize/1` and `maximize/1` fail. The library's own
  tests fail 9 cases: 2 in test_clpr, 7 in test_examples_clpr. CLP(Q) is
  unaffected. We haven't found an upstream report of it.
- Codeberg has had a reader regression since 5901e15d (2026-10-10), upstream
  Codeberg #3490: `X = '“'` is a syntax error. Every build carrying
  d57b6a88 has it.
- So applying d57b6a88 alone would also bring the new regression. Keep the
  current oracle until Codeberg head passes both repros and the clpq/clpr
  tests. Carrying our additions over is mechanical: copy `src/lib/clpq.pl`,
  `src/lib/clpr.pl`, `src/tests/clpq/` and `src/tests/clpr/`, and apply a
  28-line `tests/scryer/src_tests.rs` hunk, which applies cleanly to head.

## Two Scryer builds; no upstream PR for now (operator, 2026-11-02)

- The clpq build stays as the CLP(Q|R) oracle and the default for every
  test (`tests/_oracles.SCRYER`).
- A plain upstream build (no clpq), pinned to a Codeberg commit, sits beside
  it as `tests/_oracles.SCRYER_UPSTREAM`. It is for checking upstream
  behaviour and fixes. No test uses it as an oracle until upstream clears the
  two regressions above.
- No PR of our clpq/clpr port to Scryer for now. The blocker is the
  licence: the 1.3.3 sources carry an OFAI copyright notice and no licence
  grant (see `clausal/logic/clpq/PROVENANCE.md`). Scryer is BSD-3, and our
  acceptance of that risk does not carry over to upstream. So there is no
  licence outreach, no reading of SWI-Prolog's clpqr, and no Codeberg
  account until the operator reopens it.

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
