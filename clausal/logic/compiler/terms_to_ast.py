"""Term → AST expression lowering.

Converts a compile-time term value (Var, scalar, list, Compound,
functor-dataclass, KWTerm, DictTerm, SetTerm, SetLiteral, DictLiteral,
StarUnpack, TupleLiteral, Call-with-LoadName, PyThunk, …) into a
Python AST expression that, at runtime, reconstructs that term.

Also provides the small parsing helpers ``_is_star_list`` /
``_parse_star_segments`` / ``_count_stars`` (used both here for list
rewriting and by ``.star_segments`` for body-Is compilation) and
``_dotted_name_from_loadattr`` (used here and by ``.globals_env``).
Co-locating the parsing helpers with ``term_to_ast_expr`` avoids a
star_segments ↔ terms_to_ast import cycle.
"""

from __future__ import annotations

import ast
import datetime

from contextlib import contextmanager
from fractions import Fraction
from typing import Any

from clausal.logic.variables import Var, is_var, deref  # noqa: F401
from clausal.terms import (
    Compound,
    Add, Sub, Mult, Div, FloorDiv, Mod, Pow,
    Negate,
    Call, LoadName, LoadAttr, LoadSubscript,
    DictTerm, SetTerm, KWTerm, PyThunk,
    Undefined,
)
from clausal.pythonic_ast.nodes import (
    StarUnpack, TupleLiteral, DictLiteral, SetLiteral,
    Lambda, literal_value,
    SetLiteral as _SetLiteral_t,
)
from clausal.logic.predicate import (
    PredicateMeta, is_atom, is_term_instance, term_field_names,
    register_atom_identity,
)
from clausal.logic.constants import _FrozenList, _FrozenDict, _FrozenSet

from ._ast_helpers import _name, _call, _attr
from ._vars import _var_python_name


# ── Parsing helpers (used here and by .star_segments) ────────────────────────


# Reconstruction spec for the datetime value-term branch of term_to_ast_expr:
# exact type → (datetime-module constructor name, positional field order).
# datetime/time entries are used only when tzinfo is None (checked at the
# branch); timedelta is normalised by its constructor, so days/seconds/
# microseconds is exhaustive.
_DATETIME_CTOR_FIELDS = {
    datetime.date: ("date", ("year", "month", "day")),
    datetime.datetime: (
        "datetime",
        ("year", "month", "day", "hour", "minute", "second", "microsecond"),
    ),
    datetime.time: ("time", ("hour", "minute", "second", "microsecond")),
    datetime.timedelta: ("timedelta", ("days", "seconds", "microseconds")),
}


def headlit_global_key(term: Any) -> str:
    """The base_globals key under which an opaque head literal is injected.

    Keyed by ``id()`` (like ``_pyt_<id>`` for PyThunks) so the collector in
    globals_env and the guard emitter in head_match reference the SAME entry.
    The value is kept alive by the clause head, so the id is stable.
    """
    return f"$headlit_{id(term)}"


def _is_opaque_head_literal(term: Any) -> bool:
    """True for a GROUND Python value that ``head_to_match_pattern`` has no
    dedicated branch for (``datetime.date``, ``Decimal``, ``Fraction``,
    ``tuple``, ``set``/``frozenset``, ``Path``, …) and would otherwise compile
    to the accept-all wildcard fallback (A02-F003).

    Such a value is captured and unified against a ``$headlit_<id>`` global
    injected by the globals collector. Types the compiler already handles
    inline (primitives, str/bytes, and structural term nodes) return False, as
    do non-ground containers (which stay structural / keep the old wildcard).
    """
    term = deref(term)
    if is_var(term):
        return False
    # Primitives emitted as ast.Constant; str/bytes have dedicated guards.
    if term is None or isinstance(term, (bool, int, float, complex, str, bytes)):
        return False
    # Structural term types with dedicated head_to_match_pattern branches.
    if isinstance(term, (list, dict, Compound, DictTerm, SetTerm, KWTerm,
                         StarUnpack, Call, LoadName, LoadAttr,
                         TupleLiteral, DictLiteral, SetLiteral)):
        return False
    if is_term_instance(term):
        return False
    if isinstance(term, type) and isinstance(term, PredicateMeta):
        return False
    # Ground containers with a nested unbound Var stay structural (a captured
    # literal can't bind the inner Var) — keep the degraded wildcard for them.
    if isinstance(term, (tuple, set, frozenset)):
        return all(not is_var(deref(e)) for e in term)
    return True


class PredicateAsTermError(Exception):
    """A predicate (arity ≥ 1) was used where a term value was expected.

    Overwhelmingly this is the atom/predicate name clash: a bare name in
    *data* position — most often a dict key, ``{query_date: 5}`` — that is
    also the name of a predicate in the same module resolves to the
    **predicate class**, which is not a term value.

    A predicate object is neither identical nor equal to the same-named atom,
    so accepting it here would replace a load-time crash with a dict whose key
    can never be read back — exactly the silent-mismatch class of bug this
    module's ``atom_identity_expr`` exists to prevent.  It stays an error;
    only the diagnostic is improved.
    """

    def __init__(self, pred: Any) -> None:
        self.pred = pred
        name = getattr(pred, "__name__", repr(pred))
        arity = len(getattr(pred, "_fields", ()) or ())
        super().__init__(
            f"{name}/{arity} is a predicate, not a term value: the bare name "
            f"'{name}' in data position resolves to the predicate defined in "
            f"this module, not to a same-named atom. If an atom was meant "
            f"(e.g. as a dict key), name it unambiguously: use the qualified "
            f"form of the module that owns it (owner.{name}), or use a string "
            f"key (\"{name}\"), or rename one of the two. A predicate object "
            f"is not equal to the atom of the same name, so it cannot be used "
            f"as a key."
        )


