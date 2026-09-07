"""Attributed variable builtins: put_attr/3, get_attr/3, del_attr/2,
get_attrs/2, put_attrs/2, attvar/1, term_attvars/2."""

from __future__ import annotations

from clausal.logic.variables import deref, is_var, unify, put_attr, get_attr, del_attr
from clausal.logic.predicate import is_term_instance, term_field_names
from clausal.terms import (
    Compound,
    DictTerm,
    SetTerm,
    SegList,
    SegString,
    SegBytes,
    ConcreteSeg,
    VarSeg,
)

from clausal.logic.atoms import (
    NIL_SPELLING, is_atom, key_of, mint, spelling,
)
from clausal.logic.builtins._helpers import _is_empty_list
from clausal.logic.builtins._registry import _builtin
from clausal.logic.runtime._seg_helpers import normalize_seg_input


# ── The Key funnel ─────────────────────────────────────────────────────────


def _storage_key(key, context):
    """The dict key an attribute *Key* argument denotes, or ``None``.

    Spec §6.4: an attribute key is a NAME, so it is an ATOM — a
    source-written ``put_attr(X, mykey, V)`` hands ``("mykey",)`` here after
    THE FLIP (2026-09-06-atoms-as-cells-strings).  These four builtins gated
    on ``isinstance(key, str)``, which post-flip matches a STRING and nothing
    a program can write, so every source-written call failed silently.

    The key is stored by its **spelling**, which is the decision this funnel
    exists to make once for all of ``put_attr/3``, ``get_attr/3``,
    ``del_attr/2`` and ``put_attrs/2``:

    * it is the namespace the engine's own attributes already occupy —
      ``clpfd``'s ``FD_KEY = "fd"``, ``dif``, ``clpb``, ``freeze``, ``units``
      and the ``register_attr_hook`` registry are all plain ``str`` — so a
      source-written key and a library key of the same name are the SAME
      attribute, as they are in SWI, rather than two invisible namespaces;
    * ``capi_put_attr``/``capi_get_attr`` in ``variables/_variables.c`` take
      the key object as given (it is only ever a dict key and a hook-registry
      lookup), so spelling storage needs no C change at all.

    ``get_attrs/2`` mints the spellings back into atoms on the way out, so
    the TERM surface is atoms in both directions.

    An unbound key answers ``None`` and the caller FAILS — that is the mode
    signal these predicates have always given.  A STRING key raises
    ``type_error(atom, …)``: a string is not a name (§6.4), and a silent
    failure is precisely what hid this bug.

    A string has two shapes — a plain ``str`` and a ground ``SegString`` that
    walks to one — and they must give the SAME answer, so the value is walked
    (``normalize_seg_input``) before the ``str`` test.  Without the walk a
    ``SegString`` key fell through to the trailing ``None`` and failed
    silently, which is the very reporting hole this funnel was built to
    close.
    """
    key = normalize_seg_input(key)
    if _is_empty_list(key):
        # The nil atom (fix round 2, item 2).  ``atoms.is_atom`` below is the
        # arity-0-CELL shape test and answers False for ``[]``, so a nil key
        # FAILED silently while ``""`` -- the same term -- raised
        # ``type_error(atom, …)`` at the str branch.  It is an atom; its
        # spelling is the two bracket characters.
        return NIL_SPELLING
    if is_atom(key):
        return spelling(key)
    if is_var(key):
        return None
    if type(key) is str:
        from clausal.logic.exceptions import (  # noqa: PLC0415
            LogicException, type_error,
        )
        raise LogicException(type_error("atom", key, context))
    return None


# ── Per-key operations ─────────────────────────────────────────────────────


@_builtin("put_attr", 3)
def _put_attr__3(var, key, value, trail, k):
    """put_attr(Var, Key, Value) — attach attribute under Key to Var.

    Var must be an unbound variable. Key must be a ground ATOM (§6.4);
    a string raises ``type_error(atom, …)``. Trailed.
    """
    var_d = deref(var)
    if not is_var(var_d):
        return
    key_d = _storage_key(deref(key), "put_attr/3")
    if key_d is None:
        return
    put_attr(var_d, key_d, deref(value), trail)
    yield None


@_builtin("get_attr", 3)
def _get_attr__3(var, key, value, trail, k):
    """get_attr(Var, Key, Value) — retrieve attribute under Key.

    Key is an ATOM (§6.4); a string raises ``type_error(atom, …)``.
    Fails if Var has no attribute for Key, or if Var is not an unbound variable.
    """
    var_d = deref(var)
    if not is_var(var_d):
        return
    key_d = _storage_key(deref(key), "get_attr/3")
    if key_d is None:
        return
    attr = get_attr(var_d, key_d)
    if attr is None:
        return
    if unify(value, attr, trail):
        yield None


