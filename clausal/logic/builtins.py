"""clausal.logic.builtins — built-in and standard-library predicates (Step 8).

Built-ins are Python generator functions with the standard simple-mode
dispatch signature::

    def predicate__N(arg0, …, argN-1, trail, k): …

They yield ``None`` for each solution.  Stateless built-ins are stored in
``_BUILTINS``.  Built-ins that need a reference to the live database (assertz,
asserta, retract, signature) are stored in ``_DB_BUILTINS`` as factory
callables; ``get_builtin_dispatch`` passes the database when creating them.

``Database.table_for`` calls ``get_builtin_dispatch(functor, arity, db)`` as a
fallback when a predicate is not found locally, so built-ins are available in
every database without requiring explicit registration.

Built-ins implemented
---------------------
Core inspection
    functor/3   — decompose/compose term functor name and arity
    arg/3       — Nth argument of a compound term (1-based)
    univ/2      — T =.. [Functor | Args]  (term ↔ list)

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
"""

from __future__ import annotations

import dataclasses
from typing import Any, Callable

from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.terms import Compound, KWTerm


# ── Registry dicts ─────────────────────────────────────────────────────────────
# _BUILTINS: stateless dispatch functions  {(functor, arity) → fn}
# _DB_BUILTINS: factory callables         {(functor, arity) → fn(db) → dispatch_fn}

_BUILTINS: dict[tuple[str, int], Callable] = {}
_DB_BUILTINS: dict[tuple[str, int], Callable] = {}


def _builtin(functor: str, arity: int):
    """Decorator: register a function as a stateless built-in."""
    def decorator(fn: Callable) -> Callable:
        _BUILTINS[(functor, arity)] = fn
        return fn
    return decorator


def _db_builtin(functor: str, arity: int):
    """Decorator: register a factory as a db-dependent built-in."""
    def decorator(factory: Callable) -> Callable:
        _DB_BUILTINS[(functor, arity)] = factory
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

    # dataclass ↔ dataclass (same type)
    if (
        dataclasses.is_dataclass(t1)
        and dataclasses.is_dataclass(t2)
        and not isinstance(t1, type)
        and not isinstance(t2, type)
        and type(t1) is type(t2)
    ):
        fields = dataclasses.fields(t1)
        mark = trail.mark()
        for f in fields:
            if not structural_unify(getattr(t1, f.name), getattr(t2, f.name), trail):
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


