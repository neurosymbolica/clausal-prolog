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
    assert ih.PrologFinder()._suffixes() == (".pl", ".clausal")
    spec = ih.PrologFinder().find_spec("efcp", path=[str(tree)])
    assert isinstance(spec.loader, ih.NativePrologLoader)
    assert ih.PrologFinder().find_spec("efseam", path=[str(tree)]) is None


def test_prolog_finder_before_the_flip(tree):
    assert ih.PrologFinder._extensions == (".pl",)
    assert ih.PrologFinder().find_spec("efcp", path=[str(tree)]) is None
