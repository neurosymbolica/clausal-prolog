"""A code list renders like its twin, and a char list keys a dict like its twin.

* ``write_canonical(b"ab")`` printed the Python repr ``b'ab'``, which no reader
  reads back; the equal ``[97, 98]`` prints ``'.'(97,'.'(98,[]))``.
* A dict key written as a char list (``{[a, b]: 1}``, ``D[[a, b]]``) was a raw
  ``TypeError`` or a ``type_error(dict_key)``, though ``[a, b]`` is the term
  ``"ab"``, a key that works.  A char list now keys as the chars carrier.  An
  int list is deliberately NOT folded to its ``bytes`` spelling (the key is
  handed back, and ``[1, 2]`` coming back as ``b'\x01\x02'`` would surprise):
  it stays ``type_error(dict_key)``, loud, never a silent miss.
"""
from __future__ import annotations

import contextlib
import io

import pytest

from clausal.logic.solve import solve
from clausal.logic.variables import Var
from clausal.testing import load_clausal_module

_SRC = """\
-private([a, b, c])
w1 <- write_canonical(b"ab")
w2 <- write_canonical([97, 98])
w3 <- write_canonical(b"")
d1(V) <- (D is {"ab": 1}, V is D[[a, b]])
d2(V) <- (D is {[a, b]: 1}, V is D["ab"])
d3(V) <- (D is {b"ab": 1}, V is D[b"ab"])
d7(V) <- (D is {b"ab": 1}, V is D[[97, 98]])
d4(V) <- (D is {[a, b]: 1}, V is D[[a, b]])
d5(V) <- (D is {[a, b]: 1}, V is D[[a, c]])
d6(K) <- (D is {[a, b]: 1}, dict_pairs(D, [K-_]))
"""


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    p = tmp_path_factory.mktemp("shapes") / "shapes.seam"
    p.write_text(_SRC)
    return load_clausal_module(p)


def _printed(mod, name):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert any(True for _ in solve(name, mod))
    return buf.getvalue()


@pytest.mark.parametrize("name, out", [
    ("w1", "'.'(97,'.'(98,[]))"),
    ("w2", "'.'(97,'.'(98,[]))"),
    ("w3", "[]"),
])
def test_write_canonical_of_a_code_list(mod, name, out):
    assert _printed(mod, name) == out


def _answers(mod, name):
    v = Var()
    return [v.value for _ in solve((name, v), mod)]


@pytest.mark.parametrize("name", ["d1", "d2", "d3", "d4"])
def test_a_char_or_code_list_key_reads_its_twin(mod, name):
    assert _answers(mod, name) == [1]


def test_a_missing_list_key_is_an_existence_error(mod):
    from clausal.logic.exceptions import LogicException
    with pytest.raises(LogicException, match="existence_error"):
        _answers(mod, "d5")


def test_an_int_list_key_is_not_folded_to_bytes(mod):
    from clausal.logic.exceptions import LogicException
    with pytest.raises(LogicException, match=r"type_error\(dict_key"):
        _answers(mod, "d7")


def test_a_char_list_key_is_stored_as_the_carrier(mod):
    assert _answers(mod, "d6") == [("$chars", "ab")]


def test_a_list_key_with_no_hashable_spelling_is_a_type_error(tmp_path):
    from clausal.logic.exceptions import LogicException
    p = tmp_path / "badkey.seam"
    p.write_text('-private([a])\nbad(V) <- (D is {[a, 1]: 1}, V is D[[a, 1]])\n')
    with pytest.raises(LogicException, match=r"type_error\(dict_key"):
        m = load_clausal_module(p)
        _answers(m, "bad")
