"""``-meta_predicate(p(1, ?))``: module-qualify a meta-argument at the call.

Operator ruling 2026-09-25 (ruling 1, "follow Scryer").  Ruling S makes a
predicate name passed as data the PLAIN atom, so a higher-order predicate in
another module used to look that atom up in ITS OWN module.  Scryer's answer
is the meta_predicate declaration: at a call of a declared predicate, every
argument whose spec is ``:`` or a non-negative integer is qualified with the
CALLER's module (``M:G``) unless it is already qualified; ``?``/``+``/``-``
arguments are untouched.  Scryer's ``loader.pl``::

    qualified_spec((:)).
    qualified_spec(MS) :- integer(MS), MS >= 0.

    expand_module_name(ESG0, MS, M, ESG) :-
        (  var(ESG0) -> ( M == user -> ESG = ESG0 ; ESG = M:ESG0 )
        ;  ESG0 = _:_ -> ESG = ESG0
        ;  ... built_in ... -> ESG = ESG0
        ;  ESG = M:ESG0 ).

and its ``setup_meta_predicate`` (``src/machine/preprocessor.rs``) accepts
exactly ``+``, ``-``, ``?``, ``:`` and integers ``0..MAX_ARITY`` -- ``^``
and ``//`` are an ``InvalidMetaPredicateDecl`` there, so they are refused
here too.

The qualified goal is the runtime cell ``(":", M, G)`` -- the spelling
``call/N``'s qualified arm, ``solve`` and ``resolve_qualified_goal_cell``
already resolve -- so it reaches maplist & co., phrase and time_goal inside
the callee through the existing qualified-goal path.

Where it happens: at the CALL SITE.  A compiled body call whose callee the
compiler resolves (``terms_to_goalop``'s ``SubCall``) wraps each qualifying
argument in :class:`MetaArg`, which lowers to ``$meta_qualify($meta_db, A)``:
the decision is static, the wrapping is at run time (the argument may be a
variable bound to an already-qualified goal, which Scryer also leaves
alone).  ``call/N`` (``higher_order._resolve_named_goal``) and the Python
``solve.call`` entry qualify when THEY resolve a declared predicate, with the
module they resolved it in -- Scryer's ``expand_call_goal``.
"""
from __future__ import annotations

import functools
import sys
import types
from typing import Any

from clausal.logic.variables import deref

QUALIFIED = ":"

#: The spec atoms Scryer accepts besides integers.
DATA_SPECS = frozenset({"+", "-", "?"})


def is_qualifying_spec(spec: Any) -> bool:
    """Scryer's ``qualified_spec/1``: ``:`` or an integer >= 0."""
    return spec == QUALIFIED or (type(spec) is int and spec >= 0)


def valid_spec(spec: Any) -> bool:
    return spec in DATA_SPECS or is_qualifying_spec(spec)


def module_designator(db: Any) -> Any:
    """The designator a qualification written in *db*'s module carries: the
    module's NAME (an atom, as Scryer writes ``M:G``) when that name resolves
    back to this very module, else the ``Module`` object itself -- which
    ``resolve_module`` accepts too, so a module the ``.clausal`` runner popped
    from ``sys.modules`` still resolves."""
    md = getattr(db, "module_dict", None)
    module = md.get("$module") if isinstance(md, dict) else None
    if module is None:
        return None
    name = getattr(module, "name", None)
    if isinstance(name, str):
        found = sys.modules.get(name)
        if found is module or getattr(found, "__clausal_module__", None) is module:
            return name
    return module


def _is_predicate_handle(v: Any, db: Any = None) -> bool:
    """A predicate HANDLE names its module inside the atom.  A ``-hide``
    DATA atom is mangled the same way but names no predicate: it is
    qualified like any other atom.  *db* is the calling database, the
    ruling-Q0 hint so a handle naming a module popped from ``sys.modules``
    still resolves (roborev 2026-09-25)."""
    from clausal.logic.atoms import is_mangled  # noqa: PLC0415
    from clausal.logic.predicate import is_declared_predicate_name  # noqa: PLC0415
    return (type(v) is str and is_mangled(v)
            and is_declared_predicate_name(v, db=db))


def _already_qualified(value: Any, db: Any = None) -> bool:
    v = deref(value)
    if type(v) is tuple and len(v) == 3 and v[0] == QUALIFIED:
        return True
    return _is_predicate_handle(v, db)


_FUNCTION_KINDS = (types.FunctionType, types.MethodType, functools.partial)


def is_goal_object(value: Any) -> bool:
    """THE test for a goal OBJECT -- a goal that is not a NAME (atom or
    cell) and resolves itself: anything answering ``_get_dispatch`` (a
    predicate class, a ``BuiltinPredicate``, the ``_UnqualifiedName`` /
    ``call_body.MetaCallGoal`` adapters) or a plain Python function (a Python-written
    closure, a compiled Clausal lambda).  Dereferenced first.

    Deliberately NOT ``callable()``: a unit ``Quantity`` (``byte(4)``), a
    Python type, a pythonic-AST node and any other object with ``__call__``
    are not goals, and must not skip a goal position's qualification.

    Shared by ``$meta_qualify`` (a goal object in a GOAL position is not
    wrapped), ``higher_order._resolve_named_goal`` and ``dcg`` (``M:Obj``
    dispatches the object)."""
    v = deref(value)
    if type(v) is str or type(v) is tuple:
        return False
    return hasattr(v, "_get_dispatch") or isinstance(v, _FUNCTION_KINDS)


