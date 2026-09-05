# P3-3 Task 5 — cells as goals, the core surfaces (R11)

Branch `feat/p33-state-reloc`, on `f5ac6b1b`.

Brief: `.superpowers/sdd/p33-state-relocation/task-5-brief.md`.

---

## What changed, per brief checkbox

### 1. `head_key` cell branch

`clausal/logic/database.py:1251-1258` — a cell branch placed LAST, immediately
before the `raise TypeError`. It reuses the consolidated shape discipline
through a new narrowing helper rather than re-spelling it (see §"One spelling"
below):

```python
is_cell_head, cell_functor_name = compound_cell_shape(head)
if is_cell_head:
    return cell_functor_name, len(head) - 1
```

Placed last, not first, because every branch above it is a cheaper and far
commoner shape and this one only fires for a `tuple`. A `TUPLE_TAG` cell and a
slot-0-`Var` tuple keep the existing `TypeError` — exactly what
`compound_cell_shape` excludes. Docstring "Handles:" list and the `TypeError`
message updated to name the cell shape (`clausal/logic/database.py:1230`,
`:1261-1262`).

Funnel-lint allowlist range for `head_key` updated from `(1223, 1255)` to
`(1224, 1264)` with the reason recorded (`tests/test_funnel_lint.py:305-315`).
The start moved by one because this task also widened database.py's
`clausal.logic.exceptions` import (`type_error`, for `_stored_head_key`); the
end moved because `head_key` itself grew. This is the first change to
`head_key`'s BODY since the Phase-1 funnel froze it — the seven earlier entries
in that comment were all pure line-count shifts — so the comment now says so
rather than repeating "byte-identical".

**Not in the brief, added on review** —
`clausal/logic/database.py:1267-1296`, `_stored_head_key(head, channel)`, used
by `Database.assertz` (`:788`) and `Database.asserta` (`:801`). `head_key`
accepting a cell opened a hole in the LOW-LEVEL store door: before this task
`db.assertz(Clause(head=("p", 1), body=[]))` raised `TypeError`; after the cell
branch it stored the clause, `compile_predicate_trampoline` compiled it without
complaint, and `p(X)` answered `X` **unbound** — a silent wrong answer, verified
by running it. No lowering path reads a cell as a head (`head_match` and
`list_dispatch._get_head_arg` both want a `Compound` or a class term). So the
low-level door refuses with `type_error(callable, Cell)` naming `assertz/1`,
which is the door that normalizes. Pinned by
`tests/test_cell_goals.py::TestTheLowLevelDoorRefusesACellHead` (4 tests,
including "and it stored nothing"). `clausal/logic/compiler/list_dispatch.py:59-70`'s
"no cell can reach here as a head" comment was re-verified and rewritten to
name the two doors that now make it true.

### 2. `_term_to_goal` cell branch + the qualified form

`clausal/logic/solve.py:209-216`. `("f", a, b)` → `AstCall(LoadName("f"),
[a, b])` — byte-identical to the node a `Compound` goal produces, pinned by
`test_a_cell_goal_lowers_to_the_same_node_a_compound_goal_does`. Two functors
are handled before the general case:

- `(":", M, G)` → `resolve_qualified_goal_cell(term, "solve/1")`;
- a control-construct functor → `refuse_control_construct_cell(...)`.

