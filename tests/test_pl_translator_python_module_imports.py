"""D46: the OLD .pl translator front end imports a Python-backed module by
name/N, as the native front end does (D32).

``:- use_module(py/datetime, [days_between/3]).`` used to fail on the
translator with "py.datetime is not a Clausal module, so its names have no
predicate arities to select; list the bare name `days_between` instead": it
emitted the indicator, which the seam's -import_from refuses against a
Python module.  Each name/N is now CHECKED against
clausal.module_signatures and imported bare.  The same .pl answers the same
under both front ends, and refuses the same entries with the same message.
"""
import textwrap

import pytest

from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var

SRC = """\
    :- module({name}, [gap/1, back/1, due/1]).
    {use}
    gap(N) :- days_between(date(2026, 1, 15), date(2026, 3, 1), N).
    back(N) :- days_between(date(2026, 3, 1), date(2026, 1, 15), N).
    due(D) :- timedelta(30, 0, TD), date_add(date(2026, 1, 15), TD, D).
"""

LIST = ":- use_module(py/datetime, [days_between/3, timedelta/3, date_add/3])."
WHOLE = ":- use_module(py/datetime)."


@pytest.fixture
def load(tmp_path, monkeypatch):
    import sys
    from clausal.import_hook import _load_prolog_module
    loaded = []

    def _load(frontend, name, use):
        monkeypatch.setenv("CLAUSAL_PL_FRONTEND", frontend)
        p = tmp_path / f"{name}.pl"
        p.write_text(textwrap.dedent(SRC.format(name=name, use=use)))
        loaded.append(name)
        return _load_prolog_module(name, str(p))
    yield _load
    for n in loaded:
        sys.modules.pop(n, None)


def _answers(mod):
    out = {}
    for p in ("gap", "back", "due"):
        v = Var()
        out[p] = [_deref_walk(v) for _ in solve((p, v), mod)]
    return out


@pytest.mark.parametrize("use", [LIST, WHOLE], ids=["indicators", "whole"])
def test_both_front_ends_answer_the_same(load, use):
    tag = "l" if use is LIST else "w"
    res = {fe: _answers(load(fe, f"d46_{fe}_{tag}", use))
           for fe in ("translator", "native")}
    assert res["translator"] == res["native"]
    assert res["translator"]["gap"] and res["translator"]["due"]


@pytest.mark.parametrize("entry,expect", [
    ("days_between/2", "existence_error(procedure, days_between/2) -- "
                       "py.datetime has days_between as days_between/3"),
    ("nosuch/1", "existence_error(procedure, nosuch/1) -- "
                 "py.datetime has no predicate nosuch"),
])
def test_both_front_ends_refuse_the_same_entry(load, entry, expect):
    for fe in ("translator", "native"):
        with pytest.raises(SyntaxError) as info:
            load(fe, f"d46r_{fe}_{entry.split('/')[0]}",
                 f":- use_module(py/datetime, [{entry}]).")
        msg = str(info.value)
        assert expect in msg, (fe, msg)
        assert "py.datetime offers" in msg


def test_a_py_module_carrying_a_clausal_database_is_not_python_backed(
        tmp_path, monkeypatch):
    """roborev (Medium): as on the native path, a .py module with a Clausal
    database keeps the Clausal route (its indicators are real arities)."""
    import sys
    from clausal.tools.prolog_to_clausal import _python_backed_module
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "d46_pydb.py").write_text(
        "from clausal.logic.database import Module\n"
        "globals()['$module'] = Module('d46_pydb')\n")
    (tmp_path / "d46_pyplain.py").write_text("X = 1\n")
    try:
        assert _python_backed_module("d46_pydb") is None
        assert _python_backed_module("d46_pyplain") is not None
    finally:
        sys.modules.pop("d46_pydb", None)
        sys.modules.pop("d46_pyplain", None)


def test_a_python_module_that_fails_to_import_is_refused_at_translation(
        tmp_path, monkeypatch):
    import sys
    from clausal.tools.prolog_to_clausal import (
        PrologTranslationError, prolog_to_clausal)
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "d46_broken.py").write_text("raise RuntimeError('boom')\n")
    try:
        with pytest.raises(PrologTranslationError, match="could not be imported"):
            prolog_to_clausal(":- use_module(d46_broken, [p/1]).\n")
    finally:
        sys.modules.pop("d46_broken", None)


def test_a_non_integer_arity_is_refused():
    from clausal.tools.prolog_to_clausal import (
        PrologTranslationError, prolog_to_clausal)
    with pytest.raises(PrologTranslationError, match="not a name/N indicator"):
        prolog_to_clausal(":- use_module(py/datetime, [days_between/_]).\n")
