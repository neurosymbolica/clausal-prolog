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


@pytest.mark.parametrize("lib", ["reif", "lambda", "clpq", "tabling"])
def test_libraries_the_native_front_end_maps_are_not_refused(lib):
    """The translator's own handling of these is unchanged (library(lambda)
    is still its old 'names no module' refusal); none is the
    unknown-library error."""
    try:
        prolog_to_clausal(f":- use_module(library({lib})).\n")
    except PrologTranslationError as e:
        assert "is not a library the native front end knows" not in str(e)
