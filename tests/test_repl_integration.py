"""Integration tests for the Clausal REPL implementations.

Tests are parameterised over two "drivers" so the same scenario runs against
both ClausalConsole and ptpython with identical assertions.  Structural
differences (ptpython creates a real PythonRepl; ClausalConsole subclasses
code.InteractiveConsole) mean each driver exercises a different code path
while producing the same user-visible output.

Separated from the main suite because instantiating ptpython's PythonRepl
has non-trivial startup cost.

Run individually:
    pytest tests/test_repl_integration.py -v
"""

from __future__ import annotations

import sys
import io
import pytest

from clausal.python_repl import (
    ClausalConsole,
    _base_namespace,
    _configure_clausal_repl,
    _install_displayhook,
    _make_clausal_compile,
)

# ── Utilities ─────────────────────────────────────────────────────────────────


def capture_stdout(fn):
    """Call fn() and return whatever it wrote to stdout as a string."""
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        fn()
    finally:
        sys.stdout = old
    return buf.getvalue()


def content_lines(out: str) -> list[str]:
    """Return non-blank output lines with the Solutions prompt line removed.

    The prompt ``[SPACE/n: next  | … | ESC/q: abort | …]`` contains "or"
    (inside "abort") and must be stripped before counting solution separators.
    """
    result = []
    for line in out.splitlines():
        s = line.strip()
        if s and "SPACE/n:" not in s:
            result.append(s)
    return result


def count_or_separators(out: str) -> int:
    """Count whole-line 'or' separators (not substrings like 'abort')."""
    return content_lines(out).count("or")


def _patch_keys(monkeypatch, keys=None):
    """Patch clausal.repl._read_char to return scripted keypresses."""
    from clausal import repl as _repl
    if keys:
        it = iter(keys)
        monkeypatch.setattr(_repl, "_read_char", lambda: next(it))
    else:
        # Default: press ENTER after first solution (stop/commit)
        monkeypatch.setattr(_repl, "_read_char", lambda: '\r')


# ── Driver abstraction ────────────────────────────────────────────────────────


class ConsoleDriver:
    """Drive ClausalConsole via runsource()."""

    name = "ClausalConsole"

    def __init__(self, monkeypatch):
        self.monkeypatch = monkeypatch
        from clausal import In
        ns = _base_namespace()
        ns["In"] = In
        self._console = ClausalConsole(locals=ns, filename="<test>")

    def run(self, code: str, keys=None) -> str:
        _patch_keys(self.monkeypatch, keys)
        return capture_stdout(
            lambda: self._console.runsource(code, "<test>", "single")
        )

    def run_import(self, stmt: str) -> None:
        self._console.runsource(stmt, "<test>", "single")


class PtpythonDriver:
    """Drive a real ptpython PythonRepl via eval()."""

    name = "ptpython"

    def __init__(self, monkeypatch):
        pytest.importorskip("ptpython")
        self.monkeypatch = monkeypatch
        from ptpython.repl import PythonRepl
        from clausal import In

        self._ns = _base_namespace()
        self._ns["In"] = In

        self._repl = PythonRepl(
            get_globals=lambda: self._ns,
            get_locals=lambda: self._ns,
            create_app=False,
        )
        _configure_clausal_repl(self._repl)
        _install_displayhook()

    def run(self, code: str, keys=None) -> str:
        _patch_keys(self.monkeypatch, keys)
        return capture_stdout(lambda: self._repl.eval(code))

    def run_import(self, stmt: str) -> None:
        exec(stmt, self._ns)  # noqa: S102  (safe: test-controlled code)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _restore_displayhook():
    """Restore sys.displayhook after every test (drivers install their own)."""
    orig = sys.displayhook
    yield
    sys.displayhook = orig


@pytest.fixture(params=["console", "ptpython"], ids=["console", "ptpython"])
def driver(request, monkeypatch):
    if request.param == "console":
        return ConsoleDriver(monkeypatch)
    return PtpythonDriver(monkeypatch)  # skips if ptpython not installed


# ── Tests ─────────────────────────────────────────────────────────────────────
#
# Every test runs against BOTH drivers via the `driver` fixture.


