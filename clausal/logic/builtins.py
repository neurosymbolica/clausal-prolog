"""clausal.logic.builtins — built-in and standard-library predicates (Step 8).

Built-ins come in two flavours:

**Simple-mode** (``@_builtin``): small deterministic predicates (type checks,
arithmetic, term inspection) written with a simple internal signature::

    def predicate__N(arg0, …, argN-1, trail, k): …

They yield ``None`` for each solution and are automatically wrapped to the
trampoline dispatch protocol at registration time.

**Native trampoline** (``@_trampoline_builtin``): predicates that operate on
lists or call sub-goals.  Written with the trampoline signature directly::

    def predicate__N(this_generator, parent, arg0, …, argN-1, trail): …

They yield ``(parent, None)`` per solution and ``(parent, DONE)`` at
exhaustion, and call sub-goals via ``StepGenerator`` so the trampoline
drives every level — no hidden stack growth.

Stateless built-ins are stored in ``_BUILTINS``.  Built-ins that need a
reference to the live database (assertz, asserta, retract, signature) are
stored in ``_DB_BUILTINS`` as factory callables; ``get_builtin_dispatch``
passes the database when creating them.

``Database.get_dispatch`` calls ``get_builtin_dispatch(functor, arity, db)`` as a
fallback when a predicate is not found locally, so built-ins are available in
every database without requiring explicit registration.

Built-ins implemented
---------------------
Core inspection
    functor/3       — decompose/compose term functor name and arity
    arg/3           — Nth argument of a compound term (1-based)
    univ/2          — T =.. [Functor | Args]  (term ↔ list)
    copy_term/2     — deep copy with fresh Vars (V2-13)
    term_variables/2 — collect unbound Vars in term (V2-13)
    number_vars/3   — number unbound Vars with $VAR(N) (V2-13)

Runtime database manipulation
    assertz/1   — add clause at end of its predicate
    asserta/1   — add clause at front of its predicate
    retract/1   — remove first matching clause (structural head equality)

Keyword-term introspection (WK-5)
    vary/3          — produce a copy of a term with field overrides
    extend/3        — produce a copy of a KWTerm with additional fields
    unbound_keys/2  — collect names of unbound-Var fields in a term
    signature/3     — reflect the registered signature for a predicate

Standard library — type checks
    var/1, nonvar/1, atom/1, number/1, integer/1, float_/1, string/1,
    compound/1, callable/1, is_list/1, ground/1

Standard library — arithmetic
    between/3, succ/2, plus/3, abs_/2, max_/3, min_/3

Standard library — list predicates
    member/2, append/3, length/2, last/2, reverse/2,
    nth0/3, nth1/3, flatten/2, msort/2, sort/2,
    permutation/2, select/3, subtract/3, intersection/3, union/3,
    list_to_set/2, sum_list/2, max_list/2, min_list/2

Standard library — pair helpers
    pairs_keys_values/3, pairs_keys/2, pairs_values/2

Higher-order list predicates (V2-11)
    map_list/2, map_list/3, include/3, exclude/3, foldl/4

Pythonic aliases (V2-11)
    merge_sort/2 (→ msort/2), get_item/3 (→ nth0/3),
    member_check/2 (→ memberchk/2), unpack/2 (→ univ/2)
"""

from __future__ import annotations

from typing import Any, Callable

import sys as _sys

from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.logic.predicate import is_term_instance, term_field_names
from clausal.logic.trampoline import DONE, StepGenerator
from clausal.terms import Compound, KWTerm, term_str as _term_str


# ── Simple → trampoline adapter ──────────────────────────────────────────────


def _simple_to_trampoline(simple_fn):
    """Wrap a simple-mode dispatch function as a trampoline-protocol function.

    Simple-mode signature:  ``fn(*args, trail, k)`` → yields ``None``
    Trampoline signature:   ``fn(this_gen, parent, *args, trail)`` → yields ``(parent, None)`` / ``(parent, DONE)``
    """
    def trampoline_fn(this_generator, parent, *args):
        # args = (*pred_args, trail)  — trail is always last
        for _ in simple_fn(*args, None):
            yield (parent, None)
        yield (parent, DONE)
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


def _builtin(functor: str, arity: int):
    """Decorator: register a function as a stateless built-in (auto-wrapped to trampoline)."""
    def decorator(fn: Callable) -> Callable:
        _BUILTINS[(functor, arity)] = _simple_to_trampoline(fn)
        return fn
    return decorator


def _trampoline_builtin(functor: str, arity: int):
    """Decorator: register a native trampoline-protocol built-in (no wrapping).

    Use for builtins that operate on lists or call sub-goals, so they
    participate directly in the trampoline without an extra wrapper layer.

    Signature: ``fn(this_generator, parent, arg0, …, argN-1, trail)``
    Must yield ``(parent, None)`` per solution and ``(parent, DONE)`` at end.
    """
    def decorator(fn: Callable) -> Callable:
        _BUILTINS[(functor, arity)] = fn
        return fn
    return decorator


def _ensure_trampoline_dispatch(goal_val):
    """Return a trampoline-protocol dispatch function for *goal_val*.

    Handles:
    - PredicateMeta / BuiltinPredicate with ``_get_dispatch()`` → returns that
    - Simple-mode callable ``fn(*args, trail, k)`` → wraps to trampoline
    """
    if hasattr(goal_val, '_get_dispatch'):
        return goal_val._get_dispatch()
    # Assume simple-mode callable
    return _simple_to_trampoline(goal_val)




def _db_builtin(functor: str, arity: int):
    """Decorator: register a factory as a db-dependent built-in (auto-wrapped to trampoline)."""
    def decorator(factory: Callable) -> Callable:
        _DB_BUILTINS[(functor, arity)] = _wrap_db_factory(factory)
        return factory
    return decorator


def structural_unify(t1: Any, t2: Any, trail: Any) -> bool:
    """Python-level structural unification that handles Compound, KWTerm, and dataclasses.

    The C extension's ``unify`` handles Var, tuple, list, and atomic equality.
    This wrapper adds recursive unification for Compound, KWTerm, and dataclass
    terms (WK-6 cross-representation unification).
    """
    t1 = deref(t1)
    t2 = deref(t2)

    # If either is unbound Var, delegate to the C unify (it handles Var binding).
    if is_var(t1) or is_var(t2):
        return bool(unify(t1, t2, trail))

    # Both are ground (or at least non-Var at the top level).
    # Compound ↔ Compound
    if isinstance(t1, Compound) and isinstance(t2, Compound):
        if t1.functor != t2.functor or len(t1.args) != len(t2.args):
            return False
        mark = trail.mark()
        for a1, a2 in zip(t1.args, t2.args):
            if not structural_unify(a1, a2, trail):
                trail.undo(mark)
                return False
        return True

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

    # KWTerm ↔ KWTerm (same functor and same key set)
    if isinstance(t1, KWTerm) and isinstance(t2, KWTerm):
        if t1.functor != t2.functor or set(t1.keys()) != set(t2.keys()):
            return False
        mark = trail.mark()
        for key in t1.keys():
            if not structural_unify(t1._fields[key], t2._fields[key], trail):
                trail.undo(mark)
                return False
        return True

    # Fall back to C unify for all other combinations (atoms, tuples, etc.)
    return bool(unify(t1, t2, trail))


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
                raise NotImplementedError(
                    f"Builtin {self._functor}/{self._arity} has no dispatch function"
                )
        return self._dispatch_fn

    def _arity_dispatch(self, this_generator, parent, *args):
        """Dispatch to the correct arity handler based on arg count.

        Trampoline protocol: args = (*pred_args, trail).
        Arity = len(args) - 1.
        """
        arity = len(args) - 1  # exclude trail
        fn = self._arity_map.get(arity)
        if fn is None:
            from clausal.logic.trampoline import DONE as _DONE
            yield (parent, _DONE)
            return
        yield from fn(this_generator, parent, *args)

    def _merge(self, other: "BuiltinPredicate") -> None:
        """Merge another BuiltinPredicate into this one for multi-arity dispatch."""
        if self._arity_map is None:
            self._arity_map = {}
            # Add our own arity to the map.
            if self._dispatch_fn is not None:
                self._arity_map[self._arity] = self._dispatch_fn
            elif self._factory is not None and self._db is not None:
                self._arity_map[self._arity] = self._factory(self._db)
        if other._dispatch_fn is not None:
            self._arity_map[other._arity] = other._dispatch_fn
        elif other._factory is not None and other._db is not None:
            self._arity_map[other._arity] = other._factory(other._db)

    def __repr__(self) -> str:
        if self._arity_map:
            arities = sorted(self._arity_map)
            return f"BuiltinPredicate({self._functor!r}/{arities})"
        return f"BuiltinPredicate({self._functor!r}/{self._arity})"


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


