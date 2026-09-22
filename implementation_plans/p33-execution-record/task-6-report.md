# P3-3 Task 6 report — R10: qualified goals + module resolution

Branch `feat/p33-state-reloc`, base `c8020d9d`.

---

## 1. What changed, and why

### `clausal/logic/solve.py`

| where | what |
|---|---|
| module docstring (~:10) | records that `module=` now also takes a dotted-name `str`, and points at `resolve_module` as the shared resolver for that argument *and* for `(":", M, G)`. |
| `import types as _types` (:39) | needed at module scope now that the function-local `import types as _types` inside `_compile_as_query` was removed (it shadowed the new global for no reason). |
| `_term_to_goal` (~:161–232) | the `:`/2 branch no longer calls the Task-5 stub for its side effect; it resolves and **recurses on the inner goal**, so `(":", M, ("p", X))` lowers to exactly the node `("p", X)` lowers to. Docstring records that the *module switch* is not made here — `_term_to_goal` turns a term into a node and has no say in which db the node compiles against — and that `_strip_module_qualification` makes it upstream. |
| `_templatize_query_goal` (~:414–437) | comment only: the `:`/2 arm is no longer "deferred", it is "already stripped before this function is reached on the query path"; the branch stays for direct callers and keeps the F5 arity match with `_term_to_goal`. |
| `_compile_as_query` (~:452–462) | first statement is now `goal, module = _strip_module_qualification(goal, module)`. This is the module switch. |
| `resolve_module` (new, ~:560–607) | the R10 resolver. `str` → `sys.modules[dotted]` → `_coerce_module`; anything else → `_coerce_module` directly. Lookup-only. Refusals become `existence_error(module, repr(designator))`. |
| `_no_such_module` (new, ~:610–630) | the single raise site for that error, so the message is identical whichever arm refused. |
| `_module_for_moduleless_solve` (new, ~:633–670) | `solve(goal)` with no `module=`: a qualified cell names its own module and runs; any other cell raises `existence_error(module, <the cell>)` naming the gap; everything else keeps `_infer_module` + its legacy `TypeError`. |
| `_strip_module_qualification` (new, ~:673–695) | peels a top-level `(":", M, G)` and returns `(G, M's Module)`. |
| `_infer_module` (~:698–712) | docstring note: a cell never reaches here, and why. |
| `solve` (~:840–860) | `module=None` → `_module_for_moduleless_solve(goal)`; otherwise `resolve_module(module, None, "solve/2")` instead of `_coerce_module`. `once`/`query`/`query_wfs` inherit both through `solve`. |
| `_tabled_entry_for_goal` (~:1035–1067) | added the two CELL shapes: the qualified `(":", M, G)` (resolved, `mod` switched to the exporter, then falls through) and the plain cell `("p", A)` (which used to hit the final `else` and read as non-tabled). The legacy `LoadAttr` caller-dict walk is untouched, as R10 requires. |
| `__all__` | `resolve_module` added. |

### `clausal/logic/cells.py`

`resolve_qualified_goal_cell(cell, context, calling_module=None)` (~:365–430) — the
Task-5 stub's **body** replaced, keeping the symbol and the two call shapes.
It now returns `(module, inner_goal)`:

- loops, peeling one `:`/2 layer per turn, so **innermost wins** and **every**
  designator in the chain is resolved (an unresolvable outer module raises even
  when the inner one would have answered). Each layer resolves with the layer
  above it as `calling_module`, so the diagnostic reports who asked.
- normalises a bare-`str` inner goal to the zero-arity cell it names
  (`M:k` → `M:k()`), because a `str` is an atom and an atom in goal position
  names a predicate of the arity its arguments make up.
- any other inner shape is handed back unchanged; deciding what is callable
  stays the caller's job.
- `resolve_module` is imported inside the function — a module-scope import of
  `clausal.logic.solve` would close the cycle the file's other local imports
  already document.

### `clausal/logic/builtins/higher_order.py`

- `_resolve_named_goal` (~:29–100): the `:`/2 arm resolves and then **restarts
  the whole resolution against the exporting db** —
  `return _resolve_named_goal(target.db, inner, (), context)`. One level only:
  the resolver unwraps nesting itself, so `inner` is never another `:`/2.
  Restarting (rather than inlining a lookup) is what makes the control-construct
  refusal, the dispatch-table lookup and the `_namespace_dispatch` fallback all
  apply to the inner goal for free, in the exporter's namespace.
  Fold-then-check is untouched, so the cell and atom spellings still decide on
  one folded goal (Task 5 fix round 1, F4).
- `_calling_module(db)` (new): `db.module_dict["$module"]`, for the diagnostic
  only — there is no back-pointer from `Database` to `Module`.