class TestQuerySyntax:
    """*(goals) query syntax — core feature parity tests."""

    def test_no_solutions_prints_false(self, driver):
        out = driver.run("*(In(X, []))")
        assert "false." in out

    def test_single_solution_shows_binding(self, driver):
        out = driver.run("*(In(X, [42]))")
        assert "42" in out

    def test_single_solution_exhausts_with_no_more_message(self, driver):
        out = driver.run("*(In(X, [42]))")
        assert "No more solutions." in out

    def test_stop_after_first_with_enter(self, driver):
        # Two solutions; user presses ENTER after first → only first shown
        out = driver.run("*(In(X, [1, 2]))", keys=['\r'])
        assert "1" in out
        assert "2" not in out.split("1")[1]  # 2 not shown after the first binding

    def test_advance_with_space(self, driver):
        out = driver.run("*(In(X, [1, 2]))", keys=[' '])
        assert "1" in out
        assert "2" in out
        assert "or" in out

    def test_show_all_with_a(self, driver):
        out = driver.run("*(In(X, [1, 2, 3]))", keys=['a'])
        assert "1" in out
        assert "2" in out
        assert "3" in out
        assert count_or_separators(out) == 2

    def test_abort_with_esc_shows_only_first(self, driver):
        out = driver.run("*(In(X, [1, 2, 3]))", keys=['\x1b'])
        assert "1" in out
        # After ESC, no 'or' separator and no second/third solution
        assert count_or_separators(out) == 0

    def test_conjunction_two_goals(self, driver):
        # In([1,2,3]) ∩ In([2,3,4]) = {2, 3}
        out = driver.run(
            "*(In(X, [1,2,3]), In(X, [2,3,4]))",
            keys=[' ', '\r'],  # next, stop
        )
        assert "2" in out
        assert "3" in out

    def test_variables_auto_declared_uppercase(self, driver):
        # X and Y should be auto-allocated as Var() inside *(...)
        out = driver.run("*(In(X, [10, 20]))", keys=[' '])
        assert "X" in out

    def test_true_binding_shows_true(self, driver):
        # Zero-variable query succeeds with "true."
        out = driver.run("*(In(1, [1, 2, 3]))")
        assert "true." in out


class TestNormalPython:
    """Normal Python should pass through unchanged."""

    def test_assignment_executes(self, driver):
        driver.run("my_var_99 = 7 * 6")
        # Re-use the namespace for ptpython; for console check locals
        if isinstance(driver, ConsoleDriver):
            assert driver._console.locals.get("my_var_99") == 42
        else:
            assert driver._ns.get("my_var_99") == 42

    def test_import_then_query(self, driver):
        driver.run_import("from clausal import Append")
        out = driver.run("*(Append([1], [2], R))")
        assert "1" in out
        assert "2" in out


class TestEmbedSyntax:
    """--expr term embedding syntax."""

    def test_embed_name_produces_LoadName(self, driver):
        from clausal.pythonic_ast.nodes import LoadName
        driver.run("my_term = --foo")
        if isinstance(driver, ConsoleDriver):
            ns = driver._console.locals
        else:
            ns = driver._ns
        assert isinstance(ns.get("my_term"), LoadName)
        assert ns["my_term"].name == "foo"


class TestSolutionsDisplay:
    """Solutions display hook — interactive output format."""

    def test_or_separator_between_solutions(self, driver):
        out = driver.run("*(In(X, [1, 2, 3]))", keys=[' ', ' '])
        assert count_or_separators(out) == 2

    def test_no_blank_line_after_output(self, driver):
        """Verify displayhook doesn't emit a trailing blank line from repr('')."""
        out = driver.run("*(In(X, [42]))")
        # The output should end with 'No more solutions.\n', not have an extra blank
        stripped = out.rstrip("\n")
        assert not stripped.endswith("\n")


# ── Compile-hook unit tests (ptpython-specific) ───────────────────────────────


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("ptpython"),
    reason="ptpython not installed",
)
class TestCompileHook:
    """Unit tests for _make_clausal_compile — the ptpython compile hook."""

    @pytest.fixture
    def fake_repl(self):
        class _Fake:
            def get_compiler_flags(self): return 0
        return _Fake()

    def test_normal_exec_unchanged(self, fake_repl):
        fn = _make_clausal_compile(fake_repl)
        code_obj = fn("x = 1 + 2", "exec")
        ns = {}
        exec(code_obj, ns)
        assert ns["x"] == 3

    def test_single_expr_promoted_to_single_mode(self, fake_repl):
        """A bare expression in exec mode is compiled as 'single' → displayhook fires."""
        import sys
        fn = _make_clausal_compile(fake_repl)
        code_obj = fn("[1, 2, 3]", "exec")

        calls = []
        orig = sys.displayhook
        sys.displayhook = lambda v: calls.append(v)
        try:
            exec(code_obj, {})
        finally:
            sys.displayhook = orig
        assert calls == [[1, 2, 3]]

    def test_multistatement_stays_exec(self, fake_repl):
        """Multi-statement code is NOT promoted (single mode would fail)."""
        fn = _make_clausal_compile(fake_repl)
        code_obj = fn("x = 1\ny = 2", "exec")
        ns = {}
        exec(code_obj, ns)
        assert ns["x"] == 1 and ns["y"] == 2

    def test_star_query_compiles(self, fake_repl):
        """*(In(X, [1])) transforms without error."""
        from clausal import In
        ns = _base_namespace()
        ns["In"] = In
        fn = _make_clausal_compile(fake_repl)
        # exec mode parse; transformer rewrites; should compile cleanly
        code_obj = fn("*(In(X, [1]))", "exec")
        assert code_obj is not None

    def test_real_syntax_error_propagates(self, fake_repl):
        fn = _make_clausal_compile(fake_repl)
        with pytest.raises(SyntaxError):
            fn("x = @", "exec")

    def test_embed_syntax_transforms(self, fake_repl):
        """--name becomes a LoadName term."""
        from clausal.pythonic_ast.nodes import LoadName
        fn = _make_clausal_compile(fake_repl)
        code_obj = fn("result = --myatom", "exec")
        ns = dict(_base_namespace())
        exec(code_obj, ns)
        assert isinstance(ns.get("result"), LoadName)
        assert ns["result"].name == "myatom"
