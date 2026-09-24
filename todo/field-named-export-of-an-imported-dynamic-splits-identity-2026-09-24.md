# A field-named `-module` entry beside `-import_from` of a `-dynamic` predicate splits identity — silently

**Found:** 2026-09-24, dropping the vocabulary-implements idiom
(`todo/done/vocabulary-implements-steal-has-no-row-form-2026-09-24.md`).
**Pre-existing** (the refusal added there does not fire on this shape).

## Reproduction

`tests/fixtures/fnmismatch_schema.clausal` declares `-dynamic(fnm_verdict/2)`
and exports it. A module that re-exports it, with NO clauses of its own for it:

    -module(rx, [fnm_verdict(STATUS, CITATIONS), rx_add(S), rx_chk(R)])
    -import_from(tests.fixtures.fnmismatch_schema, [fnm_verdict])
    rx_add(S) <- assertz(fnm_verdict(S, []))
    rx_chk(R) <- fnm_verdict(R, C_UNUSED)

Measured: `rx.fnm_verdict` is the ATOM `'fnm_verdict'`, not the schema's
predicate; after `rx_add(ok)`, `rx_chk` answers `[]` and the schema's
`fnm_verdict` answers `[]`. The assert went nowhere either module reads,
with no error.

Spelled `fnm_verdict/2` in the export list instead, the same module shares
the schema's predicate, and the assert lands on the owner (`['ok']` from
both). Against a DEFINING exporter with field names
(`impord_declare_then_import`) identity is shared too.

## Question (not guessed)

Which wins when a file declares `f(A, B)` (field names, no clauses -> a DATA
functor) and `-import_from`s a PREDICATE `f/2`: should the import win (as it
does against a defining exporter), or should the clash be a load error? Either
way the silent split is wrong. Until 2026-09-24 the idiom's local clause hid
this (the head re-bound the name).
