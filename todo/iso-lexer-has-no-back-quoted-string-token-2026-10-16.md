# The ISO lexer has no back-quoted string token (ISO 6.4.7)

Filed 2026-10-16 by iso-export-lane, from engine-lane's re-review of the
D60 lexer tightening (fix round 2, nit 3b). OPEN, low priority.

## The gap

ISO 13211-1 6.4.7 defines a back quoted string token: text between back
quotes (`` ` ``), with a doubled back quote or an escape sequence inside,
following the same rules as the other quoted tokens.
`clausal/tools/toklex/specs/iso.toklex.pl` has no such token. A back quote
outside a comment or a quoted token is just an unexpected character.

## What the three systems do

Measured 2026-10-16. Clausal: main 1a363862, through the `.pl` front
end. Scryer: v0.10.0-137-g9acba77a. Trealla: v2.92.3. Each case was read as
`t :- X = <case>, writeq(X), nl.` from a file.

| case | Clausal | Scryer | Trealla |
|---|---|---|---|
| `` `abc` `` | refused: `unexpected character '`'` | `syntax_error(back_quoted_string)` | the atom `abc` |
| ``` `a``b` ``` | refused, same | `syntax_error(back_quoted_string)` | `'a\`b'` |
| `` `a\x60\b` `` | refused, same | `syntax_error(missing_quote)` | `'a\`b'` |
| `` `a\zb` `` | refused, same | `syntax_error(missing_quote)` | illegal character escape |
| ` `` ` (empty) | refused, same | `syntax_error(back_quoted_string)` | `''` |
| `current_prolog_flag(back_quotes, F)` | `domain_error(prolog_flag, back_quotes)` | `domain_error(prolog_flag, back_quotes)` | (not run) |

A back quote inside a comment or inside a quoted atom (`'a`b'`) reads
normally in Clausal.

## So what differs

The outcome already matches Scryer: a back quoted string is refused as a
term. (Our reading is that Part 1 gives a back quoted string no meaning as
a term. This has not been checked against the standard text.) What differs
is the diagnosis:

- Clausal names the opening back quote as an "unexpected character". It
  never forms the token, so it cannot say that the token is a back quoted
  string, or point at a bad escape or a missing closing quote inside it.
- An unclosed back quote is not recognised as an unterminated token.

## A fix, if wanted

Add a `back_quoted` token to `iso.toklex.pl` with the same unit grammar as
`quoted_atom` (a doubled `` ` ``, `esc_term`, or plain characters other
than control characters). Have the reader refuse it as a term, with an
error that names it, as Scryer's `back_quoted_string` does. Then
`toklex.diagnose._KIND` can gain a `` ` `` entry for escape faults inside
it. A token kind added this way also has to be mapped in
`prolog_tokenizer._KIND_MAP` (see `clausal/tools/toklex/AGENTS.md`). Ulrich
Neumerkel's syntax page has no row that needs this.
