# P3-3 Task 5b report — `(name, arity)`-keyed resolution across `-import_from`

Branch `feat/p33-state-reloc`, BASE `044593b1`.

---

## 1. What changed and why, per file

### `clausal/logic/cells.py`

* **`:177` `DECLARED_ATOMS_KEY = "__clausal_declared_atoms__"`** (+ the block comment
  above it). A new module-namespace registry, sibling of `FUNCTOR_SIGNATURES_KEY`,
  recording every spelling a file declared as a **bare 0-arity atom** in its
  `-module`/`-private` list.

  Why it has to exist: post-pivot the binding normally *is* the declaration
  (a declared atom binds its interned spelling), but not when the same file also
  writes 0-arity clauses for the name — the clause block mints a real
  `PredicateMeta` and `_process_declarations`' don't-clobber guard keeps it, so
  the binding then says "predicate" and the atom-ness is unrecoverable from the
  namespace. The owner's own lowering still knows (its `-module` list is in front
  of it); the importer did not, and that asymmetry is sub-shape 2.

### `clausal/logic/compiler_v2.py`

* **`:29`** import of `DECLARED_ATOMS_KEY`.
* **`:1584–1596` (in `_process_declarations`)** — record the bare entries of every
  `ModuleDeclItem`/`PrivateDeclItem` into `module_dict[DECLARED_ATOMS_KEY]`, before
  the binding loop decides what each name binds to.
* **`:463–501` `_imported_reference(mod, orig_name, value)`** (new) and its two call
  sites in **`_process_imports` (`:517`, `:524`)** — the **dotted key** an
  `-import_from` writes (`"<module>.<OrigName>"`, the key the import remap emits for
  every *reference* to the imported spelling) now holds the interned atom **str**
  when, and only when, the owner declared `orig_name` as an atom AND the imported
  value is a **zero-field** `PredicateMeta`. The bare local binding
  (`module_dict[local_name]`) and the owner's own module attribute are untouched.
  This is **sub-shape 2**.
  * The declaration is the authority, not the presence of /0 clauses (controller
    ruling): a /0 predicate the owner never declared as an atom stays the class,
    and a DUAL declaration (`-module(m, [dual, dual(G)])`) carries fields on its
    class, so it stays the class too.
* **`:1112–1140` `_local_functor_arities`** (new) — `{name: {arity,…}}` for every
  functor signature this file fixes, read from the **clause nodes** plus the
  `-module`/`-private` functor entries plus the ISO `name/arity` export spelling.
  Read from the nodes, not from `module_dict`, because an `-import_from` of the
  same spelling overwrites the module binding.
* **`:1142–1200` `_local_call_reroutes`** (new) — `{(dotted key, arity): local name}`
  for the call sites that mean LOCAL, implementing the three ruling conditions:
  (a) the name is one an `-import_from` remapped (same `ImportFromItem`s
  `_import_remap` was built from, rebuilding the identical dotted key);
  (b) this file establishes `(name, N)` itself;
  (c) the **imported binding carries no functor signature** — the OWNER's fact,
  asked of the owner's namespace with the same `functor_signature_for`
  `_check_atoms_applied_as_functors` uses.
* **`:1202–1250` `_route_imported_atom_calls_to_local`** (new) — walks the clause
  **bodies** and re-points a qualifying `Call`'s `func` from `LoadName(dotted)` to
  `LoadName(local)`. This is **sub-shape 1**.
* **`:171–180` (in `compile_module`)** — new **Step 3b-ter**, immediately after
  Step 3b-bis and before Step 3c/4. Same phase and same reason as 3b-bis:
  "is the imported name a functor?" is the owner's fact and is first answerable
  after the module body has run.

  Why a rewrite and not a binding change: the applied form and the bare form of
  the same spelling can both occur in one file (they do, in
  `tests/fixtures/t5b_local_pred.clausal`), and `base_globals` is keyed by NAME.
  Re-pointing the call site is what gives the two positions **different globals
  keys**; no binding-level fix can serve both.

### `clausal/logic/compiler/globals_env.py`

