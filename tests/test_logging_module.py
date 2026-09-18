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
from clausal.logic.cells import chars

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
        # nv
        result = _run_simple_var(_get_logger_1)
        assert isinstance(result, pylogging.Logger)
        assert result.name == "clausal"

    def test_get_logger_named(self):
        # nv
        result = _run_simple_var(_get_logger_2, chars("test.unit.named"))
        assert isinstance(result, pylogging.Logger)
        assert result.name == "test.unit.named"

    def test_get_logger_same_name_same_object(self):
        # nv
        r1 = _run_simple_var(_get_logger_2, chars("test.unit.same"))
        r2 = _run_simple_var(_get_logger_2, chars("test.unit.same"))
        assert r1 is r2

    def test_get_logger_different_names(self):
        # nv
        r1 = _run_simple_var(_get_logger_2, chars("test.unit.a"))
        r2 = _run_simple_var(_get_logger_2, chars("test.unit.b"))
        assert r1 is not r2


class TestSetGetLevel:
    def test_set_debug(self):
        # nv
        trail = Trail()
        logger = pylogging.getLogger("test.unit.setlvl1")
        _run_simple(_set_level_2, logger, chars("debug"))
        result = _run_simple_var(_get_level_2, logger)
        assert result == chars("DEBUG")

    def test_set_warning(self):
        # nv
        trail = Trail()
        logger = pylogging.getLogger("test.unit.setlvl2")
        _run_simple(_set_level_2, logger, chars("warning"))
        result = _run_simple_var(_get_level_2, logger)
        assert result == chars("WARNING")

    def test_set_error(self):
        # nv
        logger = pylogging.getLogger("test.unit.setlvl3")
        _run_simple(_set_level_2, logger, chars("error"))
        result = _run_simple_var(_get_level_2, logger)
        assert result == chars("ERROR")

    def test_set_critical(self):
        # nv
        logger = pylogging.getLogger("test.unit.setlvl4")
        _run_simple(_set_level_2, logger, chars("critical"))
        result = _run_simple_var(_get_level_2, logger)
        assert result == chars("CRITICAL")

    def test_set_info(self):
        # nv
        logger = pylogging.getLogger("test.unit.setlvl5")
        _run_simple(_set_level_2, logger, chars("info"))
        result = _run_simple_var(_get_level_2, logger)
        assert result == chars("INFO")

    def test_fatal_alias(self):
        # nv
        logger = pylogging.getLogger("test.unit.setlvl6")
        _run_simple(_set_level_2, logger, chars("fatal"))
        result = _run_simple_var(_get_level_2, logger)
        assert result == chars("CRITICAL")

    def test_warn_alias(self):
        # nv
        logger = pylogging.getLogger("test.unit.setlvl7")
        _run_simple(_set_level_2, logger, chars("warn"))
        result = _run_simple_var(_get_level_2, logger)
        assert result == chars("WARNING")


class TestIsEnabledFor:
    def test_enabled(self):
        # nv
        logger = pylogging.getLogger("test.unit.enab1")
        logger.setLevel(pylogging.DEBUG)
        assert _run_simple(_is_enabled_for_2, logger, chars("info")) == 1

    def test_disabled(self):
        # nv
        logger = pylogging.getLogger("test.unit.enab2")
        logger.setLevel(pylogging.ERROR)
        assert _run_simple(_is_enabled_for_2, logger, chars("debug")) == 0

    def test_same_level(self):
        # nv
        logger = pylogging.getLogger("test.unit.enab3")
        logger.setLevel(pylogging.WARNING)
        assert _run_simple(_is_enabled_for_2, logger, chars("warning")) == 1


