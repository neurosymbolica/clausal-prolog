"""Lint: warn on ``A | B`` cons syntax in a clause head.

A clause head containing ``BitOr`` over list literals is almost certainly
Prolog cons syntax (``[H|T]``) written by someone who does not know this DSL
spells it ``[H, *T]``.  The head compiles to a BitOr *term* that never unifies
with a real list, so every clause silently never matches — a measured
authoring study died on exactly this.  Warn at load time.
See ``todo/done/C1-ill-typed-interop-calls-are-silent-failures.md``.
"""

from __future__ import annotations

import warnings

from clausal.import_hook import _load_module
from clausal.templating.term_rewriting import ClausalLintWarning


def _lint_warnings(tmp_path, name, text):
    src = tmp_path / f"{name}.clausal"
    src.write_text(text)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _load_module(name, str(src))
    return [w for w in caught if issubclass(w.category, ClausalLintWarning)]


def test_warns_on_bracketed_cons_in_rule_head(tmp_path):
    # The canonical Prolog shape: [H | T] — BitOr as a list-literal element.
    # H_UNUSED: only the cons-bar shape matters here, not H's binding — a
    # plain H would also trip the (unrelated) singleton lint.
    ws = _lint_warnings(tmp_path, "cons_rule",
                        "my_len([H_UNUSED | T], N) <- (my_len(T, M), N == M + 1)\n")
    assert len(ws) == 1
    assert "did you mean" in str(ws[0].message)
    assert "[H, *T]" in str(ws[0].message)


def test_warns_on_list_literal_bitor_operand(tmp_path):
    # The measured authoring study's exact shape: head([W, S] | REST, ...) —
    # a list literal as a BitOr operand, outside any brackets.
    # S_UNUSED: only the cons-bar shape matters here — a plain S would also
    # trip the (unrelated) singleton lint.
    ws = _lint_warnings(
        tmp_path, "cons_study",
        "totals([W, S_UNUSED] | REST, N) <- (totals(REST, M), N == M + W)\n")
    assert len(ws) == 1
    assert "[H, *T]" in str(ws[0].message)


def test_warns_on_cons_in_fact_head(tmp_path):
    ws = _lint_warnings(tmp_path, "cons_fact", "starts([1 | _]),\n")
    assert len(ws) == 1


def test_warns_on_multi_element_cons(tmp_path):
    ws = _lint_warnings(tmp_path, "cons_multi",
                        "pair([A, B | T], A, B) <- (T is not [42])\n")
    assert len(ws) == 1


def test_warning_names_the_line(tmp_path):
    ws = _lint_warnings(tmp_path, "cons_line",
                        "ok(1),\n\nbad([H | T]) <- (H is not T)\n")
    assert len(ws) == 1
    assert "line 3" in str(ws[0].message)


def test_warns_on_cons_in_dcg_head(tmp_path):
    ws = _lint_warnings(tmp_path, "cons_dcg",
                        '-double_quotes(atom)\ntakes([H | T]) >> (["x"])\n')
    assert len(ws) == 1
    assert "[H, *T]" in str(ws[0].message)


def test_no_warn_on_clean_dcg_head(tmp_path):
    # The DCG path appends the synthetic _dcg0/_dcg1 state args to the
    # head before the lint runs — bare Names must not trip it.
    ws = _lint_warnings(tmp_path, "ok_dcg",
                        '-double_quotes(atom)\ntakes([H, *T]) >> (["x"])\n')
    assert ws == []


def test_warns_on_cons_in_asserted_rule_head(tmp_path):
    # assertz'd rules go through the expression-level `<-` path, not the
    # module-level one — same silently-never-matches failure mode.
    ws = _lint_warnings(
        tmp_path, "cons_assertz",
        "grow(X) <- (assertz(tmp_pred([H | T]) <- (H is not T)), X is 1)\n")
    assert len(ws) == 1


def test_no_warn_on_clean_asserted_rule_head(tmp_path):
    ws = _lint_warnings(
        tmp_path, "ok_assertz",
        "grow(X) <- (assertz(tmp_pred([H, *T]) <- (H is not T)), X is 1)\n")
    assert ws == []


def test_no_warn_on_star_spread_head(tmp_path):
    # The correct spelling must stay silent.
    # H_UNUSED: only the cons-bar shape matters here — a plain H would also
    # trip the (unrelated) singleton lint.
    ws = _lint_warnings(tmp_path, "ok_star",
                        "my_len([H_UNUSED, *T], N) <- (my_len(T, M), N == M + 1)\n")
    assert ws == []


def test_no_warn_on_plain_heads(tmp_path):
    assert _lint_warnings(tmp_path, "ok_plain",
                          "edge(1, 2),\npath(X, Y) <- edge(X, Y)\n") == []


def test_no_warn_on_bare_name_bitor_head(tmp_path):
    # A | B over plain names in a head is a structural BitOr pattern
    # (clpb-style) — not obviously cons; stay silent.
    # B_UNUSED: only the cons-bar shape matters here — a plain B would also
    # trip the (unrelated) singleton lint.
    ws = _lint_warnings(tmp_path, "ok_names",
                        "-private([holds(E)])\nholds(A | B_UNUSED) <- (holds(A))\n")
    assert ws == []


def test_no_warn_on_bitor_in_body(tmp_path):
    # The lint is about heads; body expressions are evaluated, not matched.
    ws = _lint_warnings(tmp_path, "ok_body",
                        "mask(X, Y) <- (Y is ++(X | 8))\n")
    assert ws == []
