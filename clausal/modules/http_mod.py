"""Backward compatibility — canonical implementation in clausal.modules.py.http."""
from clausal.modules.py.http import *  # noqa: F401,F403
from clausal.modules.py.http import (  # noqa: F401 — re-export internals for tests
    _HttpPredicate, _simple_to_trampoline, _do_request, _urlopen,
    _dict_term_to_headers,
    _get_2, _get_3, _post_3, _post_4, _request_3,
    _json_get_2, _json_post_3,
)
