"""A ``use_module`` whose target's PARENT package fails to import reports that
failure, not "no module ... on sys.path".

Finding a submodule imports its parent packages first. When a parent's
``__init__`` raised (here: it imports a predicate a sibling does not
export), ``_module_source`` swallowed the ImportError and answered "no
such module", so the load error named a module that exists and hid the
real fault. Found 2026-11-13 in a generated package whose ``__init__``
imported an unexported name: every test file failed with "no module
pkg.fixtures on sys.path".

A module that is genuinely absent still gets the "no module" refusal.
Trees are synthetic, built in ``tmp_path``.
"""
from __future__ import annotations

import importlib
import sys
import textwrap

import pytest

_NAMES = ("umpie_pkg", "umpie_t", "umpie_absent")


def _evict():
    for name in list(sys.modules):
        if name.split(".", 1)[0] in _NAMES:
            del sys.modules[name]


@pytest.fixture
def root(tmp_path):
    _evict()
    saved = list(sys.path)
    sys.path[:] = [str(tmp_path)] + saved
    importlib.invalidate_caches()
    yield tmp_path
    sys.path[:] = saved
    _evict()


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def _package(root, init_imports):
    _write(root / "umpie_pkg" / "__init__.clausal", f"""\
        :- module(umpie_pkg, [a/1, b/1]).
        :- use_module(umpie_pkg/sib, [{init_imports}]).
        :- use_module(umpie_pkg/fix, [b/1]).
        :- end_module(umpie_pkg).
        """)
    _write(root / "umpie_pkg" / "sib.clausal", """\
        :- module(sib, [a/1]).
        a(1).
        :- end_module(sib).
        """)
    _write(root / "umpie_pkg" / "fix.clausal", """\
        :- module(fix, [b/1]).
        b(2).
        :- end_module(fix).
        """)


def _importer(root, target):
    _write(root / "umpie_t.clausal", f"""\
        :- module(umpie_t, []).
        :- use_module({target}, [b/1]).
        :- end_module(umpie_t).
        """)


def test_a_failing_parent_package_is_reported_as_itself(root):
    _package(root, "a/1, missing/1")
    _importer(root, "umpie_pkg/fix")
    with pytest.raises(Exception) as info:
        importlib.import_module("umpie_t")
    message = str(info.value)
    assert "missing" in message, message
    assert "no module umpie_pkg.fix on sys.path" not in message, message


def test_a_sound_package_still_imports(root):
    _package(root, "a/1")
    _importer(root, "umpie_pkg/fix")
    importlib.import_module("umpie_t")


def test_an_absent_module_is_still_no_module(root):
    _importer(root, "umpie_absent/fix")
    with pytest.raises(Exception) as info:
        importlib.import_module("umpie_t")
    assert "no module umpie_absent.fix on sys.path" in str(info.value)


def test_an_absent_submodule_of_a_sound_package_is_still_no_module(root):
    _package(root, "a/1")
    _importer(root, "umpie_pkg/nothere")
    with pytest.raises(Exception) as info:
        importlib.import_module("umpie_t")
    assert "no module umpie_pkg.nothere on sys.path" in str(info.value)
