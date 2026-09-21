# P3-3 Task 4 report — bake-in from rows + the backend seam

**Commit:** `906c11f6` — *P3-3 Task 4: bake-in from the row, and the stencil-v2
backend seam* (branch `feat/p33-state-reloc`, on top of `dd0a8ad2`).
One commit: the seam, the bake-in and the fold-ins all turn on the same two
files and the same suite gate, so splitting them would have made the gate
evidence harder to read, not easier.

---

## 1. What was implemented, per brief checkbox

### ☑ `_maybe_cache_dispatch` reads the row

`clausal/logic/compiler/globals_env.py:553-590` (the nested closure inside
`_inject_resolved_targets`).

The two questions that decide a bake are now asked of the `PredRow`:

```python
        row = obj._row
        if row is None or not row.locked:
            return
        dispatch = row.dispatch_fn
        if dispatch is not None:
            base_globals[_disp_key(name, arity)] = dispatch
```

The arity guard is unchanged and keeps its original rationale comment verbatim
(cited in the new docstring paragraph and re-pinned by
`TestBakeInReadsTheRow::test_an_arity_mismatch_is_not_baked`).
`_inject_resolved_targets`'s own docstring line was updated from "is a locked
`PredicateMeta`" to "whose `PredRow` is locked".

**Deviation from the brief's literal wording, deliberate, flagged for the
controller.** The brief says `row = db.row(name, arity)`. I used the CLASS's
own row (`obj._row`) instead, and documented why in the docstring. The reason
is a correctness one, not a style one: `db` here is the COMPILING module's
Database, while `obj` may be a cross-module import whose row lives on the
OWNER's Database. `db.row(name, arity)` would then either

* return `None` (imported predicate not present in the compiling db) — every
  cross-module bake silently disappears, a pure perf cliff; or worse
* return a **different predicate's** row when the compiling module happens to
  define its own `name/arity` — the `$disp_name_arity` key would then bake the
  LOCAL dispatch under a key whose call site resolves to the IMPORTED class,
  silently redirecting the call. That is a wrong-answer shape.

`obj._row` is the same object as `db.row(name, arity)` in the local case (which
is what the P3-2 class properties already forwarded to), and is the right one
in the cross-module case. If the controller wants the literal `db.row(...)`
spelling, say so and I will change it — but I believe the brief's wording
predates the cross-module consideration rather than ruling on it.

**Staleness invariant** — its own tests, unit and end-to-end:

* `tests/test_backend_seam.py::TestBakeInReadsTheRow::test_an_unlocked_row_is_never_baked`
  — a row with a dispatch installed but `locked=False` produces no `$disp_` key.
* `::test_no_disp_key_exists_for_an_unlocked_row_after_a_real_compile` — loads
  `tests/clausal_modules/family.clausal`, collects every unlocked row (plus one
  forced unlocked after the fact), and asserts no compiled dispatch's globals
  carries a `$disp_` key for any of them.
* `::test_a_baked_call_site_still_answers` — `Ancestor("tom", Who)` still
  enumerates `["ann", "bob", "liz", "pat"]`, i.e. the bake path is exercised
  by behaviour, not only by inspection.

### ☑ `row.backend` + `Database.set_backend_chooser` + `register_backend`

`clausal/logic/database.py`:

| thing | line |
|---|---|
| `DEFAULT_BACKEND = "python"` | 68 |
| `PredRow.backend` (documented, defaulted from `DEFAULT_BACKEND`) | 101-106 |
| `_BACKEND_CHOOSER` / `_BACKEND_INSTALLERS` module state | 440-441 |
| `Database.set_backend_chooser` (the one-page contract docstring) | 497-547 |
| `Database.backend_chooser` | 548-553 |
| `Database.register_backend` | 554-567 |
| `Database.backend_dispatch` | 569-598 |

`clausal/logic/compiler/predicate.py:2079-2088` — the consult, in `_install`,
before the tabling wrap:

```python
    if db is not None:
        fn = db.backend_dispatch(functor, arity, fn)
```

Design decisions, all stated in the docstring:

* **A backend PRODUCES, it does not install.** `installer(row, python_fn)`
  returns the callable to install; everything after — tabling wrap, table
  abolition, the `Database.mutate` transaction, the provenance stamp, the class
  binding — is the same code the Python dispatch goes through. That is what
  keeps "installation in one place" true, and it is why the consult sits before
  the wrap rather than at the `set_dispatch` line.
* **Returning `None` means "not mine".** A real backend cannot compile every
  predicate shape; declining falls back to the Python dispatch and leaves
  `row.backend == "python"`.
* **Process-wide hook, per-row decision.** A row names its own `db`, so a
  chooser wanting per-module policy reads `row.db`. This avoids a speculative
  per-Database installation API with no in-tree consumer.
* **`"python"` is byte-for-byte the install of before.** With no chooser set,
  `backend_dispatch` is one module-global read and `return fn` — it does not
  even look a row up (pinned by
  `TestBackendSeam::test_no_chooser_means_the_seam_does_not_run`, which asserts
  `db._rows == {}`).
* **Nothing registered in tree.** `register_backend("python", …)` raises
  `ValueError`; an unregistered chosen name raises `LookupError` naming both
  the backend and the predicate.

