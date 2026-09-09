"""Currency predicate type and factory.

A currency is a units *base dimension* (self-keyed, like metre) carrying
per-currency display metadata: minor-unit scale, ISO-4217 code, and symbol.
Dimension safety (no cross-currency addition, no coercion, scale-by-
dimensionless-only) is inherited unchanged from Quantity/units.
"""
from __future__ import annotations

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
    return pred
