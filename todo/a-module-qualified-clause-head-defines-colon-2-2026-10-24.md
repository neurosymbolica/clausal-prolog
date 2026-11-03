# A module-qualified clause head defines `:/2` instead of the qualified predicate

Filed 2026-10-24, found in review of the ISO built-ins-are-static fix. OPEN.

**Status: PARTLY FIXED 2026-11-03.** A head (clause or grammar rule)
qualified with the file's OWN module -- the name its `module/2` gives --
now defines the predicate in that module, as in Scryer (`iso_l3`'s
`_strip_own_qualifier`); so does an own-qualified predicate indicator
`m:p/N` in `dynamic/1`, `discontiguous/1`, `table/1` and the
`constants_number_*` tables (`iso_l3_directives._strip_own_qualifier_pi`).
Pinned in `tests/test_module_qualified_clause_head.py`.
Still open, waiting on a ruling: every other qualifier (below).

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

## What is left (2026-11-03)

Scryer (the oracle build), checked 2026-11-03:

| Head | Where | Scryer |
|---|---|---|
| `a:baz(7).` | module `a` | `baz/1` in `a` (FIXED here too) |
| `a:g --> [a].` | module `a` | `g//0` in `a` (FIXED here too) |
| `b:qux(8).` | module `a` | `qux/1` added to module `b` (`b:qux(X)` gives 8; `a:qux(X)` existence_error) |
| `user:zed(9).` | module `a` | `zed/1` in `user` (callable unqualified from the toplevel) |
| `m:foo(1).` | no module/2 | `foo/1` in `m`; `foo(X)` existence_error |
| `user:bar(2).` | no module/2 | `bar/1` in `user` |
| `M:foo(1).`, `7:foo(1).` | anywhere | whole load refused: `permission_error(modify, static_procedure, (:)/2)` |

These still load as clauses of `(:)/2` here. Options:

- (a) Refuse every remaining qualified head, with Scryer's
  `permission_error(modify, static_procedure, (:)/2)` for a variable or
  non-atom module and a "a clause for another module is not supported"
  refusal for an atom. Simple; one Clausal file is one Python module and
  nothing else adds clauses to another module at load. Changes the
  `tools/pl_parity.py` row of `clausal_constants_trealla.pl` (its
  `user:` heads).
- (b) As (a), but treat `user:` in a file WITHOUT module/2 as the file's
  own module (its predicates are what that file's `-g` goals and
  importers see, the closest thing to Scryer's `user`). Keeps that prelude
  loading. Note the goal side does not do this today: `user:p(X)` in a
  non-module `.pl` file raises existence_error(procedure, p/1) even when
  the file defines p/1, so (b) should change both or neither.
- (c) Scryer's semantics: add the clause to the named module (creating
  it). Needs a way to contribute clauses to a module defined elsewhere
  (static, possibly already compiled and locked) -- a design question of
  its own.

Recommendation: (a) for variable/non-atom modules now (it is plain ISO
practice and Scryer agrees), and (b) for `user:`, with the goal side made
to match; (c) only if a real program needs it.
