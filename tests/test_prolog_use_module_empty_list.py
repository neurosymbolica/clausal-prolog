"""``:- use_module(M, []).`` in a ``.pl`` file is a located translation error.

It used to reach the loader as ``-import_from(qm, [])`` and crash there with
``ValueError: empty names on ImportFrom``.  Measured 2026-09-29, the two
reference engines DISAGREE on what it means:

* Scryer (src/loader.pl): ``use_module(M, [])`` is ``remove_module(M)`` --
  it REMOVES M's exports from the importing module and never loads M, so a
  later ``qm:p(X)`` is ``existence_error(procedure, p/1)``.
* Trealla (and SWI): it loads M and imports nothing, so ``qm:p(X)`` answers.

Clausal can do neither faithfully without silently picking one, so the
translator refuses it, naming the line and both readings, and points at the
spellings that mean the same thing in both engines.
"""

from __future__ import annotations

import sys
import textwrap

import pytest

from clausal.import_hook import _load_prolog_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.tools.prolog_to_clausal import (
    PrologTranslationError,
    prolog_to_clausal,
)

QM = """\
:- module(qmempty, [p/1]).
p(1).
p(2).
"""


@pytest.fixture(autouse=True)
def on_path(tmp_path):
    sys.path.insert(0, str(tmp_path))
    yield
    sys.path.remove(str(tmp_path))
    for key in list(sys.modules):
        if key.startswith(("qmempty", "_pl_empty_")):
            del sys.modules[key]


def _write(tmp_path, name, text):
    p = tmp_path / f"{name}.pl"
    p.write_text(textwrap.dedent(text))
    return str(p)


def test_empty_import_list_is_a_located_error_through_the_hook(tmp_path):
    _write(tmp_path, "qmempty", QM)
    main = _write(tmp_path, "_pl_empty_main", """\
        % a comment line
        :- use_module(qmempty, []).
        q(X) :- qmempty:p(X).
    """)
    with pytest.raises((SyntaxError, ImportError)) as ei:
        _load_prolog_module("_pl_empty_main", main)
    msg = str(ei.value)
    assert "empty names on ImportFrom" not in msg
    assert "line 2" in msg
    assert "use_module(qmempty, [])" in msg
    assert "remove_module" in msg          # Scryer's reading is named
    assert "Trealla" in msg


@pytest.mark.parametrize("src", [
    ":- use_module(qmempty, []).\n",
    ":- use_module(library(lists), []).\n",
    ":- use_module(library(clpz), []).\n",
    ":- use_module(library(no_such_lib), []).\n",
])
def test_every_empty_import_list_is_refused(src):
    with pytest.raises(PrologTranslationError) as ei:
        prolog_to_clausal(src)
    assert "line 1" in str(ei.value)


def test_suggested_spelling_gives_qualified_access(tmp_path):
    """Positive control: the spelling the error recommends loads the module
    and a qualified qmempty:p(X) answers."""
    _write(tmp_path, "qmempty", QM)
    main = _write(tmp_path, "_pl_empty_ok", """\
        :- use_module(qmempty).
        q(X) :- qmempty:p(X).
    """)
    mod = _load_prolog_module("_pl_empty_ok", main)
    x = Var()
    got = [deref(x) for _ in call("q", x, module=mod.__clausal_module__)]
    assert got == [1, 2]
