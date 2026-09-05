"""Tagged cells: the unconditional plain-tuple compiled term representation.

Every compound term compiles to a cell (P3-2, the cell-default flip) -- there
is no opt-in flag left to spell. (History: this module started as the Phase 2
bridge's opt-in representation, Task 1 of
``docs/superpowers/plans/2026-09-03-phase2-bridge.md``; P3-2 deleted the
``-tagged_terms`` flag that gated it.)

Spec: ``implementation_plans/tagged-tuple-term-representation.md`` (design
§1, optimisations §3c).

A *cell* is a plain Python ``tuple`` whose slot 0 identifies its shape:

  - a ``str`` functor   -> ``("point", x, y)``   a compound term ``point/2``.
  - the ``tuple`` TYPE OBJECT (``TUPLE_TAG``) -> ``(tuple, e1, e2, ...)``
    tuple-DATA, not a compound -- this is how a cell represents a bare
    Python tuple as term data without slot 0 colliding with a real user
    value (a plain data tuple's own slot 0 could be anything; tagging with
    the ``tuple`` type itself sidesteps that).

Nothing else may occupy slot 0 -- ``make_cell`` enforces this; ``is_cell``
recognizes it.

Phase 3 Task 5 (§1b, ``implementation_plans/tagged-tuple-term-representation.md``):
an unbound-``Var`` functor slot -- the bridge's higher-order/not-yet-resolved
cell, ``(X, a, b)`` -- is DEPRECATED and no longer part of this domain.
It caused the bridge's one Critical (a cell built with a Var functor
vanished from recognition the instant ``unify`` bound that functor, because
recognition dereferenced slot 0 and the bound value could be anything),
imposed a permanent deref on every recognition site, and permitted category
instability (``(F, 1)`` flipping from compound to tuple-data if ``F`` binds
to the ``tuple`` type). Higher-order metaprogramming over cells routes
through ``functor/3`` / ``=../2`` / ``call/N`` instead (P3-3; ISO's own
trade-off). A tuple whose slot 0 is a Var (bound or not) is therefore not a
cell at all -- it falls through to plain-tuple handling everywhere, the
same as a tuple tagged with an ``int`` or any other non-str, non-``tuple``
value. ``make_cell`` raises ``TypeError`` for a Var functor same as any
other invalid one; every recognition site (``is_cell``, the funnel
accessors, ``head_match``, the head walker, the list-dispatch gates) reads
slot 0 RAW -- no deref, ever, on this path.

BRIDGE-ENTRY RULING (ledgered in the Phase 2 bridge plan's Global
Constraints): ``is_cell`` does NOT require ``sys.intern``'d functors --
equality is the semantics of functor comparison everywhere a cell is
compared (the existing C tuple-unify branch this module deliberately rides
compares slot 0 with ``==``, never ``is``; see ``do_unify``'s
``PyTuple_Check(t1) && PyTuple_Check(t2)`` branch in
``clausal/logic/variables/_variables.c``). ``make_cell`` interns as a
convenience only (fewer distinct string objects, marginally faster
compares in practice) -- ``is_cell`` and every accessor here accept ANY
``str`` in slot 0, interned or not.

THE DISCIPLINE (formerly documented here as an accepted "known ambiguity",
now the rule per §1b's slot-0 narrowing): every runtime tuple IS a cell --
a plain user tuple whose slot 0 happens to be a ``str`` -- e.g. ``("hello",
1)`` meant as ordinary tuple data, not a compound -- is a str-functor cell
by shape, full stop, and ``is_cell``/the funnel accessors in
``clausal/logic/builtins/_helpers.py`` treat it as one. There is no
narrower "is this REALLY a cell" test to fall back on; a caller that needs
"plain tuple data, not a compound" must use the ``TUPLE_TAG``-tagged form
(``make_tuple_cell``) rather than a bare str-first tuple. The residual
untagged shapes this bridge stage still has -- ``dict``/``set`` pairs, which
carry no slot-0 tag at all -- are Phase 4's business (pair migration,
per the plan's roadmap), not this module's.

Cells ride the *existing* C unify/walk tuple branches unchanged (they are
just tuples): this module adds no C code and no new representation
machinery, only Python-level construction/inspection helpers, per the
Phase 2 bridge plan's Global Constraints ("Cells are plain tuples ...
They already unify/walk/key through the existing C tuple branches -- do
not add representation machinery the engine already has.").
"""