# ── Helpers ────────────────────────────────────────────────────────────────────


def _functor_name(term: Any) -> str | None:
    """Return the functor name of a ground term, or None."""
    if isinstance(term, Compound):
        return term.functor if isinstance(term.functor, str) else None
    if isinstance(term, KWTerm):
        return term.functor
    if is_term_instance(term):
        return type(term).__name__
    if isinstance(term, list):
        return "[]" if len(term) == 0 else "."
    if isinstance(term, (bool, int, float, str, bytes)) or term is None:
        return repr(term) if not isinstance(term, str) else term
    return None


def _arity(term: Any) -> int | None:
    """Return the arity of a ground term, or None."""
    if isinstance(term, Compound):
        return len(term.args)
    if isinstance(term, KWTerm):
        return len(term)
    if is_term_instance(term):
        return len(term_field_names(term))
    if isinstance(term, list):
        return 0 if len(term) == 0 else 2
    if isinstance(term, (bool, int, float, str, bytes)) or term is None:
        return 0
    return None


def _nth_arg(term: Any, n: int) -> Any:
    """Return the n-th argument (1-based) of a compound term, or raise IndexError."""
    if isinstance(term, Compound):
        if n < 1 or n > len(term.args):
            raise IndexError(f"arg index {n} out of range for {term!r}")
        return term.args[n - 1]
    if isinstance(term, KWTerm):
        vals = list(term.values())
        if n < 1 or n > len(vals):
            raise IndexError(f"arg index {n} out of range for {term!r}")
        return vals[n - 1]
    if is_term_instance(term):
        fields = term_field_names(term)
        if n < 1 or n > len(fields):
            raise IndexError(f"arg index {n} out of range for {term!r}")
        return getattr(term, fields[n - 1])
    if isinstance(term, list) and len(term) >= n >= 1:
        return term[n - 1]
    raise IndexError(f"arg index {n} out of range for {term!r}")


def _args_list(term: Any) -> list:
    """Return the argument list of a compound term."""
    if isinstance(term, Compound):
        return list(term.args)
    if isinstance(term, KWTerm):
        return list(term.values())
    if is_term_instance(term):
        return [getattr(term, name) for name in term_field_names(term)]
    return []


def _is_compound(term: Any) -> bool:
    return (
        isinstance(term, (Compound, KWTerm))
        or is_term_instance(term)
    )


def _is_ground(term: Any) -> bool:
    """True if term contains no unbound Vars."""
    term = deref(term)
    if is_var(term):
        return False
    if isinstance(term, (bool, int, float, str, bytes)) or term is None:
        return True
    if isinstance(term, list):
        return all(_is_ground(e) for e in term)
    if isinstance(term, Compound):
        return isinstance(term.functor, str) and all(_is_ground(a) for a in term.args)
    if isinstance(term, KWTerm):
        return all(_is_ground(v) for v in term.values())
    if is_term_instance(term):
        return all(_is_ground(getattr(term, name)) for name in term_field_names(term))
    return True


# ── Core inspection ────────────────────────────────────────────────────────────


@_builtin("Functor", 3)
def _functor__3(term, name, arity, trail, k):
    """functor(Term, Name, Arity) — decompose or compose a term.

    If Term is bound: unify Name with its functor name and Arity with its arity.
    If Term is unbound: Name and Arity must be bound; construct a Compound.
    """
    term_val = deref(term)

    if is_var(term_val):
        # Construction mode
        name_val = deref(name)
        arity_val = deref(arity)
        if is_var(name_val) or is_var(arity_val):
            return
        if not isinstance(arity_val, int) or arity_val < 0:
            return
        if arity_val == 0:
            constructed = name_val
        else:
            args = tuple(Var() for _ in range(arity_val))
            constructed = Compound(str(name_val), args)
        mark = trail.mark()
        if unify(term, constructed, trail):
            yield None
        trail.undo(mark)
    else:
        # Inspection mode
        f_val = _functor_name(term_val)
        a_val = _arity(term_val)
        if f_val is None or a_val is None:
            return
        mark = trail.mark()
        if unify(name, f_val, trail):
            mark2 = trail.mark()
            if unify(arity, a_val, trail):
                yield None
            trail.undo(mark2)
        trail.undo(mark)


@_builtin("Arg", 3)
def _arg__3(n, term, arg_out, trail, k):
    """arg(N, Term, Arg) — unify Arg with the N-th argument of Term (1-based)."""
    n_val = deref(n)
    term_val = deref(term)
    if is_var(n_val) or is_var(term_val):
        return
    if not isinstance(n_val, int):
        return
    try:
        arg_val = _nth_arg(term_val, n_val)
    except IndexError:
        return
    mark = trail.mark()
    if unify(arg_out, arg_val, trail):
        yield None
    trail.undo(mark)


@_builtin("Unpack", 2)
def _univ__2(term, lst, trail, k):
    """univ(Term, List) — ``=..`` in Prolog.

    If Term is bound: List unifies with [functor | args].
    If Term is unbound: List must be [FunctorName | Args]; Term is constructed.
    """
    term_val = deref(term)

    if not is_var(term_val):
        # Decomposition
        f_val = _functor_name(term_val)
        if f_val is None:
            return
        decomposed = [f_val] + _args_list(term_val)
        mark = trail.mark()
        if unify(lst, decomposed, trail):
            yield None
        trail.undo(mark)
    else:
        # Construction
        lst_val = deref(lst)
        if is_var(lst_val) or not isinstance(lst_val, list) or len(lst_val) == 0:
            return
        f_val = deref(lst_val[0])
        if is_var(f_val):
            return
        args_vals = [deref(a) for a in lst_val[1:]]
        if len(args_vals) == 0:
            constructed: Any = f_val  # atom
        else:
            constructed = Compound(str(f_val), tuple(args_vals))
        mark = trail.mark()
        if unify(term, constructed, trail):
            yield None
        trail.undo(mark)


# ── V2-13 Term inspection ──────────────────────────────────────────────────────


def _copy_term(term: Any, var_map: dict) -> Any:
    """Recursively copy *term*, replacing each unbound Var with a fresh one.

    *var_map* maps original Var id → fresh Var so that sharing is preserved.
    """
    term = deref(term)
    if is_var(term):
        vid = id(term)
        if vid not in var_map:
            var_map[vid] = Var()
        return var_map[vid]
    if isinstance(term, (bool, int, float, str, bytes)) or term is None:
        return term
    if isinstance(term, list):
        return [_copy_term(e, var_map) for e in term]
    if isinstance(term, Compound):
        return Compound(term.functor, tuple(_copy_term(a, var_map) for a in term.args))
    if isinstance(term, KWTerm):
        return KWTerm({k: _copy_term(v, var_map) for k, v in term.items()})
    if is_term_instance(term):
        return type(term)(**{
            name: _copy_term(getattr(term, name), var_map)
            for name in term_field_names(term)
        })
    return term