**The Task 6 stub is `clausal.logic.cells.resolve_qualified_goal_cell(cell,
context)`** (`clausal/logic/cells.py:290-323`). It raises
`LogicException(existence_error("procedure", Compound("/", (":", 2)), msg))`
naming itself in the message, and its docstring says in as many words that Task
6 replaces the BODY and that the two callers (`solve._term_to_goal` and
`higher_order`'s `call/N`) already route through it, so Task 6's integration is
that one body. Pinned three ways:
`test_a_qualified_goal_cell_is_refused_by_the_task_6_stub` (exact error term +
the message naming the function),
`test_a_qualified_goal_cell_is_refused_by_call_too`, and
`test_the_stub_is_the_one_task_6_replaces`.

### 3. R11 in `database_ops`

`_reject_cell_head` → `_check_cell_head_permission(term_val, context, db,
module_dict)` (`clausal/logic/builtins/database_ops.py:76-153`). Non-cells are
returned unchanged; a cell is decided three ways and, when allowed, NORMALIZED
and returned as the term to use as the clause head / retract pattern:

| target | outcome |
|---|---|
| `row.dynamic` for that arity | proceed, normalized |
| a row that is not dynamic, **or** a name declared with N fields in this module | `permission_error(modify, static_procedure, f/N)` |
| neither | `existence_error(procedure, f/N)` |

`_build_clause` gained `db, module_dict` parameters and calls it
(`:72`); the two assert factories pass them (`:288`, `:329`). `retract__1`
calls it directly before `head_key` (`:366-372`).

Three things the brief's one-line spec did not settle, each decided and
recorded:

- **`_declared_with_fields`** (`:157-171`). A data functor — declared with
  fields, given no clauses — has NO Database row at all (being data is
  precisely having none), so the row lookup alone called the P3-2 case
  *unknown* and returned an `existence_error` where that refusal's whole point
  is "this name is data; declare it `-dynamic`". Caught by
  `tests/test_exceptions.py::TestAssertzAgainstADataFunctor` on the first full
  run. The fix reads the module's `__clausal_functor_signatures__` registry
  through `compiler.terms_to_ast.functor_signature_for` — the funnel the
  compiler's own cell placers use, so `-import_from`'d spellings answer too —
  and it is arity-checked (`test_the_declaration_check_is_arity_checked`).
- **Normalization target.** With a class in scope the head is `pred_cls(*args)`;
  with none it is `Compound(functor, args)`. Reasoning below in "Deviations".
- **Canonical functor.** When `_find_pred_cls` finds a class, `functor` is
  reset to `pred_cls.__name__` before the row lookup, because an
  `-import_from` alias binds the exporter's class under the LOCAL spelling
  while the row lives under the exporter's (`_find_pred_cls`'s own docstring
  makes this point). Without it an aliased target would have been called
  unknown.

### 4. `call/N` cells

`clausal/logic/builtins/higher_order.py:30-138`.

**db-threading route chosen: converted `call_goal`/`call` to db-receiving
builtins.** Registered straight into `_DB_BUILTINS` (whose documented contract
is `fn(db) -> trampoline dispatch fn`) rather than through `@_db_builtin`,
because that decorator wraps its product with `_simple_to_trampoline` and
`call_goal` is already trampoline-native. Arity set and dispatch shape are
unchanged; `_get_dispatch` and the 4-tuple dispatch plan were not touched.

**Why this and not the goal-lowering seam.** The brief said to verify via
`_registry` whether call/N can be made db-receiving without changing the
arity/dispatch shape, and it can: `_DB_BUILTINS`'s contract is exactly a
factory over `db`, and `get_builtin_dispatch`/`get_builtin_predicate` already
route db builtins through it. Decisively, this route delivers precisely the db
the requirement asks for — `globals_env` resolves a body's `call/N` target at
COMPILE time via `get_builtin_predicate(name, arity, db)` with the compiling
module's db, so the db reaching the builtin is the CALLING module's by
construction, not by a runtime guess. The goal-lowering seam could not have
done it: the goal is a runtime value, so there is nothing at lowering time to
resolve.

> **CORRECTED, fix round 1 (F2).** The sentence above originally read "the
> resolution is against the CALLING module's namespace by construction". That
> overstated it: what the route delivers is the calling module's **db**, and
> `db.get_dispatch` reads that db's dispatch table plus the builtin registry —
> **not** its module dict. An `-import_from`'d predicate lives on the OWNER's
> row and was therefore missed, so `call` failed silently on a goal `solve`
> answered. Fix round 1 adds the namespace lookup as a second step
> (`_namespace_dispatch`); with it, the claim holds.

`_resolve_named_goal(db, goal_val, extra_args, context)` (`:30-78`) does the
work, reached only after the pre-existing `callable(...) or
hasattr(..., "_get_dispatch")` route declines:

- a CELL contributes `goal_val[1:]`; a bare `str` ATOM contributes nothing;
  anything else returns `None`;
- ISO argument folding: `call(f(A), B)` is the goal `f(A, B)`, so cell args
  come first and call/N's extras follow;
- `db.get_dispatch(functor, len(call_args))`;
- returns `None` — a silent failure — for a non-cell non-atom, for `db is
  None`, and for a name that resolves to nothing.

**§4.2 contract, unchanged and pinned.** Silent-fail for non-cell
non-callables is untouched: `int`, `float`, `list` and a `TUPLE_TAG` data cell
all still fail silently
(`test_a_non_cell_non_callable_goal_still_fails_silently`,
`test_a_tuple_tag_data_cell_goal_fails_silently`), and so does an unknown cell
name (`test_an_unknown_cell_goal_fails_silently`) — a name that resolves to
nothing is the same non-goal it was before. All 11 `tests/test_prolog_*.py`
files were in the focused set and stay green.

