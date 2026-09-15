"""``++expr`` converts its Python value to functor-first form on the way in.

Ruled 2026-09-15. A value crossing from Python into a term arrives as a TERM
without the author converting it by hand -- which is the mechanism that makes
every future crossing correct by construction, rather than each one being
remembered.

Covers both thunk kinds: an f-string returns a ``str``, a scalar, so it passes
through untouched and needs no separate path.
"""
import datetime
import os
import tempfile
from decimal import Decimal

import pytest

from clausal.import_hook import _load_module
from clausal import Var
from clausal.logic.seam import once_bind, export

SRC = """-module({name}, [ret, pair, fstr])
import datetime
ret(++datetime.date(2023, 6, 1)),
pair(++(1, 2)),
fstr(++f"plain"),
"""


@pytest.fixture(scope="module")
def mod():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "esc.clausal")
    with open(p, "w") as fh:
        fh.write(SRC.format(name="esc"))
    return _load_module("esc", p)


def _one(mod, name):
    V = Var()
    assert once_bind((name, V), mod.__dict__), f"{name} failed"
    return export(V)


def test_a_python_date_from_an_escape_arrives_as_a_term(mod):
    assert _one(mod, "ret") == ("date", 2023, 6, 1)


def test_a_python_tuple_from_an_escape_arrives_as_DATA(mod):
    """The documented hazard's other side: a bare Python tuple is data, and
    now says so, instead of being read as the compound ``1(2)``."""
    assert _one(mod, "pair") == ("()", 1, 2)


def test_an_fstring_thunk_is_unaffected(mod):
    """It returns a str, a scalar, so the same hook is a no-op for it."""
    assert _one(mod, "fstr") == "plain"
