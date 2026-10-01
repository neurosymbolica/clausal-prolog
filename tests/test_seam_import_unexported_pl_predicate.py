"""Operator ruling 2026-10-01: in CLAUSAL code, importing a predicate that a
``.pl`` module DEFINES but does not EXPORT is a load-time error,
``permission_error(access, private_procedure, Name/Arity)``.

Covers a seam ``-import_from(M, [p])`` and its equivalent forms
(``p/N``, ``alias(p, q)``) and a ``.pl`` ``use_module(M, [p/N])``, under
both ``.pl`` front ends.  On 841b6b24 every one of these silently imported
the predicate.

Scryer (``use_module(m, [helper/1])`` with ``helper/1`` defined in ``m``
and not exported) accepts the directive silently and imports nothing, so
the later call ``helper(X)`` raises
``error(existence_error(procedure, helper/1), helper/1)``.  The load-time
``permission_error`` is the operator's provisional shape.

Python code is not affected (no export privacy from Python:
tests/test_pl_module_unexported_from_python.py).
"""
import sys
import textwrap

import pytest

from clausal.import_hook import _load_module

FRONT_ENDS = ("translator", "native")

PM = """\
    :- module(pm, [rate/1, duo/1]).
    rate(X) :- helper(X).
    helper(5).
    duo(1).
    duo(1, 2).
"""

OPEN = """\
    helper(5).
"""

MULTI = """\
    :- module(multi, [p/1, p/2]).
    p(1).
    p(1, 2).
"""

ERR = r"permission_error\(access, private_procedure, {}\)"


@pytest.fixture
def pkg(tmp_path, monkeypatch):
    made = []

    def _make(fe, tag):
        monkeypatch.setenv("CLAUSAL_PL_FRONTEND", fe)
        monkeypatch.syspath_prepend(str(tmp_path))
        root = tmp_path / tag
        root.mkdir()
        (root / "__init__.py").write_text("")
        (root / "pm.pl").write_text(textwrap.dedent(PM))
        (root / "open_pl.pl").write_text(textwrap.dedent(OPEN))
        (root / "multi.pl").write_text(textwrap.dedent(MULTI))
        made.append(tag)

        def load(name, src, ext="seam"):
            path = root / f"{name}.{ext}"
            path.write_text(textwrap.dedent(src).replace("PKG", tag))
            return _load_module(f"{tag}.{name}", str(path))
        return load

    yield _make
    for tag in made:
        for key in [k for k in sys.modules
                    if k == tag or k.startswith(tag + ".")]:
            sys.modules.pop(key, None)


@pytest.mark.parametrize("fe", FRONT_ENDS)
@pytest.mark.parametrize("entry", ["helper", "helper/1", "alias(helper, h)"])
def test_a_seam_import_of_an_unexported_predicate_is_an_error(pkg, fe, entry):
    load = pkg(fe, f"ux_seam_{fe}_{entry.split('/')[0].split('(')[0]}"
               f"{'_ind' if '/' in entry else ''}")
    with pytest.raises(ImportError, match=ERR.format("helper/1")):
        load("imp", f"-import_from(PKG.pm, [{entry}])\n")


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_an_unexported_arity_of_an_exported_name_is_an_error(pkg, fe):
    """``duo/1`` is exported, ``duo/2`` is not: the indicator for the
    private arity is refused, the exported one and the bare name import."""
    load = pkg(fe, f"ux_arity_{fe}")
    with pytest.raises(ImportError, match=ERR.format("duo/2")):
        load("bad", "-import_from(PKG.pm, [duo/2])\n")
    mod = load("ok", """\
        -import_from(PKG.pm, [duo/1])
        def f():
            return [X for X in --duo(X)]
    """)
    assert mod.f() == [1]


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_a_name_exported_at_several_arities_imports_each(pkg, fe):
    """``[p/1, p/2]`` exports both arities (review finding: the export
    list was read one entry per name, so ``p/2`` was refused)."""
    load = pkg(fe, f"ux_multi_{fe}")
    mod = load("ok", """\
        -import_from(PKG.multi, [p/2])
        def f():
            return [(X, Y) for X, Y in --p(X, Y)]
    """)
    assert mod.f() == [(1, 2)]
    mod = load("ok1", "-import_from(PKG.multi, [p/1, p/2])\n")


def _existence(exc_info, indicator):
    from clausal.logic.exceptions import LogicException
    assert isinstance(exc_info.value, LogicException)
    name, arity = indicator.split("/")
    assert exc_info.value.term[1] == (
        "existence_error", "procedure", ("/", name, int(arity)))


@pytest.mark.parametrize("fe", FRONT_ENDS)
@pytest.mark.parametrize("entry, local", [("duo", "duo"),
                                          ("alias(duo, dd)", "dd")])