@_builtin("CopyTerm", 2)
def _copy_term__2(original, copy, trail, k):
    """copy_term(Original, Copy) — unify Copy with a deep copy of Original with fresh Vars."""
    orig_val = deref(original)
    copied = _copy_term(orig_val, {})
    mark = trail.mark()
    if unify(copy, copied, trail):
        yield None
    trail.undo(mark)


def _collect_vars(term: Any, seen_ids: set, result: list) -> None:
    """Collect all unbound Vars in *term* into *result*, preserving left-to-right order."""
    term = deref(term)
    if is_var(term):
        vid = id(term)
        if vid not in seen_ids:
            seen_ids.add(vid)
            result.append(term)
        return
    if isinstance(term, (bool, int, float, str, bytes)) or term is None:
        return
    if isinstance(term, list):
        for e in term:
            _collect_vars(e, seen_ids, result)
        return
    if isinstance(term, Compound):
        for a in term.args:
            _collect_vars(a, seen_ids, result)
        return
    if isinstance(term, KWTerm):
        for v in term.values():
            _collect_vars(v, seen_ids, result)
        return
    if is_term_instance(term):
        for name in term_field_names(term):
            _collect_vars(getattr(term, name), seen_ids, result)


@_builtin("TermVariables", 2)
def _term_variables__2(term, vars_out, trail, k):
    """term_variables(Term, Vars) — unify Vars with list of unbound variables in Term."""
    term_val = deref(term)
    result: list = []
    _collect_vars(term_val, set(), result)
    mark = trail.mark()
    if unify(vars_out, result, trail):
        yield None
    trail.undo(mark)


@_builtin("NumberVars", 3)
def _number_vars__3(term, start, end, trail, k):
    """number_vars(Term, Start, End) — bind unbound Vars in Term to '$VAR'(N) atoms.

    Variables are numbered left-to-right starting at Start.  End is unified
    with the next available number after all variables are numbered.
    """
    start_val = deref(start)
    if is_var(start_val) or not isinstance(start_val, int):
        return
    term_val = deref(term)
    vars_list: list = []
    _collect_vars(term_val, set(), vars_list)
    # Bind each unbound var to Compound("$VAR", (N,))
    marks = []
    for i, v in enumerate(vars_list):
        m = trail.mark()
        atom = Compound("$VAR", (start_val + i,))
        if not unify(v, atom, trail):
            for mk in reversed(marks):
                trail.undo(mk)
            return
        marks.append(m)
    end_val = start_val + len(vars_list)
    mark = trail.mark()
    if unify(end, end_val, trail):
        yield None
    trail.undo(mark)
    for mk in reversed(marks):
        trail.undo(mk)


# ── Runtime database manipulation ─────────────────────────────────────────────


def _normalize_fact_clause(term: Any):
    """Convert a ground Compound fact to Var+Is form for output-mode queries.

    ``Compound("f", (1, 2))`` → head=Compound("f", (v0, v1)), body=[Is(v0,1), Is(v1,2)]

    This makes dynamically asserted facts queryable in output mode (with unbound
    Var arguments), matching standard Prolog semantics for assert.
    Facts asserted via the DSL already use Var+Is form via the term transformer.
    """
    from clausal.logic.database import Clause  # avoid top-level import cycle
    from clausal.terms import Unify as _Unify

    if isinstance(term, Compound):
        new_args = []
        body: list = []
        for arg in term.args:
            arg_val = deref(arg)
            if not is_var(arg_val):
                v = Var()
                new_args.append(v)
                body.append(_Unify(left=v, right=arg_val))
            else:
                new_args.append(arg_val)
        return Clause(head=Compound(term.functor, tuple(new_args)), body=body)
    # Dataclass and KWTerm facts are passed as-is; their field patterns work
    # correctly since they use Python structural matching.
    from clausal.logic.database import Clause  # already imported above
    return Clause(head=term, body=[])


def _build_clause(term_val: Any) -> "Any":
    """Build a Clause from a runtime term passed to assertz/asserta.

    Handles Predicate nodes (rules) and plain terms (facts).
    Ground Compound facts are normalized to Var+Is form.
    """
    from clausal.logic.database import Clause, _flatten_body  # avoid top-level cycle
    from clausal.terms import Predicate as _Predicate

    if isinstance(term_val, _Predicate):
        return Clause(head=term_val.head, body=_flatten_body(term_val.body))
    return _normalize_fact_clause(term_val)


def _find_pred_cls(functor: str, module_dict: "dict | None") -> "Any":
    """Return the PredicateMeta class for functor from module_dict, or None."""
    from clausal.logic.predicate import PredicateMeta  # noqa: PLC0415
    if module_dict is None:
        return None
    candidate = module_dict.get(functor)
    return candidate if isinstance(candidate, PredicateMeta) else None


@_db_builtin("Assert", 1)
def _assertz_factory(db):
    """assertz(Term) — add Term as a fact at end of its predicate's clause list.

    Ground facts are automatically normalized to Var+Is form so they are
    queryable in output mode (matching standard Prolog assert semantics).
    When a module dict is available on the database, also syncs to the
    PredicateMeta class and recompiles with module globals for cross-predicate
    resolution.
    """
    from clausal.logic.database import head_key
    from clausal.logic.compiler import compile_predicate_trampoline
    module_dict = getattr(db, "module_dict", None)

    def assertz__1(term, trail, k):
        term_val = deref(term)
        if is_var(term_val):
            return
        clause = _build_clause(term_val)
        functor, arity = head_key(clause.head)
        pred_cls = _find_pred_cls(functor, module_dict)
        if pred_cls is not None and pred_cls._locked:
            raise RuntimeError(
                f"Predicate {functor}/{arity} is locked. "
                "Use dynamic() to allow runtime assertion."
            )
        db.assertz(clause)
        if pred_cls is not None:
            pred_cls._clauses.append(clause)
            pred_cls._dispatch_fn = None
        clauses = db.clauses_for(functor, arity)
        compile_predicate_trampoline(functor, arity, clauses, db,
                                     globals_=module_dict, pred_cls=pred_cls)
        yield None

    return assertz__1


@_db_builtin("AssertFirst", 1)
def _asserta_factory(db):
    """asserta(Term) — add Term as a fact at front of its predicate's clause list.

    When a module dict is available on the database, also syncs to the
    PredicateMeta class and recompiles with module globals.
    """
    from clausal.logic.database import head_key
    from clausal.logic.compiler import compile_predicate_trampoline
    module_dict = getattr(db, "module_dict", None)

    def asserta__1(term, trail, k):
        term_val = deref(term)
        if is_var(term_val):
            return
        clause = _build_clause(term_val)
        functor, arity = head_key(clause.head)
        pred_cls = _find_pred_cls(functor, module_dict)
        if pred_cls is not None and pred_cls._locked:
            raise RuntimeError(
                f"Predicate {functor}/{arity} is locked. "
                "Use dynamic() to allow runtime assertion."
            )
        db.asserta(clause)
        if pred_cls is not None:
            pred_cls._clauses.insert(0, clause)
            pred_cls._dispatch_fn = None
        clauses = db.clauses_for(functor, arity)
        compile_predicate_trampoline(functor, arity, clauses, db,
                                     globals_=module_dict, pred_cls=pred_cls)
        yield None

    return asserta__1


