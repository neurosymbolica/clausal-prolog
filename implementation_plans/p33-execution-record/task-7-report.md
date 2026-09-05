# P3-3 Task 7 report — specialization stops minting

Branch `feat/p33-state-reloc`, base `c3e9943a`, commit `d1812072`.

---

## 1. What changed and why, per file

### `clausal/logic/specialization.py`

The three `specialize_mi*` entry points each spelled the SAME install block for
themselves: `make_predicate(new_name, fields)`, then a throwaway
`Database(module_dict=module_dict)`, then `db.assertz(clause)` per clause into
that throwaway, plus a `db.module_dict[new_name] = pred_cls` write so
`db.assertz` could resolve through the class and a `pred_cls._assertz(clause)`
fallback for when there was no module dict. The defining module's own database
never heard of the predicate: **`db.row("SolveCountNatnum", 2)` answered `None`
while the class answered queries** (probe run on the pre-change tree, module
`tests.fixtures.specialize_natnum`; `Database({NatnumProgram/1, Test/1})` — the
specialized predicate simply absent).

* **`SPECIALIZE_AUTHOR_PREFIX = "specialize:"` + `_specialization_author(db)`
  (:252, :255)** — new. The author string a specialization's writes are stamped
  with. See §3 for why it is derived from `load_author()` rather than a bare
  constant.
* **`_defining_db(db, module_dict)` (:260)** — new. Resolves which
  `Database` the specialized predicate is a row of: the caller's when it passes
  one, otherwise a per-call `Database` over the caller's namespace. Ruling and
  reasoning in §3.
* **`_install_specialized(pred_cls, new_name, fields, clauses, db,
  module_dict, solve_goal_name=None, goal_map=None)` (:289)** — new, and
  the single copy of what the three sites each duplicated. In ONE
  `db.mutate(new_name, arity, author=…, kind=WRITE_LOAD_CLAUSES,
  detail="-specialize", through=pred_cls)` transaction it (fix round 1 F5
  moved the namespace writes inside it too, and F3 respelled the channel)
  (a) `pred_cls._bind_row(db, new_name, arity, authorized=True)`,
  (b) `pred_cls._ensure_clauses()[:] = clauses`,
  (c) `db.register_signature(new_name, arity, tuple(fields))`,
  (d) claims `row.source` for the specialization author when nobody owns the
      row yet,
  (e) `compile_predicate_trampoline(...)`, nested inside the same transaction
      so the gate's exit does not invalidate the dispatch the compile just
      installed.
  The `module_dict`-write + `_assertz`-fallback dance is DELETED with the
  second store it existed to keep in step: after (a), `pred_cls._clauses` IS
  `db._clauses[(new_name, arity)]`.
  `through=pred_cls` puts the class's CURRENT row in the write's blast radius,
  so a `pred_cls` handed in from outside that is already somebody else's
  predicate is refused rather than silently rebound.
* **`specialize_mi` (:368, `db` param at :375, install at :424)**,
  **`specialize_mi_deep` (:1381 / :1389 / :1448)**, **`specialize_mi_cpd`
  (:1716 / :1724 / :1784)** — each
  gains a trailing `db: "Database | None" = None` parameter (purely additive:
  no existing positional call shape moves) and each 30-line install block
  collapses to one `_install_specialized(...)` call. The three
  `make_predicate(new_name, fields)` minting sites at the old :277 / :1313 /
  :1671 are unchanged as *mints* — what changed is that the minted class is now
  bound to a row before anything is written through it.
* Module docstring (:13–:16) updated to say the entry point registers a ROW.

### `clausal/logic/compiler_v2.py`

* **`_run_specialization` (`db=db` at :1022, :1027, :1032)** — passes `db=db` to all three
  specializer calls. This is the whole "defining module" story for the real
  path: `_run_specialization` already held the module's `Database` and simply
  did not hand it over.