The docstring cites `implementation_plans/stencil-v2-scoping-memo.md` ("What
rewrites" → "The integration seam", the ~1,196-LOC complete-rewrite item) and
states the three-point contract: one invalidation point (`row.invalidate()`),
per-predicate choice (this hook), installation in one place.

Tests: `tests/test_backend_seam.py::TestBackendSeam` — 8 tests covering the
default, the chooser's argument and recorded answer, a registered backend
supplying the dispatch, a declining backend, an unregistered name, the
`"python"` re-registration refusal, and an end-to-end module load with a
`"python"` chooser wired (same clause keys, same answers, every row
`backend == "python"`).

### ☑ `$cells` consolidation

Moved from the two hand-copied `base_globals` literals
(`compiler/predicate.py`, the trampoline strategy at old :869-875 and the
shallow strategy at old :1689-1695) into `INJECTED_RUNTIME_BUILTINS`
(`compiler/predicate.py:315-324`), with the original comment carried over plus
a note on the consequence.

**`STRICTNESS_EXEMPT_RUNTIME_NAMES`: NOT needed — verified, not assumed.**
`INJECTED_RUNTIME_BUILTINS` is folded into `import_hook.runtime_builtins`
(`import_hook.py:310`), and the strictness check distrusts *any*
`runtime_builtins` entry — so an exemption would have been required if the name
were spellable. It is not: `$` is not a legal Python identifier character, so
no `.clausal` module, strict or otherwise, can write `$cells` as a bare atom and
reach the distrust check at all. The probe suites confirm it empirically:
`tests/test_strict_atoms_default.py`, `tests/test_atom_identity_warning.py`,
`tests/test_unknown_builtin.py` and `tests/test_tagged_terms.py` all green
(200 passed) with no exemption added, and the full-suite failure set is
unchanged. Pinned by the new
`tests/test_tagged_terms.py::…::test_the_cells_namespace_is_injected_from_one_place`,
which asserts the single source, the absent exemption, the `$` prefix, and that
the literal appears exactly once in `compiler/predicate.py`.

One consequence, deliberate and noted in the comment: `$cells` now also reaches
every module dict via `runtime_builtins`, so `head_match`'s "emitted only when
that entry is actually present" guard degrades to the wildcard on strictly
fewer paths. That is a strengthening (an exact tuple-DATA tag match where a
wildcard used to stand); the suite gate confirms it flips no test.

### ☑ Fold-in: the `is_term_instance` deep gate

`clausal/logic/compiler/arg_index.py:345-359` — the `is_term_instance` branch of
`_runtime_arg_key` gains the same `deep_gate and not _is_deeply_ground(a)`
condition the cell branch two blocks above carries.

`todo/first-arg-index-partially-ground-instance-keys-into-bucket-2026-09-05.md`
→ `todo/done/` via `git mv`, with a `## Resolution` section (the dest path was
staged explicitly after the append — the rename shows as `R` in the index and
the added content is present).

The repro from the todo IS the test, restored to the two sites the P3-2 revert
stripped it from:

* `tests/test_first_arg_index.py::TestCellIndexKey::test_a_cell_with_an_unbound_slot_is_unindexable`
  — `_runtime_arg_key(Wrap(sub=Var())) is _INDEX_VAR` (verbatim from the todo's
  "The bug" section);
* `::test_a_fully_ground_cell_still_keys_normally` —
  `Wrap(sub="direct") == ("Wrap", 1)` and, additionally,
  `_runtime_arg_key(Wrap(sub=Var()), deep_gate=False) == ("Wrap", 1)`, pinning
  that the gate is opt-out and the O(1) key survives where the compile-time
  flag says no gate is needed.

**4-tuple invariant intact.** No plan-shape code was touched;
`(pos, idx_dict, default_fn, deep_gate)` is unchanged, the flag computation in
`list_dispatch._lifted_head_arg_needs_deep_gate` (which already covered term
instances) is unchanged, and the P3-2 driven-bucket tests are untouched and
green: `tests/test_first_arg_index.py` 79 passed.

---

## 2. TDD evidence

### RED — deep-gate fold-in

```
$ PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest \
    tests/test_first_arg_index.py -q -p no:cacheprovider \
    -k "unbound_slot or fully_ground_cell"
        assert _runtime_arg_key(("Wrap", v)) is _INDEX_VAR
        assert _runtime_arg_key(("Item", "r", ("Met", v), "d")) is _INDEX_VAR
>       assert _runtime_arg_key(Wrap(sub=Var())) is _INDEX_VAR
E       AssertionError: assert ('Wrap', 1) is <object object at 0xe06fe0021910>
tests/test_first_arg_index.py:277: AssertionError
1 failed, 1 passed, 77 deselected, 2 warnings in 0.27s
```

### GREEN — deep-gate fold-in

```
$ PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest \
    tests/test_first_arg_index.py -q -p no:cacheprovider
79 passed, 2 warnings in 0.70s
```

### RED — the backend seam

```
$ PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest \
    tests/test_backend_seam.py -q -p no:cacheprovider
>       previous = Database.set_backend_chooser(None)
E       AttributeError: type object 'Database' has no attribute 'set_backend_chooser'
tests/test_backend_seam.py:146: AttributeError
...
6 passed, 2 warnings, 8 errors in 0.26s
```

### GREEN — the backend seam

```
$ PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest \
    tests/test_backend_seam.py -q -p no:cacheprovider
14 passed, 2 warnings in 0.33s
```

### RED — atom applied as a functor

```
$ PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest \
    tests/test_atom_diagnostics.py -q -p no:cacheprovider -k "as_a_functor"
E       Failed: DID NOT RAISE SyntaxError
tests/test_atom_diagnostics.py:237: Failed
E       Failed: DID NOT RAISE SyntaxError
tests/test_atom_diagnostics.py:249: Failed
2 failed, 22 deselected, 2 warnings in 0.29s
```

### GREEN — atom applied as a functor

```
$ PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest \
    tests/test_atom_diagnostics.py -q -p no:cacheprovider
24 passed, 2 warnings in 0.30s
```

Plus the live repro from the todo, before → after:

```
before:  call("c", X)  ->  [Trail…, Trail…]   # the bound2 clause silently absent
         db._clauses[("c",1)][1].head == c(X=Call(func='bound2', args=[AttVar(_1)], …))
after:   SyntaxError: …/p2.clausal:5: `bound2` is declared as an atom (a bare name
         in -module, or -private/-hide) but is applied as a functor here.  Declare
         it with arguments in the -module functor list (e.g. `bound2(X)`), or
         reference it bare as the atom it is.
```

### Honest note on the bake-in tests

The six `TestBakeInReadsTheRow` tests **passed before the change as well as
after**. That is expected and is not a TDD gap being papered over: since P3-3
Task 2 `cls._locked` and `cls._dispatch_fn` are properties that forward to the
row, so reading the row explicitly is semantically identical for every case
those tests can construct. They are pinned here because the brief asks for the
staleness invariant to have its own test, and because they are what would catch
a future regression in the direction the seam makes tempting. The RED evidence
for this task is the seam and the two fold-ins.

---

## 3. Cheap-pass verdicts

### `todo/owa-unknown-functor-head-args-never-indexed-2026-09-05.md` — NOT fixed

**Verdict: not cheap. Dated note appended (2026-09-05, "Cheap-pass
assessment"); todo left open and tracked.**

The line count that decided it: the fix is not one condition on an existing
branch but **two new branches that must agree**.

* Lift side — `list_dispatch._lift_clause_at_pos`'s refusal is
  `cell_signature_for_name(lift_term.func.name, globals_) is None`, and
  `terms_to_ast.cell_signature_for_name` returns `None` for an OWA-unknown name
  *by construction* (neither `__clausal_functor_signatures__` nor a resolved
  class names its fields). Allowing the lift means a signature-free pattern
  path through `head_to_match_pattern` built from the call's own positional args
  — a new branch, with keyword args still necessarily refused (no slot layout).
* Key side — `arg_index._arg_to_index_key`'s `Call(LoadName)` branch keys off
  the same resolution. A lift the key side does not match routes callers to a
  bucket holding no clauses: a **wrong-answer** shape, not a missed
  optimization.

Two new branches plus driven answer-level tests alongside
`tests/test_implicit_functors.py` (the failure mode is silent under-matching, so
unit-level pattern assertions would not be enough) is comfortably past the
~20-line bar, and the sharpness of getting it wrong is the real argument. The
todo's own "safe as-is" reasoning stands.

### `todo/atom-declared-name-applied-as-functor-is-silent-2026-09-05.md` — FIXED

**Verdict: cheap. 20 implementation lines + 2 tests (~28 lines total),
inside the controller's ~30-line bar.**

`clausal/templating/term_rewriting.py:1279-1298`, in
`TermTransformer._visit_call_func` — the ONE place a `Call`'s func position is
visited, which is why the check lives there rather than at each `visit_Call`
branch. A bare `Name` whose identifier is in `transformer.atoms` (a bare name in
`-module`, or a `-private` entry) or `transformer._hidden_atoms` (a `-hide`-en
one) raises a `SyntaxError` naming the atom, its `file:line`, and the remedy.

Tests: `tests/test_atom_diagnostics.py::test_an_atom_applied_as_a_functor_is_refused_at_load`
(head position) and `::test_an_atom_applied_as_a_functor_in_a_body_is_refused_too`
(body position) — both positions from the todo's repro.

Todo `git add`-ed (it was untracked) then `git mv`-ed to `todo/done/` with a
`## Resolution` section.

**Not done, deliberately and recorded in the Resolution:** the todo's proposed
`-implicit_functors` variant (lower to a cell instead of raising). The
transformer carries no `-implicit_functors` state — the directive compiles to a
module-level `__clausal_implicit_functors__` the *compiler* reads — so threading
it in is a larger change than the cheap pass allowed. Raising is strictly
better than the silent behaviour either way, and whoever wants that lowering now
gets a loud error pointing at the exact site. This is the "do not let this grow"
line the controller drew.

---

## 4. Funnel-lint re-pins

`tests/test_funnel_lint.py` reds on a stale range after the database.py edits:

```
clausal/logic/database.py:1238: disallowed atom_bypass pattern:
    'isinstance(head, PredicateMeta) and not head._fields'
```

`head_key` moved **1088-1120 → 1214-1246** (+126 lines), all of it the backend
seam added *earlier in the same file* (`DEFAULT_BACKEND`, `_BACKEND_CHOOSER` /
`_BACKEND_INSTALLERS`, and the four `Database` methods). `head_key` itself is
byte-identical — only its line number moved, the seventh such mechanical shift
on this entry. Re-pinned with a comment recording the shift and its cause, in
the same style as the six before it. `tests/test_funnel_lint.py`: 9 passed.

No compiler_v2.py range needed re-pinning (that file is untouched).

---

## 5. Spot A/B

Full transcript: `.superpowers/sdd/p33-state-relocation/task4-bench.txt`.
Method per Task 2: byte-copy base tree with the five touched files reverted to
`dd0a8ad2`, same `.so` artifacts; every bench process asserts
`clausal.__file__` is under the tree it was told to measure BEFORE importing
`benchmarks.workloads`, and echoes the resolved path on every raw line;
interleaved with ALTERNATING within-pair order; one fresh process per sample.

`bench_struct_tabling(1500, 3)`, 10 pairs, twice:

| run | base median | head median | delta median | delta min |
|---|---|---|---|---|
| A | 2.1637 s | 2.1301 s | **-1.55%** | +2.78% |
| B | 2.0774 s | 2.1054 s | **+1.35%** | +0.50% |

Two runs of the identical driver on identical code swing 2.9 points, i.e. the
instrument's noise band. **Both are inside the >3%-fails bar, in both
directions.**

Decisive corroboration by counting work rather than timing it (cProfile call
counts, which do not drift with the machine):

```
base   252564 function calls   (primitive 245129)
head   252553 function calls   (primitive 245118)
            -11                         -11
```

-11 calls out of 252,564 (-0.004%), in the *faster* direction — the `$cells`
consolidation removes one dict store per compiled predicate. This matches what
the change does: the bake-in read and the seam consult are compile-time only
(the seam is one global read and an early return when no chooser is set), and
the `_runtime_arg_key` deep gate is on the dispatch path but is not reached by
this workload at all (`struct_tabling` indexes cells, not term instances).

**Verdict: no measurable regression.**

---

## 6. Full suite

```
$ PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest tests -q \
    -p no:cacheprovider --continue-on-collection-errors \
    2>&1 | tee .superpowers/sdd/p33-state-relocation/task-4-full.txt
...
FAILED tests/test_doc_snippet_coverage.py::test_no_raw_untested_blocks - Asse...
ERROR tests/test_clportools.py - NameError: name '_CpSolverSolutionCallback' ...
144 failed, 12175 passed, 56 skipped, 39 xfailed, 748 warnings, 1 error in 95.81s (0:01:35)
```

```
$ grep -E '^(FAILED|ERROR) ' …/task-4-full.txt \
    | sed -E 's/^(FAILED|ERROR) //; s/ - .*//' | sort -u \
    > …/task-4-failed-names.txt
$ wc -l …/task-4-failed-names.txt
145 .superpowers/sdd/p33-state-relocation/task-4-failed-names.txt

$ comm -3 <(sort …/task-3-base-failed-names.txt) …/task-4-failed-names.txt
```

**Literal `comm` output: (empty — no lines).**

145 names, byte-identical to `task-3-base-failed-names.txt`. **No inversions**,
so no ruling citation is needed.

---

## 7. Files changed

| file | what |
|---|---|
| `clausal/logic/database.py` | `DEFAULT_BACKEND`; `PredRow.backend` documented; `_BACKEND_CHOOSER`/`_BACKEND_INSTALLERS`; `Database.set_backend_chooser` (contract docstring), `backend_chooser`, `register_backend`, `backend_dispatch` |
| `clausal/logic/compiler/predicate.py` | `$cells` into `INJECTED_RUNTIME_BUILTINS` (two duplicates removed); seam consult in `_install` + docstring |
| `clausal/logic/compiler/globals_env.py` | `_maybe_cache_dispatch` reads the row; docstrings |
| `clausal/logic/compiler/arg_index.py` | `is_term_instance` deep-gate fold-in |
| `clausal/templating/term_rewriting.py` | atom-applied-as-functor refusal in `_visit_call_func` |
| `tests/test_backend_seam.py` | **new** — 14 tests (bake-in from rows + the seam) |
| `tests/test_first_arg_index.py` | deep-gate fold-in repro restored at two sites; `make_predicate` import |
| `tests/test_tagged_terms.py` | `$cells` single-source + no-exemption pin |
| `tests/test_atom_diagnostics.py` | two atom-as-functor tests |
| `tests/test_funnel_lint.py` | `head_key` range re-pin 1088-1120 → 1214-1246 |
| `todo/done/first-arg-index-partially-ground-instance-keys-into-bucket-2026-09-05.md` | `git mv` + Resolution |
| `todo/done/atom-declared-name-applied-as-functor-is-silent-2026-09-05.md` | tracked, `git mv` + Resolution |
| `todo/owa-unknown-functor-head-args-never-indexed-2026-09-05.md` | dated cheap-pass assessment |

Untouched, as instructed:
`todo/importer-without-dynamic-locks-shared-dynamic-predicate-for-its-owner-2026-09-05.md`
(still untracked). No C sources touched. `<harness-library>` not touched.
`compiler_v2._belongs_elsewhere` left as the ledgered second copy.

---

## 8. Self-review findings

* **`Database.backend_chooser()` was dead on arrival.** Caught in self-review —
  the accessor existed with no reader. Rather than delete the read side of a
  settable hook, I made it live: the chooser test now asserts
  `backend_chooser() is None` before and `is chooser` after. (Amended into the
  commit; the full suite was re-run after the amend and the failure set is
  still identical.)
* **A first cut of `test_no_chooser_means_the_seam_does_not_run` asserted the
  wrong thing** — `db._rows == {}` after `_install`, which fails because
  `db.set_dispatch` mints the row on the Task-3 write path, not the seam.
  Rewritten to call `backend_dispatch` directly, which is what the test is
  actually about.
* **`_install`'s `db` is always a real `Database`, never `_GlobalsDb`** —
  verified rather than assumed (`_effective_db` is a separate local at
  `compiler/predicate.py:783` and `:1610`; all four `_install` call sites pass
  `db`). So `db.backend_dispatch` cannot land on the signature-only proxy.
* **`_get_dispatch` protocol untouched.** No signature or semantic change; the
  seam sits behind `_install`, and `_DbDispatchAdapter` is unmodified.
* The stale sentence in `PredRow`'s docstring ("`locked`, `source` and `writes`
  are new state that nothing else reads or writes **yet this task**") is a
  Task-1 relic that Tasks 2-3 falsified. I removed `backend` from that list
  (it is now genuinely read) but left the rest alone rather than widen the diff.

## 9. Concerns

1. **The `obj._row` vs `db.row(name, arity)` deviation** (§1, first checkbox) is
   the one thing in this task I would most want a controller eye on. I believe
   it is a correctness improvement over the brief's literal wording, and it is
   documented in the code, but it IS a deviation.
2. **`$cells` now reaches every module dict** via `runtime_builtins`, which
   makes `head_match`'s presence-guarded tuple-DATA arm fire on more paths than
   before. The suite gate says nothing flips, and the direction is
   wildcard → exact match (a strengthening), but it is a wider behavioural
   surface than "delete a duplicate" sounds like, and worth a reviewer's eye.
3. **The atom-as-functor refusal is unconditional**, including under
   `-implicit_functors`, where the todo argued for lowering to a cell instead.
   No in-tree module trips it (full suite unchanged), but an out-of-tree
   `-implicit_functors` file that applies a declared atom will now fail to load
   where it previously mis-compiled silently. Loud beats silent, and the
   Resolution note records the deferred alternative.
4. **The backend seam has no in-tree consumer**, by design (the brief forbids
   one). Its shape is therefore justified by the stencil memo rather than by a
   working second backend; the first real backend may want something the
   `installer(row, fn) -> Callable | None` contract does not give it. That is
   the accepted cost of building the seam before the thing that uses it.

---

# Fix round 1

**Commit:** `cf242dd7` — *P3-3 Task 4 fix round 1: a dual-declared name applies
as the functor*. Three review items, nothing else.

## I-1 (Important) — a dual-declared name applies as the FUNCTOR

**Repro confirmed first, on both trees.** Against the fix-round-0 commit
`906c11f6` the reviewer's module is refused:

```
SyntaxError: …/c2.clausal:3: `dual` is declared as an atom (a bare name in
-module, or -private/-hide) but is applied as a functor here.  Declare it with
arguments in the -module functor list (e.g. `dual(X)`), …
```

Against the branch base `dd0a8ad2` the *nested* form is the silent bug this
task exists to close — `c(dual(1)),` answered
`Call(func='dual', args=[1], kwargs=[])`, a leaked compiler node — which is the
evidence that the bare-`str` lowering (not the dual declaration) was the fault.

**Changes.**

* `clausal/templating/term_rewriting.py:1179-1183` — `TermTransformer.__init__`
  gains a `declared_functors` parameter.
* `:1214-1224` — stored as `transformer._declared_functors`: the
  EmbedTransformer's **live** `_seen_functors` dict (functor name → field
  names), deliberately not a copy, so a functor registered later in the file is
  visible the moment it is registered.
* `:4180-4193` — `_make_term_transformer` threads
  `declared_functors=transformer._seen_functors`.
* `:1665-1677` — the nested arrow-lambda `TermTransformer` threads it too, and
  gains the `hidden_atoms` / `module_name` it was already missing.
* `:1279-1319` — `_visit_call_func`: for a name in the atom set, the functor
  reference is emitted directly and the refusal is skipped when the name is
  also declared as a functor —

  * `_import_remap` first, emitting the **dotted** `LoadName` (an imported
    functor is declared as a functor, and dotted is what `visit_Name`'s remap
    branch would produce);
  * then `_declared_functors`, emitting the plain `LoadName`.

  `visit_Name` cannot make this decision itself: its atom test runs *before*
  its import-remap and fallthrough branches, which is exactly why the applied
  form came out as a bare `str`. A `-hide`-en name is excluded from the bypass
  — `_register_functor` refuses a hide/functor collision head-on, so a hidden
  name can never be dual-declared and always refuses.

**The `-import_from` question the review asked.** Yes, it changes the answer,
and it is a second **live** instance of the same silent bug rather than a
hypothetical. Verified by dumping the transformed source on both trees for

```
-module(importer3, [c(X)])
-private([wrap])
-import_from(owner, [wrap])
c(wrap(1)),
```

| tree | emitted func node |
|---|---|
| base `dd0a8ad2` | `Call(func="wrap", …)` — the broken bare `str` |
| fix round 1 | `LoadName(name="owner.wrap", …)` — resolves, answers `('wrap', 1)` |

Pinned by
`tests/test_atom_diagnostics.py::test_an_imported_functor_shadowed_by_a_local_atom_decl_applies_as_the_functor`
(AST level, so the owner module need not exist for the rewrite).

**Tests added** (`tests/test_atom_diagnostics.py`):

* `test_a_name_declared_as_BOTH_atom_and_functor_applies_as_the_functor` —
  the reviewer's module loads and `c(X)` answers `[1]`.
* `test_a_dual_declared_name_nested_in_a_head_arg_builds_the_functor_term` —
  `c(dual(1))` answers the `dual/1` term (`functor_arity == ("dual", 1)`) and
  **not** a `Call` node. Note (corrected in fix round 2 — the round-1 wording
  blamed the dual declaration and was wrong): the term comes back as a class
  instance rather than a cell because this module DEFINES `dual/1`, and
  `_process_declarations` keeps a class for a functor that has clauses while
  binding the interned spelling for one that does not (R6). A dual-declared
  but undefined functor is a cell. The assertion is therefore on functor
  identity, not on representation.
* `test_an_atom_only_name_applied_as_a_functor_still_raises` — the refusal
  still fires for the case the todo filed.
* `test_an_imported_functor_shadowed_by_a_local_atom_decl_applies_as_the_functor`
  — above.

### RED (I-1)

```
$ PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest \
    tests/test_atom_diagnostics.py -q -p no:cacheprovider \
    -k "BOTH or dual or atom_only"
E           SyntaxError: /tmp/tmpuxwgxh0b.clausal:3: `dual` is declared as an atom (a bare name in -module, or -private/-hide) but is applied as a functor here.  Declare it with arguments in the -module functor list (e.g. `dual(X)`), or reference it bare as the atom it is.
E           SyntaxError: /tmp/tmp19qj5gpd.clausal:3: `dual` is declared as an atom (a bare name in -module, or -private/-hide) but is applied as a functor here.  Declare it with arguments in the -module functor list (e.g. `dual(X)`), or reference it bare as the atom it is.
2 failed, 2 passed, 23 deselected, 2 warnings in 0.43s
```

and, for the import half (run with `term_rewriting.py` restored to `906c11f6`):

```
$ PYTHONPATH=$PWD … -m pytest tests/test_atom_diagnostics.py -q \
    -p no:cacheprovider -k "imported_functor"
E           SyntaxError: line 3: `atomfn_wrap` is declared as an atom (a bare name in -module, or -private/-hide) but is applied as a functor here.  Declare it with arguments in the -module functor list (e.g. `atomfn_wrap(X)`), or reference it bare as the atom it is.
1 failed, 27 deselected, 2 warnings in 0.39s
```

### GREEN (I-1)

```
$ PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest \
    tests/test_atom_diagnostics.py -q -p no:cacheprovider
28 passed, 2 warnings in 0.31s
```

## M-1 — the closure note's scope, stated exactly

`todo/done/atom-declared-name-applied-as-functor-is-silent-2026-09-05.md` gains
a `## Fix round 1 amendment` section. The I-1 fix does **not** make the
cross-module case fire at compile time, so it is recorded as a residual rather
than pinned. Verified on this branch, after the fix:

```
owner:     -module(owner, [verdict, wrap(G)])
importer:  -module(importer, [c(X)])
           -import_from(owner, [verdict])
           c(verdict(1)),

→ module LOADS; first call raises
  File "<template>", line 3, in c__1
  TypeError: 'str' object is not callable
```

The importer's `_atoms` never contains `verdict` (an `-import_from` records the
name in `_import_remap` / `_imported_functors`), so this check cannot see it.
The amendment states it as: **covered** — same-module declarations (`-module`
bare entries, `-private`, `-hide`), head and body position, plus the
dual-declared and import-shadowed lowerings; **not covered** — an atom imported
from another module, loud-but-unlocated (no file, no line, no name of the
offending declaration), which would need the importer to consult the owner's
signature registry at the `-import_from` or call site.