from __future__ import annotations

import sys
from typing import Any

from clausal.logic.variables import deref, is_var

__all__ = [
    "FUNCTOR_SIGNATURES_KEY",
    "IMPLICIT_FUNCTORS_FLAG",
    "CELLS_NAMESPACE_KEY",
    "TUPLE_TAG",
    "make_cell",
    "make_tuple_cell",
    "is_cell",
    "cell_functor",
    "cell_args",
    "cell_arity",
    "intern_cell",
    "clear_intern_table",
    "is_intern_enabled",
    "set_intern_enabled",
    "compound_cell_shape",
    "CELL_GOAL_CONTROL_FUNCTORS",
    "refuse_control_construct_cell",
    "QUALIFIED_GOAL_FUNCTOR",
    "resolve_qualified_goal_cell",
]
# NOTE: `_cell_shape` is intentionally NOT in __all__ (internal helper) but
# IS imported directly by other modules that need to test "is this
# cell-shaped" without a second read of slot 0 -- the same
# "leading-underscore, cross-module funnel helper" convention that
# `_helpers.py` already uses for _functor_name/_arity/etc. Importers, all
# routing raw slot-0 checks through this ONE predicate rather than
# re-spelling "type(x) is tuple and (type(x[0]) is str or x[0] is
# TUPLE_TAG)" locally (P3-2 Task 5 carry-forward consolidation):
#   - clausal/logic/builtins/_helpers.py (the funnel -- inlines the str-only
#     compound check directly, see `_cell_functor`, since it additionally
#     needs to exclude TUPLE_TAG from "compound")
#   - clausal/logic/compiler/head_match.py (the live-cell branch)
#   - clausal/logic/compiler/globals_env.py (`_walk_head`'s cell branch)
#   - clausal/logic/compiler/list_dispatch.py (the head-literal/deep-gate
#     helpers)
#   - `compound_cell_shape` below -- the P3-3 Task 5 narrowing (str functor
#     only) that database.head_key, solve._term_to_goal/_structural_key/
#     _templatize_query_goal, builtins/higher_order's call/N family and
#     builtins/database_ops' assert/retract gate all share.  Those five call
#     `compound_cell_shape`, NOT `_cell_shape` directly, so the
#     "is this cell-shaped AND does it name a predicate" question has one
#     spelling too.
# See _cell_shape's docstring.


# The tag used in slot 0 for a "tuple as term data" cell: ``(tuple, e1,
# ...)``. This is the ``tuple`` TYPE OBJECT itself, not the string
# ``"tuple"`` -- see ``is_cell``/``make_tuple_cell``.
TUPLE_TAG = tuple


# The module-namespace key holding a module's functor-signature registry:
# ``{"point": ("x", "y"), ...}``, one entry per ``(name, fields)`` the
# ``-module``/``-private`` rewrite saw -- predicates included, since the
# data/predicate split is decided by binding shape (whether a functor has
# clauses), not by anything the registry itself records.  Emitted by
# ``clausal/templating/term_rewriting.py``'s ``_handle_module_directive`` /
# ``_handle_private_directive`` as a module-level
# ``__clausal_functor_signatures__ = {...}`` assignment (accumulated via
# ``dict.update`` across multiple directives in the same file -- an
# assignment rather than a ``module_items`` entry, deliberately: module items
# are recovered separately when a module loads from its ``.pyc`` cache,
# whereas an assignment is part of the cached bytecode and therefore cannot
# go missing on the cached path);
# ``-import_from`` copies the imported names' entries into the importer's
# dict under their LOCAL spelling.
#
# ``clausal/logic/compiler/terms_to_ast.py``'s ``functor_signature_for``
# consults this registry FIRST, falling back to a resolved class's
# ``_fields`` while generated functor classes still exist (P3-2 Tasks 1-2 of
# the cell-default flip).  Once a later task removes those classes, this
# registry becomes the sole source of truth for a functor's declared field
# names.
FUNCTOR_SIGNATURES_KEY = "__clausal_functor_signatures__"


