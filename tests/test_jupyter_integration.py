"""Tests for Jupyter notebook HTML rendering of Solutions."""

import pytest
from unittest.mock import patch, MagicMock
from clausal.repl import Solutions, _format_bindings_html, _in_jupyter_kernel


# ── Detection ────────────────────────────────────────────────────────────────

def test_in_jupyter_kernel_false_in_test_env():
    """Returns False in a normal test environment (no IPython shell)."""
    assert _in_jupyter_kernel() is False


def test_in_jupyter_kernel_false_when_import_fails():
    """Returns False when IPython is not importable."""
    with patch.dict('sys.modules', {'IPython': None}):
        # Force re-import to fail
        result = _in_jupyter_kernel()
        # Should not raise, should return False
        assert result is False


# ── _format_bindings_html ────────────────────────────────────────────────────

def test_format_bindings_html_empty():
    result = _format_bindings_html({})
    assert "true." in result
    assert "clausal-atom" in result


def test_format_bindings_html_single():
    result = _format_bindings_html({"X": 1})
    assert "X" in result
    assert "clausal-var" in result
    assert "1" in result


def test_format_bindings_html_multiple():
    result = _format_bindings_html({"X": 1, "Y": 2})
    assert "X" in result
    assert "Y" in result
    assert "1" in result
    assert "2" in result


def test_format_bindings_html_escapes_key():
    result = _format_bindings_html({"<VAR>": 1})
    assert "<VAR>" not in result
    assert "&lt;VAR&gt;" in result


# ── _repr_html_() ────────────────────────────────────────────────────────────

def test_repr_html_no_solutions():
    html = Solutions(iter([]))._repr_html_()
    assert "false." in html
    assert "<style>" in html


def test_repr_html_single_solution():
    html = Solutions(iter([{"X": 42}]))._repr_html_()
    assert "X" in html
    assert "42" in html
    assert "No more solutions." in html


def test_repr_html_multiple_solutions():
    html = Solutions(iter([{"X": 1}, {"X": 2}, {"X": 3}]))._repr_html_()
    assert "1" in html
    assert "2" in html
    assert "3" in html
    assert "clausal-or" in html
    assert "No more solutions." in html


def test_repr_html_or_separator():
    html = Solutions(iter([{"X": 1}, {"X": 2}]))._repr_html_()
    assert ">or<" in html


def test_repr_html_limit_default():
    """Default limit of 20 is applied."""
    items = [{"X": i} for i in range(30)]
    html = Solutions(iter(items))._repr_html_()
    assert "showing first 20" in html
    # Value 29 should not appear
    assert ">29<" not in html


def test_repr_html_limit_custom():
    items = [{"X": i} for i in range(10)]
    html = Solutions(iter(items), limit=5)._repr_html_()
    assert "showing first 5" in html


def test_repr_html_limit_not_hit():
    """When all solutions fit within limit, show 'No more solutions.'."""
    items = [{"X": i} for i in range(3)]
    html = Solutions(iter(items))._repr_html_()
    assert "No more solutions." in html
    assert "showing first" not in html


def test_repr_html_true_for_ground_query():
    """Empty bindings dict means ground query succeeded."""
    html = Solutions(iter([{}]))._repr_html_()
    assert "true." in html


def test_repr_html_html_escaping():
    """HTML special characters in values are escaped."""
    html = Solutions(iter([{"X": "<script>alert(1)</script>"}]))._repr_html_()
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_repr_html_contains_css():
    html = Solutions(iter([{"X": 1}]))._repr_html_()
    assert "<style>" in html
    assert "clausal-output" in html
    assert "clausal-number" in html


# ── _ipython_display_ routing ───────────────────────────────────────────────

def test_ipython_display_calls_run_in_terminal():
    """In non-Jupyter environment, _ipython_display_ calls _run()."""
    s = Solutions(iter([{"X": 1}]))
    called = []
    s._run = lambda: called.append(True)
    with patch('clausal.repl._in_jupyter_kernel', return_value=False):
        s._ipython_display_()
    assert called == [True]


def test_ipython_display_uses_html_in_jupyter():
    """In Jupyter environment, _ipython_display_ uses HTML display."""
    s = Solutions(iter([{"X": 1}]))
    displayed = []

    mock_ipython_display = MagicMock()
    mock_ipython_display.display = lambda x: displayed.append(x)
    mock_ipython_display.HTML = lambda x: x

    with patch('clausal.repl._in_jupyter_kernel', return_value=True):
        with patch.dict('sys.modules', {'IPython.display': mock_ipython_display}):
            s._ipython_display_()
    assert len(displayed) == 1
    assert "<style>" in displayed[0]
