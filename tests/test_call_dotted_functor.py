"""solve.call with a DOTTED functor answers what the compiled call answers.

todo/name-arity-branch-residual-lows-2026-09-24.md item 1:
``call("alow.numlist", 3, L, module=I)`` refused ("'alow.numlist'/2 is not
defined") while a compiled ``alow.numlist(3, L)`` in the same module
answered [1, 2, 3] (alow has numlist/1 only, so arity 2 is the builtin).
"""
import pytest

from clausal.logic.solve import _deref_walk, call, solve
from clausal.logic.variables import Var
from clausal.predicate_diagnostics import PredicateNotFoundError
from tests._suffix import SEAM


@pytest.fixture
def importer(tmp_path, monkeypatch):
    import sys
    from clausal.import_hook import _load_module
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / f"cdf_alow{SEAM}").write_text(
        "-module(cdf_alow, [numlist/1])\n-private([x])\nnumlist(x),\n")
    p = tmp_path / f"cdf_alowi{SEAM}"
    p.write_text("-module(cdf_alowi, [t/1])\n-import_module(cdf_alow)\n"
                 "t(L) <- cdf_alow.numlist(3, L)\n")
    yield _load_module("cdf_alowi", str(p))
    for k in ("cdf_alow", "cdf_alowi"):
        sys.modules.pop(k, None)


def test_dotted_call_matches_the_compiled_call(importer):
    L = Var()
    compiled = [_deref_walk(L) for _ in solve(("t", L), importer)]
    L = Var()
    direct = [_deref_walk(L) for _ in call("cdf_alow.numlist", 3, L,
                                           module=importer)]
    assert compiled == direct == [[1, 2, 3]]


def test_dotted_call_at_the_owners_own_arity(importer):
    L = Var()
    assert [_deref_walk(L) for _ in call("cdf_alow.numlist", L,
                                         module=importer)] == ["x"]


def test_an_unknown_dotted_name_still_refuses(importer):
    with pytest.raises(PredicateNotFoundError):
        list(call("cdf_alow.nosuch", 3, module=importer))