## M-2 — the refusal joins the engine's error family

`clausal/logic/database.py:585-596` — `backend_dispatch`'s unregistered-backend
refusal now raises `LogicException(existence_error("backend", name, context))`
instead of a bare `LookupError`, so it is catchable by `catch/3` like every
other refusal in the file. The `clausal.logic.exceptions` import
(`database.py:19-23`) widened to bring in `existence_error`.

`tests/test_backend_seam.py::TestBackendSeam::test_an_unregistered_backend_name_is_loud`
now pins the **term**, not just the text: `error/2` → `existence_error/2` with
args `("backend", "no-such-backend")`, plus the backend name and `p/1` in the
message.

### RED (M-2)

```
$ PYTHONPATH=$PWD … -m pytest tests/test_backend_seam.py -q \
    -p no:cacheprovider -k unregistered
E               LookupError: backend 'no-such-backend' chosen for p/1 is not registered — call Database.register_backend('no-such-backend', installer) first
1 failed, 13 deselected, 2 warnings in 0.19s
```

### GREEN (M-2)

```
$ PYTHONPATH=$PWD … -m pytest tests/test_backend_seam.py -q -p no:cacheprovider
14 passed, 2 warnings in 0.33s
```

## Funnel-lint re-pin (again)

M-2's wider exceptions import and multi-line raise pushed `head_key` down
another 9 lines: **1214-1246 → 1223-1255**. `head_key` is still byte-identical;
the allowlist comment records this eighth shift and its cause.
`tests/test_funnel_lint.py`: 9 passed.

