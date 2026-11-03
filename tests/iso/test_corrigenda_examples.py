"""Examples from the ISO corrigenda texts on Ulrich Neumerkel's pages, pinned
against the engine and Scryer (2026-11-03).

* Cor.2 (https://www.complang.tuwien.ac.at/ulrich/iso-prolog/dtc2) 8.5.5.4:
  ``term_variables(t, [_, _|a])`` is ``type_error(list, [_, _|a])`` -- a Vars
  that is neither a list nor a partial list (8.5.5.3 a).  It used to fail.
* WDCor.3 (https://www.complang.tuwien.ac.at/ulrich/iso-prolog/WDCor3)
  8.14.2.4: ``write_term(1, [quoted(B)])`` is ``instantiation_error``.  It
  used to be ``domain_error(write_option, quoted(_))``.

Each row catches ``error(F, _)`` and answers ``F``: the context is
implementation defined (Scryer names write_term/3).
"""

from __future__ import annotations

import importlib
import sys

import pytest

from .test_iso_answers_scryer import _engine_answers, _scryer_answers

#: (row name, body binding R, what both print)
ROWS = [
    ("Cor.2 8.5.5.4 improper Vars",
     "catch(term_variables(t, [_, _|a]), error(F, _), R = F)",
     ["type_error(list,[_,_|a])"]),
    ("term_variables, an atom for Vars",
     "catch(term_variables(f(_), a), error(F, _), R = F)",
     ["type_error(list,a)"]),
    ("term_variables, a partial list for Vars",
     "term_variables(f(X, Y), [A|B]), R = [A|B]", ["[_,_]"]),
    ("term_variables, an empty list that is too short",
     "term_variables(f(_), []), R = y", []),
    ("WDCor.3 8.14.2.4 unbound quoted",
     "catch(write_term(1, [quoted(_)]), error(F, _), R = F)",
     ["instantiation_error"]),
    ("unbound ignore_ops", "catch(write_term(1, [ignore_ops(_)]), error(F, _), R = F)",
     ["instantiation_error"]),
    ("a non-Boolean quoted",
     "catch(write_term(1, [quoted(foo)]), error(F, _), R = F)",
     ["domain_error(write_option,quoted(foo))"]),
]

PROGRAM = "".join(f"r{i}(R) :- {body}.\n" for i, (_, body, _) in enumerate(ROWS))


@pytest.fixture(scope="module")
def pl_mod(tmp_path_factory):
    d = tmp_path_factory.mktemp("corrigenda")
    mp = pytest.MonkeyPatch()
    mp.setenv("CLAUSAL_PL_FRONTEND", "native")
    mp.syspath_prepend(str(d))
    name = "_iso_corrigenda_1103"
    (d / f"{name}.pl").write_text(PROGRAM)
    sys.modules.pop(name, None)
    importlib.invalidate_caches()
    try:
        yield importlib.import_module(name)
    finally:
        sys.modules.pop(name, None)
        mp.undo()


@pytest.mark.parametrize("i", range(len(ROWS)), ids=[r[0] for r in ROWS])
def test_engine(pl_mod, i):
    assert _engine_answers(pl_mod, f"r{i}", 3) == ROWS[i][2]


def test_oracle(scryer):
    del scryer   # the fixture only asserts the binary is there
    got = _scryer_answers(PROGRAM, [(f"r{i}(R)", 3) for i in range(len(ROWS))])
    assert got == [r[2] for r in ROWS]
