"""Shared dimensional-analysis utilities for scipy wrapper predicates.

All scipy wrapper modules import from this module::

    from clausal.modules.py._scipy_units import (
        make_quantity_aware,
        REQUIRE_DIMENSIONLESS, PASS_THROUGH_FIRST, PASS_THROUGH_LAST, STRIP_TO_PLAIN,
        strip_quantity, quantity_dims, merge_dims, wrap_result,
        probe_function_units,
    )

Zero-overhead design
--------------------
``make_quantity_aware(call, propagator)`` wraps *call* so that:

- When all inputs are plain (no ``Quantity``), *call* is invoked directly —
  zero overhead beyond a single ``any(isinstance(...))`` scan that
  short-circuits on the first non-Quantity value.
- When at least one input is a ``Quantity``, values are stripped, *call* is
  invoked on the raw values, then *propagator* attaches output dimensions.

Set ``_SCIPY_UNITS_ENABLED = False`` **before** importing any scipy module to
disable all wrapping: ``make_quantity_aware`` then returns *call* unchanged,
leaving predicate objects identical to the pre-units baseline.
"""

from __future__ import annotations

from clausal.terms import Quantity, UnitsMismatch


# ── Global enable flag ─────────────────────────────────────────────────────

#: Set to ``False`` before importing any scipy module to skip all unit
#: wrapping.  ``make_quantity_aware`` returns the callable unchanged, so
#: there is truly zero overhead even for the isinstance scan.
_SCIPY_UNITS_ENABLED: bool = True


# ── Low-level helpers ──────────────────────────────────────────────────────

def strip_quantity(x):
    """Return ``x.value`` if *x* is a :class:`~clausal.terms.Quantity`, else *x* unchanged."""
    return x.value if isinstance(x, Quantity) else x


def quantity_dims(x):
    """Return ``dict(x.dims)`` if *x* is a Quantity, else ``None``."""
    return dict(x.dims) if isinstance(x, Quantity) else None


def merge_dims(a: dict, b: dict, sign: int) -> dict:
    """Return *a* + *sign*·*b* with zero-exponent keys removed.

    Delegates to :meth:`~clausal.terms.Quantity._merge_dims`.
    Both *a* and *b* must be plain ``dict`` objects (not ``MappingProxyType``).
    """
    return Quantity._merge_dims(a, b, sign)


def wrap_result(value, dims):
    """Return ``Quantity(value, dims)`` if *dims* is non-``None`` and non-empty, else *value* unchanged."""
    if dims:
        return Quantity(value, dims)
    return value


# ── Standard propagators ───────────────────────────────────────────────────

def _require_dimensionless_propagator(dims_list, result):
    """Raise :class:`~clausal.terms.UnitsMismatch` if any input has non-empty dims."""
    for d in dims_list:
        if d is not None and d:   # non-None and non-empty dict
            raise UnitsMismatch(
                f"Function requires dimensionless arguments; got dims {d}"
            )
    return None   # dimensionless Quantities: return plain result


def _pass_through_first_propagator(dims_list, result):
    """Output dims = dims of the first :class:`~clausal.terms.Quantity` input."""
    d = dims_list[0]
    if not d:
        return None
    return wrap_result(result, d)


def _pass_through_last_propagator(dims_list, result):
    """Output dims = dims of the last :class:`~clausal.terms.Quantity` input."""
    d = None
    for x in dims_list:
        if x is not None:
            d = x
    if not d:
        return None
    return wrap_result(result, d)


def _strip_to_plain_propagator(dims_list, result):
    """Strip Quantity inputs; always return the plain result regardless of dims."""
    return None


#: Propagator: raise :class:`~clausal.terms.UnitsMismatch` if any input has
#: non-empty dims (e.g. for transcendental functions).
REQUIRE_DIMENSIONLESS = _require_dimensionless_propagator

#: Propagator: output has the same dims as the first Quantity input
#: (e.g. FFT, linear signal filters).
PASS_THROUGH_FIRST = _pass_through_first_propagator

#: Propagator: output has the same dims as the last Quantity input.
PASS_THROUGH_LAST = _pass_through_last_propagator

#: Propagator: strip Quantity inputs, always return a plain (non-Quantity) result
#: (e.g. statistical test statistics, opaque factor tuples).
STRIP_TO_PLAIN = _strip_to_plain_propagator


# ── Main factory ───────────────────────────────────────────────────────────

def make_quantity_aware(call, unit_propagator=None):
    """Wrap *call* to handle :class:`~clausal.terms.Quantity` inputs transparently.

    When :data:`_SCIPY_UNITS_ENABLED` is ``False``, returns *call* unchanged.

    **Fast path** — when no input is a Quantity, *call* is invoked directly
    with no wrapping overhead.

    **Quantity path** — strips ``.value`` from each Quantity input, calls
    *call* on the stripped values, then invokes
    ``unit_propagator(dims_list, result)`` to attach output dimensions.
    *dims_list* contains ``dict(x.dims)`` for each Quantity input and
    ``None`` for plain inputs.  If *unit_propagator* is ``None`` or returns
    ``None``, the plain result is returned unchanged.
    """
    if not _SCIPY_UNITS_ENABLED:
        return call

    def wrapped(*inputs):
        # ── fast path ──────────────────────────────────────────────────────
        if not any(isinstance(x, Quantity) for x in inputs):
            return call(*inputs)
        # ── quantity path ──────────────────────────────────────────────────
        stripped = [x.value if isinstance(x, Quantity) else x for x in inputs]
        result = call(*stripped)
        if unit_propagator is not None:
            dims_list = [dict(x.dims) if isinstance(x, Quantity) else None
                         for x in inputs]
            out = unit_propagator(dims_list, result)
            if out is not None:
                return out
        return result

    return wrapped


# ── Callable-probing utility ───────────────────────────────────────────────

def probe_function_units(f, x_quantity):
    """Call ``f(x_quantity)`` once and return the output dims dict, or ``None``.

    If *f* returns a :class:`~clausal.terms.Quantity`, returns
    ``dict(result.dims)``.  If *f* returns a plain number or array, returns
    ``None`` (*f* operates on raw values and does not propagate units).

    The probe consumes one function evaluation.  For ``scipy.differentiate``
    and ``scipy.integrate`` this is negligible relative to scipy's own call
    count.
    """
    out = f(x_quantity)
    if isinstance(out, Quantity):
        return dict(out.dims)
    return None
