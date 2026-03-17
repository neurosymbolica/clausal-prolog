"""Backward compatibility — canonical implementation in clausal.modules.py.re."""
from clausal.modules.py.re import *  # noqa: F401,F403
from clausal.modules.py.re import (  # noqa: F401 — re-export internals for tests
    _RegexPredicate, _simple_to_trampoline, _compile_pattern, _groups_dict,
    _match_2, _match_3, _search_2, _search_3,
    _replace_4, _split_3, _findall_3,
)
