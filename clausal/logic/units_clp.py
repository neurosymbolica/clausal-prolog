"""clausal.logic.units_clp — the units side channel around CLP.

A CLP comparison is two expression trees. Quantities and units-attributed
variables may appear anywhere in them, but the solvers (CLP(FD), CLP(Q),
CLP(R), and the C cores behind them) only ever see bare numbers and bare
variables. This module sits between the two:

  1. ``analyse``   — dimensional analysis on the trees, FIRST. Infers the
                     dims of every variable, applies one rule per node, and
                     throws ``error(system_error(units_mismatch), Ctx)``
                     before any solver runs.
  2. ``strip``     — every ``Quantity`` becomes its solver number
                     (``Decimal -> Fraction``, exact), every united variable
                     becomes its bare *shadow* variable.
  3. the link hook — when the solver binds a shadow, the user's variable is
                     bound to a ``Quantity`` with the computed dims; the
                     ``units`` hook in ``units_constraint`` does the other
                     direction.

Spec: docs/superpowers/specs/2026-09-12-clp-units-side-channel-design.md.
Written with no clpfd import at module level so a second solver front end
(CLP(Z3)'s ``_z3_arith_binary``) can call ``strip_for_solver`` unchanged.
"""

from __future__ import annotations

import numbers
from decimal import Decimal
from typing import Any

from clausal.logic.variables import (
    Trail, Var, deref, is_var, get_attr, put_attr, unify, register_attr_hook,
    present_number,
)
from clausal.logic.units_constraint import UNITS_KEY, UnitState, to_solver_number

LINK_KEY = "units_link"

# Lazily imported node classes (clausal.terms imports the logic package).
_Add = _Sub = _Mult = _Div = _FloorDiv = _Mod = _Pow = _Negate = _Quantity = None
_BINARY: tuple = ()


def _ensure_imports() -> None:
    global _Add, _Sub, _Mult, _Div, _FloorDiv, _Mod, _Pow, _Negate, _Quantity, _BINARY
    if _Add is None:
        from clausal.terms import (Add, Sub, Mult, Div, FloorDiv, Mod, Pow,  # noqa: PLC0415
                                   Negate, Quantity)
        _Add, _Sub, _Mult, _Div, _FloorDiv, _Mod, _Pow, _Negate = (
            Add, Sub, Mult, Div, FloorDiv, Mod, Pow, Negate)
        _Quantity = Quantity
        _BINARY = (Add, Sub, Mult, Div, FloorDiv, Mod, Pow)


class _NotEngaged(Exception):
    """A leaf the side channel does not speak for (atom, string, date, …).
    The caller falls back to the existing guards, which own that error."""


# ── dimension algebra ────────────────────────────────────────────────────────

def _merge(a: dict, b: dict, sign: int) -> dict:
    out = dict(a)
    for k, v in b.items():
        nv = out.get(k, 0) + sign * v
        if nv:
            out[k] = nv
        else:
            out.pop(k, None)
    return out


def _scale(a: dict, n: int) -> dict:
    return {k: v * n for k, v in a.items() if v * n != 0}


def _unscale(a: dict, n: int) -> dict | None:
    """Inverse of ``_scale``; None when some exponent is not divisible by n."""
    out = {}
    for k, v in a.items():
        if v % n:
            return None
        out[k] = v // n
    return out


def _render_pair(a: dict, b: dict) -> str:
    """``metre vs second``, qualifying same-named dimensions exactly as
    ``Quantity._require_same_dims`` does (``dollar (AUD) vs dollar (USD)``)."""
    from clausal.terms import _dims_str, _colliding_dim_names  # noqa: PLC0415
    left, right = _dims_str(a), _dims_str(b)
    if left == right:
        collide = _colliding_dim_names(a, b)
        left = _dims_str(a, qualify=collide)
        right = _dims_str(b, qualify=collide)
        if left == right:
            right += " — these are different dimensions that share a name"
    return f"{left or 'dimensionless'} vs {right or 'dimensionless'}"


def _mismatch(context: str, a: dict, b: dict, what: str = "") -> Exception:
    from clausal.logic.exceptions import LogicException, system_error  # noqa: PLC0415
    detail = f"{what}: " if what else ""
    return LogicException(system_error(
        "units_mismatch", f"{context}: {detail}{_render_pair(a, b)}"))