**Three db-less seams in `_registry.py`.** Moving out of `_BUILTINS` broke
three paths that read it directly for a dispatch with no db to offer:
`_build_all_builtin_classes` (both the single- and multi-arity sites),
`BuiltinPredicate._get_dispatch`, and `BuiltinPredicate._merge`. All three now
go through one new helper, `_stateless_dispatch(functor, arity)`
(`clausal/logic/builtins/_registry.py:55-79`): `_BUILTINS` first, then a
`_DB_BUILTINS` factory that carries `_db_optional`. `call_goal`'s factory is the
only one that sets that flag, and `factory(None)` is its pre-Task-5 self —
everything it did before (invoking a goal OBJECT) needs no db, only the new name
resolution does. Pinned by
`test_the_db_less_call_dispatch_still_invokes_a_goal_object`, which drives both
halves. Without this, `_BUILTIN_CLASSES["call"]` would have lost its dispatch
and a bare `call_goal` passed to a meta-predicate would have silently failed.

### 5. `_goal_cache_key` / `_templatize_query_goal` / `_structural_key`

- `_structural_key` (`clausal/logic/solve.py:277-284`): a cell branch INSIDE
  the `(list, tuple)` branch (so scalars pay nothing), returning
  `("cell", functor, args)`.
- `_goal_cache_key` (`:302-306`): cells admitted. They were in the "neither a
  predicate term nor a Compound" bucket, i.e. uncached outright.
- `_templatize_query_goal` (`:400-427`): a cell branch parameterizing slots
  1.. exactly as the `Compound` branch does, plus an early return for the two
  DEFERRED functors so the refusal a few lines later quotes the goal the caller
  wrote rather than a template full of fresh `Var`s.

**Cache-key tag choice: `"cell"`, not `"seq"`.** A cell in GOAL position
compiles to a CALL; the equal-shaped tuple in ARGUMENT position is baked as
tuple DATA. Two different compiled artifacts should not share a tag that reads
"a tuple of N+1 elements". I checked for a live collision and there is none —
`_goal_cache_key` admits only goal shapes, and a data tuple is never a
top-level goal — so this is legibility and defence in depth, not a bug fix, and
the docstring says exactly that (`:247-255`). Pinned by
`test_a_cell_goal_keys_under_its_own_tag_not_the_sequence_tag` (which also
pins that a `TUPLE_TAG` cell and a `list` still key as `"seq"`) and
`test_different_cell_functors_do_not_share_a_key`.

### 6. Control constructs in cell-goal position — DEFERRED with a diagnostic

`clausal/logic/cells.py:255-288`: `CELL_GOAL_CONTROL_FUNCTORS = frozenset({",",
";", "->", "\\+"})` — exactly the four the controller named — and
`refuse_control_construct_cell(cell, functor, context)` raising
`LogicException(type_error("callable_control_construct_unsupported", cell,
msg))`. The culprit is the cell itself: a plain tuple, so it round-trips through
unification and `copy_term` and a `catch/3` pattern can match it. The message
names the functor, its arity, and the compile-time node it lowers to
(`,`→`And`, `;`→`Or`, `->`→if-then, `\+`→`Not`), and the docstring records WHY
this is a feature rather than a branch (cut/barrier semantics, delimited
control for `->`, a NAF-database decision for `\+`).

Called from both goal surfaces. In `call/N` the refusal is applied to the goal
as ARGUMENT FOLDING leaves it, so `call(",", A, B)` and `call((",", A, B))`
produce the same message about the same term. Pinned by five tests, including a
parametrize over all four functors and one asserting the message names the
compile-time form.

`*->` (soft cut) is deliberately NOT in the set: the controller named four
functors and I kept to them literally. It is noted here so adding it is a
decision rather than a discovery.

### 7. Tests

`tests/test_cell_goals.py`, 54 tests in 7 classes, all answer-driven. Coverage
maps to the brief's list: cell goals ground and var-carrying (and against a
RULE, not only facts); `call/1..3` over cells including extra args and a bare
atom; assertz/asserta of a cell into a dynamic predicate queryable via cell
goal, class-term goal AND `call`-node goal; the static and unknown error
classes pinned by exact error TERM plus message substrings; the cache-key
sharing instrumented on `len(_query_cache)`, both for two var-carrying goals
and for four distinct GROUND ones (which templatizing collapses to one entry).
Beyond the list: the two deferred forms, the low-level door, retract by cell
(including the cross-representation case against a source-loaded class-term
head, and the no-match case asserting no write happened), and the
`_BUILTINS`→`_DB_BUILTINS` registry move.

