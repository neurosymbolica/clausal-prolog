"""Fix batch E (2026-09-29): residue of the 2026-09-28 engine-bug triage,
re-verified on main 44b358a9.

Each test is a repro turned round to pin the fixed behaviour.
"""
import sys
import textwrap

import pytest

from clausal.import_hook import _load_module


def _load(tmp_path, monkeypatch, name, src, libs=None, ext="seam"):
    """Load *src* as module *name* from *tmp_path*; *libs* are sibling files
    ``{filename: source}`` the module may import."""
    monkeypatch.syspath_prepend(str(tmp_path))
    for fname, lsrc in (libs or {}).items():
        (tmp_path / fname).write_text(textwrap.dedent(lsrc))
        sys.modules.pop(fname.rsplit(".", 1)[0], None)
    path = tmp_path / f"{name}.{ext}"
    path.write_text(textwrap.dedent(src))
    sys.modules.pop(name, None)
    return _load_module(name, str(path))


class TestStructuralEqSeesABoundVariableInsideATerm:
    """todo/structural-eq-misses-a-variable-bound-inside-a-list-2026-09-28:
    the bare ``==`` ground fallback compared a list/cell holding a BOUND
    variable against its value and answered false.  ISO ==/2 (8.4.1.1)
    dereferences every subterm; so do unification and the quoted '=='."""

    SRC = """
        -allow_singletons
        -private([f(_)])
        t1(X) <- (X is [Y], Y is 1, X == [1])
        t2(X) <- (X is ['-'(Y, 2)], Y is 1, X == ['-'(1, 2)])
        t3(X) <- (X is f(Y), Y is 1, X == f(1))
        q1(X) <- (Y is 1, X is [Y], X == [1])
        d1(X) <- (X is {'k': Y}, Y is 1, X == {'k': 1})
        n1(X) <- (X is [Y], Y is 1, X != [1])
        n2(X) <- (X is [Y], Y is 2, X != [1])
        u1(X) <- (X is [Y], X == [1])
        w1(X) <- (X is [Y], Y is 2, X == [1])
        def run(name):
            return [X for X in --call(++name, X)]
    """

    @pytest.mark.parametrize("name", ["t1", "t2", "t3", "q1", "d1", "n2"])
    def test_holds(self, tmp_path, monkeypatch, name):
        mod = _load(tmp_path, monkeypatch, "eq_bound_in_term", self.SRC)
        assert len(mod.run(name)) == 1

    @pytest.mark.parametrize("name", ["n1", "u1", "w1"])
    def test_does_not_hold(self, tmp_path, monkeypatch, name):
        mod = _load(tmp_path, monkeypatch, "eq_bound_in_term", self.SRC)
        assert mod.run(name) == []
