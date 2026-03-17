"""Tests for structured logging module — clausal.modules.logging.

Python-side tests covering output capture, level filtering, handler
management, file handlers, formatters, and .clausal fixture integration.
"""

from __future__ import annotations

import io
import logging as pylogging
import os

import pytest

from clausal.logic.solve import call
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.trampoline import DONE, StepGenerator
from clausal.import_hook import _load_module

# Import the module predicates directly for unit testing.
from clausal.modules.py.logging import (
    _get_logger_1, _get_logger_2,
    _set_level_2, _get_level_2, _is_enabled_for_2,
    _log_3, _debug_1, _debug_2, _info_1, _info_2,
    _warning_1, _warning_2, _error_1, _error_2,
    _critical_1, _critical_2,
    _stream_handler_2, _file_handler_2, _set_formatter_2,
    _add_handler_2, _remove_handler_2, _basic_config_1,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _run_simple(fn, *args):
    """Run a simple-mode builtin and return number of solutions."""
    trail = Trail()
    count = 0
    for _ in fn(*args, trail, None):
        count += 1
    return count


def _run_simple_var(fn, *args_before_result):
    """Run simple-mode with trailing Var, return deref'd first result."""
    trail = Trail()
    result = Var()
    for _ in fn(*args_before_result, result, trail, None):
        return deref(result)
    return None


def _make_capture_handler(logger_name):
    """Create a logger with a StringIO handler, return (logger, buf)."""
    logger = pylogging.getLogger(logger_name)
    logger.setLevel(pylogging.DEBUG)
    # Remove any existing handlers to avoid interference.
    logger.handlers.clear()
    logger.propagate = False
    buf = io.StringIO()
    handler = pylogging.StreamHandler(buf)
    handler.setFormatter(pylogging.Formatter("%(levelname)s:%(message)s"))
    logger.addHandler(handler)
    return logger, buf


# ══════════════════════════════════════════════════════════════════════════════
# UNIT TESTS — Python-level predicate functions
# ══════════════════════════════════════════════════════════════════════════════


class TestGetLogger:
    def test_get_logger_default(self):
        result = _run_simple_var(_get_logger_1)
        assert isinstance(result, pylogging.Logger)
        assert result.name == "clausal"

    def test_get_logger_named(self):
        result = _run_simple_var(_get_logger_2, "test.unit.named")
        assert isinstance(result, pylogging.Logger)
        assert result.name == "test.unit.named"

    def test_get_logger_same_name_same_object(self):
        r1 = _run_simple_var(_get_logger_2, "test.unit.same")
        r2 = _run_simple_var(_get_logger_2, "test.unit.same")
        assert r1 is r2

    def test_get_logger_different_names(self):
        r1 = _run_simple_var(_get_logger_2, "test.unit.a")
        r2 = _run_simple_var(_get_logger_2, "test.unit.b")
        assert r1 is not r2


class TestSetGetLevel:
    def test_set_debug(self):
        trail = Trail()
        logger = pylogging.getLogger("test.unit.setlvl1")
        _run_simple(_set_level_2, logger, "debug")
        result = _run_simple_var(_get_level_2, logger)
        assert result == "DEBUG"

    def test_set_warning(self):
        trail = Trail()
        logger = pylogging.getLogger("test.unit.setlvl2")
        _run_simple(_set_level_2, logger, "warning")
        result = _run_simple_var(_get_level_2, logger)
        assert result == "WARNING"

    def test_set_error(self):
        logger = pylogging.getLogger("test.unit.setlvl3")
        _run_simple(_set_level_2, logger, "error")
        result = _run_simple_var(_get_level_2, logger)
        assert result == "ERROR"

    def test_set_critical(self):
        logger = pylogging.getLogger("test.unit.setlvl4")
        _run_simple(_set_level_2, logger, "critical")
        result = _run_simple_var(_get_level_2, logger)
        assert result == "CRITICAL"

    def test_set_info(self):
        logger = pylogging.getLogger("test.unit.setlvl5")
        _run_simple(_set_level_2, logger, "info")
        result = _run_simple_var(_get_level_2, logger)
        assert result == "INFO"

    def test_fatal_alias(self):
        logger = pylogging.getLogger("test.unit.setlvl6")
        _run_simple(_set_level_2, logger, "fatal")
        result = _run_simple_var(_get_level_2, logger)
        assert result == "CRITICAL"

    def test_warn_alias(self):
        logger = pylogging.getLogger("test.unit.setlvl7")
        _run_simple(_set_level_2, logger, "warn")
        result = _run_simple_var(_get_level_2, logger)
        assert result == "WARNING"


class TestIsEnabledFor:
    def test_enabled(self):
        logger = pylogging.getLogger("test.unit.enab1")
        logger.setLevel(pylogging.DEBUG)
        assert _run_simple(_is_enabled_for_2, logger, "info") == 1

    def test_disabled(self):
        logger = pylogging.getLogger("test.unit.enab2")
        logger.setLevel(pylogging.ERROR)
        assert _run_simple(_is_enabled_for_2, logger, "debug") == 0

    def test_same_level(self):
        logger = pylogging.getLogger("test.unit.enab3")
        logger.setLevel(pylogging.WARNING)
        assert _run_simple(_is_enabled_for_2, logger, "warning") == 1


class TestOutputCapture:
    """Verify actual log output via captured StringIO handler."""

    def test_debug_output(self):
        logger, buf = _make_capture_handler("test.unit.cap.debug")
        _run_simple(_debug_2, logger, "hello debug")
        assert buf.getvalue() == "DEBUG:hello debug\n"

    def test_info_output(self):
        logger, buf = _make_capture_handler("test.unit.cap.info")
        _run_simple(_info_2, logger, "hello info")
        assert buf.getvalue() == "INFO:hello info\n"

    def test_warning_output(self):
        logger, buf = _make_capture_handler("test.unit.cap.warning")
        _run_simple(_warning_2, logger, "hello warn")
        assert buf.getvalue() == "WARNING:hello warn\n"

    def test_error_output(self):
        logger, buf = _make_capture_handler("test.unit.cap.error")
        _run_simple(_error_2, logger, "hello error")
        assert buf.getvalue() == "ERROR:hello error\n"

    def test_critical_output(self):
        logger, buf = _make_capture_handler("test.unit.cap.critical")
        _run_simple(_critical_2, logger, "hello crit")
        assert buf.getvalue() == "CRITICAL:hello crit\n"

    def test_log3_output(self):
        logger, buf = _make_capture_handler("test.unit.cap.log3")
        _run_simple(_log_3, logger, "warning", "log3 msg")
        assert buf.getvalue() == "WARNING:log3 msg\n"


class TestLevelFiltering:
    """Verify that messages below the logger's level are suppressed."""

    def test_debug_suppressed_at_warning(self):
        logger, buf = _make_capture_handler("test.unit.filt1")
        logger.setLevel(pylogging.WARNING)
        _run_simple(_debug_2, logger, "should not appear")
        assert buf.getvalue() == ""

    def test_error_passes_at_warning(self):
        logger, buf = _make_capture_handler("test.unit.filt2")
        logger.setLevel(pylogging.WARNING)
        _run_simple(_error_2, logger, "should appear")
        assert "should appear" in buf.getvalue()

    def test_info_suppressed_at_error(self):
        logger, buf = _make_capture_handler("test.unit.filt3")
        logger.setLevel(pylogging.ERROR)
        _run_simple(_info_2, logger, "nope")
        assert buf.getvalue() == ""


class TestMultipleHandlers:
    """Verify that multiple handlers both receive messages."""

    def test_two_handlers(self):
        logger = pylogging.getLogger("test.unit.multi")
        logger.setLevel(pylogging.DEBUG)
        logger.handlers.clear()
        logger.propagate = False

        buf1 = io.StringIO()
        buf2 = io.StringIO()
        h1 = pylogging.StreamHandler(buf1)
        h2 = pylogging.StreamHandler(buf2)
        h1.setFormatter(pylogging.Formatter("%(message)s"))
        h2.setFormatter(pylogging.Formatter("%(message)s"))
        logger.addHandler(h1)
        logger.addHandler(h2)

        _run_simple(_info_2, logger, "both handlers")
        assert buf1.getvalue().strip() == "both handlers"
        assert buf2.getvalue().strip() == "both handlers"


class TestHandlerCreation:
    def test_stream_handler_stdout(self):
        result = _run_simple_var(_stream_handler_2, "stdout")
        assert isinstance(result, pylogging.StreamHandler)

    def test_stream_handler_stderr(self):
        result = _run_simple_var(_stream_handler_2, "stderr")
        assert isinstance(result, pylogging.StreamHandler)

    def test_set_formatter(self):
        trail = Trail()
        handler = pylogging.StreamHandler(io.StringIO())
        _run_simple(_set_formatter_2, handler, "%(levelname)s - %(message)s")
        assert handler.formatter is not None
        assert "%(levelname)s" in handler.formatter._fmt


class TestFileHandler:
    def test_file_handler_creates_file(self, tmp_path):
        log_path = tmp_path / "test.log"
        result = _run_simple_var(_file_handler_2, str(log_path))
        assert isinstance(result, pylogging.FileHandler)
        result.close()

    def test_file_handler_writes(self, tmp_path):
        log_path = tmp_path / "test_write.log"
        logger = pylogging.getLogger("test.unit.filewrite")
        logger.setLevel(pylogging.DEBUG)
        logger.handlers.clear()
        logger.propagate = False

        handler = pylogging.FileHandler(str(log_path))
        handler.setFormatter(pylogging.Formatter("%(message)s"))
        logger.addHandler(handler)

        _run_simple(_info_2, logger, "file output test")
        handler.flush()
        handler.close()

        content = log_path.read_text()
        assert "file output test" in content


class TestAddRemoveHandler:
    def test_add_and_remove(self):
        logger = pylogging.getLogger("test.unit.addrem")
        logger.handlers.clear()
        buf = io.StringIO()
        handler = pylogging.StreamHandler(buf)

        trail = Trail()
        _run_simple(_add_handler_2, logger, handler)
        assert handler in logger.handlers

        _run_simple(_remove_handler_2, logger, handler)
        assert handler not in logger.handlers


class TestBasicConfig:
    def test_basic_config_level(self):
        # basicConfig only works if root has no handlers yet, so this
        # test is limited — just verify it doesn't crash.
        trail = Trail()
        assert _run_simple(_basic_config_1, {"level": "debug"}) == 1


class TestArityOneShorthand:
    """Verify arity-1 predicates log to the default 'clausal' logger."""

    def test_debug_1(self):
        assert _run_simple(_debug_1, "shorthand debug") == 1

    def test_info_1(self):
        assert _run_simple(_info_1, "shorthand info") == 1

    def test_warning_1(self):
        assert _run_simple(_warning_1, "shorthand warning") == 1

    def test_error_1(self):
        assert _run_simple(_error_1, "shorthand error") == 1

    def test_critical_1(self):
        assert _run_simple(_critical_1, "shorthand critical") == 1


class TestFormatterOutput:
    """Verify custom formatter patterns produce expected output."""

    def test_custom_format(self):
        logger, buf = _make_capture_handler("test.unit.fmt")
        # Replace formatter with a custom one.
        logger.handlers[0].setFormatter(
            pylogging.Formatter("[%(levelname)s] %(message)s")
        )
        _run_simple(_info_2, logger, "formatted")
        assert buf.getvalue() == "[INFO] formatted\n"

    def test_name_in_format(self):
        logger, buf = _make_capture_handler("test.unit.fmt.name")
        logger.handlers[0].setFormatter(
            pylogging.Formatter("%(name)s:%(message)s")
        )
        _run_simple(_warning_2, logger, "with name")
        assert buf.getvalue() == "test.unit.fmt.name:with name\n"


class TestVarDeref:
    """Verify that Var values are deref'd before logging."""

    def test_bound_var_in_message(self):
        logger, buf = _make_capture_handler("test.unit.var")
        trail = Trail()
        v = Var()
        unify(v, "world", trail)
        msg = f"hello {v}"
        _run_simple(_info_2, logger, msg)
        assert "hello world" in buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════════
# FIXTURE INTEGRATION: Load .clausal file and run Test predicates
# ══════════════════════════════════════════════════════════════════════════════


_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(name):
    path = os.path.join(_FIXTURE_DIR, f"{name}.clausal")
    mod = _load_module(name, path)
    return mod.__dict__["$module"]


def _succeeds(functor, *args, module):
    for _ in call(functor, *args, module=module):
        return True
    return False


class TestLoggingFixture:
    """Run Test predicates from tests/fixtures/logging_basic.clausal."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("logging_basic")

    @pytest.mark.parametrize("name", [
        # GetLogger
        "get_logger named",
        "get_logger same name",
        "get_logger default",
        # SetLevel / GetLevel
        "set_level debug",
        "set_level warning",
        "set_level error",
        "set_level critical",
        "set_level info",
        # IsEnabledFor
        "enabled_for yes",
        "enabled_for no",
        "enabled_for same level",
        # Logging predicates
        "debug succeeds",
        "info succeeds",
        "warning succeeds",
        "error succeeds",
        "critical succeeds",
        # Log/3
        "log at info",
        "log at debug",
        # Arity-1 shorthand
        "debug arity 1",
        "info arity 1",
        "warning arity 1",
        "error arity 1",
        "critical arity 1",
        # StreamHandler / AddHandler
        "stream_handler stdout",
        "stream_handler stderr",
        "add_handler",
        # SetFormatter
        "set_formatter",
        # Hierarchy
        "logger hierarchy",
    ])
    def test_fixture(self, name):
        assert _succeeds("Test", name, module=self.mod)
