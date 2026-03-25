"""Backward compatibility — canonical implementation in clausal.modules.py.csv."""
from clausal.modules.py.csv import *  # noqa: F401,F403
from clausal.modules.py.csv import (  # noqa: F401 — re-export internals for tests
    _CsvPredicate, _simple_to_trampoline, _deref_row,
    _parse_row_2, _parse_2, _parse_records_3,
    _generate_2, _generate_records_3,
    _read_file_2, _read_records_2, _write_file_2,
)