def _undetermined(context: str, vars_: list) -> Exception:
    from clausal.logic.exceptions import LogicException, system_error  # noqa: PLC0415
    names = ", ".join(repr(v) for v in vars_)
    return LogicException(system_error(
        "units_undetermined",
        f"{context}: cannot infer the units of {names}; declare one with "
        f"has_units/2 or multiply by a unit quantity"))


# ── scanning ─────────────────────────────────────────────────────────────────

def _is_plain_number(x: Any) -> bool:
    return (isinstance(x, (numbers.Real, Decimal))
            and not isinstance(x, bool))


def has_units_material(x: Any) -> bool:
    """True if *x* holds a Quantity or a units-attributed Var anywhere, and
    every leaf is one the side channel speaks for. A foreign leaf (atom,
    string, date, …) returns False so the existing guards own the error."""
    _ensure_imports()
    try:
        return _scan(x)
    except _NotEngaged:
        return False


def _scan(x: Any) -> bool:
    x = deref(x)
    if isinstance(x, _Quantity):
        return True
    if is_var(x):
        return get_attr(x, UNITS_KEY) is not None
    if _is_plain_number(x):
        return False
    if isinstance(x, _BINARY):
        left = _scan(x.left)
        right = _scan(x.right)
        return left or right
    if isinstance(x, _Negate):
        return _scan(x.operand)
    raise _NotEngaged()


def _has_solver_state(v) -> bool:
    # FD_KEY / Q_KEY / REAL_KEY, spelled literally to keep this module free
    # of solver imports; tests/test_units_clp.py pins the spellings agree.
    return (get_attr(v, "fd") is not None or get_attr(v, "clpq") is not None
            or get_attr(v, "real") is not None)


# ── analysis ─────────────────────────────────────────────────────────────────