# The module-namespace key marking a module as opted into OPEN-WORLD functor
# construction (P3-2 Task 6, user ruling R7): ``-implicit_functors`` compiles
# to a module-level ``__clausal_implicit_functors__ = True`` assignment, the
# same "flag survives the ``.pyc``-cached load path" shape
# ``TAGGED_TERMS_FLAG`` used before the Phase 2 bridge's flag machinery was
# deleted (P3-2 Task 2, THE FLIP) -- an assignment rather than a
# ``module_items`` entry, because an assignment is part of the cached
# bytecode and therefore cannot go missing on the cached path, whereas a
# module item is recovered separately when a module loads from its ``.pyc``.
#
# Construction checking is ON by default everywhere (``FUNCTOR_SIGNATURES_KEY``
# governs it): a keyword-free reference to an undeclared functor is a runtime
# ``NameError`` and an over-arity reference to a declared one is a
# compile-time ``SyntaxError`` (see
# ``clausal.logic.compiler.terms_to_ast.cell_signature_for_name`` /
# ``_place_signature_slots``).  A module carrying this flag opts OUT of both
# checks for keyword-free construction only: ``clausal.logic.compiler.
# terms_to_ast.term_to_ast_expr`` and ``clausal.logic.compiler.head_match.
# head_to_match_pattern`` both consult it (via ``terms_to_ast.
# lowering_globals()``) to build a cell of ANY functor at ANY WRITTEN arity,
# declared signature or not -- signatures become advisory, not a keyhole, for
# every plain (keyword-free) reference in a flagged module.  Keyword
# construction/matching still needs a real signature to place its named
# slots against, flag or no flag -- the flag opens functor VOCABULARY, not
# the keyword-placement contract.  Orthogonal to ``-strict_atoms`` /
# ``-implicit_atoms``: this flag says nothing about bare (0-arity) ATOM
# references, which keep whatever declaredness discipline those directives
# already govern.
IMPLICIT_FUNCTORS_FLAG = "__clausal_implicit_functors__"


# The key under which a compiled predicate's ``base_globals`` holds THIS
# module, so emitted code can name ``TUPLE_TAG`` as a DOTTED value pattern
# (``$cells.TUPLE_TAG``).  A ``match`` pattern cannot test a bare name -- that
# is a capture, not a value test -- so the tuple-DATA tag needs an attribute
# access, and this is its root.  The ``$`` prefix is what makes it safe: no
# Python identifier can collide with it, whereas rooting the pattern at
# ``builtins`` would break in any module that happens to bind that name
# (``base_globals`` is updated FROM the module namespace).  Injected by
# ``clausal/logic/compiler/predicate.py`` and read by
# ``head_match.head_to_match_pattern``'s live-cell branch, which emits the
# tuple-DATA arm only when the entry is actually present.
CELLS_NAMESPACE_KEY = "$cells"


def _valid_functor_slot(slot0: Any) -> bool:
    """True if *slot0* is a legal cell slot-0 value (the bridge-entry
    ruling, narrowed by §1b/Task 5): a ``str`` functor or the ``tuple``
    type object. Nothing else -- a Var functor is DEPRECATED (see the
    module docstring) and no longer legal here.

    *slot0* is read RAW by the caller (see ``_cell_shape`` below) -- this
    function never derefs.

    EXACT type, not ``isinstance`` (Task 5 review fix round 1): matches
    the exact-type convention the rest of the post-Task-4 cell machinery
    already committed to (``arg_index._arg_to_index_key``,
    ``_runtime_arg_key``/``_is_deeply_ground_walk``, and this task's own
    brief-mandated ``_helpers._cell_functor``, which spells
    ``type(term[0]) is str`` directly). No test in this suite constructs a
    ``str`` subclass as a functor.
    """
    return type(slot0) is str or slot0 is TUPLE_TAG


def _cell_shape(x: Any) -> tuple[bool, Any]:
    """Return ``(is_cell, slot0)`` for *x*, reading slot 0 RAW.

    §1b/Task 5: NO deref, ever, on this recognition path -- the bridge's
    slot-0-Var (higher-order functor) support is deprecated precisely
    because it required one (see the module docstring). ``is_cell`` is
    defined in terms of this; several other modules import this directly
    to test "is this cell-shaped" without a second read of slot 0 (see the
    NOTE above ``__all__`` for the full, current list of importers) --
    ``clausal/logic/builtins/_helpers.py``'s own ``_cell_functor`` is the
    one exception, inlining an equivalent str-only check directly instead
    of importing this, since it needs different "compound" semantics
    (excluding ``TUPLE_TAG``).
    """
    if type(x) is not tuple or len(x) < 1:
        return False, None
    slot0 = x[0]
    return _valid_functor_slot(slot0), slot0


