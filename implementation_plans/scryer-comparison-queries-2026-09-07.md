# Scryer comparison sheet — atoms-as-cells / strings (2026-09-07)

Rulings in `docs/superpowers/specs/2026-09-06-atoms-as-cells-strings-design.md`
that were taken from the ISO text or from memory of Scryer, not from running
Scryer. The "Clausal" column is what the engine answers at `30478ae4`. The
"Scryer 0.10.0 says" column is measured against
`/workspace/scryer-prolog/target/release/scryer-prolog` (default
`double_quotes(chars)`). Scryer 0.10 has no `msort/2`, `is_list/1`,
`upcase_atom/2`, `char_type/2`, or `atom_string/2`; order rows were re-cast
with `compare/3` and toplevel-display rows use
`write_term(T, [quoted(true), double_quotes(true)])`, Scryer's own toplevel
form, where noted. A mismatch is either a Clausal defect to file or a known
divergence to record — the last two columns say which.

| # | Scryer query | Clausal answer (spec §) | Confidence / expected outcome | Scryer 0.10.0 says |
|---|---|---|---|---|
| 1 | `msort([b, "a", 1, foo(x), [z]], L).` | `L = [1, b, "a", [z], foo(x)]` (§6.5: Number < Atom < Sequence < Compound) | **LOW.** ISO 7.2.1 orders compounds arity-first, so Scryer likely gives `[1, b, foo(x), "a", [z]]` (`'.'/2` has arity 2). Pre-existing Clausal band order, not introduced by the flip; if Scryer differs, file a divergence todo (fix = key lists/strings as `'.'/2` compounds in `_standard_order_key`). | No `msort/2`; measured with `compare/3` instead: `compare(<, foo(x), [z])`, `compare(>, f(a,b), [z])`, `compare(<, "a", [z])`, `compare(<, b, "a")`. Lists/strings order as `'.'/2` compounds (arity 2, name `.`). **Clausal diverges** — the sequence band ranks below all compounds; pre-existing (spec §14 item 9). |
| 2 | `atom_length("abc", N).` | `type_error(atom, "abc")` (§6.6, ISO 8.16.1) | MEDIUM. If Scryer answers `N = 3`, Clausal is stricter than Scryer; decide whether to follow Scryer. | **Match**: `type_error(atom, "abc")`. |
| 3 | `atom_chars("hi", L).` | `type_error(atom, "hi")` (§6.6) | MEDIUM (same family as 2). | **Match**: `type_error(atom, "hi")`. |
| 4 | `atom_chars(A, "hi").` | `A = hi` | HIGH. | **Match**: `A = hi`. |
| 5 | `char_code("a", C).` | `type_error(character, "a")` (§6.6) | MEDIUM-HIGH (`"a"` is `[a]`, not a char). | **Match**: `type_error(character, "a")`. |
| 6 | `atom_concat(1, 2, X).` | `X = '12'` (§6.6, ISO allows atomic) | MEDIUM. | `type_error(atom, 1)`. **Clausal diverged; fixed in this commit** — `atom_concat/3` now rejects a bound number up front for every argument position (`tests/test_chars.py::TestAtomConcat`). |
| 7 | `functor(T, "foo", 2).` | `type_error(atomic, "foo")` (§6.4, ISO 8.5.1.3 e) | MEDIUM. Scryer may print the culprit as `[f,o,o]`. | **Match**: `type_error(atomic, "foo")`. |
| 8 | `T =.. ["foo", 1].` | `type_error(atom, "foo")` (§6.4, ISO 8.5.3.3) | MEDIUM. | **Match**: `type_error(atom, "foo")`. |
| 9 | `T =.. ["foo"].` | `type_error(atomic, "foo")` | MEDIUM. | **Match**: `type_error(atomic, "foo")`. |
| 10 | `functor("hello", N, A).` | `N = '.'`, `A = 2` (§6.4) | HIGH. | **Match**: `functor("hello", '.', 2)`. |
| 11 | `arg(2, "hello", T).` | `T = "ello"` | HIGH (Scryer shows a partial string). | **Match**: `arg(2, "hello", "ello")`. |
| 12 | `functor("", N, A).` | `N = []`, `A = 0` | HIGH (`""` is `[]`). | **Match**: `functor([], [], 0)`. |
| 13 | `write("abc"), nl.` | prints `abc` (§6.7) | MEDIUM. | Prints `[a,b,c]`. **Divergence** — Clausal prints `abc`; ruling pending (human display vs strict; spec §14 item 10). |
| 14 | `writeq("abc"), nl.` | prints `"abc"` | HIGH. | Prints `[a,b,c]` — Scryer's `writeq/1` proper prints the list; the `"abc"` form is `write_term(T, [quoted(true), double_quotes(true)])`, Scryer's *toplevel's* display, not `writeq/1`. **Divergence** — Clausal's `writeq` is that toplevel form; ruling pending (spec §14 item 11). |
| 15 | `writeq([a,b]), nl.` | prints `"ab"` (§6.7: a list of chars is a string) | MEDIUM-HIGH. | Prints `[a,b]` (same toplevel-vs-`writeq/1` distinction as row 14). **Divergence** — Clausal prints `"ab"`; ruling pending (spec §14 item 11). |
| 16 | `write([a,b]), nl.` | prints `ab` | MEDIUM. | Prints `[a,b]` — same family as rows 14/15; Clausal's char-list write collapses to `ab`. Ruling pending (spec §14 item 11). |
| 17 | `write(""), nl.` / `write([]), nl.` | prints `[]` (both) | MEDIUM. | **Match**: `[]` (both). |
| 18 | `write_canonical("hello"), nl.` | `'.'(h,'.'(e,'.'(l,'.'(l,'.'(o,[])))))` | VERIFIED by the operator 2026-09-06. | **Match**, byte-for-byte. |
| 19 | `write_canonical(foo(a, "b")), nl.` | `foo(a,'.'(b,[]))` (no spaces) | HIGH. | **Match**, byte-for-byte. |
| 20 | `write_canonical(1+2), nl.` | `+(1,2)` | HIGH. | **Match**, byte-for-byte. |
| 21 | `writeq('foo bar'), writeq('.'), writeq([]), nl.` | `'foo bar''.'[]` | HIGH. | **Match**, byte-for-byte. |
| 22 | `sort(["ab", [a,b]], L).` | `L = ["ab"]` (§6.5: same term, dedup) | HIGH. | **Match**: `L = ["ab"]` (dedups to the one element). |
| 23 | `"abc" = [H\|T].` | `H = a`, `T = "bc"` | HIGH. | **Match**: `H = a`, `T = "bc"`. |
| 24 | `"" = [].` | true | HIGH. | **Match**: true. |
| 25 | `"a" = a.` | false (§6.2) | HIGH. | **Match**: false. |
| 26 | `atom([]).` / `atomic([]).` / `atomic("").` | false / false / false | **KNOWN DIVERGENCE** — Scryer: true / true / true (`[]` is a reserved atom). Parked spec §14.1; needs a ruling, not a check. | Confirmed: true / true / true. |
| 27 | `is_list("abc").` / `length("abc", N).` | true / `N = 3` | HIGH. | `length/2` **matches**: `N = 3`. `is_list/1` has no Scryer equivalent — **not testable**. |
| 28 | `append("ab", "cd", X).` | `X = "abcd"` | HIGH. | **Match**: `X = "abcd"`. |
| 29 | `atom_codes(ab, C).` | `C = b"ab"` — the codes model: denotes `[97, 98]` | HIGH as a term; representation differs (bytes). | **Match** as a term: `C = [97,98]` (a plain code list; Clausal's `b"ab"` differs only in representation). |
| 30 | `number_chars(N, "12").` | `N = 12` | HIGH. | **Match**: `N = 12`. Sibling `number_codes(N, "12")` → `type_error(integer, '1')` (chars are not codes) — Clausal is lenient there: minor divergence. |
| 31 | `X = "foo"(1).` | syntax error (§7, ISO 6.3.3) | HIGH — Scryer also rejects. | **Match**: syntax error. |
| 32 | `:- set_prolog_flag(double_quotes, codes).` then `X = "ab".` | Clausal refuses `-double_quotes(codes)` (codes are `b"…"`) | KNOWN DIVERGENCE by design. | Not independently re-tested; Clausal's refusal is a deliberate design choice, not a compatibility gap — known divergence by design stands. |
| 33 | `compare(O, a, b).` / `a @< b.` | not defined in Clausal | KNOWN GAP (spec §4 non-goal; todo). | Scryer has both (used above to test row 1) — still **not defined in Clausal**; known gap stands. |
| 34 | `1 = 1.0.` | true in Clausal | **KNOWN DIVERGENCE** — Scryer: false (§14.3, pre-existing). | Not re-tested (unrelated to atoms/strings); known divergence stands. |
| 35 | `X = "abc", atom(X).` / `X = 'abc', atom(X).` | false / true | HIGH. | **Match**: false / true. |
| 36 | `callable("foo").` / `callable(foo).` | false / true | HIGH. | `callable(foo)` **matches** (true). `callable("foo")` is **TRUE** in Scryer (a list is a compound) — same divergence family as row 26; Clausal treats lists as non-compound for `compound/1`/`callable/1`. |
| 37 | `atom_chars(X, [a, "b"]).` | `type_error(character, "b")` | MEDIUM (`"b"` is `[b]`). | **Match**: `type_error(character, "b")`. |
| 38 | `sub_atom(abc, B, 1, A, S).` | enumerates `S = a; b; c` as atoms | HIGH. | **Match**: enumerates `S = a; b; c`. |
| 39 | `msort(["b", "a", "ab"], L).` | `L = ["a", "ab", "b"]` (keys as char lists) | HIGH (lexicographic by element). | No `msort/2` in Scryer — **not testable**. |
| 40 | `X = 'hello world', writeq(X), nl.` | `'hello world'` | HIGH. | **Match**: prints `'hello world'`. |

Measured against Scryer 0.10.0: row 6 was a real Clausal defect (numbers
accepted by `atom_concat/3`); it is fixed in this commit. Rows 1, 13, 14, 15,
16, 26, and 36 are confirmed divergences awaiting a ruling — 1 and 26/36 are
pre-existing and already parked (spec §14.1, §4), 13/14/15/16 are new and
parked as spec §14 items 10–12. Row 30 has a minor sibling divergence
(`number_codes/2` leniency). Rows 27 and 39 aren't testable in Scryer (no
`is_list/1` or `msort/2`). Everything else is confirmed.