@_db_builtin("Retract", 1)
def _retract_factory(db):
    """retract(Term) — remove the first clause whose head unifies with Term.

    Uses unification (not structural equality) so it correctly handles
    normalized facts whose heads contain Var placeholders.  Bindings
    from the head unification are undone after the clause is removed
    (retract is not backtrackable in this implementation).
    When a module dict is available on the database, also syncs to the
    PredicateMeta class.
    """
    from clausal.logic.database import head_key
    from clausal.logic.compiler import compile_predicate_trampoline
    module_dict = getattr(db, "module_dict", None)

    def retract__1(term, trail, k):
        term_val = deref(term)
        if is_var(term_val):
            return
        try:
            functor, arity = head_key(term_val)
        except TypeError:
            return
        clause_list = db._clauses.get((functor, arity))
        if clause_list is None:
            return
        pred_cls = _find_pred_cls(functor, module_dict)
        if pred_cls is not None and pred_cls._locked:
            raise RuntimeError(
                f"Predicate {functor}/{arity} is locked. "
                "Use dynamic() to allow runtime retraction."
            )
        # Find first clause whose head unifies with term_val (and whose
        # Is-body goals are consistent with that unification).
        from clausal.terms import Unify as _Unify  # avoid top-level cycle
        for i, clause in enumerate(clause_list):
            tmp_trail = Trail()
            mark = tmp_trail.mark()
            if not structural_unify(term_val, clause.head, tmp_trail):
                tmp_trail.undo(mark)
                continue
            # Verify body: check that Unify goals are consistent with the head
            # unification.  We check only Unify goals (normalization artefacts).
            body_ok = True
            for goal in clause.body:
                if isinstance(goal, _Unify):
                    lv = deref(goal.left)
                    rv = deref(goal.right)
                    chk_trail = Trail()
                    chk_mark = chk_trail.mark()
                    if not structural_unify(lv, rv, chk_trail):
                        body_ok = False
                        chk_trail.undo(chk_mark)
                        break
                    chk_trail.undo(chk_mark)  # don't retain Is bindings
            if not body_ok:
                tmp_trail.undo(mark)  # undo head bindings before next iteration
                continue
            # Found a matching clause — remove it.
            tmp_trail.undo(mark)  # clean up temporary bindings
            del clause_list[i]
            # Sync removal to pred_cls if available (match by identity).
            if pred_cls is not None:
                for j, pcls_clause in enumerate(pred_cls._clauses):
                    if pcls_clause is clause:
                        del pred_cls._clauses[j]
                        pred_cls._dispatch_fn = None
                        break
            clauses = db.clauses_for(functor, arity)
            if clauses:
                compile_predicate_trampoline(functor, arity, clauses, db,
                                             globals_=module_dict, pred_cls=pred_cls)
            yield None
            return  # retract is not backtrackable

    return retract__1


# ── Tabling ───────────────────────────────────────────────────────────────────


@_db_builtin("ClearTable", 2)
def _abolish_table_factory(db):
    """abolish_table(Functor, Arity) — remove cached answers for a tabled predicate."""

    def abolish_table__2(functor_arg, arity_arg, trail, k):
        f = deref(functor_arg)
        a = deref(arity_arg)
        if is_var(f) or is_var(a):
            return
        if not isinstance(f, str) or not isinstance(a, int):
            return
        db.abolish_table(f, a)
        yield None

    return abolish_table__2


@_db_builtin("ClearAllTables", 0)
def _abolish_all_tables_factory(db):
    """abolish_all_tables — remove all cached tabling answers."""

    def abolish_all_tables__0(trail, k):
        db.abolish_all_tables()
        yield None

    return abolish_all_tables__0


# ── WK-5: Keyword-term introspection ──────────────────────────────────────────


@_builtin("Vary", 3)
def _vary__3(overrides, term, new_term, trail, k):
    """vary(Overrides, Term, NewTerm) — copy Term with field overrides.

    Overrides is a Python dict {field_name: new_value}.
    Term must be a functor dataclass or KWTerm.
    NewTerm is unified with the resulting copy.
    """
    overrides_val = deref(overrides)
    term_val = deref(term)
    if is_var(overrides_val) or is_var(term_val):
        return
    if not isinstance(overrides_val, dict):
        return
    if is_term_instance(term_val) and not isinstance(term_val, KWTerm):
        try:
            fields = term_field_names(term_val)
            kwargs = {name: getattr(term_val, name) for name in fields}
            kwargs.update(overrides_val)
            result = type(term_val)(**kwargs)
        except (TypeError, ValueError):
            return
    elif isinstance(term_val, KWTerm):
        try:
            result = term_val.with_overrides(**overrides_val)
        except KeyError:
            return
    else:
        return
    mark = trail.mark()
    if unify(new_term, result, trail):
        yield None
    trail.undo(mark)


@_builtin("Extend", 3)
def _extend__3(additions, term, new_term, trail, k):
    """extend(Additions, Term, NewTerm) — copy Term with additional fields.

    Additions is a Python dict {field_name: value}.
    Term must be a KWTerm (dataclass terms have fixed schemas).
    NewTerm is unified with the resulting extended term.
    """
    additions_val = deref(additions)
    term_val = deref(term)
    if is_var(additions_val) or is_var(term_val):
        return
    if not isinstance(additions_val, dict):
        return
    if isinstance(term_val, KWTerm):
        try:
            result = term_val.with_extensions(**additions_val)
        except KeyError:
            return
    else:
        return
    mark = trail.mark()
    if unify(new_term, result, trail):
        yield None
    trail.undo(mark)


@_builtin("UnboundKeys", 2)
def _unbound_keys__2(term, keys_list, trail, k):
    """unbound_keys(Term, Keys) — Keys is the list of field names holding unbound Vars.

    Works for functor dataclass instances and KWTerm.
    """
    term_val = deref(term)
    if is_var(term_val):
        return
    keys: list[str] = []
    if is_term_instance(term_val) and not isinstance(term_val, KWTerm):
        for name in term_field_names(term_val):
            if is_var(deref(getattr(term_val, name))):
                keys.append(name)
    elif isinstance(term_val, KWTerm):
        for fname, val in term_val.items():
            if is_var(deref(val)):
                keys.append(fname)
    mark = trail.mark()
    if unify(keys_list, keys, trail):
        yield None
    trail.undo(mark)


@_db_builtin("Signature", 3)
def _signature_factory(db):
    """signature(FunctorName, Arity, Names) — reflect the registered signature."""
    def signature__3(functor_name, arity, names, trail, k):
        f_val = deref(functor_name)
        a_val = deref(arity)
        if is_var(f_val) or is_var(a_val):
            return
        if not isinstance(a_val, int):
            return
        sig = db.signature_for(str(f_val), a_val)
        if sig is None:
            return
        mark = trail.mark()
        if unify(names, list(sig), trail):
            yield None
        trail.undo(mark)
    return signature__3


# ── Constraint builtins ───────────────────────────────────────────────────────


@_builtin("Dif", 2)
def _dif__2(x, y, trail, k):
    """dif(X, Y) — disequality constraint: succeed if X and Y can remain different."""
    from clausal.logic.constraints import dif as _dif_fn  # noqa: PLC0415
    if _dif_fn(x, y, trail):
        yield None


# ── Reified builtins (V2-8 Phase B) ──────────────────────────────────────────


@_builtin("Eq", 3)
def _eq__3(x, y, t, trail, k):
    """eq(X, Y, T) — reified equality: T is True if X=Y, False if dif(X,Y)."""
    from clausal.logic.reif import eq__3  # noqa: PLC0415
    yield from eq__3(x, y, t, trail, k)


