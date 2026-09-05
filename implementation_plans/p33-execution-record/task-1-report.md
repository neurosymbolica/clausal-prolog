# Task 1 report — PredRow + authoritative store (additive)

Worktree: `/workspace/clausal-bug-fix/.claude/worktrees/p33-state-reloc`, branch
`feat/p33-state-reloc`, base HEAD `d3cfe27a`.

## Backing strategy chosen

**Option B from the brief: the existing dicts (`_clauses`, `_dispatch`,
`_lazy_recompile`, `_signatures`) stay the canonical storage, unchanged.
`PredRow` is a new thin read-through facade over them, cached per key in a new
`Database._rows` dict.**

Why: a grep for external consumers indexing these dicts directly turned up a
wide, heterogeneous surface — `db._clauses.get(...)`, `.keys()`, `in`,
`.clear()`, direct `[key]` subscript reads *and* writes, iteration — across
`stratification.py`, `compiler_v2.py` (x4 sites), `database_ops.py`,
`type_checks.py`, `testing.py`, and several tests
(`test_search.py::472-474`, `audit_2026_05_25/test_class_C04_...py`). Building
"thin dict-compat shim" objects that fully replicate `dict` semantics (get,
keys, `in`, `del`, `.clear()`, iteration order) for four separate containers
would have been the larger, riskier diff, and every one of those call sites
would need re-verification against the shim's semantics. Leaving the dicts
untouched means every existing public method on `Database`
(`assertz`/`asserta`/`retract`/`set_dispatch`/`get_dispatch`/
`register_signature`/`signature_for`/`clauses_for`/`mark_dynamic`/...) is
**not touched by this task at all** — zero lines changed in any of them — so
"byte-identical behavior" is true by construction, not by test coverage.

