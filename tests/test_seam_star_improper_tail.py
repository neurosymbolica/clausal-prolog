"""A seam star that is a hole-built improper list (fix round 4, 2026-10-13).

``A is [*T], T is foo`` makes A a SegList of one hole, bound to the atom
``foo`` -- a bare ``str`` since atoms-as-str; text is the chars carrier.
``R is [x, *A]`` then built the chars ``"xfoo"``: the list-pattern twins
read the bare str the star walked to as text.  It is the improper list
``[x|foo]`` (D50), as ``T is foo, R is [x, *T]`` already was.

``R is [*A, x]`` with A improper failed silently; there is no such term, so
it is ``type_error(list, A)``.
"""

from __future__ import annotations

import itertools

import pytest

from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.terms import term_writeq
from clausal.testing import load_clausal_module

_N = itertools.count()

SEAM = """\
-private([x, b, foo])
m1(R) <- (A is [*T], T is foo, R is [x, *A])
m2(R) <- (T is foo, A is [*T], R is [x, *A])
m3(R) <- (A is [*T], T is 1, R is [x, *A])
m4(R) <- (A is [*T], R is [x, *A], T is foo)
m5(R) <- (A is [*T], T is foo, R is A)
m6(R) <- (A is [b, *T], T is foo, R is [x, *A])
m7(P) <- (A is [b, *T], T is foo, R is [*A, x], P is R)
m8(P) <- (T is foo, A is [b, *T], R is [*A, x], P is R)
"""


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    d = tmp_path_factory.mktemp("seam_star_improper")
    p = d / f"_seam_star_improper{next(_N)}.seam"
    p.write_text(SEAM)
    return load_clausal_module(str(p))


def _first(mod, name):
    r = Var()
    for _ in call(name, r, module=mod):
        return term_writeq(deref(r))
    return None


@pytest.mark.parametrize("name, out", [
    ("m1", "[x|foo]"), ("m2", "[x|foo]"), ("m3", "[x|1]"), ("m4", "[x|foo]"),
    ("m5", "foo"), ("m6", "[x,b|foo]"),
])
def test_a_hole_only_star_bound_to_an_atom_is_the_tail(mod, name, out):
    assert _first(mod, name) == out


@pytest.mark.parametrize("name", ["m7", "m8"])
def test_an_improper_star_before_an_element_raises(mod, name):
    with pytest.raises(LogicException) as exc:
        _first(mod, name)
    formal = exc.value.term[1]
    assert formal[:2] == ("type_error", "list"), exc.value.term
    assert term_writeq(formal[2]) == "[b|foo]", exc.value.term
