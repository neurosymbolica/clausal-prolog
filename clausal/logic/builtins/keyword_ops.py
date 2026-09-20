"""Keyword-term introspection builtins (WK-5): vary/3, extend/3,
unbound_keys/2, signature/3."""

from __future__ import annotations

from clausal.logic.cells import (
    is_chars, chars_text,                  # stage 1: the chars carrier
    compound_cell_shape, cell_args, cell_arity, make_cell,
)
from clausal.logic.atoms import is_atom, mint, spelling
from clausal.logic.exceptions import (
    LogicException, instantiation_error, type_error,
)
from clausal.logic.variables import deref, is_var, unify
from clausal.logic.predicate import is_term_instance, term_field_names, term_field_dict
from clausal.terms import KWTerm, DictTerm

from clausal.logic.builtins._registry import _builtin, _db_builtin


def _field_keys(mapping, context: str):
    """Normalise an overrides/additions dict to identifier-spelling keys.

    THE FLIP (spec §6.4): a field name written in source is an ATOM, so
    ``vary({x: V}, …)`` (and ``{"x": V}`` in the default double-quotes mode)
    arrives with the cell ``("x",)`` as its key.  KWTerm field names
    themselves stay identifier ``str``s (§6.4, last row), so the atom is read
    through ``spelling`` here.  A plain ``str`` key — what the Python API
    hands over — is already that identifier spelling and is taken as one.

    A key that is neither raises ``type_error(atom, Key, *context*)`` (Task
    12).  It used to answer ``None``, which both callers turned into a silent
    FAILURE: ``vary({1: 2}, T, N)`` simply did not succeed, and a malformed
    override read as "no such variation" instead of as the ill-typed call it
    is.  ``signature/3`` in this module already raises for the same mistake
    in its own name position.

    An UNBOUND key is the instantiation fault, not the type fault, and gets
    ``instantiation_error`` — the same split ``signature/3`` makes between
    its ``is_var`` guard and its ``is_atom`` guard (Task 12 fix round 1).
    ``type_error(atom, _G123)`` named a variable as the wrong SORT of term
    when the term is right and only the binding is missing.
    """
    out = {}
    for key, value in mapping.items():
        key = deref(key)
        if is_var(key):
            raise LogicException(instantiation_error(context))
        if is_atom(key):
            key = spelling(key)
        elif is_chars(key):
            key = chars_text(key)      # stage 1: a chars-string key is its text
        elif not isinstance(key, str):
            raise LogicException(type_error("atom", key, context))
        out[key] = value
    return out


def _declared_field_names(db, term_val):
    """The field names of a CELL, or ``None``.

    P2: a cell is a functor and POSITIONS -- it carries no field names.  The
    names come from where they are DECLARED (``-private([point(x, y, z)])``),
    which is the database's signature registry, and that is the whole reason
    these two builtins became db-receiving.  ``signature/3`` has always read
    the same registry; this makes ``vary/3`` and ``unbound_keys/2`` address
    fields by the same names ``signature/3`` answers with.
    """
    if db is None:
        return None
    is_cell, functor = compound_cell_shape(term_val)
    if not is_cell:
        return None
    return db.signature_for(functor, cell_arity(term_val))


@_db_builtin("vary", 3, fields=("overrides", "term", "new_term"), db_optional=True)
def _vary_factory(db):
    def _vary__3(overrides, term, new_term, trail, k):
        """vary(Overrides, Term, NewTerm) — copy Term with field overrides.

        Overrides is a Python dict {field_name: new_value}.
        Term is a declared functor CELL, a functor dataclass, or a KWTerm.
        NewTerm is unified with the resulting copy.
        """
        overrides_val = deref(overrides)
        term_val = deref(term)
        if is_var(overrides_val) or is_var(term_val):
            return
        if isinstance(overrides_val, DictTerm):
            overrides_val = overrides_val.data
        if not isinstance(overrides_val, dict):
            return
        overrides_val = _field_keys(overrides_val, "vary/3")
        names = _declared_field_names(db, term_val)
        if names is not None:
            args = list(cell_args(term_val))
            for key, value in overrides_val.items():
                if key not in names:
                    # An override naming no field of this term is "no variation",
                    # which is what the class path answered too -- its
                    # ``type(term)(**kwargs)`` raised TypeError and fell here.
                    return
                args[names.index(key)] = value
            result = make_cell(compound_cell_shape(term_val)[1], *args)
        elif is_term_instance(term_val) and not isinstance(term_val, KWTerm):
            try:
                kwargs = term_field_dict(term_val)
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
    return _vary__3


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
    if isinstance(additions_val, DictTerm):
        additions_val = additions_val.data
    if not isinstance(additions_val, dict):
        return
    additions_val = _field_keys(additions_val, "extend/3")
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


@_db_builtin("unbound_keys", 2, fields=("term", "keys"), db_optional=True)
def _unbound_keys_factory(db):
    def _unbound_keys__2(term, keys_list, trail, k):
        """unbound_keys(Term, Keys) — Keys is the list of field names holding unbound Vars.

        Works for functor dataclass instances and KWTerm.

        THE FLIP (spec §6.4): a field NAME handed back to the program is an
        ATOM.  The registry stays keyed by the identifier spelling (a ``str``);
        only the answer is minted.
        """
        term_val = deref(term)
        if is_var(term_val):
            return
        keys: list[tuple] = []
        names = _declared_field_names(db, term_val)
        if names is not None:
            for name, val in zip(names, cell_args(term_val)):
                if is_var(deref(val)):
                    keys.append(mint(name))
        elif is_term_instance(term_val) and not isinstance(term_val, KWTerm):
            for name in term_field_names(term_val):
                if is_var(deref(getattr(term_val, name))):
                    keys.append(mint(name))
        elif isinstance(term_val, KWTerm):
            for fname, val in term_val.items():
                if is_var(deref(val)):
                    keys.append(mint(fname))
        mark = trail.mark()
        if unify(keys_list, keys, trail):
            yield None
        trail.undo(mark)
    return _unbound_keys__2


@_db_builtin("signature", 3, fields=("functor_name", "arity", "names"))
def _signature_factory(db):
    """signature(FunctorName, Arity, Names) — reflect the registered signature.

    THE FLIP (spec §6.4): the name position speaks ATOMS.  *FunctorName* is
    read through ``spelling``; a string (or any other non-atom) raises
    ``type_error(atom, …)``.  Each answered parameter name is a name too, so
    *Names* comes back as a list of atoms.  The database registry itself
    stays keyed by the identifier spelling.
    """
    def signature__3(functor_name, arity, names, trail, k):
        f_val = deref(functor_name)
        a_val = deref(arity)
        if is_var(f_val) or is_var(a_val):
            return
        if not isinstance(a_val, int):
            return
        if not is_atom(f_val):
            raise LogicException(type_error("atom", f_val, "signature/3"))
        sig = db.signature_for(spelling(f_val), a_val)
        if sig is None:
            return
        mark = trail.mark()
        if unify(names, [mint(n) for n in sig], trail):
            yield None
        trail.undo(mark)
    return signature__3