### Tests

- `tests/test_qualified_goals.py` (new, 55 tests) — see §2.
- `tests/fixtures/t6_lib.clausal`, `t6_exporter.clausal`, `t6_importer.clausal`
  (new) — real cross-module loads. The exporter and importer both define
  `p/1`, `tp/1` (tabled in both) and `home/1` with **different** facts, so
  "which module answered" is readable straight off the answers. The exporter
  additionally `-import_from`s `libp/1` from the lib, which is what forces the
  qualified `call/N` path through `_namespace_dispatch` in the exporting db.
- `tests/test_cell_goals.py` — the four Task-5 pins on the stub UPDATED, not
  deleted (§2, last block).

---

## 2. Brief checkbox → the test that pins it

**`resolve_module` implementing the revised R10 chain**
- `sys.modules[dotted]` → `TestResolveModule::test_a_dotted_str_resolves_through_sys_modules`
- `Module` → `…::test_a_module_resolves_to_itself`
- `__clausal_module__` → `…::test_a_python_module_resolves_through_clausal_module`
- `Module` wrap (the `_coerce_module` last resort) → `…::test_a_plain_python_module_is_wrapped`
- miss in `sys.modules` → `…::test_a_str_that_misses_in_sys_modules_is_an_existence_error`
- designator repr'd, non-str shapes → `…::test_a_non_designator_is_an_existence_error` (parametrized: `7`, `1.5`, `("m",)`, `(":",)`, `b"m"`, `None`), `…::test_an_unbound_var_designator_is_an_existence_error` (which also asserts the Var stays unbound)
- **no import as a side effect** → `…::test_resolution_never_imports`
- `_tabled_entry_for_goal`'s legacy caller-dict walk NOT re-pointed → the walk
  is byte-identical in the diff; the new resolver is added *beside* it
  (`TestQualifiedTabling::test_the_entry_lookup_follows_the_qualification`
  exercises the new path). Convergence follow-up: §7.

**`solve(goal, module=…)`**
- str designator → `TestSolveModuleDesignator::test_a_str_module_argument_resolves`, `…::test_the_str_and_the_module_object_agree`
- Module / py-module still accepted → `…::test_a_python_module_argument_still_works`, and every other test in the file passes a `Module`
- unresolvable str → `…::test_an_unresolvable_str_module_argument_is_an_existence_error`
- module-less cell goal → `existence_error` naming the gap, **not** `_infer_module` → `…::test_an_unqualified_cell_goal_without_a_module_names_the_gap`
- `_infer_module` keeps its legacy customers → `…::test_a_class_term_goal_without_a_module_still_infers`
- the docstring note → `…::test_infer_module_documents_that_cells_never_reach_it`

**`(":", M, G)` in `_term_to_goal` and in `_tabled_entry_for_goal`**
- lowering → `TestTermToGoalQualified::test_the_qualified_cell_lowers_to_the_inner_goals_call_node`, `…::test_the_nested_qualified_cell_lowers_to_the_innermost_goal`, `…::test_colon_slash_3_is_still_an_ordinary_call`
- **module locality (the core pin)** → `TestQualifiedCellGoal::test_module_locality_the_exporter_answers_not_the_caller`, `…::test_the_locality_pin_holds_at_a_second_arity`, `…::test_a_qualified_goal_answers_the_exporters_witness`
- module designator may itself be a `Module`/py-module → `…::test_a_module_designator_may_be_the_module_object_itself`
- qualification alone suffices → `…::test_a_qualified_goal_needs_no_module_argument`
- zero-arity and bare-atom inner goals → `…::test_a_zero_arity_inner_goal_runs`, `…::test_a_bare_atom_inner_goal_is_the_zero_arity_cell`
- unresolvable / non-str M → `…::test_an_unresolvable_module_is_an_existence_error`, `…::test_a_non_str_module_designator_is_an_existence_error`
- control construct under a qualification → `…::test_a_control_construct_under_a_qualification_is_still_refused` (same `type_error(callable_control_construct_unsupported, …)`, routed through `refuse_control_construct_cell`)
- nesting, innermost wins, outer still resolved → `TestNestedQualification` (4 tests)
- the tabling entry → `TestQualifiedTabling::test_the_entry_lookup_follows_the_qualification`, plus `…::test_an_unqualified_cell_goal_also_reaches_the_entry_lookup` for the plain-cell shape the qualified path needed

