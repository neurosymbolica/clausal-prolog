"""phrase/2,3 grammar-body translation errors, against Ulrich Neumerkel's
phrase/2,3 comparison (https://www.complang.tuwien.ac.at/ulrich/iso-prolog/phrase),
rows #5-#8, #13, #17-#21, #28-#30, #38, #46-#48 and the bound-tail rows
after #45.

Three defects in ``clausal/logic/builtins/dcg.py``'s run-time translation of
a grammar body (``_dcg_body_goal``):

* C. An IMPROPER terminal list, ``[a|b]``, is the cons cell ``'.'(a, b)``,
  which fell through to the nonterminal arm: ``phrase([a|b], L)`` raised
  ``existence_error(procedure, '.'/4)``.  It is ``type_error(list, [a|b])``.
* B. A PARTIAL terminal list, ``[a|L]`` with ``L`` unbound when the body is
  translated, names an unknown number of terminals: ISO and Scryer raise
  ``instantiation_error``.  At the top level phrase failed silently; nested,
  the SegList became a garbage goal tuple.  A tail bound BEFORE the call
  (``L = [], phrase([a|L], [a])``) is a proper list and must keep working.
* A. A non-callable nonterminal leaf (``1``) was emitted as the raw goal
  ``(1, S0, S)``, and call/1's body converter reported the WHOLE translated
  body, Python internals included (``AttVar(_59)``, ``SetTerm({False})``),
  or nothing at all when an earlier goal failed first (#13).  It is
  ``type_error(callable, 1)``, raised when the body is translated.

The check ORDER is Scryer's, measured (the table accepts either answer for
#19-#21 and #48): a list-shape error anywhere in the body wins over a
non-callable leaf anywhere in it, so ``phrase((1,[a|L]),[])`` is
``instantiation_error`` and ``phrase((1,[a|b]),[])`` is
``type_error(list,[a|b])``.  SICStus reports the leftmost problem instead.

``\\+ B`` is ``\\+ phrase(B, S0, _), S0 = S``: B is translated when the
negation RUNS, so ``phrase(([a],\\+1),[])`` is false (#29: the table's
non-``representation_error`` answer) and ``phrase(\\+1,L)`` raises
``type_error(callable,1)`` (#28).  Scryer refuses ``\\+`` in a grammar body
(``representation_error(dcg_body)``); Clausal keeps it (see
tests/test_dcg_braces.py), so those rows are not compared with Scryer.
"""

from __future__ import annotations

import importlib
import sys
import warnings

import pytest

from .test_iso_answers_scryer import _engine_answers, _scryer_answers


def _f(goal: str) -> str:
    """*goal* with its error's FORMAL term bound to R."""
    return f"catch({goal}, error(F, _), R = F)"