* **`:534–556` `_atom_shadows_row(binding, db, name, arity)`** (new) and its use at
  **`:691` (in `_inject_resolved_targets`)** — a `str` module binding is an ATOM
  (data, never callable) and loses to this module's own `db.row(name, arity)` when
  one exists. Needed because `_process_imports` overwrites the importer's local
  `PredicateMeta` binding with the imported atom str, so the rerouted
  `LoadName(local)` would otherwise resolve straight back to the str and die in
  `predicate._dispatch_at` exactly as before. Narrow on both axes: `str` only
  (every other shape is trusted as before) and only when the row really exists
  (`db.row`, not `get_dispatch`, so asking compiles nothing) — a call on an atom
  that names no local predicate keeps its existing positioned diagnostic.
* **`:621` `called_names`** and **`:646–661` (dotted branch of
  `_inject_resolved_targets`)** — for a **DATA** reference (`arity == -1`) this
  module's own dotted-key binding wins over the attribute walk; for a name this
  clause set also **applies**, the attribute walk still wins. `_collect_globals_info`
  yields a dotted name twice for an applied reference (once at its call arity, once
  at `-1` for the `LoadName` inside the `Call`), so the question has to be asked of
  the whole target set — that is what makes the choice deterministic rather than
  set-iteration-order dependent. Keeping the attribute for applied names also
  preserves `PredicateMeta`'s much better "takes 0 arguments, but this call passes 1"
  diagnostic for an imported /0 predicate applied at arity N (pinned by
  `test_predicate_arity_mismatch_diagnostic.py::TestZeroArityFactAtomHead::
  test_calling_an_atom_fact_at_arity_one`, which stays green unchanged).

### Tests

* **`tests/test_import_arity_resolution.py`** (new, 16 tests) with fixtures
  `tests/fixtures/t5b_{atom_vocab,local_pred,functor_vocab,functor_clash,dual_owner,
  dual_importer}.clausal`. All end-to-end: real `_load_module` loads, answers
  asserted, never AST.
  `t5b_functor_clash.clausal` carries the `# clausal: no-collect` marker (it is a
  deliberate load refusal; without the marker conftest's `.clausal` collector adds a
  146th failing name).
* **Three superseded P3-1 pins updated** (all three pinned the *old* behaviour of the
  very shape this task re-decides — the P3-1 Task 2 ruling itself deferred the
  routing to P3-3):
  * `tests/test_functor_import_ordering.py::TestZeroArityAtomThenPredicate::
    test_dotted_owner_path_call_raises_a_clean_existence_error`
    → `…::test_the_applied_form_reaches_the_local_predicate` (+ class docstring).
  * `tests/test_imported_functor_clause_clobber.py::TestOneFileLoadedTwiceUnderTwoNames::
    test_the_atom_vocabulary_shape_survives_both_load_routes` — the "both routes agree"
    property is kept; the answer it agrees on changed from a raised existence_error to
    the local row's two solutions.
  * `tests/test_predicate_arity_mismatch_diagnostic.py::TestTermConstructionUnaffected::
    test_atom_vocabulary_then_predicate_dotted_path_raises_cleanly`
    → `…::test_atom_vocabulary_then_predicate_applied_form_answers`.

---

## 2. Brief checkboxes, and the test that pins each

Pre-fix evidence (same fixtures, before the change): `t5b_go`/`t5b_all` raised
`existence_error(procedure, t5b_slot/2, "atom 't5b_slot' is not callable at arity 2
(resolved via a data reference…)")`; `t5b_iread_fact` → `[]`; `t5b_ikey` with a plain
`str` key → `[]`. The peer scratch repros
(`scratchpad/peerprobe/{sib,main,owner3,importer3}.clausal`) reproduced identically
and now answer `[2]` and `iread_fact -> [1]`.

