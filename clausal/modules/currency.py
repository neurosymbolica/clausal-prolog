"""clausal.modules.currency — money constructors, rounding, display, accessors.

Currency amounts are Decimal-backed units base dimensions (see
clausal.modules.countries). This module adds the user-facing builtins:
exact constructors, explicit-mode rounding/formatting, and metadata accessors.
"""
from __future__ import annotations

from decimal import (
    Decimal, ROUND_HALF_UP, ROUND_HALF_EVEN, ROUND_HALF_DOWN,
    ROUND_UP, ROUND_DOWN, ROUND_CEILING, ROUND_FLOOR,
)
from typing import Callable

from clausal.terms import Quantity
from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py import ModulePredicate


def _simple_to_trampoline(simple_fn: Callable) -> Callable:
    """Wrap a k-less simple-mode generator fn(*args, trail) → trampoline."""
    def trampoline_fn(this_generator, _proceed, _fail, _catcher, *args):
        for _ in simple_fn(*args):
            yield (_proceed, None)
        yield (_fail, DONE)
    return trampoline_fn


_MODES = {
    "half_up": ROUND_HALF_UP,
    "half_even": ROUND_HALF_EVEN,
    "half_down": ROUND_HALF_DOWN,
    "up": ROUND_UP,
    "down": ROUND_DOWN,
    "ceiling": ROUND_CEILING,
    "floor": ROUND_FLOOR,
}


def _currency_of(amount):
    """Return the currency predicate of a currency Quantity, or None."""
    if not isinstance(amount, Quantity) or len(amount.dims) != 1:
        return None
    (key, exp), = amount.dims.items()
    if exp == 1 and getattr(key, "is_currency", False):
        return key
    return None


def _quantize(amount, currency, mode_str):
    """Return the amount's value quantized to the currency's scale using mode_str."""
    rounding = _MODES.get(mode_str)
    if rounding is None:
        raise ValueError(f"unknown rounding mode {mode_str!r}; expected one of "
                         f"{sorted(_MODES)}")
    return amount.value.quantize(Decimal(1).scaleb(-currency.scale), rounding=rounding)


# ── constructors ──────────────────────────────────────────────────────────────

def _money_impl(text, currency, out, trail):
    t, c = deref(text), deref(currency)
    if is_var(t) or is_var(c) or not getattr(c, "is_currency", False):
        return
    q = Quantity(Decimal(str(t)), c)                 # CHECKED path (precision check)
    if unify(deref(out), q, trail):
        yield None


def _money_precise_impl(text, currency, out, trail):
    t, c = deref(text), deref(currency)
    if is_var(t) or is_var(c) or not getattr(c, "is_currency", False):
        return
    q = Quantity(Decimal(str(t)), dict(c._dims))     # UNCHECKED path (raw dict dims)
    if unify(deref(out), q, trail):
        yield None


# ── accessors ─────────────────────────────────────────────────────────────────

def _accessor(attr):
    def impl(currency, out, trail):
        c = deref(currency)
        if not getattr(c, "is_currency", False):
            return
        if unify(deref(out), getattr(c, attr), trail):
            yield None
    return impl


money = ModulePredicate("money")
money._register(3, _simple_to_trampoline(_money_impl))

money_precise = ModulePredicate("money_precise")
money_precise._register(3, _simple_to_trampoline(_money_precise_impl))

currency_scale = ModulePredicate("currency_scale")
currency_scale._register(2, _simple_to_trampoline(_accessor("scale")))

currency_code = ModulePredicate("currency_code")
currency_code._register(2, _simple_to_trampoline(_accessor("iso_code")))

currency_symbol = ModulePredicate("currency_symbol")
currency_symbol._register(2, _simple_to_trampoline(_accessor("symbol")))
