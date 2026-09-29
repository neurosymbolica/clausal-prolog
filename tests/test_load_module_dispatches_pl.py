"""``import_hook._load_module(name, path)`` loads a ``.pl`` path through the
Prolog loader ``CLAUSAL_PL_FRONTEND`` selects (as ``_load_prolog_module``
does) instead of parsing it as Clausal source, which died at the first
``%``.  A ``.seam``/``.clausal`` path is unchanged."""
from __future__ import annotations

import itertools

import pytest

from clausal import import_hook as ih
from clausal.import_hook import _load_module
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var

_N = itertools.count()

PL = """\
% a comment the Clausal parser cannot read
:- module({name}, [colour/1]).
colour(red).
colour(green).
"""


def _answers(mod, name):
    v = Var()
    return [_deref_walk(v) for _ in solve((name, v), mod)]


@pytest.mark.parametrize("frontend,loader", [
    ("translator", "PrologLoader"), ("native", "NativePrologLoader")])
def test_pl_path_loads_through_the_selected_front_end(tmp_path, monkeypatch,
                                                      frontend, loader):
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", frontend)
    name = f"lm_pl_{frontend}_{next(_N)}"
    p = tmp_path / f"{name}.pl"
    p.write_text(PL.format(name=name))
    mod = _load_module(name, str(p))
    assert type(mod.__loader__) is getattr(ih, loader)
    assert _answers(mod, "colour") == ["red", "green"]


@pytest.mark.parametrize("suffix", [".seam", ".clausal"])
def test_seam_and_clausal_paths_are_unchanged(tmp_path, monkeypatch, suffix):
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", "native")
    name = f"_lm_seam_{next(_N)}"
    p = tmp_path / f"{name}{suffix}"
    p.write_text("-private([red])\ncolour(red),\n")
    mod = _load_module(name, str(p))
    assert type(mod.__loader__) is ih.PredicateLoader
    assert _answers(mod, "colour") == ["red"]