`tests/test_lambdas.py` — 5 tests reached into `_BUILTINS[("call_goal", n)]`
directly. Retargeted onto `_registry._stateless_dispatch`, which is the
registry's db-less door and hands back exactly the function `_BUILTINS` used to
hold, with a comment saying why.

---

## One spelling for the shape check

The controller's instruction was to reuse `_reject_cell_head`'s test rather than
re-spell it. That test — `_cell_shape` plus `functor is not TUPLE_TAG and
isinstance(functor, str)` — was about to be needed at five sites across four
modules, so instead of copying it five times I built it ONCE, on `_cell_shape`,
as `cells.compound_cell_shape(x) -> (is_compound_cell, functor)`
(`clausal/logic/cells.py:230-253`). `head_key`, `solve` (three functions),
`higher_order` and `database_ops` all call that; `database_ops`' own copy of the
composite is gone. `cells.py`'s importer NOTE above `__all__` was updated to
record the new narrowing and to say that these five call `compound_cell_shape`,
not `_cell_shape`.

`builtins/_helpers._cell_functor` is the funnel's equivalent and stays separate
— it inlines its slot-0 check by design, per the note already in `cells.py`.
The two are semantically identical (`_valid_functor_slot` spells `type(slot0) is
str`, so "not TUPLE_TAG" and "is str" coincide); a comment in
`compound_cell_shape` records that.

---

## Deviations from the brief

1. **The normalized clause head is the CLASS TERM, not a `Call` node.** The
   brief says "normalize the cell to the Call-node clause shape the existing
   path builds — reuse `_normalize_fact_clause`'s machinery".
   `_normalize_fact_clause` does not build `Call`-node heads: for a `Compound`
   it builds a `Compound` head with a Var+Unify body, and for a class term it
   passes the term through. So "the shape the existing path builds" is one of
   those two, and I pick by what is in scope: `pred_cls(*args)` when a class is
   in scope, `Compound(functor, args)` otherwise, then `_normalize_fact_clause`
   unchanged. Rationale: a cell is a SPELLING of a term, so it must produce the
   clause that term produces spelled any other way — which keeps the clause
   list homogeneous, keeps first-arg indexing seeing the shape it sees for
   every other clause, and (measured, not assumed) is what makes
   `retract(("p", 1))` match a clause LOADED FROM SOURCE. With a `Compound`
   head that retract fails silently: `structural_unify` has no
   `Compound`↔class-instance branch. Pinned by
   `test_the_asserted_clause_has_the_shape_the_source_clauses_have`,
   `test_a_cell_retract_removes_a_clause_loaded_from_source` and
   `test_a_cell_assert_into_a_classless_dynamic_row_uses_a_compound_head`.

2. **The static `permission_error` message is not byte-verbatim.** The term is
   (`permission_error(modify, static_procedure, f/N)`) and so is the substance,
   but two words changed. (a) The old parenthetical "is a data functor
   (declared with fields and given no clauses) ... has no clause list to add
   to" is now conditional: a static procedure that HAS clauses gets "is a
   static procedure" instead, because R11 makes that case reachable (a
   runtime-built `("q", 1)` against a static `q/1`) and the data-functor
   wording would be simply false there. (b) The tail "declare it -dynamic to
   assert against it" became "declare it -dynamic(f/N) to modify it at
   runtime", because the same gate now serves `retract/1`, where "assert
   against it" reads wrong, and naming the arity makes the remedy
   copy-pasteable. Nothing pinned the old text (grepped: zero hits in `tests/`,
   `docs/`, `clausal/`); `tests/test_exceptions.py::TestAssertzAgainstADataFunctor`
   asserts on the TERM plus the substrings `"assertz/1"`, `"-dynamic"`,
   `"data functor"`, all of which survive, and it passes unchanged.

3. **`_stored_head_key` is new work outside the checkbox list.** Justified in
   §1 above: without it the `head_key` checkbox introduces a silent-wrong-answer
   path through `Database.assertz`. Found by asking what the widened `head_key`
   lets through, and verified by running it, not by inspection.

