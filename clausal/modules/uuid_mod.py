"""Backward compatibility — canonical implementation in clausal.modules.py.uuid."""
from clausal.modules.py.uuid import *  # noqa: F401,F403
from clausal.modules.py.uuid import (  # noqa: F401 — re-export internals for tests
    _UuidPredicate, _simple_to_trampoline, _resolve_namespace,
    _NAMESPACE_ALIASES,
    _uuid4_1, _uuid1_1, _uuid3_3, _uuid5_3,
    _uuid_str_2, _uuid_hex_2, _uuid_urn_2, _uuid_bytes_2, _uuid_int_2,
    _uuid_version_2, _uuid_fields_7, _is_uuid_1,
)