#: (row name, body binding R, what the engine prints,
#:  what Scryer prints -- None where Scryer is not the reference)
ROWS = [
    # ── C: an improper terminal list ────────────────────────────────────
    ("#5 phrase([a|b],L)", _f("phrase([a|b],L)"),
     ["type_error(list,[a|b])"], ["type_error(list,[a|b])"]),
    ("nested improper terminal", _f("phrase(([a],[b|c]),[a,b])"),
     ["type_error(list,[b|c])"], ["type_error(list,[b|c])"]),
    ("#5 full error term", "catch(phrase([a|b],L), E, R = E)",
     ["error(type_error(list,[a|b]),phrase/2)"], None),
    # ── B: a partial terminal list ──────────────────────────────────────
    ("#6 phrase([a|L],K)", _f("phrase([a|L],K)"),
     ["instantiation_error"], ["instantiation_error"]),
    ("#38 phrase([a|L],L)", _f("phrase([a|L],L)"),
     ["instantiation_error"], ["instantiation_error"]),
    ("#7 phrase([a|L],[a,b])", _f("phrase([a|L],[a,b])"),
     ["instantiation_error"], ["instantiation_error"]),
    ("#8 phrase([a|L],[])", _f("phrase([a|L],[])"),
     ["instantiation_error"], ["instantiation_error"]),
    ("#17 phrase(({L=[]},[a|L]),[a])", _f("phrase(({L=[]},[a|L]),[a])"),
     ["instantiation_error"], ["instantiation_error"]),
    ("#18 phrase([a|L],K), L=[b]", _f("(phrase([a|L],K), L=[b])"),
     ["instantiation_error"], ["instantiation_error"]),
    ("phrase/3 partial terminal", _f("phrase([a|L],[a],S)"),
     ["instantiation_error"], ["instantiation_error"]),
    ("#6 full error term", "catch(phrase([a|L],K), E, R = E)",
     ["error(instantiation_error,phrase/2)"], None),
    # must NOT regress: a tail bound before the call is a proper list
    ("after #45: L=[],phrase([a|L],[b])", "L=[], phrase([a|L],[b]), R = L",
     [], []),
    ("after #45: L=[],phrase([a|L],[a])", "L=[], phrase([a|L],[a]), R = L",
     ["[]"], ["[]"]),
    ("tail bound to a non-list after the list was built",
     _f("(X = [a|T], T = b, phrase(X, L))"),
     ["type_error(list,[a|b])"], ["type_error(list,[a|b])"]),
    ("tail bound to a partial list", _f("(X = [a|T], T = [b|_], phrase(X, L))"),
     ["instantiation_error"], ["instantiation_error"]),
    ("tail bound before, nested",
     "L=[b], phrase(([a|L],[c]),[a,b,c]), R = true",
     ["true"], ["true"]),
    # ── A: a non-callable nonterminal leaf ──────────────────────────────
    ("#13 phrase(({fail},1),L)", _f("phrase(({fail},1),L)"),
     ["type_error(callable,1)"], None),
    ("#19 phrase(([a|L],1),[])", _f("phrase(([a|L],1),[])"),
     ["instantiation_error"], ["instantiation_error"]),
    ("#20 phrase((1,[a|L]),[])", _f("phrase((1,[a|L]),[])"),
     ["instantiation_error"], ["instantiation_error"]),
    ("#21 phrase((1,[a|b]),[])", _f("phrase((1,[a|b]),[])"),
     ["type_error(list,[a|b])"], ["type_error(list,[a|b])"]),
    ("#46 phrase((1,{2}),[])", _f("phrase((1,{2}),[])"),
     ["type_error(callable,1)"], None),
    ("#47 phrase(({2},1),[])", _f("phrase(({2},1),[])"),
     ["type_error(callable,1)"], None),
    ("#48 phrase((1,(2,[_|_],3),4),[])", _f("phrase((1,(2,[_|_],3),4),[])"),
     ["instantiation_error"], ["instantiation_error"]),
    ("first non-callable leaf, left to right", _f("phrase((a,(2,b;3)),[])"),
     ["type_error(callable,2)"], None),
    ("non-callable float leaf after a terminal", _f("phrase(([a],1.5),[a])"),
     ["type_error(callable,1.5)"], None),
    ("#28 phrase(\\+1,L)", _f("phrase(\\+1,L)"),
     ["type_error(callable,1)"], None),
    ("#29 phrase(([a],\\+1),[])", "phrase(([a],\\+1),[]), R = true",
     [], None),
    ("#30 phrase(([a],\\+1;[]),[])", "phrase(([a],\\+1;[]),[]), R = true",
     ["true"], None),
    ("#46 full error term", "catch(phrase((1,{2}),[]), E, R = E)",
     ["error(type_error(callable,1),phrase/2)"], None),
    ("phrase/3 full error term", "catch(phrase((g,1),[x],_), E, R = E)",
     ["error(type_error(callable,1),phrase/3)"], None),
    # ── controls: these were right before and must stay right ───────────
    ("#9 phrase(([a],[]),[a])", "phrase(([a],[]),[a]), R = true",
     ["true"], ["true"]),
    ("#14 phrase(([a];[]),L)", "phrase(([a];[]),L), length(L, R)",
     ["1", "0"], ["1", "0"]),
    ("#15 braces content is call/1's", _f("phrase({fail,1},L)"),
     ["type_error(callable,((fail,1),_=[]))"], None),
    ("#45 phrase(([a],phrase(2)),[])", "phrase(([a],phrase(2)),[]), R = true",
     [], []),
    ("nonterminal leaf", "phrase((g,[y]),L), L == [x,y], R = true",
     ["true"], ["true"]),
    ("negated terminal", "phrase((\\+[b],[a]),[a]), R = true",
     ["true"], None),
    ("phrase(1,L)", _f("phrase(1,L)"),
     ["type_error(callable,1)"], ["type_error(callable,1)"]),
    # ── ``true`` and ``false`` are not grammar control constructs (WG17 DCG,
    # Scryer): they name the nonterminals true//0 and false//0, which do not
    # exist.  It used to fail silently.  Scryer refuses ``\\+`` in a body, so
    # the negated rows are the engine's alone: ``\\+ G`` is
    # ``\\+ phrase(G, S0, _), S0 = S`` and the inner phrase/3 raises.
    ("phrase(true,[])", _f("phrase(true,[])"),
     ["existence_error(procedure,true/2)"],
     ["existence_error(procedure,true/2)"]),
    ("phrase(true,[a],R)", _f("phrase(true,[a],_)"),
     ["existence_error(procedure,true/2)"],
     ["existence_error(procedure,true/2)"]),
    ("phrase(false,[])", _f("phrase(false,[])"),
     ["existence_error(procedure,false/2)"],
     ["existence_error(procedure,false/2)"]),
    ("\\+ true raises", _f("phrase((\\+ true),[])"),
     ["existence_error(procedure,true/2)"], None),
    ("\\+ true raises under phrase/3", _f("phrase((\\+ true),[a],_)"),
     ["existence_error(procedure,true/2)"], None),
    # ── the state after a negation is S0 = S, observed through phrase/3
    ("\\+ [b] leaves the input", "phrase(\\+ [b],[a],R)",
     ['"a"'], None),
    ("g, \\+ h fails when h would match", "phrase((g, \\+ h),[x,y,z],R)",
     [], None),
    ("g, \\+ g leaves the rest", "phrase((g, \\+ g),[x,y,z],R)",
     ['"yz"'], None),
]

