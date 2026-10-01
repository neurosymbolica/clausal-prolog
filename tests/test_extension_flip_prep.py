"""The extension flip is a change of the suffix tuples in ``_suffixes.py``.

At the flip ``CLAUSAL_SUFFIXES`` becomes ``(".seam",)`` and
``CLAUSAL_PROLOG_SUFFIXES`` becomes ``(".clausal",)``.  Everything else the
flip needs is already in code paths that read those tuples at each call, so
these tests SIMULATE the flip by patching the tuples and check:

* the bytecode cache key of a ``.clausal`` file changes with its surface, so
  a seam ``.pyc`` is never served for a Clausal Prolog file;
* a Clausal Prolog file loads through the NATIVE front end whatever
  ``CLAUSAL_PL_FRONTEND`` says (the translator is end-of-life there);
* ``PrologFinder`` and ``PredicateFinder`` follow the tuples.

Before the flip every one of these paths is inert (the Clausal Prolog tuple
is empty); the unpatched assertions pin that.
"""
from __future__ import annotations

import hashlib
import importlib
import os
import shutil
import sys

import pytest

from clausal import _suffixes
from clausal import import_hook as ih
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, walk

FLIPPED = {"CLAUSAL_SUFFIXES": (".seam",),
           "CLAUSAL_PROLOG_SUFFIXES": (".clausal",)}


@pytest.fixture
def flip(monkeypatch):
    """Simulate the extension flip: ``.clausal`` is Clausal Prolog."""
    for name, value in FLIPPED.items():
        monkeypatch.setattr(_suffixes, name, value)
    ih._SUFFIX_SALTS.clear()
    yield
    ih._SUFFIX_SALTS.clear()


def _old_salt(suffix):
    """The key every suffix had before the salt was keyed on the surface."""
    if suffix == ".clausal":
        return 0
    d = hashlib.blake2b(b"clausal-source-suffix:" + suffix.encode(),
                        digest_size=4)
    return int.from_bytes(d.digest(), "big") or 1


def _answers(mod, name="which"):
    x = Var()
    return [walk(deref(x)) for _ in call(name, x, module=mod)]


# ── (a) the cache key follows the surface ──


def test_existing_cache_keys_are_unchanged_before_the_flip():
    for suffix in (".clausal", ".seam", ".pl"):
        assert ih._suffix_salt("m" + suffix) == _old_salt(suffix), suffix


def test_the_flip_changes_the_clausal_key(flip):
    salt = ih._suffix_salt("m.clausal")
    assert salt != 0, "a Clausal Prolog file must not get the seam key"
    assert salt not in (ih._suffix_salt("m.seam"), ih._suffix_salt("m.pl"))
    # The seam and .pl keys are untouched by the flip.
    assert ih._suffix_salt("m.seam") == _old_salt(".seam")
    assert ih._suffix_salt("m.pl") == _old_salt(".pl")


def test_a_seam_pyc_is_not_served_for_the_same_file_after_the_flip(
        tmp_path, monkeypatch):
    """Same path, same size, same mtime_ns: only the surface changes."""
    src = tmp_path / "efkey.clausal"
    src.write_text("which(1),\n")                 # seam
    try:
        assert _answers(ih._load_module("efkey_seam", str(src))) == [1]
        assert list((tmp_path / "__pycache__").glob("efkey.*.pyc"))
        st = os.stat(src)
        src.write_text("which(2).\n")             # Prolog, same size
        os.utime(src, ns=(st.st_atime_ns, st.st_mtime_ns))
        assert os.stat(src).st_size == st.st_size
        for name, value in FLIPPED.items():
            monkeypatch.setattr(_suffixes, name, value)
        ih._SUFFIX_SALTS.clear()
        mod = ih._load_module("efkey_cp", str(src))
        assert isinstance(mod.__spec__.loader, ih.NativePrologLoader)
        assert _answers(mod) == [2]
    finally:
        ih._SUFFIX_SALTS.clear()
        for n in ("efkey_seam", "efkey_cp"):
            sys.modules.pop(n, None)
        shutil.rmtree(tmp_path / "__pycache__", ignore_errors=True)


# ── (b) Clausal Prolog always loads natively ──


