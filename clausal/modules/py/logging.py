"""clausal.modules.py.logging — Structured logging predicates for Clausal.

Wraps Python's ``logging`` module, exposing logger creation, level
management, handler configuration, and leveled log output as Clausal
predicates.

Import via::

    -import_from(py.logging, [GetLogger, Info, Debug, Warning, Error, Critical,
                       SetLevel, GetLevel, IsEnabledFor, Log,
                       AddHandler, RemoveHandler,
                       StreamHandler, FileHandler, SetFormatter,
                       BasicConfig])

Or via module import::

    -import_module(py.logging)
    # then use py.logging.GetLogger(...), py.logging.Info(...), etc.

Logging predicates always succeed (they are side-effects).
Messages use Clausal's f-string support for interpolation::

    Info(Logger_, f"User {UserID_} logged in")
"""

from __future__ import annotations

from clausal.modules.py import _import_stdlib
_pylogging = _import_stdlib("logging")

import sys as _sys
from typing import Any, Callable

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.trampoline import DONE


# ── Adapter ──────────────────────────────────────────────────────────────────


class _LoggingPredicate:
    """Adapter with ``_get_dispatch()`` for a logging predicate.

    Supports multi-arity dispatch (e.g. Info/1 + Info/2).
    """

    __slots__ = ("_name", "_dispatch_fns")

    def __init__(self, name: str) -> None:
        self._name = name
        self._dispatch_fns: dict[int, Callable] = {}

    def _register(self, arity: int, fn: Callable) -> None:
        self._dispatch_fns[arity] = fn

    def _get_dispatch(self) -> Callable:
        if len(self._dispatch_fns) == 1:
            return next(iter(self._dispatch_fns.values()))
        return self._multi_dispatch

    def _multi_dispatch(self, this_generator, parent, *args):
        arity = len(args) - 1  # exclude trail
        fn = self._dispatch_fns.get(arity)
        if fn is None:
            yield (parent, DONE)
            return
        yield from fn(this_generator, parent, *args)

    def __repr__(self) -> str:
        arities = sorted(self._dispatch_fns)
        return f"logging.{self._name}/{arities}"


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


def _resolve_level(level: Any) -> int:
    """Convert a level name (string) or int to a Python logging level int."""
    level = deref(level)
    if isinstance(level, int):
        return level
    name = str(level).lower()
    return _LEVEL_MAP.get(name, _pylogging.NOTSET)


def _resolve_logger(logger_val: Any) -> _pylogging.Logger:
    """Resolve a logger argument to a Python Logger instance."""
    logger_val = deref(logger_val)
    if isinstance(logger_val, _pylogging.Logger):
        return logger_val
    # Treat as a logger name string.
    return _pylogging.getLogger(str(logger_val))


def _trampoline(fn):
    """Wrap a simple-mode fn(*args, trail, k) → trampoline protocol."""
    def trampoline_fn(this_generator, parent, *args):
        for _ in fn(*args, None):
            yield (parent, None)
        yield (parent, DONE)
    return trampoline_fn


# ── GetLogger ────────────────────────────────────────────────────────────────


def _get_logger_1(logger_out, trail, k):
    """GetLogger/1: unify with the default 'clausal' logger."""
    lg = _pylogging.getLogger(_DEFAULT_LOGGER_NAME)
    if unify(logger_out, lg, trail):
        yield None


def _get_logger_2(name, logger_out, trail, k):
    """GetLogger/2: unify Logger with getLogger(Name)."""
    name = deref(name)
    lg = _pylogging.getLogger(str(name))
    if unify(logger_out, lg, trail):
        yield None


# ── SetLevel / GetLevel ──────────────────────────────────────────────────────


def _set_level_2(logger, level, trail, k):
    """SetLevel/2: set the logger's level."""
    lg = _resolve_logger(logger)
    lv = _resolve_level(level)
    lg.setLevel(lv)
    yield None


def _get_level_2(logger, level_out, trail, k):
    """GetLevel/2: unify Level with the logger's effective level name."""
    lg = _resolve_logger(logger)
    name = _pylogging.getLevelName(lg.getEffectiveLevel())
    if unify(level_out, name, trail):
        yield None


# ── IsEnabledFor ─────────────────────────────────────────────────────────────


def _is_enabled_for_2(logger, level, trail, k):
    """IsEnabledFor/2: succeeds if logger would process level."""
    lg = _resolve_logger(logger)
    lv = _resolve_level(level)
    if lg.isEnabledFor(lv):
        yield None


# ── Logging predicates ───────────────────────────────────────────────────────


def _log_3(logger, level, msg, trail, k):
    """Log/3: log at an arbitrary level."""
    lg = _resolve_logger(logger)
    lv = _resolve_level(level)
    lg.log(lv, "%s", str(deref(msg)))
    yield None


def _debug_1(msg, trail, k):
    """Debug/1: log at DEBUG with default logger."""
    _pylogging.getLogger(_DEFAULT_LOGGER_NAME).debug("%s", str(deref(msg)))
    yield None


def _debug_2(logger, msg, trail, k):
    """Debug/2: log at DEBUG level."""
    lg = _resolve_logger(logger)
    lg.debug("%s", str(deref(msg)))
    yield None


def _info_1(msg, trail, k):
    """Info/1: log at INFO with default logger."""
    _pylogging.getLogger(_DEFAULT_LOGGER_NAME).info("%s", str(deref(msg)))
    yield None


def _info_2(logger, msg, trail, k):
    """Info/2: log at INFO level."""
    lg = _resolve_logger(logger)
    lg.info("%s", str(deref(msg)))
    yield None


def _warning_1(msg, trail, k):
    """Warning/1: log at WARNING with default logger."""
    _pylogging.getLogger(_DEFAULT_LOGGER_NAME).warning("%s", str(deref(msg)))
    yield None


