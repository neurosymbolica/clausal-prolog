"""Type-checking builtins: IsVar/1, IsBound/1, IsStr/1, IsNumber/1,
IsInt/1, IsFloat/1, IsCompound/1, IsCallable/1, IsList/1, IsGround/1."""

from __future__ import annotations

from clausal.logic.variables import deref, is_var
from clausal.logic.predicate import is_term_instance, term_field_names
from clausal.terms import Compound, KWTerm

from clausal.logic.builtins._registry import _builtin
from clausal.logic.builtins._helpers import _is_ground


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