def get_builtin_dispatch(
    functor: str, arity: int, db: Any
) -> Callable | None:
    """Return the dispatch function for a built-in predicate, or None.

    Called by ``Database.table_for`` when a predicate is not found locally.
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
    if dataclasses.is_dataclass(term) and not isinstance(term, type):
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
    if dataclasses.is_dataclass(term) and not isinstance(term, type):
        return len(dataclasses.fields(term))
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
    if dataclasses.is_dataclass(term) and not isinstance(term, type):
        fields = dataclasses.fields(term)
        if n < 1 or n > len(fields):
            raise IndexError(f"arg index {n} out of range for {term!r}")
        return getattr(term, fields[n - 1].name)
    if isinstance(term, list) and len(term) >= n >= 1:
        return term[n - 1]
    raise IndexError(f"arg index {n} out of range for {term!r}")


def _args_list(term: Any) -> list:
    """Return the argument list of a compound term."""
    if isinstance(term, Compound):
        return list(term.args)
    if isinstance(term, KWTerm):
        return list(term.values())
    if dataclasses.is_dataclass(term) and not isinstance(term, type):
        return [getattr(term, f.name) for f in dataclasses.fields(term)]
    return []


def _is_compound(term: Any) -> bool:
    return (
        isinstance(term, (Compound, KWTerm))
        or (dataclasses.is_dataclass(term) and not isinstance(term, type))
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
    if dataclasses.is_dataclass(term) and not isinstance(term, type):
        return all(_is_ground(getattr(term, f.name)) for f in dataclasses.fields(term))
    return True


# ── Core inspection ────────────────────────────────────────────────────────────


@_builtin("functor", 3)
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


@_builtin("arg", 3)
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


@_builtin("univ", 2)
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


# ── Runtime database manipulation ─────────────────────────────────────────────


def _normalize_fact_clause(term: Any):
    """Convert a ground Compound fact to Var+Is form for output-mode queries.

    ``Compound("f", (1, 2))`` → head=Compound("f", (v0, v1)), body=[Is(v0,1), Is(v1,2)]

    This makes dynamically asserted facts queryable in output mode (with unbound
    Var arguments), matching standard Prolog semantics for assert.
    Facts asserted via the DSL already use Var+Is form via the term transformer.
    """
    from clausal.logic.database import Clause  # avoid top-level import cycle
    from clausal.terms import Is as _Is

    if isinstance(term, Compound):
        new_args = []
        body: list = []
        for arg in term.args:
            arg_val = deref(arg)
            if not is_var(arg_val):
                v = Var()
                new_args.append(v)
                body.append(_Is(left=v, right=arg_val))
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


@_db_builtin("assertz", 1)
def _assertz_factory(db):
    """assertz(Term) — add Term as a fact at end of its predicate's clause list.

    Ground facts are automatically normalized to Var+Is form so they are
    queryable in output mode (matching standard Prolog assert semantics).
    """
    from clausal.logic.database import head_key
    from clausal.logic.compiler import compile_predicate

    def assertz__1(term, trail, k):
        term_val = deref(term)
        if is_var(term_val):
            return
        clause = _build_clause(term_val)
        functor, arity = head_key(clause.head)
        db.assertz(clause)
        clauses = db.clauses_for(functor, arity)
        compile_predicate(functor, arity, clauses, db)
        yield None

    return assertz__1


@_db_builtin("asserta", 1)
def _asserta_factory(db):
    """asserta(Term) — add Term as a fact at front of its predicate's clause list."""
    from clausal.logic.database import head_key
    from clausal.logic.compiler import compile_predicate

    def asserta__1(term, trail, k):
        term_val = deref(term)
        if is_var(term_val):
            return
        clause = _build_clause(term_val)
        functor, arity = head_key(clause.head)
        db.asserta(clause)
        clauses = db.clauses_for(functor, arity)
        compile_predicate(functor, arity, clauses, db)
        yield None

    return asserta__1


@_db_builtin("retract", 1)
def _retract_factory(db):
    """retract(Term) — remove the first clause whose head unifies with Term.

    Uses unification (not structural equality) so it correctly handles
    normalized facts whose heads contain Var placeholders.  Bindings
    from the head unification are undone after the clause is removed
    (retract is not backtrackable in this implementation).
    """
    from clausal.logic.database import head_key
    from clausal.logic.compiler import compile_predicate

    def retract__1(term, trail, k):
        term_val = deref(term)
        if is_var(term_val):
            return
        try:
            functor, arity = head_key(term_val)
        except TypeError:
            return
        tbl = db._tables.get((functor, arity))
        if tbl is None:
            return
        # Find first clause whose head unifies with term_val (and whose
        # Is-body goals are consistent with that unification).
        from clausal.terms import Is as _Is  # avoid top-level cycle
        for i, clause in enumerate(tbl._clauses):
            tmp_trail = Trail()
            mark = tmp_trail.mark()
            if not structural_unify(term_val, clause.head, tmp_trail):
                tmp_trail.undo(mark)
                continue
            # Verify body: check that Is goals are consistent with the head
            # unification.  We check only Is goals (normalization artefacts).
            body_ok = True
            for goal in clause.body:
                if isinstance(goal, _Is):
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
            del tbl._clauses[i]
            tbl.dispatch_fn = None
            clauses = db.clauses_for(functor, arity)
            if clauses:
                compile_predicate(functor, arity, clauses, db)
            yield None
            return  # retract is not backtrackable

    return retract__1


# ── WK-5: Keyword-term introspection ──────────────────────────────────────────


