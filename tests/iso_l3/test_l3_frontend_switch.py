"""D3(a): ``CLAUSAL_PL_FRONTEND=native|translator`` selects the ``.pl`` front
end; the translator stays the default until slice 8, and the front-end id is
part of the bytecode cache key (R2: the P1 author was once served the other
front end's cached code).

Every test here clears ``__pycache__`` (or starts in a fresh tmp dir) and
asserts WHICH front end ran, by the loader class and by the L3 stats' non-zero
denominator.
"""
from __future__ import annotations

import importlib
import os
import shutil
import sys

import pytest

from clausal import import_hook as ih

ENV = "CLAUSAL_PL_FRONTEND"


@pytest.fixture
def pkg(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    names: list[str] = []
    yield tmp_path, names
    for n in names:
        sys.modules.pop(n, None)
    for p in tmp_path.rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)


def _import(tmp, names, name):
    sys.modules.pop(name, None)
    for p in tmp.rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)
    names.append(name)
    importlib.invalidate_caches()
    return importlib.import_module(name)


def _answers(mod, name):
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref, walk
    x = Var()
    return [walk(deref(x)) for _ in call(name, x, module=mod)]


# ── selection ──


def test_unset_env_selects_the_translator(pkg, monkeypatch):
    tmp, names = pkg
    monkeypatch.delenv(ENV, raising=False)
    (tmp / "fe_unset.pl").write_text("f(1).\ng(X) :- f(X).\n")
    mod = _import(tmp, names, "fe_unset")
    assert type(mod.__loader__) is ih.PrologLoader
    assert ih.pl_frontend() == "translator"
    assert _answers(mod, "g") == [1]


def test_explicit_translator_is_the_translator(pkg, monkeypatch):
    tmp, names = pkg
    monkeypatch.setenv(ENV, "translator")
    (tmp / "fe_tr.pl").write_text("f(1).\n")
    assert type(_import(tmp, names, "fe_tr").__loader__) is ih.PrologLoader


def test_native_env_selects_the_native_loader(pkg, monkeypatch):
    tmp, names = pkg
    monkeypatch.setenv(ENV, "native")
    (tmp / "fe_nat.pl").write_text("f(1).\nf(2).")
    mod = _import(tmp, names, "fe_nat")
    assert type(mod.__loader__) is ih.NativePrologLoader
    st = mod.__loader__.l3_stats
    assert st["read"] == 2 and st["lowered"] == 2 and st["refused"] == 0, st
    assert _answers(mod, "f") == [1, 2]


def test_load_prolog_module_follows_the_env(tmp_path, monkeypatch):
    path = tmp_path / "fe_helper.pl"
    path.write_text("f(1).\n")
    monkeypatch.setenv(ENV, "native")
    mod = ih._load_prolog_module("fe_helper_n", str(path))
    assert type(mod.__loader__) is ih.NativePrologLoader
    assert mod.__loader__.l3_stats["lowered"] == 1
    monkeypatch.delenv(ENV)
    mod = ih._load_prolog_module("fe_helper_t", str(path))
    assert type(mod.__loader__) is ih.PrologLoader
    for n in ("fe_helper_n", "fe_helper_t"):
        sys.modules.pop(n, None)


def test_an_unknown_frontend_value_is_an_error_not_a_default(pkg, monkeypatch):
    tmp, names = pkg
    monkeypatch.setenv(ENV, "natve")
    (tmp / "fe_typo.pl").write_text("f(1).\n")
    with pytest.raises(ImportError, match="CLAUSAL_PL_FRONTEND"):
        _import(tmp, names, "fe_typo")


def test_native_refusal_is_an_import_error_naming_the_pl_line(pkg, monkeypatch):
    tmp, names = pkg
    monkeypatch.setenv(ENV, "native")
    (tmp / "fe_ref.pl").write_text("f(1).\n\n:- initialization(f(1)).\n")
    with pytest.raises(SyntaxError) as ei:
        _import(tmp, names, "fe_ref")
    assert ei.value.lineno == 3
    assert "fe_ref.pl:3" in str(ei.value)
    assert "fe_ref" not in sys.modules


