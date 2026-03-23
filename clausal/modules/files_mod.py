"""Backward compatibility — canonical implementation in clausal.modules.py.files."""
from clausal.modules.py.files import *  # noqa: F401,F403
from clausal.modules.py.files import (  # noqa: F401 — re-export internals for tests
    _FilesPredicate, _simple_to_trampoline, _require_ground_str,
    _file_exists_1, _directory_exists_1, _path_exists_1,
    _directory_files_2, _directory_entries_2,
    _file_size_2, _file_modification_time_2,
    _delete_file_1, _delete_directory_1, _rename_file_2, _copy_file_2,
    _make_directory_1, _make_directory_path_1,
    _read_file_to_string_2, _write_string_to_file_2, _append_string_to_file_2,
    _absolute_path_2, _join_path_3, _split_path_3, _file_extension_2,
    _temp_file_1, _temp_directory_1,
)