PROGRAM = ("g --> [x].\nh --> [y].\n"
           "cyc(T) :- X = [a|X], catch(phrase(X, _), B, true), nonvar(B),\n"
           "          B = error(type_error(T, _), _).\n"
           + "".join(f"r{i}(R) :- {body}.\n"
                     for i, (_, body, _, _) in enumerate(ROWS)))

#: Scryer expands a literal phrase/2,3 goal when it LOADS the clause, and a
#: partial terminal list makes that expansion raise and abort the consult;
#: ``call(phrase, ...)`` reaches the same phrase/2,3 at run time instead.
SCRYER_PROGRAM = (":- use_module(library(dcgs)).\n"
                  + PROGRAM.replace("phrase(", "call(phrase,"))


@pytest.fixture(scope="module")
def pl_mod(tmp_path_factory):
    d = tmp_path_factory.mktemp("dcg_body_errors")
    mp = pytest.MonkeyPatch()
    mp.setenv("CLAUSAL_PL_FRONTEND", "native")
    mp.syspath_prepend(str(d))
    name = "_dcg_body_errors_ulrich_1014"
    (d / f"{name}.pl").write_text(PROGRAM)
    sys.modules.pop(name, None)
    importlib.invalidate_caches()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")      # the rows' singletons
            mod = importlib.import_module(name)
        yield mod
    finally:
        sys.modules.pop(name, None)
        mp.undo()


@pytest.mark.parametrize("i", range(len(ROWS)), ids=[r[0] for r in ROWS])
def test_engine(pl_mod, i):
    assert _engine_answers(pl_mod, f"r{i}", 3) == ROWS[i][2]


def test_no_python_internals_in_any_answer(pl_mod):
    """Every answer is a Prolog term: nothing of the engine's Python
    representation (a SegList's ``*``, ``AttVar``, a ``SetTerm``, a class)
    reaches the text."""
    for i, (name, _, _, _) in enumerate(ROWS):
        for line in _engine_answers(pl_mod, f"r{i}", 3):
            for leak in ("AttVar", "SetTerm", "*", "<class", "'.'("):
                assert leak not in line, (name, line)


def test_oracle(scryer):
    """The rows Scryer is the reference for, against the clean Scryer build.
    The rows marked None differ by design: Scryer refuses ``\\+`` in a
    grammar body, and reports a non-callable leaf through call/1 with the
    whole translated body as the culprit, where the table's answer is the
    leaf."""
    del scryer   # the fixture only asserts the binary is there
    picked = [i for i, r in enumerate(ROWS) if r[3] is not None]
    got = _scryer_answers(SCRYER_PROGRAM, [(f"r{i}(R)", 3) for i in picked])
    assert got == [ROWS[i][3] for i in picked]


def test_cyclic_terminal_list_is_an_error_not_a_hang(pl_mod, monkeypatch):
    """``X = [a|X]`` is not a list: it is ``type_error(list, X)``, raised
    before the walk that would never end.  The ball is caught by a VARIABLE
    and taken apart afterwards: an ``error(type_error(list,_),_)`` pattern
    in the catch itself trips an engine-wide RecursionError on a ball that
    holds a cyclic term (it reproduces with a plain ``throw``), so the error
    builder is wrapped to record its culprit and to hand the ball an acyclic
    stand-in."""
    import signal
    import clausal.logic.exceptions as exc

    real = exc.type_error
    seen = []

    def spy(kind, culprit, *rest):
        seen.append(kind)
        return real(kind, "cyclic", *rest)

    monkeypatch.setattr(exc, "type_error", spy)

    def alarm(*_):
        raise TimeoutError("phrase on a cyclic list hung")

    old = signal.signal(signal.SIGALRM, alarm)
    signal.alarm(20)
    try:
        got = _engine_answers(pl_mod, "cyc", 1)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)
    assert seen == ["list"]
    assert got == ["list"]
