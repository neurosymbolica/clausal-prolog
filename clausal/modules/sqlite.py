"""Backward compatibility — canonical implementation in clausal.modules.py.sqlite."""
from clausal.modules.py.sqlite import *  # noqa: F401,F403
from clausal.modules.py.sqlite import (  # noqa: F401 — re-export internals for tests
    _SQLitePredicate, _simple_to_trampoline,
    _CONNECTIONS, _LOCK, _get_connection,
    _sqlite_connect_2, _sqlite_disconnect_1, _sqlite_current_connection_1,
    _sqlite_query_3, _sqlite_query_4, _sqlite_exec_2, _sqlite_exec_3,
    _sqlite_row_count_3, _sqlite_table_2, _sqlite_column_4,
)
