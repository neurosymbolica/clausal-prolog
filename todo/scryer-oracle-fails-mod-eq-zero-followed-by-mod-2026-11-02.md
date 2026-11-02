# The Scryer oracle fails `Y mod N =:= 0` followed directly by another `Y mod M` goal

**Filed:** 2026-11-02. **Status:** open (a Scryer defect; nothing to fix in
Clausal, which answers correctly). Upstream report pending an operator OK.

## Repro (scryer-prolog-clpq build, `scryer-prolog -v` = v0.10.0-137-g9acba77a)

```prolog
k(Y) :- Y mod 4 =:= 0, Y mod 7 =\= 0.
% consulted, then:  ?- k(2024).   false   (true expected)
```

It shows only inside a consulted clause; at the top level the same
conjunction succeeds. It needs `Y mod N =:= 0` followed DIRECTLY by a goal
that evaluates `Y mod M`:

| clause body | Scryer on 2024 |
|---|---|
| `Y mod 4 =:= 0, Y mod 100 =\= 0` | false |
| `Y mod 4 =:= 0, Y mod 100 > 0` | false |
| `Y mod 4 =:= 0, B is Y mod 100, B =\= 0` | false |
| `Y mod 100 =\= 0, Y mod 4 =:= 0` (swapped) | true |
| `Y mod 4 =:= 0, true, Y mod 100 =\= 0` | true |
| `A is Y mod 4, A =:= 0, Y mod 100 =\= 0` | true |
| `Y mod 3 =:= 2, Y mod 7 =\= 0` (non-zero) | true |
| `Y mod 4 =:= 0, Z is Y + 1, Z > 0` | true |

## Do

- Treat a Clausal-vs-Scryer disagreement of this shape (leap-year style
  divisibility chains) as an oracle defect in the differential fuzzer and
  the `*_scryer` oracle tests; don't "fix" Clausal toward it.
- Workaround in Prolog meant to run on Scryer too: compute the remainder
  with `is/2` first.
- Re-check on a newer Scryer before reporting upstream.