class _Analysis:
    """One comparison's dimension inference.

    ``env`` maps ``var._id`` to a dims dict once known. Vars are known from
    a ``units`` attribute, or are dimensionless when they already carry
    solver state (they are bare numbers to the solver), or are unknown and
    inferred. Numbers are dimensionless. ``_known`` walks bottom-up and
    returns None for "not yet"; ``_push`` walks top-down with a required
    dims and assigns unknown vars. The two alternate to a fixpoint; then
    the single unknown factor of a product is defaulted to dimensionless
    (a bare multiplier is what ground arithmetic accepts too) and the
    fixpoint re-runs; what is still unknown is undetermined and throws.
    """

    def __init__(self, context: str) -> None:
        self.context = context
        self.env: dict[int, dict] = {}
        self.vars: dict[int, Any] = {}
        self.unknown_order: list[int] = []

    # leaves ---------------------------------------------------------------
    def _var_dims(self, v) -> dict | None:
        vid = v._id
        if vid in self.env:
            return self.env[vid]
        if vid not in self.vars:
            self.vars[vid] = v
            state = get_attr(v, UNITS_KEY)
            if state is not None:
                self.env[vid] = dict(state.dims)
            elif _has_solver_state(v):
                self.env[vid] = {}
            else:
                self.unknown_order.append(vid)
        return self.env.get(vid)

    def _assign(self, v, dims: dict) -> None:
        self.env[v._id] = dict(dims)

    # bottom-up ------------------------------------------------------------
    def _known(self, x: Any) -> dict | None:
        x = deref(x)
        if isinstance(x, _Quantity):
            return dict(x.dims)
        if is_var(x):
            return self._var_dims(x)
        if _is_plain_number(x):
            return {}
        if isinstance(x, (_Add, _Sub, _Mod)):
            l, r = self._known(x.left), self._known(x.right)
            if l is not None and r is not None:
                if l != r:
                    raise _mismatch(self.context, l, r, type(x).__name__)
                return l
            return l if l is not None else r
        if isinstance(x, _FloorDiv):
            l, r = self._known(x.left), self._known(x.right)
            if l is not None and r is not None and l != r:
                raise _mismatch(self.context, l, r, "FloorDiv")
            return {}
        if isinstance(x, _Mult):
            l, r = self._known(x.left), self._known(x.right)
            return _merge(l, r, +1) if l is not None and r is not None else None
        if isinstance(x, _Div):
            l, r = self._known(x.left), self._known(x.right)
            return _merge(l, r, -1) if l is not None and r is not None else None
        if isinstance(x, _Pow):
            n = self._exponent(x)
            base = self._known(x.left)
            return _scale(base, n) if base is not None else None
        if isinstance(x, _Negate):
            return self._known(x.operand)
        raise _NotEngaged()

    def _exponent(self, x) -> int:
        e = deref(x.right)
        if isinstance(e, _Quantity):
            if e.dims:
                raise _mismatch(self.context, dict(e.dims), {}, "exponent")
            e = e.value
        if isinstance(e, bool) or not isinstance(e, int):
            raise _mismatch(self.context, {}, {},
                            f"exponent must be a ground int, got {e!r}")
        return e

    # top-down -------------------------------------------------------------
    def _push(self, x: Any, want: dict) -> None:
        x = deref(x)
        if isinstance(x, _Quantity):
            if dict(x.dims) != want:
                raise _mismatch(self.context, dict(x.dims), want)
            return
        if is_var(x):
            have = self._var_dims(x)
            if have is None:
                self._assign(x, want)
            elif have != want:
                raise _mismatch(self.context, have, want)
            return
        if _is_plain_number(x):
            if want:
                raise _mismatch(self.context, {}, want, "plain number")
            return
        if isinstance(x, (_Add, _Sub, _Mod)):
            self._push(x.left, want)
            self._push(x.right, want)
            return
        if isinstance(x, _FloorDiv):
            if want:
                raise _mismatch(self.context, {}, want, "FloorDiv")
            l, r = self._known(x.left), self._known(x.right)
            if l is not None:
                self._push(x.right, l)
            elif r is not None:
                self._push(x.left, r)
            return
        if isinstance(x, _Mult):
            l, r = self._known(x.left), self._known(x.right)
            if l is not None:
                self._push(x.right, _merge(want, l, -1))
            if r is not None:
                self._push(x.left, _merge(want, r, -1))
            return
        if isinstance(x, _Div):
            l, r = self._known(x.left), self._known(x.right)
            if r is not None:
                self._push(x.left, _merge(want, r, +1))
            if l is not None:
                self._push(x.right, _merge(l, want, -1))
            return
        if isinstance(x, _Pow):
            n = self._exponent(x)
            base = _unscale(want, n)
            if base is None:
                raise _mismatch(self.context, want, {}, f"not a {n}th power")
            self._push(x.left, base)
            return
        if isinstance(x, _Negate):
            self._push(x.operand, want)
            return
        raise _NotEngaged()

    # driver ---------------------------------------------------------------
    def _fixpoint(self, l, r) -> None:
        while True:
            before = len(self.env)
            dl, dr = self._known(l), self._known(r)
            if dl is not None:
                self._push(l, dl)
                self._push(r, dl)
            if dr is not None:
                self._push(r, dr)
                self._push(l, dr)
            if len(self.env) == before:
                return

    def _default_one_factor(self, x: Any) -> bool:
        """Default the single unknown bare-var factor of a Mult/Div whose
        result is unknown to dimensionless. Returns True if one was found."""
        x = deref(x)
        if isinstance(x, (_Mult, _Div)):
            l, r = deref(x.left), deref(x.right)
            kl, kr = self._known(l), self._known(r)
            if kl is None and kr is not None and is_var(l):
                self._assign(l, {})
                return True
            if kr is None and kl is not None and is_var(r):
                self._assign(r, {})
                return True
            return self._default_one_factor(l) or self._default_one_factor(r)
        if isinstance(x, _BINARY):
            return self._default_one_factor(x.left) or self._default_one_factor(x.right)
        if isinstance(x, _Negate):
            return self._default_one_factor(x.operand)
        return False

    def run(self, l, r) -> tuple[dict, dict]:
        self._fixpoint(l, r)
        while any(vid not in self.env for vid in self.unknown_order):
            if not (self._default_one_factor(l) or self._default_one_factor(r)):
                missing = [self.vars[v] for v in self.unknown_order if v not in self.env]
                raise _undetermined(self.context, missing)
            self._fixpoint(l, r)
        dl, dr = self._known(l), self._known(r)
        self._push(l, dl)
        self._push(r, dr)
        if dl != dr:
            raise _mismatch(self.context, dl, dr)
        return dl, dr


def analyse(l: Any, r: Any, context: str) -> tuple[dict, dict, dict[int, dict]]:
    """Dimensions of both sides and of every Var leaf; raises the ISO term."""
    _ensure_imports()
    a = _Analysis(context)
    dl, dr = a.run(l, r)
    return dl, dr, a.env


def ground_dims(tree: Any) -> dict:
    """Dims of a fully ground tree — the positive-control entry point."""
    _ensure_imports()
    a = _Analysis("ground")
    d = a._known(tree)
    a._push(tree, d)
    return d
