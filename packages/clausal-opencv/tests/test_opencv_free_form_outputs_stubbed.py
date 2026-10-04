"""``haar_cascade_path/2``: the PATH is a STRING, the NAME stays an ATOM.

Ruled 2026-10-04 (adapters are their own entry point, strings spec 9.4):
a filesystem path is free-form text, the string ``('$chars', p)``; a
cascade name is a key and stays an atom (a plain ``str``).

Runs WITHOUT OpenCV (``*_stubbed.py``, see packages/conftest.py): a fake
module in ``opencv._cv2`` supplies ``data.haarcascades``, and the
registry's lazily built fact cache is reset around each test.
"""

from __future__ import annotations

import types

import pytest

from clausal.logic.cells import chars, is_chars
from clausal.logic.variables import Trail, Var, deref
from clausal.modules.py import opencv
from clausal.modules.py import opencv_objdetect as od


def _fact_cache():
    fn = od.haar_cascade_path._dispatch_fns[2]
    [cache] = [c.cell_contents for c in fn.__closure__
               if isinstance(c.cell_contents, dict)]
    return cache


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