@_builtin("DifT", 3)
def _dif_t__3(x, y, t, trail, k):
    """dif_t(X, Y, T) — reified disequality: T is True if dif(X,Y), False if X=Y."""
    from clausal.logic.reif import dif_t__3  # noqa: PLC0415
    yield from dif_t__3(x, y, t, trail, k)


# ── CLP(FD) builtins ─────────────────────────────────────────────────────────


@_builtin("InDomain", 3)
def _in_domain__3(var_or_list, lo, hi, trail, k):
    """in_domain(Var, Lo, Hi) — post domain [Lo, Hi] on Var or list of Vars."""
    from clausal.logic.clpfd import in_domain as _in_domain_fn  # noqa: PLC0415
    if _in_domain_fn(var_or_list, lo, hi, trail):
        yield None


@_builtin("Label", 1)
def _label__1(vars_list, trail, k):
    """label(Vars) — enumerate values for FD-constrained variables."""
    from clausal.logic.clpfd import label as _label_fn  # noqa: PLC0415
    yield from _label_fn(vars_list, trail)


@_builtin("AllDifferent", 1)
def _all_different__1(vars_list, trail, k):
    """all_different(Vars) — post all-different constraint on list of Vars."""
    from clausal.logic.clpfd import all_different as _all_diff_fn  # noqa: PLC0415
    if _all_diff_fn(vars_list, trail):
        yield None


@_builtin("Equivalent", 2)
def _equivalent__2(t1, t2, trail, k):
    """equivalent(T1, T2) — structural equality (old == behavior)."""
    from clausal.logic.clpfd import equivalent as _equiv_fn  # noqa: PLC0415
    if _equiv_fn(t1, t2, trail):
        yield None


# ── Standard library: type checks ─────────────────────────────────────────────


@_builtin("IsVar", 1)
def _var__1(x, trail, k):
    """var(X) — succeeds if X is an unbound logic variable."""
    if is_var(deref(x)):
        yield None


@_builtin("IsBound", 1)
def _nonvar__1(x, trail, k):
    """nonvar(X) — succeeds if X is bound (not an unbound Var)."""
    if not is_var(deref(x)):
        yield None


@_builtin("IsStr", 1)
def _atom__1(x, trail, k):
    """atom(X) — succeeds if X is a string (Prolog atom)."""
    x_val = deref(x)
    if not is_var(x_val) and isinstance(x_val, str):
        yield None


@_builtin("IsNumber", 1)
def _number__1(x, trail, k):
    """number(X) — succeeds if X is an int or float (not bool)."""
    x_val = deref(x)
    if (
        not is_var(x_val)
        and isinstance(x_val, (int, float))
        and not isinstance(x_val, bool)
    ):
        yield None


@_builtin("IsInt", 1)
def _integer__1(x, trail, k):
    """integer(X) — succeeds if X is an int (not bool)."""
    x_val = deref(x)
    if not is_var(x_val) and isinstance(x_val, int) and not isinstance(x_val, bool):
        yield None


@_builtin("IsFloat", 1)
def _float__1(x, trail, k):
    """float_(X) — succeeds if X is a Python float."""
    x_val = deref(x)
    if not is_var(x_val) and isinstance(x_val, float):
        yield None



@_builtin("IsCompound", 1)
def _compound__1(x, trail, k):
    """compound(X) — succeeds if X is a compound term with arity > 0."""
    x_val = deref(x)
    if is_var(x_val):
        return
    if isinstance(x_val, Compound) and len(x_val.args) > 0:
        yield None
    elif isinstance(x_val, KWTerm) and len(x_val) > 0:
        yield None
    elif is_term_instance(x_val) and len(term_field_names(x_val)) > 0:
        yield None


@_builtin("IsCallable", 1)
def _callable__1(x, trail, k):
    """callable(X) — succeeds if X is an atom or compound."""
    x_val = deref(x)
    if is_var(x_val):
        return
    if isinstance(x_val, (str, Compound, KWTerm)):
        yield None
    elif is_term_instance(x_val):
        yield None


@_builtin("IsList", 1)
def _is_list__1(x, trail, k):
    """is_list(X) — succeeds if X is a Python list."""
    if isinstance(deref(x), list):
        yield None


@_builtin("IsGround", 1)
def _ground__1(x, trail, k):
    """ground(X) — succeeds if X contains no unbound Vars."""
    if _is_ground(deref(x)):
        yield None


# ── Standard library: arithmetic ──────────────────────────────────────────────


@_builtin("Between", 3)
def _between__3(low, high, x, trail, k):
    """between(Low, High, X) — X ranges over integers from Low to High inclusive."""
    low_val = deref(low)
    high_val = deref(high)
    if is_var(low_val) or is_var(high_val):
        return
    if not isinstance(low_val, int) or not isinstance(high_val, int):
        return
    x_val = deref(x)
    if not is_var(x_val):
        # Check mode
        if isinstance(x_val, int) and low_val <= x_val <= high_val:
            yield None
    else:
        # Generate mode
        for i in range(low_val, high_val + 1):
            mark = trail.mark()
            if unify(x, i, trail):
                yield None
            trail.undo(mark)


@_builtin("Succ", 2)
def _succ__2(x, y, trail, k):
    """succ(X, Y) — Y = X + 1 (both non-negative integers)."""
    x_val = deref(x)
    y_val = deref(y)
    if not is_var(x_val):
        if not isinstance(x_val, int) or isinstance(x_val, bool) or x_val < 0:
            return
        mark = trail.mark()
        if unify(y, x_val + 1, trail):
            yield None
        trail.undo(mark)
    elif not is_var(y_val):
        if not isinstance(y_val, int) or isinstance(y_val, bool) or y_val < 1:
            return
        mark = trail.mark()
        if unify(x, y_val - 1, trail):
            yield None
        trail.undo(mark)


@_builtin("Plus", 3)
def _plus__3(x, y, z, trail, k):
    """plus(X, Y, Z) — Z = X + Y; any two determine the third."""
    x_val = deref(x)
    y_val = deref(y)
    z_val = deref(z)
    x_known = not is_var(x_val)
    y_known = not is_var(y_val)
    z_known = not is_var(z_val)

    if x_known and y_known:
        mark = trail.mark()
        if unify(z, x_val + y_val, trail):
            yield None
        trail.undo(mark)
    elif x_known and z_known:
        mark = trail.mark()
        if unify(y, z_val - x_val, trail):
            yield None
        trail.undo(mark)
    elif y_known and z_known:
        mark = trail.mark()
        if unify(x, z_val - y_val, trail):
            yield None
        trail.undo(mark)


@_builtin("Abs", 2)
def _abs__2(x, y, trail, k):
    """abs_(X, Y) — Y = abs(X)."""
    x_val = deref(x)
    if is_var(x_val):
        return
    if not isinstance(x_val, (int, float)):
        return
    mark = trail.mark()
    if unify(y, abs(x_val), trail):
        yield None
    trail.undo(mark)


@_builtin("Max", 3)
def _max__3(x, y, z, trail, k):
    """max_(X, Y, Z) — Z = max(X, Y)."""
    x_val = deref(x)
    y_val = deref(y)
    if is_var(x_val) or is_var(y_val):
        return
    mark = trail.mark()
    if unify(z, max(x_val, y_val), trail):
        yield None
    trail.undo(mark)


@_builtin("Min", 3)
def _min__3(x, y, z, trail, k):
    """min_(X, Y, Z) — Z = min(X, Y)."""
    x_val = deref(x)
    y_val = deref(y)
    if is_var(x_val) or is_var(y_val):
        return
    mark = trail.mark()
    if unify(z, min(x_val, y_val), trail):
        yield None
    trail.undo(mark)


