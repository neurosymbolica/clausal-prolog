"""Lint: warn on `X is not <pattern-with-unbound-var>`.

`is not` is dif/2 (disequality). Against a partial term (a compound/list with a
fresh variable or `_`) it compares with a fresh variable and so ALWAYS succeeds
— silently turning a guard into an always-true goal. This is a high-cost footgun
(it caused a 3^N solution blow-up in a downstream helper library). Warn at load time; stay
silent for the correct ground/scalar uses. See todo/lint-is-not-wildcard-pattern.md.
"""

from __future__ import annotations

import warnings

from clausal.import_hook import _load_module
from clausal.templating.term_rewriting import ClausalLintWarning
from tests._suffix import SEAM


def _lint_warnings(tmp_path, name, text):
    src = tmp_path / f"{name}{SEAM}"
    src.write_text(text)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _load_module(name, str(src))
    return [w for w in caught if issubclass(w.category, ClausalLintWarning)]


def test_warns_on_compound_with_wildcard(tmp_path):
    ws = _lint_warnings(tmp_path, "lint_compound",
                        "-private([tag(X)])\nbad(S) <- (S is not tag(_))\n")
    assert len(ws) == 1
    assert "always" in str(ws[0].message).lower()


def test_warns_on_list_with_var(tmp_path):
    # Z_UNUSED: only Z's unbound-ness matters here — a plain Z would also
    # trip the (unrelated) singleton lint.
    ws = _lint_warnings(tmp_path, "lint_list", "bad(S) <- (S is not [Z_UNUSED])\n")
    assert len(ws) == 1


def test_warns_on_nested_compound_with_var(tmp_path):
    # Z_UNUSED: only Z's unbound-ness matters here — a plain Z would also
    # trip the (unrelated) singleton lint.
    ws = _lint_warnings(tmp_path, "lint_nested",
                        "-private([f(X), g(Y)])\nbad(S) <- (S is not f(g(Z_UNUSED)))\n")
    assert len(ws) == 1


def test_no_warn_on_scalar_rhs(tmp_path):
    assert _lint_warnings(tmp_path, "ok_int", "ok(S) <- (S is not 0)\n") == []
    assert _lint_warnings(tmp_path, "ok_str", '-double_quotes(atom)\nok(K) <- (K is not "key")\n') == []


def test_no_warn_on_empty_list(tmp_path):
    assert _lint_warnings(tmp_path, "ok_empty", "ok(KEYS) <- (KEYS is not [])\n") == []


def test_no_warn_on_bare_var_rhs(tmp_path):
    assert _lint_warnings(tmp_path, "ok_bare", "ok(X, Y) <- (X is not Y)\n") == []


def test_no_warn_on_ground_compound(tmp_path):
    ws = _lint_warnings(tmp_path, "ok_ground",
                        '-double_quotes(atom)\n-private([tag(X)])\nok(S) <- (S is not tag("a"))\n')
    assert ws == []