def _warning_2(logger, msg, trail, k):
    """Warning/2: log at WARNING level."""
    lg = _resolve_logger(logger)
    lg.warning("%s", str(deref(msg)))
    yield None


def _error_1(msg, trail, k):
    """Error/1: log at ERROR with default logger."""
    _pylogging.getLogger(_DEFAULT_LOGGER_NAME).error("%s", str(deref(msg)))
    yield None


def _error_2(logger, msg, trail, k):
    """Error/2: log at ERROR level."""
    lg = _resolve_logger(logger)
    lg.error("%s", str(deref(msg)))
    yield None


def _critical_1(msg, trail, k):
    """Critical/1: log at CRITICAL with default logger."""
    _pylogging.getLogger(_DEFAULT_LOGGER_NAME).critical("%s", str(deref(msg)))
    yield None


def _critical_2(logger, msg, trail, k):
    """Critical/2: log at CRITICAL level."""
    lg = _resolve_logger(logger)
    lg.critical("%s", str(deref(msg)))
    yield None


# ── Handler creation ─────────────────────────────────────────────────────────


def _stream_handler_2(stream_name, handler_out, trail, k):
    """StreamHandler/2: create a StreamHandler for 'stdout' or 'stderr'."""
    stream_name = deref(stream_name)
    name = str(stream_name).lower()
    if name == "stdout":
        h = _pylogging.StreamHandler(_sys.stdout)
    elif name == "stderr":
        h = _pylogging.StreamHandler(_sys.stderr)
    else:
        h = _pylogging.StreamHandler(_sys.stderr)
    if unify(handler_out, h, trail):
        yield None


def _file_handler_2(path, handler_out, trail, k):
    """FileHandler/2: create a FileHandler for the given path."""
    path = deref(path)
    h = _pylogging.FileHandler(str(path))
    if unify(handler_out, h, trail):
        yield None


def _set_formatter_2(handler, fmt_str, trail, k):
    """SetFormatter/2: set a Formatter on a handler."""
    handler = deref(handler)
    fmt_str = deref(fmt_str)
    formatter = _pylogging.Formatter(str(fmt_str))
    handler.setFormatter(formatter)
    yield None


# ── Handler management ───────────────────────────────────────────────────────


def _add_handler_2(logger, handler, trail, k):
    """AddHandler/2: add a handler to the logger."""
    lg = _resolve_logger(logger)
    handler = deref(handler)
    lg.addHandler(handler)
    yield None


def _remove_handler_2(logger, handler, trail, k):
    """RemoveHandler/2: remove a handler from the logger."""
    lg = _resolve_logger(logger)
    handler = deref(handler)
    lg.removeHandler(handler)
    yield None


# ── BasicConfig ──────────────────────────────────────────────────────────────


def _basic_config_1(opts, trail, k):
    """BasicConfig/1: call logging.basicConfig with a dict of options.

    Supported keys: level, format, datefmt, filename, filemode, stream.
    """
    opts = deref(opts)
    kwargs = {}
    if isinstance(opts, dict):
        for key, val in opts.items():
            key = str(key)
            if key == "level":
                kwargs["level"] = _resolve_level(val)
            elif key in ("format", "datefmt", "filename", "filemode"):
                kwargs[key] = str(val)
            elif key == "stream":
                name = str(val).lower()
                if name == "stdout":
                    kwargs["stream"] = _sys.stdout
                elif name == "stderr":
                    kwargs["stream"] = _sys.stderr
        _pylogging.basicConfig(**kwargs)
    yield None


# ── Build and export predicate objects ───────────────────────────────────────

GetLogger = _LoggingPredicate("GetLogger")
GetLogger._register(1, _trampoline(_get_logger_1))
GetLogger._register(2, _trampoline(_get_logger_2))

SetLevel = _LoggingPredicate("SetLevel")
SetLevel._register(2, _trampoline(_set_level_2))

GetLevel = _LoggingPredicate("GetLevel")
GetLevel._register(2, _trampoline(_get_level_2))

IsEnabledFor = _LoggingPredicate("IsEnabledFor")
IsEnabledFor._register(2, _trampoline(_is_enabled_for_2))

Log = _LoggingPredicate("Log")
Log._register(3, _trampoline(_log_3))

Debug = _LoggingPredicate("Debug")
Debug._register(1, _trampoline(_debug_1))
Debug._register(2, _trampoline(_debug_2))

Info = _LoggingPredicate("Info")
Info._register(1, _trampoline(_info_1))
Info._register(2, _trampoline(_info_2))

Warning = _LoggingPredicate("Warning")
Warning._register(1, _trampoline(_warning_1))
Warning._register(2, _trampoline(_warning_2))

Error = _LoggingPredicate("Error")
Error._register(1, _trampoline(_error_1))
Error._register(2, _trampoline(_error_2))

Critical = _LoggingPredicate("Critical")
Critical._register(1, _trampoline(_critical_1))
Critical._register(2, _trampoline(_critical_2))

StreamHandler = _LoggingPredicate("StreamHandler")
StreamHandler._register(2, _trampoline(_stream_handler_2))

FileHandler = _LoggingPredicate("FileHandler")
FileHandler._register(2, _trampoline(_file_handler_2))

SetFormatter = _LoggingPredicate("SetFormatter")
SetFormatter._register(2, _trampoline(_set_formatter_2))

AddHandler = _LoggingPredicate("AddHandler")
AddHandler._register(2, _trampoline(_add_handler_2))

RemoveHandler = _LoggingPredicate("RemoveHandler")
RemoveHandler._register(2, _trampoline(_remove_handler_2))

BasicConfig = _LoggingPredicate("BasicConfig")
BasicConfig._register(1, _trampoline(_basic_config_1))