4. **`_registry._stateless_dispatch` is new work outside the file list.** The
   brief named `higher_order.py` for the call/N change; making call/N
   db-receiving is not possible without it (three sites in `_registry.py` read
   `_BUILTINS` for a db-less dispatch). It changes no behaviour for any other
   builtin: `_DB_BUILTINS` factories without `_db_optional` answer `None`
   there, which is what those sites did with a missing `_BUILTINS` key before.

---

## Focused test block (GREEN)

```
$ PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest \
    tests/test_cell_goals.py tests/test_lambdas.py tests/test_prolog_*.py \
    tests/test_cells.py tests/test_database.py tests/test_funnel_lint.py \
    tests/test_funnel_accessors.py tests/test_mutation_gate.py \
    tests/test_predrow.py tests/test_builtin_classes.py \
    tests/test_tagged_terms.py tests/test_tagged_terms_parity.py \
    tests/test_higher_order.py tests/test_solve.py tests/test_exceptions.py \
    tests/test_backend_seam.py tests/test_first_arg_index.py \
    -q -p no:cacheprovider

1457 passed, 2 xfailed, 95 warnings in 10.70s
```

`tests/test_cell_goals.py` alone: `54 passed`.

## Full suite

```
$ PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest tests/ -q \
    -p no:cacheprovider --continue-on-collection-errors

144 failed, 12239 passed, 56 skipped, 39 xfailed, 748 warnings, 1 error in 120.74s
```

145 failing NAMES (144 FAILED + 1 ERROR), written to
`.superpowers/sdd/p33-state-relocation/task-5-failed-names.txt`. Against the
ledger:

```
$ comm -3 .superpowers/sdd/p33-state-relocation/task-3-base-failed-names.txt \
          .superpowers/sdd/p33-state-relocation/task-5-failed-names.txt
=== END (empty above == identical) ===
```

`comm -3` produced no output: the failing-name set is byte-identical to
`task-3-base-failed-names.txt` (145 names). Gate met.

### Reds fixed during the task (both real, both in the first full run)

- `tests/test_exceptions.py::TestAssertzAgainstADataFunctor` ×2 — the
  data-functor case had no Database row and fell into the unknown branch. Fixed
  by `_declared_with_fields`; see §3.
- `tests/test_lambdas.py::TestLambdaRuntime::test_call_goal_*` ×5 — the tests
  index `_BUILTINS` directly; retargeted onto `_stateless_dispatch`. Registry
  bookkeeping, not behaviour: all five drive closures, and all five pass with
  the same assertions.

---

## Self-review notes

- **Every claim in this report that could be checked by running something,
  was.** The silent-wrong-answer through `Database.assertz` (§1), the nested-cell
  gap (below), the class-term `call/N` asymmetry (below) and the
  `Compound`-vs-class-term retract asymmetry (deviation 1) are all things I ran
  before writing them down; two of them changed the design.
- The `_term_to_goal` cell branch is placed AFTER the `Compound` branch and the
  `_structural_key` cell branch INSIDE the `(list, tuple)` branch, so no
  non-tuple term pays for either.
- `_check_cell_head_permission` reads `row.clauses`, which is the
  non-minting getter (Task 2 fix round 1) — reading it cannot flip
  `is_defined()` False→True.
- Normalized terms SHARE the caller's argument objects (no copy, no deref), so
  a retract by cell pattern binds the caller's variables. Pinned by
  `test_a_cell_retract_binds_the_patterns_variables`.
- `retract` gating happens BEFORE `_first_match_index`, so the "search first,
  then open the transaction" property Task 3 fix round 2 established is
  untouched — the gate raises or normalizes, it opens no transaction.
- The frozen `_get_dispatch` protocol and the 4-tuple dispatch plan were not
  touched. `eval_harness*` was not touched. `_belongs_elsewhere`,
  `_SKIPPED_ITEMS` and Task 4's backend seam were not touched.
- Perf: `call/N` resolution moved from a dict lookup to a factory call, but
  only at COMPILE time — `globals_env` resolves the target once into
  `base_globals` and `BuiltinPredicate._get_dispatch` memoises. Per-solution
  cost is unchanged: one extra `if dispatch is not None` in the trampoline
  body, and `_resolve_named_goal` is not reached at all by a goal-object call.

## Concerns

