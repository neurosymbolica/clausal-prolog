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
