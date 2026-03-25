"""Backward compatibility — canonical implementation in clausal.modules.py.pbkdf2."""
from clausal.modules.py.pbkdf2 import *  # noqa: F401,F403
from clausal.modules.py.pbkdf2 import (  # noqa: F401 — re-export internals for tests
    _Pbkdf2Predicate, _simple_to_trampoline, _to_bytes,
    _derive_4, _derive_5,
)
