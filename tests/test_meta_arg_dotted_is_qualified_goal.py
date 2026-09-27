"""A dotted ``lib.p(...)`` in a -meta_predicate GOAL position is ``lib:p(...)``.

Operator ruling 2026-09-25: a dotted ``lib.p(...)`` written directly as an
argument in a position the CALLEE declares as a goal (an integer spec, or
``:``) compiles as the QUALIFIED GOAL -- the cell ``(":", lib, ("p", ...))``
-- exactly as the same dotted call written in goal position resolves in lib.
It used to be lowered in TERM position first, where ruling (a) makes it the
plain cell ``("p", ...)``, and ``$meta_qualify`` then qualified that with the
CALLER's module, so the caller's own ``p`` ran (or it raised).  A bare dotted
name ``lib.p`` there is ``(":", lib, "p")``.  ``'?'``/``'+'``/``'-'``
positions keep term lowering (the plain cell, ruling (a)).

Scryer (verified on the box, 2026-09-25)::

    :- meta_predicate(e0(0)), meta_predicate(e1(1, ?)),
       meta_predicate(e2(2, ?, ?)), meta_predicate(cprobe(:, ?)).
    ?- cprobe(mqlib:decide(1, seen), T).    % T = mqlib:decide(1,seen)
    ?- cprobe(mqlib:decide, T).             % T = mqlib:decide
    ?- e0(mqlib:decide(1, V)).              % V = lib_version
    ?- e1(mqlib:decide(1), V).              % V = lib_version
    ?- e2(mqlib:decide, 1, V).              % V = lib_version
    ?- e1(mqlib:nosuch, _).   % error(existence_error(procedure,nosuch/1),nosuch/1)

(The mqdom caller defines its own decide/2 answering caller_version.)
"""
from __future__ import annotations

import sys
import textwrap

import pytest

from clausal import cell_args, cell_functor
from clausal.logic.atoms import mangle, mint
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call
from clausal.logic.variables import Var, walk


def _load(tmp_path, monkeypatch, name, body):
    from clausal.import_hook import _load_module
    monkeypatch.syspath_prepend(str(tmp_path))
    p = tmp_path / f"{name}.clausal"
    p.write_text(textwrap.dedent(body).lstrip())
    mod = _load_module(name, str(p))
    assert sys.modules[name] is mod
    return mod


_LIB = """
    -module(mdqlib_ERA, [e0(G), e1(G, X), e2(G, X, Y), cprobe(M, Q),
                         gprobe(G, Q), qprobe(M, Q), chop(M, Q), decide(B, V),
                         applyto(G, V)])
    -meta_predicate(e0(0), e1(1, '?'), e2(2, '?', '?'), cprobe(':', '?'),
                    gprobe(0, '?'), qprobe('?', '?'), chop(':', '?'))
    -private([lib_version])
    e0(G) <- call_goal(G),
    e1(G, X) <- call_goal(G, X),
    e2(G, X, Y) <- call_goal(G, X, Y),
    cprobe(M, Q) <- (Q is M),
    gprobe(G, Q) <- (Q is G),
    qprobe(M, Q) <- (Q is M),
    chop(M, Q) <- cprobe(M, Q),
    decide(_B_UNUSED, lib_version),
    applyto(G, V) <- call_goal(G, V),
"""