def compound_cell_shape(x: Any) -> tuple[bool, Any]:
    """Return ``(is_compound_cell, functor)`` -- ``_cell_shape`` narrowed to
    the cells that can name a PREDICATE.

    A ``TUPLE_TAG`` cell is tuple DATA: it has no functor name, so it is
    never a goal, never a clause head, and never an ``assertz`` argument.
    Everything ``_cell_shape`` accepts that is not ``TUPLE_TAG`` is a ``str``
    functor (see ``_valid_functor_slot``), so this is exactly "a cell with a
    str functor", read RAW, with no second look at slot 0.

    THE ONE SPELLING for P3-3's goal/head surfaces (Task 5, R11):
    ``database.head_key``, ``solve._term_to_goal``/``_structural_key``/
    ``_templatize_query_goal``, ``higher_order``'s ``call/N`` family and
    ``database_ops``'s assert/retract gate all ask this question and all ask
    it here, built ON ``_cell_shape`` rather than re-spelling it.
    ``builtins/_helpers._cell_functor`` is the funnel's own equivalent and
    stays separate for the reason recorded above ``__all__``: the funnel
    inlines its slot-0 check rather than importing one.
    """
    ok, functor = _cell_shape(x)
    if ok and functor is not TUPLE_TAG:
        return True, functor
    return False, None


# The control-construct functors an ISO term can spell (``','(A, B)`` is the
# conjunction as a TERM, which under cells is ``(",", A, B)``).  DEFERRED in
# cell-GOAL position this phase -- see ``refuse_control_construct_cell``.
#
# ``*->`` (soft cut) is in the set on the P3-3 Task 5 fix-round-1 ruling: it is
# a control construct in every Prolog that has it, and the fact that this
# engine has no compile-time form for it yet is a reason to give the SAME
# diagnostic, not a reason to let it fall through to an ordinary ``*->``/2
# lookup and fail silently.
CELL_GOAL_CONTROL_FUNCTORS = frozenset({",", ";", "->", "*->", "\\+"})

# What to tell the user instead, per functor -- the whole remedy clause, not
# just a node name, because ``*->`` has no compile-time form to point at.
_CONTROL_CONSTRUCT_REMEDY = {
    ",": "write the conjunction in the clause body, where `,` compiles to an "
         "And node",
    ";": "write the disjunction in the clause body, where `;` compiles to an "
         "Or node",
    "->": "write the if-then in the clause body, where `->` compiles to an Or "
          "of And nodes",
    "\\+": "write the negation in the clause body, where `\\+` compiles to a "
           "Not node",
    "*->": "there is no compile-time `*->` on the adaptor surface either — "
           "soft cut arrives with the ISO surface, and this refusal is what "
           "keeps it from looking like an ordinary missing predicate",
}


def refuse_control_construct_cell(cell: Any, functor: Any, context: str) -> None:
    """Refuse a control-construct functor in cell-GOAL position (P3-3 Task 5).

    ISO's conjunction-as-a-term is ``','(A, B)``, which under the cell
    representation is the ordinary cell ``(",", A, B)``; the same goes for
    ``;``, ``->``, ``*->`` and ``\\+``.  Calling one means running a control construct
    the engine only ever lowers at COMPILE time -- the adaptor surface never
    produces these as terms (a conjunction written in a clause body becomes an
    ``And`` node), so only a runtime-built term can reach a goal position
    spelling one.

    Supporting them is a real feature (a runtime goal-tree interpreter), not a
    branch: it needs cut/barrier semantics, a delimited-control story for
    ``->``, and a decision about ``\\+``'s NAF database -- all of which the
    ISO-surface phase owns.  Until then the diagnostic names the functor and
    the compile-time form, instead of the goal quietly failing (which is what
    ``call((",", A, B))`` did before this task) or an internal
    ``NotImplementedError`` from ``terms_to_goalop``.

    Raises ``LogicException(type_error(callable_control_construct_unsupported,
    Cell))``; returns None for every other functor.  The culprit is the cell
    itself -- a plain tuple, so it round-trips through unification and
    ``copy_term`` and can be matched by a ``catch/3`` pattern.
    """
    if functor not in CELL_GOAL_CONTROL_FUNCTORS:
        return
    # Local import, and it has to be: ``clausal.terms`` imports THIS module
    # for ``TUPLE_TAG`` and ``clausal.logic.exceptions`` imports
    # ``clausal.terms``, so a module-level import here would close the cycle.
    from clausal.logic.exceptions import (  # noqa: PLC0415
        LogicException, type_error,
    )
    remedy = _CONTROL_CONSTRUCT_REMEDY[functor]
    raise LogicException(type_error(
        "callable_control_construct_unsupported", cell,
        f"{context}: {functor}/{len(cell) - 1} is a control construct, and a "
        f"control construct built as a TERM is not callable yet — {remedy} "
        f"(deferred to the ISO-surface phase; see clausal/logic/cells.py "
        f"refuse_control_construct_cell)",
    ))


