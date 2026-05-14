"""Core term inspection builtins: functor/3, arg/3, unpack/2, copy_term/2,
term_variables/2, numbervars/3."""

from __future__ import annotations

from typing import Any

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.predicate import PredicateMeta, is_term_instance, term_field_names, make_predicate
from clausal.terms import Compound, KWTerm

from clausal.logic.builtins._registry import _builtin
from clausal.logic.builtins._helpers import _functor_name, _arity, _nth_arg, _args_list


# ── Python fallbacks for _copy_term / _collect_vars ───────────────────────────
# These are the reference implementations.  The C versions in _variables.c are
# used when available.  Keep these in sync with any changes to the C code.


def _copy_term_py(term: Any, var_map: dict) -> Any:
    """Recursively copy *term*, replacing each unbound Var with a fresh one.

    *var_map* maps original Var id -> fresh Var so that sharing is preserved.
    """
    term = deref(term)
    if is_var(term):
        vid = id(term)
        if vid not in var_map:
            var_map[vid] = Var()
        return var_map[vid]
    if isinstance(term, (bool, int, float, str, bytes)) or term is None:
        return term
    if isinstance(term, type) and isinstance(term, PredicateMeta) and not term._fields:
        return term
    if isinstance(term, list):
        return [_copy_term_py(e, var_map) for e in term]
    if isinstance(term, Compound):
        return Compound(term.functor, tuple(_copy_term_py(a, var_map) for a in term.args))
    if isinstance(term, KWTerm):
        return KWTerm(term.functor, **{k: _copy_term_py(v, var_map) for k, v in term.items()})
    if is_term_instance(term):
        return type(term)(**{
            name: _copy_term_py(getattr(term, name), var_map)
            for name in term_field_names(term)
        })
    return term


def _collect_vars_py(term: Any, result: list, _seen: set | None = None) -> None:
    """Collect all unbound Vars in *term* into *result*, left-to-right order."""
    if _seen is None:
        _seen = set()
    term = deref(term)
    if is_var(term):
        vid = id(term)
        if vid not in _seen:
            _seen.add(vid)
            result.append(term)
        return
    if isinstance(term, (bool, int, float, str, bytes)) or term is None:
        return
    if isinstance(term, type) and isinstance(term, PredicateMeta) and not term._fields:
        return
    if isinstance(term, list):
        for e in term:
            _collect_vars_py(e, result, _seen)
        return
    if isinstance(term, Compound):
        for a in term.args:
            _collect_vars_py(a, result, _seen)
        return
    if isinstance(term, KWTerm):
        for v in term.values():
            _collect_vars_py(v, result, _seen)
        return
    if is_term_instance(term):
        for name in term_field_names(term):
            _collect_vars_py(getattr(term, name), result, _seen)


# ── C-accelerated versions (with Python fallback) ────────────────────────────

_copy_term_impl = _copy_term_py
_collect_vars_impl = _collect_vars_py
try:
    from clausal.logic.variables._variables import (
        _copy_term_impl,
        _collect_vars_impl,
    )
except ImportError:
    pass

# Re-export for callers that import _copy_term directly (e.g. specialization.py)
_copy_term = _copy_term_impl


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


@_builtin("arg", 3)
def _arg__3(n, term, arg_out, trail, k):
    """arg(N, Term, arg) — unify arg with the N-th argument of Term (1-based)."""
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


@_builtin("unpack", 2)
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


@_builtin("copy_term", 2)
def _copy_term__2(original, copy, trail, k):
    """copy_term(Original, Copy) — unify Copy with a deep copy of Original with fresh Vars."""
    orig_val = deref(original)
    copied = _copy_term_impl(orig_val, {})
    mark = trail.mark()
    if unify(copy, copied, trail):
        yield None
    trail.undo(mark)


@_builtin("term_variables", 2)
def _term_variables__2(term, vars_out, trail, k):
    """term_variables(Term, Vars) — unify Vars with list of unbound variables in Term."""
    term_val = deref(term)
    result: list = []
    _collect_vars_impl(term_val, result)
    mark = trail.mark()
    if unify(vars_out, result, trail):
        yield None
    trail.undo(mark)


@_builtin("numbervars", 3)
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
    _collect_vars_impl(term_val, vars_list)
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


# ── gensym/2 ──────────────────────────────────────────────────────────────────

import threading

_gensym_counters: dict[str, int] = {}
_gensym_lock = threading.Lock()


@_builtin("gensym", 2)
def _gensym__2(prefix, atom, trail, k):
    """gensym(Prefix, Atom) — generate a unique atom by appending a counter.

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


# ── global_atom/2 ─────────────────────────────────────────────────────────────


@_builtin("global_atom", 2)
def _global_atom__2(name, atom, trail, k):
    """global_atom(Name, Atom) — reflect on the process-wide global atom dict.

    Exposes ``clausal.import_hook.predicate_builtins``, the dict that seeds
    every fresh predicate module's globals.  Modes:

      (+Name, -Atom): mint-on-demand.  Look Name up in the global dict; if
        absent, create a fresh ``make_predicate(Name, [])`` and install it.
        Unify Atom with the resulting class.
      (+Name, +Atom): guard.  Succeed iff ``predicate_builtins[Name] is Atom``.
      (-Name, +Atom): reverse lookup.  Succeed iff Atom is a PredicateMeta
        whose ``__name__`` resolves back to Atom in the dict (i.e. Atom is
        genuinely the registered global, not a module-local namesake); unify
        Name with that name.
      (-Name, -Atom): enumerate.  Yield one solution per ``(name, cls)`` pair
        where the value is a PredicateMeta of arity 0.  Order not guaranteed.
    """
    # Lazy import: clausal.import_hook depends transitively on this package,
    # so a top-level import here would create a cycle at package load time.
    from clausal.import_hook import predicate_builtins

    name_val = deref(name)
    atom_val = deref(atom)
    name_bound = not is_var(name_val)
    atom_bound = not is_var(atom_val)

    if name_bound:
        if not isinstance(name_val, str):
            return
        if atom_bound:
            # Guard mode: succeed iff atom_val IS the registered global.
            if predicate_builtins.get(name_val) is atom_val:
                yield None
            return
        # Mint-on-demand mode.
        cls = predicate_builtins.setdefault(
            name_val, make_predicate(name_val, [])
        )
        mark = trail.mark()
        if unify(atom, cls, trail):
            yield None
        trail.undo(mark)
        return

    # name is unbound.
    if atom_bound:
        # Reverse-lookup mode.  Atom must be a PredicateMeta whose __name__
        # resolves back to Atom in the global dict.
        if not isinstance(atom_val, PredicateMeta):
            return
        cls_name = atom_val.__name__
        if predicate_builtins.get(cls_name) is not atom_val:
            return
        mark = trail.mark()
        if unify(name, cls_name, trail):
            yield None
        trail.undo(mark)
        return

    # Both unbound — enumerate arity-0 PredicateMeta entries.
    # Snapshot keys so concurrent minting elsewhere can't perturb iteration.
    for key, val in list(predicate_builtins.items()):
        if not isinstance(val, PredicateMeta) or val._fields:
            continue
        mark = trail.mark()
        if unify(name, key, trail) and unify(atom, val, trail):
            yield None
        trail.undo(mark)
