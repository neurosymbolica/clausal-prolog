"""Backward compatibility — canonical implementation in clausal.modules.py.yaml."""
from clausal.modules.py.yaml import *  # noqa: F401,F403
from clausal.modules.py.yaml import (  # noqa: F401 — re-export internals for tests
    _YamlPredicate, _simple_to_trampoline,
    _read_2, _write_2, _read_all_2, _write_all_2,
    _read_file_2, _write_file_2, _get_3,
)
