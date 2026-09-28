"""An f-string in a clause is a STRING (ruling R2, 2026-09-28).

``"..."`` is the chars carrier under the default ``-double_quotes`` mode, and
an f-string is the same kind of term: text, not a symbol.  It used to be the
bare Python ``str`` the f-string evaluates to -- an ATOM since the
atoms-as-str flip.  Under ``-double_quotes(atom)`` it follows the module's
mode and is the atom, as ``"..."`` is.
"""
import sys
import textwrap

from clausal.import_hook import _load_module
from clausal.logic.cells import chars


def _load(tmp_path, monkeypatch, name, src):
    monkeypatch.syspath_prepend(str(tmp_path))
    path = tmp_path / f"{name}.seam"
    path.write_text(textwrap.dedent(src))
    sys.modules.pop(name, None)
    return _load_module(name, str(path))


def test_fstring_in_a_clause_body_is_a_string(tmp_path, monkeypatch):
    mod = _load(tmp_path, monkeypatch, "fstr_body", """
        msg(M) <- (M is f"total {3}")
        greet(N, M) <- (M is f"hello {N}")
        same <- (msg(M), M is "total 3")
        def run():
            return [M for M in --msg(M)]
        def run2():
            return [M for M in --greet(world, M)]
        def run3():
            if --same:
                return True
            return False
    """.replace("world", "'world'"))
    assert mod.run() == [chars("total 3")]
    assert mod.run2() == [chars("hello world")]
    # the same term a "..." literal is
    assert mod.run3() is True


def test_fstring_as_an_argument_is_a_string(tmp_path, monkeypatch):
    mod = _load(tmp_path, monkeypatch, "fstr_arg", """
        label(X, f"n={X}"),
        def run():
            return [L for L in --label(7, L)]
        def is_string():
            if --(label(7, L), string(L)):
                return True
            return False
    """)
    assert mod.run() == [chars("n=7")]
    assert mod.is_string() is True


def test_fstring_under_double_quotes_atom_is_the_atom(tmp_path, monkeypatch):
    mod = _load(tmp_path, monkeypatch, "fstr_atom", """
        -double_quotes(atom)
        msg(M) <- (M is f"total {3}")
        def run():
            return [M for M in --msg(M)]
    """)
    assert mod.run() == ["total 3"]


def test_write_text_prints_an_fstring(tmp_path, monkeypatch, capsys):
    mod = _load(tmp_path, monkeypatch, "fstr_write", """
        show(X) <- writeln_text(f"X is {X}")
        def run():
            if --show(4):
                return True
            return False
    """)
    assert mod.run() is True
    assert capsys.readouterr().out == "X is 4\n"
