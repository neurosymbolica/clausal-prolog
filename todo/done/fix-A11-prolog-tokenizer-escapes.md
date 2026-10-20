# fix(A11-F034/F040): ISO escape sequences mangled/fatal; malformed numbers raise bare ValueError

- F034 (prolog_tokenizer.py:269-318, 355-368): only `\n \t \\ \' \"`
  supported. `'\r'`/`'\a'` become two chars (backslash+letter); ISO hex
  `'\x41\'` and octal `'\101\'` die as "Unterminated quoted atom"; line
  continuation `'a\<NL>b'` keeps the backslash-newline (ISO: 'ab'); `0'''`
  fatal (ISO: 39); `0'\x41\` tokenizes as THREE tokens. The emitter
  (`clausal_to_prolog._quote_atom`) also never generates escapes beyond
  `\\`/`\'` — control chars are emitted raw (ISO-invalid text only this
  tokenizer can re-read).
- F040 (:326-353, 394-398): `1e`, `0x`, `1.5e` raise bare ValueError with no
  line/col — callers catching TokenizeError/ParseError crash.

**Fix**: full ISO 6.4.2 escape table both directions; wrap numeric-literal
conversion in TokenizeError with position.

**Tests**: test_F034_iso_escapes, test_F040_malformed_number_tokenize_error
(xfail) + test_guard_tokenizer_radix_and_bignum.