@_builtin("Sign", 2)
def _sign__2(x, s, trail, k):
    """Sign(X, S) — S is the sign of X: -1, 0, or 1."""
    x_val = deref(x)
    if is_var(x_val):
        return
    if not isinstance(x_val, (int, float)):
        return
    sign_val = (x_val > 0) - (x_val < 0)
    mark = trail.mark()
    if unify(s, sign_val, trail):
        yield None
    trail.undo(mark)


@_builtin("Gcd", 3)
def _gcd__3(x, y, g, trail, k):
    """Gcd(X, Y, G) — G is the greatest common divisor of X and Y."""
    from math import gcd
    x_val = deref(x)
    y_val = deref(y)
    if is_var(x_val) or is_var(y_val):
        return
    if not isinstance(x_val, int) or not isinstance(y_val, int):
        return
    mark = trail.mark()
    if unify(g, gcd(x_val, y_val), trail):
        yield None
    trail.undo(mark)


@_builtin("DivMod", 4)
def _divmod__4(x, y, q, r, trail, k):
    """DivMod(X, Y, Q, R) — Q is X // Y and R is X mod Y."""
    x_val = deref(x)
    y_val = deref(y)
    if is_var(x_val) or is_var(y_val):
        return
    if not isinstance(x_val, int) or not isinstance(y_val, int):
        return
    if y_val == 0:
        return
    quotient, remainder = divmod(x_val, y_val)
    mark = trail.mark()
    if unify(q, quotient, trail):
        m2 = trail.mark()
        if unify(r, remainder, trail):
            yield None
        trail.undo(m2)
    trail.undo(mark)


# ── Standard library: list predicates ─────────────────────────────────────────


@_trampoline_builtin("In", 2)
def _member__2(this_generator, parent, elem, lst, trail):
    """member(Elem, List) — Elem is a member of List; enumerates on backtrack."""
    lst_val = deref(lst)
    if isinstance(lst_val, list):
        for item in lst_val:
            mark = trail.mark()
            if unify(elem, item, trail):
                yield (parent, None)
            trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("InCheck", 2)
def _memberchk__2(this_generator, parent, elem, lst, trail):
    """memberchk(Elem, List) — like member/2 but commits to the first match."""
    lst_val = deref(lst)
    if isinstance(lst_val, list):
        for item in lst_val:
            mark = trail.mark()
            if unify(elem, item, trail):
                yield (parent, None)
                yield (parent, DONE)
                return
            trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("Append", 3)
def _append__3(this_generator, parent, l1, l2, l3, trail):
    """append(L1, L2, L3) — L3 is the concatenation of L1 and L2.

    Modes:
      append(+, +, -) — deterministic concatenation
      append(+, -, +) — split L3 starting from L1
      append(-, -, +) — enumerate all splits of L3
    """
    l1_val = deref(l1)
    l2_val = deref(l2)
    l3_val = deref(l3)

    if isinstance(l1_val, list) and isinstance(l2_val, list):
        # Both known: concatenate
        mark = trail.mark()
        if unify(l3, l1_val + l2_val, trail):
            yield (parent, None)
        trail.undo(mark)
    elif isinstance(l1_val, list) and isinstance(l3_val, list):
        # L1 and L3 known: compute L2
        n = len(l1_val)
        if len(l3_val) >= n and l3_val[:n] == l1_val:
            mark = trail.mark()
            if unify(l2, l3_val[n:], trail):
                yield (parent, None)
            trail.undo(mark)
    elif isinstance(l3_val, list):
        # Only L3 known: enumerate all splits
        for i in range(len(l3_val) + 1):
            mark = trail.mark()
            if unify(l1, l3_val[:i], trail) and unify(l2, l3_val[i:], trail):
                yield (parent, None)
            trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("Length", 2)
