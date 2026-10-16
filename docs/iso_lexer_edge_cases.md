# ISO Lexer Edge Cases

Clausal Prolog's reader follows the escape, quoted-character and number
rules of ISO/IEC 13211-1 §6.4, including in places where many Prolog systems
are more lenient. Until October 2026 our lexer was lenient too. It accepted
bare-exponent floats, uppercase radix prefixes, unknown escapes, octal and
hex escapes without their closing backslash, raw control characters inside
quotes, and a few other forms. We tightened it to match the standard,
and if the standard is ever relaxed in these areas, we will relax with it.

This page records each tightened case: what ISO says, what we used to do,
what two other systems do, and the reason for the rule as we understand it.
Two reasons for keeping such a record:

- Some of these rules are widely ignored, which may mean the standard is
  stricter than practice needs. Making the cases visible helps that
  discussion.
- Where a rule protects against an ambiguity with another part of the
  grammar, documenting that link is useful to other implementers and helps
  test the standard itself.

The "reason" column gives **our reading** of why each rule exists. It is not
a quotation from the standard or its committee. The row numbers are from
Ulrich Neumerkel's
[Conformity Testing I: Syntax](https://www.complang.tuwien.ac.at/ulrich/iso-prolog/conformity_testing)
page (see [ISO Prolog Conformity](iso_conformity.md)).

## How the other systems were checked

Each case was read as `t :- X = <case>, writeq(X), nl.` from a file by
[Scryer Prolog](https://www.scryer.pl) v0.10.0-137-g9acba77a and
[Trealla Prolog](https://github.com/trealla-prolog/trealla) v2.92.3, on
2026-10-16. "error" means the clause was refused with a syntax error.

## Numbers

| Case | ISO | Clausal before | Scryer | Trealla | Ulrich row |
|---|---|---|---|---|---|
| `1e9` | not a float | float `1.0e9` | error | error | — |
| `1E9` | not a float | float `1.0e9` | error | error | #47 |
| `1.0e9`, `1.0E9` | float | float | float | float | — |
| `0X1F`, `0O17`, `0B101` | not a number | 31, 15, 5 | error | error | #43, #272 |

**Bare exponents** (`1e9`). In ISO 6.4.5 a float is an integer, a fraction
and an optional exponent, and the fraction is not optional. Without that
rule, `1e9` would be both a float and the integer `1` followed by the name
`e9`. Ulrich's rows #49 and #50 show this matters: after
`op(9, xf, e9)`, `1e9 = e9(1)` must succeed, and after `op(9, xf, e)`,
`1e-9` reads as `-(e(1), 9)`. Requiring the fraction keeps a digit run
followed by a letter from turning into a number depending on which letter
it is. Accepting `1e9` is probably the most common extension in practice,
which makes it the strongest candidate on this page for relaxing the
standard.

**Uppercase exponent char.** `E` is allowed: ISO 6.4.5's exponent char is
`e` or `E`, and Scryer's lexer spells the same production that way. Only the
missing fraction makes `1E9` invalid. (Our first tightening also dropped the
`E`; that was a mistake, corrected before landing.)

**Uppercase radix prefixes** (`0X1F`). ISO 6.4.4 writes `0x`, `0o` and `0b`
in lowercase only. With that rule, an uppercase letter after a `0` always
starts a new token, here a variable (`X1F`). Accepting `0X` would make
`0X1F` mean a number in one reading and `0` followed by the variable `X1F`
in another.

## Quoted atoms and strings

| Case | ISO | Clausal before | Scryer | Trealla | Ulrich row |
|---|---|---|---|---|---|
| `'\e'` | error | ESC character | error | ESC character | #17, #19 |
| `'\s'` | error | space | error | space | — |
| `'\d'`, `'\z'`, `'\ca'`, `'\N'`, `'\9'`, `'\u1'` | error | kept the backslash | error | `'\d'` kept, `'\z'` error | #16, #21, #22, #104, #105, #229, #241 |
| `'\ '`, `'\<TAB>'` (a backslash before a space or tab) | error | kept the backslash | error | error | #11, #12, #193 |
| `'\141'` (no closing `\`) | error | `a` | error | error | #102 |
| `'\141\'` | `a` | `a` | `a` | `a` | — |
| a raw tab inside quotes | error | accepted | error | error | #5 |
| a raw newline inside quotes | error | accepted | error | error | #6 |
| another raw control character (U+0001, DEL) | error | accepted | error | U+0001 error, DEL accepted | — |

**A closed set of escapes.** ISO 6.4.2.1 lists exactly which characters may
follow a backslash: the symbolic escapes `` a b f n r t v \ ' " ` ``, the octal
and hex escapes, and backslash-newline as a line continuation. Anything else
is an error. A closed set means `'\e'` reads the same everywhere or is
refused everywhere. It does not depend on which extensions a system happens
to have. The two other systems already disagree: Trealla reads `'\e'` as ESC
and `'\s'` as a space, and Scryer refuses both. `\e` (escape) and `\s`
(space) are popular enough that adding them to the standard may be worth
discussing.

**The closing backslash on octal and hex escapes.** Without the closing
`\`, an escape like `'\1411'` is ambiguous between octal 141 followed by `1`
and octal 1411. The terminator makes the end of the escape explicit, so the
escape does not need a fixed width.

**No raw control characters inside quotes.** A literal tab, newline or any
other control character (Unicode category Cc: U+0000 to U+001F, DEL, and
U+0080 to U+009F) inside quotes is an error, but a space is allowed. The rule makes
quoted text visible on the page: a tab that looks like spaces cannot slip
into an atom. It also makes an unclosed quote fail on its own line instead
of swallowing the rest of the file. A newline that belongs in the text is
written `\n`, and a quoted atom can continue onto the next line with
backslash-newline.

Clausal still reads some characters that Scryer refuses. These are the
non-ASCII space and separator characters, such as U+00A0 (no-break space),
U+2003 (em space) and U+2028 (line separator), and the lone-surrogate
escape `'\xD800\'`. ISO leaves characters outside its own character set to
the implementation, so we have not tightened them.

## Character codes (`0'`)

| Case | ISO | Clausal before | Scryer | Trealla | Ulrich row |
|---|---|---|---|---|---|
| `0''` | not a char code | 39 | error | error | #117, #120, #197 |
| `0'''` | 39 | 39 | 39 | 39 | #115 |
| `0'\'` | 39 | 39 | 39 | 39 | #114 |
| `0'` followed by a raw tab | error | 9 | error | error | #177 |
| `0'\141`, `0'\x41` (no closing `\`) | error | 97, 65 | error | error | — |
| `0'\e`, `0'\s` | error | 27, 32 | error | 27, 32 | — |
| `0'\141\`, `0'\x41\` | 97, 65 | 97, 65 | 97, 65 | 97, 65 | — |

**A quote after `0'` must be doubled**, just as inside a quoted atom
(`0'''`), or escaped (`0'\'`). A single quote is not a valid character
there, so `0''` reads as the integer `0` followed by the empty atom `''`.
Ulrich's rows #120 and #197 depend on that reading: with `''` declared as an
operator, `0''1` reads as `''(0, 1)`, and with `''` as a postfix
operator, `0''` reads as `''(0)`.

**No raw control character after `0'`**, for the same reason as inside
quotes: `0'` followed by a tab looks like `0'` followed by spaces. A space
itself is allowed, so `0' ` is 32.

**The same escapes as inside quotes.** After `0'\` comes one escape from
the same closed set, and an octal or hex escape needs its closing
backslash: `0'\141\` is 97, and `0'\141`, `0'\e` and `0'\s` are errors,
just as `'\141'`, `'\e'` and `'\s'` are.
