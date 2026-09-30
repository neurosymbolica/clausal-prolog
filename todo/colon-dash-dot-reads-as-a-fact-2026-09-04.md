# `:- .` reads as a fact whose head is the atom `':-'`

**Filed:** 2026-09-04 (second item of
`todo/done/toklex-unclosed-block-comment-silent-eof-2026-09-04.md`), split
out 2026-09-30 when that file's first item was resolved. Still open.

`read_module(":- .\n")` returns `[Clause(term=':-', ...)]`: the Pratt
parser's bare-operator-atom leniency accepts a prefix operator with no
operand before `.`. ISO calls that a syntax error. Options (no preference
recorded): downgrade such a `PClause` to a `SyntaxIssue` in
`PrologReader._classify_pitem`, or validate clause shape in the consumer.
Full write-up in the done file.