@_builtin("vary", 3)
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
    if dataclasses.is_dataclass(term_val) and not isinstance(term_val, type):
        try:
            result = dataclasses.replace(term_val, **overrides_val)
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


@_builtin("extend", 3)
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


@_builtin("unbound_keys", 2)
def _unbound_keys__2(term, keys_list, trail, k):
    """unbound_keys(Term, Keys) — Keys is the list of field names holding unbound Vars.

    Works for functor dataclass instances and KWTerm.
    """
    term_val = deref(term)
    if is_var(term_val):
        return
    keys: list[str] = []
    if dataclasses.is_dataclass(term_val) and not isinstance(term_val, type):
        for f in dataclasses.fields(term_val):
            if is_var(deref(getattr(term_val, f.name))):
                keys.append(f.name)
    elif isinstance(term_val, KWTerm):
        for fname, val in term_val.items():
            if is_var(deref(val)):
                keys.append(fname)
    mark = trail.mark()
    if unify(keys_list, keys, trail):
        yield None
    trail.undo(mark)


@_db_builtin("signature", 3)
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


# ── Standard library: type checks ─────────────────────────────────────────────


@_builtin("var", 1)
def _var__1(x, trail, k):
    """var(X) — succeeds if X is an unbound logic variable."""
    if is_var(deref(x)):
        yield None


@_builtin("nonvar", 1)
def _nonvar__1(x, trail, k):
    """nonvar(X) — succeeds if X is bound (not an unbound Var)."""
    if not is_var(deref(x)):
        yield None


@_builtin("atom", 1)
def _atom__1(x, trail, k):
    """atom(X) — succeeds if X is a string (Prolog atom)."""
    x_val = deref(x)
    if not is_var(x_val) and isinstance(x_val, str):
        yield None


@_builtin("number", 1)
def _number__1(x, trail, k):
    """number(X) — succeeds if X is an int or float (not bool)."""
    x_val = deref(x)
    if (
        not is_var(x_val)
        and isinstance(x_val, (int, float))
        and not isinstance(x_val, bool)
    ):
        yield None


@_builtin("integer", 1)
def _integer__1(x, trail, k):
    """integer(X) — succeeds if X is an int (not bool)."""
    x_val = deref(x)
    if not is_var(x_val) and isinstance(x_val, int) and not isinstance(x_val, bool):
        yield None


@_builtin("float_", 1)
def _float__1(x, trail, k):
    """float_(X) — succeeds if X is a Python float."""
    x_val = deref(x)
    if not is_var(x_val) and isinstance(x_val, float):
        yield None


@_builtin("string", 1)
def _string__1(x, trail, k):
    """string(X) — alias for atom/1: succeeds if X is a Python str."""
    x_val = deref(x)
    if not is_var(x_val) and isinstance(x_val, str):
        yield None


@_builtin("compound", 1)
def _compound__1(x, trail, k):
    """compound(X) — succeeds if X is a compound term with arity > 0."""
    x_val = deref(x)
    if is_var(x_val):
        return
    if isinstance(x_val, Compound) and len(x_val.args) > 0:
        yield None
    elif isinstance(x_val, KWTerm) and len(x_val) > 0:
        yield None
    elif (
        dataclasses.is_dataclass(x_val)
        and not isinstance(x_val, type)
        and len(dataclasses.fields(x_val)) > 0
    ):
        yield None


@_builtin("callable", 1)
def _callable__1(x, trail, k):
    """callable(X) — succeeds if X is an atom or compound."""
    x_val = deref(x)
    if is_var(x_val):
        return
    if isinstance(x_val, (str, Compound, KWTerm)):
        yield None
    elif dataclasses.is_dataclass(x_val) and not isinstance(x_val, type):
        yield None


@_builtin("is_list", 1)
def _is_list__1(x, trail, k):
    """is_list(X) — succeeds if X is a Python list."""
    if isinstance(deref(x), list):
        yield None


@_builtin("ground", 1)
def _ground__1(x, trail, k):
    """ground(X) — succeeds if X contains no unbound Vars."""
    if _is_ground(deref(x)):
        yield None


