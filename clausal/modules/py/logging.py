"""clausal.modules.py.logging — Structured logging predicates for Clausal.

Wraps Python's ``logging`` module, exposing logger creation, level
management, handler configuration, and leveled log output as Clausal
predicates.

Import via::

    -import_from(py.logging, [get_logger, info, debug, warning, error, critical,
                       set_level, get_level, is_enabled_for, log,
                       add_handler, remove_handler,
                       stream_handler, file_handler, set_formatter,
                       basic_config])

Or via module import::

    -import_module(py.logging)
    # then use py.logging.get_logger(...), py.logging.info(...), etc.

Logging predicates always succeed (they are side-effects).
Messages use Clausal's f-string support for interpolation::

    info(Logger_, f"User {UserID_} logged in")
"""

from __future__ import annotations

from clausal.modules.py import (
    text_result,   # stage 1: a str result is the chars carrier
    _import_stdlib, ModulePredicate, simple_to_trampoline, text_or_str,
    to_text,
)

_pylogging = _import_stdlib("logging")

import sys as _sys
from typing import Any

from clausal.logic.variables import Var, deref, is_var, unify


# ── Helpers ──────────────────────────────────────────────────────────────────

_DEFAULT_LOGGER_NAME = "clausal"

_LEVEL_MAP = {
    "debug": _pylogging.DEBUG,
    "info": _pylogging.INFO,
    "warning": _pylogging.WARNING,
    "warn": _pylogging.WARNING,
    "error": _pylogging.ERROR,
    "critical": _pylogging.CRITICAL,
    "fatal": _pylogging.CRITICAL,
}



def _message_text(val) -> str:
    """The text of a log MESSAGE, which may be any term.

    Text (a string or an atom) crosses as itself; anything else is rendered
    by the engine's own unquoted writer, so a compound logs as ``f(a, b)``
    rather than as a Python tuple repr.
    """
    text = to_text(val)
    if text is not None:
        return text
    from clausal.terms import term_str
    return term_str(val, quoted=False)


def _resolve_level(level: Any) -> int:
    """Convert a level name (string) or int to a Python logging level int."""
    level = deref(level)
    if isinstance(level, int):
        return level
    name = text_or_str(level).lower()
    return _LEVEL_MAP.get(name, _pylogging.NOTSET)


def _resolve_logger(logger_val: Any) -> _pylogging.Logger:
    """Resolve a logger argument to a Python Logger instance."""
    logger_val = deref(logger_val)
    if isinstance(logger_val, _pylogging.Logger):
        return logger_val
    # Treat as a logger name string.
    return _pylogging.getLogger(text_or_str(logger_val))


# ── get_logger ────────────────────────────────────────────────────────────────


def _get_logger_1(logger_out, trail, k):
    """get_logger/1: unify with the default 'clausal' logger."""
    lg = _pylogging.getLogger(_DEFAULT_LOGGER_NAME)
    if unify(logger_out, lg, trail):
        yield None


def _get_logger_2(name, logger_out, trail, k):
    """get_logger/2: unify Logger with getLogger(Name)."""
    name = deref(name)
    lg = _pylogging.getLogger(text_or_str(name))
    if unify(logger_out, lg, trail):
        yield None


# ── set_level / get_level ──────────────────────────────────────────────────────


def _set_level_2(logger, level, trail, k):
    """set_level/2: set the logger's level."""
    lg = _resolve_logger(logger)
    lv = _resolve_level(level)
    lg.setLevel(lv)
    yield None


def _get_level_2(logger, level_out, trail, k):
    """get_level/2: unify Level with the logger's effective level name."""
    lg = _resolve_logger(logger)
    name = _pylogging.getLevelName(lg.getEffectiveLevel())
    if unify(level_out, text_result(name), trail):
        yield None


# ── is_enabled_for ─────────────────────────────────────────────────────────────


def _is_enabled_for_2(logger, level, trail, k):
    """is_enabled_for/2: succeeds if logger would process level."""
    lg = _resolve_logger(logger)
    lv = _resolve_level(level)
    if lg.isEnabledFor(lv):
        yield None


# ── Logging predicates ───────────────────────────────────────────────────────


def _log_3(logger, level, msg, trail, k):
    """log/3: log at an arbitrary level."""
    lg = _resolve_logger(logger)
    lv = _resolve_level(level)
    lg.log(lv, "%s", _message_text(deref(msg)))
    yield None


def _debug_1(msg, trail, k):
    """debug/1: log at DEBUG with default logger."""
    _pylogging.getLogger(_DEFAULT_LOGGER_NAME).debug("%s", _message_text(deref(msg)))
    yield None


def _debug_2(logger, msg, trail, k):
    """debug/2: log at DEBUG level."""
    lg = _resolve_logger(logger)
    lg.debug("%s", _message_text(deref(msg)))
    yield None


def _info_1(msg, trail, k):
    """info/1: log at INFO with default logger."""
    _pylogging.getLogger(_DEFAULT_LOGGER_NAME).info("%s", _message_text(deref(msg)))
    yield None


def _info_2(logger, msg, trail, k):
    """info/2: log at INFO level."""
    lg = _resolve_logger(logger)
    lg.info("%s", _message_text(deref(msg)))
    yield None


def _warning_1(msg, trail, k):
    """warning/1: log at WARNING with default logger."""
    _pylogging.getLogger(_DEFAULT_LOGGER_NAME).warning("%s", _message_text(deref(msg)))
    yield None


def _warning_2(logger, msg, trail, k):
    """warning/2: log at WARNING level."""
    lg = _resolve_logger(logger)
    lg.warning("%s", _message_text(deref(msg)))
    yield None