## Full suite

```
$ PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest tests -q \
    -p no:cacheprovider --continue-on-collection-errors \
    2>&1 | tee .superpowers/sdd/p33-state-relocation/task-4-fix1-full.txt
...
FAILED tests/test_doc_snippet_coverage.py::test_no_raw_untested_blocks - Asse...
ERROR tests/test_clportools.py - NameError: name '_CpSolverSolutionCallback' ...
144 failed, 12179 passed, 56 skipped, 39 xfailed, 748 warnings, 1 error in 96.45s (0:01:36)

$ wc -l .superpowers/sdd/p33-state-relocation/task-4-fix1-failed-names.txt
145

$ comm -3 <(sort …/task-3-base-failed-names.txt) …/task-4-fix1-failed-names.txt
```

**Literal `comm` output: (empty — no lines).** 145 names, byte-identical to
`task-3-base-failed-names.txt`. No inversions.

(12,179 passed vs 12,175 in fix round 0 — the four net-new tests.)

## Files changed in fix round 1

| file | what |
|---|---|
| `clausal/templating/term_rewriting.py` | `declared_functors` threaded into `TermTransformer`; `_visit_call_func` emits the functor reference for a dual-declared name |
| `clausal/logic/database.py` | unregistered-backend refusal → `LogicException(existence_error(...))`; `existence_error` imported |
| `tests/test_atom_diagnostics.py` | 4 tests (dual-declared body/head, atom-only still raises, imported-functor shadowing) |
| `tests/test_backend_seam.py` | unregistered-backend test pins the error TERM |
| `tests/test_funnel_lint.py` | `head_key` range 1214-1246 → 1223-1255 |
| `todo/done/atom-declared-name-applied-as-functor-is-silent-2026-09-05.md` | `## Fix round 1 amendment` — exact scope, and the uncovered cross-module residual |