# The functor of the module-QUALIFIED goal form ``M:G``, which under cells is
# the arity-2 cell ``(":", M, G)``.
QUALIFIED_GOAL_FUNCTOR = ":"


def resolve_qualified_goal_cell(cell: Any, context: str) -> Any:
    """Resolve the module-qualified goal cell ``(":", M, G)`` to ``(module, G)``.

    STUB (P3-3 Task 5).  Task 6 of the state-relocation plan provides
    ``resolve_module`` and REPLACES THIS FUNCTION BODY; until then every
    qualified goal is refused with a typed ``existence_error`` naming the
    form, so Task 5's goal surfaces can land the branch (and be gated) without
    waiting on Task 6, and no caller has to learn a new call shape when the
    real resolver arrives.

    The two callers -- ``solve._term_to_goal`` and ``higher_order``'s
    ``call/N`` family -- already route ``(":", M, G)`` here, so Task 6's whole
    integration is this body: resolve *M* to a module, then hand back the
    module and the inner goal *G* for the caller to lower against.

    :param cell:    the ``(":", M, G)`` cell.
    :param context: the calling surface's indicator, for the error's context.
    :raises LogicException: always, until Task 6.
    """
    from clausal.logic.exceptions import (  # noqa: PLC0415 -- see the note in
        LogicException, existence_error,   # refuse_control_construct_cell
    )
    from clausal.terms import Compound  # noqa: PLC0415

    raise LogicException(existence_error(
        "procedure", Compound("/", (QUALIFIED_GOAL_FUNCTOR, 2)),
        f"{context}: the module-qualified goal {cell[1]!r}:{cell[2]!r} cannot "
        f"be resolved yet — `:`/2 goal resolution lands with the module "
        f"resolver in P3-3 Task 6 (see cells.resolve_qualified_goal_cell)",
    ))


def make_cell(functor: Any, *args: Any) -> tuple:
    """Construct a cell ``(functor, *args)``, enforcing the slot-0 ruling.

    *functor* must be one of:

      - a ``str`` -- interned via ``sys.intern`` as a convenience (see the
        module docstring's BRIDGE-ENTRY RULING: ``is_cell`` does not
        require this, ``make_cell`` does it only to make repeated
        same-functor cells cheaper to compare/store).
      - ``TUPLE_TAG`` (the ``tuple`` type object) -- for tuple-as-data cells.

    Anything else (``int``, a class other than ``tuple``, ``None``, an
    unbound or bound ``Var``, ...) raises ``TypeError``. A ``Var`` functor
    is DEPRECATED per §1b (see the module docstring) -- it is no longer a
    legal slot-0 value, regardless of whether it is bound: higher-order
    metaprogramming over cells routes through ``functor/3`` / ``=../2`` /
    ``call/N`` instead (P3-3).
    """
    if isinstance(functor, str):
        functor = sys.intern(functor)
    elif functor is TUPLE_TAG:
        pass
    else:
        raise TypeError(
            "make_cell: functor must be a str or the `tuple` type object "
            f"(TUPLE_TAG); got {functor!r} ({type(functor).__name__}) -- "
            "a Var functor is deprecated (§1b), use functor/3 or =../2 for "
            "higher-order construction over cells"
        )
    return (functor, *args)