# ── Standard library: arithmetic ──────────────────────────────────────────────


@_builtin("between", 3)
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


@_builtin("succ", 2)
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


@_builtin("plus", 3)
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


@_builtin("abs_", 2)
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


@_builtin("max_", 3)
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


@_builtin("min_", 3)
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


# ── Standard library: list predicates ─────────────────────────────────────────


@_builtin("member", 2)
def _member__2(elem, lst, trail, k):
    """member(Elem, List) — Elem is a member of List; enumerates on backtrack."""
    lst_val = deref(lst)
    if not isinstance(lst_val, list):
        return
    for item in lst_val:
        mark = trail.mark()
        if unify(elem, item, trail):
            yield None
        trail.undo(mark)


@_builtin("memberchk", 2)
def _memberchk__2(elem, lst, trail, k):
    """memberchk(Elem, List) — like member/2 but commits to the first match."""
    lst_val = deref(lst)
    if not isinstance(lst_val, list):
        return
    for item in lst_val:
        mark = trail.mark()
        if unify(elem, item, trail):
            yield None
            return
        trail.undo(mark)


@_builtin("append", 3)
def _append__3(l1, l2, l3, trail, k):
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
            yield None
        trail.undo(mark)
    elif isinstance(l1_val, list) and isinstance(l3_val, list):
        # L1 and L3 known: compute L2
        n = len(l1_val)
        if len(l3_val) >= n and l3_val[:n] == l1_val:
            mark = trail.mark()
            if unify(l2, l3_val[n:], trail):
                yield None
            trail.undo(mark)
    elif isinstance(l3_val, list):
        # Only L3 known: enumerate all splits
        for i in range(len(l3_val) + 1):
            mark = trail.mark()
            if unify(l1, l3_val[:i], trail) and unify(l2, l3_val[i:], trail):
                yield None
            trail.undo(mark)


@_builtin("length", 2)
def _length__2(lst, n, trail, k):
    """length(List, N) — N is the length of List."""
    lst_val = deref(lst)
    n_val = deref(n)
    if isinstance(lst_val, list):
        mark = trail.mark()
        if unify(n, len(lst_val), trail):
            yield None
        trail.undo(mark)
    elif not is_var(n_val) and isinstance(n_val, int) and n_val >= 0:
        result = [Var() for _ in range(n_val)]
        mark = trail.mark()
        if unify(lst, result, trail):
            yield None
        trail.undo(mark)


@_builtin("last", 2)
def _last__2(lst, elem, trail, k):
    """last(List, Elem) — Elem is the last element of List."""
    lst_val = deref(lst)
    if isinstance(lst_val, list) and len(lst_val) > 0:
        mark = trail.mark()
        if unify(elem, lst_val[-1], trail):
            yield None
        trail.undo(mark)


@_builtin("reverse", 2)
def _reverse__2(lst, rev, trail, k):
    """reverse(List, Rev) — Rev is the reverse of List."""
    lst_val = deref(lst)
    if isinstance(lst_val, list):
        mark = trail.mark()
        if unify(rev, list(reversed(lst_val)), trail):
            yield None
        trail.undo(mark)


@_builtin("nth0", 3)
def _nth0__3(n, lst, elem, trail, k):
    """nth0(N, List, Elem) — Elem is the N-th element of List (0-based)."""
    n_val = deref(n)
    lst_val = deref(lst)
    if not isinstance(lst_val, list):
        return
    if not is_var(n_val):
        if not isinstance(n_val, int) or n_val < 0 or n_val >= len(lst_val):
            return
        mark = trail.mark()
        if unify(elem, lst_val[n_val], trail):
            yield None
        trail.undo(mark)
    else:
        for i, item in enumerate(lst_val):
            mark = trail.mark()
            if unify(n, i, trail) and unify(elem, item, trail):
                yield None
            trail.undo(mark)


