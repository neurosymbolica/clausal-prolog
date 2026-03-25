"""Backward compatibility — canonical implementation in clausal.modules.py.hmac."""
from clausal.modules.py.hmac import *  # noqa: F401,F403
from clausal.modules.py.hmac import (  # noqa: F401 — re-export internals for tests
    _HmacPredicate, _simple_to_trampoline, _to_bytes,
    _sign_3, _sign_4, _verify_3, _verify_4,
)