@pytest.mark.parametrize("frontend", ["translator", "native", ""])
def test_clausal_prolog_ignores_the_pl_frontend_switch(flip, monkeypatch,
                                                       frontend):
    monkeypatch.setenv(ih.PL_FRONTEND_ENV, frontend)
    assert ih._prolog_loader_class_for("m.clausal") is ih.NativePrologLoader
    expected = (ih.NativePrologLoader if frontend == "native"
                else ih.PrologLoader)
    assert ih._prolog_loader_class_for("m.pl") is expected


def test_before_the_flip_clausal_is_not_prolog(monkeypatch):
    monkeypatch.setenv(ih.PL_FRONTEND_ENV, "translator")
    assert not _suffixes.is_prolog_source("m.clausal")
    assert _suffixes.prolog_suffixes() == (".pl",)
    assert ih._prolog_loader_class_for("m.pl") is ih.PrologLoader


@pytest.fixture
def tree(tmp_path, monkeypatch):
    (tmp_path / "efcp.clausal").write_text(
        ":- module(efcp, [which/1]).\nwhich(3).\n:- end_module(efcp).\n")
    (tmp_path / "efseam.seam").write_text("which(4),\n")
    monkeypatch.setattr(sys, "path", [str(tmp_path)] + sys.path)
    importlib.invalidate_caches()
    yield tmp_path
    for n in ("efcp", "efseam"):
        sys.modules.pop(n, None)
    shutil.rmtree(tmp_path / "__pycache__", ignore_errors=True)
    importlib.invalidate_caches()


def test_the_finder_routes_clausal_prolog_to_the_native_loader(
        flip, tree, monkeypatch):
    monkeypatch.setenv(ih.PL_FRONTEND_ENV, "translator")
    spec = ih.PredicateFinder().find_spec("efcp", path=[str(tree)])
    assert isinstance(spec.loader, ih.NativePrologLoader)
    spec = ih.PredicateFinder().find_spec("efseam", path=[str(tree)])
    assert isinstance(spec.loader, ih.PredicateLoader)
    assert _answers(importlib.import_module("efcp")) == [3]
    assert _answers(importlib.import_module("efseam")) == [4]


def test_before_the_flip_the_finder_reads_clausal_as_seam(tree):
    spec = ih.PredicateFinder().find_spec("efcp", path=[str(tree)])
    assert type(spec.loader) is ih.PredicateLoader


# ── (c) PrologFinder follows the tuple ──


def test_prolog_finder_extensions_follow_the_tuple(flip, tree):
    assert ih.PrologFinder()._suffixes() == (".clausal", ".pl")
    spec = ih.PrologFinder().find_spec("efcp", path=[str(tree)])
    assert isinstance(spec.loader, ih.NativePrologLoader)
    assert ih.PrologFinder().find_spec("efseam", path=[str(tree)]) is None


def test_prolog_finder_before_the_flip(tree):
    assert ih.PrologFinder._extensions == (".pl",)
    assert ih.PrologFinder().find_spec("efcp", path=[str(tree)]) is None


# ── clausal-fmt / clausal-rewrite refuse Prolog-syntax files ──

_PROLOG = ":- module(efp, [p/1]).\np(1).\n:- end_module(efp).\n"
_SEAM = "p(1),\n"


@pytest.mark.parametrize("tool", ["fmt", "rewrite"])
def test_after_the_flip_the_seam_tools_refuse_clausal_prolog(
        flip, tmp_path, capsys, tool):
    from clausal.fmt.cli import main as fmt_main
    from clausal.rewrite.cli import main as rewrite_main
    main = fmt_main if tool == "fmt" else rewrite_main
    cp = tmp_path / "efp.clausal"
    cp.write_text(_PROLOG)
    assert main([str(cp)]) == 2
    err = capsys.readouterr().err
    assert "refused: this is Clausal Prolog source" in err
    assert f"clausal-{tool} handles seam (.seam) source only" in err
    assert cp.read_text() == _PROLOG                  # untouched
    if tool == "rewrite":
        # Its shipped rules are themselves seam files still spelled
        # .clausal: under a simulated flip they cannot load until the
        # rename sweep moves them, so only the refusal is checked here.
        return
    # A directory walk does not pick the Prolog file up at all.
    seam = tmp_path / "efs.seam"
    seam.write_text(_SEAM)
    assert main(["--check", str(tmp_path)]) == 0
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("tool", ["fmt", "rewrite"])
def test_the_seam_tools_refuse_a_named_pl_file(tmp_path, capsys, tool):
    from clausal.fmt.cli import main as fmt_main
    from clausal.rewrite.cli import main as rewrite_main
    main = fmt_main if tool == "fmt" else rewrite_main
    pl = tmp_path / "efp.pl"
    pl.write_text(_PROLOG)
    assert main([str(pl)]) == 2
    assert "refused: this is Prolog source" in capsys.readouterr().err
    assert pl.read_text() == _PROLOG