def make_tuple_cell(*elems: Any) -> tuple:
    """Construct a tuple-DATA cell ``(tuple, e1, ..., en)``.

    Equivalent to ``make_cell(TUPLE_TAG, *elems)``, spelled out for callers
    building tuple-as-data cells (no functor validation to speak of --
    ``TUPLE_TAG`` is always valid).
    """
    return (TUPLE_TAG, *elems)


def is_cell(x: Any) -> bool:
    """True if *x* is shaped like a cell.

    A cell is a non-empty ``tuple`` (exactly ``type(x) is tuple`` -- a
    ``tuple`` subclass, e.g. a namedtuple, is deliberately excluded; term
    instances in this engine are dataclasses / ``PredicateMeta`` instances,
    never tuple subclasses, so this cannot collide with them) whose slot 0,
    read RAW (no deref -- §1b/Task 5), is a ``str`` or the ``tuple`` type
    object. A Var functor -- bound or not -- is DEPRECATED (see the module
    docstring) and is no longer cell-shaped at all: a tuple built with one
    falls through to plain-tuple handling everywhere, the same as any
    other non-str, non-``tuple`` tag.

    This is a SHAPE-only test -- see the module docstring's THE DISCIPLINE
    note: a plain user tuple like ``("hello", 1)`` also answers ``True``
    here. That is the rule for this bridge stage, not a bug.
    """
    return _cell_shape(x)[0]


def cell_functor(c: tuple) -> Any:
    """Return the functor slot (slot 0) of cell *c*, read RAW.

    §1b/Task 5: no deref -- a legally-constructed cell's slot 0 is always
    already a ``str`` or the ``tuple`` type object (``make_cell`` enforces
    this; a Var functor is deprecated and never reaches here). No shape
    validation -- callers that don't already know *c* is cell-shaped
    should check ``is_cell(c)`` first.
    """
    return c[0]


def cell_args(c: tuple) -> tuple:
    """Return the argument slice (slots 1..) of cell *c*, as a tuple."""
    return c[1:]


def cell_arity(c: tuple) -> int:
    """Return the arity (argument count) of cell *c*."""
    return len(c) - 1