# Depth counter for ``atom_identity_lowering()`` (a plain int is enough — the
# compiler is single-threaded and reentrancy is handled by the counter).
_ATOM_IDENTITY_DEPTH = 0


@contextmanager
def atom_identity_lowering():
    """Lower 0-arity atoms BY IDENTITY inside this block.

    An atom is a class, so the natural lowering is a bare ``Name`` resolved, at
    run time, in the compiled function's globals.  For a clause compiled from a
    module's own source that is right (and one ``LOAD_GLOBAL`` rather than a
    call): the atom came from that very namespace, so the name is guaranteed to
    resolve back to the same object.

    It is *wrong* for a term the compiler received as a live OBJECT from
    somewhere else.  The query compiler bakes the arguments of
    ``solve(m.pred(profile, …))`` into a query template whose globals are the
    **callee's** module namespace.  A ``DictTerm`` key that is an atom was then
    re-looked-up there by name — and under the snake_case convention that name
    is very often bound to a same-named *predicate*, so the template silently
    substituted that other object as the key and every read missed: ``get/3``
    failed, ``get/4`` returned the default, ``P[key]`` raised a bogus
    ``existence_error``.  Where the name was simply unbound it was a raw
    ``NameError`` inside ``<template>``.

    Inside this block such atoms lower to ``$atom(<token>)`` instead, which
    resolves the registered object itself — giving atom keys the same immunity
    string keys have always had from lowering to ``ast.Constant``.

    See ``todo/query-template-rebinds-atom-dict-keys.md`` and
    ``implementation_plans/dict-atom-keys-vs-predicates.md`` (option 2).
    """
    global _ATOM_IDENTITY_DEPTH
    _ATOM_IDENTITY_DEPTH += 1
    try:
        yield
    finally:
        _ATOM_IDENTITY_DEPTH -= 1


def atom_identity_expr(term: Any) -> ast.expr | None:
    """Return the by-identity lowering of *term*, or None to lower normally.

    None means either "not an atom" or "not inside
    :func:`atom_identity_lowering`" — both fall back to the bare-Name lowering.
    """
    if _ATOM_IDENTITY_DEPTH and is_atom(term):
        return _call(
            _name("$atom"),
            ast.Constant(value=register_atom_identity(term)),
        )
    return None


# ── ``-tagged_terms``: the Phase 2 bridge's per-module cell lowering ─────────
#
# EXPERIMENTAL.  A module carrying the ``-tagged_terms`` directive compiles
# saturated constructions of the functors it declares to CELL literals --
# ``("point", x, y)`` -- instead of ``point(...)`` / ``point._clausal_new(...)``
# class instances.  See ``clausal/logic/cells.py`` and the directive's
# docstring in ``clausal/templating/term_rewriting.py``.
#
# The flag reaches this module the same way ``atom_identity_lowering`` does:
# a module-level stack rather than a new parameter on ``term_to_ast_expr``,
# which has 56 call sites across the compiler and one signature every one of
# them would have to grow.  The stack holds the flagged module's namespace so
# the emission gate can resolve a functor NAME to the class it names; a
# ``compile_predicate_*`` entrypoint pushes exactly one entry for the duration
# of one predicate's compilation.
#
# The stack is SEALING, not merely settable: an UNFLAGGED compile pushes
# ``None``, it does not push nothing.  Only the TOP entry is ever consulted, so
# a compile that targets an unflagged namespace cannot inherit a flagged scope
# an outer compile happens to have left open and start emitting cells into a
# module that never asked for them.  No path reaches that nesting today, which
# is exactly why it has to be structural rather than a convention -- see
# ``TestGateSymmetry.test_an_unflagged_compile_inside_a_flagged_scope_emits_no_cells``.
_TAGGED_TERMS_STACK: "list[dict | None]" = []


@contextmanager
def tagged_terms_lowering(module_globals: "dict | None"):
    """Scope the cell lowering for the duration of one predicate's compile.

    *module_globals* is the flagged module's namespace — the same dict the
    compile entrypoint received as ``globals_`` — used to resolve a functor
    name to the class it refers to, and to answer "does this functor belong to
    the flagged module?".

    ``None`` opens an explicitly UNFLAGGED scope: the block emits no cells even
    if an outer block left a flagged scope open.  Both
    :func:`clausal.logic.compiler.predicate.compile_predicate_trampoline` and
    ``compile_predicate_shallow`` always enter this manager — with the
    namespace when it carries :data:`clausal.logic.cells.TAGGED_TERMS_FLAG`,
    with ``None`` when it does not — so "unflagged" is a state the stack
    records, never merely the absence of one.
    """
    _TAGGED_TERMS_STACK.append(module_globals)
    try:
        yield
    finally:
        _TAGGED_TERMS_STACK.pop()


def tagged_terms_globals() -> "dict | None":
    """The flagged module's namespace, or None outside a flagged compile.

    Reads only the TOP of the stack: an unflagged compile nested inside a
    flagged one answers ``None``, because it pushed ``None``.
    """
    return _TAGGED_TERMS_STACK[-1] if _TAGGED_TERMS_STACK else None


