# fix(A11-F042): Prolog tools dead code / drift batch

- `prolog_parser._left_prec` (:342) never called — the missing piece behind
  A11-F028 (wire it in, don't delete).
- `clausal_to_prolog._needs_parens` (:147) never called; the inline logic at
  :191-200 has a half-implemented equal-precedence branch with dangling
  comments.
- `prolog_tokenizer._GRAPHIC_STOP` (:61) unused.
- `clausal_to_prolog._convert_import_from:481` builds a garbage
  `PCompound(...split("(")[0] + "(", ())` immediately overwritten at :484.
- `_is_directive_percent` (tokenizer :141) constant-False stub.

Clean up alongside the functional fixes that touch each file.
