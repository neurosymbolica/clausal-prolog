# A literal dotted (LoadAttr-chain) head-arg reference is correct but unindexed

Found during the imported-atom index-key hotfix (fix/imported-atom-index-key,
2026-09-05). Originally filed as a much broader claim
("imported-atom-head-args-mostly-unindexed") based on inspecting a compiled
dispatch function's `__globals__` *after* compilation, which was the WRONG
signal (see "Corrected reading" below) — renamed and rewritten after the
fix's design review drove the actual fixtures and traced
`_build_arg_index` live during compilation.

## Corrected reading: indexing works for two of the three regression shapes

- **Bare single-hop `-import_from`** (`tests/fixtures/atom_index_bare_importer.clausal`):
  INDEXED. Traced live: `_build_arg_index(clauses, arity=2, pos=1, env=<base_globals>)`
  returns `{'buckets': {'aa': [...], 'bb': [...], 'cc': [...], 'dd': [...]}, 'n_distinct': 4}`.
  The compile-time `env` genuinely contains
  `'tests.fixtures.atom_index_owner.aa' -> 'aa'` etc. at bucket-build time —
  `globals_env.py`'s "Check globals_ directly" branch (~line 512-515,
  handling non-predicate values `_process_imports` stores under dotted
  keys) populates it, not the `sys.modules`-getattr branch the first pass
  blamed.
- **Atom re-exported through a package `__init__`, two import hops**
  (`tests/fixtures/atom_index_pkg_reexport_importer.clausal`, the
  diagnosis's own `mini/` shape, §9 item 2): ALSO INDEXED. Same live trace,
  same 4-bucket result. See
  `TestPackageReexportedAtomHeadArg::test_the_two_hop_reference_is_genuinely_indexed`
  in `tests/test_imported_atom_head_index.py`.

(The mistaken original claim came from inspecting
`predicate._dispatch_fn.__globals__` *after* compilation finished, which is
a different, already-pruned dict from the `env`/`base_globals` object
`_build_arg_index` actually saw live at bucket-build time — a false
negative, not evidence of a miss.)

## The one shape that genuinely IS unindexed

- **A literal dotted qualified reference written in source**
  (`-import_module` + `mod.attr` in the head, e.g.
  `tests/fixtures/atom_index_dotted_importer.clausal`): this compiles to a
  real `LoadAttr` CHAIN (`LoadAttr(object=LoadName('mod'), attr='attr')`),
  not a single dotted `LoadName`. `globals_env.py::_collect_globals_info`'s
  `_walk_body` only records a dotted call target for (a) `Call(LoadName)`,
  (b) `Call(LoadAttr)` (via `_dotted_name_from_loadattr`), or (c) a bare
  `LoadName` whose OWN `.name` already contains a `.` (the string the
  import machinery produces for a bare imported reference). A plain
  `LoadAttr` used as a VALUE (not a call target) matches none of those, so
  it is never added to `targets`, `_inject_resolved_targets` never runs on
  it, and `base_globals` never gets the dotted key — confirmed by the same
  live trace (`_build_arg_index` returns `None` for this fixture's
  position 1). The hotfix's `env` lookup correctly misses and falls back
  to `_INDEX_VAR` — CORRECT (full scan via real `unify()`, proven by
  `TestDottedQualifiedAtomHeadArg`), just unindexed.

## Fix direction

Teach `_collect_globals_info`'s `_walk_body` to also record a target for a
bare `LoadAttr` used as a value (not just inside a `Call`) — i.e. treat a
value-position `LoadAttr` the same as the `Call(LoadAttr)` case, adding
`(_dotted_name_from_loadattr(term), -1)` to `targets`. That is a narrow,
mechanical addition to an existing branch, not a new resolution mechanism —
`_inject_resolved_targets` already handles a `-1`-arity dotted target
correctly (see the `elif isinstance(term, LoadName) and "." in term.name`
sibling case it mirrors).

Related: todo/owa-unknown-functor-head-args-never-indexed-2026-09-05.md
(same "correct but unindexed" family). Natural home: P3-3 Task 4's
dispatch-closure work if still open, else its own small task.

## Acceptance

`tests/fixtures/atom_index_dotted_importer.clausal`, compiled with
`_INDEX_THRESHOLD` clauses, shows a real bucket for position 1 (traced
`_build_arg_index` call, or codegen evidence), not `None`/fallback scan.