def _is_cell_functor_class(cls: Any) -> bool:
    """True if *cls* is a DATA functor whose instances lower to cells.

    A data functor is a :class:`PredicateMeta` class with at least one field
    and NO clauses: the module declared it (``-module`` export list,
    ``-private``, or first use) purely to build terms with.  A class that has
    clauses is a predicate — calling it is a goal, and ``call/1`` and friends
    dispatch on the class — so its instances keep class emission even in a
    flagged module.

    Arity 0 is excluded: a 0-arity reference is an ATOM and stays the class
    object itself (Phase 3 does the atom pivot, not this bridge).

    A ``-dynamic`` declaration also disqualifies: the ISO declare-then-assertz
    pattern leaves a predicate clause-free at compile time and fills it in
    later, so "no clauses" alone would misread it as data and compile its
    references to cells that the clauses asserted afterwards could never
    match.  ``_dynamic_arities`` is ``None`` on every class the compiler did
    not stamp, so ordinary data functors are unaffected.

    So does a ``_position`` / ``position`` field.  ``term_to_ast_expr``'s
    keyword slow path DROPS those fields when it constructs a term instance,
    and a positional cell cannot reproduce a dropped field — the two
    representations of such a functor are not interchangeable.  The exclusion
    lives HERE, in the gate that both :func:`cell_functor_for_name` and
    :func:`cell_functor_for_instance` go through, rather than at one emission
    site: a check applied to construction but not to matching (or to instances
    but not to source references) yields a clause that builds one shape and
    matches another — one that can never fire.  Whatever the answer is for a
    given functor, every site has to give the same one.
    """
    return (
        isinstance(cls, type)
        and isinstance(cls, PredicateMeta)
        and bool(getattr(cls, "_fields", ()))
        and not getattr(cls, "_clauses", None)
        and not getattr(cls, "_dynamic_arities", None)
        and not any(
            name in ("_position", "position")
            for name in getattr(cls, "_fields", ())
        )
    )


def cell_functor_for_name(name: str, arity: int,
                          resolve_globals: "dict | None" = None) -> "str | None":
    """Resolve *name* to a cell functor for a saturated *arity* construction.

    Returns the functor string to put in slot 0, or None when the reference
    must keep class emission — no flagged scope is open, the name does not
    resolve, resolves to something that is not a data functor, is not
    saturated at *arity*, or belongs to another module (compound data does not
    cross the flag boundary; see the directive docstring).

    *resolve_globals* is the namespace to look *name* up in.  Call sites that
    have one pass it, so the name resolves against the SAME dict the
    class-emission branch beside it uses — in ``head_match`` that is
    ``_resolve_loadname(name, globals_)``, and a cell branch resolving
    somewhere else could disagree with its own fallback about what ``name``
    means.  When omitted, the flagged module's own namespace is used.  Either
    way the OWNERSHIP question is answered against the flagged scope, the only
    namespace that can say what "this module" is.

    A dotted name (``other.Wrap``) always returns None: it is by definition
    another module's functor.
    """
    scope = tagged_terms_globals()
    if scope is None or "." in name:
        return None
    namespace = resolve_globals if resolve_globals is not None else scope
    cls = namespace.get(name)
    if not _is_cell_functor_class(cls):
        return None
    if len(cls._fields) != arity:
        return None
    # Own-module gate: the flagged module's ``__name__`` must be the class's
    # defining module.  An imported functor keeps class emission so that data
    # built here still matches the owner's clause heads.
    owner = getattr(cls, "__module__", None)
    here = scope.get("__name__")
    if owner is not None and here is not None and owner != here:
        return None
    return cls.__name__


def cell_functor_for_instance(term: Any) -> "str | None":
    """Resolve a live term INSTANCE to its cell functor, or None.

    Same gates as :func:`cell_functor_for_name` — including the
    ``_position``/``position`` exclusion both inherit from
    :func:`_is_cell_functor_class` — applied to ``type(term)``.  No name
    resolution is involved: the class is the term's own type.
    """
    scope = tagged_terms_globals()
    if scope is None:
        return None
    cls = type(term)
    if not _is_cell_functor_class(cls):
        return None
    owner = getattr(cls, "__module__", None)
    here = scope.get("__name__")
    if owner is not None and here is not None and owner != here:
        return None
    return cls.__name__


def cell_literal_ast(functor: str, arg_exprs: list[ast.expr]) -> ast.Tuple:
    """The cell literal ``("functor", <arg0>, ...)`` as an AST expression."""
    return ast.Tuple(
        elts=[ast.Constant(value=functor), *arg_exprs],
        ctx=ast.Load(),
    )


def _is_star_list(term: Any) -> bool:
    """Return True if term is a list containing at least one StarUnpack."""
    return isinstance(term, list) and any(isinstance(e, StarUnpack) for e in term)


def _parse_star_segments(lst: list) -> list[tuple]:
    """Parse a list with StarUnpack(s) into segments.

    Returns a list of ("fixed", [elem, ...]) or ("star", var) tuples.
    """
    segments: list[tuple] = []
    fixed_buf: list = []
    for elem in lst:
        if isinstance(elem, StarUnpack):
            if fixed_buf:
                segments.append(("fixed", fixed_buf))
                fixed_buf = []
            segments.append(("star", elem.value))
        else:
            fixed_buf.append(elem)
    if fixed_buf:
        segments.append(("fixed", fixed_buf))
    return segments


def _count_stars(segments: list[tuple]) -> int:
    return sum(1 for kind, _ in segments if kind == "star")


