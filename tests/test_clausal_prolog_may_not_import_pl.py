"""Clausal Prolog may not import ISO Prolog (operator ruling 2026-10-01).

The dependency direction is ONE-WAY: a ``.pl`` module may import a Clausal
Prolog module, a Clausal Prolog module may NEVER import a ``.pl`` module
(arbitrary ``.pl`` is assumed to use cut; vendored Prolog is converted to
Clausal Prolog).  There is no opt-in.  A ``.seam`` module is a legal
import target for both, and a seam importer is not affected.

The refusal is a load error carrying ``permission_error(access,
prolog_module, M)``, the shape of the Python-target refusal
(``permission_error(access, python_module, M)``).  It looks at the file the
finders PICKED, so a name with a ``.seam`` or Clausal Prolog twin (both win
over ``.pl``) is not refused.

The Clausal Prolog surface has no extension until the extension flip
(``_suffixes.CLAUSAL_PROLOG_SUFFIXES`` is empty), so the refusal is inert
today; these tests SIMULATE the flip by patching the tuples, as
``tests/test_extension_flip_prep.py`` does.
"""
from __future__ import annotations

import importlib
import shutil
import sys

import pytest

from clausal import _suffixes
from clausal import import_hook as ih
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, walk

FLIPPED = {"CLAUSAL_SUFFIXES": (".seam",),
           "CLAUSAL_PROLOG_SUFFIXES": (".clausal",)}

REFUSAL = "permission_error(access, prolog_module, {m})"
REASON = ("Clausal Prolog may not import ISO Prolog (.pl), which may use "
          "cut; convert")


@pytest.fixture
def flip(monkeypatch):
    """Simulate the extension flip: ``.clausal`` is Clausal Prolog."""
    for name, value in FLIPPED.items():
        monkeypatch.setattr(_suffixes, name, value)
    ih._SUFFIX_SALTS.clear()
    yield
    ih._SUFFIX_SALTS.clear()


_PL_LIB = ":- module({m}, [p/1]).\np({v}).\n"
_CP_LIB = ":- module({m}, [p/1]).\np({v}).\n:- end_module({m}).\n"
_SEAM_LIB = "-module({m}, [p(X)])\np({v}),\n"


class Tree:
    """A temporary sys.path entry; every module written is unloaded after."""

    def __init__(self, root, monkeypatch):
        self.root = root
        self.names: list[str] = []
        monkeypatch.syspath_prepend(str(root))

    def write(self, rel: str, text: str):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.parent != self.root:
            init = path.parent / "__init__.py"
            if not init.exists():
                init.write_text("")
            self.names.append(
                str(path.parent.relative_to(self.root)).replace("/", "."))
        path.write_text(text)
        dotted = rel.rsplit(".", 1)[0].replace("/", ".")
        self.names.append(dotted)
        sys.modules.pop(dotted, None)
        return dotted

    def importer(self, name: str, directive: str, *, suffix=".clausal",
                 body="q(X) :- p(X).\n"):
        end = f":- end_module({name}).\n" if suffix == ".clausal" else ""
        return self.write(name + suffix,
                          f":- module({name}, [q/1]).\n:- {directive}.\n"
                          f"{body}{end}")

    def load(self, name: str):
        for p in self.root.rglob("__pycache__"):
            shutil.rmtree(p, ignore_errors=True)
        importlib.invalidate_caches()
        return importlib.import_module(name)

    def close(self):
        for n in self.names:
            sys.modules.pop(n, None)
        for p in self.root.rglob("__pycache__"):
            shutil.rmtree(p, ignore_errors=True)
        importlib.invalidate_caches()


@pytest.fixture
def tree(tmp_path, monkeypatch):
    t = Tree(tmp_path, monkeypatch)
    yield t
    t.close()


def _q(mod, name="q"):
    x = Var()
    return [walk(deref(x)) for _ in call(name, x, module=mod)]


def _refused(tree, name) -> str:
    with pytest.raises((SyntaxError, ImportError)) as ei:
        tree.load(name)
    return str(ei.value)


# ── NO: a Clausal Prolog module importing a .pl module ──


