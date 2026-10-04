"""A symbolic NAME an adapter hands back crosses as an ATOM; free-form text
stays text; a bound argument may be either ("atom out, text in", Python-
boundary spec 2026-09-21, ruled for adapter results 2026-10-04).

Engine adapters covered: py.os platform/1, py.logging get_level/2,
py.sqlite current_connection/1.  The tag itself (``symbol`` /
``text_result`` / ``unify_result``) is pinned too, with the leak rule: no
term holds the tag class, only a plain ``str``.
"""

from __future__ import annotations

import sys

import pytest

from clausal._suffixes import SEAM_SUFFIX
from clausal.import_hook import _load_module
from clausal.logic.cells import chars
from clausal.logic.solve import call, _deref_walk
from clausal.logic.variables import Trail, Var, deref
from clausal.modules.py import symbol, text_result, unify_result


SRC = """\
-double_quotes(chars)
-import_from(py.os, [platform, working_directory])
-import_from(py.logging, [get_logger, set_level, get_level])
-import_from(py.sqlite, [connect, disconnect, current_connection])

plat(P) <- platform(P)
plat_text() <- platform(++sys_platform_text())
plat_atom() <- platform(++sys_platform_atom())
cwd(D) <- working_directory(D)

level(L) <- (get_logger("t.symbolic.lvl", G), set_level(G, "warning"),
             get_level(G, L))
level_atom() <- (get_logger("t.symbolic.lvl", G), set_level(G, "warning"),
                 get_level(G, 'WARNING'))
level_text() <- (get_logger("t.symbolic.lvl", G), set_level(G, "warning"),
                 get_level(G, "WARNING"))
level_lower_atom() <- (get_logger("t.symbolic.lvl", G), set_level(G, "WARNING"),
                       get_level(G, 'warning'))
level_lower_text() <- (get_logger("t.symbolic.lvl", G), set_level(G, 'WARNING'),
                       get_level(G, "warning"))
level_other() <- (get_logger("t.symbolic.lvl", G), set_level(G, "warning"),
                  get_level(G, 'error'))

alias(A) <- (connect(":memory:", "symbolic_alias_1"),
             current_connection(A), A == 'symbolic_alias_1',
             disconnect("symbolic_alias_1"))
"""


@pytest.fixture(scope="module")
def module(tmp_path_factory):
    src = tmp_path_factory.mktemp("symbolic") / f"symbolic_probe{SEAM_SUFFIX}"
    src.write_text(SRC, encoding="utf-8")
    mod = _load_module("symbolic_probe", str(src))
    mod.__dict__["sys_platform_text"] = lambda: chars(sys.platform)
    mod.__dict__["sys_platform_atom"] = lambda: sys.platform
    return mod.__dict__["$module"]


def _one(module, name):
    x = Var()
    got = [_deref_walk(x) for _ in call(name, x, module=module)]
    assert len(got) == 1, got
    return got[0]


def _holds(module, name):
    return len(list(call(name, module=module))) >= 1


# ── the tag ──────────────────────────────────────────────────────────────


def test_a_symbol_result_is_a_plain_str_atom():
    out = text_result(symbol("cpu"))
    assert out == "cpu" and type(out) is str           # leak rule: no tag


def test_a_symbol_inside_a_list_is_an_atom_and_plain_text_stays_text():
    out = text_result([symbol("x"), None, "free form"])
    assert out[0] == "x" and type(out[0]) is str
    assert out[1] is None
    assert out[2] == chars("free form")


def test_unify_result_accepts_the_atom_or_the_text():
    for bound in ("cpu", chars("cpu")):
        assert unify_result(bound, symbol("cpu"), Trail())
    assert not unify_result("gpu", symbol("cpu"), Trail())
    assert not unify_result(chars("gpu"), symbol("cpu"), Trail())
    v = Var()
    assert unify_result(v, symbol("cpu"), Trail())
    assert type(deref(v)) is str and deref(v) == "cpu"


# ── engine adapters ──────────────────────────────────────────────────────


def test_platform_is_an_atom(module):
    p = _one(module, "plat")
    assert p == sys.platform and type(p) is str


def test_platform_check_mode_accepts_atom_and_text(module):
    assert _holds(module, "plat_atom")
    assert _holds(module, "plat_text")


def test_working_directory_stays_text(module):
    assert _one(module, "cwd") == chars(__import__("os").getcwd())


def test_a_log_level_is_a_lowercase_atom(module):
    # Ruled 2026-10-04 (D11): lowercase, the spelling set_level/2 takes.
    assert _one(module, "level") == "warning"


def test_a_bound_level_is_read_in_either_case(module):
    assert _holds(module, "level_atom")
    assert _holds(module, "level_text")
    assert _holds(module, "level_lower_atom")
    assert _holds(module, "level_lower_text")
    assert not _holds(module, "level_other")


def test_a_custom_level_name_is_a_lowercase_atom_and_an_unnamed_one_text():
    import logging
    from clausal.modules.py.logging import _get_level_2
    logging.addLevelName(5, "TRACE")
    lg = logging.getLogger("t.symbolic.custom")
    for level, want in ((5, "trace"), (15, chars("Level 15"))):
        lg.setLevel(level)
        v = Var()
        assert list(_get_level_2(lg, v, Trail(), None))
        assert deref(v) == want


def test_a_symbol_inside_a_dictterm_accepts_text_too():
    from clausal.terms import DictTerm
    out = DictTerm({"p": symbol("cpu")})
    assert unify_result(DictTerm({"p": "cpu"}), out, Trail())
    assert unify_result(DictTerm({"p": chars("cpu")}), out, Trail())


def test_a_connection_alias_is_an_atom(module):
    a = _one(module, "alias")
    assert a == "symbolic_alias_1" and type(a) is str