def _dotted_name_from_loadattr(node) -> str | None:
    """Extract a dotted name string from a LoadAttr chain.

    ``LoadAttr(object=LoadName("graphs"), attr="Path")`` → ``"graphs.Path"``
    ``LoadAttr(object=LoadAttr(..., "sub"), attr="Pred")`` → ``"mod.sub.Pred"``
    ``LoadName("foo")`` → ``"foo"``

    Returns None if the chain contains non-name nodes.
    """
    if isinstance(node, LoadName):
        return node.name
    if isinstance(node, LoadAttr):
        prefix = _dotted_name_from_loadattr(node.object)
        if prefix is not None:
            return f"{prefix}.{node.attr}"
    return None


# ── Term → AST expression ──────────────────────────────────────────────────────


def term_to_ast_expr(
    term: Any, var_context: dict[int, str], *, eval_arith: bool = True
) -> ast.expr:
    """Convert a term value to a Python AST expression.

    The generated expression evaluates at runtime to the term.
    Vars already in var_context are referenced by name.  Vars not yet in
    var_context (body-only Vars) are introduced via walrus ``(_vN := Var())``.

    when *eval_arith* is True (the default), arithmetic term nodes
    (Add, Sub, …) are compiled to native Python operators so they evaluate
    at runtime.  when False, they are kept as structural term constructors
    (e.g. ``Add(left=x, right=1)``).

    Supports: Var, Python scalars, list, Compound, functor dataclasses.
    """
    raw = term
    term = deref(term)

    if is_var(term):
        vid = term._id
        if vid in var_context:
            return _name(var_context[vid])
        # Body-only Var: introduce via walrus assignment
        vname = _var_python_name(term)
        var_context[vid] = vname
        return ast.NamedExpr(
            target=ast.Name(id=vname, ctx=ast.Store()),
            value=_call(_name("Var")),
        )

    if isinstance(term, LoadName):
        return _name(term.name)

    # Bare (non-Call) LoadAttr in value position: a module-qualified atom used
    # as a VALUE, e.g. ``currency.euro`` on the RHS of a unify or as a call
    # argument.  Lower it to the equivalent Python attribute access so the
    # ``-import_module``'d module object (present in the compiled function's
    # globals) yields its exported atom at runtime.  Without this the term falls
    # through to the generic term-instance constructor below and is re-emitted as
    # a ``LoadAttr(...)`` reflection node, which never unifies with the atom.
    # Mirrors the qualified-call path (``Call`` + ``LoadAttr`` further down).
    if isinstance(term, LoadAttr):
        dotted = _dotted_name_from_loadattr(term)
        if dotted is not None:
            parts = dotted.split(".")
            expr: ast.expr = _name(parts[0])
            for attr in parts[1:]:
                expr = ast.Attribute(value=expr, attr=attr, ctx=ast.Load())
            return expr

    # Subscript read ``P[K]`` in value position (e.g. the RHS of ``V is P[K]``).
    # Lower to the ``$subscript`` runtime helper, which derefs both operands,
    # reads the DictTerm value, and throws a catchable error on a missing or
    # non-ground key.  See clausal/logic/runtime/dict_ops.py and
    # todo/dict-native-profile-api.md (item 1).
    if isinstance(term, LoadSubscript):
        return _call(
            _name("$subscript"),
            term_to_ast_expr(term.object, var_context, eval_arith=eval_arith),
            term_to_ast_expr(term.index, var_context, eval_arith=eval_arith),
        )

    term = literal_value(term)
    if term is None or isinstance(term, bool):
        return ast.Constant(value=term)

    # The Kleene ``Undefined`` builtin singleton: emit a bare ``Name`` reference
    # (like a zero-arity PredicateMeta atom below), since ``Undefined`` is an
    # injected builtin present in every compiled predicate's globals.  This
    # keeps its process-wide identity through query/clause compilation.
    if term is Undefined:
        return _name("Undefined")

    if isinstance(term, (int, float, str, bytes, complex)):
        return ast.Constant(value=term)

    # datetime values: first-class value terms (immutable, hashable, unify by
    # value; ``Date/4`` produces them and ``DaysBetween``/``DateAdd`` consume
    # them). A DIRECT query arg never reaches here — ``_templatize_query_goal``
    # parameterizes it — but a NESTED occurrence (inside a list/compound arg)
    # is lowered structurally and needs a reconstruction. Emitted through
    # ``__import__`` so the generated code depends on no namespace entry.
    # Exact types only, and only tz-naive datetime/time: a subclass or an
    # arbitrary tzinfo carries state the base constructor cannot rebuild, so
    # those keep the honest fallthrough below. NOT arithmetic: ``==`` on a
    # date stays unification, never a CLP constraint.
    if type(term) in _DATETIME_CTOR_FIELDS and getattr(term, "tzinfo", None) is None:
        ctor, fields = _DATETIME_CTOR_FIELDS[type(term)]
        # ``fold`` is not part of datetime equality, so unification would
        # succeed without it — but the bound object must be what the caller
        # passed, matching the by-reference direct-arg path.
        keywords = []
        if getattr(term, "fold", 0):
            keywords.append(ast.keyword(arg="fold", value=ast.Constant(value=1)))
        return ast.Call(
            func=ast.Attribute(
                value=ast.Call(
                    func=_name("__import__"),
                    args=[ast.Constant(value="datetime")],
                    keywords=[],
                ),
                attr=ctor,
                ctx=ast.Load(),
            ),
            args=[ast.Constant(value=getattr(term, f)) for f in fields],
            keywords=keywords,
        )

    if isinstance(term, StarUnpack):
        return ast.Starred(
            value=term_to_ast_expr(term.value, var_context, eval_arith=eval_arith),
            ctx=ast.Load(),
        )

    if isinstance(term, TupleLiteral):
        _rec = lambda t: term_to_ast_expr(t, var_context, eval_arith=eval_arith)
        return ast.Tuple(
            elts=[_rec(e) for e in term.elements],
            ctx=ast.Load(),
        )

    if isinstance(term, tuple):
        # An already-materialized Python tuple (e.g. a structured
        # -constants RHS, which builds a real tuple directly rather than
        # the uninstantiated TupleLiteral node an ordinary clause body's
        # ``(a, b)`` literal produces — see the docstring on
        # EmbedTransformer._transform_constant_rhs). Same recursive
        # reconstruction as the TupleLiteral branch just above.
        _rec = lambda t: term_to_ast_expr(t, var_context, eval_arith=eval_arith)
        return ast.Tuple(
            elts=[_rec(e) for e in term],
            ctx=ast.Load(),
        )

    if isinstance(term, list):
        # If the list contains a StarUnpack, use _build_star_list/_build_multi_star_list
        # helper to safely handle unbound Vars at runtime.
        _rec = lambda t: term_to_ast_expr(t, var_context, eval_arith=eval_arith)
        # A -constants list value is frozen (_FrozenList — see
        # clausal.logic.constants._freeze). The RECONSTRUCTION a compiled
        # clause builds from it must be frozen too, not just the original:
        # under tabling/answer-caching, a reconstructed answer can be
        # shared across multiple consumers, where a plain mutable list
        # would let one consumer's mutation corrupt what every other
        # consumer of the same cached answer sees. A _FrozenList never
        # holds a StarUnpack (constants are always fully ground), so this
        # only needs to guard the plain-list return path below.
        is_frozen_list = isinstance(term, _FrozenList)
        star_count = sum(1 for e in term if isinstance(e, StarUnpack))
        if star_count == 1:
            # Single-star: use _build_star_list(before, star, after)
            star_idx = next(i for i, e in enumerate(term) if isinstance(e, StarUnpack))
            before = term[:star_idx]
            star_val = term[star_idx].value
            after = term[star_idx + 1:]
            return ast.Call(
                func=_name("$build_star_list"),
                args=[
                    ast.List(
                        elts=[_rec(e) for e in before],
                        ctx=ast.Load(),
                    ),
                    _rec(star_val),
                    ast.List(
                        elts=[_rec(e) for e in after],
                        ctx=ast.Load(),
                    ),
                ],
                keywords=[],
            )
        elif star_count > 1:
            # Multi-star: build segments list and call _build_multi_star_list
            segments = _parse_star_segments(term)
            seg_elts = []
            for kind, val in segments:
                if kind == "star":
                    seg_elts.append(ast.Tuple(
                        elts=[ast.Constant(value="star"), _rec(val)],
                        ctx=ast.Load(),
                    ))
                else:
                    seg_elts.append(ast.Tuple(
                        elts=[
                            ast.Constant(value="fixed"),
                            ast.List(elts=[_rec(e) for e in val], ctx=ast.Load()),
                        ],
                        ctx=ast.Load(),
                    ))
            return ast.Call(
                func=_name("$build_multi_star_list"),
                args=[ast.List(elts=seg_elts, ctx=ast.Load())],
                keywords=[],
            )
        list_ast_ = ast.List(
            elts=[_rec(e) for e in term],
            ctx=ast.Load(),
        )
        if is_frozen_list:
            return _call(_name("$FrozenList"), list_ast_)
        return list_ast_

    if isinstance(term, dict):
        dict_ast_ = ast.Dict(
            keys=[term_to_ast_expr(k, var_context, eval_arith=eval_arith) for k in term.keys()],
            values=[term_to_ast_expr(v, var_context, eval_arith=eval_arith) for v in term.values()],
        )
        # An already-materialized raw dict (e.g. a ++()-escape-built
        # -constants value that never went through DictTerm) — frozen the
        # same way a list is; see the _FrozenList branch's comment above.
        if isinstance(term, _FrozenDict):
            return _call(_name("$FrozenDict"), dict_ast_)
        return dict_ast_


    if isinstance(term, DictTerm):
        # A logic-variable key ({K: V}) must be dereferenced at construction
        # time, exactly as in the DictLiteral lowering below: emitted bare, the
        # frame var keys the rebuilt dict as the Var object and every later
        # get(OUT, <value>, _) misses silently.  $dict_key derefs (and raises a
        # catchable instantiation_error on a never-bound key).
        #
        # Atom keys/values need no special handling here: under
        # ``atom_identity_lowering()`` — which the query compiler holds open
        # while lowering caller-supplied terms — the recursive call below emits
        # an atom by identity, so a key atom cannot be re-resolved onto a
        # same-named binding of the namespace the generated code runs in.
        def _dictterm_key(k):
            expr = term_to_ast_expr(k, var_context, eval_arith=eval_arith)
            return _call(_name("$dict_key"), expr) if is_var(k) else expr
        dict_arg = ast.Dict(
            keys=[_dictterm_key(k) for k in term.keys()],
            values=[term_to_ast_expr(v, var_context, eval_arith=eval_arith) for v in term.values()],
        )
        # A -constants DictTerm value has a frozen backing store (see
        # clausal.logic.constants._freeze's DictTerm branch). The
        # RECONSTRUCTION a compiled clause builds each time it runs must be
        # frozen too — see the _FrozenList branch's comment above for why
        # (tabling/answer-caching can share a reconstructed answer across
        # consumers). Plain ``DictTerm(...)`` can't produce that directly —
        # its constructor takes a defensive ``dict(data)`` copy — so this
        # routes through ``$FrozenDictTerm`` (clausal.logic.constants.
        # _freeze_dict_term), which patches ``._data`` after construction.
        if isinstance(term.data, _FrozenDict):
            return _call(_name("$FrozenDictTerm"), dict_arg)
        return _call(_name("DictTerm"), dict_arg)

    if isinstance(term, SetTerm):
        # Recurse per element (mirrors the SetLiteral branch just below):
        # a bare ``ast.Constant(value=e)`` is only valid when every element
        # is a Python-literal-embeddable scalar. A SetTerm built from a
        # structured -constants RHS (``_FLAGS_ = {red, green}``) can hold
        # atom instances (PredicateMeta 0-arity classes) or other term
        # types, which ``ast.Constant`` rejects at compile() time — those
        # need the same Name-reference/constructor-call treatment any other
        # term position gets.
        _rec = lambda t: term_to_ast_expr(t, var_context, eval_arith=eval_arith)
        return _call(
            _name("SetTerm"),
            ast.List(
                elts=[_rec(e) for e in sorted(term.elements, key=repr)],
                ctx=ast.Load(),
            ),
        )

    if isinstance(term, (set, frozenset)):
        # A raw Python set (e.g. a ++()-escape-built -constants value —
        # a SOURCE-level {...} set literal always lowers to SetTerm above,
        # never a raw set). ``frozenset`` values are returned unwrapped by
        # ``_freeze`` (already immutable/hashable), so they reconstruct as
        # a bare ``frozenset(...)`` call; a mutable-set-derived value is a
        # ``_FrozenSet`` (frozen — see the _FrozenList branch's comment
        # above for why the RECONSTRUCTION must be frozen too) and
        # reconstructs via ``$FrozenSet``. Sorted by repr for deterministic
        # codegen, same as the SetTerm branch above.
        _rec = lambda t: term_to_ast_expr(t, var_context, eval_arith=eval_arith)
        elts = [_rec(e) for e in sorted(term, key=repr)]
        ctor = "$FrozenSet" if isinstance(term, _FrozenSet) else "frozenset"
        return _call(_name(ctor), ast.List(elts=elts, ctx=ast.Load()))

    # SetLiteral (AST node from visit_Set): emit SetTerm([elem, ...]) constructor
    if isinstance(term, _SetLiteral_t):
        return _call(
            _name("SetTerm"),
            ast.List(
                elts=[term_to_ast_expr(e, var_context, eval_arith=eval_arith) for e in term.elements],
                ctx=ast.Load(),
            ),
        )

    if isinstance(term, DictLiteral):
        _rec = lambda t: term_to_ast_expr(t, var_context, eval_arith=eval_arith)
        # A computed key that is a logic VARIABLE must be dereferenced at
        # runtime: a key bound in the same clause frame as the literal
        # (``{K: V}`` / ``{**OLD, K: V}``) otherwise reaches dict construction
        # as the Var object, keying the dict by the variable rather than its
        # value.  $dict_key derefs (and errors on an unbound key).  Literal
        # keys are already ground, so they are emitted unwrapped.
        _key = lambda k: (
            _call(_name("$dict_key"), _rec(k)) if is_var(k) else _rec(k)
        )
        has_splat = any(k is None for k in term.keys)
        if not has_splat:
            # No splats: plain dict used as DictTerm constructor argument.
            return ast.Dict(
                keys=[_key(k) for k in term.keys],
                values=[_rec(v) for v in term.values],
            )
        # Splat dict sugar: {**OLD, k: v} → DictTerm({**deref(OLD).data, k: v})
        # Splat values are DictTerms; access .data to get the underlying dict.
        py_keys = []
        py_vals = []
        for k, v in zip(term.keys, term.values):
            if k is None:
                py_keys.append(None)
                # Splat source: {**OLD, ...} → {**$splat_data(OLD), ...}.
                # $splat_data derefs and validates OLD is a dict, raising a
                # catchable typed error on an unbound/non-dict source rather
                # than a raw AttributeError on ``.data``.
                py_vals.append(_call(_name("$splat_data"), _rec(v)))
            else:
                py_keys.append(_key(k))
                py_vals.append(_rec(v))
        return _call(
            _name("DictTerm"),
            ast.Dict(keys=py_keys, values=py_vals),
        )

    if isinstance(term, SetLiteral):
        _rec = lambda t: term_to_ast_expr(t, var_context, eval_arith=eval_arith)
        return ast.Set(elts=[_rec(e) for e in term.elements])

    if isinstance(term, Compound):
        f = term.functor
        f_expr: ast.expr
        if is_var(f):
            vid = f._id
            f_expr = _name(var_context[vid]) if vid in var_context else _call(_name("Var"))
        else:
            f_expr = ast.Constant(value=f)
        args_elts = [term_to_ast_expr(a, var_context, eval_arith=eval_arith) for a in term.args]
        return _call(
            _name("Compound"),
            f_expr,
            ast.Tuple(elts=args_elts, ctx=ast.Load()),
        )

    # Arithmetic term nodes: when eval_arith is set, generate native Python
    # operators so they evaluate at runtime.  when False (e.g. predicate call
    # arguments), keep them as structural term constructors.
    if eval_arith and isinstance(term, (Add, Sub, Mult, Div, FloorDiv, Mod, Pow, Negate)):
        return arith_to_ast_expr(term, var_context)

    # Call nodes with LoadName/LoadAttr func: compile as direct function call so
    # that e.g. phrase(count_leaves(T_), ...) constructs a count_leaves instance,
    # not a Call AST node.  LoadAttr handles qualified calls like mod.Pred(X_).
    if isinstance(term, Call) and isinstance(term.func, (LoadName, LoadAttr)):
        if isinstance(term.func, LoadName):
            fname = term.func.name
        else:
            fname = _dotted_name_from_loadattr(term.func)
        arg_exprs = [
            term_to_ast_expr(a, var_context, eval_arith=eval_arith)
            for a in term.args
        ]
        kw_exprs = [
            ast.keyword(
                arg=kw.name,
                value=term_to_ast_expr(kw.value, var_context, eval_arith=eval_arith),
            )
            for kw in (term.kwargs or [])
        ]
        # ``-tagged_terms``: a SATURATED, keyword-free construction of a
        # functor this flagged module declares becomes a cell literal.  This
        # is the branch that matters for ``.clausal`` source — a compound
        # written in a clause (``cons(N, T)``) reaches the compiler as
        # ``Call(LoadName('cons'), …)``, not as a live instance.  Keyword or
        # partial construction falls through to the class call below: a cell
        # is positional and total, with no field names to attach and no
        # Var-backfill for the fields left out.
        if not kw_exprs:
            _cell_f = cell_functor_for_name(fname, len(arg_exprs))
            if _cell_f is not None:
                return cell_literal_ast(_cell_f, arg_exprs)
        return ast.Call(
            func=_name(fname),
            args=arg_exprs,
            keywords=kw_exprs,
        )

    # Zero-arity PredicateMeta class: the class IS the atom value.
    # Emit a bare Name reference so the compiled code loads the class directly
    # — except under ``atom_identity_lowering()`` (query templates), where the
    # name would be re-resolved in a foreign namespace.  See that helper.
    if is_atom(term):
        return atom_identity_expr(term) or _name(term.__name__)

    if is_term_instance(term):
        cls = type(term)
        cls_name = cls.__name__
        fields = term_field_names(term)
        # ``-tagged_terms``: a live instance of a functor this flagged module
        # declares lowers to a cell literal, matching what the module's own
        # source-level constructions compile to (the ``Call(LoadName)`` branch
        # above).  The reachable producer of such an instance is the query
        # compiler, whose template globals ARE the callee module's namespace
        # — so a query argument built as ``m.point(1, 2)`` still meets the
        # flagged module's cells.
        #
        # The scope check comes FIRST (one list-index test outside a flagged
        # compile, ahead of any per-field work).  The ``_position``/
        # ``position`` exclusion that used to sit here now lives in
        # ``_is_cell_functor_class``, so ``head_match``'s pattern branch
        # inherits the same answer — see that gate's docstring.
        _cell_f = cell_functor_for_instance(term)
        if _cell_f is not None:
            return cell_literal_ast(
                _cell_f,
                [
                    term_to_ast_expr(
                        getattr(term, name), var_context,
                        eval_arith=eval_arith,
                    )
                    for name in fields
                ],
            )
        if (
            isinstance(cls, PredicateMeta)
            and isinstance(vars(cls).get("_clausal_new"), classmethod)
            and not any(name in ("_position", "position") for name in fields)
        ):
            # Saturated, no position field, generated fast constructor
            # available: emit a positional call to it instead of the
            # keyword-based slow-path constructor call below.  Gate on
            # ``vars(cls).get("_clausal_new")`` actually BEING the generated
            # classmethod, not merely present by that name — a class whose
            # FIELD is literally named "_clausal_new" also has an entry at
            # that key (the __slots__ member descriptor; see the attach guard
            # in predicate.py), and calling that descriptor as a constructor
            # raises a TypeError at runtime.
            #
            # This positional emission is order-dependent on ``fields`` for
            # whichever class ``cls_name`` resolves to at call time; it is
            # solve.py's ``_collect_types_from_term`` update-after-module-dict
            # that keeps query templates resolving to the caller's actual
            # class rather than a stale one.
            #
            # Cross-ref: this gate is DELIBERATELY narrower than the walk/copy
            # rebuilders' Phase 0 gate (see solve.py's _deref_walk_py) — the
            # extra ``"_position"``/``"position"`` exclusion above is required
            # here because the slow path just below drops those fields from
            # the emitted kwargs entirely, whereas the walkers' slow path
            # keeps all fields. Do not "unify" the two gates by deleting this
            # condition.
            return _call(
                _attr(cls_name, "_clausal_new"),
                *[
                    term_to_ast_expr(
                        getattr(term, name), var_context, eval_arith=eval_arith,
                    )
                    for name in fields
                ],
            )
        return ast.Call(
            func=_name(cls_name),
            args=[],
            keywords=[
                ast.keyword(
                    arg=name,
                    value=term_to_ast_expr(
                        getattr(term, name), var_context, eval_arith=eval_arith,
                    ),
                )
                for name in fields
                if name not in ("_position", "position")
            ],
        )

    # KWTerm: generate KWTerm("functor", key=val, ...)
    if isinstance(term, KWTerm):
        keywords = [
            ast.keyword(arg=k, value=term_to_ast_expr(v, var_context, eval_arith=eval_arith))
            for k, v in term.items()
        ]
        return ast.Call(
            func=_name("KWTerm"),
            args=[ast.Constant(value=term.functor)],
            keywords=keywords,
        )

    # PyThunk: deferred Python expression via lambda wrapper.
    # Used for f-strings in .clausal files and ++() Python escapes.
    # The thunk stores a callable (lambda) and a list of Var objects.
    # The compiler emits: thunk.fn(deref(local0), deref(local1), ...)
    if isinstance(term, PyThunk):
        # Reference to the thunk's .fn stored in compiled function globals.
        # Use a unique name to avoid collisions.
        thunk_name = f"_pyt_{id(term)}"
        arg_exprs = []
        for var_obj in term.var_objects:
            vid = var_obj._id
            if vid in var_context:
                arg_exprs.append(_call(_name("$deref"), _name(var_context[vid])))
            else:
                # Body-only var — allocate and deref
                vname = _var_python_name(var_obj)
                var_context[vid] = vname
                arg_exprs.append(_call(
                    _name("$deref"),
                    ast.NamedExpr(
                        target=ast.Name(id=vname, ctx=ast.Store()),
                        value=_call(_name("Var")),
                    ),
                ))
        return ast.Call(
            func=_name(thunk_name),
            args=arg_exprs,
            keywords=[],
        )

    if isinstance(term, Lambda):
        raise NotImplementedError(
            "Lambdas are currently only supported as predicate call arguments"
        )

    # A predicate CLASS (arity ≥ 1 — the zero-arity/atom case returned above)
    # in term position.  Almost always the atom/predicate name clash.
    if isinstance(term, PredicateMeta):
        raise PredicateAsTermError(term)

    # A live BOUND Var whose value has no literal lowering (e.g. a
    # ``datetime.date`` produced by an earlier goal): reference the Var itself
    # so runtime deref yields the value.  ``isinstance``, not ``is_var`` —
    # is_var() derefs and is False for bound Vars.  Only possible when the Var
    # was registered up front (the query compiler collects bound Vars with
    # ``_collect_vars(goal, include_bound=True)``); an unregistered one keeps
    # the honest NotImplementedError below rather than fabricating a fresh
    # (unbound!) Var, which would silently change goal semantics.
    if isinstance(raw, Var) and raw._id in var_context:
        return _name(var_context[raw._id])

    # `...` REIFIES (render inverts reify, so reflection must keep modelling
    # it — TestPlainConstants pins the round-trip) but has no evaluation rule
    # in a goal; without this branch it fell through to the internal
    # NotImplementedError below, with no source line.  The clause-position
    # scope stack the compiler maintains (Slice G5) locates it at the owning
    # clause.
    if term is Ellipsis:
        from ._ast_helpers import _current_position
        msg = ("`...` (Ellipsis) is not supported in a clause body: it is "
               "inert term structure with no evaluation rule. Remove it.")
        pos = _current_position()
        if isinstance(pos, tuple) and pos and isinstance(pos[0], int):
            raise SyntaxError(msg, (None, pos[0], None, None))
        raise SyntaxError(msg)

    raise NotImplementedError(
        f"term_to_ast_expr: unsupported term type {type(term).__name__}: {term!r}"
    )


