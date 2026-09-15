"""Currency predicate type and factory.

A currency is a units *base dimension* (self-keyed, like metre) carrying
per-currency display metadata: minor-unit scale, ISO-4217 code, and symbol.
Dimension safety (no cross-currency addition, no coercion, scale-by-
dimensionless-only) is inherited unchanged from Quantity/units.
"""
from __future__ import annotations

from decimal import Decimal

from clausal.modules.units import _UnitsPredicate


class _CurrencyPredicate(_UnitsPredicate):
    """A units base-dimension predicate that denotes a currency.

    ``historical`` is True for a withdrawn/superseded currency (e.g. the
    Deutsche Mark). Historical currencies exist so legal rulebases can reason
    about obligations denominated in them; they are named by their ISO code
    (``germany.dem``) rather than a base word, since successive currencies of
    one country reuse the same word.
    """

    __slots__ = ("is_currency", "iso_code", "scale", "symbol", "historical",
                 "start", "end")

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.is_currency = True
        self.iso_code = None
        self.scale = None
        self.symbol = None
        self.historical = False
        self.start = None   # in-service start, ISO date string or None
        self.end = None     # in-service end, ISO date string or None (open)

    def __repr__(self) -> str:
        tag = " historical" if self.historical else ""
        return f"<currency{tag} {self._name} ({self.iso_code})>"


def _make_currency(name: str, iso_code: str, scale: int, symbol: str,
                   start: str | None = None, end: str | None = None,
                   historical: bool = False) -> _CurrencyPredicate:
    """Create a self-keyed currency base dimension with display metadata.

    ``start``/``end`` are the in-service date range (ISO strings, or None for
    open-ended/unknown); a future ``start`` denotes a scheduled currency not yet
    in use.
    """
    pred = _CurrencyPredicate(name)
    pred._dims = {pred: 1}          # self-referential key — a base dimension
    pred.iso_code = iso_code
    pred.scale = scale
    pred.symbol = symbol
    pred.start = start
    pred.end = end
    pred.historical = historical
    # Keyed by the BINDING name -- what _unit_identifier answers and what a
    # rulebase writes -- not `name`, which `dollar` shares twenty-two ways.
    from clausal.modules import _unit_registry          # noqa: PLC0415
    from clausal.terms import _unit_identifier          # noqa: PLC0415
    _unit_registry.register(
        _unit_identifier(pred),
        _unit_registry.UnitInfo(name=name, is_currency=True, iso_code=iso_code,
                                scale=scale, symbol=symbol, historical=historical,
                                start=start, end=end))
    return pred


def _make_minor_unit(currency: _CurrencyPredicate) -> "Quantity":
    """The currency's MINOR unit, as an ordinary scaled unit.

    ``cent = _make_minor_unit(dollar)`` is ``Quantity(Decimal('0.01'),
    {dollar: 1})`` -- the same shape as ``kilometre = Quantity(1000,
    {metre: 1})``. Being an ordinary scaled unit is the whole design: it
    needs no special case in the directive, in the annotation sugar or in
    arithmetic, and ``155000 (cent)`` normalises to its base exactly as
    ``5 (kilometre)`` does.

    Two properties are load-bearing and neither is optional:

    * the factor is **derived from the currency's ISO scale**, so it cannot
      drift from the scale the rounding and formatting paths use; and
    * it is a **Decimal**, built with ``scaleb`` rather than written as a
      literal. ``gram = Quantity(1e-3, {kilogram: 1})`` carries a FLOAT
      factor, which is why ``7 gram`` is 0.007 in binary floating point.
      Money in this corpus is kept in exact decimal precisely to stay out of
      that, and a factor is the one place it could get back in.

    A scale-0 currency (yen, won -- 16 of them) has no minor unit in
    circulation, and one invented at scale 0 would make ``1 minor`` equal
    ``1 yen``. Refused rather than defined.
    """
    from clausal.terms import Quantity          # noqa: PLC0415 (cycle at import)
    if not currency.scale:
        raise ValueError(
            f"{currency._name} ({currency.iso_code}) has no minor unit: its "
            f"ISO 4217 scale is {currency.scale}, so the minor unit would "
            f"equal the currency itself")
    return Quantity(Decimal(1).scaleb(-currency.scale), {currency: 1})
