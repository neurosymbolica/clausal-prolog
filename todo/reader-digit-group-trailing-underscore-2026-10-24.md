# The reader takes a trailing or doubled digit-group underscore

Filed 2026-10-24, from the syntax-error vocabulary work (operator ruling
2026-10-24; `tests/iso/test_syntax_error_terms_scryer.py`, rows
`digit_group_trailing` and `digit_group_double`). Low severity: a text that
is a syntax error elsewhere reads as a number here.

## What

The lexer's digit-group rule in `clausal/tools/toklex/specs/iso.toklex.pl`
is `def(udigits, digit then (digit | '_')*)`, so `1_000_` and `1__000` are
integer tokens (the underscores are dropped: both read as `1000`). Scryer
refuses both with `syntax_error(cannot_parse_big_int)`; SWI-Prolog refuses
them too (a digit group separator must be followed by a digit; Cor.3
digit groups).

The same rule, deliberately, lets `0x1_` and `0x_1` match (the spec's own
comment: "any string over {hexdig,'_'} that contains >= 1 hexdig", the
ratified divergence set of `tests/toklex/test_parity.py`).

## To decide

- Tighten `udigits` to `digit then ('_'? digit)*` (one underscore, between
  digits), and the radix rules likewise? That is a lexer semantic change
  with parity implications (the translator front end shares the lexer),
  outside the error-term work, so it was not made there.
- If it is tightened, the parser already maps an integer glued to an
  `_`-led variable to `cannot_parse_big_int`
  (`PrologParser._unexpected_kind`), so the two rows above would then
  match Scryer's atom with no further change; drop them from
  `KNOWN_DIFFERENCES` in the test.
