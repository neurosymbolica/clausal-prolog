"""Backward compatibility — canonical implementation in clausal.modules.py.os."""
from clausal.modules.py.os import *  # noqa: F401,F403
from clausal.modules.py.os import (  # noqa: F401 — re-export internals for tests
    _OsPredicate, _simple_to_trampoline,
    _environment_variable_2, _set_environment_variable_2,
    _unset_environment_variable_1, _working_directory_1,
    _change_directory_1, _pid_1, _argv_1, _platform_1, _cpu_count_1,
)