1. **A cell goal nested inside `And`/`Or`/`Not`, or written in a CLAUSE BODY,
   is still not lowered.** `_term_to_goal` only ever sees the TOP-LEVEL goal;
   the general fix belongs in `terms_to_goalop._convert_inner`, which is a
   compiler change with its own gate and was not in this brief. Verified:
   `solve(And(("p", X), ("p", X)), mod)` still raises `NotImplementedError:
   terms_to_goalop: goal shape not yet supported (tuple)`. Parked with the fix
   sketched in
   `todo/a-cell-goal-nested-in-a-control-node-is-not-lowered-2026-09-06.md`.
2. **`call/N` resolves a cell and an atom by name but NOT a runtime-built class
   TERM**, which is what `p(X)` evaluates to when `p/1` has clauses. So the two
   spellings of one goal differ, and the one that works is the one whose
   predicate cannot succeed. Pre-existing (both failed silently before), made
   visible by this task. Pinned as-is and parked in
   `todo/call-n-does-not-resolve-a-runtime-built-class-term-goal-2026-09-06.md`
   with the branch and the blast-radius sweep it needs.
3. **`*->` is not in `CELL_GOAL_CONTROL_FUNCTORS`.** The controller named four
   functors and I kept to them. A `("*->", C, T)` cell goal will attempt an
   ordinary `*->`/2 lookup and fail silently rather than get the diagnostic.
   One-word fix if that is wanted.
4. **A cell assert requires an existing `-dynamic` declaration, where a
   `Compound` assert still creates its predicate.** Deliberate (a cell is
   indistinguishable from a str-headed data tuple, so it must not mint state),
   and it is the brief's ruling — but it is an asymmetry between two spellings
   of assert, and worth a second look when the ISO surface lands, since ISO
   `assert/1` does create.
5. **`_declared_with_fields` imports `compiler.terms_to_ast` from
   `builtins/database_ops`.** Function-local, on the refusal path only, so no
   import-time cycle and no hot-path cost — but it is a builtins→compiler
   direction that did not exist in this file before.

---

## Fix round 1

FIX_BASE `6ae672ef`. Seven items ruled by the controller (F1–F5, F7, C3); F6 and
F8 deferred, untouched.

### F1 (Important) — a cell `assertz` stored the caller's LIVE `Var`

Reproduced first: with `p(1), p(2)` and `seen/1` dynamic,

```python
X = Var()
for _ in solve(("p", X), lm):
    list(pcall("assertz", ("seen", X), module=lm))
# seen(Y) → [2, 2]      while Compound("seenc", (X,)) → [1, 2]
```

`_check_cell_head_permission` hands the cell's slots straight to
`pred_cls(*args)`, and `_normalize_fact_clause` passes a class term through
untouched, so every stored head held the same variable.

Fixed on the ASSERT path only, in `_build_clause`
(`clausal/logic/builtins/database_ops.py:70-88`): `was_cell` is captured before
the gate, and after the gate returns the head goes through the new
`_freeze_asserted_head_args` (`:91-129`), which rebuilds it with each argument
`deref`'d. Both head shapes are handled — `Compound(functor, ...)` and
`type(head)(*fields)` — so the fix does not depend on which normalization the
gate chose. A SHALLOW `deref`, deliberately: that is exactly what the `Compound`
path's Var+Unify machinery does, and the point is for the two spellings to
agree.

Not in `_check_cell_head_permission`, per the ruling: `retract` calls that gate
directly and must keep SHARING, since binding the pattern's variables is how a
retracted clause's values escape with the solution (A09-F008). Pinned both
ways — `test_collect_by_assert_over_a_cell_stores_one_clause_per_solution`
(the driven loop, asserting `[1, 2]`), `test_the_cell_spelling_agrees_with_the_compound_spelling`
(both spellings in one test), and `test_the_freeze_is_on_the_assert_path_only`
(retract still binds).

RED at base, with the freeze disabled in the working tree:

```
E       assert [2, 2] == [1, 2]
E       assert [2, 2] == [1, 2]
FAILED tests/test_cell_goals.py::TestCellAssertRetract::test_collect_by_assert_over_a_cell_stores_one_clause_per_solution
FAILED tests/test_cell_goals.py::TestCellAssertRetract::test_the_cell_spelling_agrees_with_the_compound_spelling
2 failed, 56 deselected
```

The class-term spelling `assertz(m.seen(X))` is NOT changed (ruled out of
scope) and, with the unbound-argument residual that both surviving paths share,
is written up in
`todo/assert-stores-live-vars-for-class-term-and-cell-spellings-2026-09-06.md`,
which names both spellings, carries the repro, records that ISO `assert/1`
copies its argument (the eventual one-line fix for all of it), notes the
`retract/1` interaction that forbids doing it in the shared gate, and marks the
cell spelling as fixed in this round.