_DOM = """
    -module(mdqdom_ERA, [])
    -import_module(mdqlib_ERA)
    -import_from(mdqlib_ERA, [e0, e1, e2, cprobe, gprobe, qprobe, chop])
    -private([seen, caller_version])
    decide(_B_UNUSED, caller_version),
    applyto(_G_UNUSED, caller_version),
    x0(V) <- e0(mdqlib_ERA.decide(1, V)),
    x1(V) <- e1(mdqlib_ERA.decide(1), V),
    x2(V) <- e2(mdqlib_ERA.decide, 1, V),
    own0(V) <- e0(decide(1, V)),
    own1(V) <- e1(decide(1), V),
    own2(V) <- e2(decide, 1, V),
    c_applied(T) <- cprobe(mdqlib_ERA.decide(1, seen), T),
    g_applied(T) <- gprobe(mdqlib_ERA.decide(1, seen), T),
    q_applied(T) <- qprobe(mdqlib_ERA.decide(1, seen), T),
    c_bare(T) <- cprobe(mdqlib_ERA.decide, T),
    g_bare(T) <- gprobe(mdqlib_ERA.decide, T),
    c_hop(T) <- chop(mdqlib_ERA.decide(1, seen), T),
    x_lam(V) <- e0(mdqlib_ERA.applyto((A <- (A is 5)), V)),
    miss0() <- e0(mdqlib_ERA.nosuch(1)),
    miss1() <- e1(mdqlib_ERA.nosuch, 1),
"""


@pytest.fixture(params=["handle"])
def dq(request, tmp_path, monkeypatch):
    # W4b-2d flip: the load itself binds an import to the OWNER's handle, so
    # the class-era arm and the stand-in flip are gone (task-9 brief rule 3);
    # the positive control asserts the real flip happened.
    era = request.param
    _load(tmp_path, monkeypatch, f"mdqlib_{era}", _LIB.replace("ERA", era))
    dom = _load(tmp_path, monkeypatch, f"mdqdom_{era}", _DOM.replace("ERA", era))
    D = dom.__dict__["$module"]
    assert D.module_dict["e1"] == mangle(f"mdqlib_{era}", "e1")
    return era, D


def _one(module, goal):
    q = Var()
    out = [walk(q) for _ in call(goal, q, module=module)]
    assert len(out) == 1, out
    return out[0]


@pytest.mark.parametrize("goal", ["x0", "x1", "x2"])
def test_a_dotted_meta_argument_runs_the_owners_predicate(dq, goal):
    """0, 1 and 2 extra arguments (x2 is the bare dotted name)."""
    _era, D = dq
    assert _one(D, goal) == "lib_version"


@pytest.mark.parametrize("goal", ["own0", "own1", "own2"])
def test_the_callers_own_name_still_runs_the_callers_predicate(dq, goal):
    """The control: the same shapes without the module prefix."""
    _era, D = dq
    assert _one(D, goal) == "caller_version"


@pytest.mark.parametrize("goal", ["c_applied", "g_applied", "c_hop"])
def test_the_dotted_call_arrives_as_the_owner_qualified_goal(dq, goal):
    """``:`` and integer spec; through a second ``:`` hop inside the library
    it is NOT re-qualified (already qualified)."""
    era, D = dq
    assert _one(D, goal) == (":", f"mdqlib_{era}", ("decide", 1, "seen"))


@pytest.mark.parametrize("goal", ["c_bare", "g_bare"])
def test_a_bare_dotted_name_arrives_as_the_owner_qualified_atom(dq, goal):
    era, D = dq
    assert _one(D, goal) == (":", f"mdqlib_{era}", "decide")


def test_a_question_mark_position_keeps_the_plain_cell(dq):
    """Ruling (a): a dotted call in TERM position is the plain cell."""
    _era, D = dq
    assert _one(D, "q_applied") == ("decide", 1, "seen")


@pytest.mark.parametrize("goal", ["miss0", "miss1"])
def test_a_missing_owner_predicate_raises_existence_error(dq, goal):
    """Never the caller's predicate, never a silent failure."""
    _era, D = dq
    with pytest.raises(LogicException) as exc:
        list(call(goal, module=D))
    formal = cell_args(exc.value.term)[0]
    assert cell_functor(formal) == "existence_error"
    assert cell_args(formal) == (mint("procedure"), ("/", mint("nosuch"), 1))


def test_a_lambda_inside_the_dotted_call_is_hoisted_and_stays_owner_qualified(dq):
    """The lambda-hoisting walk rebuilds the marker: it must keep the module."""
    _era, D = dq
    assert _one(D, "x_lam") == 5
