# Scryer comparison sheet — atoms-as-cells / strings (2026-09-07)

Rulings in `docs/superpowers/specs/2026-09-06-atoms-as-cells-strings-design.md`
that were taken from the ISO text or from memory of Scryer, not from running
Scryer (no Prolog in the build sandbox). Run each query in Scryer (default
`double_quotes(chars)`); the "Clausal" column is what the engine answers at
`30478ae4`. A mismatch is either a Clausal defect to file or a known
divergence to record — the last column says which we expect.

| # | Scryer query | Clausal answer (spec §) | Confidence / expected outcome |
|---|---|---|---|
| 1 | `msort([b, "a", 1, foo(x), [z]], L).` | `L = [1, b, "a", [z], foo(x)]` (§6.5: Number < Atom < Sequence < Compound) | **LOW.** ISO 7.2.1 orders compounds arity-first, so Scryer likely gives `[1, b, foo(x), "a", [z]]` (`'.'/2` has arity 2). Pre-existing Clausal band order, not introduced by the flip; if Scryer differs, file a divergence todo (fix = key lists/strings as `'.'/2` compounds in `_standard_order_key`). |
| 2 | `atom_length("abc", N).` | `type_error(atom, "abc")` (§6.6, ISO 8.16.1) | MEDIUM. If Scryer answers `N = 3`, Clausal is stricter than Scryer; decide whether to follow Scryer. |
| 3 | `atom_chars("hi", L).` | `type_error(atom, "hi")` (§6.6) | MEDIUM (same family as 2). |
| 4 | `atom_chars(A, "hi").` | `A = hi` | HIGH. |
| 5 | `char_code("a", C).` | `type_error(character, "a")` (§6.6) | MEDIUM-HIGH (`"a"` is `[a]`, not a char). |
| 6 | `atom_concat(1, 2, X).` | `X = '12'` (§6.6, ISO allows atomic) | MEDIUM. |
| 7 | `functor(T, "foo", 2).` | `type_error(atomic, "foo")` (§6.4, ISO 8.5.1.3 e) | MEDIUM. Scryer may print the culprit as `[f,o,o]`. |
| 8 | `T =.. ["foo", 1].` | `type_error(atom, "foo")` (§6.4, ISO 8.5.3.3) | MEDIUM. |
| 9 | `T =.. ["foo"].` | `type_error(atomic, "foo")` | MEDIUM. |
| 10 | `functor("hello", N, A).` | `N = '.'`, `A = 2` (§6.4) | HIGH. |
| 11 | `arg(2, "hello", T).` | `T = "ello"` | HIGH (Scryer shows a partial string). |
| 12 | `functor("", N, A).` | `N = []`, `A = 0` | HIGH (`""` is `[]`). |
| 13 | `write("abc"), nl.` | prints `abc` (§6.7) | MEDIUM. |
| 14 | `writeq("abc"), nl.` | prints `"abc"` | HIGH. |
| 15 | `writeq([a,b]), nl.` | prints `"ab"` (§6.7: a list of chars is a string) | MEDIUM-HIGH. |
| 16 | `write([a,b]), nl.` | prints `ab` | MEDIUM. |
| 17 | `write(""), nl.` / `write([]), nl.` | prints `[]` (both) | MEDIUM. |
| 18 | `write_canonical("hello"), nl.` | `'.'(h,'.'(e,'.'(l,'.'(l,'.'(o,[])))))` | VERIFIED by the operator 2026-09-06. |
| 19 | `write_canonical(foo(a, "b")), nl.` | `foo(a,'.'(b,[]))` (no spaces) | HIGH. |
| 20 | `write_canonical(1+2), nl.` | `+(1,2)` | HIGH. |
| 21 | `writeq('foo bar'), writeq('.'), writeq([]), nl.` | `'foo bar''.'[]` | HIGH. |
| 22 | `sort(["ab", [a,b]], L).` | `L = ["ab"]` (§6.5: same term, dedup) | HIGH. |
| 23 | `"abc" = [H\|T].` | `H = a`, `T = "bc"` | HIGH. |
| 24 | `"" = [].` | true | HIGH. |
| 25 | `"a" = a.` | false (§6.2) | HIGH. |
| 26 | `atom([]).` / `atomic([]).` / `atomic("").` | false / false / false | **KNOWN DIVERGENCE** — Scryer: true / true / true (`[]` is a reserved atom). Parked spec §14.1; needs a ruling, not a check. |
| 27 | `is_list("abc").` / `length("abc", N).` | true / `N = 3` | HIGH. |
| 28 | `append("ab", "cd", X).` | `X = "abcd"` | HIGH. |
| 29 | `atom_codes(ab, C).` | `C = b"ab"` — the codes model: denotes `[97, 98]` | HIGH as a term; representation differs (bytes). |
| 30 | `number_chars(N, "12").` | `N = 12` | HIGH. |
| 31 | `X = "foo"(1).` | syntax error (§7, ISO 6.3.3) | HIGH — Scryer also rejects. |
| 32 | `:- set_prolog_flag(double_quotes, codes).` then `X = "ab".` | Clausal refuses `-double_quotes(codes)` (codes are `b"…"`) | KNOWN DIVERGENCE by design. |
| 33 | `compare(O, a, b).` / `a @< b.` | not defined in Clausal | KNOWN GAP (spec §4 non-goal; todo). |
| 34 | `1 = 1.0.` | true in Clausal | **KNOWN DIVERGENCE** — Scryer: false (§14.3, pre-existing). |
| 35 | `X = "abc", atom(X).` / `X = 'abc', atom(X).` | false / true | HIGH. |
| 36 | `callable("foo").` / `callable(foo).` | false / true | HIGH. |
| 37 | `atom_chars(X, [a, "b"]).` | `type_error(character, "b")` | MEDIUM (`"b"` is `[b]`). |
| 38 | `sub_atom(abc, B, 1, A, S).` | enumerates `S = a; b; c` as atoms | HIGH. |
| 39 | `msort(["b", "a", "ab"], L).` | `L = ["a", "ab", "b"]` (keys as char lists) | HIGH (lexicographic by element). |
| 40 | `X = 'hello world', writeq(X), nl.` | `'hello world'` | HIGH. |

Rows 1, 2, 7, 13, 26 are the ones whose outcome could change a shipped
behaviour; everything else is confirmation.