# ── Selective ground-cell interning (Task 4) ──────────────────────────────
#
# Spec: ``docs/superpowers/plans/2026-09-03-phase2-bridge.md`` Task 4.
#
# ``intern_cell`` recursively collapses structurally-equal, FULLY-GROUND
# cells to the same tuple object via a module-level table -- the tabling
# freeze boundary (``clausal.logic.tabling.TableEntry.add_answer``) is the
# hook that calls it, gated by ``is_intern_enabled()`` below (default OFF).
#
# Scope, per the plan's Global Constraints ("Interning (Task 4) applies
# ONLY to fully-ground cells ... a Var anywhere disqualifies -- Var.__hash__
# stays untouched this stage"):
#
#   - Only CELLS are ever looked up in / stored into the intern table.
#     Class terms, atoms, scalars, lists, dicts -- everything that is not
#     ``is_cell``-shaped -- passes through ``intern_cell`` UNCHANGED and
#     never touches the table.
#   - "Ground" here means: no ``Var`` reachable by walking slot 0 or the
#     argument slots of the cell and any CELL nested inside it. A ``Var``
#     found anywhere in that walk disqualifies the whole cell (and every
#     cell containing it) from interning -- it is returned unchanged,
#     object-identical to what was passed in. A non-cell argument (e.g. a
#     list) is not walked further for embedded Vars -- this stage's cells
#     are built from declared functors and scalars/cells per Task 2's
#     emission rules, so that gap is not exercised by this bridge's corpus.
#   - Interning never calls ``Var.__hash__``: ``_try_intern`` below is
#     STRICTLY groundness-first -- it never calls ``hash()``/``==`` (via a
#     dict operation) on ANY value until every value reachable inside it
#     has already been proven Var-free by this same walk. A tuple's
#     native ``hash()`` recurses through nested tuples calling ``hash()``
#     on every element, so a table lookup attempted on a not-yet-proven
#     substructure would transitively hash any ``Var`` nested inside it --
#     an earlier version of this function took exactly that shortcut (a
#     "does *c* already match a previously-interned value?" pre-check
#     before walking *c*'s own structure) and was rejected on review
#     because it violated this invariant, even though it happened to be
#     safe in practice (default ``object.__hash__`` on a Var never raises,
#     and a Var-containing key can never collide with a stored ground
#     one). See the task report's "TDD" section for the full trace.
#
# ITERATIVE, NOT RECURSIVE (also load-bearing): ``_try_intern`` walks
# post-order using an explicit stack, not Python recursion. A tabled
# predicate's cons-chain grows ONE cell per subgoal, bottom-up (``Nats(K,
# cons(K, T))`` where ``T`` is subgoal ``K-1``'s already-frozen answer) --
# and ``freeze_args`` (the tabling freeze boundary this hook sits behind,
# Python fallback or C twin -- see ``clausal.logic.solve._deref_walk_py``)
# unconditionally rebuilds a brand-new nested tuple on every call, even
# for substructure that is already fully ground. So *T* arriving at
# subgoal K is always a length-(K-1) chain that must be groundness-checked
# in full (no identity or value shortcut is available before groundness
# is established -- see above), and a naive Python-recursive walk would
# recurse that many call frames deep on EVERY subsequent cell: for a long
# chain (n ~ 1500, this stage's target size) that is enough, added to the
# tabling trampoline's own already-deep call stack, to raise
# ``RecursionError`` -- hit for real during this task's own measurement
# dry run before this function was made iterative; see the task report's
# "TDD" section. An explicit Python-``list``-based stack has no such
# limit (bounded by available memory, not ``sys.getrecursionlimit()``).
#
# Net effect: checking/caching a K-deep chain costs O(K) work on every
# ``add_answer`` call (O(depth^2) total over a chain of that depth, same
# order as the O(depth^2) the walk/freeze work already costs by design at
# each level) -- slower than the (rejected) value-shortcut version, but
# correct per the ``Var.__hash__`` invariant and immune to
# ``RecursionError`` regardless of chain depth.
def intern_cell(c: Any) -> Any:
    """Recursively intern *c* bottom-up, ground cells only.

    - Not a cell at all (``is_cell(c)`` False) -> returned unchanged. Class
      terms, atoms, and every other non-cell value take this path; they
      never touch ``_INTERN_TABLE``.
    - A cell that is not fully ground (a ``Var`` reachable anywhere in its
      cell structure) -> returned unchanged, object-identical to *c*.
      Non-ground cells are never cached (their shape can still change via
      later unification), and no ``Var`` anywhere in *c* is ever hashed
      while establishing this (see the section docstring above).
    - A fully-ground cell -> its nested cell arguments are interned first
      (bottom-up), then ``(functor, *args)`` is looked up in the shared
      table; the first cell built with a given ground shape becomes the
      canonical object every structurally-equal cell thereafter collapses
      to.

    Hashing a ground cell can still raise ``TypeError`` (e.g. a ``list``
    argument -- ground but unhashable): guarded per level with try/except,
    falling back to returning that level's cell unchanged rather than
    raising or caching a bogus entry.
    """
    if not is_cell(c):
        return c
    ok, result = _try_intern(c)
    return result if ok else c


# The intern table itself: canonical-tuple -> the SAME canonical-tuple
# object (a set would do the membership check, but storing the value lets
# ``.get`` return the canonical object in one lookup).
_INTERN_TABLE: dict[tuple, tuple] = {}


def clear_intern_table() -> None:
    """Empty the intern table.

    Test isolation: the table is process-global (module-level), so a test
    that asserts identity via interning must not see another test's
    entries -- call this in setup/teardown. Also useful between benchmark
    rounds that must not let one round's interned answers keep an earlier
    round's table entries "warm."
    """
    _INTERN_TABLE.clear()


# Sentinel for "this node's subtree contains a Var" in ``_try_intern``'s
# ``result_of`` map -- distinct from every real value a cell could ever
# resolve to (never returned to a caller, never stored in
# ``_INTERN_TABLE``, so no risk of confusion with a genuine cell answer).
_NOT_GROUND = object()