**call/N over `(":", M, G)`**
- `TestQualifiedCallN::test_call_over_a_qualified_cell_dispatches_in_the_exporting_db`
- both spellings identical → `…::test_the_atom_spelling_agrees_with_the_cell_spelling` (and `test_cell_goals.py::test_the_atom_spelling_of_a_qualified_goal_folds_the_same_way`, `…::test_both_spellings_of_an_unresolvable_qualified_goal_raise_alike`)
- locality through call/N → `…::test_call_over_a_qualified_cell_does_not_see_the_callers_predicate`
- the namespace route in the exporting db → `…::test_a_qualified_goal_resolves_through_the_exporters_namespace`
- bare-atom inner goal → `…::test_a_qualified_goal_with_a_bare_atom_inner_goal_runs`
- unresolvable module raises out of `call` → `…::test_an_unresolvable_module_raises_out_of_call`
- control construct → `…::test_a_control_construct_under_a_qualification_is_refused_by_call`
- §4.2 silent-failure contract preserved → `…::test_a_qualified_goal_naming_nothing_fails_silently`
- `:`/3 is not the qualified form on the call/N path either → `…::test_the_folded_colon_slash_3_form_is_not_the_qualified_one`

**Tests: table lands in the exporter's homes**
- `TestQualifiedTabling::test_the_table_lands_in_the_exporters_store` — both
  stores start empty, and after a qualified tabled goal only the **exporter's**
  `db.table_store` holds `("tp", 1, …)`; the importer's is still `{}` even
  though the importer declares its own tabled `tp/1`.
- `…::test_a_tabled_predicate_answers_through_a_qualified_goal` (21, 22 vs 3, 4)
- `…::test_query_wfs_annotates_a_qualified_tabled_goal` — the entry actually
  reaches the WFS surface.

**Tests: parity with the dotted Call node**
- `TestQualifiedDottedParity::test_the_two_spellings_answer_alike_through_a_fixture_predicate` (through `DottedP/1` in the importer fixture, i.e. the compiled `.clausal` spelling)
- `…::test_the_two_spellings_answer_alike_as_goal_nodes` (the `Call(LoadAttr(…))` node built by hand)

**Task 5 pins updated, not deleted** (`tests/test_cell_goals.py`)
- `test_the_atom_spelling_of_a_qualified_goal_hits_the_same_stub` → renamed
  `…_folds_the_same_way`: both spellings now ANSWER alike. The diagnostic half
  of F4's pin is kept as a new sibling,
  `test_both_spellings_of_an_unresolvable_qualified_goal_raise_alike`, which
  still asserts one shared error term and only the context differing
  (call/3 vs call/1).
- `test_a_qualified_goal_cell_is_refused_by_the_task_6_stub` → split into
  `test_a_qualified_goal_cell_now_resolves_instead_of_being_refused` and
  `test_an_unresolvable_qualified_goal_cell_is_an_existence_error`.
- `test_a_qualified_goal_cell_is_refused_by_call_too` → `…_resolves_through_call_too`.
- `test_only_colon_slash_2_is_the_deferred_qualified_form` → `…_is_the_qualified_form`; the assertions are unchanged (`_term_to_goal((":", "m", ("g",)))` still raises — `'m'` names no module).
- `test_the_stub_is_the_one_task_6_replaces` → `test_the_stub_became_the_resolver`, which now also asserts the new `(module, inner_goal)` return.
- The file's module docstring records the deferral→replacement transition.

---

## 3. The templating / caching decision for qualified cells

**Decision: a qualified cell goal IS templated and IS cached, with the RESOLVED
(exporting) module as the cache key's module component.** Task 5 excluded it
from both; that exclusion is gone on the query path.

The mechanism is the placement of `_strip_module_qualification`: it runs as the
**first** statement of `_compile_as_query`, before `_templatize_query_goal` and
before `_goal_cache_key`. From that line on the goal is an ordinary cell goal
and `module` is the module that answers, so:

- templating: ground arguments under a qualification parameterize like any
  other cell goal's, so `M:p(11)` and `M:p(12)` share one compiled query
  instead of compiling one each — pinned by
  `TestTermToGoalQualified::test_the_qualified_goal_is_templatized_after_the_strip`.
- caching: the key is the ordinary `(structural_key, id(module))` with the
  *resolved* module's id. That is the correct key precisely because the
  compiled artifact depends on the exporter's `db` and `module_dict`, not on
  the caller's. Two consequences fall out and are both pinned by
  `…::test_the_qualified_cell_goal_is_cached_per_resolved_module`: the same
  qualified goal asked from two different callers shares ONE entry (it compiles
  to the same thing), and the same inner goal asked of two different modules
  gets two.

Keying on the caller instead would have been merely wasteful; keying the
*unstripped* goal on the caller would have been wasteful **and** would have let
the `("cell", ":", …)` structural key carry a module designator as a literal —
a second, weaker encoding of the same fact.