### F2 (Important) — `call/N` missed an `-import_from`'d predicate

`db.get_dispatch` is the dispatch table plus the builtin registry; it does not
read the module dict, and an `-import_from`'d predicate lives on the OWNER's
row. So `solve(("lp", Z), importer)` answered `[1, 2]` and `call(("lp", Z))`
from the same module answered `[]`.

`_resolve_named_goal` now falls back to the module namespace before returning
`None` (`clausal/logic/builtins/higher_order.py:88-92`), through a new
`_namespace_dispatch` (`:95-127`) that reuses `database_ops`'
`_find_pred_cls` (arity-checked) and `_home_db` rather than growing a second
copy of the resolver. The home lookup is keyed on `pred_cls.__name__`, not the
local spelling, because an `-import_from` alias binds the exporter's class under
a different name — the same canonicalization `_check_cell_head_permission`
already does. It returns `None` for a name that is not in the namespace at that
arity, so silent failure is unchanged where it should be. Pinned by
`test_an_imported_predicate_answers_call_as_it_answers_solve`, which asserts
`call` answers **equal** `solve`'s answers on the same cell.

Report §4 corrected in place, as a marked `CORRECTED, fix round 1 (F2)` block
under the paragraph rather than a silent edit: the route delivers the calling
module's **db**, and `db.get_dispatch` reads that db's dispatch table, not its
module dict; with the fallback the original claim holds. `progress.md` not
touched (the controller has ledgered the correction).

### F3 (Minor) — a 0-argument control cell failed silently

`and call_args` dropped (`higher_order.py:78-83`). `call((",",))` now raises the
same `type_error` `solve((",",), m)` raises. Pinned by
`test_a_zero_argument_control_cell_is_refused_not_silently_failed`.

### F4 (Minor) — the atom spelling bypassed the qualified-goal stub

Both deferred routes now decide on the FOLDED goal
(`higher_order.py:71-83`): the fold happens first, `folded = (functor,) +
tuple(call_args)` is built once, and the `:`/2 stub and the control-construct
refusal both read it. So `call(":", M, G)` and `call((":", M, G))` are one goal
and get one error — and the same is now true of `call(",", A, B)` vs
`call((",", A, B))`, which the old code only got right by accident of the arity
guard. The `is_cell` guard on the qualified route is gone. Pinned by
`test_the_atom_spelling_of_a_qualified_goal_hits_the_same_stub` (same error TERM
from both spellings; the contexts differ, naming `call/3` vs `call/1`, which is
correct) and `test_the_atom_spelling_of_a_control_construct_hits_the_same_refusal`.

### F5 (Minor) — the two `:` arity guards disagreed

`_templatize_query_goal`'s guard is now `cell_f == QUALIFIED_GOAL_FUNCTOR and
len(goal) == 3` (`clausal/logic/solve.py:405-417`), matching `_term_to_goal`'s.
Pinned by `test_only_colon_slash_2_is_the_deferred_qualified_form`, which drives
both functions: `(":", 1, 2, 3)` lowers to an ordinary `AstCall(LoadName(":"),
[1, 2, 3])` and templatizes to three params, while `(":", M, G)` stays deferred
on both.

### F7 (Minor) — `_declared_with_fields` promised a distinction it does not make

**Both**, chosen deliberately: renamed to `_declared_here_at_arity`
(`database_ops.py:214`) AND the docstring rewritten to say exactly what it
answers ("does this module declare that name at that arity", whatever it turned
out to be) and why the ordering at its one call site makes that the right
question — it is consulted only after `home.row(functor, arity)` came back
`None`, and a declared name with no row has no clauses, no dispatch, no
signature and no `-dynamic` mark, which is what being a data functor consists
of. The docstring says in as many words that moving the call above the row
lookup breaks that. The caller's own docstring paragraph was updated to match.

### C3 — `*->` joins the control set

`CELL_GOAL_CONTROL_FUNCTORS = frozenset({",", ";", "->", "*->", "\+"})`
(`clausal/logic/cells.py:272`), with the ruling recorded above it. `*->` has no
compile-time form in this engine at all, so the per-functor message table
changed from node NAMES to whole remedy clauses
(`_CONTROL_CONSTRUCT_NODES` → `_CONTROL_CONSTRUCT_REMEDY`, `:274-289`): the four
others still say "write it in the clause body, where `X` compiles to an N node",
and `*->` says there is no compile-time `*->` either — soft cut arrives with the
ISO surface, and this refusal is what keeps it from looking like an ordinary
missing predicate. The existing parametrization gained `"*->"`; RED at base:

```
FAILED tests/test_cell_goals.py::TestDeferredCellGoalForms::test_a_control_construct_cell_goal_is_refused_by_solve[*->]
1 failed, 4 passed, 58 deselected
```

### Focused block (GREEN)

```
$ PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest \
    tests/test_cell_goals.py tests/test_lambdas.py tests/test_prolog_*.py \
    tests/test_cells.py tests/test_database.py tests/test_funnel_lint.py \
    tests/test_funnel_accessors.py tests/test_mutation_gate.py \
    tests/test_predrow.py tests/test_builtin_classes.py \
    tests/test_tagged_terms.py tests/test_tagged_terms_parity.py \
    tests/test_higher_order.py tests/test_solve.py tests/test_exceptions.py \
    tests/test_backend_seam.py tests/test_first_arg_index.py \
    -q -p no:cacheprovider

