"""Backward compatibility — canonical implementation in clausal.modules.py.logging."""
from clausal.modules.py.logging import *  # noqa: F401,F403
from clausal.modules.py.logging import (  # noqa: F401 — re-export internals for tests
    _LoggingPredicate, _trampoline, _resolve_level, _resolve_logger,
    _DEFAULT_LOGGER_NAME, _LEVEL_MAP,
    _get_logger_1, _get_logger_2, _set_level_2, _get_level_2,
    _is_enabled_for_2, _log_3,
    _debug_1, _debug_2, _info_1, _info_2,
    _warning_1, _warning_2, _error_1, _error_2,
    _critical_1, _critical_2,
    _stream_handler_2, _file_handler_2, _set_formatter_2,
    _add_handler_2, _remove_handler_2, _basic_config_1,
)