class TestOutputCapture:
    """Verify actual log output via captured StringIO handler."""

    def test_debug_output(self):
        # nv
        logger, buf = _make_capture_handler("test.unit.cap.debug")
        _run_simple(_debug_2, logger, chars("hello debug"))
        assert buf.getvalue() == "DEBUG:hello debug\n"

    def test_info_output(self):
        # nv
        logger, buf = _make_capture_handler("test.unit.cap.info")
        _run_simple(_info_2, logger, chars("hello info"))
        assert buf.getvalue() == "INFO:hello info\n"

    def test_warning_output(self):
        # nv
        logger, buf = _make_capture_handler("test.unit.cap.warning")
        _run_simple(_warning_2, logger, chars("hello warn"))
        assert buf.getvalue() == "WARNING:hello warn\n"

    def test_error_output(self):
        # nv
        logger, buf = _make_capture_handler("test.unit.cap.error")
        _run_simple(_error_2, logger, chars("hello error"))
        assert buf.getvalue() == "ERROR:hello error\n"

    def test_critical_output(self):
        # nv
        logger, buf = _make_capture_handler("test.unit.cap.critical")
        _run_simple(_critical_2, logger, chars("hello crit"))
        assert buf.getvalue() == "CRITICAL:hello crit\n"

    def test_log3_output(self):
        # nv
        logger, buf = _make_capture_handler("test.unit.cap.log3")
        _run_simple(_log_3, logger, chars("warning"), chars("log3 msg"))
        assert buf.getvalue() == "WARNING:log3 msg\n"

    def test_compound_message_is_written_by_the_engine_writer(self):
        """A message that is not text logs as the TERM, and does not raise.

        THE FLIP (spec §9.4): ``to_text`` answers ``None`` for a cell of
        arity >= 1 rather than raising, precisely so ``_message_text``'s
        documented fallback — the engine's own unquoted writer — is
        reachable.  A Python ``repr`` here would print ``('foo', 1)``.
        """
        # nv
        from clausal.terms import Compound

        logger, buf = _make_capture_handler("test.unit.cap.compound")
        _run_simple(_info_2, logger, Compound("foo", (1,)))
        assert buf.getvalue() == "INFO:foo(1)\n"

    def test_atom_message_logs_its_spelling(self):
        # nv — an ATOM is text (spec §9.4): its spelling, not its repr.
        from clausal.logic.atoms import mint

        logger, buf = _make_capture_handler("test.unit.cap.atommsg")
        _run_simple(_info_2, logger, mint("hello atom"))
        assert buf.getvalue() == "INFO:hello atom\n"


class TestLevelFiltering:
    """Verify that messages below the logger's level are suppressed."""

    def test_debug_suppressed_at_warning(self):
        # nv
        logger, buf = _make_capture_handler("test.unit.filt1")
        logger.setLevel(pylogging.WARNING)
        _run_simple(_debug_2, logger, chars("should not appear"))
        assert buf.getvalue() == ""

    def test_error_passes_at_warning(self):
        # nv
        logger, buf = _make_capture_handler("test.unit.filt2")
        logger.setLevel(pylogging.WARNING)
        _run_simple(_error_2, logger, chars("should appear"))
        assert "should appear" in buf.getvalue()

    def test_info_suppressed_at_error(self):
        # nv
        logger, buf = _make_capture_handler("test.unit.filt3")
        logger.setLevel(pylogging.ERROR)
        _run_simple(_info_2, logger, chars("nope"))
        assert buf.getvalue() == ""


class TestMultipleHandlers:
    """Verify that multiple handlers both receive messages."""

    def test_two_handlers(self):
        # nv
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

        _run_simple(_info_2, logger, chars("both handlers"))
        assert buf1.getvalue().strip() == "both handlers"
        assert buf2.getvalue().strip() == "both handlers"


class TestHandlerCreation:
    def test_stream_handler_stdout(self):
        # nv
        result = _run_simple_var(_stream_handler_2, chars("stdout"))
        assert isinstance(result, pylogging.StreamHandler)

    def test_stream_handler_stderr(self):
        # nv
        result = _run_simple_var(_stream_handler_2, chars("stderr"))
        assert isinstance(result, pylogging.StreamHandler)

    def test_set_formatter(self):
        # nv
        trail = Trail()
        handler = pylogging.StreamHandler(io.StringIO())
        _run_simple(_set_formatter_2, handler, chars("%(levelname)s - %(message)s"))
        assert handler.formatter is not None
        assert "%(levelname)s" in handler.formatter._fmt