Concretely:
- `PredRow.clauses` is a **direct list-object reference**, captured once at
  row-mint time from `self._clauses.setdefault(key, [])`. All legacy mutation
  sites (`assertz`'s `.setdefault(key, []).append(...)`, `asserta`'s
  guarded `[key] = []` + `.insert(0, ...)`, `retract`'s `del ...[key][i]`) only
  ever mutate in place or `setdefault`-find the existing list — they never
  replace the dict value wholesale — so the identity holds forever once
  minted. Pinned directly: `test_row_clauses_is_the_same_list_object_assertz_mutates`
  asserts `db._clauses[key] is row.clauses`.
- `PredRow.dispatch_fn` / `.lazy_recompile` / `.signature` are **properties**
  that read/write straight through to `self._db._dispatch` /
  `._lazy_recompile` / `._signatures` (`.get(key)` / `[key] = value`) — always
  live, no staleness possible, no second store to fall out of sync.
- `PredRow.dynamic` is also a live property over the existing `self._dynamic`
  set (`mark_dynamic`/`is_dynamic`'s backing store) — free view coherence
  since that state already existed; wiring it costs nothing and is more
  faithful to "the Database is the authoritative store" than leaving it dead.
- `PredRow.backend` / `.locked` / `.source` / `.writes` are genuinely **new**
  state with no existing Database equivalent (backend selection is a Task 4
  concept, per-row lock state and load-attribution are Task 2/3 concepts) —
  plain dataclass fields with the defaults the Interfaces block specifies
  (`backend="python"`, `locked=False`, `source=None`, `writes=[]`). Nothing
  reads or writes them yet outside the new tests, so they cannot be a source
  of behavior change this task.

`Database.row(functor, arity, create=False)`:
- Returns the cached row if one already exists for the key.
- Otherwise treats the predicate as "known" (and safe to auto-vivify even
  with `create=False`) if the key is already present in *any* of
  `_clauses`/`_dispatch`/`_lazy_recompile`/`_signatures`/`_dynamic` — i.e. a
  predicate that only ever went through a legacy path (e.g. plain
  `db.assertz`, never touching `.row()`) is still discoverable. This is what
  makes the Database "authoritative" regardless of entry door.
- Otherwise (`not known and not create`) returns `None`.
- Minting always does `self._clauses.setdefault(key, [])` first (so the
  clauses list exists and is captured by reference) before constructing and
  caching the `PredRow`.

No behavior-changing side effect is possible from any of this in the current
codebase: `Database.row()` is a brand-new method that nothing in production
code calls yet (confirmed by grep — the only callers are the new tests), so
whatever internal bookkeeping it does (e.g. `setdefault`-creating an empty
`_clauses[key]` entry when minting on a previously-clauseless key) cannot
alter any existing observable behavior this task; that mechanism only starts
to matter once Task 2+ wires callers onto it.

`PredRow.invalidate()` clears `dispatch_fn` only (`self.dispatch_fn = None`),
leaving `lazy_recompile` untouched — matches the brief exactly and is now (by
convention, per the brief; structurally enforced starting Task 3) the one
sanctioned invalidation spelling.

`WriteStamp = namedtuple("WriteStamp", "author kind detail")`, exported from
`clausal.logic.database`. `PredRow.record_write(author, kind, detail=None)` is
the append-with-cap helper (name and signature are new — the Interfaces block
specifies only the `writes: list[WriteStamp]` field and "append-only, capped
at 32", not a method name; `record_write` is what Task 3's `Database.mutate`
provenance stamping is expected to call). It appends a `WriteStamp` and trims
to the last 32 entries (`del self.writes[: len(self.writes) - 32]`). Nothing
calls this outside the new tests this task — Task 3 wires it into
`Database.mutate`.

## Files changed

- `clausal/logic/database.py`: added `WriteStamp`, `PredRow` (new class, ~90
  lines, placed between `Clause` and `Database`), `Database._rows` (new dict
  in `__init__`), `Database.row()` (new method). Zero lines changed inside
  any pre-existing method body. `__all__` extended with `PredRow`,
  `WriteStamp`.
- `tests/test_predrow.py` (new): 23 tests — row identity/create semantics,
  view coherence in both directions for `clauses`/`dispatch_fn`/
  `lazy_recompile`/`signature`/`dynamic`, `invalidate()` clears dispatch only,
  `PredRow` defaults for the not-yet-wired fields, `WriteStamp` shape, and the
  32-entry write cap (40 appends → last 32 survive, oldest 8 dropped, order
  preserved).
- `tests/test_funnel_lint.py`: one `AllowEntry` line-range update, see gate
  evidence below — not a behavior change, a lint-allowlist re-pin.

## TDD evidence

1. Wrote `tests/test_predrow.py` against the pre-implementation file; ran it
   first — collection failed with `ImportError: cannot import name 'PredRow'
   from 'clausal.logic.database'` (expected red).
2. Implemented `PredRow` + `Database.row()`; reran — `23 passed`.
3. Ran a covering set (`test_predrow.py`, `test_low_level_db_mutation_sync.py`,
   `test_predicate_meta.py`, `test_search.py`, `test_tabling_lifecycle.py`,
   `test_directives.py`, `test_functor_reexport.py`,
   `test_functor_arity_conflict.py`, `test_specialization.py`,
   `test_specialization_pipeline.py`, `test_listing.py`) — `506 passed`.

## Gate evidence

Full suite command (foreground, from worktree root):
```
/workspace/clausal/venv/bin/python -m pytest tests/ --continue-on-collection-errors --tb=no -q -rf
```

First run (before the funnel-lint fix): `145 failed, 12080 passed, 56
skipped, 39 xfailed, 748 warnings, 1 error` — one MORE failure than baseline.
Diffing failure-name sets against `baseline-failed-names.txt` isolated exactly
one new name:
`tests/test_funnel_lint.py::test_migrated_tree_has_no_disallowed_funnel_bypass_patterns`.

Root cause (verified, not guessed): this lint keys its `ALLOWLIST` by
`(file, line-range)`. `clausal/logic/database.py` already had a pre-existing
allowlisted pattern — `isinstance(head, PredicateMeta) and not head._fields`
inside `head_key` — pinned at lines `(541, 573)`, with a comment recording
that the *same thing* happened during P3-2 Task 3 (a mechanical line shift
from an earlier insertion in the same file moved this pre-existing pattern
out of its old allowlisted range). Inserting the new ~90-line `PredRow` class
+ `Database.row()` earlier in the file pushed `head_key`'s body from
541-573 down to 670-698. Confirmed by grep (`isinstance(head, PredicateMeta)
and not head._fields` now at line 694) and by the lint's own failure message
citing line 694. This is the identical mechanical-shift situation the
existing comment already documents a precedent for, not a new bypass site
and not a semantic change — `head_key` itself is byte-identical, only its
line number moved.

Fix: updated the `AllowEntry` range in `tests/test_funnel_lint.py` from
`(541, 573)` to `(668, 700)`, following the same annotation style as the
prior shift's comment (added a new comment line documenting this second
shift, citing this report).

Second run (after the fix):
```
144 failed, 12081 passed, 56 skipped, 39 xfailed, 748 warnings, 1 error in 102.35s (0:01:42)
```
Failure-name-set diff against `baseline-failed-names.txt`: **empty** (`diff`
exit code 0, both sets 144 names, byte-identical). Passed count is baseline's
12058 + 23 (the new `test_predrow.py` tests) = 12081, exactly as expected.
Run executed — confirmed (timed, non-zero duration, summary line present,
full output saved at `.superpowers/sdd/p33-state-relocation/task-1-full.txt`).

**Gate: PASS.**

## Commits

One commit: `clausal/logic/database.py` (PredRow + Database.row()),
`tests/test_predrow.py` (new), `tests/test_funnel_lint.py` (allowlist re-pin).

## Concerns / notes for later tasks

- The funnel-lint allowlist is line-pinned and this is now the SECOND time a
  file insertion earlier in `database.py` has shifted it. Task 2 (which
  explicitly touches `database.py` again — deleting the mirror blocks and
  `_pred_cls_for`) should expect to re-pin this same `AllowEntry` again, and
  should check `tests/test_funnel_lint.py`'s self-check test
  (`test_1b`/ALLOWLIST self-check) as part of its own gate run, not just the
  covering set.
- `PredRow.record_write`'s name/signature is my choice, not brief-mandated;
  flagging so Task 3's `Database.mutate` provenance wiring either reuses it
  or renames it deliberately (grep-enforced "one spelling" per the plan's
  Task 2 note applies just as much here).
- `locked` and `source` are inert placeholders this task (no backing store
  exists yet for either) — this is intentional per the brief's scope, not an
  oversight; Task 2/3 give them real semantics.

## Fix round 1 (review findings)

Two Important findings from review, both in `clausal/logic/database.py` /
`tests/test_predrow.py`.

### Finding 1 — `clauses` was a captured reference; `_rows` cache uninvalidated

`PredRow.clauses` was a plain dataclass field, captured once (`self._clauses
.setdefault(key, [])`) at row-mint time. A wholesale wipe of the backing
dicts — a pattern that already exists in this suite
(`tests/test_search.py:472-474`: `db._clauses.clear(); db._dispatch.clear();
db._lazy_recompile.clear()`) — replaces the dict's value objects out from
under any already-minted row: the cached `PredRow.clauses` list becomes an
orphan (copy-not-alias divergence), and `Database._rows` never gets a chance
to re-mint since it's an unconditional cache hit. Untested in the original
submission.

**Fix:** `clauses` is now a property, matching the other four read-throughs:
`return self._db._clauses.setdefault(self._key, [])`. Same-object-as-canonical
holds BY CONSTRUCTION on every access; after a wipe, the very next `.clauses`
read re-aliases the fresh entry the wipe (or a subsequent legacy write)
leaves behind. The `_rows` cache itself is left exactly as it was — per the
controller's direction, the cached `PredRow` object surviving a wipe is
harmless now that every one of its fields is a live read-through, so there
is nothing to invalidate.

Test added: `test_row_self_heals_across_wholesale_backing_dict_wipe` — mints
a row, asserts pre-wipe `clauses`/`dispatch_fn` agree with a legacy
`assertz`/`set_dispatch`, wipes `_clauses`/`_dispatch`/`_lazy_recompile` (the
exact `test_search.py` pattern), then asserts `row.clauses is
db._clauses[key]` (re-aliased, not stale), `row.clauses == []`,
`row.dispatch_fn is None`, and that a subsequent legacy `assertz` is visible
through the row again. All prior identity/view-coherence tests kept as-is —
they still pass unchanged since a live property is a strict behavioral
superset of the old captured-reference field for every case they exercised.

### Finding 2 — `row()`'s eager `_clauses.setdefault` silently flipped `is_defined()`

`Database.row()` unconditionally did `self._clauses.setdefault(key, [])` at
mint time, for every row including ones auto-vivified purely from
dispatch/signature/dynamic state (`test_row_dispatch_fn_reads_through_set_
dispatch` in the original submission is exactly this setup: `set_dispatch`
only, no clauses ever asserted). That silently flipped `db.is_defined(f, a)`
from `False` to `True` as a side effect of merely calling `db.row(f, a)` —
a real, if latent, behavior-visible side effect of a "read-only" call.

**Fix:** removed the eager `_clauses.setdefault` from `row()` entirely — it
now only decides whether the key is "known" (by membership, not by mutating
anything) and constructs `PredRow(self, key)` with no clauses argument.
Finding 1's `clauses` property makes vivification happen lazily, and only at
the point that's actually mutating: the first `.clauses` read. This narrows
the side effect from "calling `db.row()`" to "reading `row.clauses`" and it
is now documented explicitly in the property's docstring, with a pointer to
Task 2's compile-install path as the real, deliberate minting site going
forward.

Tests added:
- `test_row_create_false_on_dispatch_only_predicate_does_not_flip_is_defined`
  — pins that `db.row(f, a, create=False)` on a dispatch-only predicate
  leaves `is_defined` `False`.
- `test_row_clauses_first_read_lazily_vivifies_is_defined` — pins that the
  first `row.clauses` read on that same row *does* flip it to `True`,
  documented as intended (not a regression to chase later).

### Side effect on the funnel-lint allowlist (again)

Both fixes added lines earlier in `database.py` (the new `clauses` property
plus its docstring), mechanically shifting `head_key`'s pre-existing
`atom_bypass` pattern again — from line 694 (round 1's pin, `668-700`) to
line 717. Same situation as round 1 and the P3-2 precedent it cites: caught
immediately by the covering run (`test_funnel_lint.py` was failing again on
collection before this re-pin), confirmed by grep, not a semantic change.
Re-pinned `tests/test_funnel_lint.py`'s `AllowEntry` range to `(691, 723)`
with a comment documenting this second shift.

### Covering results (fix round 1)

```
/workspace/clausal/venv/bin/python -m pytest tests/test_predrow.py -q --tb=short
```
→ `26 passed` (23 original + 3 new: 1 for Finding 1, 2 for Finding 2).

```
/workspace/clausal/venv/bin/python -m pytest \
  tests/test_predrow.py tests/test_low_level_db_mutation_sync.py \
  tests/test_predicate_meta.py tests/test_search.py \
  tests/test_tabling_lifecycle.py tests/test_directives.py \
  tests/test_functor_reexport.py tests/test_functor_arity_conflict.py \
  tests/test_specialization.py tests/test_specialization_pipeline.py \
  tests/test_listing.py tests/test_funnel_lint.py -q --tb=short
```
→ `518 passed` (the same covering set as the original submission, plus
`test_funnel_lint.py` added explicitly since this fix round touches its
allowlist a second time). No full-suite rerun performed per the controller's
instruction (diff stays inside `database.py` / `test_predrow.py` /
`test_funnel_lint.py`, all three exercised directly by this covering run).

### Files changed (fix round 1)

- `clausal/logic/database.py`: `PredRow.clauses` field → property
  (setdefault-backed, live); `Database.row()` no longer touches `_clauses`
  at mint time; docstrings updated on both.
- `tests/test_predrow.py`: +3 tests (self-heal-across-wipe;
  create-false-does-not-flip-is_defined; first-clauses-read-does-flip-it).
- `tests/test_funnel_lint.py`: `AllowEntry` range re-pinned `668-700` →
  `691-723` (second mechanical shift, same file).