@_builtin("del_attr", 2)
def _del_attr__2(var, key, trail, k):
    """del_attr(Var, Key) — remove attribute under Key from Var.

    Key is an ATOM (§6.4); a string raises ``type_error(atom, …)``.
    Succeeds even if no attribute existed (no-op). Trailed.
    """
    var_d = deref(var)
    if not is_var(var_d):
        return
    key_d = _storage_key(deref(key), "del_attr/2")
    if key_d is None:
        return
    del_attr(var_d, key_d, trail)
    yield None


# ── Bulk operations (DictTerm) ─────────────────────────────────────────────


@_builtin("get_attrs", 2)
def _get_attrs__2(var, attrs, trail, k):
    """get_attrs(Var, Attrs) — unify Attrs with a DictTerm of all attributes on Var.

    The keys come back as ATOMS (§6.4/§6.8): they are stored by spelling (see
    :func:`_storage_key`), and handing the raw ``str`` back would put a STRING
    in a name position — and build a dict ``put_attrs/2`` would then refuse,
    breaking ``get_attrs(V, D), put_attrs(W, D)``.
    """
    var_d = deref(var)
    if not is_var(var_d):
        return
    raw = var_d.attrs if hasattr(var_d, 'attrs') and var_d.attrs else {}
    # ``key_of``, not ``mint``: an attribute stored under the spelling
    # ``[]`` is the atom ``'[]'``, whose ``mint`` answer is the
    # unhashable empty LIST (fix round 2, item 2).
    result = DictTerm({key_of(key): value for key, value in raw.items()})
    if unify(attrs, result, trail):
        yield None


@_builtin("put_attrs", 2)
def _put_attrs__2(var, attrs, trail, k):
    """put_attrs(Var, Attrs) — set multiple attributes from a DictTerm.

    Each key is an ATOM, applied exactly as ``put_attr/3`` applies it.
    """
    var_d = deref(var)
    attrs_d = deref(attrs)
    if not is_var(var_d):
        return
    if isinstance(attrs_d, DictTerm):
        data = attrs_d.data
    elif isinstance(attrs_d, dict):
        data = attrs_d
    else:
        return
    for key, value in data.items():
        key_d = _storage_key(deref(key), "put_attrs/2")
        if key_d is None:
            return
        put_attr(var_d, key_d, deref(value), trail)
    yield None


# ── Inspection ─────────────────────────────────────────────────────────────


@_builtin("attvar", 1)
def _is_att_var__1(var, trail, k):
    """attvar(Var) — succeeds if Var is an unbound variable with attributes."""
    var_d = deref(var)
    if is_var(var_d):
        raw = var_d.attrs if hasattr(var_d, 'attrs') else None
        if raw:
            yield None


@_builtin("term_attvars", 2)
def _term_attributed_variables__2(term, vars_list, trail, k):
    """term_attvars(Term, Vars) — collect all attributed variables in Term."""
    seen = set()
    result = []
    _collect_attvars(deref(term), seen, result)
    if unify(vars_list, result, trail):
        yield None


def _collect_attvars(term, seen, result):
    """Recursively collect attributed variables from a term."""
    if is_var(term):
        vid = id(term)
        if vid not in seen:
            seen.add(vid)
            raw = term.attrs if hasattr(term, 'attrs') else None
            if raw:
                result.append(term)
        return
    # tuple is a core Clausal structure, so it walks alongside list.
    if isinstance(term, (list, tuple)):
        for item in term:
            _collect_attvars(deref(item), seen, result)
    elif isinstance(term, Compound):
        for arg in term.args:
            _collect_attvars(deref(arg), seen, result)
    elif is_term_instance(term):
        for f in term_field_names(term):
            _collect_attvars(deref(getattr(term, f)), seen, result)
    elif isinstance(term, DictTerm):
        for v in term.data.values():
            _collect_attvars(deref(v), seen, result)
    elif isinstance(term, dict):
        for v in term.values():
            _collect_attvars(deref(v), seen, result)
    elif isinstance(term, (set, frozenset, SetTerm)):
        for elem in term:
            _collect_attvars(deref(elem), seen, result)
    elif isinstance(term, (SegList, SegString, SegBytes)):
        for seg in term.segments:
            if isinstance(seg, VarSeg):
                _collect_attvars(deref(seg.var), seen, result)
            elif isinstance(seg, ConcreteSeg):
                for elem in seg.elements:
                    _collect_attvars(deref(elem), seen, result)
            # plain str/bytes segments are ground — nothing to collect
