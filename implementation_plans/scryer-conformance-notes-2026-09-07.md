# Scryer Prolog 0.10.0 — conformance observations from the Clausal strings diff (2026-09-07)

Binary: `/workspace/scryer-prolog/target/release/scryer-prolog` (`cargo:0.10.0`), default
`double_quotes(chars)`. Every transcript below is reproducible with a file
`t.pl` containing `:- initialization(main).` and the `main/0` shown, run as
`scryer-prolog t.pl`. Only one genuine non-conformance was found; the others
are observations where Scryer is conforming and the note records why.

## 1. Standard order of partial strings (char lists) contradicts ISO 7.2.1 — and Scryer's own list ordering

ISO 7.2.1: compound terms are ordered by arity, then by name, then by
arguments left to right. `[a,b]` is `'.'(a,'.'(b,[]))`. Comparing `[a]` with
`[a,b]`: same arity (2), same name (`.`), first arguments equal (`a`), second
arguments `[]` versus `'.'(b,[])` — an atom precedes a compound, so
`[a] @< [a,b]`: a proper prefix sorts first.

Scryer gets this right for lists of integers and wrong for lists of
characters (which it stores as partial strings):

```prolog
t(A,B) :- compare(O, A, B), write_term(A-B-O, [quoted(true), double_quotes(true)]), nl.
main :- t([1], [1,2]), t([a], [a,b]), t("a", "ab"), t("ab", "abc"),
        t([a,1], [a]), t([a,b], [a|x]), t("a", [a|x]),
        t('.'(a,[]), '.'(a,'.'(b,[]))),
        sort(["ab", "a", "abc", "b"], L1), write_term(L1, [quoted(true), double_quotes(true)]), nl,
        sort([[1,2],[1],[1,2,3],[2]], L2), write_term(L2, [quoted(true), double_quotes(true)]), nl,
        ( "a" @< "ab" -> write(lt) ; write(not_lt) ), nl, halt.
```

Output:

```
[1]-[1,2]-(<)          % correct
"a"-"ab"-(>)           % ISO: <
"a"-"ab"-(>)           % same, written as "a"/"ab"
"ab"-"abc"-(>)         % ISO: <
[a,1]-"a"-(<)          % ISO: >   ('.'(1,[]) is a compound, [] is an atom)
"ab"-[a|x]-(<)         % ISO: >   ('.'(b,[]) vs x: compound > atom)
"a"-[a|x]-(>)          % ISO: <   ([] vs x: both atoms, '[]' @< x)
"a"-"ab"-(>)           % the explicit '.'/2 spelling gives the same wrong answer
["abc","ab","a","b"]   % sort/2 on strings: ISO expects ["a","ab","abc","b"]
[[1],[1,2],[1,2,3],[2]] % sort/2 on integer lists: correct
not_lt                 % "a" @< "ab" fails; ISO: succeeds
```

The pattern is exactly "when one string is exhausted first, the exhausted
side compares as *greater*" — the opposite of the ISO rule that the `[]`
tail (an atom) precedes any remaining `'.'/2` cell. It affects `compare/3`,
`@</2` and friends, `sort/2`, `msort`-style predicates, `keysort/2` on
string keys, and any `predsort`/`setof` ordering over strings. Because the
integer-list path is right, the defect is confined to the partial-string
(`PStr`) comparison and its interaction with a non-string tail. Worth
raising with Mark Thom (implementation) and Markus Triska (ordering
semantics); a minimal repro is `compare(O, "a", "ab")` — ISO says `O = (<)`.

## 2. Things that looked surprising but are conforming (no action)

- **`writeq("abc")` prints `[a,b,c]`.** ISO `writeq/1` is
  `write_term(T, [quoted(true), numbervars(true)])` and ISO has no
  `double_quotes` *write* option at all (a string is a list, full stop), so
  the list form is the conforming output. The `"abc"` form is Scryer's own
  `write_term/2` option `double_quotes(true)`, which its toplevel uses for
  answers. Clausal follows the toplevel form for `writeq/1` and exposes the
  ISO form through `write_term/2` (Clausal ruling, 2026-09-07).
- **`write("abc")` prints `[a,b,c]`.** Conforming for the same reason
  (`write/1` = `write_term(T, [numbervars(true)])`). Clausal's `write/1`
  prints a string as text by design (it is the engine's `~s`; there is no
  `format/2`) — a documented Clausal divergence, not a Scryer defect.
- **`atom([])`, `atomic([])` succeed; `atom_chars([], ['[',']'])`;
  `atom_length([], 2)`.** ISO 6.3.1: `[]` is an atom. Conforming; Clausal
  aligned to it 2026-09-07.
- **`callable("foo")` succeeds.** `"foo"` is `'.'(f, …)`, a compound;
  `callable/1` is "atom or compound". Conforming. Consequently
  `call("foo")` raises `existence_error(procedure, '.'/2)`, not a type
  error — also conforming; Clausal aligned to it.
- **`atom_concat(1, 2, X)` raises `type_error(atom, 1)`** (through
  `can_be/2`). ISO 8.16.2 requires atoms; conforming (SWI's leniency is the
  non-ISO behaviour).
- **`number_codes(N, "12")` raises `type_error(integer, '1')`.** `"12"` is a
  char list, not a code list; conforming.
- **`atom_length("abc", N)` raises `type_error(atom, "abc")`.** ISO 8.16.1;
  conforming (SWI accepts strings there).
- **`write_canonical("hello")` prints `'.'(h,'.'(e,'.'(l,'.'(l,'.'(o,[])))))`.**
  Conforming (`ignore_ops(true)`, `quoted(true)`, no `double_quotes`).

## 3. Not conformance, just absent (fine)

`msort/2`, `is_list/1`, `upcase_atom/2`, `char_type/2`, `atom_string/2`,
`sort/4`, `set_prolog_flag(double_quotes, codes)` handling in a source file
were not available in this build; none is ISO core.
