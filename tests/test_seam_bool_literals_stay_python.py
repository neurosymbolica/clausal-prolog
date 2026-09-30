"""In .seam source, Python's ``True``/``False`` literals (and the ``true``/
``false`` spellings the seam folds into them) stay the REAL Python bool
objects in Python-hosted code: ``str(v) == "True"``, ``repr``, ``==``,
``hash`` and ``isinstance(v, bool)`` are Python's.  Only the ENGINE's
logical operations -- unify, compare, arithmetic, the type tests, write/1
and format/2 -- read them as the atoms ``true``/``false`` (D35).

The seam rewrites ``str(x)`` and an f-string's ``{x}`` in Python-hosted code
into the atom-aware crossings ``seam.text_of`` / ``seam.text_value`` (an
ATOM spells itself there, not as its tuple repr).  When ``is_atom`` began
to admit the truth objects, those crossings spelled ``True`` as ``"true"``:
a module that builds ids with ``"-".join(str(v) for v in combo)`` and looks
them up by the literal ``'True-False'`` then raised ``KeyError``.  This
file is that module, reduced.
"""
from __future__ import annotations

import importlib
import sys
import textwrap

import pytest

from clausal import Var
from clausal.logic.solve import call
from clausal.logic.variables import deref, walk

SEAM = """\
    -private([combo, flag, ok, u1, ident, a])
    combos = [(True, False), (False, False)]
    ids = {"-".join(str(v) for v in c): c for c in combos}
    s_true = str(True)
    f_true = f"{True}"
    f_spec = f"{True:>6}"
    combo(C) <- (member(C, combos))
    flag(True),
    flag(false),
    ident(K) <- (K is ++("-".join(str(v) for v in (True, False))))
    u1(ok) <- (true is 1)
    """


@pytest.fixture
def mod(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "seam_bool_lits.seam").write_text(textwrap.dedent(SEAM),
                                                  encoding="utf-8")
    sys.modules.pop("seam_bool_lits", None)
    importlib.invalidate_caches()
    m = importlib.import_module("seam_bool_lits")
    yield m
    sys.modules.pop("seam_bool_lits", None)


def _answers(m, name):
    v = Var()
    return [walk(deref(v)) for _ in call(name, v, module=m)]


def test_module_level_python_reads_the_literals_as_python_bools(mod):
    assert mod.combos == [(True, False), (False, False)]
    for c in mod.combos:
        for v in c:
            assert isinstance(v, bool) and type(v) is bool
            assert str(v) in ("True", "False") and repr(v) == str(v)
    assert set(mod.ids) == {"True-False", "False-False"}
    assert mod.ids["True-False"] == (True, False)      # the lookup that raised KeyError
    assert mod.s_true == "True"                          # str(True) in hosted code
    assert mod.f_true == "True"                          # f"{True}"
    assert mod.f_spec == format(True, ">6")              # a format spec meets the BOOL: plain Python's answer ("     1")


def test_answers_holding_a_literal_are_python_bools(mod):
    out = _answers(mod, "flag")
    assert out == [True, False]
    assert out[0] is True and out[1] is False            # ``false`` folds to False too
    for v in out:
        assert isinstance(v, bool) and str(v) in ("True", "False")
        assert hash(v) == hash(int(v)) and v == int(v)   # Python's == and hash
    combos = _answers(mod, "combo")
    assert combos == [(True, False), (False, False)]
    assert all(type(v) is bool for c in combos for v in c)
    assert _answers(mod, "ident") == ["True-False"]      # a ++ escape: plain Python str


def test_the_engine_still_reads_them_as_atoms(mod):
    assert _answers(mod, "u1") == []                     # ``true = 1`` fails: an atom is not a number
