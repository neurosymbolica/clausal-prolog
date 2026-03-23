"""Backward compatibility — canonical implementation in clausal.modules.py.process."""
from clausal.modules.py.process import *  # noqa: F401,F403
from clausal.modules.py.process import (  # noqa: F401 — re-export internals for tests
    _ProcessPredicate, _simple_to_trampoline,
    _shell_1, _shell_2, _shell_output_2, _shell_output_3,
    _process_create_3, _process_create_4, _sleep_1,
)
