"""ISO/IEC 13211-2 ``:- end_module(Name).`` and the "require end_module"
setting (operator ruling 2026-09-30; ``clausal.end_module``).

Both ``.pl`` front ends apply the same checks (one implementation), so every
load test runs under each.  Every load clears ``__pycache__`` and asserts
which loader ran (the ``native`` fixture).
"""
from __future__ import annotations

import os
import sys
import textwrap

import pytest

from clausal import end_module as EM
from clausal import _suffixes

FRONTENDS = ["native", "translator"]


@pytest.fixture(autouse=True)
def _no_setting(monkeypatch):
    """No process-wide override leaks into or out of a test."""
    monkeypatch.delenv(EM.REQUIRE_END_MODULE_ENV, raising=False)
    EM.reset_require_end_module()
    yield
    EM.reset_require_end_module()


def _load(native, fe, name, text):
    return native.load(name, textwrap.dedent(text), frontend=fe)


def _refused(native, fe, name, text):
    with pytest.raises(SyntaxError) as ei:
        _load(native, fe, name, text)
    assert name not in sys.modules
    return str(ei.value)


# ── a valid end_module ──


@pytest.mark.parametrize("fe", FRONTENDS)
def test_a_matching_end_module_as_the_last_item_loads(native, ans, fe):
    mod = _load(native, fe, f"em_ok_{fe}", f"""\
        :- module(em_ok_{fe}, [p/1]).
        p(1).
        p(2).
        :- end_module(em_ok_{fe}).
        % only comments after it
        """)
    assert ans(mod, "p") == [1, 2]


# ── the refusals, each with its ISO error term ──


@pytest.mark.parametrize("fe", FRONTENDS)
def test_a_mismatched_name_is_an_existence_error(native, fe):
    msg = _refused(native, fe, f"em_mis_{fe}", f"""\
        :- module(em_mis_{fe}, [p/1]).
        p(1).
        :- end_module(other).
        """)
    assert "error(existence_error(module, other), end_module/1)" in msg
    assert f"the open module is em_mis_{fe}" in msg


@pytest.mark.parametrize("fe", FRONTENDS)
def test_a_clause_after_end_module_is_refused(native, fe):
    msg = _refused(native, fe, f"em_tr_{fe}", f"""\
        :- module(em_tr_{fe}, [p/1]).
        p(1).
        :- end_module(em_tr_{fe}).
        p(2).
        """)
    assert (f"error(permission_error(modify, module, em_tr_{fe}), "
            f"end_module/1)") in msg
    assert "the clause p(2)" in msg


@pytest.mark.parametrize("fe", FRONTENDS)
def test_a_directive_after_end_module_is_refused(native, fe):
    msg = _refused(native, fe, f"em_trd_{fe}", f"""\
        :- module(em_trd_{fe}, [p/1]).
        p(1).
        :- end_module(em_trd_{fe}).
        :- dynamic(q/1).
        """)
    assert f"permission_error(modify, module, em_trd_{fe})" in msg


@pytest.mark.parametrize("fe", FRONTENDS)
def test_end_module_without_module_2_is_an_existence_error(native, fe):
    msg = _refused(native, fe, f"em_nm_{fe}", f"""\
        p(1).
        :- end_module(em_nm_{fe}).
        """)
    assert (f"error(existence_error(module, em_nm_{fe}), end_module/1)"
            in msg)
    assert "this file has none" in msg


@pytest.mark.parametrize("fe", FRONTENDS)
def test_a_duplicate_end_module_is_refused(native, fe):
    msg = _refused(native, fe, f"em_dup_{fe}", f"""\
        :- module(em_dup_{fe}, [p/1]).
        p(1).
        :- end_module(em_dup_{fe}).
        :- end_module(em_dup_{fe}).
        """)
    assert (f"error(existence_error(module, em_dup_{fe}), end_module/1)"
            in msg)
    assert "duplicate" in msg


@pytest.mark.parametrize("fe", FRONTENDS)
@pytest.mark.parametrize("arg, term", [("X", "instantiation_error"),
                                       ("f(x)", "type_error(atom, f(x))")])
def test_a_module_name_that_is_no_atom_is_refused(native, fe, arg, term):
    msg = _refused(native, fe, f"em_na_{fe}", f"""\
        :- module(em_na_{fe}, [p/1]).
        p(1).
        :- end_module({arg}).
        """)
    assert f"error({term}, end_module/1)" in msg


