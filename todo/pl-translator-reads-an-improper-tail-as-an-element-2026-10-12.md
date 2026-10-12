# The default .pl translator reads an improper list tail as a list element (2026-10-12)

```prolog
q(L) :- L = [x|foo].
```

`clausal file.pl -g 'q(L)'` on main 7bc2e9c7 prints `L = [x,foo].`, a two-element list. ISO, Scryer
and Trealla give `L = [x|foo]`. The native .pl front end (CLAUSAL_PL_FRONTEND=native) reads it
correctly.

Found while fixing append/3 (fix/append-prefix-unifies-2026-10-12). That candidate's tests load
through the native front end for this reason.

Fix: the translator's list lowering must keep a non-list tail as the tail (a partial list / cons
cell), not append it as an element. Test `[x|foo]`, `[x,y|foo]`, `[x|f(a)]`, `[x|"ab"]`, and `[x|Y]`
with Y bound later to a non-list.

## Related, found by the append/3 fix re-review (apprev2/, 2026-10-12)

1. **A var-tail partial list later bound to a non-list splices or raises** (D50 gap; pre-existing, no
   append needed):
   - `L = [x|V], V = 1` raises PartialTermError, where Scryer gives `[x|1]`.
   - `append([x], V, L), V = foo` gives `writeq [x,f,o,o]`, `L == [x|foo]` fails, and `length` gives 4.
   - Scryer gives `[x|foo]`, `==` true, and length fails.
2. **`==` and msort recurse in Python on cons chains** and raise RecursionError at about 300-500 cells:
   `numlist(1,500,L), append(L,foo,X), append(L,foo,Y), X == Y`. Scryer gives true. C unify, writeq
   and copy_term handle 20,000 cells. The native reader also crashes on a 500-element `[...|foo]`
   literal (`iso_l3_directives._show`).
3. **`append(-, +, +improper)` is quadratic,** because it rebuilds the cons chain for every split:
   n=2000 takes 0.74 s, about 50x the proper-list path.

## Status after fix/frontend-anon-var-and-improper-tail-2026-10-12

- **Headline: FIXED.** `prolog_to_clausal._emit_list` splices only a tail that can be a list
  (a variable, a list, `[]`, or a `"..."` under chars or codes). Any other tail is emitted as
  `('.', H, T)` tuples. `[x|foo]`, `[x,y|foo]`, `[x|f(a)]`, `[x|1]`, `[x|"ab"]` under all three
  double_quotes modes, and a head `h([x|foo])` now answer as Scryer and Trealla do
  (`tests/test_pl_translator_improper_tail.py`).
- **New limit:** the cons tuples nest, so one improper literal of about 190 or more elements
  overflows Python's parser ("Parser stack overflowed"). Before the fix it loaded, but with the
  wrong term. The native front end loads 250 and fails at 500 (RecursionError), which is item 2.
- **Item 1 (var tail bound to a non-list): still open.** `L = [x|V], V = 1` still raises
  PartialTermError in both front ends and at `-g`. A partial list is a SegList whose hole must bind
  to a list or str. The fix belongs in the engine (a hole bound to a non-list must become the
  cons tail), not in a front end.
- **Item 2: `==`/`\==` FIXED.** `iso_compare._numeric_types_agree` uses an explicit stack, so
  `eq(20000)` is true (`tests/test_iso_identical_deep_cons_chain.py`). Still open: `compare/3`,
  `@<` and `msort` raise RecursionError at 500 cells (`_helpers.term_key` builds a nested key
  tuple). The native reader still crashes on a 500-element `[...|foo]` literal.
- **Item 3 (quadratic `append(-, +, +improper)`): not touched.**
