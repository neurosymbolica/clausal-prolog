"""Slice E5b: per-optimisation toggle test matrix.

Re-runs a representative correctness case under each optimisation
**individually** disabled.  Catches hidden ordering dependencies
between passes — e.g. a TRO clause that secretly relies on call-site
specialisation having already rewritten the tail call, or a DR
rewrite that double-applies when both legacy preprocess and the IR
shadow run.

The TRO matrix below is the high-risk cell — TRO is the most likely
source of subtle miscompilation during this refactor (per the E
slice plan).  Coverage of the remaining flag combinations is carried
by the full suite running with each disable in turn (see the parent
sweep in CI / commit notes); doing that as a per-test parametrise
inside this file would multiply suite runtime by 4× without adding
information beyond what TRO + the full sweep already establish.
"""

from __future__ import annotations

import pytest

from clausal.logic.compiler.predicate import compile_predicate_trampoline
from clausal.logic.database import Database, Clause
from tests.predicate_api_support import RowPredicate
from clausal.logic.solve import call
from clausal.logic.variables import Var, Trail, deref
from clausal.terms import (
    Call, LoadName, Sub, Evaluate, Gt, Unify,
)


_DEFAULTS = frozenset({"tro", "destructive_reuse", "call_site"})


@pytest.fixture(params=[
    pytest.param(_DEFAULTS, id="all-on"),
    pytest.param(_DEFAULTS - {"tro"}, id="no-tro"),
    pytest.param(_DEFAULTS - {"destructive_reuse"}, id="no-dr"),
    pytest.param(_DEFAULTS - {"call_site"}, id="no-call-site"),
])
def enabled(request):
    return request.param


def test_tro_recursive_countdown_under_each_disable(enabled):
    """A tail-recursive predicate compiled with each individual
    optimisation disabled must still produce the correct number of
    solutions.  Failure modes guarded against:

    - ``no-tro``: TRO bypass disabled; recursion uses the normal
      call path (Python stack handles N=5 trivially).
    - ``no-dr`` / ``no-call-site``: the predicate doesn't use DR
      or call-site specialisation, but disabling them must not
      perturb the TRO compile path (catches accidental coupling).
    """
    from clausal.logic.database import Module
    # A deterministic module name per parameter (``hash`` of a frozenset of
    # strs varies with PYTHONHASHSEED): the sorted enabled set, joined.
    name = "_toggle_" + "_".join(sorted(enabled))
    db = Module(name, module_dict={"__name__": name}).db
    # compiled through its handle, as a loaded module's predicate is
    # (a PredicateMeta class until W4b-3 slice 7)
    CountDown = RowPredicate('CountDown', ('n',), db)

    base_n = Var()
    n, n1 = Var(), Var()
    clauses = [
        Clause(head=CountDown(base_n), body=[Unify(left=base_n, right=0)]),
        Clause(head=CountDown(n), body=[
            Gt(left=n, right=0),
            Evaluate(left=n1, right=Sub(left=n, right=1)),
            Call(func=LoadName(name='CountDown'), args=[n1], kwargs=[]),
        ]),
    ]
    for cl in clauses:
        db.assertz(cl)
    db.register_signature('CountDown', 1, CountDown._fields)
    compile_predicate_trampoline(
        'CountDown', 1, clauses, db,
        globals_={'CountDown': CountDown.handle},
        pred_cls=CountDown.handle,
        enabled_optimisations=enabled,
    )
    trail = Trail()
    arg = Var()
    results = []
    for _ in call(CountDown.handle, 5, trail=trail):
        results.append(deref(arg))
    assert len(results) == 1
