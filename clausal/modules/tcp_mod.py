"""Backward compatibility — canonical implementation in clausal.modules.py.tcp."""
from clausal.modules.py.tcp import *  # noqa: F401,F403
from clausal.modules.py.tcp import (  # noqa: F401 — re-export internals for tests
    _TcpPredicate, _simple_to_trampoline,
    _connect_3, _listen_3, _accept_2,
    _send_2, _receive_2, _receive_3,
    _close_1, _set_timeout_2,
)
