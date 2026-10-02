"""clausal.modules.currency — money constructors, rounding, display, accessors.

Currency amounts are Decimal-backed units base dimensions (see
clausal.modules.countries). This module adds the user-facing builtins:
exact constructors, explicit-mode rounding/formatting, and metadata accessors.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Callable

from clausal.terms import Quantity, _quantize_to_scale, _format_money
from clausal.logic.cells import chars, is_chars, chars_text  # stage 1: the chars carrier
from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.logic.exceptions import (
    LogicException, domain_error, instantiation_error, type_error)
from clausal.modules.py import ModulePredicate


def _simple_to_trampoline(simple_fn: Callable) -> Callable:
    """Wrap a k-less simple-mode generator fn(*args, trail) → trampoline."""
    def trampoline_fn(this_generator, _proceed, _fail, _catcher, *args):
        for _ in simple_fn(*args):
            yield (_proceed, None)
        yield (_fail, DONE)
    return trampoline_fn


def _currency_of(amount):
    """Return the ``UnitInfo`` of a currency Quantity, or None.

    Returns the METADATA, not the dimension key. The key is about to become a
    bare atom carrying nothing, and every caller here (`_quantize`,
    `_format_money`) wants `.scale` / `.symbol` / `.iso_code` / `.name` --
    never the key itself as a key or a constructor.
    """
    from clausal.terms import _currency_info            # noqa: PLC0415
    if not isinstance(amount, Quantity) or len(amount.dims) != 1:
        return None
    (key, exp), = amount.dims.items()
    return _currency_info(key) if exp == 1 else None


def _quantize(amount, currency, mode_str):
    """Return the amount's value quantized to the currency's scale using mode_str."""
    return _quantize_to_scale(amount.value, currency.scale, mode_str)


# ── argument checks (operator rulings 2026-10-02) ─────────────────────────────
#
# Every one of these used to be a bare ``return`` -- no solutions, no error --
# so an unbound argument or a non-currency in a currency position made the
# rule silently not fire. Each is a caller error, not a "no".


def _require_currency(value, context):
    """*value* deref'd, which must be a currency: instantiation_error when
    unbound, ``type_error(currency, V)`` when it is anything else."""
    c = deref(value)
    if is_var(c):
        raise LogicException(instantiation_error(context))
    if not getattr(c, "is_currency", False):
        raise LogicException(type_error("currency", c, context))
    return c


def _require_money(value, context):
    """The ``UnitInfo`` of a money amount (a Quantity in exactly one currency).

    Unbound -> instantiation_error; not a quantity -> ``type_error(quantity,
    A)`` (the type name ``quantity_number/2`` already uses); a quantity that
    is not an amount of ONE currency (metres, euro/hour) is the right type
    out of range -> ``domain_error(money, A)``.
    """
    a = deref(value)
    if is_var(a):
        raise LogicException(instantiation_error(context))
    if not isinstance(a, Quantity):
        raise LogicException(type_error("quantity", a, context))
    c = _currency_of(a)
    if c is None:
        raise LogicException(domain_error("money", a, context))
    return a, c


def _require_mode_text(value, table, domain, context):
    """A rounding-mode / display-style argument: an ATOM or string naming an
    entry of *table*. Unbound -> instantiation_error; not text ->
    ``type_error(text, V)``; text naming no entry -> ``domain_error(Domain, V)``
    (it used to reach ``_quantize_to_scale`` and escape as a raw ValueError)."""
    from clausal.modules.py import to_text            # noqa: PLC0415
    v = deref(value)
    if is_var(v):
        raise LogicException(instantiation_error(context))
    text = to_text(v)
    if text is None:
        raise LogicException(type_error("text", v, context))
    if text not in table:
        raise LogicException(domain_error(domain, v, context))
    return text


_MONEY_STYLES = ("symbol", "code", "name", "plain")


def _rounding_modes():
    from clausal.terms import _MONEY_ROUNDING           # noqa: PLC0415
    return _MONEY_ROUNDING


# ── constructors ──────────────────────────────────────────────────────────────

def _money_impl(text, currency, out, trail):
    t = deref(text)
    if is_var(t):
        raise LogicException(instantiation_error("money/3"))
    c = _require_currency(currency, "money/3")
    q = Quantity(Decimal(chars_text(t) if is_chars(t) else str(t)), c)   # CHECKED path (precision check)
    if unify(deref(out), q, trail):
        yield None


def _money_precise_impl(text, currency, out, trail):
    t = deref(text)
    if is_var(t):
        raise LogicException(instantiation_error("money_precise/3"))
    c = _require_currency(currency, "money_precise/3")
    q = Quantity(Decimal(chars_text(t) if is_chars(t) else str(t)), dict(c._dims))   # UNCHECKED path (raw dict dims)
    if unify(deref(out), q, trail):
        yield None


# ── accessors ─────────────────────────────────────────────────────────────────

def _accessor(attr):
    """An accessor is a FUNCTION of a currency, so an unbound first argument
    asks nothing and must not answer nothing.

    It used to `return` — no solutions, no error — which is the fail-open
    shape: a typo'd field or an unbound variable becomes "no answer" and the
    rule silently does not fire. Every one of `currency_scale`,
    `currency_symbol`, `currency_start` and `currency_end` had it.

    `currency_code/2` is the exception and does not use this factory: a code
    identifies a currency, so that one is a RELATION and runs backwards.
    """
    def impl(currency, out, trail):
        c = _require_currency(currency, f"currency_{attr}/2")
        if unify(deref(out), getattr(c, attr), trail):
            yield None
    return impl


def _currency_records():
    from clausal.modules.countries import _data              # noqa: PLC0415
    return _data.CURRENCIES, _data.CURRENCY_BINDINGS


def _currency_for_code(text):
    """The currency object an ISO 4217 code names, or None.

    Case-insensitive, which covers **the two spellings that can exist**: a
    lowercase atom (`eur`, which is also how downstream code writes it) and an
    uppercase one (`"EUR"`). A mixed-case `Eur` cannot be written as an atom
    at all — TitleCase is a logic VARIABLE since 2026-09-10, so it would
    silently become a fresh variable rather than a misspelled code
    (a downstream user, 2026-09-11). Strings in either case work too.
    """
    import importlib                                          # noqa: PLC0415
    records, bindings = _currency_records()
    want = text.upper()
    for r in records:
        if r["code"] == want:
            module = importlib.import_module(
                f"clausal.modules.countries.{r['jurisdiction']}")
            return getattr(module, bindings[r["code"]])
    return None


def _currency_code_impl(currency, code, trail):
    """currency_code(?Currency, ?Code) — a RELATION, not an accessor.

    ISO 4217 codes are a bijection with the vocabulary (254 currencies, 254
    distinct codes, measured), so every mode is unambiguous:

      (+C, ?Code)  the currency's code, as the canonical UPPERCASE string —
                   unchanged, so nothing that worked before breaks.
      (-C, +Code)  the currency a code names. The code may be an ATOM or a
                   STRING, in either case: `"EUR"` written in a rulebase is
                   an atom while `iso_code` is a Python string, and before
                   this they did not unify, so even the forward CHECK
                   `currency_code(euro, "EUR")` failed silently.
      (-C, -Code)  enumerates the whole vocabulary.

    Enumeration yields ALL 254, **historical included**, because the relation
    has to be complete: the forward mode answers for a withdrawn currency, so
    the reverse and the enumeration must reach it too. "Is this a CURRENT
    currency" is a different question and `currency_end/2` answers it;
    conflating them would make this relation asymmetric.
    """
    c, k = deref(currency), deref(code)
    if not is_var(c):
        _require_currency(c, "currency_code/2")
        if unify(deref(code), chars(c.iso_code), trail):   # stage 1: a code is text
            yield None
        return
    if not is_var(k):
        # A CODE that is not text (a number, a compound) is a caller error:
        # type_error (ruling 2026-10-02; it used to fail). A TEXT naming no
        # ISO 4217 currency stays an ordinary "no" -- this is a lookup
        # RELATION and must stay usable as a test
        # (test_an_unknown_code_fails_rather_than_raising).
        from clausal.modules.py import to_text            # noqa: PLC0415
        text = to_text(k)
        if text is None:
            raise LogicException(type_error("text", k, "currency_code/2"))
        found = _currency_for_code(text)
        if found is not None and unify(deref(currency), found, trail):
            yield None
        return
    records, bindings = _currency_records()
    import importlib                                          # noqa: PLC0415
    for r in records:
        module = importlib.import_module(
            f"clausal.modules.countries.{r['jurisdiction']}")
        obj = getattr(module, bindings[r["code"]])
        mark = trail.mark()
        if (unify(deref(currency), obj, trail)
                and unify(deref(code), chars(r["code"]), trail)):   # stage 1
            yield None
        trail.undo(mark)


money = ModulePredicate("money")
money._register(3, _simple_to_trampoline(_money_impl))

money_precise = ModulePredicate("money_precise")
money_precise._register(3, _simple_to_trampoline(_money_precise_impl))

currency_scale = ModulePredicate("currency_scale")
currency_scale._register(2, _simple_to_trampoline(_accessor("scale")))

currency_code = ModulePredicate("currency_code")
currency_code._register(2, _simple_to_trampoline(_currency_code_impl))

currency_symbol = ModulePredicate("currency_symbol")
currency_symbol._register(2, _simple_to_trampoline(_accessor("symbol")))

# in-service date range (ISO date string, or None for open-ended/unknown)
currency_start = ModulePredicate("currency_start")
currency_start._register(2, _simple_to_trampoline(_accessor("start")))

currency_end = ModulePredicate("currency_end")
currency_end._register(2, _simple_to_trampoline(_accessor("end")))




def _mode_text(val) -> str:
    """The ``str`` a rounding-MODE / display-STYLE argument denotes.

    THE FLIP (spec §9.4): ``half_up`` written in a ``.clausal`` file is the
    ATOM ``("half_up",)``, and ``str()`` on it is the Python tuple repr --
    which is what the rounding table was being asked to look up.  Text is a
    string or an atom; both convert to the same ``str``.
    """
    from clausal.modules.py import to_text
    text = to_text(val)
    return text if text is not None else str(val)


# ── rounding & display ────────────────────────────────────────────────────────

def _money_round_impl(amount, mode, out, trail):
    a, c = _require_money(amount, "money_round/3")
    m = _require_mode_text(mode, _rounding_modes(), "rounding_mode", "money_round/3")
    q = Quantity(_quantize(a, c, m), dict(a.dims))   # UNCHECKED raw dict
    if unify(deref(out), q, trail):
        yield None


def _format_value(a, c, mode_str, style):
    return _format_money(a.value, c, style, mode_str)


def _money_str_impl(amount, mode, out, trail):
    a, c = _require_money(amount, "money_str/3")
    m = _require_mode_text(mode, _rounding_modes(), "rounding_mode", "money_str/3")
    if unify(deref(out), chars(_format_value(a, c, m, "code")), trail):   # stage 1
        yield None


def _money_format_impl(amount, style, mode, out, trail):
    a, c = _require_money(amount, "money_format/4")
    sty = _require_mode_text(style, _MONEY_STYLES, "money_style", "money_format/4")
    m = _require_mode_text(mode, _rounding_modes(), "rounding_mode", "money_format/4")
    if unify(deref(out), _format_value(a, c, m, sty), trail):
        yield None


money_round = ModulePredicate("money_round")
money_round._register(3, _simple_to_trampoline(_money_round_impl))

money_str = ModulePredicate("money_str")
money_str._register(3, _simple_to_trampoline(_money_str_impl))

money_format = ModulePredicate("money_format")
money_format._register(4, _simple_to_trampoline(_money_format_impl))