def _length__2(this_generator, parent, lst, n, trail):
    """length(List, N) — N is the length of List."""
    lst_val = deref(lst)
    n_val = deref(n)
    if isinstance(lst_val, list):
        mark = trail.mark()
        if unify(n, len(lst_val), trail):
            yield (parent, None)
        trail.undo(mark)
    elif not is_var(n_val) and isinstance(n_val, int) and n_val >= 0:
        result = [Var() for _ in range(n_val)]
        mark = trail.mark()
        if unify(lst, result, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("Last", 2)
def _last__2(this_generator, parent, lst, elem, trail):
    """last(List, Elem) — Elem is the last element of List."""
    lst_val = deref(lst)
    if isinstance(lst_val, list) and len(lst_val) > 0:
        mark = trail.mark()
        if unify(elem, lst_val[-1], trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("Reverse", 2)
def _reverse__2(this_generator, parent, lst, rev, trail):
    """reverse(List, Rev) — Rev is the reverse of List."""
    lst_val = deref(lst)
    if isinstance(lst_val, list):
        mark = trail.mark()
        if unify(rev, list(reversed(lst_val)), trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("GetItem", 3)
def _nth0__3(this_generator, parent, n, lst, elem, trail):
    """nth0(N, List, Elem) — Elem is the N-th element of List (0-based)."""
    n_val = deref(n)
    lst_val = deref(lst)
    if isinstance(lst_val, list):
        if not is_var(n_val):
            if isinstance(n_val, int) and 0 <= n_val < len(lst_val):
                mark = trail.mark()
                if unify(elem, lst_val[n_val], trail):
                    yield (parent, None)
                trail.undo(mark)
        else:
            for i, item in enumerate(lst_val):
                mark = trail.mark()
                if unify(n, i, trail) and unify(elem, item, trail):
                    yield (parent, None)
                trail.undo(mark)
    yield (parent, DONE)



@_trampoline_builtin("Flatten", 2)
def _flatten__2(this_generator, parent, lst, flat, trail):
    """flatten(List, Flat) — Flat is the flat list of all atoms in List."""
    lst_val = deref(lst)
    if not is_var(lst_val):
        result: list = []

        def _do_flat(x: Any) -> None:
            x = deref(x)
            if isinstance(x, list):
                for item in x:
                    _do_flat(item)
            else:
                result.append(x)

        _do_flat(lst_val)
        mark = trail.mark()
        if unify(flat, result, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("MergeSort", 2)
def _msort__2(this_generator, parent, lst, sorted_lst, trail):
    """msort(List, Sorted) — Sorted is List sorted, preserving duplicates."""
    lst_val = deref(lst)
    if isinstance(lst_val, list):
        try:
            result = sorted(lst_val)
        except TypeError:
            result = sorted(lst_val, key=lambda x: (type(x).__name__, repr(x)))
        mark = trail.mark()
        if unify(sorted_lst, result, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("Sort", 2)
def _sort__2(this_generator, parent, lst, sorted_lst, trail):
    """sort(List, Sorted) — Sorted is List sorted with duplicates removed."""
    lst_val = deref(lst)
    if isinstance(lst_val, list):
        seen: list = []
        for x in lst_val:
            if x not in seen:
                seen.append(x)
        try:
            result = sorted(seen)
        except TypeError:
            result = sorted(seen, key=lambda x: (type(x).__name__, repr(x)))
        mark = trail.mark()
        if unify(sorted_lst, result, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("Permutation", 2)
def _permutation__2(this_generator, parent, lst, perm, trail):
    """permutation(List, Perm) — Perm is a permutation of List."""
    import itertools
    lst_val = deref(lst)
    if isinstance(lst_val, list):
        for p in itertools.permutations(lst_val):
            mark = trail.mark()
            if unify(perm, list(p), trail):
                yield (parent, None)
            trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("Select", 3)
def _select__3(this_generator, parent, elem, lst, rest, trail):
    """select(Elem, List, Rest) — Elem is in List, Rest is List without one occurrence."""
    lst_val = deref(lst)
    if isinstance(lst_val, list):
        for i, item in enumerate(lst_val):
            mark = trail.mark()
            remainder = lst_val[:i] + lst_val[i + 1:]
            if unify(elem, item, trail) and unify(rest, remainder, trail):
                yield (parent, None)
            trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("Subtract", 3)
def _subtract__3(this_generator, parent, set1, set2, diff, trail):
    """subtract(Set1, Set2, Diff) — Diff is Set1 minus elements in Set2."""
    s1 = deref(set1)
    s2 = deref(set2)
    if isinstance(s1, list) and isinstance(s2, list):
        result = [x for x in s1 if x not in s2]
        mark = trail.mark()
        if unify(diff, result, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("Intersection", 3)
def _intersection__3(this_generator, parent, set1, set2, inter, trail):
    """intersection(Set1, Set2, Inter) — Inter is the intersection of Set1 and Set2."""
    s1 = deref(set1)
    s2 = deref(set2)
    if isinstance(s1, list) and isinstance(s2, list):
        result = [x for x in s1 if x in s2]
        mark = trail.mark()
        if unify(inter, result, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("Union", 3)
def _union__3(this_generator, parent, set1, set2, uni, trail):
    """union(Set1, Set2, Union) — Union is Set1 ∪ Set2 (no duplicates)."""
    s1 = deref(set1)
    s2 = deref(set2)
    if isinstance(s1, list) and isinstance(s2, list):
        result = list(s1)
        for x in s2:
            if x not in result:
                result.append(x)
        mark = trail.mark()
        if unify(uni, result, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("ToSet", 2)
def _list_to_set__2(this_generator, parent, lst, set_out, trail):
    """list_to_set(List, Set) — Set is List with duplicates removed (order preserved)."""
    lst_val = deref(lst)
    if isinstance(lst_val, list):
        seen: list = []
        for x in lst_val:
            if x not in seen:
                seen.append(x)
        mark = trail.mark()
        if unify(set_out, seen, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("SumList", 2)
def _sum_list__2(this_generator, parent, lst, total, trail):
    """sum_list(List, Total) — Total is the sum of all numbers in List."""
    lst_val = deref(lst)
    if isinstance(lst_val, list):
        try:
            s = sum(deref(x) for x in lst_val)
        except TypeError:
            yield (parent, DONE)
            return
        mark = trail.mark()
        if unify(total, s, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("MaxList", 2)
def _max_list__2(this_generator, parent, lst, maximum, trail):
    """max_list(List, Max) — Max is the maximum element of List."""
    lst_val = deref(lst)
    if isinstance(lst_val, list) and len(lst_val) > 0:
        try:
            m = max(deref(x) for x in lst_val)
        except TypeError:
            yield (parent, DONE)
            return
        mark = trail.mark()
        if unify(maximum, m, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("MinList", 2)
def _min_list__2(this_generator, parent, lst, minimum, trail):
    """min_list(List, Min) — Min is the minimum element of List."""
    lst_val = deref(lst)
    if isinstance(lst_val, list) and len(lst_val) > 0:
        try:
            m = min(deref(x) for x in lst_val)
        except TypeError:
            yield (parent, DONE)
            return
        mark = trail.mark()
        if unify(minimum, m, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


# ── Standard library: pair helpers ────────────────────────────────────────────


@_trampoline_builtin("Unzip", 3)
def _pairs_keys_values__3(this_generator, parent, pairs, keys, values, trail):
    """pairs_keys_values(Pairs, Keys, Values) — Pairs is a list of [K, V] lists."""
    pairs_val = deref(pairs)
    if isinstance(pairs_val, list):
        ks = [deref(p)[0] for p in pairs_val if isinstance(deref(p), list)]
        vs = [deref(p)[1] for p in pairs_val if isinstance(deref(p), list)]
        mark = trail.mark()
        if unify(keys, ks, trail) and unify(values, vs, trail):
            yield (parent, None)
        trail.undo(mark)
    else:
        ks_val = deref(keys)
        vs_val = deref(values)
        if isinstance(ks_val, list) and isinstance(vs_val, list) and len(ks_val) == len(vs_val):
            result = [[k, v] for k, v in zip(ks_val, vs_val)]
            mark = trail.mark()
            if unify(pairs, result, trail):
                yield (parent, None)
            trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("PairKeys", 2)
def _pairs_keys__2(this_generator, parent, pairs, keys, trail):
    """pairs_keys(Pairs, Keys) — Keys are the first elements of each pair."""
    pairs_val = deref(pairs)
    if isinstance(pairs_val, list):
        ks = [deref(p)[0] for p in pairs_val if isinstance(deref(p), list)]
        mark = trail.mark()
        if unify(keys, ks, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("PairValues", 2)
def _pairs_values__2(this_generator, parent, pairs, values, trail):
    """pairs_values(Pairs, Values) — Values are the second elements of each pair."""
    pairs_val = deref(pairs)
    if isinstance(pairs_val, list):
        vs = [deref(p)[1] for p in pairs_val if isinstance(deref(p), list)]
        mark = trail.mark()
        if unify(values, vs, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


# ── call_goal/1,2,3 — invoke a goal closure (V2-9 lambdas) ──────────────────


def _make_call_goal_trampoline(extra_n: int):
    """Generate a native trampoline call_goal builtin for *extra_n* extra args."""
    def _call_goal_n(this_generator, parent, *args):
        # args = (goal, extra1, ..., extraN, trail)
        goal_val = deref(args[0])
        if callable(goal_val) or hasattr(goal_val, '_get_dispatch'):
            dispatch = _ensure_trampoline_dispatch(goal_val)
            derefed = [deref(a) for a in args[1:extra_n + 1]]
            trail = args[extra_n + 1]
            sg = StepGenerator(dispatch, this_generator, *derefed, trail)
            _st = yield (sg, None)
            while _st is not DONE:
                yield (parent, None)
                _st = yield (sg, None)
        yield (parent, DONE)
    return _call_goal_n


for _n in range(0, 8):  # extra_n=0..7 → arity 1..8
    _BUILTINS[("CallGoal", _n + 1)] = _make_call_goal_trampoline(_n)

# Call/1..8 — aliases: Call(Goal, A1, ...) = CallGoal(Goal, A1, ...)
for _n in range(1, 9):
    _key = ("CallGoal", _n)
    if _key in _BUILTINS:
        _BUILTINS[("Call", _n)] = _BUILTINS[_key]


# ── Higher-order list predicates (V2-11) ──────────────────────────────────────


@_trampoline_builtin("MapList", 2)
def _map_list__2(this_generator, parent, goal, lst, trail):
    """map_list(Goal, List) — Goal(Elem) succeeds for each element."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    if not isinstance(lst_val, list) or not (callable(goal_val) or hasattr(goal_val, '_get_dispatch')):
        yield (parent, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    for elem in lst_val:
        sg = StepGenerator(dispatch, this_generator, deref(elem), trail)
        _st = yield (sg, None)
        if _st is DONE:
            trail.undo(outer_mark)
            yield (parent, DONE)
            return
        # Got first solution — committed choice, move to next element
    yield (parent, None)
    trail.undo(outer_mark)
    yield (parent, DONE)


@_trampoline_builtin("MapList", 3)
def _map_list__3(this_generator, parent, goal, xs, ys, trail):
    """map_list(Goal, Xs, Ys) — Goal(X, Y) maps each X to Y."""
    xs_val = deref(xs)
    goal_val = deref(goal)
    if not isinstance(xs_val, list) or not (callable(goal_val) or hasattr(goal_val, '_get_dispatch')):
        yield (parent, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    results = []
    for x in xs_val:
        y = Var()
        sg = StepGenerator(dispatch, this_generator, deref(x), y, trail)
        _st = yield (sg, None)
        if _st is DONE:
            trail.undo(outer_mark)
            yield (parent, DONE)
            return
        results.append(deref(y))
    if unify(ys, results, trail):
        yield (parent, None)
    trail.undo(outer_mark)
    yield (parent, DONE)


@_trampoline_builtin("Filter", 3)
def _include__3(this_generator, parent, goal, lst, included, trail):
    """include(Goal, List, Included) — keep elements where Goal(Elem) succeeds."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    if not isinstance(lst_val, list) or not (callable(goal_val) or hasattr(goal_val, '_get_dispatch')):
        yield (parent, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    kept = []
    for elem in lst_val:
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, deref(elem), trail)
        _st = yield (sg, None)
        found = _st is not DONE
        trail.undo(mark)
        if found:
            kept.append(deref(elem))
    if unify(included, kept, trail):
        yield (parent, None)
    trail.undo(outer_mark)
    yield (parent, DONE)


@_trampoline_builtin("Exclude", 3)
def _exclude__3(this_generator, parent, goal, lst, excluded, trail):
    """exclude(Goal, List, Excluded) — keep elements where Goal(Elem) fails."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    if not isinstance(lst_val, list) or not (callable(goal_val) or hasattr(goal_val, '_get_dispatch')):
        yield (parent, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    kept = []
    for elem in lst_val:
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, deref(elem), trail)
        _st = yield (sg, None)
        found = _st is not DONE
        trail.undo(mark)
        if not found:
            kept.append(deref(elem))
    if unify(excluded, kept, trail):
        yield (parent, None)
    trail.undo(outer_mark)
    yield (parent, DONE)


@_trampoline_builtin("FoldLeft", 4)
def _foldl__4(this_generator, parent, goal, lst, v0, v, trail):
    """foldl(Goal, List, V0, V) — left fold with Goal(Elem, Acc0, Acc1)."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    if not isinstance(lst_val, list) or not (callable(goal_val) or hasattr(goal_val, '_get_dispatch')):
        yield (parent, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    acc = v0
    for elem in lst_val:
        next_acc = Var()
        sg = StepGenerator(dispatch, this_generator, deref(elem), deref(acc), next_acc, trail)
        _st = yield (sg, None)
        if _st is DONE:
            trail.undo(outer_mark)
            yield (parent, DONE)
            return
        acc = next_acc
    if unify(v, deref(acc), trail):
        yield (parent, None)
    trail.undo(outer_mark)
    yield (parent, DONE)



# ── I/O builtins (V2-15) ──────────────────────────────────────────────────────


def _format_term_for_io(val):
    """Format a dereffed value for I/O output.

    Strings pass through as-is (supports f-strings naturally).
    Other values use str() which auto-derefs Vars via __str__.
    """
    if isinstance(val, str):
        return val
    return str(val)


@_builtin("Write", 1)
def _write__1(term, trail, k):
    """Write(Term) — print dereffed term to stdout (no newline).

    Strings are printed without quotes.  Vars are auto-dereffed.
    Works naturally with f-strings: Write(f"X is {X_}").
    """
    val = deref(term)
    _sys.stdout.write(_format_term_for_io(val))
    _sys.stdout.flush()
    yield None


@_builtin("Writeln", 1)
def _writeln__1(term, trail, k):
    """Writeln(Term) — print dereffed term to stdout with newline.

    Strings are printed without quotes.  Vars are auto-dereffed.
    Works naturally with f-strings: Writeln(f"X is {X_}").
    """
    val = deref(term)
    print(_format_term_for_io(val))
    yield None


@_builtin("PrintTerm", 1)
def _print_term__1(term, trail, k):
    """PrintTerm(Term) — print structured term representation with newline.

    Uses term_str() for Prolog-style output showing term structure
    (e.g., functors, lists, operators).  Vars show as Var(_N).
    """
    from clausal.logic.solve import _deref_walk
    val = _deref_walk(term)
    print(_term_str(val))
    yield None


@_builtin("Nl", 0)
def _nl__0(trail, k):
    """Nl — print a newline."""
    print()
    yield None


@_builtin("Tab", 1)
def _tab__1(n, trail, k):
    """Tab(N) — print N spaces."""
    n_val = deref(n)
    if is_var(n_val) or not isinstance(n_val, int):
        return
    _sys.stdout.write(" " * n_val)
    _sys.stdout.flush()
    yield None


@_builtin("WriteToString", 2)
def _write_to_string__2(term, result, trail, k):
    """WriteToString(Term, Result) — unify Result with the string representation of Term.

    Vars are auto-dereffed.  Strings pass through as-is.
    """
    val = deref(term)
    s = _format_term_for_io(val)
    mark = trail.mark()
    if unify(result, s, trail):
        yield None
    trail.undo(mark)


@_builtin("TermToString", 2)
def _term_to_string__2(term, result, trail, k):
    """TermToString(Term, Result) — unify Result with structured term_str representation."""
    from clausal.logic.solve import _deref_walk
    val = _deref_walk(term)
    s = _term_str(val)
    mark = trail.mark()
    if unify(result, s, trail):
        yield None
    trail.undo(mark)


# ─── DCG: phrase/2 and phrase/3 ──────────────────────────────────────────────


@_trampoline_builtin("phrase", 2)
def _phrase__2(this_generator, parent, rule_body, list_arg, trail):
    """phrase(RuleBody, List) — invoke DCG rule, must consume entire list."""
    rule_val = deref(rule_body)
    list_val = deref(list_arg)

    if isinstance(rule_val, type) and hasattr(rule_val, '_get_dispatch'):
        # Class reference (0 extra args): phrase(greeting, [hello, world])
        dispatch = rule_val._get_dispatch()
        sg = StepGenerator(dispatch, this_generator, list_val, [], trail)
    elif is_term_instance(rule_val):
        # Instance with args: phrase(digit(D_), [3, plus, 4])
        cls = type(rule_val)
        dispatch = cls._get_dispatch()
        fields = term_field_names(rule_val)
        user_args = [deref(getattr(rule_val, f)) for f in fields[:-2]]
        sg = StepGenerator(dispatch, this_generator, *user_args, list_val, [], trail)
    else:
        yield (parent, DONE)
        return

    _st = yield (sg, None)
    while _st is not DONE:
        yield (parent, None)
        _st = yield (sg, None)
    yield (parent, DONE)


@_trampoline_builtin("phrase", 3)
def _phrase__3(this_generator, parent, rule_body, list_arg, rest_arg, trail):
    """phrase(RuleBody, List, Rest) — invoke DCG rule, partial parse."""
    rule_val = deref(rule_body)
    list_val = deref(list_arg)
    rest_val = deref(rest_arg)

    if isinstance(rule_val, type) and hasattr(rule_val, '_get_dispatch'):
        dispatch = rule_val._get_dispatch()
        sg = StepGenerator(dispatch, this_generator, list_val, rest_val, trail)
    elif is_term_instance(rule_val):
        cls = type(rule_val)
        dispatch = cls._get_dispatch()
        fields = term_field_names(rule_val)
        user_args = [deref(getattr(rule_val, f)) for f in fields[:-2]]
        sg = StepGenerator(dispatch, this_generator, *user_args, list_val, rest_val, trail)
    else:
        yield (parent, DONE)
        return

    _st = yield (sg, None)
    while _st is not DONE:
        yield (parent, None)
        _st = yield (sg, None)
    yield (parent, DONE)


__all__ = [
    "BuiltinPredicate",
    "get_builtin_predicate",
    "get_builtin_dispatch",
    "_BUILTINS",
    "_DB_BUILTINS",
]
