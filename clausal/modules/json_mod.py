"""Backward compatibility — canonical implementation in clausal.modules.py.json."""
from clausal.modules.py.json import *  # noqa: F401,F403
from clausal.modules.py.json import (  # noqa: F401 — re-export internals for tests
    _JsonPredicate, _simple_to_trampoline,
    _python_to_clausal, _clausal_to_python,
    _parse_2, _generate_2, _pretty_generate_2,
    _get_3, _read_file_2, _write_file_2,
)
