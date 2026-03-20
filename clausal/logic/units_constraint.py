"""clausal.logic.units_constraint — dimensional variable constraints via AttVar.

An uninstantiated dimensioned slot is a plain AttVar carrying a ``"units"``
attribute whose value is a ``UnitState(dims)`` — analogous to how CLP(FD)
stores ``FDVar(domain, constraints)`` under ``"fd"``.

When the AttVar is unified the hook:
  - checks that a Dimensioned binding has matching dims;
  - transfers or merges the constraint when unified with another variable;
  - rejects plain numbers unless the constraint is dimensionless.

This module is imported for its side-effect: ``register_attr_hook`` is called
at import time, exactly like ``clpfd.py`` registers the ``"fd"`` hook.
"""

from __future__ import annotations

from clausal.logic.variables import (
    Trail,
    deref,
    is_var,
    get_attr,
    put_attr,
    register_attr_hook,
)

UNITS_KEY = "units"


class UnitState:
    """Dimensional constraint for an unbound variable.

    Immutable for trail safety — constrain_var_dims always creates a new
    instance rather than mutating an existing one.
    """

    __slots__ = ("dims",)

    def __init__(self, dims: dict) -> None:
        self.dims = {k: v for k, v in dims.items() if v != 0}

    def __eq__(self, other: object) -> bool:
        return isinstance(other, UnitState) and self.dims == other.dims

    def __repr__(self) -> str:
        return f"UnitState({self.dims!r})"


def constrain_var_dims(var, dims: dict, trail: Trail) -> bool:
    """Post a dimensional constraint on *var*.

    If *var* already has a ``"units"`` constraint, verify the dims are
    identical (units constraints don't merge — they either match or conflict).
    If it has none, attach one.  Returns True on success, False on conflict.
    """
    clean = {k: v for k, v in dims.items() if v != 0}
    existing = get_attr(var, UNITS_KEY)
    if existing is None:
        put_attr(var, UNITS_KEY, UnitState(clean), trail)
        return True
    return existing.dims == clean


def _units_hook(attr_value: UnitState, bound_to, trail: Trail) -> bool:
    """Called when an AttVar with a ``"units"`` attribute is unified.

    *attr_value* — the UnitState carried by the variable being bound.
    *bound_to*   — the value (or variable) the AttVar was unified with.
    """
    # Import here to avoid circular imports at module load time.
    from clausal.terms import Dimensioned

    bound_to = deref(bound_to)

    if isinstance(bound_to, Dimensioned):
        # Binding to a ground measurement — check dimensions match.
        return bound_to.dims == attr_value.dims

    if is_var(bound_to):
        # Unified with another variable — transfer or check constraint.
        other = get_attr(bound_to, UNITS_KEY)
        if other is None:
            put_attr(bound_to, UNITS_KEY, attr_value, trail)
            return True
        # Both constrained — dims must be identical (no intersection for units).
        return other.dims == attr_value.dims

    if isinstance(bound_to, (int, float)) and not isinstance(bound_to, bool):
        # Plain number allowed only for a dimensionless constraint.
        return not attr_value.dims

    return False


register_attr_hook(UNITS_KEY, _units_hook)


from clausal.logic.builtins._registry import _builtin  # noqa: E402


@_builtin("HasUnits", 2)
def _has_units(d, unit_pred, trail, k):
    """HasUnits(D, UnitPred): D must be (or become) dimensioned in UnitPred's dims.

    - D is a ground Dimensioned  → check dims match
    - D is an unbound AttVar     → post the "units" constraint
    - anything else              → fail
    """
    from clausal.terms import Dimensioned  # avoid circular import at module load

    if unit_pred._dims is None:
        return
    dv = deref(d)
    dims = unit_pred._dims
    if isinstance(dv, Dimensioned):
        if dv.dims == dims:
            yield None
    elif is_var(dv):
        if constrain_var_dims(dv, dims, trail):
            yield None
