"""An unknown ``library(X)`` is refused by the TRANSLATOR front end too, on
plain ``.pl`` (operator ruling 2026-10-01), with the native front end's
error: a ``.pl`` must never silently get a Python standard-library module
-- ``library(os)``, ``library(math)`` -- by reading the library name as a
module.  Known libraries (built in, mapped, the ``library(...)`` facades,
``py_*``) are unchanged.
"""
from __future__ import annotations

import textwrap

import pytest

from clausal.tools.prolog_to_clausal import (
    PrologTranslationError, prolog_to_clausal)


def _refusal(native, name, text, frontend):
    with pytest.raises(SyntaxError) as ei:
        native.load(name, textwrap.dedent(text), frontend=frontend)
    return str(ei.value)


@pytest.mark.parametrize("frontend", ["translator", "native"])
@pytest.mark.parametrize("lib,imports", [
    ("os", ""), ("os", ", [getenv/2]"), ("math", ", [sqrt/2]"),
    ("random", ""), ("time", ""), ("nosuch", ""),
    # Every listed name is an engine builtin: still an unknown library.
    ("charsio", ", [atom_chars/2]"),
])
def test_an_unknown_library_is_refused(native, frontend, lib, imports):
    name = f"unk_{lib}_{frontend}_{len(imports)}"
    msg = _refusal(native, name,
                   f"a.\n:- use_module(library({lib}){imports}).\n",
                   frontend)
    assert f"library({lib}) is not a library the native front end knows" \
        in msg, msg


@pytest.mark.parametrize("lib", ["os", "math", "nosuch"])
def test_the_translator_says_what_the_native_front_end_says(lib):
    with pytest.raises(PrologTranslationError) as ei:
        prolog_to_clausal(f":- use_module(library({lib})).\n")
    msg = str(ei.value)
    assert f"library({lib}) is not a library the native front end knows" \
        in msg
    assert "built in:" in msg and "mapped:" in msg and "facades:" in msg


@pytest.mark.parametrize("spec,want", [
    ("library(clpz), [(#=)/2, label/1]", "clausal.logic.clpfd"),
    ("library(lists), [append/3]", "built-in"),
    ("library(clpb), [sat/1]", "clausal.logic.clpb"),
    ("library(datetime), [date_add/3]", "clausal.library.datetime"),
    ("library(py_os), [cpu_count/1]", "clausal.library.py_os"),
    ("library(countries/european_union), [euro]",
     "clausal.library.countries.european_union"),
])
def test_known_libraries_are_unchanged(spec, want):
    out = prolog_to_clausal(f":- use_module({spec}).\n")
    assert want in out, out


def test_native_only_libraries_are_exactly_reif_clpq_lambda():
    """The libraries the native front end maps but the translator does not
    -- the only ones reaching the translator's last library branch, which
    the three tests below pin.  A new one must get a test of its own."""
    from clausal.tools.iso_l3_directives import (
        _BUILTIN_LIBRARIES as NB, _LIBRARY_MODULES as NM)
    from clausal.tools.prolog_to_clausal import (
        _BUILTIN_LIBRARIES as TB, _LIBRARY_TO_MODULE as TM)
    assert (set(NB) | set(NM)) - set(TB) - set(TM) == {
        "reif", "clpq", "lambda"}


def test_library_clpq_loads_and_runs_under_the_translator(native, ans):
    """Every name listed is an engine builtin: the import is a no-op and
    the module loads; entailed/1 (clpq's) runs."""
    mod = native.load("unk_clpq_ok", textwrap.dedent("""\
        :- use_module(library(clpq), [entailed/1]).
        p(yes) :- {X >= 2}, entailed(X >= 1).
        """), frontend="translator")
    assert ans(mod, "p") == ["yes"]


def test_library_reif_keeps_its_translation():
    """The translator's long-standing output for library(reif), unchanged
    (it reads reif as a module name)."""
    assert prolog_to_clausal(
        ":- use_module(library(reif), [memberd_t/3]).\n").endswith(
        "-import_from(reif, [memberd_t])\n")
    assert prolog_to_clausal(
        ":- use_module(library(reif)).\n").endswith("-import_module(reif)\n")


def test_library_lambda_keeps_its_old_refusal():
    """library(lambda) under the translator is its long-standing 'names no
    module' refusal, not the unknown-library error."""
    with pytest.raises(PrologTranslationError) as ei:
        prolog_to_clausal(":- use_module(library(lambda)).\n")
    assert "'lambda' names no module" in str(ei.value)
