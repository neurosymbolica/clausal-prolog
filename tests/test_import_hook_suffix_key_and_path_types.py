"""Import-hook edges:

* the bytecode cache key folds in the source SUFFIX: a same-directory
  ``twin.pl`` and ``twin.clausal`` write the same ``__pycache__`` file, and
  with equal size and ``mtime_ns`` each was served the other's bytecode;
* ``_load_module`` / ``_load_prolog_module`` take a ``pathlib.Path`` on a
  WARM cache too (importlib's cache-hit path raised a TypeError);
* a non-str ``sys.path`` entry is skipped, as CPython's PathFinder skips it,
  instead of raising a TypeError out of the finder.
"""
from __future__ import annotations

import importlib
import os
import pathlib
import shutil
import sys

import pytest

from clausal import import_hook as ih
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, walk
from tests._suffix import SEAM

FRONTENDS = ("native", "translator")


@pytest.fixture(params=FRONTENDS)
def frontend(request, monkeypatch):
    monkeypatch.setenv(ih.PL_FRONTEND_ENV, request.param)
    return request.param


def _answers(mod, name):
    x = Var()
    return [walk(deref(x)) for _ in call(name, x, module=mod)]


def _evict(*names):
    for n in names:
        sys.modules.pop(n, None)


def test_same_stem_pl_and_clausal_do_not_share_bytecode(frontend, tmp_path):
    pl = tmp_path / "sfxtwin.pl"
    cl = tmp_path / f"sfxtwin{SEAM}"
    pl.write_text("which(2).%\n")
    cl.write_text("which(1), \n")
    assert pl.stat().st_size == cl.stat().st_size
    st = pl.stat()
    os.utime(cl, ns=(st.st_atime_ns, st.st_mtime_ns))
    try:
        ih._load_prolog_module("sfxtwin_pl", str(pl))
        assert os.listdir(tmp_path / "__pycache__")   # the .pl wrote a .pyc
        m = ih._load_module("sfxtwin_cl", str(cl))
        assert _answers(m, "which") == [1]
        m = ih._load_prolog_module("sfxtwin_pl2", str(pl))
        assert _answers(m, "which") == [2]
    finally:
        _evict("sfxtwin_pl", "sfxtwin_cl", "sfxtwin_pl2")
        shutil.rmtree(tmp_path / "__pycache__", ignore_errors=True)


def test_the_clausal_key_is_unchanged(tmp_path):
    """Since the extension flip a .clausal file is Clausal Prolog: its key
    is a NONZERO salt of its own (never the 0 a seam .clausal had), so a
    pre-flip seam .pyc is never served for it; .seam and .pl keys differ."""
    src = tmp_path / "sfxkey.clausal"
    src.write_text("f(1).\n")
    salt = ih._suffix_salt(str(src))
    assert salt != 0
    assert salt not in (ih._suffix_salt("a.seam"), ih._suffix_salt("a.pl"))
    stats = ih.PredicateLoader("sfxkey", str(src)).path_stats(str(src))
    assert stats["mtime"] == (os.stat(src).st_mtime_ns
                              ^ ih._effective_bytecode_tag()
                              ^ salt) & 0xFFFFFFFF
    assert ih._suffix_salt("a.seam") not in (0, ih._suffix_salt("a.pl"))


@pytest.mark.parametrize("suffix,text", [(SEAM, "which(1),\n"),
                                         (".pl", "which(1).\n")])
def test_load_module_takes_a_path_on_a_warm_cache(frontend, tmp_path,
                                                  suffix, text):
    p = pathlib.Path(tmp_path / f"sfxpath{suffix}")
    p.write_text(text)
    try:
        assert _answers(ih._load_module("sfxpath_1", p), "which") == [1]
        assert _answers(ih._load_module("sfxpath_2", p), "which") == [1]
        if suffix == ".pl":
            m = ih._load_prolog_module("sfxpath_3", p)
            assert _answers(m, "which") == [1]
    finally:
        _evict("sfxpath_1", "sfxpath_2", "sfxpath_3")
        shutil.rmtree(tmp_path / "__pycache__", ignore_errors=True)


@pytest.mark.parametrize("bad", [None, b"/nonexistent-bytes-entry", 7,
                                 pathlib.Path("/nonexistent-path-entry")])
def test_a_non_str_sys_path_entry_is_skipped(tmp_path, bad):
    (tmp_path / f"sfxodd{SEAM}").write_text("which(3),\n")
    saved = list(sys.path)
    sys.path[:] = [bad, str(tmp_path)] + saved
    importlib.invalidate_caches()
    try:
        _evict("sfxodd")
        m = importlib.import_module("sfxodd")
        assert _answers(m, "which") == [3]
    finally:
        sys.path[:] = saved
        _evict("sfxodd")
        shutil.rmtree(tmp_path / "__pycache__", ignore_errors=True)
        importlib.invalidate_caches()