`_templatize_query_goal`'s own `:`/2 arm stays (unreached from `solve`, still
correct for a direct caller, and still arity-matched to `_term_to_goal`'s guard
per F5).

---

## 4. Deviations from the brief

1. **The module switch is in `_compile_as_query`, not in `_term_to_goal`.**
   The brief says "`(":", M, G)`: in `_term_to_goal` (replace Task 5's stub)".
   `_term_to_goal` *does* handle `:`/2 (it resolves — which is what raises on a
   bad designator — and lowers the inner goal), but it converts a term to an
   AST node and is given no module, so it structurally cannot choose the
   database. Making it "handle" the qualification in the sense that matters
   would have meant lowering the inner goal against whatever module the caller
   already picked, i.e. silently wrong answers for the module-locality pin. The
   switch therefore sits one frame up, in the only function that holds both the
   goal and the module. Both paths share `resolve_qualified_goal_cell`, so
   there is one strip semantics, not two.

2. **`resolve_module`'s `calling_module` does not participate in resolution.**
   Per the controller's ruling (a `str` that misses in `sys.modules` is an
   `existence_error`, full stop), there is no namespace/alias fallback to run,
   so the parameter names the asking module in the diagnostic and is documented
   as the hook a future alias chain would use. It is threaded from every caller
   that knows it (`_strip_module_qualification`, `_resolve_named_goal` via
   `_calling_module`, each nested layer) so that when such a chain arrives no
   call site has to change.

3. **`resolve_module` delegates to `_coerce_module` and converts its
   `TypeError`, rather than gating on an explicit type allow-list.** The brief
   says build ON `_coerce_module` and don't duplicate its chain; a type gate in
   front of it would have been a second, narrower copy of that chain and would
   have changed what `solve(goal, module=…)` accepts. As written the acceptance
   set of `module=` is exactly what it was, plus `str`; everything
   `_coerce_module` already refused now refuses with the typed
   `existence_error` instead of a `TypeError`. Verified against the controller's
   list: `7`, `1.5`, `("m",)`, `(":",)`, `b"m"`, `None` and an unbound `Var` all
   reach `_coerce_module`'s `TypeError` (a `Var` has neither `__dict__` nor
   `__name__` nor `__clausal_module__`) and so all raise the existence error.

4. **`call((":", M, G), Extra)` still folds to `:`/3 and fails silently.**
   Not changed, deliberately. Task 5 fix round 1 F4 pinned *fold-then-check* so
   that `call((":", M, G))` and `call(":", M, G)` are one goal; detecting the
   qualification *before* the fold would restore the divergence F4 closed
   (the atom spelling has no cell to inspect pre-fold). Treating `:`/3+ as
   "qualified with extras" would instead diverge from `_term_to_goal` and
   `_templatize_query_goal`, whose F5 pin is that only `:`/2 is the qualified
   form. So the SWI reading `call(M:G, X) ≡ M:call(G, X)` is *not* implemented;
   the current behaviour is pinned as-is by
   `TestQualifiedCallN::test_the_folded_colon_slash_3_form_is_not_the_qualified_one`.
   Flagged in §6.

5. **The bare-str `/0` body-goal gap did NOT fall out.** The parked todo
   (`todo/bare-zero-arity-predicate-body-goal-does-not-compile-2026-09-06.md`,
   untouched) is about a `str` in *clause-body* goal position reaching
   `terms_to_goalop`. What Task 6 makes work is `(":", M, "k")` → `("k",)`,
   handled on the cell path in `resolve_qualified_goal_cell` exactly as the
   brief suggested, and pinned by
   `test_a_bare_atom_inner_goal_is_the_zero_arity_cell` /
   `test_a_qualified_goal_with_a_bare_atom_inner_goal_runs`. A top-level
   `solve("ready", m)` still raises `NotImplementedError: terms_to_goalop: goal
   shape not yet supported (str)` — verified directly. The todo stands.

6. **Scope kept off `call()` (the `solve.call` entry point).** It still uses
   `_coerce_module`, so `call("p", X, module="dotted.name")` is not a str
   designator. The brief scoped `resolve_module` to `solve(module=)` and the
   `:`/2 paths; extending it is a one-liner but is a surface change nobody
   asked for.

7. **One incidental cleanup**: the function-local `import types as _types`
   inside `_compile_as_query` was deleted in favour of the new module-scope
   import it would otherwise shadow.

---

## 5. Suite gate evidence

Full suite, foreground, from the worktree:

```
144 failed, 12321 passed, 56 skipped, 39 xfailed, 748 warnings, 1 error in 101.50s
```
→ `.superpowers/sdd/p33-state-relocation/task-6-full.txt`