`todo/importer-without-dynamic-locks-shared-dynamic-predicate-for-its-owner-2026-09-05.md`
left untracked. No re-run of the A/B: the changed code is compile-time only
(the `_visit_call_func` branch) and an error path never taken in the shipped
configuration.

## Concerns after fix round 1

1. The M-1 residual (imported atom applied as a functor) is loud but
   unlocated. Recorded, not fixed — closing it means reading the owner's
   signature registry from the importer, which is a scope of its own.
2. ~~The dual-declared term is a class instance because the atom-str rebinding
   is guarded on the minted class.~~ **Withdrawn in fix round 2:** the
   re-review showed the class-instance representation comes from the module
   DEFINING the predicate (R6 — a functor with clauses keeps its class, one
   without binds its interned spelling), not from the dual declaration; a
   dual-declared but undefined functor is a cell. There is no cells-everywhere
   gap here, and nothing to ledger.

---

# Fix round 2

**Commit:** `34e5d919` — *P3-3 Task 4 fix round 2: the atom-as-functor refusal
decides last*. Three review items, nothing else.

Both Important findings are the same shape — the refusal was being decided at a
moment when the deciding fact was not yet knowable — so they are fixed by one
mechanism (deferral), split across the two moments at which each fact becomes
available. Line cost: the shared mechanism is ~55 lines, of which O1's share is
~22 (`_settle_atom_functor_sites` + the `visit_Module` hook) and O2's ~25 (the
module item + `compiler_v2._check_atoms_applied_as_functors`); both under the
~40-line cap individually.

