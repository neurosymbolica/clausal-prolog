"""Backward compatibility — canonical implementation in clausal.modules.units."""
from clausal.modules.units import *  # noqa: F401,F403
from clausal.modules import units as _units


def __getattr__(name: str):
    # A star import copies only the names bound in the canonical module; the
    # deprecated TitleCase unit spellings resolve through its ``__getattr__``
    # (and warn there), so forward them.
    return getattr(_units, name)
