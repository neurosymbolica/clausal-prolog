"""Regression: an arrow-less, multi-element comma tuple at statement (module)
level must raise, not silently evaluate-and-discard.

``fact(R), other(R)`` written as a bare module-level statement parses as a
plain Python ``Tuple(ctx=Load)`` with two ``Call`` elements.  The
EmbedTransformer only recognised the *single*-element tuple shapes
(trailing-comma fact ``pred(args),`` and trailing-comma rule ``head <- (b),``)
and the arrow-first multi-element shape (``head <- g1, g2`` → ``_ARROW_BODY_ERROR``).
A multi-element tuple whose first element is a plain ``Call`` fell through every
case, survived as a runtime expression, and was evaluated then discarded — no
clause asserted, no goal run, no error.  The author almost certainly meant a
rule body ``head <- (goal1, goal2)``.

See ``todo/statement-context-tuple-goals-silently-discarded.md``.  This was the
real footgun behind the "re-exported functor finds 0 solutions" report: a
multi-goal body written without a head or parentheses.
"""

import os

import pytest

from clausal.import_hook import _load_module


def _load(tmp_path, source: str, name: str):
    path = os.path.join(str(tmp_path), f"{name}.clausal")
    with open(path, "w") as f:
        f.write(source)
    return _load_module(name, path)


def test_arrow_less_multi_goal_statement_raises(tmp_path):
    """``fact(R), other(R)`` as a bare statement is a SyntaxError, not a no-op."""
    src = (
        "-module(mgd_a, [ q(R), fact(R), other(R) ])\n"
        "fact(a),\n"
        "q(R) <- (fact(R)),\n"
        "fact(R), other(R)\n"
    )
    with pytest.raises(SyntaxError, match="comma-separated goals"):
        _load(tmp_path, src, "mgd_a")


def test_two_bare_facts_on_one_line_raises(tmp_path):
    """Even the simplest two-call tuple ``a(1), b(2)`` is rejected."""
    src = (
        "-module(mgd_b, [ a(X), b(X) ])\n"
        "a(1), b(2)\n"
    )
    with pytest.raises(SyntaxError, match="comma-separated goals"):
        _load(tmp_path, src, "mgd_b")


def test_trailing_comma_fact_still_works(tmp_path):
    """A single-element tuple (trailing-comma fact) is unaffected."""
    mod = _load(
        tmp_path,
        "-module(mgd_c, [ edge(A, B) ])\n"
        "edge(1, 2),\n",
        "mgd_c",
    )
    assert len(mod.edge._clauses) == 1


def test_parenthesized_rule_body_still_works(tmp_path):
    """``head <- (g1, g2)`` — an explicit parenthesised conjunction — is fine."""
    mod = _load(
        tmp_path,
        "-module(mgd_d, [ q(R), fact(R), other(R) ])\n"
        "fact(a),\n"
        "other(a),\n"
        "q(R) <- (fact(R), other(R))\n",
        "mgd_d",
    )
    assert len(mod.q._clauses) == 1


def test_arrow_first_multi_goal_still_raises_arrow_error(tmp_path):
    """``head <- g1, g2`` keeps raising the pre-existing arrow-body error."""
    src = (
        "-module(mgd_e, [ q(R), fact(R), other(R) ])\n"
        "q(R) <- fact(R), other(R)\n"
    )
    with pytest.raises(SyntaxError, match="parenthesized"):
        _load(tmp_path, src, "mgd_e")