@pytest.mark.parametrize("directive,shown", [
    ("use_module(cpn_pl, [p/1])", "cpn_pl"),
    ("use_module(cpn_pl, [p])", "cpn_pl"),
    ("use_module(cpn_pl)", "cpn_pl"),
    ("use_module('cpn_pl.pl', [p/1])", "cpn_pl"),
    ("use_module(cpn_pk/cpn_sub, [p/1])", "cpn_pk.cpn_sub"),
])
def test_clausal_prolog_refuses_a_pl_import(flip, tree, directive, shown):
    tree.write("cpn_pl.pl", _PL_LIB.format(m="cpn_pl", v=1))
    tree.write("cpn_pk/cpn_sub.pl", _PL_LIB.format(m="cpn_sub", v=2))
    tree.importer("cpn_imp", directive)
    msg = _refused(tree, "cpn_imp")
    assert REFUSAL.format(m=shown) in msg, msg
    assert REASON in msg and "to .clausal" in msg, msg
    # Nothing of the refused module was loaded on the importer's behalf.
    assert "cpn_pl" not in sys.modules and "cpn_pk.cpn_sub" not in sys.modules


def test_a_pl_sibling_inside_a_package_is_refused(flip, tree):
    """A relative path resolves beside the importer first (Scryer)."""
    tree.write("cpn_pkg/helper.pl", _PL_LIB.format(m="helper", v=1))
    tree.write("cpn_pkg/main.clausal",
               ":- module(main, [q/1]).\n:- use_module(helper, [p/1]).\n"
               "q(X) :- p(X).\n:- end_module(main).\n")
    msg = _refused(tree, "cpn_pkg.main")
    assert REFUSAL.format(m="cpn_pkg.helper") in msg, msg


def test_the_translator_refuses_it_the_same_way(flip, tree):
    """The translator never loads Clausal Prolog (the surface is always
    native), but it carries the same Clausal Prolog import rules."""
    from clausal.tools.prolog_to_clausal import (
        PrologTranslationError, prolog_to_clausal)
    tree.write("cpn_tr.pl", _PL_LIB.format(m="cpn_tr", v=1))
    with pytest.raises(PrologTranslationError) as ei:
        prolog_to_clausal(":- module(t, [q/1]).\n"
                          ":- use_module(cpn_tr, [p/1]).\nq(X) :- p(X).\n"
                          ":- end_module(t).\n", surface="clausal_prolog")
    assert REFUSAL.format(m="cpn_tr") in str(ei.value)
    # The same text on the .pl surface translates.
    assert "cpn_tr" in prolog_to_clausal(
        ":- module(t, [q/1]).\n:- use_module(cpn_tr, [p/1]).\n"
        "q(X) :- p(X).\n", surface="pl")


# ── Routes that never reach a .pl today (pinned, both sides of the flip) ──


def test_library_naming_a_pl_module_is_refused_as_unknown(flip, tree):
    """``library(L)`` resolves only to a built-in library, a mapped engine
    module or a ``.seam`` facade: a vendored ``.pl`` is never reached."""
    tree.write("cpn_vend.pl", _PL_LIB.format(m="cpn_vend", v=1))
    tree.importer("cpn_libimp", "use_module(library(cpn_vend), [p/1])")
    msg = _refused(tree, "cpn_libimp")
    assert "library(cpn_vend) is not a library" in msg, msg


def test_ensure_loaded_is_not_a_directive(flip, tree):
    tree.write("cpn_el.pl", _PL_LIB.format(m="cpn_el", v=1))
    tree.importer("cpn_elimp", "ensure_loaded(cpn_el)")
    assert "unknown directive ensure_loaded/1" in _refused(tree, "cpn_elimp")


def test_a_qualified_call_into_a_loaded_pl_module_is_refused(flip, tree):
    """Route 2 of the dialect gate (ruled strict; formerly the positive pin
    ``test_a_qualified_call_into_a_loaded_pl_module_still_runs``).  The
    native front end resolves ``M:G`` at run time, never at load, so a
    Clausal Prolog clause calling ``cpn_q:p(X)`` still LOADS; once other
    code has loaded the ``.pl`` module the CALL raises route 1's term.
    Every run-time route is pinned in ``tests/test_dialect_gate_routes.py``."""
    from clausal.logic.exceptions import LogicException
    tree.write("cpn_q.pl", _PL_LIB.format(m="cpn_q", v=1))
    tree.write("cpn_qimp.clausal",
               ":- module(cpn_qimp, [q/1]).\nq(X) :- cpn_q:p(X).\n"
               ":- end_module(cpn_qimp).\n")
    mod = tree.load("cpn_qimp")
    assert isinstance(mod.__loader__, ih.NativePrologLoader)
    pl = tree.load("cpn_q")         # loaded by someone else
    assert pl.__file__.endswith("cpn_q.pl")
    assert type(pl.__loader__) is ih._prolog_loader_class_for(pl.__file__)
    with pytest.raises(LogicException) as ei:
        _q(mod)
    assert ei.value.term[1] == (
        "permission_error", "access", "prolog_module", "cpn_q")


