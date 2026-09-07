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
| 1 | `msort([b, "a", 1, foo(x), [z]], L).` | **RULED 2026-09-07** (Task 15 item 1): `L = [1, b, foo(x), "a", [z]]` — a list/string/code list is the `'.'/2` compound and sorts arity-first (§6.5). Was `[1, b, "a", [z], foo(x)]`. | **LOW** → resolved. Scryer's answer adopted. | No `msort/2`; measured with `compare/3` instead: `compare(<, foo(x), [z])`, `compare(>, f(a,b), [z])`, `compare(<, "a", [z])`, `compare(<, b, "a")`, `compare(<, [1], [1,2])`, `compare(<, [], a)`, `compare(<, 1, [])`, `compare(=, "", [])`. Lists/strings order as `'.'/2` compounds (arity 2, name `.`). **Clausal now matches.** |
| 1b | `compare(O, [a], [a,b]).` / `compare(O, "a", "ab").` | `<` (ISO 7.2.1: the shorter proper list first, its tail `'[]'` being an atom) | — | **SCRYER BUG, not copied.** Scryer answers `>` for both, while answering `<` for `compare(O, [1], [1,2])` — the *same* shape. Its partial-string comparison contradicts its own list comparison; ISO says `<`. Clausal gives `<` for all three. Pinned in `tests/test_standard_order.py::TestConsCompoundOrder::test_char_lists_follow_iso_not_scryers_partial_string_bug`. |
| 2 | `atom_length("abc", N).` | `type_error(atom, "abc")` (§6.6, ISO 8.16.1) | MEDIUM. If Scryer answers `N = 3`, Clausal is stricter than Scryer; decide whether to follow Scryer. | **Match**: `type_error(atom, "abc")`. |
| 3 | `atom_chars("hi", L).` | `type_error(atom, "hi")` (§6.6) | MEDIUM (same family as 2). | **Match**: `type_error(atom, "hi")`. |
| 4 | `atom_chars(A, "hi").` | `A = hi` | HIGH. | **Match**: `A = hi`. |
| 5 | `char_code("a", C).` | `type_error(character, "a")` (§6.6) | MEDIUM-HIGH (`"a"` is `[a]`, not a char). | **Match**: `type_error(character, "a")`. |
| 6 | `atom_concat(1, 2, X).` | `X = '12'` (§6.6, ISO allows atomic) | MEDIUM. | `type_error(atom, 1)`. **Match** — the engine already rejected a bound number in every position (`chars.py` F031/F077 up-front check); only the spec sentence was wrong, corrected here, and three pins added (`tests/test_chars.py::TestAtomConcat`). |
| 7 | `functor(T, "foo", 2).` | `type_error(atomic, "foo")` (§6.4, ISO 8.5.1.3 e) | MEDIUM. Scryer may print the culprit as `[f,o,o]`. | **Match**: `type_error(atomic, "foo")`. |
| 8 | `T =.. ["foo", 1].` | `type_error(atom, "foo")` (§6.4, ISO 8.5.3.3) | MEDIUM. | **Match**: `type_error(atom, "foo")`. |
| 9 | `T =.. ["foo"].` | `type_error(atomic, "foo")` | MEDIUM. | **Match**: `type_error(atomic, "foo")`. |
| 10 | `functor("hello", N, A).` | `N = '.'`, `A = 2` (§6.4) | HIGH. | **Match**: `functor("hello", '.', 2)`. |
| 11 | `arg(2, "hello", T).` | `T = "ello"` | HIGH (Scryer shows a partial string). | **Match**: `arg(2, "hello", "ello")`. |
| 12 | `functor("", N, A).` | `N = []`, `A = 0` | HIGH (`""` is `[]`). | **Match**: `functor([], [], 0)`. |
| 13 | `write("abc"), nl.` | **RULED 2026-09-07** (Task 15 item 4, amended): prints `[a,b,c]` — `write/1` is ISO. Was `abc`. The text printing moved to the NEW `write_text/1`. | MEDIUM → resolved. Scryer's answer adopted. | Prints `[a,b,c]`. **Clausal now matches**, byte for byte (fix round 1, item 0 removed the comma spacing from the whole ISO family). |
| 14 | `writeq("abc"), nl.` | **RULED 2026-09-07**: prints `[a,b,c]` — `writeq/1` is ISO, i.e. `write_term(T, [quoted(true), numbervars(true)])`. Was `"abc"`. | HIGH → resolved. Scryer's answer adopted. | Prints `[a,b,c]`. The `"abc"` form is `write_term(T, [quoted(true), double_quotes(true)])`, Scryer's *toplevel* display; in Clausal that is `print_term/1` / `term_to_string/2` (non-ISO names) and `write_term/2`'s option. **Clausal now matches.** |
| 15 | `writeq([a,b]), nl.` | **RULED 2026-09-07**: prints `[a,b]`. Was `"ab"`. | MEDIUM-HIGH → resolved. | Prints `[a,b]`. **Clausal now matches.** |
| 16 | `write([a,b]), nl.` | **RULED 2026-09-07**: prints `[a,b]`. Was `ab`; `write_text([a,b])` prints `ab`. | MEDIUM → resolved. | Prints `[a,b]`. **Clausal now matches.** |
| 16b | `write_term("abc", [quoted(true), double_quotes(true)]).` etc. | NEW in Clausal (Task 15 item 4): `write_term/2` with `quoted`, `double_quotes`, `ignore_ops`, `numbervars`; unknown option → `domain_error(write_option, Opt)`; non-list → `type_error(list, Opts)`. | — | Measured: `write_term("abc",[quoted(true)])` → `[a,b,c]`; `+[double_quotes(true)]` → `"abc"`; `write_term([a,b],[])` → `[a,b]`; `write_term('a b',[quoted(true)])` → `'a b'`; `write_term(abc,[bogus(true)])` → `domain_error(write_option, bogus(true))`; `write_term(abc, foo)` → `type_error(list, foo)`. **Clausal matches** (context `write_term/2`, Scryer says `write_term/3`; no streams here). |
| 17 | `write(""), nl.` / `write([]), nl.` | prints `[]` (both) | MEDIUM. | **Match**: `[]` (both). |
| 18 | `write_canonical("hello"), nl.` | `'.'(h,'.'(e,'.'(l,'.'(l,'.'(o,[])))))` | VERIFIED by the operator 2026-09-06. | **Match**, byte-for-byte. |
| 19 | `write_canonical(foo(a, "b")), nl.` | `foo(a,'.'(b,[]))` (no spaces) | HIGH. | **Match**, byte-for-byte. |
| 20 | `write_canonical(1+2), nl.` | `+(1,2)` | HIGH. | **Match**, byte-for-byte. |
| 21 | `writeq('foo bar'), writeq('.'), writeq([]), nl.` | `'foo bar''.'[]` | HIGH. | **Match**, byte-for-byte. |
| 22 | `sort(["ab", [a,b]], L).` | `L = ["ab"]` (§6.5: same term, dedup) | HIGH. | **Match**: `L = ["ab"]` (dedups to the one element). |
| 23 | `"abc" = [H\|T].` | `H = a`, `T = "bc"` | HIGH. | **Match**: `H = a`, `T = "bc"`. |
| 24 | `"" = [].` | true | HIGH. | **Match**: true. |
| 25 | `"a" = a.` | false (§6.2) | HIGH. | **Match**: false. |
| 26 | `atom([]).` / `atomic([]).` / `atomic("").` | **RULED 2026-09-07** (Task 15 item 2): true / true / true — `[]` is the reserved atom `'[]'`, and `""`/`b""` are the same term. Was false / false / false. Also `atom_length([], 2)` and `atom_chars([], ['[', ']'])`. | Was a KNOWN DIVERGENCE (spec §14.1); Scryer's answer adopted. | Confirmed: true / true / true; `atom_length([], 2)`; `atom_chars([], ['[',']'])`; `compound([])` false; `callable([])` true. **Clausal now matches.** |
| 26b | `atom_chars(X, ['[',']']).` / `T =.. [[]].` / `functor(T, [], 0).` / `atom_concat('[', ']', X).` / `sort([[], '[]'], L).` / `T =.. [[], a].` | **RULED 2026-09-07** (fix round 1, item 2): `[]` in every case, and `L = [[]]`; above arity 0 the name is an ordinary functor spelled `[]`, so `T =.. [[], a]` is `[](a)`.  Was a `("[]",)` cell, unequal to the empty list. | The other direction of row 26 — the identity has to run both ways or `sort/2` keeps two elements. | Measured, all six: `[] iseq=yes` four times, `sort` → `[[]]`, `T =.. [[], a]` → `[](a)`. **Clausal now matches.** |
| 26c | `X = [], Y = "", X == Y.` (and the ``()`` spelling) / `json.parse('{"[]": 1}', D).` | **RULED 2026-09-07** (fix round 2, item 2): every spelling of nil — `[]`, `""`, `b""`, `()` — unifies with every other, and `()` is the canonical DICT-KEY form because `[]` is unhashable.  `json.parse` of a `"[]"` key used to raise a raw Python `TypeError`. | Not a Scryer comparison — a representation consequence of row 26/26b.  Scryer has one nil object and no hashability problem, so it cannot exhibit either bug. | Scryer: `atom_chars(X, ['[',']'])` then `X == []` is `yes`, which is the identity this closes on the key side too. |
| 27 | `is_list("abc").` / `length("abc", N).` | true / `N = 3` | HIGH. | `length/2` **matches**: `N = 3`. `is_list/1` has no Scryer equivalent — **not testable**. |
| 28 | `append("ab", "cd", X).` | `X = "abcd"` | HIGH. | **Match**: `X = "abcd"`. |
| 29 | `atom_codes(ab, C).` | `C = b"ab"` — the codes model: denotes `[97, 98]` | HIGH as a term; representation differs (bytes). | **Match** as a term: `C = [97,98]` (a plain code list; Clausal's `b"ab"` differs only in representation). |
| 30 | `number_chars(N, "12").` | `N = 12` | HIGH. | **Match**: `N = 12`. Sibling `number_codes(N, "12")` → `type_error(integer, '1')` (chars are not codes) — Clausal is lenient there: minor divergence. |
| 31 | `X = "foo"(1).` | syntax error (§7, ISO 6.3.3) | HIGH — Scryer also rejects. | **Match**: syntax error. |
| 32 | `:- set_prolog_flag(double_quotes, codes).` then `X = "ab".` | Clausal refuses `-double_quotes(codes)` (codes are `b"…"`) | KNOWN DIVERGENCE by design. | Not independently re-tested; Clausal's refusal is a deliberate design choice, not a compatibility gap — known divergence by design stands. |
| 33 | `compare(O, a, b).` / `a @< b.` | not defined in Clausal | KNOWN GAP (spec §4 non-goal; todo). | Scryer has both (used above to test row 1) — still **not defined in Clausal**; known gap stands. |
| 34 | `1 = 1.0.` | true in Clausal | **KNOWN DIVERGENCE** — Scryer: false (§14.3, pre-existing). | Not re-tested (unrelated to atoms/strings); known divergence stands. |
| 35 | `X = "abc", atom(X).` / `X = 'abc', atom(X).` | false / true | HIGH. | **Match**: false / true. |
| 36 | `callable("foo").` / `callable(foo).` | **RULED 2026-09-07** (Task 15 item 2): true / true — `callable` is "atom or compound" (ISO 3.24), and a non-empty string is the compound `'.'/2`. Was false / true. `compound("abc")`, `compound([1,2])`, `compound(b"ab")` likewise true; `atomic(b"ab")` becomes false. | Was HIGH-confidence and wrong; Scryer's answer adopted. | Both **TRUE** in Scryer. **Clausal now matches.** A string being callable is not a read of its characters as a name: `call("foo")` is `existence_error(procedure, '.'/2)` — see row 36b. |
| 36b | `call("foo").` / `call("foo", X).` / `call("").` | **RULED 2026-09-07** (Task 15 item 3): `existence_error(procedure, '.'/2)` / `'.'/3` / `'[]'/0`. Was `type_error(callable, "foo")`. | — | Scryer is self-inconsistent here and only the `call/2` answer was adopted: `call("foo", X)` → `existence_error(procedure, './3')` (matches), but `call("foo")` → `type_error(callable, [f,o,o])` and `call([])` / `call("")` → `existence_error(procedure, []/0)` (matches), while a `"foo"` body goal resolves to `existence_error(procedure, f/0)` (Scryer's `[File\|Files]` consult sugar). The operator ruled the existence_error family, because `callable("foo")` being TRUE (row 36) and `call("foo")` raising `type_error(callable, …)` cannot both stand. |
| 37 | `atom_chars(X, [a, "b"]).` | `type_error(character, "b")` | MEDIUM (`"b"` is `[b]`). | **Match**: `type_error(character, "b")`. |
| 38 | `sub_atom(abc, B, 1, A, S).` | enumerates `S = a; b; c` as atoms | HIGH. | **Match**: enumerates `S = a; b; c`. |
| 39 | `msort(["b", "a", "ab"], L).` | `L = ["a", "ab", "b"]` (keys as char lists) | HIGH (lexicographic by element). | No `msort/2` in Scryer — **not testable**. |
| 40 | `X = 'hello world', writeq(X), nl.` | `'hello world'` | HIGH. | **Match**: prints `'hello world'`. |

Measured against Scryer 0.10.0: row 6 was a spec-text defect only (the engine already rejected numbers
in `atom_concat/3`); corrected in that commit. Rows 1, 13, 14, 15,
16, 26, and 36 were confirmed divergences awaiting a ruling.

**Update 2026-09-07 (Task 15, operator-ruled).** Every one of those rows is
now RULED, and in each case Scryer's answer was adopted: standard order
(row 1, spec §14.9), the writers (rows 13–16, §14.10–11), and the type
tests (rows 26/36, §14.1/§14.12), together with the string-goal error
(row 36b) that the type-test ruling forced. Rows 1b (Scryer's own char-list
comparison bug) and 16b (`write_term/2`) were added.

**Fix round 1 (operator, same day)** closed the one divergence that survived
that pass: the ISO family — `write/1`, `writeln/1`, `write_to_string/2`,
`writeq/1`, `write_term/2` — now prints NO whitespace after a comma
(`[a,b,c]`, `f(a,b)`, `{k:v}`), so rows 13–16 and 16b match Scryer byte for
byte. It also ruled the nil atom the other way round (row 26b below) and
routed every term shape through the ISO renderer, so a `Compound` argument
no longer prints its DISPLAY form inside an ISO writer's output, and a
`b"…"` code list spells out as `[97,98]` there. What remains is ADDITIVE,
not divergent: the Clausal-only `write_text/1` / `writeln_text/1` /
`write_text_to_string/2` and `print_term/1` / `term_to_string/2` families,
which keep `", "` — extra names, not changes to an ISO one.
Row 30 has a minor sibling divergence (`number_codes/2`
leniency). Rows 27 and 39 aren't testable in Scryer (no `is_list/1` or
`msort/2`); row 39's expected answer is unchanged by the order ruling
(`["a", "ab", "b"]` — all three are `'.'/2` compounds, so elements decide).
Everything else is confirmed.
