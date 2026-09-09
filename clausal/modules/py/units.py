"""Backward compatibility — canonical implementation in clausal.modules.units."""
from clausal.modules.units import *  # noqa: F401,F403
from clausal.modules import units as _units


def __getattr__(name: str):
    # A star import copies only the names bound in the canonical module; the
    # deprecated unit spellings resolve through its alias table (and warn
    # there, attributed to the line that read the name — not to this
    # forwarder).
    return _units._resolve_deprecated_name(name, __name__)
