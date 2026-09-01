"""`++` catchers: match the real Python exception object, not a transliteration.

`python_error_term(exc)` turns a stray Python exception into
`Compound(type(exc).__name__, (str(exc),))` for structural matching — but the
object itself was unreachable, so `catch(G, ++ValueError, R)` (the escape the
language already has for "this is a Python thing") could never match, and the
only working catcher was a bare CamelCase functor — which ISO reads as a
VARIABLE, silently widening a specific catcher to a catch-all under
translation (todo/error-bridge-transliterates-python-exceptions-instead-of-
using-plus-plus.md).

Contract pinned here:
- a catcher that evaluates to an exception CLASS matches by `isinstance`
  (so `++Exception` catches a `ValueError` — Python semantics, subclasses in);
- a catcher that evaluates to an exception INSTANCE (`++ValueError(M)`)
  matches by isinstance on its type and unifies `catcher.args` against
  `exc.args` — binding `M` to the real message;
- SELECTIVITY: a `++TypeError` catcher does NOT swallow a `ValueError`, and a
  `++`-catcher does NOT match a logic `throw/1` ball;
- the transliterated structural shape (`ValueError(M)`) keeps working.
"""

from __future__ import annotations

import pytest

import clausal.import_hook  # noqa: F401
from clausal.import_hook import _load_module
from clausal import Var, solve
from clausal.logic.exceptions import LogicException
from clausal.logic.variables import deref


_SRC = """\
-module(cpe, [ raise_ve(X), c_class(R), c_inst(M), c_wrong(R), c_super(R),
               c_structural(M), c_logic(R), c_inst_wrong(R) ])

raise_ve(X) <- (X is ++int("nope"))

c_class(R) <- (catch(raise_ve(_A), ++ValueError, R is "caught"))
c_inst(M) <- (catch(raise_ve(_B), ++ValueError(M), true))
c_wrong(R) <- (catch(raise_ve(_C), ++TypeError, R is "swallowed"))
c_super(R) <- (catch(raise_ve(_D), ++Exception, R is "caught_super"))
c_structural(M) <- (catch(raise_ve(_E), ValueError(M), true))
c_logic(R) <- (catch(throw("oops"), ++ValueError, R is "swallowed"))
c_inst_wrong(R) <- (catch(raise_ve(_F), ++TypeError(_M2), R is "swallowed"))
"""


@pytest.fixture()
def mod(tmp_path):
    src = tmp_path / "cpe.clausal"
    src.write_text(_SRC)
    return _load_module("cpe", str(src))


def _solutions(goal, out=None):
    vals = []
    for _ in solve(goal):
        vals.append(deref(out) if out is not None else True)
    return vals


def test_class_catcher_matches_python_exception(mod):
    r = Var()
    assert _solutions(mod.c_class(r), r) == ["caught"]


def test_instance_catcher_binds_the_real_args(mod):
    m = Var()
    [msg] = _solutions(mod.c_inst(m), m)
    assert msg == "invalid literal for int() with base 10: 'nope'"


def test_wrong_class_catcher_stays_selective(mod):
    with pytest.raises(ValueError):
        _solutions(mod.c_wrong(Var()))


def test_wrong_instance_catcher_stays_selective(mod):
    with pytest.raises(ValueError):
        _solutions(mod.c_inst_wrong(Var()))


def test_superclass_catcher_matches_by_isinstance(mod):
    r = Var()
    assert _solutions(mod.c_super(r), r) == ["caught_super"]


def test_structural_shape_still_matches(mod):
    m = Var()
    [msg] = _solutions(mod.c_structural(m), m)
    assert msg == "invalid literal for int() with base 10: 'nope'"


def test_python_catcher_does_not_match_a_logic_ball(mod):
    with pytest.raises(LogicException):
        _solutions(mod.c_logic(Var()))
