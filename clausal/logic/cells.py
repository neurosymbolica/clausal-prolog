"""Tagged cells: the Phase 2 bridge's plain-tuple term representation.

Spec: ``implementation_plans/tagged-tuple-term-representation.md`` (design
§1, optimisations §3c); this module is Task 1 of
``docs/superpowers/plans/2026-09-03-phase2-bridge.md``.

A *cell* is a plain Python ``tuple`` whose slot 0 identifies its shape:

  - a ``str`` functor   -> ``("point", x, y)``   a compound term ``point/2``.
  - the ``tuple`` TYPE OBJECT (``TUPLE_TAG``) -> ``(tuple, e1, e2, ...)``
    tuple-DATA, not a compound -- this is how a cell represents a bare
    Python tuple as term data without slot 0 colliding with a real user
    value (a plain data tuple's own slot 0 could be anything; tagging with
    the ``tuple`` type itself sidesteps that).
  - an unbound ``Var`` -> ``(X, a, b)``   a higher-order / not-yet-resolved
    functor slot; unifies against a same-shape cell and binds ``X`` to the
    other cell's functor (see ``tests/test_cells.py``, and the
    higher-order guard test in particular).

Nothing else may occupy slot 0 -- ``make_cell`` enforces this; ``is_cell``
recognizes it.

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

KNOWN AMBIGUITY (accepted, not solved, per the same ruling): a plain user
tuple whose slot 0 happens to be a ``str`` -- e.g. ``("hello", 1)`` meant
as ordinary tuple data, not a cell -- is indistinguishable from a cell by
shape alone. This bridge stage accepts that ambiguity rather than solving
it: ``is_cell`` answers ``True`` for such a tuple, and the funnel
accessors in ``clausal/logic/builtins/_helpers.py`` therefore treat it as
a cell too. Callers that need a real disambiguation between "cell" and
"plain tuple that happens to start with a str" must gate on something
other than shape -- a flagged module (Task 2's ``-tagged_terms``
directive), or an explicit call site -- not on ``is_cell`` alone.

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
    "TAGGED_TERMS_FLAG",
    "FUNCTOR_SIGNATURES_KEY",
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
]
# NOTE: `_cell_shape` is intentionally NOT in __all__ (internal helper) but
# IS imported directly by clausal/logic/builtins/_helpers.py -- the same
# "leading-underscore, cross-module funnel helper" convention that module
# already uses for _functor_name/_arity/etc. See _cell_shape's docstring.


# The tag used in slot 0 for a "tuple as term data" cell: ``(tuple, e1,
# ...)``. This is the ``tuple`` TYPE OBJECT itself, not the string
# ``"tuple"`` -- see ``is_cell``/``make_tuple_cell``.
TUPLE_TAG = tuple


# The module-namespace key a ``-tagged_terms`` module carries.  The directive
# (clausal/templating/term_rewriting.py, ``_handle_tagged_terms_directive``)
# compiles to a plain module-level ``__clausal_tagged_terms__ = True``
# assignment, and the compiler entrypoints
# (clausal/logic/compiler/predicate.py) read it back off the ``globals_`` they
# are handed -- which for a ``.clausal`` module IS that module's ``__dict__``.
#
# A module-namespace flag rather than a ``module_items`` entry, deliberately:
# module items are recovered separately when a module loads from its ``.pyc``
# cache, whereas an assignment is part of the cached bytecode and therefore
# cannot go missing on the cached path.
TAGGED_TERMS_FLAG = "__clausal_tagged_terms__"


# The module-namespace key holding a module's functor-signature registry:
# ``{"point": ("x", "y"), ...}``, one entry per ``(name, fields)`` the
# ``-module``/``-private`` rewrite saw -- predicates included, since the
# data/predicate split is decided by binding shape (whether a functor has
# clauses), not by anything the registry itself records.  Emitted by
# ``clausal/templating/term_rewriting.py``'s ``_handle_module_directive`` /
# ``_handle_private_directive`` as a module-level
# ``__clausal_functor_signatures__ = {...}`` assignment (accumulated via
# ``dict.update`` across multiple directives in the same file, the same
# "assignment, not a module item" reasoning as ``TAGGED_TERMS_FLAG`` above);
# ``-import_from`` copies the imported names' entries into the importer's
# dict under their LOCAL spelling.
#
# ``clausal/logic/compiler/terms_to_ast.py``'s ``functor_signature_for``
# consults this registry FIRST, falling back to a resolved class's
# ``_fields`` while generated functor classes still exist (P3-2 Task 1 of
# the cell-default-flip bridge).  Once a later task removes those classes,
# this registry becomes the sole source of truth for a functor's declared
# field names.
FUNCTOR_SIGNATURES_KEY = "__clausal_functor_signatures__"


def _valid_functor_slot(resolved_slot0: Any) -> bool:
    """True if *resolved_slot0* is a legal cell slot-0 value (the
    bridge-entry ruling).

    *resolved_slot0* must already be dereferenced by the caller (see
    ``_cell_shape`` below) -- this function does not deref, so it can be
    reused without paying for a second deref of the same value.
    """
    return isinstance(resolved_slot0, str) or resolved_slot0 is TUPLE_TAG or is_var(resolved_slot0)


def _cell_shape(x: Any) -> tuple[bool, Any]:
    """Return ``(is_cell, resolved_slot0)`` for *x*.

    Dereferences slot 0 EXACTLY ONCE (review fix, finding #1: a cell's
    slot 0 must be inspected post-deref, not raw -- a cell built with an
    unbound Var functor that has since been bound by ``unify`` must not
    vanish from cell recognition just because its functor slot resolved).
    ``is_cell`` is defined in terms of this; the funnel accessors in
    ``clausal/logic/builtins/_helpers.py`` import this directly (rather
    than calling ``is_cell`` and then re-deref'ing slot 0 themselves) so a
    single top-level accessor call never dereferences slot 0 twice.

    For an unbound Var, ``deref`` is a no-op (returns the Var itself); for
    a bound Var, it returns the walked-to value. Either way this is one
    (cheap, C-implemented) call.
    """
    if type(x) is not tuple or len(x) < 1:
        return False, None
    resolved = deref(x[0])
    return _valid_functor_slot(resolved), resolved


def make_cell(functor: Any, *args: Any) -> tuple:
    """Construct a cell ``(functor, *args)``, enforcing the slot-0 ruling.

    *functor* must be one of:

      - a ``str`` -- interned via ``sys.intern`` as a convenience (see the
        module docstring's BRIDGE-ENTRY RULING: ``is_cell`` does not
        require this, ``make_cell`` does it only to make repeated
        same-functor cells cheaper to compare/store).
      - ``TUPLE_TAG`` (the ``tuple`` type object) -- for tuple-as-data cells.
      - an unbound ``Var`` -- a higher-order / not-yet-resolved functor slot.

    Anything else (``int``, a class other than ``tuple``, ``None``, ...)
    raises ``TypeError``.
    """
    if isinstance(functor, str):
        functor = sys.intern(functor)
    elif functor is TUPLE_TAG:
        pass
    elif is_var(functor):
        pass
    else:
        raise TypeError(
            "make_cell: functor must be a str, the `tuple` type object "
            f"(TUPLE_TAG), or an unbound Var; got {functor!r} "
            f"({type(functor).__name__})"
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
    never tuple subclasses, so this cannot collide with them) whose
    DEREFERENCED slot 0 is a ``str``, the ``tuple`` type object, or an
    unbound ``Var`` -- a cell built with an unbound Var functor that has
    since been bound (by ``unify``) is still a cell, recognized by its
    slot 0's current, walked-to value (review fix, finding #1).

    This is a SHAPE-only test -- see the module docstring's KNOWN
    AMBIGUITY note: a plain user tuple like ``("hello", 1)`` also answers
    ``True`` here. That is accepted for this bridge stage, not a bug.
    """
    return _cell_shape(x)[0]


def cell_functor(c: tuple) -> Any:
    """Return the functor slot (slot 0) of cell *c*, dereferenced.

    An unbound-Var functor slot derefs to itself (returned as the Var);
    a bound one derefs to its walked-to value (review fix, finding #1).
    No shape validation -- callers that don't already know *c* is
    cell-shaped should check ``is_cell(c)`` first.
    """
    return deref(c[0])


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
