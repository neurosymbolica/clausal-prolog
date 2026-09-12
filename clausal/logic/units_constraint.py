"""clausal.logic.units_constraint — dimensional variable constraints via AttVar.

An uninstantiated dimensioned slot is a plain AttVar carrying a ``"units"``
attribute whose value is a ``UnitState(dims)`` — analogous to how CLP(FD)
stores ``FDVar(domain, constraints)`` under ``"fd"``.

when the AttVar is unified the hook:
  - checks that a Quantity binding has matching dims;
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
    instance rather than mutating an existing one. ``shadow`` is the bare
    variable a CLP solver sees in this variable's place (see
    ``clausal.logic.units_clp``); None until the variable first takes part
    in a constraint. Equality is by dims only: two states with the same
    dims are the same constraint whether or not a shadow exists yet.
    """

    __slots__ = ("dims", "shadow")

    def __init__(self, dims: dict, shadow=None) -> None:
        self.dims = {k: v for k, v in dims.items() if v != 0}
        self.shadow = shadow

    def __eq__(self, other: object) -> bool:
        return isinstance(other, UnitState) and self.dims == other.dims

    def __repr__(self) -> str:
        return f"UnitState({self.dims!r})"


def to_solver_number(v):
    """The bare number a solver receives for a Quantity value: a Decimal is
    an exact rational spelled in decimal notation, so it becomes a Fraction
    (exact at every scale); an integral rational presents as int, as
    everywhere in the engine; int/float/Fraction pass through."""
    from fractions import Fraction  # noqa: PLC0415
    from decimal import Decimal  # noqa: PLC0415
    from clausal.logic.variables import present_number  # noqa: PLC0415
    if isinstance(v, Decimal):
        if not v.is_finite():
            return v          # the comparators' own guards refuse it, catchably
        return present_number(Fraction(v))
    if type(v) is Fraction:
        return present_number(v)
    return v


def constrain_var_dims(var, dims: dict, trail: Trail) -> bool:
    """Post a dimensional constraint on *var*.

    If *var* already has a ``"units"`` constraint, verify the dims are
    identical (units constraints don't merge — they either match or conflict).
    If it has none, attach one.  Returns True on success, False on conflict.
    """
    clean = {k: v for k, v in dims.items() if v != 0}
    from clausal.logic import _units_flag  # noqa: PLC0415
    _units_flag.touch()
    existing = get_attr(var, UNITS_KEY)
    if existing is None:
        put_attr(var, UNITS_KEY, UnitState(clean), trail)
        return True
    return existing.dims == clean


def _units_hook(attr_value: UnitState, bound_to, trail: Trail) -> bool:
    """Called when an AttVar with a ``"units"`` attribute is unified.

    *attr_value* — the UnitState carried by the variable being bound.
    *bound_to*   — the value (or variable) the AttVar was unified with.

    With a shadow present, a Quantity binding is forwarded to the shadow
    through the CLP dispatch (``fd_eq``, not ``unify``, so an FD shadow
    meeting a rational is promoted exactly as a plain var would be), and
    two united variables unifying equate their shadows the same way.
    """
    # Import here to avoid circular imports at module load time.
    from clausal.terms import Quantity

    bound_to = deref(bound_to)

    if isinstance(bound_to, Quantity):
        # Binding to a ground measurement — check dimensions match.
        if bound_to.dims != attr_value.dims:
            return False
        if attr_value.shadow is not None:
            from clausal.logic.clpfd import fd_eq  # noqa: PLC0415  (module-level: C wrapper when loaded)
            # A shadow and a bare number carry no units: skip the side channel.
            return fd_eq(attr_value.shadow, to_solver_number(bound_to.value), trail,
                         _units_done=True)
        return True

    if is_var(bound_to):
        # Unified with another variable — transfer or check constraint.
        other = get_attr(bound_to, UNITS_KEY)
        if other is None:
            put_attr(bound_to, UNITS_KEY, attr_value, trail)
            return True
        # Both constrained — dims must be identical (no intersection for units).
        if other.dims != attr_value.dims:
            return False
        if attr_value.shadow is not None and other.shadow is not None:
            if attr_value.shadow is other.shadow:
                return True
            from clausal.logic.clpfd import fd_eq  # noqa: PLC0415
            return fd_eq(attr_value.shadow, other.shadow, trail, _units_done=True)
        if attr_value.shadow is not None:
            put_attr(bound_to, UNITS_KEY, attr_value, trail)   # inherit the shadow
        return True

    import numbers  # noqa: PLC0415
    from decimal import Decimal  # noqa: PLC0415
    if (isinstance(bound_to, (numbers.Real, Decimal))
            and not isinstance(bound_to, bool)):
        # Plain number (int, float, Fraction, Decimal) allowed only for a
        # dimensionless constraint.
        return not attr_value.dims

    return False


register_attr_hook(UNITS_KEY, _units_hook)


from clausal.logic.builtins._registry import _builtin  # noqa: E402


@_builtin("has_units", 2)
def _has_units(d, unit_pred, trail, k):
    """has_units(D, UnitPred): D must be (or become) dimensioned in UnitPred's dims.

    - D is a ground Quantity  → check dims match
    - D is an unbound AttVar     → post the "units" constraint
    - anything else              → fail
    """
    from clausal.terms import Quantity  # avoid circular import at module load

    dims = getattr(unit_pred, "_dims", None)
    if dims is None:
        return
    dv = deref(d)
    if isinstance(dv, Quantity):
        if dv.dims == dims:
            yield None
    elif is_var(dv):
        if constrain_var_dims(dv, dims, trail):
            yield None