| Checkbox | Test |
|---|---|
| **Sub-shape 1** — applied form with N>0 args lowers as the LOCAL call when (a) remapped, (b) local `(k,N)` signature, (c) imported binding has no functor signature | `TestImportedAtomWithLocalArityNPredicate::test_the_applied_form_reaches_the_local_row` (call site sits **above** the clauses, so order-independence is pinned too) and `…::test_every_local_clause_answers_through_the_rerouted_site`. Also `test_functor_import_ordering.py::TestZeroArityAtomThenPredicate::test_the_applied_form_reaches_the_local_predicate` on the pre-existing corpus fixture pair. |
| Bare `k` (0 args) in data position stays the imported atom str | `…::test_the_bare_form_in_a_head_stays_the_imported_atom`, `…::test_the_bare_form_in_a_body_stays_the_imported_atom` (both assert `type(value) is str`) |
| A genuinely imported predicate is untouched | `…::test_a_genuinely_imported_predicate_still_reaches_its_owner` |
| **Sub-shape 1 negative pin** — imported FUNCTOR of arity N + local arity-N clauses keeps today's behaviour | `TestImportedFunctorCollisionIsUnchanged::test_the_load_is_refused_with_the_one_defining_module_message`. **Today's behaviour, pinned exactly: the LOAD is refused** with a `SyntaxError` from the mutation gate — "…defines a clause for `t5b_pair/2`, which it `-import_from`'s from …; Clausal has no `-multifile`: a predicate has exactly one defining module … may not write `t5b_pair/2`". Unchanged by this task: condition (c) sees the owner's arity-2 signature and declines to reroute. |
| **Sub-shape 2** — owner-declared atom with /0 clauses lowers as the atom str in DATA position in the importer; all three importer reads answer | `TestImportedDeclaredAtomWithZeroArityClauses::test_the_importer_reads_the_dual_declared_key` (was `[]`), `…::test_the_importer_reads_the_plain_declared_key` (control), `…::test_the_importer_reads_through_the_owners_own_predicate`, plus `…::test_the_key_is_the_plain_str_in_a_body_argument` and `…::test_the_key_is_the_plain_str_in_a_head_argument` (driven with a Python dict keyed by the plain spelling, so only a `str` lowering can find it) |
| Sub-shape 2 GOAL position — `(kfact, 0)` still runs the owner's /0 predicate | `…::test_goal_position_still_runs_the_owners_zero_arity_predicate` (`call(t5b_kfact)`) |
| Precondition pinned | `…::test_the_owner_binds_the_dual_declared_name_to_its_class` |
| Python `getattr` surface unchanged | `TestImportedAtomWithLocalArityNPredicate::test_the_module_attribute_is_unchanged`, `TestImportedDeclaredAtomWithZeroArityClauses::test_the_module_attribute_is_unchanged` — see §3 |
| Corpus shape verified end-to-end with the scratch pairs | done, see the evidence paragraph above; no downstream name appears in any code, fixture, test or message |
| Full suite name-set gate | §5 |

