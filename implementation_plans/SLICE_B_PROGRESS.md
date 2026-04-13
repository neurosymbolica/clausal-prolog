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
fields.  After this, the thread-local `_compile_context_local` has no
readers; it can be deleted from `_monolith.py`.

**Status:** ☐ not started

### B2 — Migrate leaf-to-mid-layer helpers to take ctx

**Scope:** Functions currently taking `(..., db, var_context,
trail_name, k_stmts[, self_name, parent_name])` migrate to taking
`(ctx, ..., k_stmts)`.  Cohort order (smallest call-graphs first):

- Star-Is compilers (`_compile_star_is`, `_compile_single_star_is`,
  `_compile_multi_star_is` in `star_segments.py`).
- Tabled NAF (`_compile_tabled_naf_simple` in `tabled_naf.py`).
- Control constructs (`_compile_once`, `_compile_catch`,
  `_compile_freeze`, `_compile_when`, `_compile_find_all_core`,
  `_compile_throw`, `_compile_catch(+_trampoline)`,
  `_compile_goal_lambda`, `_compile_call_nth`, `_compile_count_all`,
  `_compile_setup_call_cleanup`, `_compile_arith_cmp`, `_deref_cmp`).
- Reified ITE (`_compile_reified_ite_eq_impl`,
  `_compile_reified_ite_fd_impl`, `_compile_general_ite(+_trampoline)`).

**Status:** ☐ not started

### B3 — Migrate `compile_goal` / `compile_goal_trampoline` dispatchers

**Scope:** Public entry points keep their legacy signatures for
external callers (`solve.py`, tests).  Internal recursive calls go
through a ctx-taking `_dispatch_goal(ctx, goal, k_stmts)` /
`_dispatch_goal_trampoline(ctx, goal, k_stmts)` helper.  Public
functions become thin wrappers that construct ctx and delegate.

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
