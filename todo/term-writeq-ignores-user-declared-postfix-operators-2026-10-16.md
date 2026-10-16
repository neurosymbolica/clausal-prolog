# term_writeq ignores user-declared operators: `''(0)` where writeq/1 prints `0 ''`

Filed/found: 2026-10-16, by iso-export-lane, from engine-lane's review of
the lexer-tightening branch (Ulrich syntax conformity row #197). Severity:
low, cosmetic. It affects how answers and error terms are displayed, not
what is computed.

## What / Repro

Ulrich #197: after `op(100, xf, '')`, `writeq(0'')` writes `0 ''` (Codex
also accepts `0''`). In a `.pl` file:

```prolog
:- op(9, xf, '').
r(R) :- R = ''(0).
```

- `writeq/1` follows the operator table: `X = ''(0), writeq(X)` prints
  `0 ''`, and so does Scryer.
- The CLI's answer line and the Python-side `clausal.terms.term_writeq`
  print `X = ''(0)` / `''(0)`. They do not consult the user-declared
  operators. The same holds for any user-declared postfix operator.

`term_writeq` is also the writer for error-message text, and that path is
under ruling R2 (Scryer byte-for-byte error messages). Any fix has to keep
R2. D62 (the CLI answer printer's `[a]`/`"a"` display) touches the same
printer.

## Candidates / Options

1. Let the CLI answer printer write through the same op-aware writer as
   `writeq/1`, leaving `term_writeq`'s error-message path alone. This is the
   narrow fix that D62's recommendation also points to.
2. Make `term_writeq` itself op-aware. Check R2 first.
