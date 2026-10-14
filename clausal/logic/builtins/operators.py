"""Operators: op/3 and current_op/3 (ISO 8.14.3, 8.14.4) as goals.

Both act on the process-wide run-time table,
:func:`clausal.tools.prolog_operators.runtime_op_table`: ``op/3`` run as a
goal changes it, ``current_op/3`` enumerates it.  A ``.pl`` file's
``:- op/3`` directive is checked by the same :func:`op_error` and also
reaches this table when Scryer would make it global (a file that is not a
module; a module's exported ops).  Clauses are read when their file is
loaded, so ``op/3`` as a goal does not change how any loaded source reads.

Errors, with ``op/3`` / ``current_op/3`` as the context:

* ``op/3`` (8.14.3.3, Scryer-verified order): an unbound priority,
  specifier, operator, element or list tail is ``instantiation_error``; a
  priority that is not an integer ``type_error(integer, P)``, a specifier
  that is not an atom ``type_error(atom, S)``, an operator that is neither
  an atom nor a list ``type_error(list, O)``, an element that is not an atom
  ``type_error(atom, E)``; then :func:`op_error`'s ``permission_error`` and
  ``domain_error`` s.  A refused op/3 changes nothing, also for a list.
* ``current_op/3`` (8.14.4.3): a bound priority that is not an integer
  0..1200 is ``domain_error(operator_priority, P)``, a bound specifier that
  is not one of the seven ``domain_error(operator_specifier, S)``, a bound
  operator that is not an atom ``type_error(atom, O)``.  Scryer answers
  ``type_error`` for the first two when they are not an integer / an atom;
  here ISO decides.
"""

from __future__ import annotations

from typing import Any

from clausal.logic.atoms import mint
from clausal.logic.exceptions import (
    LogicException, domain_error, instantiation_error, permission_error,
    type_error,
)
from clausal.logic.variables import deref, is_var, unify
from clausal.logic.builtins._registry import _builtin
from clausal.logic.builtins.chars import _atom_to_str
from clausal.logic.builtins.lists import _as_items
from clausal.tools.prolog_operators import (
    SPECIFIERS, op_error, runtime_op_table,
)

_OP = "op/3"
_CURRENT = "current_op/3"


def _op_names(val: Any) -> list:
    """The operator names ``op/3``'s third argument gives (each an atom's
    spelling, ``'[]'`` for the empty list), or the ISO error."""
    name = _atom_to_str(val)
    if name is not None:
        return [name]
    items = _as_items(val)
    if items is None:
        from clausal.terms import SegList, SegString, SegBytes  # noqa: PLC0415
        if isinstance(val, SegList):
            walked = val._walk_raw()
            if isinstance(walked, SegList):
                raise LogicException(instantiation_error(_OP))
            if not isinstance(walked, list):     # an improper list
                raise LogicException(type_error("list", walked, _OP))
            items = walked
        elif isinstance(val, (SegString, SegBytes)):
            raise LogicException(instantiation_error(_OP))
        else:
            raise LogicException(type_error("list", val, _OP))
    names = []
    for e in items:
        e = deref(e)
        if is_var(e):
            raise LogicException(instantiation_error(_OP))
        n = _atom_to_str(e)
        if n is None:
            raise LogicException(type_error("atom", e, _OP))
        names.append(n)
    return names


def _raise(err: tuple, culprit_spec, culprit_prec):
    if err[0] == "permission_error":
        _, action, kind, name = err
        raise LogicException(permission_error(action, kind, mint(name), _OP))
    if err[1] == "operator_priority":
        raise LogicException(domain_error("operator_priority", culprit_prec,
                                          _OP))
    raise LogicException(domain_error("operator_specifier", culprit_spec, _OP))


@_builtin("op", 3)
def _op__3(priority, specifier, operator, trail, k):
    """op(Priority, Specifier, Operator) -- ISO 8.14.3: set (or, with
    priority 0, remove) the operator(s) in the run-time table."""
    p, s, o = deref(priority), deref(specifier), deref(operator)
    if is_var(p) or is_var(s) or is_var(o):
        raise LogicException(instantiation_error(_OP))
    if type(p) is not int:
        raise LogicException(type_error("integer", p, _OP))
    spec = _atom_to_str(s)
    if spec is None:
        raise LogicException(type_error("atom", s, _OP))
    names = _op_names(o)
    table = runtime_op_table()
    err = op_error(table, p, spec, names)
    if err is not None:
        _raise(err, s, p)
    for n in names:
        table.define(p, spec, n)
    yield None


@_builtin("current_op", 3)
def _current_op__3(priority, specifier, operator, trail, k):
    """current_op(Priority, Specifier, Operator) -- ISO 8.14.4: enumerate
    the run-time table's operators."""
    p, s, o = deref(priority), deref(specifier), deref(operator)
    if not is_var(p) and (type(p) is not int or not 0 <= p <= 1200):
        raise LogicException(domain_error("operator_priority", p, _CURRENT))
    if not is_var(s):
        if _atom_to_str(s) not in SPECIFIERS:
            raise LogicException(domain_error("operator_specifier", s,
                                              _CURRENT))
    name = None
    if not is_var(o):
        name = _atom_to_str(o)
        if name is None:
            raise LogicException(type_error("atom", o, _CURRENT))
    table = runtime_op_table()
    # A snapshot: a goal run between two answers may change the table.
    entries = [e for e in table.entries() if name is None or e.name == name]
    for e in entries:
        mark = trail.mark()
        if (unify(priority, e.precedence, trail)
                and unify(specifier, mint(e.specifier), trail)
                and unify(operator, mint(e.name), trail)):
            yield None
        trail.undo(mark)
