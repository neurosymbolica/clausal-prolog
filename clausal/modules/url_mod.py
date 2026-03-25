"""Backward compatibility — canonical implementation in clausal.modules.py.url."""
from clausal.modules.py.url import *  # noqa: F401,F403
from clausal.modules.py.url import (  # noqa: F401 — re-export internals for tests
    _UrlPredicate, _simple_to_trampoline,
    _encode_2, _decode_2, _parse_2, _join_2,
)
