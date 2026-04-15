"""Compile-time context dataclass.

``CompilationContext`` bundles the values that are threaded through
every goal / body / predicate compilation routine:

- ``db``           — the database used for dispatch lookups and
                     signature resolution.
- ``var_context``  — mutable Var._id → python-local-name mapping.
                     Mutated in place as ``term_to_ast_expr`` and
                     ``_preallocate_body_vars`` discover new Vars.
                     Per-clause: each clause gets a fresh dict
                     (head Vars differ per clause).
- ``trail_name``   — the name of the compiled function's trail
                     parameter (always ``"trail"`` today;
                     parameterised for historical reasons).
- ``self_name``    — (trampoline only) name of the self-generator
                     parameter — ``"this_generator"`` by default.
- ``proceed_name`` — (trampoline only) name of the solution-target
                     parameter — ``"_proceed"`` by default.
- ``fail_name``    — (trampoline only) name of the exhaustion-target
                     parameter — ``"_fail"`` by default.
- ``catcher_name`` — (trampoline only) name of the exception-handler
                     parameter — ``"_catcher"`` by default.

Plus three fields shared across all clauses of one predicate
compilation:

- ``locked_dispatch_keys``    — frozenset of ``_disp_Foo_N`` names
                                that have dispatch functions pre-
                                cached in ``base_globals``.  Emission
                                uses this to emit a direct reference
                                instead of ``Foo._get_dispatch()`` on
                                every call.  Set once in
                                ``compile_predicate_*`` before any
                                clause compiles.
- ``bucket_ref_map``          — dict keyed by static-call-site
                                ``(fname, arity, pos, key)`` tuples;
                                value is the name of a pre-bound
                                bucket function in ``base_globals``.
                                Populated by
                                ``_inject_bucket_refs_trampoline`` so
                                call-site specialisation can skip the
                                general dispatch wrapper when the
                                indexed-arg key is a static constant.
- ``joint_bucket_ref_map``    — same idea for joint (pos_i, pos_j)
                                indexing.

These three fields replace what used to be
``_compile_context_local: threading.local``.  The thread-local was
a back-channel between the predicate-compilation setup (which
populates these maps) and the dispatch-call emission (which reads
them).  By putting them on ``CompilationContext`` we make the
data-flow explicit and drop a reliance on module-level mutable
state.

The two trampoline-only parameter-name fields are harmless in
shallow mode — shallow helpers simply don't read them.  Keeping a
single ``CompilationContext`` class (rather than separate shallow /
trampoline classes) lets functions that are strategy-agnostic accept
either without branching on type.

Migration status: this dataclass is being introduced incrementally.
Public entrypoints (``compile_goal``, ``compile_body``,
``compile_predicate_*``) keep their positional-tuple signatures for
backward compatibility with external callers (tests, ``solve.py``,
``compiler_v2.py``).  Internal helpers switch to accepting ``ctx``
one sub-slice at a time — see
``implementation_plans/SLICE_B_PROGRESS.md``.
"""

from __future__ import annotations

import dataclasses
from contextlib import contextmanager
from typing import Any, TYPE_CHECKING

from ._ast_helpers import (
    FreshNames,
    _THIS_GEN_NAME,
    _PROCEED_PARAM_NAME,
    _FAIL_PARAM_NAME,
    _CATCHER_PARAM_NAME,
    _current_position,
    _pop_position,
    _push_position,
)

if TYPE_CHECKING:
    from .strategy import Strategy


_ALL_OPTIMISATIONS: frozenset[str] = frozenset(
    {"tro", "destructive_reuse", "call_site", "continuation_tco"}
)


def _default_enabled_optimisations() -> frozenset[str]:
    """Default enabled-optimisations set for new ``CompilationContext``s.

    Honours the ``CLAUSAL_DISABLE_OPT`` env var (comma-separated subset
    of {``tro``, ``destructive_reuse``, ``call_site``}) so the
    per-optimisation test sweep can run the full suite under each
    individual disable without per-test plumbing.  Unknown names are
    silently ignored.
    """
    import os
    raw = os.environ.get("CLAUSAL_DISABLE_OPT", "")
    if not raw:
        return _ALL_OPTIMISATIONS
    disabled = {s.strip() for s in raw.split(",") if s.strip()}
    return _ALL_OPTIMISATIONS - disabled


