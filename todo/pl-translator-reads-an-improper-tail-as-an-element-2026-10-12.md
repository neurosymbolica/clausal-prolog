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

## Status after fix round 1 (2026-10-13)

- **Item 1: FIXED** (4ff9b485). A partial list's hole bound to a non-list is the improper tail in
  every front end, at `-g`, and whether bound before or after the list is built:
  `L = [x|V], V = 1` gives `[x|1]`, and `X = [a|T], T = foo` gives `[a|foo]` (was "afoo").
  `append([x], V, L), V = foo` gives `[x|foo]`, `==` holds, and `length` fails.
- **Item 2: `==` FIXED, also on cyclic terms (ffcc40b8).** Still open: `compare/3`, `@<` and
  `msort` raise RecursionError at about 500 cells (`_helpers.term_key`). The native reader still
  crashes on a 500-element `[...|foo]` literal.
- **Item 3: not touched.**
- Size limit of improper literals under the translator: filed as
  `todo/translator-improper-list-literal-size-limit-2026-10-13.md`.
- Seen while testing: the NATIVE front end refuses `g --> [x|"ab"].` under
  `double_quotes(chars)` ("a terminal list ends in \"ab\""). Scryer and the translator accept it
  (`phrase(g, L)` gives `[x,a,b]`).

## Status after fix round 2 (2026-10-13)

- List builtins now read a hole-built improper list exactly as the literal `[a|foo]` (0c8257ae).
  nth0/nth1/select now handle improper lists, and `=..`, atom_codes, atom_chars and number_codes
  give type_error(list, _).
- A cyclic partial list (`X = [a|X]`) walks as its cons cells, and `==` on two DISTINCT cyclic
  terms answers coinductively (444b1425).
- Still open from this family:
  - `compare/3`, `@<` and `msort` on a cyclic term, or on a cons chain of about 500 cells,
    raise RecursionError (`_helpers.term_key`); Scryer gives `=`.
  - `findall(Z, member(Z, [X, Y]), L)` with X and Y cyclic raises
    `RecursionError: _is_ground: term nesting too deep` (copying a cyclic term).
  - `_seglists_as_source` (assertz) scans only tuples and lists, so a hole inside a DictTerm in
    an asserted clause is still shared with the caller.
  - The translator loads `h(T) --> [x|T].`, where native and Scryer refuse a partial terminal
    list (instantiation_error).
  - The native reader crashes on a 500-element `[...|foo]` literal; item 3 (quadratic append)
    is not touched.

## Status after fix round 3 (2026-10-13)

- **`==` on two DISTINCT cyclic terms RAISES again** (`X = f(X), Y = f(Y), X == Y`;
  `X = [a|X], Y = [a|Y], X == Y`; also two cyclic terms under `=`). That matches base; Scryer
  answers yes/no. Round 2's coinductive fallback was REMOVED by ruling: its seen set keyed on ids
  of objects it created and freed, so it answered TRUE for different terms (`X = f(X,[1,2,3]),
  Y = f(Y,[1,2,4])`, and acyclic pairs deep enough to overflow). A correct cycle-safe compare
  needs stable keys (dereferenced objects of the term, kept alive), a termination argument for
  SegList cycles, and a fuzz with Python-list leaves. A deep ACYCLIC pair that overflows
  `structural_eq` raises too.
- nth0/nth1 walk a cyclic list by index (Scryer/Trealla: `X = [a,b|X], nth0(5, X, E)` gives `b`).
  `length/2` on a cyclic list is `resource_error(finite_memory)` with N unbound and fails with N
  bound (Scryer).
- Still open, minor (round-3 review):
  - A builtin's error ball carries the culprit's hole unbound: `atom_length` on a hole-built
    list shows `[a|_254]`.
  - `sort`, `atom_codes` and `=..` on a cyclic list raise RecursionError where Scryer gives
    `type_error(list, [a|...])`. `@<` and `msort` as well (`term_key`).
  - Printing a named cyclic binding at `-g` raises (`_deref_walk`).
  - `copy_term`/`findall` of a cyclic term raise (`_copy_term`/`_is_ground` depth).

## Status after fix round 4 (2026-10-13)

- `==`/`\==` now keep 1 and 1.0 apart through a hole-built list: `X = [a|T], T = 1.0, X == [a|1]`
  was TRUE (all three front ends; base raised PartialTermError), `T = [1], X == [a,1.0]` was true
  on base too, and `[1|T] == [1.0|T]` was true. `_numeric_types_agree` (the ISO numeric pass after
  `structural_eq`) skipped any SegList against a list, tuple or cons cell, and never descended
  into one. It now reads a SegList as the term it denotes (its list, its cons cells, or its
  elements with the holes as their variables). The seen guard keys on the term's own objects, so
  a cyclic partial list still terminates. compare/3, @</2, msort/2, sort/2, the tabling variant
  key, dif/2, subsumes_term/2 and `\=` were audited: each already read a hole-built list as the
  literal (the order key and the tabling key walk it; the others unify). dif/2, `\=`,
  subsumes_term/2 and memberchk/2 conflate 1 with 1.0 for the LITERAL as well, because `=` does:
  todo/iso-unify-conflates-int-and-float-2026-09-09.md, not this family.
- Seam: `A is [*T], T is foo, R is [x, *A]` gave `"xfoo"` (the twins read the bare str a
  hole-only SegList walks to as text; an atom is a str since atoms-as-str, text is the carrier).
  It is `[x|foo]`. `R is [*A, x]` with A improper (hole-built or a cons cell) failed silently, or
  appended the cons cell as an element; it is `type_error(list, A)` in both twins and in
  `_build_star_list`.
- Still open, minor: a star bound to a non-list that is no cons cell (`[*A, x]` with `A = foo`)
  is still appended as an element by the twins' catch-all. A cyclic star before another star
  (`A is [b, *A], B is [c], R is [*A, *B]`) raises the Python `_CyclicPartialList`, not a logic
  error.
