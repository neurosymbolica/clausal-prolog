"""clausal.modules.currency — money constructors, rounding, display, accessors.

Currency amounts are Decimal-backed units base dimensions (see
clausal.modules.countries). This module adds the user-facing builtins:
exact constructors, explicit-mode rounding/formatting, and metadata accessors.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Callable

from clausal.terms import Quantity, _quantize_to_scale, _format_money
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
    return _quantize_to_scale(amount.value, currency.scale, mode_str)


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


# ── rounding & display ────────────────────────────────────────────────────────

def _money_round_impl(amount, mode, out, trail):
    a, m = deref(amount), deref(mode)
    c = _currency_of(a)
    if c is None or is_var(m):
        return
    q = Quantity(_quantize(a, c, str(m)), dict(a.dims))   # UNCHECKED raw dict
    if unify(deref(out), q, trail):
        yield None


def _format_value(a, c, mode_str, style):
    return _format_money(a.value, c, style, mode_str)


def _money_str_impl(amount, mode, out, trail):
    a, m = deref(amount), deref(mode)
    c = _currency_of(a)
    if c is None or is_var(m):
        return
    if unify(deref(out), _format_value(a, c, str(m), "code"), trail):
        yield None


def _money_format_impl(amount, style, mode, out, trail):
    a, sty, m = deref(amount), deref(style), deref(mode)
    c = _currency_of(a)
    if c is None or is_var(sty) or is_var(m):
        return
    if unify(deref(out), _format_value(a, c, str(m), str(sty)), trail):
        yield None


money_round = ModulePredicate("money_round")
money_round._register(3, _simple_to_trampoline(_money_round_impl))

money_str = ModulePredicate("money_str")
money_str._register(3, _simple_to_trampoline(_money_str_impl))

money_format = ModulePredicate("money_format")
money_format._register(4, _simple_to_trampoline(_money_format_impl))
