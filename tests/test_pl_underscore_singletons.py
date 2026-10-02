"""D19: in a ``.pl`` file a variable whose name starts with ``_`` (``_Y``) is
exempt from the singleton warning, by the Prolog convention ISO and Scryer
follow.  The ``.pl`` import path used to warn "rename to ``_Y_UNUSED``"
(``ClausalSingletonWarning``) for it.

The exemption is the ``.pl`` path's only: in ``.clausal``/``.seam`` source
the singleton rule has no exceptions (ruled), so the same clause still warns
there.
"""

from __future__ import annotations

import os
import warnings

from clausal import Var
from clausal.import_hook import _load_module, _load_prolog_module
from clausal.lint_warnings import ClausalSingletonWarning
from clausal.logic.solve import call
from clausal.logic.variables import deref, walk
from tests._suffix import SEAM


def _singleton_warnings(load):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        mod = load()
    return mod, [str(w.message) for w in caught
                 if issubclass(w.category, ClausalSingletonWarning)]


def _write(tmp_path, name, text):
    path = os.path.join(tmp_path, name)
    with open(path, "w") as fh:
        fh.write(text)
    return path


def test_a_pl_underscore_variable_is_not_a_singleton(tmp_path):
    path = _write(tmp_path, "d19_pl.pl",
                  "p(1, a).\np(2, b).\n"
                  "g(L) :- setof(X, p(X, _Y), L).\n")
    mod, found = _singleton_warnings(
        lambda: _load_prolog_module("tests_d19_pl", path))
    assert found == []
    out = Var()
    # setof/3 groups by the free _Y, as in Prolog
    assert [walk(deref(out)) for _ in call("g", out, module=mod)] == [[1], [2]]


def test_a_pl_plain_singleton_still_warns(tmp_path):
    """Only the ``_``-prefixed name is exempt; ``X`` once is a singleton in
    Prolog too."""
    path = _write(tmp_path, "d19_pl_plain.pl",
                  "p(1, a).\nh(L) :- setof(Z, p(Z, W), L).\n")
    _mod, found = _singleton_warnings(
        lambda: _load_prolog_module("tests_d19_pl_plain", path))
    assert len(found) == 1 and "`W`" in found[0]


def test_the_same_singleton_in_a_clausal_file_still_warns(tmp_path):
    path = _write(tmp_path, f"d19_clausal{SEAM}",
                  "p(1, 10),\np(2, 20),\n"
                  "g(L) <- setof(X, p(X, _Y), L)\n")
    _mod, found = _singleton_warnings(
        lambda: _load_module("tests_d19_clausal", path))
    assert len(found) == 1 and "`_Y`" in found[0]