Name extraction (`^(FAILED|ERROR) `, prefix and ` - …` stripped, `sort -u`)
→ `.superpowers/sdd/p33-state-relocation/task-6-failed-names.txt`

```
145 task-6-failed-names.txt
145 task-3-base-failed-names.txt
comm -3 task-3-base-failed-names.txt task-6-failed-names.txt   →  (empty)
cmp  task-3-base-failed-names.txt task-6-failed-names.txt      →  BYTE_IDENTICAL
```

145 names, 144 FAILED + 1 ERROR (`tests/test_clportools.py`), matching the
Task 3 ledger exactly. The known wall-clock flake
`test_F026_multi_star_splits_bounded_for_moderate_input` did **not** appear, so
no re-run was needed. `clausal.__file__` was asserted to be under the worktree
before any run was trusted.

Targeted re-run after the final comment-only edit:
`tests/test_qualified_goals.py tests/test_cell_goals.py tests/test_module_imports.py
tests/test_wfs.py tests/test_tabling.py` → **305 passed**.

---

## 6. Concerns

1. **`call(M:G, Extra)` is a silent failure** (deviation §4.4). Two pinned
   rulings (F4's fold-then-check, F5's `:`/2-only) jointly force it, and I kept
   both rather than break one unasked. It is the one place a user could
   reasonably expect SWI's `M:call(G, X)` and get nothing. If the ISO-surface
   phase wants that reading, it has to revisit F4 or F5 explicitly.

2. **`_term_to_goal`'s `:`/2 branch is correct only because nothing calls it
   with a qualification and a mismatched module.** It is documented, and today
   `_compile_as_query` (its only production caller) strips first. A future
   caller that lowers a qualified term against a module it chose itself would
   get the inner goal compiled against the wrong db, silently. Making it total
   was the alternative to raising an internal error there; I chose total +
   documented, but a reviewer may prefer a guard.

3. **`_tabled_entry_for_goal` swallows a resolution failure** (`except
   LogicException: return None, None`). Justified because it is asked *after*
   `solve()` has already run the goal — a designator that does not resolve has
   already raised on the way in — but it is a broad `except` in a diagnostic
   path.

4. **`_calling_module` reads `db.module_dict["$module"]`.** That key is an
   import-hook convention, not an API. It feeds the diagnostic only, and
   returns `None` harmlessly when absent, but it is a second consumer of a
   private-ish spelling.

5. **`_tabled_entry_for_goal` now treats every plain tuple goal as a cell.**
   That is the intended widening (a cell goal was invisible to the entry lookup
   before), and the suite is unchanged, but `query_wfs` callers passing a tuple
   that is *not* a goal would now get a table lookup attempt rather than an
   immediate `(None, None)`. It cannot produce a wrong answer — the lookup
   simply misses — but it is a behaviour widening beyond the qualified case.

---

## 7. Convergence follow-up to file at close-out

> **`_tabled_entry_for_goal`'s dotted caller-dict walk should converge on
> `resolve_module`.** `clausal/logic/solve.py::_tabled_entry_for_goal` now
> contains two different answers to "which module's db holds this goal's
> table". The older one, for a dotted `Call(LoadAttr(LoadName(pkg), Pred))`
> goal, walks the *querying* module's `module_dict` for the first segment, then
> `getattr`s segment by segment, with a `sys.modules[".".join(segments)]`
> shortcut in the middle and a `_coerce_module` at the end; the newer one, for
> a qualified cell `(":", M, G)`, calls `resolve_module`, which is
> `sys.modules[dotted]` → `_coerce_module` and nothing else. R10 deliberately
> pinned the legacy walk as-is for Task 6, and P3-3 Task 6 added the resolver
> beside it rather than through it, so the two are known to differ in at least
> three observable ways: the legacy walk resolves a *relative* first segment
> out of the caller's namespace (the resolver does not), it accepts any object
> a `getattr` chain lands on (the resolver accepts what `_coerce_module`
> accepts), and it answers `(None, None)` where the resolver raises
> `existence_error(module, …)`. The convergence task is to decide which of
> those three the dotted surface actually needs, keep exactly those as
> documented parameters of one shared resolver, and delete the second copy —
> with a test that the dotted and cell spellings of the *same* cross-module
> tabled goal locate the *same* `TableEntry`
> (`tests/test_qualified_goals.py::TestQualifiedDottedParity` already asserts
> they answer alike, which is the weaker half of that). Until then the two
> paths can disagree about which module owns a table for goals that are meant
> to be two spellings of one thing.

---

# Fix round 1

FIX_BASE `971c2f41`. One commit, same worktree.

## R-A — `call(M:G, Extra…)` implemented (was concern 1 / deviation §4.4)

