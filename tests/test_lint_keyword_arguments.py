"""Keyword-argument lint: a TERM is built positionally.

``point(x=1, y=2)`` is Python's keyword-call syntax borrowed as a term
spelling.  It has no ISO Prolog reading, it is the only way a predicate
could declare parameter NAMES (so it made the field names of a functor
depend on which clause came first), and it was the last surface producer of
a keyword-term class -- a third term representation beside the cell and the
class instance.  The spelling is REFUSED as of 2026-09-19; the class and the
machinery that existed only for it (including ``extend/3``) are deleted.

Two spellings keep their keywords, and both are tested here:

* a ``-directive``'s OPTIONS (``-specialize(solve, p, alias=q)``) -- those are
  options of the directive, not arguments of a term;
* an EDCG hidden argument (``p(L, _edcg_counter_in=0)``) -- ``_``-led by
  construction, addressing a GENERATED argument rather than declaring a
  field name.
"""
import pathlib
import textwrap
import warnings

import pytest

from clausal.import_hook import _load_module
from clausal.templating import term_rewriting
from clausal.templating.term_rewriting import ClausalKeywordArgumentWarning
from tests._suffix import SEAM


#: The severity the engine ships with; pinned by ``test_default_severity``.
_SHIPPED_SEVERITY = term_rewriting.KEYWORD_ARGUMENT_SEVERITY


def _load(tmp_path, name, text):
    path = tmp_path / f"{name}{SEAM}"
    path.write_text(textwrap.dedent(text).lstrip())
    return _load_module(f"kwl_{name}", str(path))


def _warns(tmp_path, name, text, monkeypatch):
    monkeypatch.setattr(term_rewriting, "KEYWORD_ARGUMENT_SEVERITY", "warn")
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        _load(tmp_path, name, text)
    return [w for w in rec
            if issubclass(w.category, ClausalKeywordArgumentWarning)]


# ── refused ─────────────────────────────────────────────────────────────────

def test_default_severity_is_error():
    assert _SHIPPED_SEVERITY == "error"


def test_a_keyword_clause_head_is_refused(tmp_path):
    with pytest.raises(SyntaxError, match="keyword"):
        _load(tmp_path, "head", """
            fib(N=0, F=0),
            fib(1, 1),
        """)


def test_a_keyword_term_in_a_body_is_refused(tmp_path):
    with pytest.raises(SyntaxError, match="keyword"):
        _load(tmp_path, "term", """
            -private([vec(X, Y)])
            p(P) <- (P is vec(x=1, y=2))
        """)


def test_a_keyword_goal_is_refused(tmp_path):
    with pytest.raises(SyntaxError, match="keyword"):
        _load(tmp_path, "goal", """
            q(1, 2),
            p <- q(a=1, b=2)
        """)


def test_the_message_names_the_field_and_the_positional_remedy(tmp_path, monkeypatch):
    ws = _warns(tmp_path, "msg", """
        fib(N=0, F=0),
    """, monkeypatch)
    assert len(ws) == 1
    msg = str(ws[0].message)
    assert "fib" in msg and "N" in msg and "positional" in msg


def test_one_report_per_site_not_per_keyword(tmp_path, monkeypatch):
    ws = _warns(tmp_path, "persite", """
        fib(N=0, F=0),
        gib(A=1, B=2, C=3),
    """, monkeypatch)
    assert len(ws) == 2


# ── accepted ────────────────────────────────────────────────────────────────

def test_a_directive_option_keyword_is_accepted(monkeypatch):
    """``-specialize(solve_count, natnum_program, alias=solve_count_natnum)``
    still loads: the directive call site hands the lint the directive's args
    and its keyword VALUES, never the directive ``Call`` itself."""
    monkeypatch.setattr(term_rewriting, "KEYWORD_ARGUMENT_SEVERITY", "warn")
    fixture = str(pathlib.Path(__file__).parent / "fixtures"
                  / "specialize_natnum.clausal")
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        _load_module("kwl_specialize_natnum", fixture)
    assert [w for w in rec
            if issubclass(w.category, ClausalKeywordArgumentWarning)] == []


def test_an_edcg_hidden_argument_keyword_is_accepted(tmp_path, monkeypatch):
    assert _warns(tmp_path, "edcg", """
        -edcg_acc(counter, _x, _in, _out, {_out == _in + _x})
        -edcg_pred(bump, 0, [counter])

        bump >> ([1] // counter)

        run(COUNT) <- bump(_edcg_counter_in=0, _edcg_counter_out=COUNT)
    """, monkeypatch) == []


def test_a_python_escape_keyword_is_accepted(tmp_path, monkeypatch):
    assert _warns(tmp_path, "escape", """
        p(D) <- (D is ++(dict(a=1)))
    """, monkeypatch) == []


def test_hosted_python_keywords_are_untouched(tmp_path, monkeypatch):
    assert _warns(tmp_path, "hosted", """
        def helper(a=1, b=2):
            return dict(a=a, b=b)

        p(X) <- (X is ++(helper(a=3)))
    """, monkeypatch) == []
