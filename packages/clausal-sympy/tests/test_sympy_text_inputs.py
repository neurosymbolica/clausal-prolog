"""A STRING names a SymPy symbol as an atom does (spec §9.4, "text in").

``sym/2`` gated its name on ``isinstance(name, str)``, so a string -- the
chars carrier ``('$chars', 'x')`` -- failed it; and the term converter
read the carrier as the compound ``'$chars'(x)``, an unknown function.
The probe is written under ``-double_quotes(chars)`` so ``"..."`` IS a
string; each goal has an atom twin that answered before.
"""

from __future__ import annotations

import pytest

pytest.importorskip("sympy", reason="sympy not installed")

from clausal._suffixes import SEAM_SUFFIX
from clausal.import_hook import _load_module
from clausal.logic.solve import call, _deref_walk
from clausal.logic.cells import chars
from clausal.logic.variables import Var


SRC = """\
-double_quotes(chars)
-import_from(sympy, [sym, expand, sym_str])

sym_text(S) <- (sym("x", X), sym_str(X, S))
sym_atom(S) <- (sym('x', X), sym_str(X, S))
expand_text(S) <- (expand(("y" + 1) * 2, E), sym_str(E, S))
expand_atom(S) <- (expand(('y' + 1) * 2, E), sym_str(E, S))
"""


@pytest.fixture(scope="module")
def module(tmp_path_factory):
    src = tmp_path_factory.mktemp("sympytext") / f"sympy_text_probe{SEAM_SUFFIX}"
    src.write_text(SRC, encoding="utf-8")
    return _load_module("sympy_text_probe", str(src)).__dict__["$module"]


def _answer(module, name):
    s = Var()
    got = [_deref_walk(s) for _ in call(name, s, module=module)]
    return got


@pytest.mark.parametrize("name", ["sym_text", "sym_atom"])
def test_sym_takes_a_string_or_an_atom_name(module, name):
    assert _answer(module, name) == [chars("x")]   # sym_str/2 answers a STRING


@pytest.mark.parametrize("name", ["expand_text", "expand_atom"])
def test_a_string_in_an_expression_is_a_symbol(module, name):
    assert _answer(module, name) == [chars("2*y + 2")]
