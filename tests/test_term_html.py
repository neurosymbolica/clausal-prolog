"""Tests for HTML term formatting in clausal.terms."""

import pytest
from clausal.terms import term_html, term_pformat_html, JUPYTER_CSS
from clausal.logic.variables import Var


# ── term_html ────────────────────────────────────────────────────────────────

def test_term_html_int():
    # nv
    result = term_html(42)
    assert 'class="clausal-number"' in result
    assert "42" in result


def test_term_html_float():
    # nv
    result = term_html(3.14)
    assert 'class="clausal-number"' in result
    assert "3.14" in result


def test_term_html_str():
    # nv
    result = term_html("hello")
    assert 'class="clausal-string"' in result
    assert "hello" in result


def test_term_html_var():
    # nv
    result = term_html(Var())
    assert 'class="clausal-var"' in result
    assert "_" in result


def test_term_html_list():
    # nv
    result = term_html([1, 2])
    assert 'class="clausal-bracket-0"' in result
    assert 'class="clausal-number"' in result
    assert "1" in result
    assert "2" in result


def test_term_html_nested_list():
    # nv
    result = term_html([[1]])
    assert "clausal-bracket-0" in result
    assert "clausal-bracket-1" in result


def test_term_html_empty_list():
    # nv
    result = term_html([])
    assert "[]" in result or ("]" in result and "[" in result)


def test_term_html_bool():
    # nv
    assert term_html(True) == "True"
    assert term_html(False) == "False"


def test_term_html_none():
    # nv
    assert term_html(None) == "None"


def test_term_html_special_chars():
    """HTML-special characters in strings are escaped."""
    # nv
    result = term_html("<script>alert(1)</script>")
    assert "<script>" not in result
    assert "&lt;script&gt;" in result


def test_term_html_ampersand_in_string():
    # nv
    result = term_html("a&b")
    assert "&amp;" in result


# ── Compound terms ───────────────────────────────────────────────────────────

def test_term_html_compound():
    # nv
    from clausal.terms import Compound
    result = term_html(Compound("foo", (1, 2)))
    assert 'class="clausal-atom"' in result
    assert "foo" in result
    assert "1" in result
    assert "2" in result


# ── term_pformat_html ────────────────────────────────────────────────────────

def test_term_pformat_html_short():
    """Short terms are returned flat (no <pre> wrapping)."""
    # nv
    result = term_pformat_html(42)
    assert "<pre>" not in result
    assert "42" in result


def test_term_pformat_html_long():
    """Long terms get <pre> wrapping."""
    # nv
    long_list = list(range(50))
    result = term_pformat_html(long_list, width=20)
    assert "<pre>" in result


# ── JUPYTER_CSS ──────────────────────────────────────────────────────────────

def test_jupyter_css_has_required_classes():
    # nv
    for cls in ['clausal-number', 'clausal-string', 'clausal-atom',
                'clausal-var', 'clausal-bracket-0', 'clausal-or',
                'clausal-footer']:
        assert cls in JUPYTER_CSS


def test_jupyter_css_has_style_tag():
    # nv
    assert "<style>" in JUPYTER_CSS
    assert "</style>" in JUPYTER_CSS