def test_native_syntax_issue_is_an_import_error_naming_the_pl_line(
        pkg, monkeypatch):
    tmp, names = pkg
    monkeypatch.setenv(ENV, "native")
    (tmp / "fe_syn.pl").write_text("f(1).\nf(.\n")
    with pytest.raises(SyntaxError) as ei:
        _import(tmp, names, "fe_syn")
    assert ei.value.lineno == 2 and "syntax error" in str(ei.value)


# ── the cache key ──


def test_the_two_front_ends_have_different_cache_keys(tmp_path):
    path = tmp_path / "ck.pl"
    path.write_text("f(1).\n")
    tr = ih.PrologLoader("ck", str(path)).path_stats(str(path))
    nat = ih.NativePrologLoader("ck", str(path)).path_stats(str(path))
    assert tr["size"] == nat["size"]
    assert tr["mtime"] != nat["mtime"]
    # The translator's key is exactly what it was before the switch existed,
    # so every cache written with the env unset stays valid.
    st = os.stat(path)
    assert tr["mtime"] == (st.st_mtime_ns
                           ^ ih._effective_bytecode_tag()) & 0xFFFFFFFF


def test_the_native_salt_is_nonzero_in_the_32_bits_importlib_keeps():
    assert ih._native_frontend_salt() & 0xFFFFFFFF != 0


def test_a_cached_entry_of_one_front_end_is_never_served_to_the_other(
        pkg, monkeypatch):
    """Load natively (writes a .pyc), then with the translator WITHOUT
    clearing the cache: the translator must compile, not reuse, and vice
    versa.  Counted by source_to_code calls, per loader class."""
    tmp, names = pkg
    (tmp / "ck2.pl").write_text("f(1).\n")
    calls: list[str] = []
    for cls in (ih.PrologLoader, ih.NativePrologLoader):
        orig = cls.source_to_code

        def wrapped(self, data, path="<string>", _orig=orig, _cls=cls):
            calls.append(_cls.__name__)
            return _orig(self, data, path)
        monkeypatch.setattr(cls, "source_to_code", wrapped)

    def load(frontend):
        monkeypatch.setenv(ENV, frontend)
        sys.modules.pop("ck2", None)
        names.append("ck2")
        importlib.invalidate_caches()
        return importlib.import_module("ck2")

    for p in tmp.rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)
    load("native")
    assert calls == ["NativePrologLoader"]
    assert list(tmp.rglob("*.pyc")), "the native load wrote no .pyc"
    load("translator")
    assert calls == ["NativePrologLoader", "PrologLoader"]
    load("native")
    assert calls == ["NativePrologLoader", "PrologLoader", "NativePrologLoader"]
    # POSITIVE CONTROL: the same front end twice IS served from the cache.
    mod = load("native")
    assert calls[-1] == "NativePrologLoader" and len(calls) == 3
    # ...and the cache-hit path still reports its stats: it re-reads the
    # file and re-lowers only the directives (slice 2), so the one clause
    # is counted as skipped.
    st = mod.__loader__.l3_stats
    assert st["read"] == 1 and st["skipped"] == 1 and st["lowered"] == 0, st


def test_every_file_the_native_path_runs_is_in_its_cache_key():
    """R2's census: whatever code RUNS while the native front end compiles a
    .pl file is covered by the engine fingerprint or by the native salt."""
    import clausal
    from clausal.tools import toklex
    package = os.path.dirname(os.path.abspath(clausal.__file__))
    toklex.load_lexer.cache_clear()
    ran: set = set()

    def prof(frame, event, arg):
        if event == "call":
            ran.add(frame.f_code.co_filename)

    sys.setprofile(prof)
    try:
        ih.NativePrologLoader("m", "m.pl").source_to_code(
            b":- op(700, xfx, ===>).\n" b"p(1).\n", "m.pl")
    except SyntaxError:
        pass   # the directive is refused; the reader and L3 ran
    finally:
        sys.setprofile(None)
    tools = {os.path.relpath(f, package) for f in ran
             if isinstance(f, str) and f.startswith(
                 os.path.join(package, "tools") + os.sep)}
    assert "tools/iso_l3.py" in tools and "tools/prolog_reader.py" in tools
    covered = set(ih._NATIVE_FRONTEND_FILES) | set(ih._COMPILATION_FILES)
    uncovered = {f for f in tools
                 if f not in covered and not f.startswith("tools/toklex/")}
    assert not uncovered, uncovered