@dataclasses.dataclass
class CompilationContext:
    db: Any  # Database | None — typed loosely to avoid circular import
    var_context: dict[int, str]
    trail_name: str
    self_name: str = _THIS_GEN_NAME
    proceed_name: str = _PROCEED_PARAM_NAME
    fail_name: str = _FAIL_PARAM_NAME
    catcher_name: str = _CATCHER_PARAM_NAME

    # ── Per-predicate shared state (populated before any clause compiles)
    #
    # These fields carry information from the predicate-compilation setup
    # down to dispatch-call emission inside individual clause bodies.
    # They previously lived in ``_compile_context_local: threading.local``;
    # moving them here makes the data-flow explicit and removes a
    # module-level mutable-state dependency.
    #
    # ``bucket_ref_map`` and ``joint_bucket_ref_map`` are mutable dicts
    # shared across all clauses of one predicate — ``ctx.replace()`` does
    # a shallow copy, so these dict references remain the same object
    # across any per-clause ctx fork.
    locked_dispatch_keys: frozenset[str] = frozenset()
    bucket_ref_map: dict[tuple, str] = dataclasses.field(default_factory=dict)
    joint_bucket_ref_map: dict[tuple, str] = dataclasses.field(default_factory=dict)

    # Per-predicate globals dict — the ``base_globals`` passed into
    # ``exec``.  Needed by optimisation-hint analysis passes
    # (``optimisations/call_site.py``) to resolve callee
    # :class:`PredicateMeta` objects when computing bucket-ref hints.
    # ``None`` in test-only / partial-setup contexts; analyses must
    # treat that as "no hints available".
    base_globals: "dict | None" = None

    # ── Per-compilation fresh-name generator ─────────────────────────────
    #
    # A single ``FreshNames`` instance is shared across every ``ctx.replace()``
    # fork of a given compilation (``dataclasses.replace`` preserves fields
    # not listed in *overrides*, so all forks see the same object).  Two
    # separate ``compile_predicate_*`` invocations therefore get two separate
    # counters: AST output of one compilation no longer depends on how many
    # predicates were compiled earlier in the process.
    fresh: FreshNames = dataclasses.field(default_factory=FreshNames)

    # ── Compilation strategy (shallow vs trampoline) ─────────────────────
    #
    # Populated by ``compile_predicate_shallow`` / ``compile_predicate_trampoline``
    # before any clause compiles.  Shared helpers read ``ctx.strategy``
    # instead of taking per-hook kwargs — see ``compiler/strategy.py`` and
    # ``implementation_plans/COMPILER_MIGRATION_PLAN.md`` §5.
    #
    # ``None`` means "not yet chosen" — legitimate during the brief window
    # between CompilationContext construction and strategy assignment, but
    # helpers that need the strategy must fail loudly if they find it absent.
    strategy: "Strategy | None" = None

    # ── Slice E5a: per-optimisation enable/disable toggle ────────────────
    #
    # Names match the three E1/E2/E3 passes in
    # :mod:`clausal.logic.compiler.optimisations`.  Default is "all on"
    # — behavioural parity with pre-E5 compiles.  E5a gates only the
    # IR-side analyse/apply invocations; the legacy bypasses
    # (``preprocess_clause`` DR rewrite, ``_compile_tro_body``,
    # ``_inject_bucket_refs_trampoline``) still drive codegen and run
    # unconditionally.  E5b extends the gate to the legacy paths so a
    # disabled flag actually surfaces un-optimised AST end-to-end, and
    # adds the per-optimisation test matrix.
    enabled_optimisations: frozenset = dataclasses.field(
        default_factory=lambda: _default_enabled_optimisations()
    )

    # ── Slice E4c: TRO mode for the current clause-body compile ──────────
    #
    # ``"loop"`` (default for non-bucket trampolines) emits a local
    # ``_tro = True`` flag consumed by the enclosing ``while True``
    # wrapper.  ``"signal"`` (bucket sub-functions) writes the shared
    # ``_tro_state`` list instead.  ``None`` means the current compile is
    # **not** for a TRO-eligible clause — the SubCall arm in
    # :mod:`._lower_goalop_shared` will refuse to emit a TRO tail in that
    # state (defence against a stray ``tail_recursive`` hint slipping
    # through the IR shadow into ``_compile_body_impl``).
    tro_mode: "str | None" = None

    # ── Slice E6c: TRO plan for the current clause-body compile ──────────
    #
    # Set by the body-compiler wrapper installed in
    # :func:`_build_predicate_trampoline_funcdef` before invoking
    # ``body_compiler`` for a TRO-eligible clause.  Carries the
    # ``check_indices`` frozenset and an ``eligible`` flag.  When
    # ``eligible`` is ``True``, :func:`_compile_body_impl` splits
    # goals into ``prefix + [tail]`` and uses :func:`_compile_tro_tail`
    # as the leaf, matching the (retired) ``_compile_tro_body`` bypass.
    # On the IR side, :func:`_run_ir_parallel` applies
    # :func:`optimisations.tro.apply` to mark the tail :class:`SubCall`.
    # Typed ``Any`` to avoid an import cycle with
    # :mod:`.optimisations.tro`; runtime duck-types on
    # ``.eligible`` / ``.check_indices``.
    tro_plan: "Any | None" = None

    # ── Slice E6d-β: per-predicate clause → body IR cache ────────────────
    #
    # Populated by ``_build_predicate_trampoline_funcdef`` when it sweeps
    # for TRO-eligible clauses via ``optimisations.tro.analyse``: the
    # analyse call needs the body IR, and ``_compile_body_impl`` needs
    # the same IR a moment later.  Caching avoids a second
    # ``terms_to_goalop`` build per clause.  Keyed by ``id(clause)`` —
    # entries are created only for clauses whose body is inside the IR
    # subset (``terms_to_goalop`` did not raise).  ``None`` in contexts
    # that bypass the predicate-trampoline path.
    clause_ir_cache: "dict[int, Any] | None" = None

    # Parallel to ``clause_ir_cache`` — the ``TROPlan`` for each clause
    # (present iff the clause made it into the IR cache).  The TRO-aware
    # body_compiler wrapper reads this instead of re-running analyse.
    clause_tro_plans: "dict[int, Any] | None" = None

    # ── Slice G: source-position scope stack ─────────────────────────────
    #
    # :meth:`at_position` pushes a 4-tuple ``(start_line, start_col,
    # end_line, end_col)`` onto a module-level stack in
    # :mod:`._ast_helpers` that leaf AST builders read from when
    # stamping ``lineno`` / ``col_offset`` on the nodes they construct.
    # The stack is module-level rather than per-``CompilationContext``
    # so emitter helpers don't need to thread a context handle through
    # every call — a single ``with ctx.at_position(ir.position):`` at
    # the top of a lowering match arm scopes every emission inside.
    #
    # Compiles are not concurrent within a single interpreter thread
    # (the compiler holds the GIL for its duration), so a plain list
    # is safe; if that ever changes, switch the module-level slot to a
    # ``contextvars.ContextVar`` without touching call sites.

    @contextmanager
    def at_position(self, pos):
        """Push *pos* onto the position stack for the duration of the block.

        *pos* may be ``None`` (no-op push), a 4-tuple, or any object
        exposing a ``.position`` attribute (e.g. a :class:`GoalOp` or a
        ``pythonic_ast.nodes.Node``) — the attribute is unwrapped so
        call sites can pass the IR op or term directly.
        """
        if pos is not None and not isinstance(pos, tuple):
            pos = getattr(pos, "position", None)
        _push_position(pos)
        try:
            yield
        finally:
            _pop_position()

    @property
    def current_position(self):
        return _current_position()

    def replace(self, **overrides) -> "CompilationContext":
        """Return a shallow copy with fields overridden.

        Useful when a nested compilation needs a different ``self_name``
        or ``parent_name`` (e.g., NAF mini-trampoline using ``_naf_self``
        / ``_naf_parent``) but inherits everything else.  ``var_context``,
        ``bucket_ref_map``, and ``joint_bucket_ref_map`` are shared by
        reference — mutations in the nested compile are visible to the
        caller, matching current behaviour.
        """
        return dataclasses.replace(self, **overrides)
