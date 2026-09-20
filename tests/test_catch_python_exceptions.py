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
- the transliterated structural shape (`ValueError(M)`) is TitleCase in a
  Clausal position and no longer loads: the lint names `++ValueError`.
"""

from __future__ import annotations

import pytest

from clausal.logic.cells import chars_text
from clausal.logic.atoms import mint
import clausal.import_hook  # noqa: F401
from clausal.import_hook import _load_module
from clausal import Var, solve
from clausal.logic.exceptions import LogicException
from clausal.logic.variables import deref


_SRC = """\
-module(cpe, [ raise_ve(X), c_class(R), c_inst(M), c_wrong(R), c_super(R),
               c_logic(R), c_inst_wrong(R),
               c_logic_super(R) ])

raise_ve(X) <- (X is ++int("nope"))

c_class(R) <- (catch(raise_ve(_A), ++ValueError, R is "caught"))
c_inst(M) <- (catch(raise_ve(_B), ++ValueError(M), true))
c_wrong(R) <- (catch(raise_ve(_C), ++TypeError, R is "swallowed"))
c_super(R) <- (catch(raise_ve(_D), ++Exception, R is "caught_super"))
c_logic(R) <- (catch(throw("oops"), ++ValueError, R is "swallowed"))
c_logic_super(R) <- (catch(throw("oops"), ++Exception, R is "swallowed"))
c_inst_wrong(R) <- (catch(raise_ve(_F), ++TypeError(_M2), R is "swallowed"))
"""


@pytest.fixture()
def mod(tmp_path):
    src = tmp_path / "cpe.clausal"
    src.write_text(_SRC)
    return _load_module("cpe", str(src))


def _solutions(goal, out=None, *, module):
    """R-P2-2: a cell goal carries no module and ``solve`` will not guess one
    (module locality), so the caller — which has it in scope — passes it."""
    vals = []
    for _ in solve(goal, module):
        vals.append(deref(out) if out is not None else True)
    return vals


def test_class_catcher_matches_python_exception(mod):
    r = Var()
    assert _solutions(mod.c_class(r), r, module=mod) == [mint("caught")]


def test_instance_catcher_binds_the_real_args(mod):
    m = Var()
    [msg] = _solutions(mod.c_inst(m), m, module=mod)
    assert chars_text(msg) == "invalid literal for int() with base 10: 'nope'"


def test_wrong_class_catcher_stays_selective(mod):
    with pytest.raises(ValueError):
        _solutions(mod.c_wrong(Var()), module=mod)


def test_wrong_instance_catcher_stays_selective(mod):
    with pytest.raises(ValueError):
        _solutions(mod.c_inst_wrong(Var()), module=mod)


def test_superclass_catcher_matches_by_isinstance(mod):
    r = Var()
    assert _solutions(mod.c_super(r), r, module=mod) == [mint("caught_super")]


def test_structural_titlecase_catcher_is_a_syntax_error(tmp_path):
    """The transliterated shape ``ValueError(M)`` cannot be written any more:
    it is TitleCase in a Clausal position, and the error names the escape."""
    src = tmp_path / "cpe_struct.clausal"
    src.write_text(
        "-module(cpe_struct, [raise_ve(X), c_structural(M)])\n"
        "raise_ve(X) <- (X is ++int(\"nope\"))\n"
        "c_structural(M) <- (catch(raise_ve(_E), ValueError(M), true))\n")
    with pytest.raises(SyntaxError, match="reach it as `\\+\\+ValueError`"):
        _load_module("cpe_struct", str(src))


def test_python_catcher_does_not_match_a_logic_ball(mod):
    with pytest.raises(LogicException):
        _solutions(mod.c_logic(Var()), module=mod)


def test_superclass_python_catcher_does_not_match_a_logic_ball(mod):
    # LogicException subclasses Exception, so a bare isinstance check would
    # let ++Exception swallow a logic throw/1 ball (roborev job 18). The ++
    # boundary is Python-only: logic balls keep their own catch-all spelling,
    # catch(G, _, R).
    with pytest.raises(LogicException):
        _solutions(mod.c_logic_super(Var()), module=mod)
