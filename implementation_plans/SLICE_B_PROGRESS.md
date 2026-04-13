# Slice B progress tracker

**Goal** (from `COMPILER_MIGRATION_PLAN.md` §4):
Finish deferred-refactor #2. Every internal compile helper takes
`CompilationContext`. Thread-local state moves onto ctx.
`_monolith.py` is deleted. `__init__.__getattr__` delegation gone.

Slice B is the single largest slice in the migration. This tracker
records what's landed and what remains.

---

## Sub-slices

### B1 — Foundation for ctx-threading: dataclass fields + `_dispatch_call_iter`

**Scope (as executed, narrower than originally planned):**
Add three fields to `CompilationContext` for the thread-local state
that will eventually migrate off `_compile_context_local`:
`locked_dispatch_keys`, `bucket_ref_map`, `joint_bucket_ref_map`.
Migrate the smallest reader, ``_dispatch_call_iter``, to take ``ctx``
and read `locked_dispatch_keys` from it.  The thread-local stays in
place for now; a full migration requires threading ctx through the
full chain from `compile_predicate_*` → `_make_body_compiler` →
`compile_body` → `compile_goal` → `_compile_predicate_call` →
`_dispatch_call_iter`, which is multiple sub-slices of cascading
work.  Documented as sub-slice **B1a**; the remainder of the thread-
local migration is **B1b / B1c**.

**Status:** ☐ B1 scope revised into sub-slices B1a, B1b, B1c (see below)

### B1a — Inline Phase-0.5a aliases from `_monolith` into `predicate.py`

**Scope:** Remove the `for _n in dir(_m)` bulk-copy hack in
`predicate.py` by copying the Phase-0.5a runtime-helper alias imports
(`_dif_fn`, `_fd_eq_fn`, `_DictTerm_t`, `_KWTerm_s`, …) into
`predicate.py` directly.  Remove the corresponding block from
`_monolith.py`.  ~50 names relocated.  Preserves external API; no
behavioural change.

This eliminates one of the three "ugly hacks" listed in the compiler
README §11 (the "`predicate.py` bulk-copies `_monolith`'s globals"
gotcha).

**Status:** ✅ done

Delivered:

- Phase 0.5a alias block moved from `_monolith.py` to `predicate.py`.
- `for _n in dir(_m): globals().setdefault(_n, getattr(_m, _n))` and
  the following `del _n` removed.
- Runtime helpers (``_head_list_unify_input`` / ``_output`` /
  ``_head_multi_star_error`` / ``_body_star_unify`` /
  ``_body_multi_star_unify`` / ``_build_star_list`` /
  ``_build_multi_star_list`` / ``_in_iter`` / ``_tramp_call``) that
  flowed in via the bulk copy are now explicitly imported from
  ``clausal.logic.runtime.*`` — one less layer of indirection between
  their definition and their appearance in ``base_globals``.
- ``_deref_walk_fn``, ``_set_of_dedup``, ``_seglist_unify_gen``,
  ``_compile_context_local``, ``_BUILTIN_CLASSES``,
  ``BuiltinPredicate``, ``get_builtin_predicate``,
  ``_inject_bucket_refs_trampoline``, ``_yield_step_stmt`` likewise
  imported from their canonical locations.
- Three alias reassignments kept in ``_monolith`` only for the
  legacy re-export path used by ``__init__.__getattr__`` delegation:
  ``get_builtin_predicate``, ``BuiltinPredicate``, ``_BUILTIN_CLASSES``.
  These retire in B6 with ``_monolith.py`` itself.

Tests: 10409 pass, 0 fail (ex-trealla).

### B1b — `_dispatch_call_iter` takes ctx; plumb `locked_dispatch_keys` through

**Scope:** `_dispatch_call_iter(ctx, fname, arity, arg_exprs)` reads
from `ctx.locked_dispatch_keys`.  `_compile_predicate_call` takes ctx
and passes it to `_dispatch_call_iter`.  `compile_goal` accepts an
optional `ctx` kwarg (constructing one locally from tuple args +
thread-local-fallback when omitted).  `compile_body` similarly.
`_make_body_compiler` accepts a `ctx_template` that flows through to
`compile_body` and into `compile_goal`'s inner calls.
`compile_predicate_shallow` builds a shared `ctx_template`, captures
it in `body_compiler`, and mutates `ctx_template.locked_dispatch_keys`
at the same point it writes the thread-local.