class TestFileHandler:
    def test_file_handler_creates_file(self, tmp_path):
        # nv
        log_path = tmp_path / "test.log"
        result = _run_simple_var(_file_handler_2, chars(str(log_path)))
        assert isinstance(result, pylogging.FileHandler)
        result.close()

    def test_file_handler_writes(self, tmp_path):
        # nv
        log_path = tmp_path / "test_write.log"
        logger = pylogging.getLogger("test.unit.filewrite")
        logger.setLevel(pylogging.DEBUG)
        logger.handlers.clear()
        logger.propagate = False

        handler = pylogging.FileHandler(str(log_path))
        handler.setFormatter(pylogging.Formatter("%(message)s"))
        logger.addHandler(handler)

        _run_simple(_info_2, logger, chars("file output test"))
        handler.flush()
        handler.close()

        content = log_path.read_text()
        assert "file output test" in content


class TestAddRemoveHandler:
    def test_add_and_remove(self):
        # nv
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
        from clausal.logic.atoms import mint

        # basicConfig only works if root has no handlers yet, so this
        # test is limited — just verify it doesn't crash.
        # nv
        trail = Trail()
        assert _run_simple(_basic_config_1, {mint("level"): chars("debug")}) == 1


class TestArityOneShorthand:
    """Verify arity-1 predicates log to the default 'clausal' logger."""

    def test_debug_1(self):
        # nv
        assert _run_simple(_debug_1, chars("shorthand debug")) == 1

    def test_info_1(self):
        # nv
        assert _run_simple(_info_1, chars("shorthand info")) == 1

    def test_warning_1(self):
        # nv
        assert _run_simple(_warning_1, chars("shorthand warning")) == 1

    def test_error_1(self):
        # nv
        assert _run_simple(_error_1, chars("shorthand error")) == 1

    def test_critical_1(self):
        # nv
        assert _run_simple(_critical_1, chars("shorthand critical")) == 1


class TestFormatterOutput:
    """Verify custom formatter patterns produce expected output."""

    def test_custom_format(self):
        # nv
        logger, buf = _make_capture_handler("test.unit.fmt")
        # Replace formatter with a custom one.
        logger.handlers[0].setFormatter(
            pylogging.Formatter("[%(levelname)s] %(message)s")
        )
        _run_simple(_info_2, logger, chars("formatted"))
        assert buf.getvalue() == "[INFO] formatted\n"

    def test_name_in_format(self):
        # nv
        logger, buf = _make_capture_handler("test.unit.fmt.name")
        logger.handlers[0].setFormatter(
            pylogging.Formatter("%(name)s:%(message)s")
        )
        _run_simple(_warning_2, logger, chars("with name"))
        assert buf.getvalue() == "test.unit.fmt.name:with name\n"


class TestVarDeref:
    """Verify that Var values are deref'd before logging."""

    def test_bound_var_in_message(self):
        # nv
        logger, buf = _make_capture_handler("test.unit.var")
        trail = Trail()
        v = Var()
        unify(v, "world", trail)
        msg = f"hello {v}"
        _run_simple(_info_2, logger, chars(msg))
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
        # get_logger
        "get_logger named",
        "get_logger same name",
        "get_logger default",
        # set_level / get_level
        "set_level debug",
        "set_level warning",
        "set_level error",
        "set_level critical",
        "set_level info",
        # is_enabled_for
        "enabled_for yes",
        "enabled_for no",
        "enabled_for same level",
        # Logging predicates
        "debug succeeds",
        "info succeeds",
        "warning succeeds",
        "error succeeds",
        "critical succeeds",
        # log/3
        "log at info",
        "log at debug",
        # Arity-1 shorthand
        "debug arity 1",
        "info arity 1",
        "warning arity 1",
        "error arity 1",
        "critical arity 1",
        # stream_handler / add_handler
        "stream_handler stdout",
        "stream_handler stderr",
        "add_handler",
        # set_formatter
        "set_formatter",
        # Hierarchy
        "logger hierarchy",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", chars(name), module=self.mod)