## O1 (Important) — declaration order no longer decides

**Repro confirmed at `cf242dd7` first.** The reviewer's file is refused:

```
SyntaxError: /tmp/tmpw5jyq81_.clausal:2: `dual` is declared as an atom (a bare
name in -module, or -private/-hide) but is applied as a functor here. …
```

**Change.** `clausal/templating/term_rewriting.py`:

* `:1338-1368` — `_visit_call_func` no longer decides. A `-hide`-en name still
  raises on the spot (it can be neither dual-declared —
  `_register_functor` refuses that collision head-on — nor imported, since the
  mangling is file-local). Any other declared atom in func position emits the
  functor reference (dotted when `_import_remap` knows the name, plain
  otherwise) and appends `(name, lineno, dotted)` to a shared candidate list.
* `:1244-1253` / `:3812-3816` — the list is `TermTransformer._atom_functor_sites`,
  threaded from `EmbedTransformer` the way `_bare_atom_refs` already is, through
  `_make_term_transformer` and the nested arrow-lambda transformer.
* `:4436-4466` — `EmbedTransformer._settle_atom_functor_sites`, called from
  `visit_Module` (`:4424`)
  right after `_check_var_shaped_predicate_names()`. That is the
  first moment `_seen_functors` holds every functor the FILE establishes,
  wherever it was written. A candidate that reached a functor declaration is
  accepted; one that did not, and is not imported, is refused here.
* `:1174-1200` — `_atom_as_functor_message`, one text for all three raise
  sites, built where the call site's file and line are known and carried to
  whichever site ends up raising it.

**Pins** (`tests/test_atom_diagnostics.py`):

* `test_a_functor_established_AFTER_its_first_use_is_not_refused` — the
  reviewer's ordA file loads and `c(X)` answers `[1]`.
* `test_the_other_declaration_order_still_loads` — the mirror order, pinned so
  the fix cannot regress the direction that already worked.
* `test_an_atom_only_name_is_still_refused_wherever_it_appears` — a name
  declared as an atom with no functor clause anywhere is still refused, with
  its own `file:line`.
* The two round-1 dual-declaration pins and the original todo pins stay green.

## O2 (Important, introduced by round 1) — the bypass consults the owner

**Repro confirmed at `cf242dd7` first**: the owner-atom importer loaded and died
at the first call with `File "<template>", line 4 / TypeError: 'str' object is
not callable`.

**Change.** Whether an `-import_from`'d name is a functor is the OWNER's fact,
and the owner has not executed at rewrite time — so the remaining candidates
travel to the pass that runs after the module body:

* `clausal/pythonic_ast/nodes.py:1166-1185` — new module item
  `AtomAppliedAsFunctor(sites=((name, message), …))`. Deliberately **not** added
  to `simple_ast.__all__`: that list is copied wholesale into
  `import_hook.runtime_builtins` and therefore into every module namespace and
  the strict-atoms distrust set, and this item has no business there.
  `term_rewriting` and `compiler_v2` import it by name, which does not need
  `__all__`.
* `clausal/templating/term_rewriting.py:4460-4466` — `visit_Module` emits the
  item for candidates it could not settle.
* `clausal/logic/compiler_v2.py:1030-1056` — `_check_atoms_applied_as_functors`,
  wired in at `:157-168` as step 3b-bis, immediately after
  `_process_bare_atom_refs` and before clause compilation. It asks the one
  existing question: `functor_signature_for(name, module_dict) is None`.
  `-import_from` copies the owner's registry entry across under the local
  spelling **for a functor** and has nothing to copy for an atom, so the
  registry already carries the answer — no second source of truth is
  introduced, which is the constraint the functor-signature registry is under.

The raise lands during `compile_module`, i.e. at load, before any query, and
before an unresolvable reference can become an unlocated runtime `TypeError`.

**Pins.** The round-1 test at `tests/test_atom_diagnostics.py:329-353` is
**replaced**: it asserted on unparsed AST against a module (`other.mod`) that
does not exist, so it structurally could not see what the owner declares. Real
fixtures now, both directions:

| fixture | declares |
|---|---|
| `tests/fixtures/t4f2_owner_functor.clausal` | `wrapf(G)` — a FUNCTOR |
| `tests/fixtures/t4f2_owner_atom.clausal` | `verdict` — an ATOM |
| `tests/fixtures/t4f2_import_functor_shadow.clausal` | `-private([wrapf])` + import + `c(wrapf(1)),` |
| `tests/fixtures/t4f2_import_atom_shadow.clausal` | `-private([verdict])` + import + `c(verdict(1)),` (carries `# clausal: no-collect`, since it is meant to fail at load) |

* `test_an_imported_functor_shadowed_by_a_local_atom_decl_applies_as_the_functor`
  — loads owner + importer for real, `c(X)` answers a `wrapf/1` term.
* `test_an_imported_ATOM_shadowed_by_a_local_atom_decl_is_refused` — refused at
  load, and the message carries the importer's `file:9` **and** names the owner:

```
tests/fixtures/t4f2_import_atom_shadow.clausal:9: `verdict` is declared as an
atom in `tests.fixtures.t4f2_owner_atom` and locally, but is applied as a
functor here.  Nothing declares `verdict` with arguments: declare it as
`verdict(X)` in `tests.fixtures.t4f2_owner_atom`'s -module functor list, or
reference it bare as the atom it is.
```

### RED (O1 + O2)

```
$ PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest \
    tests/test_atom_diagnostics.py -q -p no:cacheprovider
E       Failed: DID NOT RAISE SyntaxError
E           SyntaxError: /tmp/tmp4xt_b0rt.clausal:2: `dual` is declared as an atom (a bare name in -module, or -private/-hide) but is applied as a functor here.  Declare it with arguments in the -module functor list (e.g. `dual(X)`), or reference it bare as the atom it is.
FAILED tests/test_atom_diagnostics.py::test_an_imported_ATOM_shadowed_by_a_local_atom_decl_is_refused
FAILED tests/test_atom_diagnostics.py::test_a_functor_established_AFTER_its_first_use_is_not_refused
2 failed, 32 passed, 2 warnings in 0.53s
```