def test_before_the_flip_the_seam_tools_take_clausal(tmp_path, capsys):
    from clausal.fmt.cli import main as fmt_main
    src = tmp_path / "efs.clausal"
    src.write_text(_SEAM)
    assert fmt_main(["--check", str(src)]) == 0
    assert capsys.readouterr().err == ""


def test_translate_reads_clausal_prolog_as_prolog(flip):
    from clausal.tools.translate import _detect_direction
    assert _detect_direction("m.clausal", None) == "prolog_to_clausal"
    assert _detect_direction("m.seam", None) == "clausal_to_prolog"


# ── a seam/.pl twin: a Prolog importer gets the SEAM module ──
#
# A name that exists as both ``name.seam`` and ``name.pl`` in one directory
# (a helper library with a Scryer twin) resolves to the ``.seam`` for every
# importer: the finder asks each path entry for the seam group BEFORE the
# Prolog group, and that order is the same before and after the flip.

_HELPER_SEAM = "-module(helperlib, [p(X)])\np(1),\n"
_HELPER_PL = ":- module(helperlib, [p/1]).\np(2).\n"
_IMPORTER = (":- module({m}, [q/1]).\n:- use_module(helperlib, [p/1]).\n"
             "q(X) :- p(X).\n{end}")
_TWIN_NAMES = ("helperlib", "efimp_cp", "efimp_pl")


@pytest.fixture
def twin(tmp_path, monkeypatch):
    (tmp_path / "helperlib.seam").write_text(_HELPER_SEAM)
    (tmp_path / "helperlib.pl").write_text(_HELPER_PL)
    (tmp_path / "efimp_cp.clausal").write_text(
        _IMPORTER.format(m="efimp_cp", end=":- end_module(efimp_cp).\n"))
    (tmp_path / "efimp_pl.pl").write_text(
        _IMPORTER.format(m="efimp_pl", end=""))
    for n in _TWIN_NAMES:
        sys.modules.pop(n, None)
    monkeypatch.setattr(sys, "path", [str(tmp_path)] + sys.path)
    importlib.invalidate_caches()
    yield tmp_path
    for n in _TWIN_NAMES:
        sys.modules.pop(n, None)
    shutil.rmtree(tmp_path / "__pycache__", ignore_errors=True)
    importlib.invalidate_caches()


def _group_suffixes():
    return [tuple(s) for s, _ in ih.PredicateFinder()._suffix_groups()]


def test_the_finder_asks_for_seam_before_prolog_before_the_flip():
    assert _group_suffixes() == [(".clausal", ".seam"), (".pl",)]


def test_the_finder_asks_for_seam_before_prolog_after_the_flip(flip):
    assert _group_suffixes() == [(".seam",), (".clausal", ".pl")]


def test_the_finder_picks_the_seam_twin(twin):
    spec = ih.PredicateFinder().find_spec("helperlib", path=[str(twin)])
    assert spec.origin.endswith("helperlib.seam")


@pytest.mark.parametrize("frontend", ["native", "translator"])
def test_a_pl_importer_of_a_twin_gets_the_seam_module(twin, monkeypatch,
                                                      frontend):
    monkeypatch.setenv(ih.PL_FRONTEND_ENV, frontend)
    assert _answers(importlib.import_module("efimp_pl"), "q") == [1]
    assert sys.modules["helperlib"].__file__.endswith("helperlib.seam")


@pytest.mark.parametrize("frontend", ["native", "translator"])
def test_a_clausal_prolog_importer_of_a_twin_gets_the_seam_module(
        flip, twin, monkeypatch, frontend):
    monkeypatch.setenv(ih.PL_FRONTEND_ENV, frontend)
    mod = importlib.import_module("efimp_cp")
    assert isinstance(mod.__spec__.loader, ih.NativePrologLoader)
    assert _answers(mod, "q") == [1]
    assert sys.modules["helperlib"].__file__.endswith("helperlib.seam")


@pytest.mark.parametrize("frontend", ["native", "translator"])
def test_after_the_flip_a_pl_importer_of_a_twin_still_gets_the_seam_module(
        flip, twin, monkeypatch, frontend):
    monkeypatch.setenv(ih.PL_FRONTEND_ENV, frontend)
    assert _answers(importlib.import_module("efimp_pl"), "q") == [1]
    assert sys.modules["helperlib"].__file__.endswith("helperlib.seam")


