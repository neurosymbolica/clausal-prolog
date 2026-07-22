"""Currency predicate type and factory.

A currency is a units *base dimension* (self-keyed, like Metre) carrying
per-currency display metadata: minor-unit scale, ISO-4217 code, and symbol.
Dimension safety (no cross-currency addition, no coercion, scale-by-
dimensionless-only) is inherited unchanged from Quantity/units.
"""
from __future__ import annotations

from clausal.modules.units import _UnitsPredicate


class _CurrencyPredicate(_UnitsPredicate):
    """A units base-dimension predicate that denotes a currency."""

    __slots__ = ("is_currency", "iso_code", "scale", "symbol")

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.is_currency = True
        self.iso_code = None
        self.scale = None
        self.symbol = None


def _make_currency(name: str, iso_code: str, scale: int, symbol: str) -> _CurrencyPredicate:
    """Create a self-keyed currency base dimension with display metadata."""
    pred = _CurrencyPredicate(name)
    pred._dims = {pred: 1}          # self-referential key — a base dimension
    pred.iso_code = iso_code
    pred.scale = scale
    pred.symbol = symbol
    return pred