@_builtin("nth1", 3)
def _nth1__3(n, lst, elem, trail, k):
    """nth1(N, List, Elem) — Elem is the N-th element of List (1-based)."""
    n_val = deref(n)
    lst_val = deref(lst)
    if not isinstance(lst_val, list):
        return
    if not is_var(n_val):
        if not isinstance(n_val, int) or n_val < 1 or n_val > len(lst_val):
            return
        mark = trail.mark()
        if unify(elem, lst_val[n_val - 1], trail):
            yield None
        trail.undo(mark)
    else:
        for i, item in enumerate(lst_val):
            mark = trail.mark()
            if unify(n, i + 1, trail) and unify(elem, item, trail):
                yield None
            trail.undo(mark)


@_builtin("flatten", 2)
def _flatten__2(lst, flat, trail, k):
    """flatten(List, Flat) — Flat is the flat list of all atoms in List."""
    lst_val = deref(lst)
    if is_var(lst_val):
        return
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
        yield None
    trail.undo(mark)


@_builtin("msort", 2)
def _msort__2(lst, sorted_lst, trail, k):
    """msort(List, Sorted) — Sorted is List sorted, preserving duplicates."""
    lst_val = deref(lst)
    if not isinstance(lst_val, list):
        return
    try:
        result = sorted(lst_val)
    except TypeError:
        # Mixed types: use string representation as tiebreaker
        result = sorted(lst_val, key=lambda x: (type(x).__name__, repr(x)))
    mark = trail.mark()
    if unify(sorted_lst, result, trail):
        yield None
    trail.undo(mark)


@_builtin("sort", 2)
def _sort__2(lst, sorted_lst, trail, k):
    """sort(List, Sorted) — Sorted is List sorted with duplicates removed."""
    lst_val = deref(lst)
    if not isinstance(lst_val, list):
        return
    # Deduplicate preserving order, then sort
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
        yield None
    trail.undo(mark)


@_builtin("permutation", 2)
def _permutation__2(lst, perm, trail, k):
    """permutation(List, Perm) — Perm is a permutation of List."""
    import itertools
    lst_val = deref(lst)
    if not isinstance(lst_val, list):
        return
    for p in itertools.permutations(lst_val):
        mark = trail.mark()
        if unify(perm, list(p), trail):
            yield None
        trail.undo(mark)


@_builtin("select", 3)
def _select__3(elem, lst, rest, trail, k):
    """select(Elem, List, Rest) — Elem is in List, Rest is List without one occurrence."""
    lst_val = deref(lst)
    if not isinstance(lst_val, list):
        return
    for i, item in enumerate(lst_val):
        mark = trail.mark()
        remainder = lst_val[:i] + lst_val[i + 1:]
        if unify(elem, item, trail) and unify(rest, remainder, trail):
            yield None
        trail.undo(mark)


@_builtin("subtract", 3)
def _subtract__3(set1, set2, diff, trail, k):
    """subtract(Set1, Set2, Diff) — Diff is Set1 minus elements in Set2."""
    s1 = deref(set1)
    s2 = deref(set2)
    if not isinstance(s1, list) or not isinstance(s2, list):
        return
    result = [x for x in s1 if x not in s2]
    mark = trail.mark()
    if unify(diff, result, trail):
        yield None
    trail.undo(mark)


@_builtin("intersection", 3)
def _intersection__3(set1, set2, inter, trail, k):
    """intersection(Set1, Set2, Inter) — Inter is the intersection of Set1 and Set2."""
    s1 = deref(set1)
    s2 = deref(set2)
    if not isinstance(s1, list) or not isinstance(s2, list):
        return
    result = [x for x in s1 if x in s2]
    mark = trail.mark()
    if unify(inter, result, trail):
        yield None
    trail.undo(mark)


@_builtin("union", 3)
def _union__3(set1, set2, uni, trail, k):
    """union(Set1, Set2, Union) — Union is Set1 ∪ Set2 (no duplicates)."""
    s1 = deref(set1)
    s2 = deref(set2)
    if not isinstance(s1, list) or not isinstance(s2, list):
        return
    result = list(s1)
    for x in s2:
        if x not in result:
            result.append(x)
    mark = trail.mark()
    if unify(uni, result, trail):
        yield None
    trail.undo(mark)


