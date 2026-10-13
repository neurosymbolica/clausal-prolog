# number_codes/2, atom_number/2 and a few reader spellings: ISO shape errors still missing

number_chars/2 now raises the ISO type errors when Number is bound and Chars
is malformed. The same gaps remain elsewhere. Scryer outputs measured
2026-10-13 against the clean build.

## number_codes/2 (Number bound, Codes malformed): fails silently

| query | engine | Scryer |
|---|---|---|
| `number_codes(1,1)` | fails | `type_error(list,1)` |
| `number_codes(1,[a\|2])` | fails | `type_error(list,[a\|2])` |
| `number_codes(1,[[]\|_])` | fails | `type_error(integer,[])` |

The shape check `_refuse_bound_chars_shape` in
`clausal/logic/builtins/chars.py` is character-specific; it needs an
element-kind parameter (code vs character) before number_codes/2 can use it.

## atom_number/2

`atom_number('0\'\\0', N)` gives `N = 0` and `atom_number('0\'\\0\\', N)`
fails: backwards relative to number_chars/2 (the unterminated `\0` escape
is an error, the terminated one reads as NUL). Scryer has no atom_number in
its core, so there is no oracle; follow number_chars/2.

## Reader spelling: `'\x2d\'1`

The escaped spelling of the quoted minus gives `syntax_error`; Scryer reads
`-1`.

## Ruled: layout after `-` in number text is allowed

Row #91, `number_chars(- 1, "- 1")`: engine `type_error(number,-(1))`;
Scryer and Ulrich's table `true`. Ruled 2026-10-13: Ulrich Neumerkel's
conformity suites are the standard Clausal conforms to. The fix is in the
reader, not chars.py: see todo/reader-minus-layout-number-is-a-negative-literal-2026-10-13.md.

## `0'\08\` raises the wrong syntax error

`number_chars(N, "0'\08\")`: engine `syntax_error(unexpected_char)`;
Scryer `syntax_error(incomplete_reduction)`.

## Cor.2 answer for improper tails with unbound heads

Row #37 `number_chars(N,[X|2])` (Number unbound): engine
`type_error(list,[_|2])`; Scryer `instantiation_error`. Row #72
`number_chars(V,[1,[],X|2])`: engine `type_error(list,...)`; Scryer
`instantiation_error`. Both are the Number-unbound path
(`_refuse_partial`), unchanged by the Number-bound work. Ulrich's table marks
both answers acceptable for these rows; pick the one his ISO reading
prefers, not whichever Scryer happens to give.