# ── YES: a Clausal Prolog module importing what it may ──


def test_clausal_prolog_imports_a_seam_module(flip, tree):
    tree.write("cpy_seam.seam", _SEAM_LIB.format(m="cpy_seam", v=1))
    tree.importer("cpy_imp1", "use_module(cpy_seam, [p/1])")
    assert _q(tree.load("cpy_imp1")) == [1]


def test_clausal_prolog_imports_a_clausal_prolog_module(flip, tree):
    tree.write("cpy_cp.clausal", _CP_LIB.format(m="cpy_cp", v=2))
    tree.importer("cpy_imp2", "use_module(cpy_cp, [p/1])")
    mod = tree.load("cpy_imp2")
    assert _q(mod) == [2]
    assert isinstance(sys.modules["cpy_cp"].__loader__, ih.NativePrologLoader)


def test_clausal_prolog_imports_a_library_facade(flip, tree):
    tree.importer("cpy_imp3", "use_module(library(datetime), [days_between/3])",
                  body="q(N) :- days_between(date(2026, 1, 31), "
                       "date(2026, 1, 1), N).\n")
    assert _q(tree.load("cpy_imp3")) == [30]


@pytest.mark.parametrize("twin", [".seam", ".clausal"])
def test_a_name_with_a_twin_beside_its_pl_is_not_refused(flip, tree, twin):
    """.seam > .clausal > .pl for one stem: the twin is what is imported."""
    lib = _SEAM_LIB if twin == ".seam" else _CP_LIB
    tree.write("cpy_tw" + twin, lib.format(m="cpy_tw", v=3))
    tree.write("cpy_tw.pl", _PL_LIB.format(m="cpy_tw", v=4))
    tree.importer("cpy_imp4", "use_module(cpy_tw, [p/1])")
    assert _q(tree.load("cpy_imp4")) == [3]
    assert sys.modules["cpy_tw"].__file__.endswith("cpy_tw" + twin)


# ── .pl importers and the seam: unaffected ──


@pytest.mark.parametrize("target", [".pl", ".clausal"])
def test_a_pl_module_imports_pl_and_clausal_prolog(flip, tree, target):
    lib = _PL_LIB if target == ".pl" else _CP_LIB
    tree.write("ply_lib" + target, lib.format(m="ply_lib", v=5))
    tree.importer("ply_imp", "use_module(ply_lib, [p/1])", suffix=".pl")
    assert _q(tree.load("ply_imp")) == [5]


def test_a_seam_module_still_imports_a_pl_module(flip, tree):
    """The seam is the Python boundary: the ruling leaves it alone."""
    tree.write("sey_pl.pl", _PL_LIB.format(m="sey_pl", v=6))
    tree.write("sey_imp.seam",
               "-import_from(sey_pl, [p])\nq(X) <- p(X),\n")
    assert _q(tree.load("sey_imp")) == [6]


def test_the_flip_is_in_effect_without_patching(tree):
    """No fixture patches the tuples: since the extension flip a real
    ``.clausal`` importer of a ``.pl`` is refused, and a ``.seam`` and a
    ``.pl`` importer of the same ``.pl`` still load."""
    assert _suffixes.CLAUSAL_PROLOG_SUFFIXES == (".clausal",)
    assert _suffixes.CLAUSAL_SUFFIXES == (".seam",)
    tree.write("pre_pl.pl", _PL_LIB.format(m="pre_pl", v=7))
    tree.importer("pre_plimp", "use_module(pre_pl, [p/1])", suffix=".pl")
    tree.write("pre_seamimp.seam",
               "-import_from(pre_pl, [p])\nq(X) <- p(X),\n")
    tree.importer("pre_cpimp", "use_module(pre_pl, [p/1])")
    assert _q(tree.load("pre_plimp")) == [7]
    assert _q(tree.load("pre_seamimp")) == [7]
    assert REFUSAL.format(m="pre_pl") in _refused(tree, "pre_cpimp")