"""Keyword-term introspection builtins (WK-5): Vary/3, Extend/3,
UnboundKeys/2, Signature/3."""

from __future__ import annotations

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.predicate import is_term_instance, term_field_names
from clausal.terms import KWTerm

from clausal.logic.builtins._registry import _builtin, _db_builtin


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


@_db_builtin("Signature", 3, fields=("functor_name", "arity", "names"))
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