Exactly the two names above; both fix-round-2 items, one each.  (Corrected in
fix round 3, R2 — the first writing of this block said `3 failed, 30 passed`
and attributed the third to P1.  P1 CANNOT be red at `cf242dd7`: round 1 is
what threaded `hidden_atoms`/`module_name` into the arrow-lambda transformer,
so P1's own RED is against `906c11f6` and is shown under P1 below.  The rerun
above is the reproducible one, with the four fix-round-2 sources swapped to
`cf242dd7` and the round-3 test file in place — which is why it reads 32 passed
rather than the 31 of a round-2-era test file.)

### GREEN (O1 + O2 + P1)

```
$ PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest \
    tests/test_atom_diagnostics.py -q -p no:cacheprovider
33 passed, 2 warnings in 0.35s
```

## P1 (pin only) — the `-hide` leak round 1 fixed by accident

Round 1 threaded `hidden_atoms`/`module_name` into the arrow-lambda
sub-transformer (`term_rewriting.py:1731-1732`) as a consistency tidy-up while
adding `declared_functors`. It was a real fix: without them, a `-hide`-en atom
written inside a lambda body lowered to the PLAIN spelling while the same atom
at clause level lowered to the mangled one, so the two did not unify and the
clause simply failed — silently, with no diagnostic.

Pinned at the answer level, not by an AST dump:

```
-module(t4f2_hide_in_lambda, [same(R)])
-hide([hsecret])
same(R) <- call_goal((V <- ((V == hsecret) and (R == 1))), hsecret)
```

`same(R)` must answer `[1]`.

### RED (P1, with `term_rewriting.py` restored to `906c11f6`)

```
$ PYTHONPATH=$PWD … -m pytest tests/test_atom_diagnostics.py -q \
    -p no:cacheprovider -k "lambda"
>       assert [deref(r) for _ in call(mod.same, r)] == [1]
E       assert [] == [1]
E
E         Right contains one more item: 1
```

### GREEN (P1)

```
1 passed, 32 deselected, 2 warnings in 0.31s
```

Called out as a fixed leak in the commit message.

## Documentation corrections

* `todo/done/atom-declared-name-applied-as-functor-is-silent-2026-09-05.md` —
  the **Covered** bullet now says an import-shadowed name is covered only when
  the imported name is a FUNCTOR in its owner, and that the owner-atom case is
  a located refusal. The round-1 **Not covered** bullet is marked superseded,
  and a `## Fix round 2 amendment` section states both gaps and the message the
  cross-module case now raises.
* `task-4-report.md` (fix-round-1 section, and its concern 2) — the
  "dual-declared keeps its minted class" explanation is **corrected and the
  concern withdrawn**. The class-instance representation comes from the module
  DEFINING the predicate: `_process_declarations` keeps a class for a functor
  that has clauses and binds the interned spelling for one that does not (R6).
  A dual-declared but undefined functor is a cell. There is no
  cells-everywhere gap and nothing to ledger.

## Funnel-lint

No `database.py` edits this round, so the `head_key` allowlist range
(1223-1255) is unchanged. `tests/test_funnel_lint.py`: 9 passed.

## Full suite

```
$ PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest tests -q \
    -p no:cacheprovider --continue-on-collection-errors \
    2>&1 | tee .superpowers/sdd/p33-state-relocation/task-4-fix2-full.txt
...
FAILED tests/test_doc_snippet_coverage.py::test_no_raw_untested_blocks - Asse...
ERROR tests/test_clportools.py - NameError: name '_CpSolverSolutionCallback' ...
144 failed, 12184 passed, 56 skipped, 39 xfailed, 748 warnings, 1 error in 103.42s (0:01:43)

$ wc -l .superpowers/sdd/p33-state-relocation/task-4-fix2-failed-names.txt
145

$ comm -3 <(sort …/task-3-base-failed-names.txt) …/task-4-fix2-failed-names.txt
```

**Literal `comm` output: (empty — no lines).** 145 names, byte-identical to
`task-3-base-failed-names.txt`. No inversions.

(12,184 passed vs 12,179 in fix round 1 — the net-new tests plus the three
collectible new fixtures.)

## Files changed in fix round 2

| file | what |
|---|---|
| `clausal/templating/term_rewriting.py` | `_atom_as_functor_message`; `_visit_call_func` defers instead of deciding; `_atom_functor_sites` threaded; `_settle_atom_functor_sites` called from `visit_Module` |
| `clausal/pythonic_ast/nodes.py` | new `AtomAppliedAsFunctor` module item (not exported in `__all__`, on purpose) |
| `clausal/logic/compiler_v2.py` | `_check_atoms_applied_as_functors`, wired as step 3b-bis |
| `tests/test_atom_diagnostics.py` | 5 new/replaced tests (O1 both orders, atom-only still refused, O2 both directions, P1) |
| `tests/fixtures/t4f2_*.clausal` | 4 new owner/importer fixtures |
| `todo/done/atom-declared-name-applied-as-functor-is-silent-2026-09-05.md` | corrected **Covered** bullet + `## Fix round 2 amendment` |

`todo/importer-without-dynamic-locks-shared-dynamic-predicate-for-its-owner-2026-09-05.md`
left untracked. No A/B re-run: every change is rewrite-time or load-time, none
of it on the dispatch path.

## Concerns after fix round 2

1. The refusal now has THREE raise sites across two files (corrected in fix
   round 3, R2 — the first writing said two, while `_atom_as_functor_message`'s
   own docstring already said three): the `-hide`-en case inline in
   `_visit_call_func` (`term_rewriting.py:1358`), the local case in
   `_settle_atom_functor_sites` (`term_rewriting.py:4457`), and the imported
   case in `_check_atoms_applied_as_functors` (`compiler_v2.py:1056`). That is
   two more moving parts than a single check. The message is built in one place
   and carried, so the TEXT cannot drift; the split follows when each fact
   becomes knowable — the file's own, at the end of the walk, and the owner's,
   after the owner has executed — which is a real boundary rather than an
   arbitrary one.
2. `_check_atoms_applied_as_functors` runs on every module load and iterates
   `module_items` — the same walk `_process_bare_atom_refs` already makes. It
   returns immediately when nothing was deferred (the overwhelmingly common
   case: no candidate at all).
3. A candidate that reaches `compiler_v2` is refused when the name has no
   functor signature, which also catches a name imported from a module that
   failed to register a signature for some unrelated reason. I could not
   construct such a case, but it is the one way this check could be stricter
   than intended.

---

# Fix round 3

**Commit:** `f5ac6b1b` — *P3-3 Task 4 fix round 3: the deferred worklist stays
out of reflection*. Three review items, nothing else. One code change (R1); R2
is a correction to this report, R3 a note on the todo.

## R1 (Important) — `AtomAppliedAsFunctor` leaked into `reify_source` output

