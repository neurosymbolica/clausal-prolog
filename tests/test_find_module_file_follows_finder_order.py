"""The ``.pl`` translator's twin check reads the import hook's finder order.

``_PrologToClausal._find_module_file`` answers "is ``dotted`` a ``.pl`` file
whose ``module/2`` list I should read?".  It must say no when a twin the
import hook would load INSTEAD sits beside the ``.pl`` -- and which twins
win is the finder's order, ``clausal._suffixes.SOURCE_SUFFIXES``: every
extension before ``PROLOG_SUFFIX``.  It used to spell that set as the
literal ``(".clausal", ".seam")``, which was right only until the order next
moved.  The drift test simulates a new surface ahead of ``.pl`` and fails on
the literal tuple.
"""
from __future__ import annotations

import pytest

from clausal import _suffixes
from clausal.tools.prolog_to_clausal import _PrologToClausal
from clausal.tools.prolog_dialect import Dialect


def _finder(tmp_path):
    importer = tmp_path / "importer.pl"
    importer.write_text("")
    return _PrologToClausal(Dialect.scryer_reader(),
                            source_path=str(importer),
                            module_name="importer")


def test_a_lone_pl_is_the_module(tmp_path):
    (tmp_path / "lib.pl").write_text(":- module(lib, [p/1]).\n")
    assert _finder(tmp_path)._find_module_file("lib") == str(tmp_path / "lib.pl")


@pytest.mark.parametrize(
    "twin", [s for s in _suffixes.SOURCE_SUFFIXES
             if s != _suffixes.PROLOG_SUFFIX])
def test_each_twin_ahead_of_pl_wins(tmp_path, twin):
    """Unchanged behaviour: a ``.seam`` or ``.clausal`` twin is what loads."""
    (tmp_path / "lib.pl").write_text(":- module(lib, [p/1]).\n")
    (tmp_path / f"lib{twin}").write_text("")
    assert _finder(tmp_path)._find_module_file("lib") is None


def test_the_twin_set_follows_the_finder_order(tmp_path, monkeypatch):
    """A surface added ahead of ``.pl`` in the finder order hides the
    ``.pl`` without anyone editing the translator."""
    monkeypatch.setattr(
        _suffixes, "SOURCE_SUFFIXES",
        (*_suffixes.SOURCE_SUFFIXES[:-1], ".newsurface",
         _suffixes.PROLOG_SUFFIX))
    (tmp_path / "lib.pl").write_text(":- module(lib, [p/1]).\n")
    (tmp_path / "lib.newsurface").write_text("")
    assert _finder(tmp_path)._find_module_file("lib") is None


def test_a_surface_after_pl_does_not_hide_it(tmp_path, monkeypatch):
    """The order matters, not mere presence: a surface the finder tries
    AFTER ``.pl`` loses to it, so the ``.pl`` is still the module."""
    monkeypatch.setattr(
        _suffixes, "SOURCE_SUFFIXES",
        (*_suffixes.SOURCE_SUFFIXES, ".latersurface"))
    (tmp_path / "lib.pl").write_text(":- module(lib, [p/1]).\n")
    (tmp_path / "lib.latersurface").write_text("")
    assert _finder(tmp_path)._find_module_file("lib") == str(tmp_path / "lib.pl")