def qualify(designator: Any, value: Any, spec: Any = 0, db: Any = None) -> Any:
    """``M:Value`` unless *value* is already qualified, or there is no
    module.  A goal OBJECT in a GOAL position (an integer spec) is left as
    it is -- it resolves itself; a ``:`` position is module-sensitive DATA
    and is ALWAYS qualified, as Scryer hands it over (``cd:[X]>>true`` for
    a yall lambda, verified on the box).

    A predicate HANDLE in a ``:`` position is spelled Scryer's ``M:X``
    with the handle's OWNER as ``M`` and the PLAIN name as ``X`` (operator
    ruling 2026-09-25, per the always-plain ruling: data never carries a
    mangled name) -- ``cells.qualify_mangled_goal``'s spelling, whose
    designator is ``predicate.handle_designator``'s.  A CELL whose functor
    is a handle, ``(handle, X, ...)``, is ``(":", <owner>, (plain, X,
    ...))`` the same way (coordinator relay of the standing rulings,
    2026-09-25).  In a GOAL (integer) position a handle is a goal object
    that already resolves to its owner, and is passed as it is."""
    if spec == QUALIFIED and designator is not None:
        v = deref(value)
        if _is_predicate_handle(v, db) or (
                type(v) is tuple and v and _is_predicate_handle(v[0], db)):
            from clausal.logic.cells import qualify_mangled_goal  # noqa: PLC0415
            return qualify_mangled_goal(v, db)
    if designator is None or _already_qualified(value, db):
        return value
    if type(spec) is int and is_goal_object(value):
        return value
    return (QUALIFIED, designator, value)


def qualify_in_db(db: Any, value: Any, spec: Any = 0) -> Any:
    """``$meta_qualify``: the compiled call site's runtime half."""
    return qualify(module_designator(db), value, spec, db)


def qualify_args(specs: "tuple | None", args: list, db: Any) -> list:
    """*args* with every qualifying-spec position qualified with *db*'s
    module; *args* itself when there is nothing to do."""
    if not specs or len(specs) != len(args):
        return args
    designator = module_designator(db)
    if designator is None:
        return args
    return [qualify(designator, a, s, db) if is_qualifying_spec(s) else a
            for s, a in zip(specs, args)]


def meta_specs_for_call(db: Any, fname: str, arity: int) -> "tuple | None":
    """The ``-meta_predicate`` specs of the callee a compiled body call
    ``fname(...)`` at *arity* reaches from *db*'s module, or ``None``.

    The row first (a local predicate, or an import's adopted row under the
    local name).  Then the DOTTED spelling: ``-import_from`` rewrites every
    reference to an imported predicate into the exporter's ``pkg.mod.p``,
    which is a module-dict key, not a Database key -- resolved to the
    binding's own row exactly as ``arg_index.hint_row`` does.  A dotted call
    the author wrote as such is indistinguishable here, so it too is
    qualified with the CALLING module (Scryer would qualify ``m:p(G)``'s G
    with ``m``); recorded in the ruling's report.
    """
    lookup = getattr(db, "meta_predicate_specs", None)
    if lookup is None:
        # A db-like SHIM -- ``globals_env._GlobalsDb``, which the db-less
        # compile path (``compile_predicate(..., db=None)``, the
        # ``make_predicate`` hand-built-globals recipe) sets as ``ctx.db`` --
        # implements only ``signature_for`` and records no declarations.
        return None
    specs = lookup(fname, arity)
    if specs is not None or "." not in fname:
        return specs
    md = getattr(db, "module_dict", None)
    if not isinstance(md, dict) or fname not in md:
        return None
    from clausal.logic.predicate import resolve_predicate_row  # noqa: PLC0415
    row = resolve_predicate_row(md[fname], arity=arity, db=db)
    if row is None or row.key[1] != arity:
        return None
    return row.db._meta_specs.get(row.key)


class MetaArg:
    """Compiler IR marker: a call argument in a qualifying meta position.
    ``term_to_ast_expr`` lowers it to
    ``$meta_qualify($meta_db, <value>, <spec>)``.  The child is ``.value`` so
    the compiler's generic single-child walkers (``_vars._collect_var_ids``)
    see the variables inside; ``.spec`` is the position's spec (an int, or
    ``":"``), which decides whether a goal object is exempt."""
    __slots__ = ("value", "spec")

    def __init__(self, value: Any, spec: Any = 0) -> None:
        self.value = value
        self.spec = spec

    def __repr__(self) -> str:
        return f"MetaArg({self.value!r}, {self.spec!r})"