def _error_1(msg, trail, k):
    """error/1: log at ERROR with default logger."""
    _pylogging.getLogger(_DEFAULT_LOGGER_NAME).error("%s", _message_text(deref(msg)))
    yield None


def _error_2(logger, msg, trail, k):
    """error/2: log at ERROR level."""
    lg = _resolve_logger(logger)
    lg.error("%s", _message_text(deref(msg)))
    yield None


def _critical_1(msg, trail, k):
    """critical/1: log at CRITICAL with default logger."""
    _pylogging.getLogger(_DEFAULT_LOGGER_NAME).critical("%s", _message_text(deref(msg)))
    yield None


def _critical_2(logger, msg, trail, k):
    """critical/2: log at CRITICAL level."""
    lg = _resolve_logger(logger)
    lg.critical("%s", _message_text(deref(msg)))
    yield None


# ── Handler creation ─────────────────────────────────────────────────────────


def _stream_handler_2(stream_name, handler_out, trail, k):
    """stream_handler/2: create a stream_handler for 'stdout' or 'stderr'."""
    stream_name = deref(stream_name)
    name = text_or_str(stream_name).lower()
    if name == "stdout":
        h = _pylogging.StreamHandler(_sys.stdout)
    elif name == "stderr":
        h = _pylogging.StreamHandler(_sys.stderr)
    else:
        h = _pylogging.StreamHandler(_sys.stderr)
    if unify(handler_out, h, trail):
        yield None


def _file_handler_2(path, handler_out, trail, k):
    """file_handler/2: create a file_handler for the given path."""
    path = deref(path)
    h = _pylogging.FileHandler(text_or_str(path))
    if unify(handler_out, h, trail):
        yield None


def _set_formatter_2(handler, fmt_str, trail, k):
    """set_formatter/2: set a Formatter on a handler."""
    handler = deref(handler)
    fmt_str = deref(fmt_str)
    formatter = _pylogging.Formatter(text_or_str(fmt_str))
    handler.setFormatter(formatter)
    yield None


# ── Handler management ───────────────────────────────────────────────────────


def _add_handler_2(logger, handler, trail, k):
    """add_handler/2: add a handler to the logger."""
    lg = _resolve_logger(logger)
    handler = deref(handler)
    lg.addHandler(handler)
    yield None


def _remove_handler_2(logger, handler, trail, k):
    """remove_handler/2: remove a handler from the logger."""
    lg = _resolve_logger(logger)
    handler = deref(handler)
    lg.removeHandler(handler)
    yield None


# ── basic_config ──────────────────────────────────────────────────────────────


def _basic_config_1(opts, trail, k):
    """basic_config/1: call logging.basicConfig with a dict of options.

    Supported keys: level, format, datefmt, filename, filemode, stream.
    """
    opts = deref(opts)
    kwargs = {}
    if isinstance(opts, dict):
        for key, val in opts.items():
            key = text_or_str(key)
            if key == "level":
                kwargs["level"] = _resolve_level(val)
            elif key in ("format", "datefmt", "filename", "filemode"):
                kwargs[key] = text_or_str(val)
            elif key == "stream":
                name = text_or_str(val).lower()
                if name == "stdout":
                    kwargs["stream"] = _sys.stdout
                elif name == "stderr":
                    kwargs["stream"] = _sys.stderr
        _pylogging.basicConfig(**kwargs)
    yield None


# ── Build and export predicate objects ───────────────────────────────────────

get_logger = ModulePredicate("get_logger")
get_logger._register(1, simple_to_trampoline(_get_logger_1))
get_logger._register(2, simple_to_trampoline(_get_logger_2))

set_level = ModulePredicate("set_level")
set_level._register(2, simple_to_trampoline(_set_level_2))

get_level = ModulePredicate("get_level")
get_level._register(2, simple_to_trampoline(_get_level_2))

is_enabled_for = ModulePredicate("is_enabled_for")
is_enabled_for._register(2, simple_to_trampoline(_is_enabled_for_2))

log = ModulePredicate("log")
log._register(3, simple_to_trampoline(_log_3))

debug = ModulePredicate("debug")
debug._register(1, simple_to_trampoline(_debug_1))
debug._register(2, simple_to_trampoline(_debug_2))

info = ModulePredicate("info")
info._register(1, simple_to_trampoline(_info_1))
info._register(2, simple_to_trampoline(_info_2))

warning = ModulePredicate("warning")
warning._register(1, simple_to_trampoline(_warning_1))
warning._register(2, simple_to_trampoline(_warning_2))

error = ModulePredicate("error")
error._register(1, simple_to_trampoline(_error_1))
error._register(2, simple_to_trampoline(_error_2))

critical = ModulePredicate("critical")
critical._register(1, simple_to_trampoline(_critical_1))
critical._register(2, simple_to_trampoline(_critical_2))

stream_handler = ModulePredicate("stream_handler")
stream_handler._register(2, simple_to_trampoline(_stream_handler_2))

file_handler = ModulePredicate("file_handler")
file_handler._register(2, simple_to_trampoline(_file_handler_2))

set_formatter = ModulePredicate("set_formatter")
set_formatter._register(2, simple_to_trampoline(_set_formatter_2))

add_handler = ModulePredicate("add_handler")
add_handler._register(2, simple_to_trampoline(_add_handler_2))

remove_handler = ModulePredicate("remove_handler")
remove_handler._register(2, simple_to_trampoline(_remove_handler_2))

basic_config = ModulePredicate("basic_config")
basic_config._register(1, simple_to_trampoline(_basic_config_1))
