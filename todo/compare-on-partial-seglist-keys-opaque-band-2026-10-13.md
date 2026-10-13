# compare/3, @< and sort/2 key a PARTIAL hole-built list in the opaque band (2026-10-13)

A non-ground SegList (a partial list built through a hole, or written with a variable tail) has
no structural order key: `_helpers.term_key` sends it to `_OpaqueOrder`, the opaque band. So
compare/3, `@<`/`@>`, msort/2 and sort/2 do not read a partial list as the term it denotes.
Pre-existing: identical answers at 5972ae08. `todo/done/seg-star-keys-in-the-opaque-standard-order-band-2026-09-07.md`
called it "a separate question" and no todo tracked it.

Repros (`clausal --once -g kN pc.pl`, native front end):

```prolog
k1  :- A = [0.0|T], B = [0|T], compare(O, A, B), write(O), nl.
%      Clausal: =        Scryer: <   Trealla: <
k6  :- A = [x|H], H = [a|T], B = [x, a|T], compare(O, A, B), write(O), nl.
%      Clausal: >        Scryer: =   Trealla: =
k12 :- A = [x|H], H = [a|T], B = [x, a|T],
       msort([A, B], S), length(S, N), sort([A, B], S2), length(S2, N2), write(N-N2), nl.
%      Clausal: 2-2      Trealla: 2-1   (Scryer has no msort/2)
```

## The broken invariant

iso_compare documents `compare(=, X, Y) <=> X == Y`. Since the improper-tail fix (round 4),
`==` reads a hole-built list as its term, so `[1|T] == [1.0|T]` is false while
`compare(O, [1|T], [1.0|T])` still gives `=` (k1). The other direction breaks too: k6 is `==`
true and compare `>`.

## Fuzz counts

Hole-built vs literal fuzz (2,200 pairs × 4 build modes, clausal and native front ends):

- In **108** rows, sort/2 MERGED two distinct partial terms written as literals.
- In **385** rows, sort/2 KEPT two identical hole-built partial terms as duplicates.

`==` was 0 wrong in the same fuzz. Ground pairs had 0 violations of any kind.

## Fix sketch

Give a partial SegList a structural key: walk it once (`_walk_once`), then key it as its
elements followed by the tail variable's key, so every spelling of `[E1, ..., En|T]` (one
SegList, a chain of them, or a literal) gets one key. Keep the term's own objects alive while
keying, as `_numeric_types_agree` does, so a cyclic partial list terminates. Pin k1, k6 and k12 against Scryer/Trealla, and re-run the fuzz
with sort/2 and compare/3 checked against `==`.
