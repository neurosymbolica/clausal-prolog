# writeq/1 disagrees with Scryer on operators and quoting (2026-09-27)

Found while doing slice 1 of the Compound retirement (the `LogicException`
message now renders through `clausal.terms.term_writeq`, which prints what
Scryer's toplevel prints for an uncaught error). `writeq/1`, `write/1` and
`write_term/2` still go through `term_str`, which disagrees with Scryer on:

| term (as cell) | Scryer `writeq` | ours `writeq/1` today |
|---|---|---|
| `('/', 'foo', 1)` | `foo/1` | `/(foo,1)` |
| `('+', 1, 2)` | `1+2` | `+(1,2)` |
| `('-', 1)` | `- (1)` | `-(1)` |
| `('A b', 1)` | `'A b'(1)` | `A b(1)` (functor never quoted, does not re-read) |
| `('$VAR', 1)` | `B` (numbervars(true)) | `$VAR(1)` |
| `'/*'` | `'/*'` | `/*` (opens a comment when re-read) |
| `'\r'`, `'\x85\'` | `'\r'`, `'\x85\'` | `'\x0d\'`, raw U+0085 |
| `f(X, Y, X)` | `f(_1,_2,_1)` | `f(_,_,_)` |
| `1.0e22`, `1.5e-7`, `0.00001` | `1.0e22`, `1.5e-7`, `0.00001` | `1e+22`, `1.5e-07`, `1e-05` |

Proposed: route the ISO writer family (`_format_term_iso` in
`clausal/logic/builtins/io.py`) through `term_writeq`'s layout (with
`quoted`/`double_quotes` threaded through), so `writeq/1` prints what Scryer
prints. That changes `writeq/1`/`write/1` output for every operator term, so
it is a visible change of its own and was kept out of slice 1, which
changes only the exception message. `term_str`'s display family
(`print_term/1`, `str()`) is a separate question: code downstream sorts and
dedups on `str()`, so it must not move without notice.

Also seen while probing (engine semantics, not rendering): each of these
raises in Scryer and answers without an error here --
`arg(x, [1], X)` (Scryer `type_error(integer,x)`), `functor(X, foo, -1)` and
`sub_atom(abc, B, -1, A, S)` (`domain_error(not_less_than_zero,-1)`),
`char_code(X, -1)` (`representation_error(character_code)`).