# ── Arithmetic term → AST expression ──────────────────────────────────────────

_ARITH_BINOP_MAP: list[tuple[type, ast.operator]] = [
    (Add,      ast.Add()),
    (Sub,      ast.Sub()),
    (Mult,     ast.Mult()),
    (Div,      ast.Div()),
    (FloorDiv, ast.FloorDiv()),
    (Mod,      ast.Mod()),
    (Pow,      ast.Pow()),
]


def arith_to_ast_expr(term: Any, var_context: dict[int, str]) -> ast.expr:
    """Convert an arithmetic term to a Python arithmetic AST expression.

    Generates code that evaluates the expression to a Python number at runtime.
    Vars are dereferenced.  Arithmetic binary operators are unboxed to native
    Python ``ast.BinOp`` nodes.
    """
    term = deref(term)

    if is_var(term):
        vid = term._id
        vname = var_context.get(vid, _var_python_name(term))
        return _call(_name("$deref"), _name(vname))

    term = literal_value(term)
    if isinstance(term, (int, float, Fraction)) and not isinstance(term, bool):
        return ast.Constant(value=term)

    # int / int → Fraction(n, d) for exact rational arithmetic
    if isinstance(term, Div):
        left_t = deref(term.left)
        right_t = deref(term.right)
        if (isinstance(left_t, int) and not isinstance(left_t, bool)
                and isinstance(right_t, int) and not isinstance(right_t, bool)):
            return ast.Call(
                func=_name("$Fraction"),
                args=[ast.Constant(value=left_t), ast.Constant(value=right_t)],
                keywords=[],
            )

    if isinstance(term, Negate):
        return ast.UnaryOp(
            op=ast.USub(),
            operand=arith_to_ast_expr(term.operand, var_context),
        )

    for cls, ast_op in _ARITH_BINOP_MAP:
        if isinstance(term, cls):
            return ast.BinOp(
                left=arith_to_ast_expr(term.left, var_context),
                op=ast_op,
                right=arith_to_ast_expr(term.right, var_context),
            )

    # Fallback: treat as a plain term (e.g. a Var holding a number at runtime)
    return term_to_ast_expr(term, var_context)