`AtomAppliedAsFunctor` is a compile-time WORKLIST. For a file where every
candidate is *accepted* — an importer that shadows an imported FUNCTOR with a
local atom declaration, which loads and answers correctly — nothing ever
consumes the item, so it stays in `module_items` permanently.
`_reify_module_item` (`clausal/reflection.py:~1030-1050`) falls through to a
generic `ModuleDirective` for any item it does not recognise, so the reified
form of that perfectly legal file carried an absolute path and a would-be error
message.

**Change.** `clausal/reflection.py:1012-1019` —
`_SKIPPED_ITEMS = {"BareAtomRefs", "AtomAppliedAsFunctor"}`, with a comment
stating what the set is *for* (compile-time worklists, which carry no source
the author wrote) so the next worklist item is added deliberately rather than
discovered in someone's output.

**Pin.** `tests/test_atom_diagnostics.py::test_the_deferred_item_never_reaches_reflection_output`
does both halves in one test, as the review asked: it reifies
`tests/fixtures/t4f2_import_functor_shadow.clausal` and asserts no
`ModuleDirective` named `AtomAppliedAsFunctor` comes back, then loads the same
fixture for real and asserts `c(X)` answers a `wrapf/1` term. Without the second
half the pin would pass just as well if the item silently stopped being emitted.

### RED

```
$ PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest \
    tests/test_atom_diagnostics.py -q -p no:cacheprovider -k reflection_output
>       assert not leaked, leaked
E       AssertionError: [ModuleDirective(name='AtomAppliedAsFunctor', args=[[['wrapf', "<reflected>:8: `wrapf` is declared as an atom in `test...tests.fixtures.t4f2_owner_functor`'s -module functor list, or reference it bare as the atom it is."]]], position=None)]
1 failed, 33 deselected, 2 warnings in 0.18s
```

### GREEN

```
$ PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest \
    tests/test_atom_diagnostics.py tests/test_reflection.py -q -p no:cacheprovider
73 passed, 4 warnings in 0.53s
```

## R2 — two corrections to this report

Both applied in place, each marked as corrected where it sits.

**The fix-round-2 RED block.** It claimed `3 failed, 30 passed` and attributed
the third failure to P1. P1 cannot be red at `cf242dd7` — fix round 1 is what
threaded `hidden_atoms`/`module_name` into the arrow-lambda sub-transformer, so
the leak was already closed there. The block now shows the reproducible run,
taken by swapping the four fix-round-2 sources
(`term_rewriting.py`, `compiler_v2.py`, `nodes.py`, `reflection.py`) to
`cf242dd7` with the round-3 test file in place:

```
2 failed, 32 passed, 2 warnings in 0.53s
FAILED tests/test_atom_diagnostics.py::test_an_imported_ATOM_shadowed_by_a_local_atom_decl_is_refused
FAILED tests/test_atom_diagnostics.py::test_a_functor_established_AFTER_its_first_use_is_not_refused
```

Exactly the two fix-round-2 items, one each. (The review's expected `31 passed`
was for a round-2-era test file; the R1 test added this round passes at
`cf242dd7` too — the item type does not exist there — hence 32.) P1's own RED
against `906c11f6` is unchanged and still shown under P1.

**Concern 1 of fix round 2.** It said "two raise sites". There are THREE, as
`_atom_as_functor_message`'s own docstring
(`term_rewriting.py:1174-1200`) already said:

| site | file:line | decides |
|---|---|---|
| `_visit_call_func`, inline | `term_rewriting.py:1358` | a `-hide`-en name |
| `_settle_atom_functor_sites` | `term_rewriting.py:4457` | the local case, after the walk |
| `_check_atoms_applied_as_functors` | `compiler_v2.py:1056` | the imported case, after the owner ran |

Corrected in place, with the table's reasoning (each site is where its fact
first becomes knowable).

## R3 — todo note: the IPython entry path

Appended to
`todo/done/atom-declared-name-applied-as-functor-is-silent-2026-09-05.md` as
`## Fix round 3 note`, and cross-referenced from the fix-round-2 amendment's
"Superseded" line so a reader of the Not-covered list cannot miss it.

`clausal/import_hook.py::_FreshEmbedTransformer.visit` (~1047-1051) runs a
fresh `EmbedTransformer` per IPython cell and returns the rewritten tree; it
never reads `_module_items` and never calls `compile_module`, so
`_check_atoms_applied_as_functors` — the pass that settles the IMPORTED half —
does not run interactively. `-private([x])` + `-import_from(m, [x])` + `x(1)`
in a cell still reaches the unlocated runtime `TypeError`. The LOCAL half does
fire there, because `EmbedTransformer.visit_Module` raises during the rewrite
the cell itself performs. No fix: giving the interactive path somewhere to
settle deferred items is a change to that path, not to this check.

## Full suite

```
$ PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest tests -q \
    -p no:cacheprovider --continue-on-collection-errors \
    2>&1 | tee .superpowers/sdd/p33-state-relocation/task-4-fix3-full.txt
...
FAILED tests/test_doc_snippet_coverage.py::test_no_raw_untested_blocks - Asse...
ERROR tests/test_clportools.py - NameError: name '_CpSolverSolutionCallback' ...
144 failed, 12185 passed, 56 skipped, 39 xfailed, 748 warnings, 1 error in 116.36s (0:01:56)

$ wc -l .superpowers/sdd/p33-state-relocation/task-4-fix3-failed-names.txt
145

$ comm -3 <(sort …/task-3-base-failed-names.txt) …/task-4-fix3-failed-names.txt
```

**Literal `comm` output: (empty — no lines).** 145 names, byte-identical to
`task-3-base-failed-names.txt`. No inversions.

## Files changed in fix round 3

| file | what |
|---|---|
| `clausal/reflection.py` | `AtomAppliedAsFunctor` added to `_SKIPPED_ITEMS`, with a comment on what the set is for |
| `tests/test_atom_diagnostics.py` | `test_the_deferred_item_never_reaches_reflection_output` (reify + load in one test) |
| `todo/done/atom-declared-name-applied-as-functor-is-silent-2026-09-05.md` | `## Fix round 3 note` (IPython entry path) + cross-reference from the round-2 amendment |
| `task-4-report.md` | R2's two corrections, in place |

`todo/importer-without-dynamic-locks-shared-dynamic-predicate-for-its-owner-2026-09-05.md`
left untracked. No A/B re-run: the only code change is a set literal read at
reification time.

## Concerns after fix round 3

1. `_SKIPPED_ITEMS` is a denylist, so a future compile-time worklist item leaks
   into reflection output by default and is only noticed when someone reads a
   reified module. The comment added this round says so at the site; an
   allowlist (reify only items with a `_DIRECTIVE_NAMES` entry) would invert
   the default, but that is a change to reflection's contract and outside this
   task.
2. The R1 pin reifies from SOURCE TEXT, so the message it would have caught
   carries `<reflected>:8` rather than an absolute path. The absolute-path
   variant the review saw comes from the file-load path; the item is the same
   object either way, and the assertion is on the item's presence, not its
   text.