# ── required ──

_MISSING = """\
    :- module({name}, [p/1]).
    p(1).
    """


@pytest.mark.parametrize("fe", FRONTENDS)
def test_a_missing_end_module_loads_under_the_pl_default(native, ans, fe):
    name = f"em_miss_{fe}"
    mod = _load(native, fe, name, _MISSING.format(name=name))
    assert ans(mod, "p") == [1]


@pytest.mark.parametrize("fe", FRONTENDS)
def test_the_env_var_requires_end_module_and_names_file_and_module(
        native, monkeypatch, fe):
    name = f"em_req_{fe}"
    monkeypatch.setenv(EM.REQUIRE_END_MODULE_ENV, "1")
    msg = _refused(native, fe, name, _MISSING.format(name=name))
    assert f"{name}.pl" in msg and f"module {name} does not end" in msg
    assert (f"error(existence_error(directive, end_module({name})), load/1)"
            in msg)
    assert "CLAUSAL_REQUIRE_END_MODULE=1" in msg


@pytest.mark.parametrize("fe", FRONTENDS)
def test_required_does_not_touch_a_file_without_module_2(native, ans,
                                                         monkeypatch, fe):
    monkeypatch.setenv(EM.REQUIRE_END_MODULE_ENV, "1")
    mod = _load(native, fe, f"em_plain_{fe}", "p(1).\n")
    assert ans(mod, "p") == [1]


@pytest.mark.parametrize("fe", FRONTENDS)
def test_the_python_setter_requires_it_and_env_0_does_not(native,
                                                          monkeypatch, fe):
    name = f"em_set_{fe}"
    EM.set_require_end_module(True)
    _refused(native, fe, name, _MISSING.format(name=name))
    EM.reset_require_end_module()
    monkeypatch.setenv(EM.REQUIRE_END_MODULE_ENV, "0")
    _load(native, fe, name, _MISSING.format(name=name))


@pytest.mark.parametrize("fe", FRONTENDS)
def test_the_files_own_flag_directive_requires_it_for_that_file(native, fe):
    name = f"em_fl_{fe}"
    msg = _refused(native, fe, name, f"""\
        :- set_prolog_flag(require_end_module, true).
        :- module({name}, [p/1]).
        p(1).
        """)
    assert "this file's set_prolog_flag(require_end_module, true)" in msg


@pytest.mark.parametrize("fe", FRONTENDS)
def test_the_files_own_flag_false_wins_over_the_process_setting(native, fe):
    EM.set_require_end_module(True)
    name = f"em_fl0_{fe}"
    _load(native, fe, name, f"""\
        :- set_prolog_flag(require_end_module, false).
        :- module({name}, [p/1]).
        p(1).
        """)


def test_an_unknown_env_value_is_an_error_not_a_default(monkeypatch):
    monkeypatch.setenv(EM.REQUIRE_END_MODULE_ENV, "maybe")
    with pytest.raises(ValueError, match="CLAUSAL_REQUIRE_END_MODULE"):
        EM.end_module_required(EM.SURFACE_PL)


# ── the surface -> default table ──


def test_the_surface_default_table():
    assert EM.REQUIRE_END_MODULE_DEFAULTS == {"pl": False,
                                              "clausal_prolog": True}
    assert EM.end_module_required(EM.SURFACE_CLAUSAL_PROLOG) is True
    assert EM.end_module_required(EM.SURFACE_PL) is False
    # The seam is never affected, whatever the override says.
    EM.set_require_end_module(True)
    assert EM.end_module_required(EM.SURFACE_SEAM) is False
    assert EM.end_module_required(EM.SURFACE_PL) is True
    EM.set_require_end_module(False)
    assert EM.end_module_required(EM.SURFACE_CLAUSAL_PROLOG) is False


def test_surface_of_follows_the_suffix_tuples(monkeypatch):
    assert EM.surface_of("m.pl") == "pl"
    assert EM.surface_of("m.seam") == "seam"
    assert EM.surface_of("m.clausal") == "seam"       # until the flip
    # The flip moves .clausal into CLAUSAL_PROLOG_SUFFIXES; nothing else.
    monkeypatch.setattr(_suffixes, "CLAUSAL_PROLOG_SUFFIXES", (".clausal",))
    monkeypatch.setattr(_suffixes, "CLAUSAL_SUFFIXES", (".seam",))
    assert EM.surface_of("m.clausal") == "clausal_prolog"
    assert EM.end_module_required(EM.surface_of("m.clausal")) is True


