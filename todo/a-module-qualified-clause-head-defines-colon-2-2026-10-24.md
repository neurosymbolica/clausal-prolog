# A module-qualified clause head defines `:/2` instead of the qualified predicate

Filed 2026-10-24, found in review of the ISO built-ins-are-static fix. OPEN.

On the native front end (`.pl` and `.clausal`), a clause whose head is
`M:H` loads as a clause of `:/2`:

```
p(1).
m:foo(1).
```

loads, and defines `(:)/2`, not `foo/1` in `m`. Scryer defines `m:foo/1`
(the clause goes to module `m`); `user:foo(1).` defines `foo/1` in `user`.
The translator front end refuses every qualified head ("Only plain
(unquoted-style) functor names can name Clausal predicates").

Already handled: `M:H` with `H` an ISO built-in is refused with
`permission_error(modify, static_procedure, PI)` as Scryer refuses it
(`iso_l3.lower_clause`; pinned by the `qualified_*` rows of
`tests/iso/test_builtin_redefinition_scryer.py`). A grammar rule with a
qualified head is refused ("a module-qualified head is not supported").

Options: (a) refuse a qualified head on every surface, as the grammar-rule
path does; (b) define `H` in `M` when `M` is the file's own module (or
`user` for a non-module file), and refuse it otherwise. The repository's
`clausal/tools/prolog_preludes/clausal_constants_trealla.pl` has
`user:`-qualified heads (a prelude for Trealla, not loaded by the engine,
but read by `tools/pl_parity.py`), so (a) changes that file's parity row.