@_builtin("list_to_set", 2)
def _list_to_set__2(lst, set_out, trail, k):
    """list_to_set(List, Set) — Set is List with duplicates removed (order preserved)."""
    lst_val = deref(lst)
    if not isinstance(lst_val, list):
        return
    seen: list = []
    for x in lst_val:
        if x not in seen:
            seen.append(x)
    mark = trail.mark()
    if unify(set_out, seen, trail):
        yield None
    trail.undo(mark)


@_builtin("sum_list", 2)
def _sum_list__2(lst, total, trail, k):
    """sum_list(List, Total) — Total is the sum of all numbers in List."""
    lst_val = deref(lst)
    if not isinstance(lst_val, list):
        return
    try:
        s = sum(deref(x) for x in lst_val)
    except TypeError:
        return
    mark = trail.mark()
    if unify(total, s, trail):
        yield None
    trail.undo(mark)


@_builtin("max_list", 2)
def _max_list__2(lst, maximum, trail, k):
    """max_list(List, Max) — Max is the maximum element of List."""
    lst_val = deref(lst)
    if not isinstance(lst_val, list) or len(lst_val) == 0:
        return
    try:
        m = max(deref(x) for x in lst_val)
    except TypeError:
        return
    mark = trail.mark()
    if unify(maximum, m, trail):
        yield None
    trail.undo(mark)


@_builtin("min_list", 2)
def _min_list__2(lst, minimum, trail, k):
    """min_list(List, Min) — Min is the minimum element of List."""
    lst_val = deref(lst)
    if not isinstance(lst_val, list) or len(lst_val) == 0:
        return
    try:
        m = min(deref(x) for x in lst_val)
    except TypeError:
        return
    mark = trail.mark()
    if unify(minimum, m, trail):
        yield None
    trail.undo(mark)


# ── Standard library: pair helpers ────────────────────────────────────────────


@_builtin("pairs_keys_values", 3)
def _pairs_keys_values__3(pairs, keys, values, trail, k):
    """pairs_keys_values(Pairs, Keys, Values) — Pairs is a list of [K, V] lists."""
    pairs_val = deref(pairs)
    if isinstance(pairs_val, list):
        ks = [deref(p)[0] for p in pairs_val if isinstance(deref(p), list)]
        vs = [deref(p)[1] for p in pairs_val if isinstance(deref(p), list)]
        mark = trail.mark()
        if unify(keys, ks, trail) and unify(values, vs, trail):
            yield None
        trail.undo(mark)
    else:
        ks_val = deref(keys)
        vs_val = deref(values)
        if isinstance(ks_val, list) and isinstance(vs_val, list):
            if len(ks_val) != len(vs_val):
                return
            result = [[k, v] for k, v in zip(ks_val, vs_val)]
            mark = trail.mark()
            if unify(pairs, result, trail):
                yield None
            trail.undo(mark)


@_builtin("pairs_keys", 2)
def _pairs_keys__2(pairs, keys, trail, k):
    """pairs_keys(Pairs, Keys) — Keys are the first elements of each pair."""
    pairs_val = deref(pairs)
    if not isinstance(pairs_val, list):
        return
    ks = [deref(p)[0] for p in pairs_val if isinstance(deref(p), list)]
    mark = trail.mark()
    if unify(keys, ks, trail):
        yield None
    trail.undo(mark)


@_builtin("pairs_values", 2)
def _pairs_values__2(pairs, values, trail, k):
    """pairs_values(Pairs, Values) — Values are the second elements of each pair."""
    pairs_val = deref(pairs)
    if not isinstance(pairs_val, list):
        return
    vs = [deref(p)[1] for p in pairs_val if isinstance(deref(p), list)]
    mark = trail.mark()
    if unify(values, vs, trail):
        yield None
    trail.undo(mark)


__all__ = [
    "get_builtin_dispatch",
    "_BUILTINS",
    "_DB_BUILTINS",
]
