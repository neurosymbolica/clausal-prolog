"""Unit metadata, keyed by the unit's ATOM.

A unit was never a predicate: it is a named entry in a table, and the atom is
its name. This module IS that table.

Data-only by design, like ``_ratio_data``: it must never import
``clausal.modules.units``, because importing that builds 84 ``Quantity``
constants and turns the CLP units side channel on for the whole process. See
``_ratio_data``'s docstring, and ``clausal/logic/_units_flag.py``, which
promises that "a program that imports no unit module pays nothing".
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UnitInfo:
    """Everything about a unit that is NOT its dimensions or its ratio.

    Dimensions live on the quantity and the ratio on the unit constant; this is
    the display and currency metadata that used to hang off the predicate
    object serving as a dimension key. Once ``_dims`` is keyed by atoms there is
    no predicate to hang it on, and this is where it goes instead.
    """

    name: str
    is_currency: bool = False
    iso_code: str | None = None
    scale: int | None = None
    symbol: str | None = None
    historical: bool = False
    start: str | None = None
    end: str | None = None

    @property
    def _name(self) -> str:
        """Alias for :attr:`name`, so a ``UnitInfo`` can stand in for a unit
        predicate wherever one is read for display.

        ``_format_money`` takes "a currency" and reads ``.scale``, ``.symbol``,
        ``.iso_code`` and ``._name``. A test pins that it accepts the PREDICATE
        directly -- a judgment prints "dollar", not "USD" -- so the contract
        stays as it is and this completes the surface from the other side.
        """
        return self.name


#: atom -> UnitInfo. Global; see ``register`` for the conflict rule.
_TABLE: dict[str, UnitInfo] = {}


def register(atom: str, unit_info: UnitInfo) -> None:
    """Record *unit_info* under *atom*.

    Re-registering an EQUAL value is allowed -- module reloads and repeated
    test imports do it routinely, and ``UnitInfo`` is frozen so equality is by
    value. A CONFLICTING one raises: two units sharing an atom is exactly the
    unsoundness ``test_unit_identifiers_are_injective`` exists to catch, and
    silently keeping one of them would hide it behind correct-looking output.
    """
    existing = _TABLE.get(atom)
    if existing is not None and existing != unit_info:
        raise ValueError(
            f"unit atom {atom!r} is already registered with different metadata: "
            f"{existing!r} vs {unit_info!r}")
    _TABLE[atom] = unit_info


def info(atom: str) -> UnitInfo | None:
    """The metadata for *atom*, or None if it names no known unit."""
    return _TABLE.get(atom)


def is_currency(atom: str) -> bool:
    """Whether *atom* names a currency. False for an unknown atom."""
    entry = _TABLE.get(atom)
    return entry is not None and entry.is_currency