**Bare body goal `kfact` (no parens) — NOT fixed, and not an import-edge bug.**
The task note asked me to fix it if it did not reach the owner's row. It does not
compile *at all*, and it does not for a **local** /0 predicate either: a file
containing `kfact,` and `ogoal <- kfact,` fails at load with
`NotImplementedError: terms_to_goalop: goal shape not yet supported (str): 'kfact'`,
and the imported spelling fails the same way with `(LoadName)`. So bare-atom-as-goal
lowering is a general gap in `terms_to_goalop`, orthogonal to `-import_from` and to
this task; `test_predicate_arity_mismatch_diagnostic.py` already records it ("refused
by the body compiler … so the reachable route is the imported one"). I pinned
`call(kfact)` instead and left the lowering alone. Flagged as a concern.

---

## 3. What `getattr(mod, kfact)` returns from Python after the change

**Unchanged in both sub-shapes** — the Python attribute surface was not touched.

* Sub-shape 2 (`t5b_dual_importer.t5b_kfact`, the owner-declared atom that also has
  /0 clauses): the owner's **`PredicateMeta` class**, and it is the *identical object*
  as `t5b_dual_owner.t5b_kfact` (`assert self.use.t5b_kfact is self.owner.t5b_kfact`).
  Only the module dict's **dotted** key `"tests.fixtures.t5b_dual_owner.t5b_kfact"`
  — an internal compiler key, not reachable as a Python attribute — now holds the
  interned atom `str`. That the class stays bound under the bare name is what keeps
  `call(t5b_kfact)` working: Task 5's `_namespace_dispatch` → `_find_pred_cls` reads
  exactly that binding.
* Sub-shape 1 (`t5b_local_pred.t5b_slot`): still the imported atom `str`
  `'t5b_slot'`, exactly as before (`_process_imports` still overwrites the local
  `PredicateMeta` binding; the local predicate is reachable from Python via the
  module's database, e.g. `call("t5b_slot", K, V, module=lm)`).

---

## 4. Deviations from the brief

1. **`clausal/templating/term_rewriting.py` is not modified.** The brief named it
   first. Both halves turned out to be decidable only *after* the owner has executed
   — condition (c) for sub-shape 1, and "did the owner declare this as an atom" for
   sub-shape 2 — which is precisely why Task 4's O2 machinery defers to
   `compiler_v2`. Rather than add a second deferral channel (a new module item plus a
   new injected runtime helper name, which would also have to be reasoned about
   against `STRICTNESS_EXEMPT_RUNTIME_NAMES`), both decisions are settled in
   `compiler_v2` at the same phase and from the same source of truth
   (`functor_signature_for`) as `_check_atoms_applied_as_functors`. The rewrite emits
   exactly what it emits today.
2. **`clausal/logic/compiler/globals_env.py` was modified** (not on the brief's file
   list). Two small, guarded changes; both are the `(name, arity)` ruling expressed
   at the resolution site, and neither could be avoided: without `_atom_shadows_row`
   the rerouted local call resolves back to the imported atom str, and without the
   dotted-key precedence a sub-shape-2 data reference is re-resolved by the attribute
   walk past the `-import_from` binding.
3. **Condition (c) reads "no functor signature at arity N > 0", not "at any arity".**
   An **empty** signature — a zero-arity predicate class — does not block the
   reroute. The justification is semantic, not a bug it rescues: `k/0` and `k/N` are
   unrelated objects (the same ISO fact the whole ruling rests on), so a /0 meaning
   is not a functor meaning *at arity N* and there is nothing for it to block. Every
   **non-empty** signature blocks, at any arity, exactly as the brief says (an
   imported `k/3` + local `k/2` still routes to the owner and still errors,
   unchanged).

   **Corrected in fix round 1 (review finding F1).** My original rationale here —
   that blocking would "leave the bug alive for a name that is both dual-declared /0
   in the owner and a local /N predicate in the importer" — was **factually wrong**,
   and the reviewer reproduced why: that shape does not load at all, before or after
   this change. The owner owns `k`, so the importer's own `k/2` clauses are refused
   at load by the mutation gate (`_refuse_foreign_writes`, `compiler_v2.py:681` —
   *"cc_use defines a clause for k/2, which it -import_from's from cc_owner … may not
   write k/0"*), identically with these seams patched off. The only route that
   reaches the relaxation is a clause-free `-private([k(A, B)])` in the importer,
   where blocking and not blocking agree. So: **the difference is unobservable
   today.** It is written this way because it is what the ruling means, not because
   any test or corpus shape separates the two. The code is unchanged (controller
   ruling); `_local_call_reroutes`' docstring now says the same thing.
4. **Three existing tests were rewritten** (listed in §1). They pinned the behaviour
   this task's ruling supersedes; the P3-1 Task 2 ruling that wrote them explicitly
   deferred the routing to P3-3. Without this the failing-name gate could not be met
   in either direction.
5. **`_inject_call_targets`** (the dead twin of `_inject_resolved_targets`) was left
   untouched in the first commit. **Deleted in fix round 1** (review finding F3) —
   see the Fix round 1 section.
6. Neutral fixture/predicate names (`t5b_*`) were used rather than the scratch names,
   so no name from the todo's domain A/B/C appears anywhere in the commit.

---

## 5. Suite gate evidence

Command (foreground, from the worktree):

```
PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest tests -q \
  -p no:cacheprovider --continue-on-collection-errors -rfE
```

Result: **145 failed, 12263 passed, 56 skipped, 39 xfailed, 1 error** in 164.65s
(12264 passed on the first of the two runs — the difference is the one flake below,
which was a FAIL in the second run and a PASS in the first).

The raw run produced 146 names; the extra one is the known wall-clock flake
`tests/audit_2026_05_25/test_class_C17_perf_memory.py::
test_F026_multi_star_splits_bounded_for_moderate_input`, re-run alone:
**1 passed**. With it excluded:

```
$ cmp task-3-base-failed-names.txt task-5b-failed-names.txt
BYTE-IDENTICAL          # 145 names incl. the 1 ERROR; comm -3 empty
```

`.superpowers/sdd/p33-state-relocation/task-5b-failed-names.txt` holds the
145-name set; `task-5b-full.txt` holds the raw run (146, flake included).

An earlier run of the same suite produced a 146th *real* name,
`tests/fixtures/t5b_functor_clash.clausal::<load>` — conftest's `.clausal` collector
loads every fixture and this one is a deliberate load refusal. Fixed by the
`# clausal: no-collect` marker (the same marker `impord_arity_clash.clausal` uses).

New/related suites: `tests/test_import_arity_resolution.py`,
`tests/test_functor_import_ordering.py`, `tests/test_imported_functor_clause_clobber.py`,
`tests/test_predicate_arity_mismatch_diagnostic.py` → **120 passed**.

---

## 6. Concerns

1. **Residual hole (deterministic, narrow) — per PREDICATE, not per file.**
   Corrected in fix round 1 (review finding F6): `base_globals` is built once per
   predicate, not once per module (`_collect_globals_info` is called from
   `compiler/predicate.py:891`), so the unit of the hole is the **clause set of one
   predicate**. A predicate that BOTH applies an imported dual-declared /0 atom at
   arity N>0 AND reads it in data position gets the CLASS under the single dotted
   globals key, so *that predicate's* data read still misses silently. The reviewer's
   matrix, all three in one importer file: `mx_read` → `[1]` (fixed by this task),
   `mx_apply` → `PredicateArityMismatchError` (the good diagnostic, preserved),
   `mx_both(V, X) <- (…get…, k(X))` → `[]` (the hole — and `[]` before this task
   too, so nothing regressed).

   The corollary is worth stating plainly: **the same spelling can now mean different
   things in two predicates of the same file** — the atom `str` in a predicate that
   only reads it, the owner's /0 class in one that also applies it. That is a
   consequence of `base_globals` being per-predicate and of one globals key not being
   able to hold two answers; it is invisible for every program that does not apply
   the atom (an error in itself), but it is a real seam and a reviewer should know it
   is there. Closing it needs the sub-shape-2 fix moved into the AST rewrite as well,
   which needs a walker over *constructed term instances* (clause heads are instances
   by Step 3, holding `LoadName` nodes in their fields) — materially more machinery
   than this task warranted.
2. **Bare atom goals still do not compile at all** (`terms_to_goalop`, §2). Not an
   import-edge bug — a local /0 predicate called bare in its own file fails the same
   way — but it is the shape the brief's "bare `kfact` as a body goal" pin wanted,
   and it remains unpinnable. Worth a todo; it plausibly belongs with Task 6's
   qualified-goal work.
3. **Sub-shape 1 rewrites clause BODIES only.** An applied `k(a, 2)` in a clause HEAD
   argument (a data construction, not a goal) keeps today's lowering. I judged that
   safer than reaching into constructed head instances; it is not a shape the corpus
   report mentions.
4. **`_atom_shadows_row` is a hot-path branch** in `_inject_resolved_targets`. It is
   guarded by `type(binding) is str` before it asks the db anything, so the cost on
   the normal path is one `type()` check per non-dotted call target.
5. **Sub-shape-1 call sites lose the `$disp_` bake.** They resolve through a
   `_DbDispatchAdapter` (no `PredicateMeta` is bound under the local name, because
   `_process_imports` still overwrites it). Correct but not on the fast path; a
   future cleanup could make `_process_imports` decline to clobber a local
   `PredicateMeta` with a non-predicate import, which would restore the bake — I did
   not, because it would change `getattr(mod, name)` and the brief fenced that.

---

## Deferred to final review

* **F4** — `_local_functor_arities` (`compiler_v2.py:1112`) and `_predicate_functor_names`
  (`compiler_v2.py:~1317`) both walk `predicate_nodes` + `module_items` for
  head-functor facts, one arity-keyed and one name-keyed; the two walks could be
  folded into one pass with two views. Deferred by the controller.
* **F5** — the **first** `-import_from` edge to reach a dual-declared atom is what
  interns its spelling into the process-wide `predicate_builtins` pool
  (`_imported_reference`); the owner itself never does, because its declaration lost
  the binding to the /0 clause block. Load order therefore decides *when* the pool
  entry appears (never *what* it is — the value is the spelling either way). Deferred
  by the controller.

---

## Fix round 1

Review verdict: APPROVED (spec, quality, both peer repros verified, rewritten tests
KEPT). Four Minor findings addressed here; F4/F5 deferred and recorded above.
FIX_BASE `8a97cb57`.

### F1 — report only: the §4.3 rationale was factually wrong

`§4` deviation 3 rewritten. My original justification claimed the relaxed condition
(c) rescues a "dual-declared /0 in the owner + local `k/N` in the importer" shape.
The reviewer showed that shape **never loads**, before or after this task: the owner
owns `k`, so `_refuse_foreign_writes` (`compiler_v2.py:681`) refuses the importer's
`k/2` clauses at load, identically with these seams patched off. The only reachable
route is a clause-free `-private([k(A, B)])`, where BASE and HEAD agree. The section
now states the real justification — `k/0` and `k/N` are unrelated objects, so an
empty signature is semantically not a block at arity N — and says plainly that **the
difference is unobservable today**. Code unchanged (controller ruling);
`_local_call_reroutes`' docstring (`compiler_v2.py:1167–1177`) was corrected to match,
since it carried the same wrong claim.

### F2 — code: `_local_call_reroutes` early return

`clausal/logic/compiler_v2.py:1179–1185`. Condition (a) — "is anything imported at
all?" — is now asked **first**, before `_local_functor_arities` builds anything. Every
module without an `-import_from` (the overwhelming majority) previously walked all its
clause heads and module items to build a table that nothing would read. It is the
cheapest of the three conditions and it gates the other two, so asking it first is
both faster and the natural order. Nothing new pinned — the behaviour is identical by
construction (the old code returned `{}` for exactly this input). Green: the four
Task 5b / rewritten test files plus `tests/test_module_imports.py` and
`tests/test_compiler_optimizations.py` → **208 passed**.

### F3 — code: `_inject_call_targets` DELETED

**My call: delete, not annotate.** Reasons: it had no production call sites (the only
reference was an unused import); Task 5b turned it from a redundant copy into a
**diverged** one (the live loop grew the dotted-key data precedence and
`_atom_shadows_row`, this one did not), so a reader consulting it would have been
misled about what the compiler does; and the two tests that exercised it were
therefore asserting nothing about the shipped path. Annotating it would have left a
second, wrong account of the resolution rule in the tree — the exact hazard the P3-3
program keeps closing elsewhere.

* `clausal/logic/compiler/globals_env.py:456–467` — the function is gone, replaced by
  a block comment recording that it existed, that it was dead, that it had diverged,
  and that `_collect_call_targets` (immediately above it) **stays**, because
  `tests/test_compiler_optimizations.py` uses it as the parity oracle for
  `_collect_globals_info`'s combined walk.
* `clausal/logic/compiler/predicate.py:86` — unused import dropped.
* `clausal/logic/compiler/globals_env.py:502–504`, `clausal/logic/compiler_v2.py:515`
  and `:527`, `clausal/templating/term_rewriting.py:5719` and `:5872` — four prose
  references retargeted onto `_inject_resolved_targets` so nothing in the tree points
  at a deleted symbol.
* `tests/test_module_imports.py:188–231` `test_inject_dotted_call_target` — **kept and
  retargeted** onto the live pair (`_collect_globals_info` to gather the targets, then
  `_inject_resolved_targets` to resolve them — the same two calls
  `compiler/predicate.py` makes). It still asserts something meaningful, and now
  asserts it about the shipped path; the docstring records the change.
* `tests/test_module_imports.py:233` `test_dotted_name_dispatch` — kept; its
  `_inject_call_targets` import was **dead** (never called in the body), so only the
  import was removed. The test asserts `_get_dispatch` reachability through a dotted
  globals key and is unaffected.

### F6 — report only: the residual hole is per-PREDICATE

`§6` concern 1 rewritten. `base_globals` is built once per predicate
(`compiler/predicate.py:891`), not once per module, so the unit of the hole is one
predicate's clause set, not the file. The reviewer's three-way matrix is recorded
verbatim (`mx_read` → `[1]` fixed, `mx_apply` → `PredicateArityMismatchError`
preserved, `mx_both` → `[]` the hole, and `[]` before this task too — nothing
regressed), together with the corollary the old wording hid: **the same spelling can
now mean different things in two predicates of one file**.

### Suite

```
PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest tests -q \
  -p no:cacheprovider --continue-on-collection-errors -rfE
```

**144 failed, 12264 passed, 56 skipped, 39 xfailed, 1 error** in 100.85s → 145 names.

```
$ cmp task-3-base-failed-names.txt task-5b-fix1-failed-names.txt
BYTE-IDENTICAL          # comm -3 → 0 lines
```

The F026 wall-clock flake did not appear in this run, so no solo re-run was needed.
Artifacts: `task-5b-fix1-failed-names.txt`, `task-5b-fix1-full.txt`.
