"""Backward compatibility — canonical implementation in clausal.modules.py.hash."""
from clausal.modules.py.hash import *  # noqa: F401,F403
from clausal.modules.py.hash import (  # noqa: F401 — re-export internals for tests
    _HashPredicate, _simple_to_trampoline, _to_bytes,
    _hash_3, _hash_bytes_3,
)
