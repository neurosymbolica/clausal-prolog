"""``haar_cascade_path/2``: the PATH is a STRING, the NAME stays an ATOM.

Ruled 2026-10-04 (adapters are their own entry point, strings spec 9.4):
a filesystem path is free-form text, the string ``('$chars', p)``; a
cascade name is a key and stays an atom (a plain ``str``).

Runs WITHOUT OpenCV (``*_stubbed.py``, see packages/conftest.py): a fake
module in ``opencv._cv2`` supplies ``data.haarcascades``, and the
registry's lazily built fact cache is reset around each test.  A bound
path -- a string or an atom written elsewhere, not the object the registry
handed out -- is matched by its text (check mode and reverse lookup).
"""

from __future__ import annotations

import types

import pytest

from clausal.logic.cells import chars, is_chars
from clausal.logic.variables import Trail, Var, deref
from clausal.modules.py import opencv
from clausal.modules.py import opencv_objdetect as od


def _fact_cache():
    return od.haar_cascade_path._dispatch_fns[2].cache


@pytest.fixture
def cascades(monkeypatch, tmp_path):
    for fname in ("haarcascade_frontalface_default.xml", "haarcascade_eye.xml"):
        (tmp_path / fname).write_text("<opencv_storage/>")
    base = str(tmp_path) + "/"
    monkeypatch.setattr(opencv, "_cv2", types.SimpleNamespace(
        data=types.SimpleNamespace(haarcascades=base)))
    _fact_cache().clear()
    yield base
    _fact_cache().clear()


def _solutions(name, path):
    """(name, path) for each answer; *path* may be bound."""
    proceed, fail = object(), object()
    fn = od.haar_cascade_path._dispatch_fns[2]
    out = []
    trail = Trail()
    for s in fn(None, proceed, fail, None, name, path, trail):
        if s[0] is proceed:
            out.append((deref(name), deref(path)))
    return out


def test_lookup_answers_the_path_as_a_string(cascades):
    [(_, p)] = _solutions("face", Var())
    assert is_chars(p)
    assert p == chars(cascades + "haarcascade_frontalface_default.xml")


def test_a_string_name_looks_up_the_same_path(cascades):
    [(_, p)] = _solutions(chars("eye"), Var())
    assert p == chars(cascades + "haarcascade_eye.xml")


def test_enumerated_names_stay_atoms_paths_are_strings(cascades):
    got = _solutions(Var(), Var())
    assert sorted(n for n, _ in got) == ["eye", "face"]
    assert all(type(n) is str for n, _ in got)
    assert all(is_chars(p) for _, p in got)


@pytest.mark.parametrize("spell", [chars, str], ids=["string", "atom"])
def test_check_mode_matches_a_path_by_its_text(cascades, spell):
    path = spell(cascades + "haarcascade_eye.xml")
    assert len(_solutions("eye", path)) == 1
    assert _solutions("face", path) == []


@pytest.mark.parametrize("spell", [chars, str], ids=["string", "atom"])
def test_reverse_lookup_by_a_path_written_elsewhere(cascades, spell):
    path = spell(cascades + "haarcascade_frontalface_default.xml")
    [(n, _)] = _solutions(Var(), path)
    assert n == "face"