1466 passed, 2 xfailed, 95 warnings in 8.90s
```

`tests/test_cell_goals.py` alone: `63 passed` (54 → 63; +9 this round).

### Full suite

```
$ PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest tests/ -q \
    -p no:cacheprovider --continue-on-collection-errors

144 failed, 12248 passed, 56 skipped, 39 xfailed, 748 warnings, 1 error in 105.69s
```

145 failing names → `.superpowers/sdd/p33-state-relocation/task-5-fix1-failed-names.txt`.

```
$ comm -3 .superpowers/sdd/p33-state-relocation/task-3-base-failed-names.txt \
          .superpowers/sdd/p33-state-relocation/task-5-fix1-failed-names.txt
=== END ===
```

`comm -3` produced no output: byte-identical to the 145-name ledger. Gate met.

**One flaky run, disclosed.** The first full run of this round came back 146
names, the extra one being
`tests/audit_2026_05_25/test_class_C17_perf_memory.py::test_F026_multi_star_splits_bounded_for_moderate_input`.
It is a wall-clock threshold assertion in `clausal.terms._multi_star_splits`
(`took 3.30s (>3s)`), a function this task does not touch on any path; it passed
in isolation and passed on the re-run above. Recorded rather than quietly
re-run.

### Self-review notes, this round

- Every fix was RED-checked against `6ae672ef` before being counted, by
  restoring the base file into the tree and running the new pins; the literal
  output is quoted above for F1 and C3, and F2/F3/F4/F5 produced 4 failures out
  of the 5 selected. The fifth,
  `test_the_atom_spelling_of_a_control_construct_hits_the_same_refusal`, PASSES
  at base — it is coverage for F4's folding, not a regression pin, and saying so
  is more useful than implying it caught something.
- Two of my own new tests were wrong on first run (an `-import_from` list
  written as `[lp(A)]` rather than `[lp]`, and an assertion comparing whole
  error tuples across two surfaces whose CONTEXT correctly differs). Both fixed
  in the test, not by widening the code.
- F4's restructuring means the fold now happens before both deferred checks, so
  `_resolve_named_goal` builds `folded` once and every downstream decision reads
  it. That is a small simplification, not just a bug fix.
- `_namespace_dispatch` short-circuits when `_home_db` returns the same db AND
  the class name equals the spelling — that is exactly the lookup that already
  came back empty, so it is not repeated.

### Concerns, this round

1. `_namespace_dispatch` imports `_find_pred_cls`/`_home_db` from
   `database_ops` into `higher_order` (function-local, resolution path only).
   Reuse over duplication, per the ruling, but it is a new edge between two
   builtins modules. The obvious end state is one db-reachable name resolver
   shared by `solve`, `database_ops` and `call/N` — which is the same collapse
   Task 3's deferred-minor list already names for Task 6.
2. F3 also makes the ATOM spelling `call(",")` raise where it used to fail
   silently. That follows from the fold and is the consistent behaviour, but it
   is a slightly wider change than the cell-only shape F3 described. Full suite
   is clean.
3. The class-term half of F1 is still live (`todo/assert-stores-live-vars-…`).
   Until the ISO-surface phase copies assert's argument, `assertz(m.seen(X))`
   and `assertz(("seen", X))` disagree — the reverse of the disagreement this
   round removed, and the todo says so.