* **`_refuse_untablable_target` (:826; the alias branch at :850)** — the `-specialize` alias
  refusal's stated reason ("`-specialize` compiles it against a database of its
  own that no `-table` directive reaches") is now FALSE, so it is reworded to
  what is still true ("the specializer compiles and installs the alias's
  dispatch itself, after this directive's wrapper"). The refusal itself is
  KEPT, with a comment recording why: Task 7 relocates state and does not get
  to lift a refusal on an unmeasured guess. `tests/test_tabling_lifecycle.py`
  pins only `-table(SolveTiny/1)` and `-specialize alias`, both still present.
  See §7.

### `clausal/logic/predicate.py`

* **`make_atom(name) -> str` (:1611)** — now returns the plain atom
  `str`. Controller ruling: atoms have been `str` since the P3-1 pivot, and a
  public factory minting a zero-arity `PredicateMeta` was the one door left in
  the public API through which a class atom could enter a program that has none
  anywhere else. Zero engine callers and zero `packages/` callers (verified by
  grep; the only in-tree references left are documentation). `__all__` export
  kept. Docstring says it exists for API continuity and points at
  `make_predicate(name, [])` for a /0 predicate class.
* **`:701` comment** — no longer names `make_atom` as a class-atom construction
  API (it isn't one any more).
* **`_bind_row` (:800)** — fix round 1 F6: its docstring and body comment now
  name `specialization._install_specialized` as the second authorized
  re-binder alongside `compiler_v2` step 4.

### `clausal/logic/builtins/inspection.py`

* **`:511` docstring** — the "legacy 0-arity `PredicateMeta`" shape is now
  described as `make_predicate(name, [])`'s, not `make_atom`'s. No code change;
  the builtin still dual-accepts that shape.

### Tests

* `tests/test_specialization_pipeline.py` — new class
  `TestSpecializedPredicateIsARow` (11 tests after fix round 1) and a
  `_module_db(mod)` helper.
* `tests/test_specialization.py` — new class
  `TestSpecializedPredicateIsARow` (9 tests).  20 new tests in total.
* `tests/fixtures/specialize_clobber.clausal` — new, fix round 1 F3.
* `tests/test_predicate_meta.py` — `TestMakeAtom` inverted (§4).
* Six suites' `make_atom(...)` call sites switched to
  `make_predicate(..., [])` (§4).

---

## 2. Brief checkbox → the test that pins it

| Checkbox | Pinned by |
| --- | --- |
| Each site registers a row in the defining module's db (`db.row(new_name, arity, create=True)` + signature) | `test_specialization_pipeline.py::TestSpecializedPredicateIsARow::test_row_exists_in_module_db`, `…::test_class_reads_the_module_row`, `…::test_signature_registered`, `…::test_clauses_visible_in_module_db`; API side: `test_specialization.py::…::test_row_registered_in_the_callers_db`, `…::test_signature_registered_in_the_callers_db` |
| …and installs compiled dispatch through the Task-3 gate, author = specialization | `test_specialization_pipeline.py::…::test_dispatch_installed_on_the_module_row`, `…::test_write_is_gate_stamped_with_the_specialization_author`, `…::test_first_write_claims_ownership_for_that_author`; API side: `test_specialization.py::…::test_clauses_and_dispatch_land_in_the_callers_db`, `…::test_write_is_gate_stamped`, `…::test_respecialization_by_the_same_author_is_permitted` |
| All three sites (shallow / deep / CPD) | `test_specialization.py::…::test_deep_and_cpd_register_rows_too` (+ the fixture suites: `specialize_deep.clausal` exercises deep, `specialize_cpd.clausal` CPD, all now through the module db) |
| Returned handle: the row-linked class (see §3) | `…::test_class_reads_the_module_row`, `…::test_no_db_still_row_linked` |
| Generated-goal references inside specialized bodies resolve via the same db rows | `test_specialization_pipeline.py::…::test_specialized_calls_specialized_through_row_dispatch` (the unfolder's recursive call: the compiled dispatch's `__globals__` entry for the predicate IS the row-linked class, and its `_get_dispatch()` IS `db.get_dispatch(...)`), `…::test_sibling_specializations_are_the_row_linked_classes`, `…::test_deep_and_shallow_share_one_module_db` |
| …a specialized predicate calling ANOTHER specialized one | `test_specialization.py::…::test_specialized_calls_specialized_through_the_shared_db` — two specializations into ONE database, the second's object program naming the first. The route is the residual one, not a lowered body goal (see §5 deviation 6): the goal survives as a term, `_SolveGoal_T7Outer` resolves it through `module_dict` to the callee's `_get_dispatch()`, hence to the callee's row, and the answers are right (`wrap(s(0))` succeeds once, `wrap(a)` fails) |
| `make_atom` returns the interned str | `test_predicate_meta.py::TestMakeAtom::test_returns_the_atom_str` (+ `test_repeated_calls_agree`, `test_hashable`, `test_unify`); the /0-class behaviour it used to provide is pinned at its new address by `…::test_zero_arity_predicate_class_comes_from_make_predicate` |
| Answers unchanged | `…::test_specialized_answers_are_unchanged`, plus the 234 pre-existing tests in the two specialization suites, all green |
| Full suite diff == ledger | §6 |

---

## 3. Per minting site: db, author, and what consumers get

All three sites are the same shape, so the decisions are common.

**The defining module's db.** `compiler_v2._run_specialization` is the only
non-test caller in the tree (grep over `clausal/`, `packages/`, `tests/`), and
it already holds the `Database` it is compiling — it just never passed it. So
the ruling is: **the caller names the defining module by passing `db=`, and
`compiler_v2` now does.** Two candidate derivations were considered and
rejected:

* *From the MI pattern's own `_home_db`* — actively WRONG here. In every
  fixture the MI is `-import_from`'d (`clausal.examples.metainterpreters`), so
  the pattern's home db is the EXPORTER's, not the module doing the
  specializing; deriving from it would file `SolveCountNatnum` in
  `clausal.examples.metainterpreters`'s database and, for the ~100 direct-API
  tests, dump test predicates into that shared module db.
* *From `module_dict["$module"].db`* — WRONG at the moment it would be read.
  `import_hook` seeds `module_dict["$module"]` with a placeholder `Module`
  whose `db` is a DIFFERENT `Database` from the one `compile_module` builds,
  and only swaps in the real one AFTER `compile_module` returns — i.e. after
  step 6b has run. A silently-wrong fallback is worse than no fallback.

**The no-db call shape (the direct Python API).** `specialize_mi(pattern,
program, name)` from a test or a script has no module, and therefore no
defining module database. RULING: it keeps a `Database` of its own, one per
specialization call, over the caller's `module_dict` when there is one — which
is exactly what the old code built, so nothing regresses. What makes it not the
free-floating shape this task removed is that the returned class READS that
database's row: the predicate is registered, signed, gate-stamped and
dispatched out of a real row instead of out of class attributes, and the
database is reachable from the handle the caller holds (`pred_cls._row.db`).
Pinned by `test_no_db_still_row_linked`. A single process-wide
`Module("specialization")` database was NOT used, per the controller's ruling —
it would be the free-floating shape wearing a name.

**The author string.** `f"specialize:{db.load_author()}"`
(`SPECIALIZE_AUTHOR_PREFIX` + the load author), e.g.
`specialize:/…/tests/fixtures/specialize_natnum.clausal`. Reasoning, having
read `write_refusal`:

* `mutate` never sets `row.source` — it only stamps `row.writes` — so a write
  claims ownership only if the writer assigns `source`. For a NEW row
  (`source is None`) `write_refusal` permits a `WRITE_LOAD_CLAUSES` outright
  (rule 3's `if owner is None: return None`), so the FIRST specialization write
  is always allowed; `_install_specialized` then sets
  `row.source = (db.module_name(), author)` **only when `row.source is None`**,
  which is what makes the first write claim ownership for the specialization
  author. A later write by that same author is then permitted by rule 1
  (`author == owner`) — pinned by
  `test_respecialization_by_the_same_author_is_permitted`.
* A bare `"specialization"` would satisfy the same two properties (rows are
  per-database, so two modules cannot collide), but it names nobody. An author
  string is provenance — that is the whole reason `load_author` is a source
  path and `runtime_author` carries the module — so the stamp says WHICH load's
  specializer wrote the row. `write_refusal` is untouched.
* The `specialize:` prefix keeps the specialization author DISTINCT from the
  plain load author, so a `-specialize` target the module also writes clauses
  for at load is a refused clobber rather than a silent merge. No fixture does
  that; the refusal is the conservative direction.

**What consumers get back.** Every consumer of the returned handle needs the
CLASS API, so all three sites keep returning `pred_cls` — now row-linked.
Grepped consumers:

* `compiler_v2._run_specialization` — binds `specialized_cls` and relies on
  `module_dict[new_name]` being a `PredicateMeta` for step 7's `_lock()` sweep
  and for every call site that resolves the alias by name.
* `tests/test_specialization.py` (~100 call sites) — `pred_cls._clauses`,
  `pred_cls._fields`, `call(pred_cls, …)`.
* `tests/test_specialization_pipeline.py` — `isinstance(..., PredicateMeta)`,
  `._clauses`, `._dispatch_fn`, `call(...)`.
* `packages/` — no callers at all.

There is no consumer that needs only name+dispatch, so nothing was switched to
that; inventing a new return type nobody asked for was declined, per the brief.

---

## 4. INVERSION LEDGER

### (a) `make_atom` — assertion inversions (`tests/test_predicate_meta.py`, `TestMakeAtom`)

| # | Before → After |
| --- | --- |
| 1 | `test_returns_predicate_meta`: `assert isinstance(make_atom("a"), PredicateMeta); a._fields == (); a._arity == 0` → `test_returns_the_atom_str`: `assert type(make_atom("a")) is str; a == "a"; not isinstance(a, PredicateMeta)` |
| 2 | `test_call_returns_self`: `a = make_atom("a"); assert a() is a` → re-homed as `test_zero_arity_predicate_class_comes_from_make_predicate`: `a = make_predicate("a", []); assert a() is a` (plus `_fields`/`_arity`) |
| 3 | `test_different_calls_different_identity`: `assert make_atom("a") is not make_atom("a")` → `test_repeated_calls_agree`: `assert make_atom("a") == make_atom("a")` |
| 4 | `test_hashable`: `d = {a: 42}; assert d[a()] == 42` → `d = {a: 42}; assert d["a"] == 42` |
| 5 | `test_unify`: `assert deref(x) is a` → `assert deref(x) == "a"` |

### (b) `make_atom` — call sites that genuinely need a /0 predicate class (25 sites, behaviour preserved, no assertion changed)

| File | Sites | Before → After |
| --- | --- | --- |
| `tests/test_first_arg_index.py` | 7 | `make_atom("Red"\|"usd"\|"non_o_a"\|"non_o_x"\|"ltr"\|"smart_t"\|"unrestricted")` → `make_predicate(<same>, [])` |
| `tests/test_predicate_arity_mismatch_diagnostic.py` | 9 | `make_atom("arcm_dynatom"\|"arcm_dyn"\|"arcm_empty"\|"arcm_compound"\|"arcm_compound_var"\|"arcm_junk"\|"arcm_mixed"\|"arcm_boom")` and `make_atom(name)` → `make_predicate(<same>, [])` |
| `tests/test_global_atoms_default.py` | 3 | `make_atom("tsaa_class_atom"\|"tiav_class_atom"\|"tfasa_class_atom")` → `make_predicate(<same>, [])` |
| `tests/test_funnel_accessors.py` | 2 | `foo_atom = make_atom("foo")`, `make_atom("baz")` → `make_predicate("foo", [])`, `make_predicate("baz", [])` |
| `tests/test_standard_order.py` | 2 | `atom_cls = make_atom("work")` ×2 → `make_predicate("work", [])` |
| `tests/test_functor_arity_conflict.py` | 2 | `make_atom("fac_bare_atom"\|"fac_identity")` → `make_predicate(<same>, [])` |

Imports updated in each of those six files (`make_atom` dropped;
`make_predicate` was already imported in all of them).

Docstrings that named `make_atom` as the class-atom construction API, retargeted
(no assertions): `tests/test_standard_order.py:185`,
`tests/test_predicate_arity_mismatch_diagnostic.py:768`,
`tests/test_term_inspection.py:858`, `tests/test_first_arg_index.py:133`,
`clausal/logic/predicate.py:701`, `clausal/logic/builtins/inspection.py:511`.

### (c) Specialized-class attribute pins (`__module__`, class identity) → row/name pins

**NONE — the expected inversions did not exist.** Grepped
`tests/test_specialization.py`, `tests/test_specialization_pipeline.py` and
`tests/test_callsite_specialization.py` for `__module__` (0 hits) and for
class-identity assertions on a specialized class (`is <name>`, `_dispatch_fn
is`, `_clauses is`) — the only hit is
`test_specialization_pipeline.py:69`'s `._dispatch_fn is not None`, which is a
non-None check, not an identity pin, and still passes unchanged (it now reads
the module row through the class). No specialization test asserted anything
about where the class lived, which is precisely how the free-floating shape
survived this long. The new tests add the row/name pins that were missing.

---

## 5. Deviations from the brief

1. **"the 4th site from Task 0's sweep"** — per the controller's ruling, that
   is the `import` statement at specialization.py:26, not a call site. Three
   minting sites, no `make_atom` call in specialization.py. Handled as ruled.
2. **`make_atom` scope** — the controller's list of test files to invert was
   indicative; the grep also found `tests/test_standard_order.py` and
   `tests/test_functor_arity_conflict.py`, and `tests/test_term_inspection.py`
   turned out to be a docstring mention only. All are ledgered above.
3. **`compiler_v2._refuse_untablable_target`'s diagnostic text** — not named in
   the brief, but the change makes its stated reason false, so it was reworded
   (behaviour unchanged, refusal kept). Rationale in §1 and §7.
4. **Two doc-comment fixes outside the named files**
   (`clausal/logic/predicate.py:701`, `clausal/logic/builtins/inspection.py:511`)
   for the same reason: they described `make_atom` as minting a class.
5. **Signature shape** — `db` was added as the LAST parameter of each entry
   point rather than beside `module_dict`, so no existing positional call moves.
6. **The second checkbox's "existing fixture showing a specialized predicate
   calling another specialized one" was substituted** (added fix round 1, per
   controller ruling on F2). No existing fixture has that shape, and none can:
   the unfolder emits NO alias-to-alias code reference, so specialization does
   not lower one alias's call to another. The mechanism that exists is the
   residual one — the goal survives as a term, the catch-all clause hands it to
   `_SolveGoal_<name>`, and `_make_solve_goal_predicate`'s
   `module_dict.get(functor)` -> `pred._get_dispatch()` fallback
   (specialization.py:1234-1239) takes it to the callee's row. That is what
   `test_specialization.py::...::test_specialized_calls_specialized_through_the_shared_db`
   pins, and `_get_dispatch` is precisely what Task 7 moved off a dropped
   Database and onto the shared one. A new mutually-calling fixture was NOT
   built, per the ruling.
7. **`globals_ = module_dict or {}` -> `module_dict if module_dict is not None
   else {}`** — a latent bug fixed in passing. The old spelling substituted a
   THROWAWAY dict whenever the caller passed an empty-but-real `module_dict`,
   so the specialized name and its `_SolveGoal_` dispatcher were installed into
   a dict the caller never saw, and the compile ran against a namespace the
   module did not own. `is not None` is the question that was meant.

---

## 6. Suite gate evidence

```
PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest tests -q \
  -p no:cacheprovider --continue-on-collection-errors -rfE
```
run in the foreground from the worktree.

* Result line: **`144 failed, 12352 passed, 56 skipped, 39 xfailed, 748
  warnings, 1 error in 100.46s`** — 144 + 1 = **145 names**.
* `.superpowers/sdd/p33-state-relocation/task-7-failed-names.txt` (145 lines)
  vs `task-3-base-failed-names.txt` (145 lines):
  `cmp` → **byte-identical**; `comm -3` → **0 lines**.
* The known wall-clock flake `test_F026_multi_star_splits_bounded_for_moderate_input`
  did not appear in any of the three full runs made during this task.
* `clausal.__file__` asserted under the worktree before every run
  (`/workspace/clausal-bug-fix/.claude/worktrees/p33-state-reloc/clausal/__init__.py`).
* Targeted: `tests/test_specialization.py` + `tests/test_specialization_pipeline.py`
  + `tests/test_tabling_lifecycle.py` + `tests/test_callsite_specialization.py`
  = **302 passed**; the six `make_atom` suites + `test_predicate_meta.py` +
  `test_term_inspection.py` = **463 passed**.
* TDD: 17 of the 19 new tests were written first.  The 9 pipeline tests were
  all RED pre-implementation (`9 failed, 62 deselected`); of the 8 API tests
  written first, 7 were RED and `test_no_db_still_row_linked` passed, because
  `compiler._install` already bound the class to the THROWAWAY db's row —
  which is exactly the bug: the right mechanism against the wrong database.
  It is kept as the regression pin for that mechanism.  Two tests were added
  after the implementation, to pin the second checkbox once the shape it
  describes existed to observe: `…pipeline…::test_sibling_specializations_
  are_the_row_linked_classes` and `…::test_specialized_calls_specialized_
  through_the_shared_db`.

---

## 7. Concerns

1. **The `-table` × `-specialize` refusal is now over-broad, probably.** It was
   justified by the private database, which is gone; the specialized dispatch
   now goes through `_install` → `ensure_tabled_wrapper` on the module's own
   db, so a tabled alias would very likely just work. I did not lift it: it is
   a behaviour change nothing in this task measures, and the ordering question
   (step 6a wraps, step 6b recompiles) deserves its own verification. Reworded
   the reason, kept the refusal, left a comment naming the follow-up.
2. **A module that both `-specialize`s to a name and writes clauses for it at
   load is now REFUSED** (load owns the row with clauses; the specialization
   author is different → rule 3). Before, the specializer silently overwrote
   `module_dict`. No fixture or test does this, so nothing observes the change;
   I judged refusing the clobber the right direction, but it is a new refusal
   and worth a reviewer's eye.
3. **`db.assertz`'s head-key validation is no longer on the specialization
   path.** The clauses are written straight into the row
   (`_ensure_clauses()[:] = clauses`, mirroring compiler_v2 step 4) instead of
   one `db.assertz` per clause, so `_stored_head_key`'s shape check no longer
   runs over specialized heads. Those heads are `pred_cls(**fields)` instances
   built by the unfolder, so the key is known by construction — but it is one
   fewer assertion on generated code.
4. **The no-db call shape still has a database nobody else can reach.** It is
   now a real, row-backed, stamped database owned by the returned class rather
   than an anonymous throwaway, and there is no module for it to belong to —
   but if the program later wants `specialize_mi` to file into a caller's
   module, the caller must pass `db=`. Ruled in §3; flagging it because it is
   the one part of the checkbox that is satisfied by argument rather than by
   construction.
5. **Write-stamp count.** One `WriteStamp` per specialization, not one per
   clause: the nested `set_dispatch`/`_install` transactions inherit the outer
   one, as designed by Task 3. Anything downstream that counted stamps to infer
   clause counts would see a change; nothing in tree does.


---

## Fix round 1

Commit `4687fc18` (Task 7 itself: `d1812072`). All eight findings addressed; none declined.

### F1 (Important) — docs pointed at a `make_atom` that no longer mints a class

* `docs/for_python_programmers.md:155-163` — the executable block
  (`is_atom(ok)`, `ok() is ok`) was false / `TypeError` after the change.
  Rewritten: `make_atom("ok")` shown returning `'ok'`, checked with
  `is_atom_value`, followed by a sentence pointing at `make_predicate("ok", [])`
  (and `is_atom`) for the zero-arity **class**.
* `docs/syntax.md:326` — "mint one dynamically with `make_atom("not")`" ->
  "mint the zero-arity class dynamically with `make_predicate("not", [])`
  (`make_atom("not")` returns the plain atom `str`)".
* `docs/builtins.md:1032-1035` (`atom/1`) — "or dynamically via
  `make_atom("name")`" -> `make_predicate("name", [])`, plus the note that
  `make_atom` returns the str. The adjacent "Does not match plain strings"
  sentence is pre-existing P3-1 staleness outside this finding's scope and was
  left alone rather than silently widened into.
* `docs/iso_prolog_compatibility_report.md:161-168` — the API block now shows
  both: `make_atom("red")` -> the str, checked with `is_atom_value`; and
  `make_predicate("red", [])` -> the class, checked with `is_atom`, with
  `Red() is Red`.
* `docs/syntax.md:662` left untouched per the ruling — minting a
  non-identifier atom with `make_atom("any name")` is still exactly right.
* `docs/iso_prolog_compatibility_report.md:449` left untouched — a historical
  changelog line about when the helpers were added, not a claim about what they
  return.

### F2 (Important) — the cross-specialization test's docstring named the wrong mechanism

`tests/test_specialization.py::TestSpecializedPredicateIsARow::test_specialized_calls_specialized_through_the_shared_db`
claimed "the generated body goal resolves through the row". It does not:
`T7Outer`'s compiled code contains no reference to `T7Inner` at all. The
docstring now says what actually happens — the goal survives as a residual
TERM, the catch-all clause hands it to `_SolveGoal_T7Outer`, and
`_make_solve_goal_predicate`'s `module_dict.get(functor)` ->
`pred._get_dispatch()` fallback (specialization.py:1234-1239) is the one route
by which one specialized predicate calls another — and names `_get_dispatch` as
the thing Task 7 moved. Per the ruling, no new mutually-calling fixture was
built; the substitution is recorded as §5 deviation 6. The same fact is now
also recorded at the install site, on `_install_specialized`'s comment over the
`_SolveGoal_` binding.

### F3 (Minor) — the new refusal is pinned, and the doubled prefix was ours

* New fixture `tests/fixtures/specialize_clobber.clausal`, carrying
  `# clausal: no-collect` so pytest's `.clausal` collector leaves it alone (the
  point of the file is that it cannot load). It declares
  `-private([MyAlias(GOALS)])`, defines `MyAlias(GOALS) <- (GOALS is [])`, then
  `-specialize(Solve, NatnumProgram, alias=MyAlias)`. The `-private`
  declaration is load-bearing and documented in the file: a clause head's own
  arg spelling registers the field as `goals`, so without it the load dies
  earlier on a field-name disagreement with `Solve`'s `GOALS` and never reaches
  the gate.
* New test
  `tests/test_specialization_pipeline.py::TestSpecializedPredicateIsARow::test_specializing_onto_a_name_this_module_defines_is_refused`
  asserts a `LogicException` whose term is
  `error(permission_error(modify, static_procedure, MyAlias/1), <context>)`.
* **The doubled prefix was ours.** `refusal_error` leads its message with
  `detail` when `detail` is a str — the channel slot that holds `assertz/1` and
  `retract/1` — and Task 7 passed `detail="specialize"` beside an author of
  `specialize:<path>`, hence `specialize: specialize:/...`. Fixed on our side:
  the channel is now `detail="-specialize"`, naming the DIRECTIVE, which is
  what that slot is for. The message now reads `-specialize: specialize:<path>
  may not write MyAlias/1: its 1 clause is owned by <path>`, and the test pins
  the `-specialize: specialize:` prefix so the two facts cannot collapse back
  into one word. `write_refusal` untouched; no source position threaded into
  the refusal, per the ruling.

### F4 (Minor) — `test_no_db_still_row_linked` now pins the stamp and the owner

Added `len(row.writes) == 1`, `writes[0].kind == WRITE_LOAD_CLAUSES`,
`writes[0].author.startswith(SPECIALIZE_AUTHOR_PREFIX)`, `row.source is not
None` and `row.source[1] == writes[0].author` — the no-`db` twin of
`test_write_is_gate_stamped`. The docstring now also states why it passed
before the change (the right mechanism against the wrong database) and why it
is kept.

### F5 (Minor) — namespace writes moved inside the transaction

`globals_[new_name] = pred_cls` and the `_SolveGoal_` install were before the
`db.mutate`, so a refused specialization left the caller's `module_dict`
holding a detached class under a name the module cannot write — the
free-floating shape this task removes, re-created on the failure path. Both
moved inside the `with`; the gate asks the policy on ENTRY, so a refusal now
fires before either write. `_install_specialized`'s docstring gained the step
and the reason. The `module_dict or {}` -> `is not None` fix is recorded as §5
deviation 7.

### F6 (Minor) — `_bind_row` names both authorized callers

`clausal/logic/predicate.py` — the docstring's "which only `compiler_v2` step 4
does" and the body comment's "The one authorized re-bind is ..." both now name
`specialization._install_specialized` as the second, and record that it passes
`through=pred_cls`, so the class's current row is in the gate's blast radius
and the case the guard exists for has already been refused before the bind is
reached.

### F7 (Minor) — sibling-namespace docstring weakened to what it pins

`test_sibling_specializations_are_the_row_linked_classes` no longer implies a
call. It now says explicitly that no clause of `DeepNatnum` calls a sibling,
that the unfolder emits no alias-to-alias reference, and that what is pinned is
the NAMESPACE the specialized predicate was lowered against — the entries it
carries for the module's other specializations are classes bound to this
database's rows, so whichever a later compile or a residual dispatch resolves,
it lands on the row.

### F8 (Minor) — identity, not equality

`tests/test_predicate_meta.py::TestMakeAtom::test_repeated_calls_agree`:
`make_atom("a") == make_atom("a")` -> `is`, with a one-line docstring saying
the claim is identity because the atom IS the str.

### Gate

```
PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest tests -q \
  -p no:cacheprovider --continue-on-collection-errors -rfE
```
foreground, from the worktree. **`144 failed, 12353 passed, 56 skipped,
39 xfailed, 748 warnings, 1 error in 102.31s`** — 145 names.
`task-7-fix1-failed-names.txt` vs `task-3-base-failed-names.txt`: `cmp` ->
**byte-identical**; `comm -3` -> **0 lines**. Passing count is +1 on Task 7's
run: the one new test (F3); F4's additions are assertions inside an existing
test. No F026 flake.

### Concerns opened by this round

1. The clobber refusal's message names the file twice — once as the
   specialization author (`specialize:<path>`) and once as the owner (`owned by
   <path>`). Both are correct and they are different facts (who is writing vs.
   who owns), but a reader of a same-file clobber sees the path twice.
   Threading a source position in was explicitly deferred to final review, so
   nothing was changed here.
2. `tests/fixtures/specialize_clobber.clausal` depends on its `-private`
   declaration to reach the gate at all. If the field-name registration rule
   for clause heads ever changes, the file would start failing for the earlier
   reason — the test asserts the exception TYPE and TERM, so it would fail
   loudly rather than go green on the wrong exception, but the fixture's shape
   is less obvious than it looks, which is why the file explains itself.
