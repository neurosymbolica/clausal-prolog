"""Registry infrastructure for builtin predicates.

Provides the decorator-based registration system, the adapters
(BuiltinPredicate, BuiltinTerm), and the public lookup API.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable

from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.logic.predicate import (
    is_term_instance, term_field_names,
    _dispatch_at, is_declared_predicate_name,
)
from clausal.logic.trampoline import DONE, StepGenerator
from clausal.terms import DictTerm, SetTerm


# ── Simple → trampoline adapter ──────────────────────────────────────────────


def _simple_to_trampoline(simple_fn):
    """Wrap a simple-mode dispatch function as a trampoline-protocol function.

    Simple-mode signature:  ``fn(*args, trail, k)`` → yields ``None``
    Trampoline signature:   ``fn(this_gen, parent, *args, trail)`` → yields ``(parent, None)`` / ``(parent, DONE)``
    """
    def trampoline_fn(this_generator, _proceed, _fail, _catcher, *args):
        # args = (*pred_args, trail)  — trail is always last
        for _ in simple_fn(*args, None):
            yield (_proceed, None)
        yield (_fail, DONE)
    return trampoline_fn


def _wrap_db_factory(factory):
    """Wrap a DB-builtin factory so its product is trampoline-protocol."""
    def wrapped_factory(db):
        simple_fn = factory(db)
        return _simple_to_trampoline(simple_fn)
    return wrapped_factory


# ── Registry dicts ─────────────────────────────────────────────────────────────
# _BUILTINS: trampoline-protocol dispatch functions  {(functor, arity) → fn}
# _DB_BUILTINS: factory callables  {(functor, arity) → fn(db) → trampoline dispatch_fn}

_BUILTINS: dict[tuple[str, int], Callable] = {}
_DB_BUILTINS: dict[tuple[str, int], Callable] = {}
_BUILTIN_FIELDS: dict[tuple[str, int], tuple[str, ...]] = {}


def _stateless_dispatch(functor: str, arity: int) -> "Callable | None":
    """The dispatch function for ``(functor, arity)`` on a path with NO db.

    ``_BUILTINS`` entries are db-free by construction and answer directly. A
    ``_DB_BUILTINS`` factory normally cannot (``assertz`` without a database is
    not a working assertz, and the caller is better off with the
    ``NotImplementedError`` than with a closure that raises ``AttributeError``
    on first use), so it answers ``None`` — unless the factory carries
    ``_db_optional``, which says the factory produces a correct, if reduced,
    dispatch for ``db=None``.

    Two families set that flag today:

    - ``call_goal``/``call`` (P3-3 Task 5), which became db-receiving only to
      resolve a cell/atom goal NAME against the caller's database. Everything
      it did before — invoking a goal OBJECT — needs no db at all, so
      ``factory(None)`` is its pre-Task-5 self, and the db-less paths (the
      ``_BUILTIN_CLASSES`` table, a ``BuiltinPredicate`` built without a db)
      keep working exactly as they did.
    - ``listing`` (P3-3 Task 8), which became db-receiving to resolve a bare
      str atom or a ``Name/Arity`` indicator against the caller's database.
      Its other three argument shapes (a ``PredicateMeta`` class or instance,
      a ``BuiltinPredicate``) need no db at all, so ``factory(None)`` is its
      pre-Task-8 self and the same db-less paths keep working — see
      ``clausal/logic/builtins/io.py``'s ``_db_optional`` comment, which is
      LOAD-BEARING there: ``_build_all_builtin_classes()`` calls this very
      function at import time to populate ``_BUILTIN_CLASSES["listing"]``.
    """
    fn = _BUILTINS.get((functor, arity))
    if fn is not None:
        return fn
    factory = _DB_BUILTINS.get((functor, arity))
    if factory is not None and getattr(factory, "_db_optional", False):
        return factory(None)
    return None


def _extract_fields_simple(fn: Callable) -> tuple[str, ...]:
    """Extract field names from a simple-mode builtin (strip trail, k)."""
    params = list(inspect.signature(fn).parameters)
    return tuple(params[:-2])  # drop trail, k


def _extract_fields_trampoline(fn: Callable) -> tuple[str, ...]:
    """Extract field names from a trampoline builtin.

    Strips ``this_generator`` + three continuation slots (``_proceed`` /
    ``_fail`` / ``_catcher``) from the front and ``trail`` from the back.
    """
    params = list(inspect.signature(fn).parameters)
    return tuple(params[4:-1])  # drop this_generator, _proceed, _fail, _catcher, and trail


def _builtin(functor: str, arity: int, *, fields: tuple[str, ...] | None = None):
    """Decorator: register a function as a stateless built-in (auto-wrapped to trampoline)."""
    def decorator(fn: Callable) -> Callable:
        _BUILTINS[(functor, arity)] = _simple_to_trampoline(fn)
        _BUILTIN_FIELDS[(functor, arity)] = fields or _extract_fields_simple(fn)
        return fn
    return decorator


def _trampoline_builtin(functor: str, arity: int, *, fields: tuple[str, ...] | None = None):
    """Decorator: register a native trampoline-protocol built-in (no wrapping).

    Use for builtins that operate on lists or call sub-goals, so they
    participate directly in the trampoline without an extra wrapper layer.

    signature: ``fn(this_generator, parent, arg0, …, argN-1, trail)``
    Must yield ``(parent, None)`` per solution and ``(parent, DONE)`` at end.
    """
    def decorator(fn: Callable) -> Callable:
        _BUILTINS[(functor, arity)] = fn
        _BUILTIN_FIELDS[(functor, arity)] = fields or _extract_fields_trampoline(fn)
        return fn
    return decorator


def _ensure_trampoline_dispatch(goal_val, arity: int | None = None, db=None):
    """Return a trampoline-protocol dispatch function for *goal_val*.

    Handles:
    - PredicateMeta / BuiltinPredicate with ``_get_dispatch()`` → returns that
    - Simple-mode callable ``fn(*args, trail, k)`` → wraps to trampoline

    *arity* is how many arguments the caller will supply.  Passing it lets a
    ``PredicateMeta`` callee refuse a goal it has no clause for, so
    ``call(citation, REF, META)`` reports the arity the way writing
    ``citation(REF, META)`` in a clause body does.  Callers that do not know
    the count (or whose count is not the callee's) omit it, and ``None`` is
    also what a foreign single-argument implementor gets — see ``_dispatch_at``.

    *db* is the caller's database, the ruling-Q0 hint for a predicate HANDLE
    (passed to ``is_declared_predicate_name`` and ``_dispatch_at``).
    """
    if hasattr(goal_val, '_get_dispatch'):
        if arity is None:
            return goal_val._get_dispatch()
        return _dispatch_at(goal_val, arity, db)
    if is_declared_predicate_name(goal_val, db=db):
        # W4b-3: a module-qualified predicate HANDLE (what a predicate name
        # is bound to after the flip).  A handle carries no arity of its own,
        # so it cannot be resolved without the caller's count -- refuse
        # loudly rather than fall through to wrapping a str as a simple-mode
        # callable.
        if arity is None:
            raise TypeError(
                f"_ensure_trampoline_dispatch: a predicate handle "
                f"({goal_val!r}) needs the call arity")
        return _dispatch_at(goal_val, arity, db)
    from clausal.logic.builtins.call_body import (  # noqa: PLC0415
        needs_meta_call, MetaCallGoal,
    )
    if needs_meta_call(goal_val, db):
        # Anything that is not already a runnable goal OBJECT -- a cell, a
        # plain atom, an unbound Var, a body node, a number, a list ... --
        # runs AS call/N (operator rule 2026-09-25, ISO first: the WG17
        # prologue defines maplist & co. via call/N), so each element answers
        # exactly what call/N answers.  Before the Node check below: a body
        # node is ``call(X > 0, 1)`` -- existence_error (>)/3, as call/N says.
        return MetaCallGoal(goal_val, db)._get_dispatch()
    # A Pythonic AST node (Predicate, Lambda, …) is
    # ``callable`` — every node gets a field-replacement ``__call__`` from
    # @node_class — but it is NOT a goal dispatch function.  This is reached
    # when a non-goal term is passed to call_goal/maplist/foldl/etc., e.g. a
    # ``Head <- Body`` arrow that degraded to a Predicate rule literal because
    # a head name was not a logic variable (logic vars are ALL-CAPS or
    # ``_leading`` — ``St`` is NOT one).  Surface a proper ISO type_error
    # instead of letting the node's keyword-only ``__call__`` blow up with a
    # raw Python TypeError.
    from clausal.pythonic_ast.nodes import Node
    if isinstance(goal_val, Node):
        from clausal.logic.exceptions import LogicException, type_error
        # The culprit must be a proper *ground term* so the resulting error
        # term round-trips through unification / copy_term — a raw AST node does
        # not (it breaks catch/3 pattern matching).  Use its string form.
        raise LogicException(type_error(
            "callable", str(goal_val),
            f"not a callable goal — got a {type(goal_val).__name__} term; "
            f"an anonymous predicate (lambda) needs logic-variable head names "
            f"(ALL-CAPS like X, or _leading)",
        ))
    info = getattr(goal_val, "__clausal_lambda__", None)
    if info is not None:
        return _lambda_to_trampoline(goal_val, info)
    # Assume simple-mode callable
    return _simple_to_trampoline(goal_val)


def _lambda_arity_error(info, n_args: int):
    """The error for a lambda ``(P1, ..., Pn) <- Body`` called with *n_args*
    arguments, n_args != n (library(lambda) in Scryer is the model):

    * too MANY: call/N adds the surplus to the body goal, so the error is
      ``existence_error(procedure, Name/(Arity + surplus))`` for the body's
      principal goal (``maplist(\\S^(S > 0), [1, 2], _)`` in Scryer is
      existence_error ``(>)/3``);
    * too FEW: ``existence_error(lambda_parameter, Lambda)``, as Scryer's
      ``call(\\X^Y^true, 1)``."""
    from clausal.logic.builtins.call_body import folded_existence_error  # noqa: PLC0415
    from clausal.logic.exceptions import LogicException, existence_error  # noqa: PLC0415
    n_params, name, arity, text = info
    if n_args > n_params and name is not None:
        return LogicException(folded_existence_error(
            name, arity + n_args - n_params, f"call/{n_args + 1}"))
    return LogicException(existence_error(
        "lambda_parameter", text,
        f"call/{n_args + 1}: the lambda takes {n_params} argument(s), "
        f"called with {n_args}"))


def _lambda_to_trampoline(fn, info):
    """:func:`_simple_to_trampoline` for a compiled lambda, refusing a call
    with the wrong number of arguments by an ISO error term (it used to be
    Python's ``TypeError: takes 3 positional arguments but 4 were given``)."""
    n_params = info[0]
    def trampoline_fn(this_generator, _proceed, _fail, _catcher, *args):
        # args = (*pred_args, trail)  -- trail is always last
        if len(args) - 1 != n_params:
            raise _lambda_arity_error(info, len(args) - 1)
        for _ in fn(*args, None):
            yield (_proceed, None)
        yield (_fail, DONE)
    return trampoline_fn


def _db_builtin(functor: str, arity: int, *, fields: tuple[str, ...] | None = None,
                db_optional: bool = False):
    """Decorator: register a factory as a db-dependent built-in (auto-wrapped to trampoline).

    ``db_optional`` marks the builtin as answering correctly, if in reduced
    form, for ``db=None`` -- see ``_stateless_dispatch``.  It has to be set
    HERE rather than on the factory: ``_stateless_dispatch`` reads the flag
    off the object stored in ``_DB_BUILTINS``, which is the wrapper, and a
    decorator cannot see an attribute the decorated function has not been
    given yet.  Until this parameter existed, no ``@_db_builtin`` could be
    db-optional at all -- only the hand-registered families could.
    """
    def decorator(factory: Callable) -> Callable:
        wrapped = _wrap_db_factory(factory)
        if db_optional:
            wrapped._db_optional = True
        _DB_BUILTINS[(functor, arity)] = wrapped
        if fields is not None:
            _BUILTIN_FIELDS[(functor, arity)] = fields
        else:
            _BUILTIN_FIELDS[(functor, arity)] = tuple(f"arg{i}" for i in range(arity))
        return factory
    return decorator


# ── structural_unify ──────────────────────────────────────────────────────────


def structural_unify(t1: Any, t2: Any, trail: Any) -> bool:
    """Python-level structural unification that handles dataclasses.

    The C extension's ``unify`` handles Var, tuple, list, and atomic equality.
    This wrapper adds recursive unification for dataclass
    terms (WK-6 cross-representation unification).
    """
    t1 = deref(t1)
    t2 = deref(t2)

    # If either is unbound Var, delegate to the C unify (it handles Var binding).
    if is_var(t1) or is_var(t2):
        return bool(unify(t1, t2, trail))

    # Both are ground (or at least non-Var at the top level).
    # list ↔ list
    if isinstance(t1, list) and isinstance(t2, list):
        if len(t1) != len(t2):
            return False
        mark = trail.mark()
        for e1, e2 in zip(t1, t2):
            if not structural_unify(e1, e2, trail):
                trail.undo(mark)
                return False
        return True

    # term instance ↔ term instance (same type)
    if (
        is_term_instance(t1)
        and is_term_instance(t2)
        and type(t1) is type(t2)
    ):
        fields = term_field_names(t1)
        mark = trail.mark()
        for name in fields:
            if not structural_unify(getattr(t1, name), getattr(t2, name), trail):
                trail.undo(mark)
                return False
        return True

    # DictTerm ↔ DictTerm (same key set, values unify pairwise)
    if isinstance(t1, DictTerm) and isinstance(t2, DictTerm):
        if t1.keys() != t2.keys():
            return False
        mark = trail.mark()
        for key in t1.keys():
            if not structural_unify(t1[key], t2[key], trail):
                trail.undo(mark)
                return False
        return True

    # SetTerm ↔ SetTerm (same elements — elements must be ground)
    if isinstance(t1, SetTerm) and isinstance(t2, SetTerm):
        return t1.elements == t2.elements

    # Fall back to C unify for all other combinations (atoms, tuples, etc.)
    return bool(unify(t1, t2, trail))


# ── BuiltinPredicate adapter ─────────────────────────────────────────────────


class BuiltinPredicate:
    """Adapter wrapping a builtin dispatch function with the ``_get_dispatch()``
    protocol used by PredicateMeta classes.

    Stateless builtins store the dispatch function directly.  DB-dependent
    builtins (assertz, retract, etc.) store the factory; ``_get_dispatch()``
    calls the factory lazily on first use.

    Multi-arity support: when a predicate name has multiple arities (e.g.
    Match/2 and Match/3), ``_merge`` combines them into one adapter with
    an arity-dispatching ``_get_dispatch()`` that selects at call time.
    """
    # ``_dispatch_fn`` here is NOT row state and the P3-3 mutation gate does
    # not apply to it: a builtin has no ``PredRow`` (nothing in the tree calls
    # ``db.row`` for one), so there is no row to transact against and nothing
    # to clobber — it is this adapter's own memo of the factory's product.
    # Deliberate stop for a future gate-bypass sweep: not an ungated write.
    __slots__ = ("_functor", "_arity", "_dispatch_fn", "_factory", "_db",
                 "_arity_map")

    def __init__(
        self,
        functor: str,
        arity: int,
        dispatch_fn: Callable | None = None,
        factory: Callable | None = None,
        db: Any = None,
    ) -> None:
        self._functor = functor
        self._arity = arity
        self._dispatch_fn = dispatch_fn
        self._factory = factory
        self._db = db
        self._arity_map: dict[int, Callable] | None = None

    def _get_dispatch(self) -> Callable:
        if self._arity_map is not None:
            return self._arity_dispatch
        if self._dispatch_fn is None:
            if self._factory is not None and self._db is not None:
                self._dispatch_fn = self._factory(self._db)
            else:
                # No db: a ``_db_optional`` factory still answers (P3-3 Task
                # 5) — see ``_stateless_dispatch``.
                self._dispatch_fn = _stateless_dispatch(
                    self._functor, self._arity)
            if self._dispatch_fn is None:
                raise NotImplementedError(
                    f"Builtin {self._functor}/{self._arity} has no dispatch function"
                )
        return self._dispatch_fn

    def _arity_dispatch(self, this_generator, _proceed, _fail, _catcher, *args):
        """Dispatch to the correct arity handler based on arg count.

        Trampoline protocol: args = (*pred_args, trail).
        Arity = len(args) - 1.
        """
        arity = len(args) - 1  # exclude trail
        fn = self._arity_map.get(arity)
        if fn is None:
            from clausal.logic.trampoline import DONE as _DONE
            yield (_fail, _DONE)
            return
        yield from fn(this_generator, _proceed, _fail, _catcher, *args)

    def _merge(self, other: "BuiltinPredicate") -> None:
        """Merge another BuiltinPredicate into this one for multi-arity dispatch."""
        if self._arity_map is None:
            self._arity_map = {}
            # Add our own arity to the map.
            if self._dispatch_fn is not None:
                self._arity_map[self._arity] = self._dispatch_fn
            else:
                fn = (self._factory(self._db)
                      if self._factory is not None and self._db is not None
                      else _stateless_dispatch(self._functor, self._arity))
                if fn is not None:
                    self._arity_map[self._arity] = fn
        if other._dispatch_fn is not None:
            self._arity_map[other._arity] = other._dispatch_fn
        else:
            fn = (other._factory(other._db)
                  if other._factory is not None and other._db is not None
                  else _stateless_dispatch(other._functor, other._arity))
            if fn is not None:
                self._arity_map[other._arity] = fn

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Construct this builtin's TERM -- the adapter's other role.

        A name in a compiled template stands for two things at once: the
        DISPATCH (``_dispatch_at(name, n)``) and the term CONSTRUCTOR, used
        when a goal appears as an argument to a meta-predicate --
        ``time_goal(listing(append))`` builds a ``listing`` term and then
        drives it.  The stateless path binds the ``_BUILTIN_CLASSES`` entry,
        which is callable and does both; a db-dependent builtin binds THIS
        adapter instead, because it is the only thing carrying the database,
        and until now it could not be called at all -- every db-dependent
        builtin in argument position raised "'BuiltinPredicate' object is
        not callable".  Construction routes to the same class the stateless
        path would have bound, so both spellings build the same term.
        """
        cls = _BUILTIN_CLASSES.get(self._functor)
        if cls is None:
            raise TypeError(
                f"builtin {self._functor}/{self._arity} has no term class to "
                f"construct -- it can be called as a goal but not built as a term"
            )
        return cls(*args, **kwargs)

    def __repr__(self) -> str:
        if self._arity_map:
            arities = sorted(self._arity_map)
            return f"BuiltinPredicate({self._functor!r}/{arities})"
        return f"BuiltinPredicate({self._functor!r}/{self._arity})"


# ── Public lookup API ─────────────────────────────────────────────────────────


def get_builtin_predicate(
    functor: str, arity: int, db: Any = None
) -> BuiltinPredicate | None:
    """Return a ``BuiltinPredicate`` adapter for the given functor/arity, or None.

    For stateless builtins the same singleton is returned on every call.
    For DB-dependent builtins a new adapter is created with the given ``db``.
    """
    key = (functor, arity)
    fn = _BUILTINS.get(key)
    if fn is not None:
        return BuiltinPredicate(functor, arity, dispatch_fn=fn)
    factory = _DB_BUILTINS.get(key)
    if factory is not None:
        return BuiltinPredicate(functor, arity, factory=factory, db=db)
    return None


def get_builtin_dispatch(
    functor: str, arity: int, db: Any
) -> Callable | None:
    """Return the dispatch function for a built-in predicate, or None.

    Called by ``Database.get_dispatch`` when a predicate is not found locally.
    """
    key = (functor, arity)
    fn = _BUILTINS.get(key)
    if fn is not None:
        return fn
    factory = _DB_BUILTINS.get(key)
    if factory is not None:
        return factory(db)
    return None


# ── BuiltinTerm: a builtin's module-level object ──────────────────────────────


class BuiltinTerm:
    """A builtin's module-level object (``clausal.between``,
    ``_BUILTIN_CLASSES["between"]``): a TERM constructor and a goal object.
    NOT a class (W4b-3 slice 3: the ``PredicateMeta`` builtin classes, and
    the ``MultiArityBuiltin`` wrapper over them, are retired).

    * Called, it builds the CELL -- ``clausal.between(1, 3, X)`` is
      ``("between", 1, 3, X)``, exactly what ``--between(1, 3, X)`` builds
      in a ``.clausal`` module.  At a REGISTERED arity (the argument count,
      positional plus keyword) the arguments are placed by
      :func:`build_term_cell` against that arity's field names.  At any
      other count it builds the cell at the WRITTEN arity, never padded
      to a registered one (operator ruling 2026-09-25: no implicit arity
      padding anywhere; a default argument is an explicit predicate):
      ``between(1, 2)`` is ``("between", 1, 2)``, which as a goal is
      ``existence_error(procedure, between/2)``, and ``between()`` is the
      atom.  Keywords name the slots of a registered arity, so keywords at
      a count no arity has are refused
      (:class:`ClausalTermConstructionError`) -- there is no written-arity
      cell they could name.  A 0-arity builtin's call is its atom
      (``clausal.nl()`` is ``'nl'``); the class era handed back the class.
    * As a goal it speaks the frozen duck-typed ``_get_dispatch()``
      protocol, so ``_dispatch_at`` and ``_ensure_trampoline_dispatch``
      answer it through their GENERIC arm: the one arity's dispatch
      function, or -- for a name registered at several arities -- a
      dispatcher keyed on the argument count at call time, which fails for
      an unregistered count.  That is what the class answered (its
      arity refusal never fired: a builtin class's private row holds no
      clauses and no declaration) and what ``MultiArityBuiltin`` answered.
      A builtin with no db-free dispatch (``_stateless_dispatch`` is
      ``None``) raises the class's ``NotImplementedError``.
    """
    __slots__ = ("_functor", "_fields_by_arity", "_dispatch_by_arity",
                 "_multi_dispatch")

    def __init__(self, functor: str) -> None:
        self._functor = functor
        self._fields_by_arity: dict[int, tuple[str, ...]] = {}
        self._dispatch_by_arity: dict[int, Callable] = {}
        self._multi_dispatch = None

    def _add(self, arity: int, fields: tuple[str, ...],
             dispatch_fn: "Callable | None") -> None:
        self._fields_by_arity[arity] = tuple(fields)
        if dispatch_fn is not None:
            self._dispatch_by_arity[arity] = dispatch_fn

    @property
    def arities(self) -> tuple[int, ...]:
        return tuple(sorted(self._fields_by_arity))

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        written = len(args) + len(kwargs)
        fields = self._fields_by_arity.get(written)
        if fields is None:
            if kwargs:
                raise self._keyword_arity_error(args, kwargs)
            # The WRITTEN arity (no padding): ``between(1, 2)`` is between/2.
            return (self._functor, *args) if args else self._functor
        if not fields:
            return self._functor
        from clausal.logic.predicate import build_term_cell  # noqa: PLC0415
        return build_term_cell(self._functor, fields, args, kwargs)

    def _keyword_arity_error(self, args: tuple, kwargs: dict):
        from clausal.logic.predicate import (  # noqa: PLC0415
            ClausalTermConstructionError, _source_site,
        )
        functor = self._functor
        written = len(args) + len(kwargs)
        known = ", ".join(f"{functor}/{a}" for a in self.arities)
        names = ", ".join(kwargs)
        message = (
            f"builtin {functor} was written with {written} argument(s), "
            f"field names ({names}), but it is registered only at {known}: "
            f"field names place the arguments of a registered arity, and a "
            f"construction is never padded to one (operator ruling "
            f"2026-09-25).  Supply every field of the arity you mean, or "
            f"build the {functor}/{written} cell positionally.")
        widest = self._fields_by_arity[max(self._fields_by_arity)]
        return ClausalTermConstructionError(
            message, functor=functor, arity=written,
            supplied_fields=tuple(kwargs), registered_fields=widest,
            registered_at=None, constructed_at=_source_site(3))

    def _get_dispatch(self) -> Callable:
        fba = self._fields_by_arity
        if len(fba) == 1:
            (arity,) = fba
            fn = self._dispatch_by_arity.get(arity)
            if fn is None:
                raise NotImplementedError(
                    f"Predicate {self._functor}/{arity} has no compiled "
                    "dispatch function. The compiler must be run first.")
            return fn
        if self._multi_dispatch is None:
            fns = self._dispatch_by_arity

            def _dispatch(this_generator, _proceed, _fail, _catcher, *args):
                fn = fns.get(len(args) - 1)  # exclude trail
                if fn is None:
                    yield (_fail, DONE)
                    return
                yield from fn(this_generator, _proceed, _fail, _catcher,
                              *args)

            self._multi_dispatch = _dispatch
        return self._multi_dispatch

    def __repr__(self) -> str:
        arities = self.arities
        spelled = (str(arities[0]) if len(arities) == 1
                   else str(list(arities)))
        return f"<builtin {self._functor}/{spelled}>"


# The name ``MultiArityBuiltin`` stays importable: it is exported from
# ``clausal.logic.builtins``.  Every builtin object is one ``BuiltinTerm``
# now, whatever its arity count.
MultiArityBuiltin = BuiltinTerm


# Populated by _build_all_builtin_classes() at module load time.  The name is
# historical (the values were PredicateMeta classes until W4b-3 slice 3).
# Maps functor name -> its BuiltinTerm.
_BUILTIN_CLASSES: dict[str, BuiltinTerm] = {}


def _build_all_builtin_classes() -> None:
    """Build one :class:`BuiltinTerm` per registered builtin NAME, holding
    each of its arities' field names and db-free dispatch.  Called once at
    module load."""
    all_keys: dict[str, list[int]] = {}
    for functor, arity in list(_BUILTIN_FIELDS):
        all_keys.setdefault(functor, []).append(arity)
    for functor, arities in all_keys.items():
        obj = BuiltinTerm(functor)
        for arity in sorted(arities):
            obj._add(arity, _BUILTIN_FIELDS[(functor, arity)],
                     _stateless_dispatch(functor, arity))
        _BUILTIN_CLASSES[functor] = obj


def get_builtin_class(functor: str) -> "BuiltinTerm | None":
    """Return the builtin's :class:`BuiltinTerm` (its term constructor and
    goal object), or None.  (Named for the class it returned until W4b-3
    slice 3.)"""
    return _BUILTIN_CLASSES.get(functor)