Covers the shallow path only; the trampoline-path equivalents
(`_dispatch_call_trampoline`, `_inject_bucket_refs_trampoline`) move
in **B1c**.

**Status:** ✅ done

Delivered:

- ``CompilationContext.locked_dispatch_keys`` is authoritative for
  the shallow path's dispatch emission.  The thread-local
  ``_compile_context_local.locked_dispatch_keys`` is still written
  by ``compile_predicate_shallow`` (same value), and still consulted
  by ``compile_goal``'s ctx fallback for legacy callers that don't
  pass ctx (external callers: tests, ``solve.py``, etc.).  Dual-write
  is explicit; B1c retires the thread-local.
- ``_dispatch_call_iter`` signature changed from
  ``(fname, arity, arg_exprs, trail_name)`` to ``(ctx, fname, arity,
  arg_exprs)``.
- ``_compile_predicate_call`` signature changed from
  ``(fname, call_args, call_kwargs, db, var_context, trail_name, k_stmts)``
  to ``(ctx, fname, call_args, call_kwargs, k_stmts)``.  Its two
  callers in ``compile_goal`` match-arms updated accordingly.
- ``compile_goal`` gained ``ctx: CompilationContext | None = None``
  kwarg.  Constructs ctx from tuple args + thread-local fallback
  when omitted; otherwise uses the passed ctx.  Recursive internal
  calls (currently only ``forall``'s rewrite) pass ctx explicitly.
- ``compile_body`` gained the same ``ctx`` kwarg.  When caller
  supplies ctx, it overlays ``db`` / ``var_context`` / ``trail_name``
  via ``ctx.replace()`` — preserving the per-predicate shared fields
  (``locked_dispatch_keys`` etc.) while swapping in the per-clause
  ``var_context``.
- ``compile_body_trampoline`` also accepts ``ctx`` kwarg (for
  signature compatibility with ``_make_body_compiler_impl``) but
  currently still reads the thread-local for its own dispatch
  emission.  B1c plumbs ctx through to it.
- ``_make_body_compiler_impl`` gained ``ctx_template`` kwarg.
  When supplied, each per-clause call forwards ctx_template via
  ``body_compile_fn(..., ctx=ctx_template)``.  The closure captures
  ctx_template *by reference*, so mutations after closure creation
  (predicate.py sets ``ctx_template.locked_dispatch_keys =
  _locked_keys`` after base_globals analysis) are visible at
  compile time.
- ``compile_predicate_shallow`` now constructs ``ctx_template`` up
  front, passes it to ``_make_body_compiler``, and sets
  ``ctx_template.locked_dispatch_keys`` at the same point it updates
  the thread-local.

Tests: 10409 pass, 0 fail (ex-trealla).  AST output unchanged
(same locked keys flow through both channels).

### B1c — Trampoline-side thread-local migration

**Scope:** `_dispatch_call_trampoline` and `_inject_bucket_refs_trampoline`
take ctx and read/write the `bucket_ref_map` / `joint_bucket_ref_map`
fields.  `compile_goal_trampoline` / `_compile_predicate_call_trampoline`
propagate ctx through recursion and into the dispatch emitter.
`predicate.py`'s trampoline path builds a `ctx_template` up front,
forwards it to `_make_body_compiler_trampoline`, and mutates its
`locked_dispatch_keys` / `bucket_ref_map` / `joint_bucket_ref_map`
at the same point it writes the thread-local.  `tro.py` constructs
a ctx at its fallback call sites.

The thread-local `_compile_context_local` is not yet deleted —
legacy back-channel callers (`ite_reified` / `control_constructs` /
`tro.py`'s prefix-goal loop) still invoke `_m.compile_goal_trampoline`
without ctx and rely on the fallback.  `predicate.py` now aliases
the thread-local's bucket maps to the *same dict* as
`ctx_template.bucket_ref_map` / `.joint_bucket_ref_map`, so both
paths observe writes.  Deletion moves to B2/B3 when those callers
migrate.

**Status:** ✅ done

Delivered:

- ``_inject_bucket_refs_trampoline(ctx, clauses, base_globals)``
  mutates ``ctx.bucket_ref_map`` / ``ctx.joint_bucket_ref_map``
  directly.  Trailing thread-local writes removed.
- ``_dispatch_call_trampoline(ctx, fname, arity, arg_exprs)`` reads
  ``ctx.bucket_ref_map``, ``ctx.joint_bucket_ref_map``,
  ``ctx.locked_dispatch_keys``, ``ctx.trail_name``, ``ctx.self_name``.
- ``_compile_predicate_call_trampoline(ctx, fname, call_args,
  call_kwargs, k_stmts)`` — dropped the tuple args in favour of ctx.
- ``compile_goal_trampoline`` gained ``ctx: CompilationContext | None
  = None`` kwarg.  Constructs ctx from tuple args + thread-local
  fallback when omitted; recursive internal calls (And, Or,
  TupleLiteral, Not) pass ctx explicitly.  The NAF branch overrides
  ``self_name`` / ``parent_name`` via ``ctx.replace()``.
- ``compile_body_trampoline`` — docstring updated: ctx now actually
  does something (no longer a no-op).  Inner ``_compile_goal`` helper
  forwards ``ctx=ctx_`` to ``compile_goal_trampoline``.
- ``_make_body_compiler_trampoline`` gained ``ctx_template`` kwarg,
  forwarded through to ``_make_body_compiler_impl``.
- ``predicate.py`` ``compile_predicate_trampoline``: constructs
  ``ctx_template`` before ``_make_body_compiler_trampoline``.  Sets
  ``ctx_template.locked_dispatch_keys`` alongside the thread-local.
  Aliases the thread-local's ``bucket_ref_map`` / ``joint_bucket_ref_map``
  to the ctx_template's dict instances (same object, two names).
  Calls ``_inject_bucket_refs_trampoline(ctx_template, clauses,
  base_globals)``.
- ``tro.py`` fallback paths: build a local ``CompilationContext``
  seeded from the thread-local and pass to both
  ``_compile_predicate_call_trampoline`` and
  ``_dispatch_call_trampoline``.
- Tests in ``test_callsite_specialization.py`` updated to the new
  3-arg signature via a small ``_mkctx`` helper that bridges to the
  thread-local so the test harness still works.

Tests: 10409 pass, 0 fail (ex-trealla).

### B2 — Migrate leaf-to-mid-layer helpers to take ctx

**Scope:** Functions currently taking `(..., db, var_context,
trail_name, k_stmts[, self_name, parent_name])` migrate to taking
`(ctx, ..., k_stmts)`.  Split into three cohorts.

**Status:** ✅ done (B2a + B2b + B2c)

### B2a — Star-Is + tabled NAF

**Status:** ✅ done

Delivered:

- ``_compile_star_is`` / ``_compile_single_star_is`` /
  ``_compile_multi_star_is`` in ``star_segments.py`` migrated to
  ``(ctx, ...)``.
- ``_compile_tabled_naf_simple`` in ``tabled_naf.py`` migrated.
- Shallow Unify + Not branches and the trampoline Not branch
  updated.  The shallow Unify branch built a minimal ctx inline
  because ``_compile_deterministic_goal`` had not yet been
  migrated; B2b cleaned that up.

Tests: 10409 pass (ex-trealla).

### B2b — Control constructs, reified ITE, and shared-goal helpers

**Status:** ✅ done

Delivered:

- All helpers in ``control_constructs.py`` migrated to
  ``(ctx, ..., k_stmts)``: ``_compile_arith_cmp``, ``_deref_cmp``,
  ``_compile_once``, ``_compile_call_nth``, ``_compile_count_all``,
  ``_compile_setup_call_cleanup``, ``_compile_freeze``,
  ``_compile_when``, ``_compile_find_all_core``, ``_compile_throw``,
  ``_compile_catch_impl``, ``_compile_catch``,
  ``_compile_catch_trampoline``, ``_compile_goal_lambda``,
  ``_hoist_lambda_args``.  ``_flatten_conjunction`` and
  ``_catcher_to_structural`` left alone (no ctx needed).
- Recursive ``_m.compile_goal`` / ``_m.compile_goal_trampoline`` calls
  inside these helpers now forward ``ctx=ctx``.
  ``_compile_catch_trampoline`` inherits ``self_name`` /
  ``parent_name`` from ctx (previously an extra positional arg).
- ``_compile_deterministic_goal`` / ``_compile_shared_membership_goal``
  / ``_compile_shared_meta_call`` in ``goal_shallow.py`` migrated to
  ``(ctx, goal, k_stmts)``.  Their call sites in ``compile_goal`` /
  ``compile_goal_trampoline`` updated.  The shallow Unify / star-Is
  branch no longer builds a throwaway inline ctx.
- ``_compile_predicate_call_impl`` migrated to
  ``(ctx, fname, call_args, call_kwargs, k_stmts, *, emit_dispatch)``.
  Its two callers (shallow + trampoline predicate-call) pass ctx.
- Shallow ``compile_goal``'s ``And`` / ``Or`` / ``TupleLiteral`` /
  ``Not`` recursive calls forward ``ctx=ctx`` (was missing on most
  of these arms before this slice).
- ``tro.py``'s TRO-tail emitter builds a local ctx before calling
  ``_hoist_lambda_args``.
- ``tests/test_lambdas.py``'s direct tests of ``_compile_goal_lambda``
  updated to use a small ``_mkctx`` helper.
- ``_compile_reified_ite`` / ``_compile_reified_ite_trampoline``,
  ``_compile_reified_ite_eq(_trampoline)`` + ``_impl``,
  ``_compile_reified_ite_fd(_trampoline)`` + ``_impl``,
  ``_compile_general_ite`` / ``_compile_general_ite_trampoline`` in
  ``ite_reified.py`` all migrated to ``(ctx, ..., k_stmts)``.  The
  trampoline variants inherit ``self_name`` / ``parent_name`` from
  ctx; ``_compile_general_ite_trampoline``'s condition sub-generator
  forks a ctx via ``ctx.replace(self_name=..., parent_name=...)``.

Tests: 10409 pass (ex-trealla).

### B2c — Retire the `_compile_context_local` thread-local

**Status:** ✅ done

Delivered:

- ``_compile_context_local`` thread-local **retired**: removed from
  ``_monolith.py``, from the module-level re-assignments in
  ``goal_shallow.py`` / ``goal_trampoline.py``, and from the
  read/restore block pairs in ``predicate.py``
  (``compile_predicate_shallow`` and
  ``compile_predicate_trampoline``) and ``tro.py``.  The
  ``if ctx is None`` fallbacks in ``compile_goal`` /
  ``compile_goal_trampoline`` now construct a plain
  ``CompilationContext`` without consulting any thread-local.
  ``ctx_template`` on ``predicate.py`` is authoritative for
  ``locked_dispatch_keys`` / ``bucket_ref_map`` /
  ``joint_bucket_ref_map``.
- ``tests/test_callsite_specialization.py``: ``_mkctx`` now
  constructs a ``CompilationContext`` with fresh maps supplied per
  test; the old ``_compile_context_local.bucket_ref_map = {}`` setup
  stanzas deleted.  The ``test_bucket_ref_map_populated`` test asserts
  against the ctx's ``bucket_ref_map`` rather than the thread-local.

Tests: 10409 pass (ex-trealla).

### B3 — Migrate `compile_goal` / `compile_goal_trampoline` dispatchers

**Scope:** Public entry points keep their legacy signatures for
external callers (`solve.py`, tests).  Internal recursive calls go
through a ctx-taking `_dispatch_goal(ctx, goal, k_stmts)` /
`_dispatch_goal_trampoline(ctx, goal, k_stmts)` helper.  Public
functions become thin wrappers that construct ctx and delegate.

**Status:** ✅ done

Delivered:

- Introduced ``_dispatch_goal(ctx, goal, k_stmts)`` in
  ``goal_shallow.py`` and ``_dispatch_goal_trampoline(ctx, goal,
  k_stmts)`` in ``goal_trampoline.py``.  Each owns the full
  goal-type match and is ctx-native — no tuple args.
- ``compile_goal`` / ``compile_goal_trampoline`` shrank to
  three-line wrappers: construct ctx from the legacy tuple args if
  the caller didn't supply one, then delegate.  External-caller
  signatures unchanged.
- All in-file recursive calls (And / Or / TupleLiteral / Not /
  forall rewrite) now use ``_dispatch_goal(ctx, ...)`` /
  ``_dispatch_goal_trampoline(ctx, ...)`` directly — no more
  positional ``db, var_context, trail_name`` repetition.
- NAF's inner compile in the trampoline path uses
  ``ctx.replace(self_name=..., parent_name=...)`` instead of the
  three-argument overlay.
- ``compile_body`` / ``compile_body_trampoline`` inline closures
  drop their ``lambda`` arg plumbing — ``compile_goal_fn`` is now
  ``lambda goal, ctx_, k: _dispatch_goal(ctx_, goal, k)``.

Tests: 10409 pass (ex-trealla).

**Status:** ☐ not started

### B4 — Eliminate `_m.compile_goal` / `_m.compile_goal_trampoline` lazy accessors

**Scope:** Replace every `_m.compile_goal(...)` and
`_m.compile_goal_trampoline(...)` with an explicit import.  Break
any resulting cycles by moving the relevant function (not by lazy
access).

**Status:** ☐ not started

### B5 — Migrate per-compilation `FreshNames`

**Scope:** Replace module-level `_compile_counter: list[int]` in
`_ast_helpers.py` with a `FreshNames` instance on
`CompilationContext.fresh`.  Two compilations no longer share name
state — the numbers reset per compilation, making AST diffs
deterministic.

**Status:** ☐ not started

### B6 — Inline `_monolith`'s aliases into `predicate.py` and retire `_monolith.py`

**Scope:** The ~50 Phase-0.5a hoisted runtime-helper aliases
(`_fd_eq_fn`, `_DictTerm_t`, ...) that live in `_monolith.py` and
reach `predicate.py` via `for _n in dir(_m)` bulk-copy get inlined
into `predicate.py` directly.  `_monolith.py` is deleted.
`__init__.__getattr__` delegation is removed; explicit re-exports
only.  Tests / tools that imported private names get pointed at the
precise new location.

**Status:** ☐ not started

### B7 — Clean up the boundary-test transitional exception

**Scope:** After B6, `_monolith.py` no longer exists, so the
allowed-list in `tests/test_runtime_compiler_boundary.py::test_compiler_imports_of_runtime_are_in_predicate_py_only`
shrinks to just `{predicate.py}`.  The transitional exception comment
is deleted.

**Status:** ☐ not started

### B8 — Move `clausal/logic/_list_unify.c` / `_trampoline.c` under `runtime/`

**Scope:** Carried forward from slice A review (item 1): the C
extensions physically belong in `runtime/`. Requires `setup.py`
extension-path updates.  Also reconsider whether
`clausal/logic/trampoline.py` / `clausal/logic/variables.py` should
migrate under `runtime/` too — both are referenced from compiled-
predicate `base_globals`.

**Status:** ☐ not started (review question; scope TBD)

---

## Invariants maintained throughout B

- Full test suite green after every sub-slice (M1).
- Public API of `compile_predicate_*` unchanged throughout.
- External callers (`solve.py`, `compiler_v2.py`, tests) unaffected
  until B6/B7.
- No sub-slice commits a half-migration: each sub-slice either fully
  migrates its scope or leaves it alone.

---

## Validation across all B sub-slices

- Full test suite (~10409 non-trealla tests + the runtime/compiler
  boundary checks) passes.
- AST diff: compile the regression corpus (a standard set of
  predicates — `append/3`, `reach/2`, a CLP(FD) example, a catch-
  heavy predicate) before and after each sub-slice. Output must be
  **byte-identical** to the commit's parent for no-semantic-change
  slices.
- Grep assertions:
  - After B1: `grep -r "_compile_context_local" clausal/` returns no
    hits.
  - After B4: `grep -r "_m\.compile_goal" clausal/logic/compiler/`
    returns no hits.
  - After B6: `grep -r "_monolith" clausal/logic/compiler/` returns
    no hits; `grep -r "__getattr__" clausal/logic/compiler/__init__.py`
    returns no hits.
