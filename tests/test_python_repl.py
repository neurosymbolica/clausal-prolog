"""Tests for clausal.python_repl — Python REPL integrations (ClausalConsole + ptpython)."""

import ast
import sys
import io
import pytest
from clausal.python_repl import (
    ClausalConsole,
    enable_python_repl,
    _base_namespace,
    _make_clausal_compile,
    _configure_clausal_repl,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def run_source(source, console=None):
    """Run source through ClausalConsole and capture stdout+stderr."""
    if console is None:
        console = ClausalConsole(filename="<test>")
    buf = io.StringIO()
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = buf
    try:
        console.runsource(source, filename="<test>", symbol="single")
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
    return buf.getvalue()


# ── _base_namespace ───────────────────────────────────────────────────────────


def test_base_namespace_has_var():
    # nv
    assert "Var" in _base_namespace()


def test_base_namespace_has_solutions():
    # nv
    assert "Solutions" in _base_namespace()


def test_base_namespace_has_set_style():
    # nv
    assert "set_style" in _base_namespace()


def test_base_namespace_has_compound():
    # nv
    assert "Compound" in _base_namespace()


# ── ClausalConsole — completeness detection ───────────────────────────────────


def test_incomplete_returns_true():
    # nv
    console = ClausalConsole(filename="<test>")
    assert console.runsource("def foo(", "<test>", "single") is True


def test_complete_returns_false():
    # nv
    console = ClausalConsole(filename="<test>")
    assert console.runsource("x = 1", "<test>", "single") is False


def test_syntax_error_returns_false():
    # nv
    console = ClausalConsole(filename="<test>")
    buf = io.StringIO()
    old = sys.stderr
    sys.stderr = buf
    try:
        result = console.runsource("x = @", "<test>", "single")
    finally:
        sys.stderr = old
    assert result is False


# ── ClausalConsole — name injection ──────────────────────────────────────────


def test_var_in_scope():
    # nv
    assert "Var" in ClausalConsole(filename="<test>").locals


def test_solutions_in_scope():
    # nv
    assert "Solutions" in ClausalConsole(filename="<test>").locals


def test_trail_in_scope():
    # nv
    assert "Trail" in ClausalConsole(filename="<test>").locals


# ── ClausalConsole — normal Python ───────────────────────────────────────────


def test_normal_assignment_executes():
    # nv
    console = ClausalConsole(filename="<test>")
    console.runsource("x = 42", "<test>", "single")
    assert console.locals.get("x") == 42


def test_normal_expression_executes():
    # nv
    assert "3" in run_source("1 + 2")


# ── ClausalConsole — EmbedTransformer (--expr syntax) ────────────────────────


def test_embed_double_minus_produces_term():
    # nv
    console = ClausalConsole(filename="<test>")
    console.runsource("result = --foo", "<test>", "single")
    # THE SEAM: ``--foo`` is the atom cell, a runtime term, not a node.
    assert console.locals.get("result") == "foo"


# ── ClausalConsole — *(goals) query syntax ───────────────────────────────────


def _make_console_with_In():
    """Console with the in_ builtin imported (as a user would do)."""
    from clausal import in_
    console = ClausalConsole(filename="<test>")
    console.locals["in_"] = in_
    return console


def test_star_query_no_solutions(monkeypatch):
    # nv
    console = _make_console_with_In()
    buf = io.StringIO()
    sys.stdout = buf
    from clausal import repl as _repl
    monkeypatch.setattr(_repl, "_read_char", lambda: '\r')
    try:
        console.runsource("*(in_(X, []))", "<test>", "single")
    finally:
        sys.stdout = sys.__stdout__
    assert "false." in buf.getvalue()


def test_star_query_single_solution(monkeypatch):
    # nv
    console = _make_console_with_In()
    buf = io.StringIO()
    sys.stdout = buf
    from clausal import repl as _repl
    monkeypatch.setattr(_repl, "_read_char", lambda: '\r')
    try:
        console.runsource("*(in_(X, [42]))", "<test>", "single")
    finally:
        sys.stdout = sys.__stdout__
    assert "42" in buf.getvalue()


def test_star_query_conjunction(monkeypatch):
    # nv
    console = _make_console_with_In()
    buf = io.StringIO()
    sys.stdout = buf
    keys = iter([' ', ' ', '\r'])
    from clausal import repl as _repl
    monkeypatch.setattr(_repl, "_read_char", lambda: next(keys))
    try:
        console.runsource("*(in_(X, [1,2,3]), in_(X, [2,3,4]))", "<test>", "single")
    finally:
        sys.stdout = sys.__stdout__
    out = buf.getvalue()
    assert "2" in out
    assert "3" in out


def test_star_query_import_then_use(monkeypatch):
    """Typical usage: import then query."""
    # nv
    console = ClausalConsole(filename="<test>")
    console.runsource("from clausal import in_", "<test>", "single")
    buf = io.StringIO()
    sys.stdout = buf
    from clausal import repl as _repl
    monkeypatch.setattr(_repl, "_read_char", lambda: '\r')
    try:
        console.runsource("*(in_(X, [1, 2, 3]))", "<test>", "single")
    finally:
        sys.stdout = sys.__stdout__
    assert "1" in buf.getvalue()


def test_goal_seam_in_the_repl_says_it_is_unavailable_and_names_the_alternative():
    """The REPL has no host Clausal module, so ``for F in --g:`` cannot run.
    The refusal used to blame "a plain .py file", which is not what the user
    typed; it now says the goal seam is not available here and names the
    query forms that are (``solve(cell, module=m)``, the REPL's ``*(...)``)."""
    # nv
    console = ClausalConsole(filename="<test>")
    out = run_source("for X in --in_(X, [1, 2]): print(X)\n", console)
    assert "NameError" in out, out
    assert "not available in the REPL" in out, out
    assert "module=m" in out and "*(pred(X))" in out, out
    assert "plain .py" not in out, out


# ── enable_python_repl ────────────────────────────────────────────────────────


def test_enable_injects_var():
    # nv
    ns = {}
    enable_python_repl(ns)
    assert "Var" in ns


def test_enable_injects_solutions():
    # nv
    ns = {}
    enable_python_repl(ns)
    assert "Solutions" in ns


def test_enable_injects_set_style():
    # nv
    ns = {}
    enable_python_repl(ns)
    assert "set_style" in ns


def test_enable_installs_displayhook():
    # nv
    import builtins
    from clausal.repl import Solutions
    ns = {}
    enable_python_repl(ns)
    buf = io.StringIO()
    sys.stdout = buf
    try:
        sys.displayhook(Solutions(iter([{"X": 99}])))
    finally:
        sys.stdout = sys.__stdout__
    assert "99" in buf.getvalue()


# ── ptpython integration ──────────────────────────────────────────────────────


pytestmark_ptpython = pytest.mark.skipif(
    not __import__("importlib").util.find_spec("ptpython"),
    reason="ptpython not installed",
)


class _FakeRepl:
    """Minimal stand-in for ptpython PythonRepl for unit tests."""

    def __init__(self):
        self._ns: dict = {}
        self.show_signature = False
        self.show_docstring = True
        self.enable_fuzzy_completion = False
        self.highlight_matching_parenthesis = False
        self._compile_with_flags = None  # will be replaced by configure

    def get_globals(self):
        return self._ns

    def get_locals(self):
        return self._ns

    def get_compiler_flags(self):
        return 0


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("ptpython"),
    reason="ptpython not installed",
)
class TestPtpythonIntegration:

    def test_configure_installs_compile_hook(self):
        # nv
        repl = _FakeRepl()
        _configure_clausal_repl(repl)
        assert repl._compile_with_flags is not None

    def test_configure_injects_var(self):
        # nv
        repl = _FakeRepl()
        _configure_clausal_repl(repl)
        assert "Var" in repl.get_globals()

    def test_configure_injects_solutions(self):
        # nv
        repl = _FakeRepl()
        _configure_clausal_repl(repl)
        assert "Solutions" in repl.get_globals()

    def test_configure_enables_fuzzy_completion(self):
        # nv
        repl = _FakeRepl()
        _configure_clausal_repl(repl)
        assert repl.enable_fuzzy_completion is True

    def test_configure_enables_signature(self):
        # nv
        repl = _FakeRepl()
        _configure_clausal_repl(repl)
        assert repl.show_signature is True

    def test_compile_hook_normal_python(self):
        """Normal Python compiles unchanged."""
        # nv
        repl = _FakeRepl()
        fn = _make_clausal_compile(repl)
        code_obj = fn("x = 1 + 2", "exec")
        ns = {}
        exec(code_obj, ns)
        assert ns["x"] == 3

    def test_compile_hook_star_query_transforms(self):
        """*(goals) is rewritten to Solutions(...)."""
        # nv
        from clausal import in_
        repl = _FakeRepl()
        repl._ns["in_"] = in_
        repl._ns["Solutions"] = __import__("clausal").Solutions
        repl._ns["_run_ipython_goal"] = __import__(
            "clausal.repl", fromlist=["_run_ipython_goal"]
        )._run_ipython_goal
        repl._ns["And"] = __import__(
            "clausal.pythonic_ast.nodes", fromlist=["And"]
        ).And
        repl._ns["Var"] = __import__("clausal").Var
        fn = _make_clausal_compile(repl)
        # *(in_(X, [1])) should compile without error
        code_obj = fn("*(in_(X, [1]))", "exec")
        assert code_obj is not None

    def test_compile_hook_embed_syntax(self):
        """--name produces a LoadName term."""
        # nv
        repl = _FakeRepl()
        fn = _make_clausal_compile(repl)
        code_obj = fn("result = --foo", "exec")
        ns = dict(_base_namespace())
        exec(code_obj, ns)
        from clausal.pythonic_ast.nodes import LoadName
        assert isinstance(ns.get("result"), LoadName)
        assert ns["result"].name == "foo"

    def test_compile_hook_syntax_error_propagates(self):
        """Real syntax errors propagate so ptpython can handle them."""
        # nv
        repl = _FakeRepl()
        fn = _make_clausal_compile(repl)
        with pytest.raises(SyntaxError):
            fn("x = @", "exec")