**`clausal/logic/builtins/higher_order.py:99–111`** — the qualified arm's guard
went `len(call_args) == 2` → `>= 2`; it now builds the `:`/2 cell from
`call_args[0:2]` explicitly and hands `tuple(call_args[2:])` to the recursion as
the extras to fold onto the **inner** goal. Five lines of body.

`…:63–80` (docstring) records the narrowed rule: the fold puts call/N's extras
after `M` and `G`, so on **this** path a folded `:`/N for any N ≥ 2 is "M:G with
N-2 extras still to place" — `call(M:p, X)` → `M:p(X)`,
`call(M:pair(11), B)` → `M:pair(11, B)` (SWI's `call(M:G, X) ≡ M:call(G, X)`).
F4 (decide on the folded goal) is what makes the arm arity-general; F5 (only
`:`/2) is restated as a statement about the **lowering** paths, where no fold
has run and `(":", A, B, C)` written as a goal really is a `:`/3 call.
`…:82–84`: the `folded` comment no longer claims both routes use it as culprit.

Pins (`tests/test_qualified_goals.py::TestQualifiedCallN`):
- `test_call_over_a_qualified_cell_with_extras_dispatches_in_the_exporting_db`
  — `call(M:p, X)` → `[11, 12]`, `call(M:pair(11), B)` → `[12]`.
- `test_the_atom_spelling_with_extras_agrees` — `call(":", M, G, X)` ==
  `call((":", M, G), X)`; needed a new `CallHost4/4` host in
  `tests/fixtures/t6_importer.clausal`.
- `test_the_extras_form_does_not_see_the_callers_predicate` — locality survives
  the fold.
- `test_an_unresolvable_module_with_extras_still_raises` —
  `existence_error(module, "'t6_nope'")`, context `call/2`.
- **FLIPPED, not deleted**: `test_the_folded_colon_slash_3_form_is_not_the_qualified_one`
  became the first of those four (same call shape, opposite expectation).
- `tests/test_cell_goals.py::test_only_colon_slash_2_is_the_qualified_form` →
  `…_on_the_lowering_paths`; assertions unchanged, docstring gained the SCOPE
  paragraph stating that call/N is not a lowering path and why the two rules
  are consistent rather than exceptions to each other.

Report §4.4 above is superseded by this section.

## F1 + F2 — `query_wfs` resolves its module once

**`clausal/logic/solve.py:679–695`** — new `_resolved_goal_and_module(goal,
module, context)`: the single entry resolution (`_module_for_moduleless_solve`
when `module is None`, else `resolve_module` + `_strip_module_qualification`).
**`…:876`** — `solve` now calls it. **`…:1024`** — `query_wfs` calls it FIRST
and passes the resolved Module and the stripped goal to **both** `solve` and
`_tabled_entry_for_goal`. `…:1009–1013` — the `module` param documented as
taking solve's designators.

Mechanisms confirmed directly before/after: `_coerce_module("dotted.name")`
raises `TypeError` (F1's crash) and `_tabled_entry_for_goal(qualified, None, …)`
returns `(None, None)` (F2's silent `True` default) — both are now unreachable
from `query_wfs` because the module is resolved before either is asked.

Pins (`tests/test_qualified_goals.py::TestQueryWfsModuleResolution`, over a new
`undef` fixture loading `wfs_win.clausal` under the dotted name
`tests.fixtures.t6_wfs_undefined`):
- `test_a_str_designator_does_not_crash_the_entry_lookup` — `module="dotted"`
  == `module=<Module>`, **truth values compared, not just answers**.
- `test_the_str_designator_reports_the_real_truth_values` — two rows, both
  `Undefined`.
- `test_a_qualified_goal_without_a_module_keeps_its_truth_values` —
  `module=None` == `module=<Module>`, both `Undefined` (this is the exact F2
  case: it read `[True, True]`).
- `test_a_qualified_goal_with_a_foreign_caller_keeps_its_truth_values`.
- `test_the_delays_survive_the_resolution_too`.

## F4 — the gap error's culprit is no longer the live goal

**`clausal/logic/solve.py:657–661`** — `existence_error("module", repr(goal))`
instead of the cell itself, with the comment naming the rule it now shares with
`resolve_module`'s culprit (an error term is a ground atom).
Pin: `TestSolveModuleDesignator::test_an_unqualified_cell_goal_without_a_module_names_the_gap`
now asserts the culprit is `repr(goal)`, is a `str`, and that unifying
`("p", Var())` with it leaves the user's `Q` unbound.

## F5 — the peel loop is bounded

**`clausal/logic/cells.py:362–368`** — new `MAX_QUALIFICATION_DEPTH = 64`
(exported). **`…:432–458`** — `while True` → `for … in
range(MAX_QUALIFICATION_DEPTH + 1)` with an `else` arm raising the same
`existence_error(module, repr(cell))`, context saying "nested more than 64
deep, or is cyclic". A bound rather than an occurs check: no bookkeeping, and
the diagnostic is one the callers already handle. `+ 1` so exactly 64 layers
is the deepest chain that WORKS and 65 is the refusal.

Pins (`TestNestedQualification`):
- `test_a_cyclic_qualification_terminates_with_an_error` — `V` unified with
  `(":", E, V)`; verified `deref(V) is` the cell, so it really is cyclic, and
  the assertion is just that it raises (reaching the assert is the pin — the
  unbounded loop hung).
- `test_a_qualification_nested_past_the_cap_is_refused` (cap + 1).
- `test_a_qualification_at_the_cap_still_answers` (cap exactly → `[11, 12]`),
  so the guard is not a new limit on legitimate nesting.

## F6 — `_no_such_module` reprs the deref'd designator

**`clausal/logic/solve.py:617–631`** — `resolve_module` keeps
`culprit = deref(designator)` and passes **that** to both raise sites (it stays
the designator even when the `sys.modules` hit replaces `target`, since a str
that resolved and then failed to coerce is still a fault about the name the
caller wrote). Verified: a `Var` bound to `7` now yields culprit `"7"`, was
`"AttVar(_4=7)"`.
Pin: `TestResolveModule::test_the_culprit_is_the_dereferenced_designator`.

## F7 — the sys.modules pop restores itself

**`tests/test_qualified_goals.py::TestResolveModule::test_resolution_never_imports`**
— `monkeypatch.delitem(sys.modules, name, raising=False)` instead of
`sys.modules.pop`.

## F8 — the moduleless qualified goal resolves once

**Choice: `_module_for_moduleless_solve` returns `(goal, module)`** with the
goal STRIPPED, and the caller passes both on — rather than passing
`calling_module=None` to a second strip. Stripping once is the stronger fix:
the second resolution was not only redundant, it ran with the *exporter* as the
calling module, so any diagnostic out of it named the module that ANSWERS as
the one that ASKED. Passing `None` would have fixed the message and left the
double resolution.

**`clausal/logic/solve.py:633–678`** — signature `-> tuple[Any, Module]`, the
qualified arm returns `_strip_module_qualification(goal, None)`, the other two
arms return `(goal, module)`; docstring states the rule and why.
`_compile_as_query`'s own strip stays (it is then a no-op on this path, and it
keeps that function correct for its direct caller in
`tests/test_unknown_builtin.py`).

## Not addressed

F9 (query-cache key `(structural_key, id(module))` vs a freshly minted Module
per plain-py-module call) — pre-existing, controller files the todo. The
legacy dotted caller-dict walk in `_tabled_entry_for_goal`, the frozen
surfaces and Task 5b's step 3b-ter are untouched.

## Suite gate (fix round 1)

```
144 failed, 12333 passed, 56 skipped, 39 xfailed, 748 warnings, 1 error in 102.08s
```
→ `task-6-fix1-full.txt`; names → `task-6-fix1-failed-names.txt`.

```
145 task-6-fix1-failed-names.txt
145 task-3-base-failed-names.txt
comm -3 task-3-base-failed-names.txt task-6-fix1-failed-names.txt  →  (empty)
cmp  …                                                            →  BYTE_IDENTICAL
```

12333 passed vs 12321 in the first round (+12 new pins, minus none). No F026
flake. `clausal.__file__` asserted under the worktree before any run was
trusted.

## Fix round 1 — scoped re-review verdict

Independent re-review of the fix-round-1 diff (`review-971c2f41..c3e9943a.diff`),
read-only, no full-suite run. Each finding checked against the current source
and re-probed directly (not just the new pins).

### Finding verdicts

- **F3 / R-A** — ADDRESSED. `higher_order.py`'s `:`/N≥2 arm rebuilds the `:`/2
  cell from `call_args[0:2]` and folds `call_args[2:]` onto the inner goal via
  recursion. Confirmed end-to-end from a THIRD module (not exporter, not
  importer) via `call/2`: `call(M:p, X)` → `[11, 12]` dispatched in the
  exporter's db, `call(M:pair(11), B)` → `[12]`, and an unresolvable `M` with
  extras still raises `existence_error(module, …)` with context `call/2`. The
  `>= 2` widening is gated on `functor == QUALIFIED_GOAL_FUNCTOR` so it cannot
  change behaviour for any other functor — the comma/control-construct path is
  untouched. `test_only_colon_slash_2_is_the_qualified_form_on_the_lowering_paths`
  is confirmed to be the renamed/rescoped pin (not deleted): assertions on
  `_term_to_goal`/`_templatize_query_goal` unchanged, docstring narrows the
  claim to the two lowering functions.
- **F1 / F2** — ADDRESSED. `_resolved_goal_and_module` resolves the module
  once in `query_wfs` and hands the same stripped goal + resolved `Module` to
  both `solve` and `_tabled_entry_for_goal`. Manually reproduced F2 on
  `wfs_win.clausal` loaded under a dotted name: `query_wfs((":", M, ("Win",
  X)), {"x": X}, None)` returns `_truth=Undefined` for both answers (was
  silently `True` pre-fix). `_tabled_entry_for_goal`'s own qualified-cell
  branch is now unreachable from `query_wfs` (goal arrives already stripped)
  but its body and the legacy dotted `LoadAttr` walk are untouched — confirmed
  by grep, the diff never touches that function.
- **F4** — ADDRESSED. `_module_for_moduleless_solve`'s gap error now culprits
  `repr(goal)` (a ground `str`), not the live cell; pin verifies unifying a
  fresh pattern with the culprit leaves the caller's `Var` unbound.
- **F5** — ADDRESSED. `MAX_QUALIFICATION_DEPTH = 64`, `for … in range(cap+1)`
  with an `else` raising `existence_error(module, …)` mentioning "cyclic".
  Pinned both edges (64 answers, 65 refuses) and both pins pass.
- **F6** — ADDRESSED. `resolve_module` derefs the designator once into
  `culprit` and uses it at both raise sites. Manually confirmed: `Var` bound
  to `7` → culprit `"7"`, not `"AttVar(...)"`.
- **F7** — ADDRESSED. `test_resolution_never_imports` uses
  `monkeypatch.delitem(sys.modules, name, raising=False)`.
- **F8** — ADDRESSED. `_module_for_moduleless_solve` now returns `(goal,
  module)` with the goal pre-stripped via `_strip_module_qualification(goal,
  None)`; `_compile_as_query`'s own strip becomes a structural no-op on this
  path (the goal is no longer `:`-shaped by the time it gets there), so the
  second resolution is eliminated rather than merely re-parented. Manually
  confirmed the outer-designator-invalid, moduleless case now raises with NO
  asker clause at all (`"asked from …"` does not appear), where the pre-fix
  code's redundant second pass could have named the just-resolved target as
  the asker. `tests/test_unknown_builtin.py`'s direct call to
  `_compile_as_query` is unaffected (it doesn't pass a qualified goal) and
  still passes.

### Untouched surfaces

Confirmed via `grep` over the diff: no hits for `_get_dispatch`,
`_belongs_elsewhere`, `_SKIPPED_ITEMS`, `$disp_`, `<harness-library>`,
`_stored_head_key`, `compiler_v2`, or `3b-ter`. Only 6 files touched
(`higher_order.py`, `cells.py`, `solve.py`, one fixture, two test files) —
matches the diffstat. `_tabled_entry_for_goal`'s legacy dotted walk body is
untouched (mentioned only in comments/docstrings in the diff).

### New breakage in the fix diff

None found.

- `tests/test_qualified_goals.py tests/test_cell_goals.py tests/test_wfs.py
  tests/test_tabling.py tests/test_unknown_builtin.py
  tests/test_module_imports.py tests/test_lambdas.py`: 393 passed, 0 failed.
- `tests/test_prolog_*.py` (all 11 files): 689 passed, 0 failed.
- The `>= 2` widening in `call/N` cannot affect a non-qualified goal: it is
  gated on `functor == QUALIFIED_GOAL_FUNCTOR` (`":"`), so a folded goal with
  any other functor (`,`, `;`, a user predicate name, …) takes the same path
  it always did.
- `_strip_module_qualification` becoming a no-op on the `solve`/`query_wfs`
  entry path does not leave a live path where `_compile_as_query` receives an
  unstripped qualified goal whose module is not the exporter: the only two
  callers of `_compile_as_query` are `solve` (already stripped via
  `_resolved_goal_and_module`) and the direct test in
  `test_unknown_builtin.py` (goal is not qualified there). `_compile_as_query`
  keeps its own strip as a defensive/independent guarantee for any future or
  direct caller, and it is exercised (redundantly but correctly) whenever one
  bypasses `solve`.

### Gate

`wc -l`: `task-3-base-failed-names.txt` = 145, `task-6-fix1-failed-names.txt`
= 145. `comm -3` on sorted copies: empty. Gate holds.

### Verdict

All findings addressed (F3/R-A, F1, F2, F4, F5, F6, F7, F8). No new breakage
found in the fix diff. Untouched surfaces confirmed untouched.
