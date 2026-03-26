"""Core term inspection builtins: Functor/3, Arg/3, Unpack/2, CopyTerm/2,
TermVariables/2, NumberVars/3."""

from __future__ import annotations

from typing import Any

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.predicate import PredicateMeta, is_term_instance, term_field_names
from clausal.terms import Compound, KWTerm

from clausal.logic.builtins._registry import _builtin
from clausal.logic.builtins._helpers import _functor_name, _arity, _nth_arg, _args_list


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
            functor_str = name_val.__name__ if isinstance(name_val, PredicateMeta) else str(name_val)
            args = tuple(Var() for _ in range(arity_val))
            constructed = Compound(functor_str, args)
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
            functor_str = f_val.__name__ if isinstance(f_val, PredicateMeta) else str(f_val)
            constructed = Compound(functor_str, tuple(args_vals))
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
    # Zero-arity PredicateMeta atoms: ground, return as-is
    if isinstance(term, type) and isinstance(term, PredicateMeta) and not term._fields:
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
    # Zero-arity PredicateMeta atoms: no variables
    if isinstance(term, type) and isinstance(term, PredicateMeta) and not term._fields:
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


# ── GenSym/2 ──────────────────────────────────────────────────────────────────

import threading

_gensym_counters: dict[str, int] = {}
_gensym_lock = threading.Lock()


@_builtin("GenSym", 2)
def _gensym__2(prefix, atom, trail, k):
    """GenSym(Prefix, Atom) — generate a unique atom by appending a counter.

    Counter is global and monotonically increasing. NOT trailed — survives
    backtracking. This is intentional and matches Prolog's gensym/2 semantics.
    """
    prefix_d = deref(prefix)
    if is_var(prefix_d) or not isinstance(prefix_d, str):
        return
    with _gensym_lock:
        count = _gensym_counters.get(prefix_d, 0) + 1
        _gensym_counters[prefix_d] = count
    result = f"{prefix_d}_{count}"
    if unify(atom, result, trail):
        yield None
