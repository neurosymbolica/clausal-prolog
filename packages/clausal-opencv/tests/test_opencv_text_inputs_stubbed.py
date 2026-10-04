"""``imwrite/2,3`` take the path a STRING or an atom denotes (spec §9.4).

Both read the path with ``deref`` and wrote ``str(path)``, so a string --
the chars carrier ``('$chars', '/tmp/x.png')`` -- reached
``cv2.imwrite`` as the repr ``"('$chars', '/tmp/x.png')"``.

Runs WITHOUT OpenCV (``*_stubbed.py``, see packages/conftest.py): the
adapter imports cv2 lazily through ``opencv._cv2``, so a fake module put
there records exactly the path the adapter hands the library.
"""

from __future__ import annotations

import types

import pytest

from clausal.logic.cells import chars
from clausal.logic.exceptions import LogicException
from clausal.logic.variables import Trail
from clausal.modules.py import opencv


@pytest.fixture
def written(monkeypatch):
    calls = []

    def imwrite(path, img, *params):
        calls.append((path, params))
        return True

    monkeypatch.setattr(opencv, "_cv2", types.SimpleNamespace(imwrite=imwrite))
    return calls


def _run(fn, *args):
    proceed, fail = object(), object()
    return [s for s in fn(None, proceed, fail, None, *args, Trail())
            if s[0] is proceed]


@pytest.mark.parametrize("path", [chars("/tmp/out.png"), "/tmp/out.png"])
def test_imwrite_2_hands_cv2_the_path(written, path):
    assert len(_run(opencv._imwrite_dispatch_2, path, [[0]])) == 1
    assert written == [("/tmp/out.png", ())]


@pytest.mark.parametrize("path", [chars("/tmp/out.jpg"), "/tmp/out.jpg"])
def test_imwrite_3_hands_cv2_the_path(written, path):
    assert len(_run(opencv._imwrite_dispatch_3, path, [[0]], [1, 90])) == 1
    assert written == [("/tmp/out.jpg", ([1, 90],))]


def test_imwrite_of_a_compound_path_is_a_type_error(written):
    with pytest.raises(LogicException) as info:
        _run(opencv._imwrite_dispatch_2, ("f", 1), [[0]])
    assert info.value.term[1][:2] == ("type_error", "text")
    assert written == []