def test_a_clausal_prolog_file_needs_end_module_through_the_lowering():
    from clausal.tools import iso_l3 as L3
    src = ":- module(cp, [p/1]).\np(1).\n"
    L3.lower_source(src, "cp.pl")                     # .pl: optional
    with pytest.raises(L3.LoweringRefused, match="end_module"):
        L3.lower_source(src, "cp.clausal", surface=EM.SURFACE_CLAUSAL_PROLOG)
    L3.lower_source(src + ":- end_module(cp).\n", "cp.clausal",
                    surface=EM.SURFACE_CLAUSAL_PROLOG)


# ── the Prolog flag ──

_FLAGS = """\
    flag(V) :- current_prolog_flag(require_end_module, V).
    set(V) :- set_prolog_flag(require_end_module, V).
    """


@pytest.mark.parametrize("fe", FRONTENDS)
def test_current_prolog_flag_reads_the_process_setting(native, ans,
                                                       monkeypatch, fe):
    mod = _load(native, fe, f"em_flag_{fe}", _FLAGS)
    assert ans(mod, "flag") == ["default"]
    monkeypatch.setenv(EM.REQUIRE_END_MODULE_ENV, "1")
    assert ans(mod, "flag") == [True]
    EM.set_require_end_module(False)
    assert ans(mod, "flag") == [False]


@pytest.mark.parametrize("fe", FRONTENDS)
def test_set_prolog_flag_as_a_goal_sets_the_process_setting(native, ans, fe):
    mod = _load(native, fe, f"em_sflag_{fe}", _FLAGS)
    assert ans(mod, "set", 1, True) == [()]
    assert EM.require_end_module_setting() is True
    assert ans(mod, "flag") == [True]
    # ... and it governs the module files loaded after it.
    name = f"em_after_{fe}"
    _refused(native, fe, name, _MISSING.format(name=name))
    assert ans(mod, "set", 1, "default") == [()]
    assert EM.require_end_module_setting() is None
    assert ans(mod, "flag") == ["default"]


# ── the seam is never affected ──


def test_a_seam_module_loads_under_the_requirement(native, ans, monkeypatch):
    monkeypatch.setenv(EM.REQUIRE_END_MODULE_ENV, "1")
    mod = native.load("em_seam", "-module(em_seam, [p/1])\np(1),\n",
                      suffix=".seam", frontend=None)
    assert ans(mod, "p") == [1]


def test_a_seam_file_cannot_set_the_flag(native):
    with pytest.raises(SyntaxError, match="does not apply to a seam file"):
        native.load("em_seamfl",
                    "-set_prolog_flag(require_end_module, true)\np(1),\n",
                    suffix=".seam", frontend=None)


# ── Scryer refuses the directive: the oracle paths strip it ──


def test_strip_end_module_comments_it_out_in_place():
    src = ":- module(m, [p/1]).\np(1).\n:- end_module(m).\n% tail\n"
    out = EM.strip_end_module(src)
    assert out.count("\n") == src.count("\n")
    assert "\n% :- end_module(m).\n" in out
    assert EM.strip_end_module("p(end_module).\n") == "p(end_module).\n"


def test_the_scryer_oracle_loads_a_file_with_end_module(tmp_path):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, here)
    try:
        from _oracles import SCRYER, run_scryer
    finally:
        sys.path.remove(here)
    if not os.path.exists(SCRYER):
        pytest.skip(f"the clean Scryer is not built at {SCRYER}")
    f = tmp_path / "emscry.pl"
    f.write_text(":- module(emscry, [p/1]).\np(1).\n:- end_module(emscry).\n")
    out = run_scryer(str(f), ["emscry:p(X)."], timeout=60)
    assert "X = 1" in out.stdout, (out.stdout, out.stderr)
    assert "domain_error" not in out.stdout + out.stderr


def test_the_exporter_refuses_to_emit_end_module():
    from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
    with pytest.raises(NotImplementedError, match="Scryer refuses"):
        clausal_source_to_prolog("-module(sx, [p/1])\np(1),\n"
                                 "-end_module(sx)\n")