# ── docs: ```seam is the seam fence, ```clausal its alias for now ──


def test_the_doc_checker_sees_both_seam_fences(tmp_path):
    from clausal.tools.doc_snippet_check import (
        SEAM_FENCE_RE, check_no_raw_untested_blocks)
    page = tmp_path / "page.md"
    page.write_text("```seam\np(1),\n```\n\n```clausal\nq(1),\n```\n\n"
                    "```seam\nthis is not ( seam\n```\n\n"
                    "```clausal\nnor ( is this\n```\n\n"
                    "```prolog\np(1).\n```\n")
    assert len(SEAM_FENCE_RE.findall(page.read_text())) == 4
    bad = check_no_raw_untested_blocks(tmp_path)
    assert [v.split()[0] for v in bad] == ["page.md:9", "page.md:13"], bad


# ── the private-procedure ImportError names the importer's own directive ──


def test_a_clausal_prolog_importer_is_told_use_module(flip, tmp_path,
                                                      monkeypatch):
    # The private-procedure check guards imports from a .pl module.
    (tmp_path / "efprivlib.pl").write_text(
        ":- module(efprivlib, [p/1]).\np(1).\nhidden(2).\n")
    (tmp_path / "efprivimp.clausal").write_text(
        ":- module(efprivimp, [q/1]).\n"
        ":- use_module(efprivlib, [hidden/1]).\n"
        "q(X) :- hidden(X).\n:- end_module(efprivimp).\n")
    monkeypatch.setattr(sys, "path", [str(tmp_path)] + sys.path)
    importlib.invalidate_caches()
    try:
        with pytest.raises(ImportError) as ei:
            importlib.import_module("efprivimp")
        assert "private_procedure" in str(ei.value)
        assert "use_module(efprivlib" in str(ei.value)
        assert "-import_from" not in str(ei.value)
    finally:
        for n in ("efprivlib", "efprivimp"):
            sys.modules.pop(n, None)
        shutil.rmtree(tmp_path / "__pycache__", ignore_errors=True)


# ── a Clausal Prolog / .pl twin: the .clausal wins (operator ruling) ──


@pytest.fixture
def cp_twin(tmp_path, monkeypatch):
    (tmp_path / "eftwinlib.clausal").write_text(
        ":- module(eftwinlib, [p/1]).\np(1).\n:- end_module(eftwinlib).\n")
    (tmp_path / "eftwinlib.pl").write_text(
        ":- module(eftwinlib, [p/1]).\np(2).\n")
    body = ":- use_module(eftwinlib, [p/1]).\nq(X) :- p(X).\n"
    (tmp_path / "eftwin_cp.clausal").write_text(
        ":- module(eftwin_cp, [q/1]).\n" + body
        + ":- end_module(eftwin_cp).\n")
    (tmp_path / "eftwin_pl.pl").write_text(
        ":- module(eftwin_pl, [q/1]).\n" + body)
    names = ("eftwinlib", "eftwin_cp", "eftwin_pl")
    for n in names:
        sys.modules.pop(n, None)
    monkeypatch.setattr(sys, "path", [str(tmp_path)] + sys.path)
    importlib.invalidate_caches()
    yield tmp_path
    for n in names:
        sys.modules.pop(n, None)
    shutil.rmtree(tmp_path / "__pycache__", ignore_errors=True)


def test_the_finders_pick_clausal_prolog_over_pl(flip, cp_twin):
    for finder in (ih.PredicateFinder(), ih.PrologFinder()):
        spec = finder.find_spec("eftwinlib", path=[str(cp_twin)])
        assert spec.origin.endswith("eftwinlib.clausal")
        assert isinstance(spec.loader, ih.NativePrologLoader)


@pytest.mark.parametrize("frontend", ["native", "translator"])
@pytest.mark.parametrize("importer", ["eftwin_cp", "eftwin_pl"])
def test_any_importer_of_a_clausal_pl_twin_gets_the_clausal(
        flip, cp_twin, monkeypatch, frontend, importer):
    monkeypatch.setenv(ih.PL_FRONTEND_ENV, frontend)
    assert _answers(importlib.import_module(importer), "q") == [1]
    assert sys.modules["eftwinlib"].__file__.endswith("eftwinlib.clausal")