def test_a_bare_name_exported_at_one_arity_imports_only_that_arity(
        pkg, fe, entry, local):
    """Operator ruling 2026-10-01 (flipped from the pinned gap): a bare
    entry brings ONLY the exported arities.  ``duo/1`` is exported and
    ``duo/2`` is not, so ``duo(X, Y)`` through the bare import is an
    unimported predicate -- existence_error, exactly as through
    ``-import_from(m, [duo/1])``.  It used to reach the private ``duo/2``."""
    from clausal.logic.solve import solve
    from clausal.logic.variables import Var
    load = pkg(fe, f"ux_barepart_{fe}_{local}")
    mod = load("ok", f"""\
        -import_from(PKG.pm, [{entry}])
        t1(X) <- {local}(X)
        t2(X, Y) <- {local}(X, Y)
    """)
    assert len(list(solve(("t1", Var()), module=mod))) == 1
    with pytest.raises(Exception) as ei:
        list(solve(("t2", Var(), Var()), module=mod))
    _existence(ei, f"{local}/2")


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_the_unexported_arity_is_free_for_the_importer(pkg, fe):
    """With only ``duo/1`` imported, the importer's own ``duo/2`` clause is
    a procedure of its own (as with ``[duo/1]``); it used to be refused as
    a write to the exporter's ``duo/2``."""
    from clausal.logic.solve import solve
    from clausal.logic.variables import Var, deref
    load = pkg(fe, f"ux_bareown_{fe}")
    mod = load("ok", """\
        -import_from(PKG.pm, [duo])
        duo(3, 4),
        t2(X, Y) <- duo(X, Y)
    """)
    X, Y = Var(), Var()
    assert [(deref(X), deref(Y))
            for _ in solve(("t2", X, Y), module=mod)] == [(3, 4)]


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_a_bare_name_exported_at_every_defined_arity_imports_each(pkg, fe):
    from clausal.logic.solve import solve
    from clausal.logic.variables import Var
    load = pkg(fe, f"ux_bareall_{fe}")
    mod = load("ok", """\
        -import_from(PKG.multi, [p])
        t1(X) <- p(X)
        t2(X, Y) <- p(X, Y)
    """)
    assert len(list(solve(("t1", Var()), module=mod))) == 1
    assert len(list(solve(("t2", Var(), Var()), module=mod))) == 1


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_a_pl_bare_use_module_entry_does_not_reach_the_private_arity(
        pkg, fe):
    """``use_module(m, [duo])`` in a ``.pl`` importer: ``duo/2`` is not
    reached.  (The native front end imports nothing for a bare entry -- an
    ISO import list holds Name/Arity -- so ``duo/1`` is unreachable there
    too; the translator brings the exported ``duo/1``.)"""
    from clausal.logic.solve import solve
    from clausal.logic.variables import Var
    load = pkg(fe, f"ux_plbare_{fe}")
    mod = load("pb", """\
        :- module(pb, [t2/2]).
        :- use_module(PKG/pm, [duo]).
        t2(X, Y) :- duo(X, Y).
    """, ext="pl")
    with pytest.raises(Exception) as ei:
        list(solve(("t2", Var(), Var()), module=mod))
    _existence(ei, "duo/2")


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_exported_predicates_and_data_names_still_import(pkg, fe):
    load = pkg(fe, f"ux_ok_{fe}")
    mod = load("ok", """\
        -import_from(PKG.pm, [rate, cite])
        def f():
            return [X for X in --rate(X)]
        def atom():
            return cite
    """)
    assert mod.f() == [5]
    assert mod.atom() == "cite"


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_a_pl_file_with_no_module_directive_exports_everything(pkg, fe):
    load = pkg(fe, f"ux_open_{fe}")
    mod = load("ok", """\
        -import_from(PKG.open_pl, [helper])
        def f():
            return [X for X in --helper(X)]
    """)
    assert mod.f() == [5]


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_a_pl_use_module_of_an_unexported_predicate_is_an_error(pkg, fe):
    load = pkg(fe, f"ux_pl_{fe}")
    with pytest.raises(ImportError, match=r"use_module\(.*" + ERR.format(
            "helper/1")):
        load("pu", """\
            :- module(pu, [t/1]).
            :- use_module(PKG/pm, [helper/1]).
            t(X) :- helper(X).
        """, ext="pl")


@pytest.mark.parametrize("fe", FRONT_ENDS)
def test_python_imports_are_not_affected(pkg, fe):
    load = pkg(fe, f"ux_py_{fe}")
    load("ok", "-import_from(PKG.pm, [rate])\n")      # loads pm
    pm = sys.modules[f"ux_py_{fe}.pm"]
    ns = {}
    exec(f"from ux_py_{fe}.pm import helper", ns)
    assert ns["helper"] == pm.helper == getattr(pm, "helper")