def _try_intern(root: tuple) -> tuple[bool, Any]:
    """Iterative, post-order, groundness-first combined check-and-intern
    pass over cell *root*. Returns ``(True, interned_value)`` if *root* is
    fully ground (recursively) and has been looked-up/stored in
    ``_INTERN_TABLE``; ``(False, None)`` if a ``Var`` was found anywhere
    in the reachable structure -- the caller (``intern_cell``) returns
    *root* itself unchanged in that case.

    Caller has already proven ``is_cell(root)``; this function does not
    re-check that for *root* itself (only for nested args, via ``is_cell``
    below). See the section docstring above for why this walk is BOTH
    iterative (an explicit stack, not Python recursion -- avoids
    ``RecursionError`` on a long chain) and groundness-first (never
    hashes/looks-up a value until everything nested inside it has already
    been proven Var-free -- never touches ``Var.__hash__``).

    Stack entries are ``("visit", node)`` -- node's children still need
    processing before node itself can be resolved -- or ``("finish",
    node)`` -- every cell-shaped child of node already has an entry in
    ``result_of`` (real value if ground, ``_NOT_GROUND`` if not), so
    node's own result can now be computed.
    """
    result_of: dict[int, Any] = {}  # id(cell) -> interned value or _NOT_GROUND
    stack: list[tuple[str, tuple]] = [("visit", root)]
    while stack:
        action, node = stack.pop()
        node_id = id(node)
        if action == "finish":
            raw_functor = node[0]
            functor = deref(raw_functor)
            # Dead post-§1b (Task 5 review, optional courtesy note): every
            # `node` reaching this walk already passed `is_cell`, which now
            # guarantees a str/TUPLE_TAG functor -- `is_var(functor)` can
            # never be True here any more. Left in place rather than
            # removed: harmless, and removing it is out of this task's
            # scope (Task 4's interning walk, gated OFF by default).
            if is_var(functor):
                result_of[node_id] = _NOT_GROUND
                continue
            changed = functor is not raw_functor
            new_args = []
            ground = True
            for a in node[1:]:
                da = deref(a)
                if is_var(da):
                    ground = False
                    break
                if is_cell(da):
                    na = result_of.get(id(da), _NOT_GROUND)
                    if na is _NOT_GROUND:
                        ground = False
                        break
                else:
                    na = da
                if na is not a:
                    changed = True
                new_args.append(na)
            if not ground:
                result_of[node_id] = _NOT_GROUND
                continue
            candidate = node if not changed else (functor, *new_args)
            try:
                existing = _INTERN_TABLE.get(candidate)
            except TypeError:
                # Some leaf under this cell isn't hashable (e.g. a list
                # argument, ground but unhashable) -- this node is still
                # "ground" (no Var was found), so record success, but
                # with THIS level built fresh here (nested cells already
                # interned where possible) rather than cached or raising.
                result_of[node_id] = candidate
            else:
                if existing is not None:
                    result_of[node_id] = existing
                else:
                    _INTERN_TABLE[candidate] = candidate
                    result_of[node_id] = candidate
        else:  # "visit"
            if node_id in result_of:
                continue  # already resolved via an earlier stack entry
            stack.append(("finish", node))
            raw_functor = node[0]
            functor = deref(raw_functor)
            # Dead post-§1b, same reasoning as the "finish" branch above.
            if is_var(functor):
                continue  # "finish" will re-detect this cheaply and stop
            for a in node[1:]:
                da = deref(a)
                if is_var(da):
                    continue  # "finish" will re-detect this cheaply too
                if is_cell(da) and id(da) not in result_of:
                    stack.append(("visit", da))

    final = result_of.get(id(root), _NOT_GROUND)
    if final is _NOT_GROUND:
        return False, None
    return True, final


# Module-level switch gating the tabling freeze-boundary hook
# (``clausal.logic.tabling.TableEntry.add_answer``). Default OFF so the
# DEFAULT-PATH INVARIANT holds unconditionally: nothing calls
# ``set_intern_enabled(True)`` except Task 4's own tests and
# ``benchmarks/workloads.py``'s ``bench_struct_tabling_tagged(..., intern=True)``.
_INTERN_ENABLED = False


def is_intern_enabled() -> bool:
    """True if the tabling freeze-boundary hook should call ``intern_cell``
    on cell-shaped answer args. Read live (a function, not a cached
    import) so callers see toggles made after their own import."""
    return _INTERN_ENABLED


def set_intern_enabled(value: bool) -> None:
    """Flip the module-level interning switch. Test/benchmark use only --
    no production code path calls this."""
    global _INTERN_ENABLED
    _INTERN_ENABLED = bool(value)
