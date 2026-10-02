"""The one-way dependency edge at RUN TIME: routes 2-7 of the dialect gate.

Operator ruling 2026-10-01 (final): ``.pl`` may call ``.clausal``;
``.clausal`` (Clausal Prolog) may NEVER call ``.pl``.  No flag or
directive opts in; it is strict for closures too.  ``.seam`` is the Python
boundary and is NOT bound by the rule.

Route 1 (an import) is refused at load and pinned in
``tests/test_clausal_prolog_may_not_import_pl.py``.  This file pins every
other route by which a Clausal Prolog frame could reach a ``.pl``
predicate, each with the error route 1 raises -- as an ISO error term::

    error(permission_error(access, prolog_module, M), Context)

and, for a Python module target (§4b), ``python_module``.

  route 2  ``M:G`` written in a clause, ``call/N`` of a qualified goal or a
           qualified closure, ``maplist``, ``findall``, a body term, a
           ``-meta_predicate`` closure handed in by a ``.pl`` caller (the
           ONE place the rule bites the allowed direction: ``.pl`` code may
           not hand ``.clausal`` a closure into ``.pl``)
  route 3  ``assertz/asserta/retract/retractall`` of ``M:Clause``
  route 4  ``clause(M:H, B)``
  route 5  Python ``solve()``: no engine check (Python is outside the rule);
           Clausal Prolog has no ``++`` to reach Python with
  route 6  the namespace fallback (``_namespace_dispatch``): defensive
  route 7  (a)-(g), one pin each

Each NO case has its YES twin: the same route from a ``.pl`` caller into a
``.clausal`` module, and from a ``.seam`` caller into a ``.pl`` module.
"""
from __future__ import annotations

import importlib
import shutil
import sys

import pytest

from clausal import _suffixes
from clausal import import_hook as ih  # noqa: F401 -- installs the finders
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, walk


# ── fixtures ──

#: A .pl library: p/1, a dynamic f/1, a DCG nonterminal, a meta-predicate.
_PL_LIB = """:- module({m}, [p/1, greet/2]).
:- dynamic(f/1).
p(1).
p(2).
f(a).
greet --> [hi].
"""

#: The same library in Clausal Prolog.
_CP_LIB = """:- module({m}, [p/1, greet/2, app/1]).
:- dynamic(f/1).
:- meta_predicate(app(0)).
p(1).
p(2).
f(a).
greet --> [hi].
app(G) :- call(G).
:- end_module({m}).
"""

#: A runner: each route as a clause taking the term from Python, in the
#: three surfaces.
_RUN_PROLOG = """:- module({m}, [rc/1, rc/2, rmap/2, rfind/2, rnot/1,
                     ra/1, rr/1, rra/1, rcl/2, rph/2]).
rc(G) :- call(G).
rc(G, X) :- call(G, X).
rmap(G, L) :- maplist(G, L).
rfind(G, L) :- findall(G, call(G), L).
rnot(G) :- \\+ call(G).
ra(C) :- assertz(C).
rr(C) :- retract(C).
rra(H) :- retractall(H).
rcl(H, B) :- clause(H, B).
rph(G, L) :- phrase(G, L).
"""
_RUN_SEAM = """rc(G) <- call(G),
rc(G, X) <- call(G, X),
rmap(G, L) <- maplist(G, L),
ra(C) <- assertz(C),
rr(C) <- retract(C),
rra(H) <- retractall(H),
rcl(H, B) <- clause(H, B),
rph(G, L) <- phrase(G, L),
"""

DENIED = ("permission_error", "access", "prolog_module")


class Tree:
    """A temporary sys.path entry; every module written is unloaded after."""

    def __init__(self, root, monkeypatch):
        self.root = root
        self.names: list[str] = []
        monkeypatch.syspath_prepend(str(root))

    def write(self, rel: str, text: str) -> str:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        dotted = rel.rsplit(".", 1)[0].replace("/", ".")
        self.names.append(dotted)
        sys.modules.pop(dotted, None)
        return dotted

    def load(self, name: str):
        for p in self.root.rglob("__pycache__"):
            shutil.rmtree(p, ignore_errors=True)
        importlib.invalidate_caches()
        return importlib.import_module(name)

    def close(self):
        for n in self.names:
            sys.modules.pop(n, None)
        for p in self.root.rglob("__pycache__"):
            shutil.rmtree(p, ignore_errors=True)
        importlib.invalidate_caches()


@pytest.fixture
def tree(tmp_path, monkeypatch):
    assert _suffixes.CLAUSAL_PROLOG_SUFFIXES == (".clausal",)
    t = Tree(tmp_path, monkeypatch)
    yield t
    t.close()


def _runner(tree, surface: str, name: str):
    if surface == ".seam":
        tree.write(name + ".seam", _RUN_SEAM)
    else:
        text = _RUN_PROLOG.format(m=name)
        if surface == ".clausal":
            text += f":- end_module({name}).\n"
        tree.write(name + surface, text)
    return tree.load(name)


def _lib(tree, surface: str, name: str):
    tree.write(name + surface, (_PL_LIB if surface == ".pl" else _CP_LIB)
               .format(m=name))
    return tree.load(name)


def _answers(mod, pred, *args):
    """Each answer as the walked value of the LAST argument (or [] for a
    goal with none to report)."""
    out = []
    for _ in call(pred, *args, module=mod):
        out.append(walk(deref(args[-1])) if args else [])
    return out


def _denied(mod, pred, *args, kind="prolog_module", target=None):
    with pytest.raises(LogicException) as ei:
        list(call(pred, *args, module=mod))
    term = ei.value.term
    assert term[0] == "error" and term[1][:3] == (
        "permission_error", "access", kind), term
    if target is not None:
        assert term[1][3] == target, term
    return ei.value


# ── route 2: M:G and call/N ──

#: (runner predicate, args builder) -- each builds the term naming module *m*.
def _route2_cases(m):
    x = Var()
    return {
        "call/1": ("rc", lambda: ((":", m, ("p", x)),)),
        "call/2 closure": ("rc", lambda: ((":", m, "p"), Var())),
        "maplist": ("rmap", lambda: ((":", m, "p"), [1, 2])),
        "body term": ("rc", lambda: ((",", "true", (":", m, ("p", Var()))),)),
    }


_ROUTE2 = ["call/1", "call/2 closure", "maplist", "body term"]


@pytest.mark.parametrize("case", _ROUTE2)
def test_route2_clausal_prolog_may_not_call_into_pl(tree, case):
    _lib(tree, ".pl", "dgr2_pl")
    run = _runner(tree, ".clausal", "dgr2_run")
    pred, build = _route2_cases("dgr2_pl")[case]
    exc = _denied(run, pred, *build(), target="dgr2_pl")
    assert "Clausal Prolog may not call ISO Prolog (.pl)" in str(exc)


@pytest.mark.parametrize("surface", [".pl", ".seam"])
@pytest.mark.parametrize("case", _ROUTE2)
def test_route2_the_allowed_directions_still_run(tree, surface, case):
    """A ``.pl`` caller into Clausal Prolog, and a ``.seam`` caller into
    ``.pl`` (the Python boundary, the programmer's responsibility)."""
    target = ".clausal" if surface == ".pl" else ".pl"
    _lib(tree, target, "dgy2_lib")
    run = _runner(tree, surface, "dgy2_run")
    pred, build = _route2_cases("dgy2_lib")[case]
    assert list(call(pred, *build(), module=run))


def test_route2_clausal_prolog_may_call_clausal_prolog_and_seam(tree):
    _lib(tree, ".clausal", "dgy2_cp")
    tree.write("dgy2_seam.seam", "p(3),\n")
    tree.load("dgy2_seam")
    run = _runner(tree, ".clausal", "dgy2_run2")
    x = Var()
    assert _answers(run, "rc", (":", "dgy2_cp", ("p", x))) == [
        (":", "dgy2_cp", ("p", 1)), (":", "dgy2_cp", ("p", 2))]
    y = Var()
    assert [walk(deref(y)) for _ in call(
        "rc", (":", "dgy2_seam", "p"), y, module=run)] == [3]


def test_route2_innermost_module_decides(tree):
    """``m1:m2:G`` runs G in m2 (ISO): a .pl OUTER name with a Clausal
    Prolog module innermost is allowed, the reverse is not."""
    _lib(tree, ".pl", "dgn_pl")
    _lib(tree, ".clausal", "dgn_cp")
    run = _runner(tree, ".clausal", "dgn_run")
    assert list(call("rc", (":", "dgn_pl", (":", "dgn_cp", ("p", Var()))),
                     module=run))
    _denied(run, "rc", (":", "dgn_cp", (":", "dgn_pl", ("p", Var()))),
            target="dgn_pl")


@pytest.mark.parametrize("pl_first", [True, False])
def test_route2_a_written_qualified_call_is_refused(tree, pl_first):
    """``dgw_pl:p(X)`` WRITTEN in a Clausal Prolog clause: the native front
    end lowers it to a dotted call, resolved when the clause set compiles
    (the .pl module already loaded) or when it runs (loaded afterwards).
    Both are refused, and catch/3 sees the error term."""
    if pl_first:
        _lib(tree, ".pl", "dgw_pl")
    tree.write("dgw_cp.clausal",
               ":- module(dgw_cp, [q/1, c/1]).\nq(X) :- dgw_pl:p(X).\n"
               "c(E) :- catch(dgw_pl:p(_), error(E, _), true).\n"
               ":- end_module(dgw_cp).\n")
    cp = tree.load("dgw_cp")
    if not pl_first:
        _lib(tree, ".pl", "dgw_pl")
    _denied(cp, "q", Var(), target="dgw_pl")
    e = Var()
    assert [walk(deref(e)) for _ in call("c", e, module=cp)] == [
        ("permission_error", "access", "prolog_module", "dgw_pl")]


def test_route2_a_pl_module_may_write_a_qualified_call_into_clausal(tree):
    _lib(tree, ".clausal", "dgw_cp2")
    tree.write("dgw_pl2.pl",
               ":- module(dgw_pl2, [q/1]).\n:- use_module(dgw_cp2, [p/1]).\n"
               "q(X) :- dgw_cp2:p(X).\n")
    assert _answers(tree.load("dgw_pl2"), "q", Var()) == [1, 2]


def test_route2_a_pl_closure_handed_to_a_clausal_meta_predicate(tree):
    """THE ONE PLACE THE RULE BITES THE ALLOWED DIRECTION (ruled: strict for
    closures too).  ``.pl`` may call a Clausal Prolog meta-predicate, but
    the closure it hands over is qualified with the CALLER's module
    (``-meta_predicate``), so running it from the Clausal Prolog frame is a
    call into ``.pl`` -- refused.  A closure naming a Clausal Prolog
    predicate is fine."""
    _lib(tree, ".clausal", "dgm_cp")
    tree.write("dgm_pl.pl",
               ":- module(dgm_pl, [mine/0, theirs/0]).\n"
               ":- use_module(dgm_cp, [app/1]).\n"
               "own.\n"
               "mine :- app(own).\n"
               "theirs :- app(dgm_cp:p(1)).\n")
    pl = tree.load("dgm_pl")
    _denied(pl, "mine", target="dgm_pl")
    assert list(call("theirs", module=pl))


def test_route2_a_python_module_target_is_refused(tree):
    """§4b: Clausal Prolog reaches Python only through a .seam module."""
    import json  # noqa: F401 -- any loaded Python module
    run = _runner(tree, ".clausal", "dgpy_run")
    _denied(run, "rc", (":", "json", ("dumps", 1, Var())),
            kind="python_module", target="json")


# ── route 3: assert / retract into M ──


@pytest.mark.parametrize("pred,term", [
    ("ra", lambda m: (":", m, ("f", "z"))),
    ("rr", lambda m: (":", m, ("f", "a"))),
    ("rra", lambda m: (":", m, ("f", Var()))),
])
def test_route3_clausal_prolog_may_not_write_a_pl_module(tree, pred, term):
    pl = _lib(tree, ".pl", "dgr3_pl")
    run = _runner(tree, ".clausal", "dgr3_run")
    _denied(run, pred, term("dgr3_pl"), target="dgr3_pl")
    x = Var()
    assert [walk(deref(x)) for _ in call("f", x, module=pl)] == ["a"]


@pytest.mark.parametrize("surface", [".pl", ".seam"])
def test_route3_the_allowed_directions_still_write(tree, surface):
    target = ".clausal" if surface == ".pl" else ".pl"
    lib = _lib(tree, target, "dgy3_lib")
    run = _runner(tree, surface, "dgy3_run")
    assert list(call("ra", (":", "dgy3_lib", ("f", "z")), module=run))
    assert list(call("rr", (":", "dgy3_lib", ("f", "a")), module=run))
    x = Var()
    assert [walk(deref(x)) for _ in call("f", x, module=lib)] == ["z"]
    assert list(call("rra", (":", "dgy3_lib", ("f", Var())), module=run))
    assert not list(call("f", Var(), module=lib))


# ── route 4: clause(M:H, B) ──


def test_route4_clausal_prolog_may_not_read_a_pl_clause(tree):
    _lib(tree, ".pl", "dgr4_pl")
    run = _runner(tree, ".clausal", "dgr4_run")
    _denied(run, "rcl", (":", "dgr4_pl", ("f", Var())), Var(),
            target="dgr4_pl")


@pytest.mark.parametrize("surface", [".pl", ".seam"])
def test_route4_the_allowed_directions_still_read(tree, surface):
    target = ".clausal" if surface == ".pl" else ".pl"
    _lib(tree, target, "dgy4_lib")
    run = _runner(tree, surface, "dgy4_run")
    b = Var()
    assert _answers(run, "rcl", (":", "dgy4_lib", ("f", "a")), b) in (
        ["true"], [True])


# ── route 7(d): phrase(M:NT, L) ──


def test_route7d_phrase_into_a_pl_module_is_refused(tree):
    _lib(tree, ".pl", "dgr7d_pl")
    run = _runner(tree, ".clausal", "dgr7d_run")
    _denied(run, "rph", (":", "dgr7d_pl", "greet"), Var(), target="dgr7d_pl")


@pytest.mark.parametrize("surface", [".pl", ".seam"])
def test_route7d_phrase_the_allowed_directions(tree, surface):
    target = ".clausal" if surface == ".pl" else ".pl"
    _lib(tree, target, "dgy7d_lib")
    run = _runner(tree, surface, "dgy7d_run")
    assert _answers(run, "rph", (":", "dgy7d_lib", "greet"), Var()) == [["hi"]]


# ── route 5: Python solve() and ``++`` ──


def test_route5_python_solve_is_not_gated(tree):
    """Python-side ``solve()``/``call()`` naming a .pl module with a Clausal
    Prolog module as ``module=`` is Python calling Prolog: no engine check
    by ruling (the programmer's responsibility)."""
    _lib(tree, ".pl", "dgr5_pl")
    cp = _lib(tree, ".clausal", "dgr5_cp")
    x = Var()
    from clausal.logic.solve import solve
    assert [walk(deref(x)) for _ in solve((":", "dgr5_pl", ("p", x)),
                                          module=cp)] == [1, 2]


@pytest.mark.parametrize("body,why", [
    ("X = ++foo", "Expected '.'"),       # ``++`` is no prefix operator
])
def test_route5_clausal_prolog_has_no_plusplus_escape(tree, body, why):
    tree.write("dgr5pp.clausal", f":- module(dgr5pp, [q/1]).\nq(X) :- {body}."
               "\n:- end_module(dgr5pp).\n")
    with pytest.raises(SyntaxError) as ei:
        tree.load("dgr5pp")
    assert why in str(ei.value)


def test_route5_plusplus_written_as_a_compound_is_no_escape(tree):
    """``++(E)`` in canonical form is the ordinary compound ``'++'(E)``: in
    arithmetic it is the evaluable ``(++)/1``, which does not exist."""
    tree.write("dgr5pq.clausal", ":- module(dgr5pq, [q/1]).\n"
               "q(X) :- X is ++(1 + 1).\n:- end_module(dgr5pq).\n")
    with pytest.raises(LogicException) as ei:
        list(call("q", Var(), module=tree.load("dgr5pq")))
    assert ei.value.term[1] == ("type_error", "evaluable", ("/", "++", 1))


# ── route 6: the namespace fallback (defensive) ──


def test_route6_a_pl_predicate_python_put_into_a_namespace(tree):
    """Only Python can bind a .pl predicate into a Clausal Prolog module's
    namespace (route 1 refuses the import); the run-time lookup that finds
    it there still refuses it, by the dialect of its home row's module."""
    pl = _lib(tree, ".pl", "dgr6_pl")
    run = _runner(tree, ".clausal", "dgr6_run")
    run.__dict__["p"] = pl.__dict__["p"]
    _denied(run, "rc", "p", Var(), target="dgr6_pl")


def test_route6_a_seam_module_namespace_is_not_gated(tree):
    pl = _lib(tree, ".pl", "dgy6_pl")
    run = _runner(tree, ".seam", "dgy6_run")
    run.__dict__["p"] = pl.__dict__["p"]
    assert _answers(run, "rc", "p", Var()) == [1, 2]


# ── route 7: the audit list, one pin each ──


def test_route7a_import_module_is_not_clausal_prolog(tree):
    """(a) the seam's ``-import_module(m)`` + dotted ``m.p(...)``: not a
    Clausal Prolog directive, so the route does not exist there."""
    tree.write("dg7a.clausal", ":- module(dg7a, [q/1]).\n"
               ":- import_module(os).\nq(1).\n:- end_module(dg7a).\n")
    with pytest.raises(SyntaxError) as ei:
        tree.load("dg7a")
    assert "unknown directive import_module/1" in str(ei.value)


def test_route7b_a_library_reaches_engine_code_and_is_allowed(tree):
    """(b) ``library(reif)`` resolves to engine code (a .seam module or the
    builtins), never a .pl: allowed."""
    tree.write("dg7b.clausal", ":- module(dg7b, [q/1]).\n"
               ":- use_module(library(reif), [if_/3]).\n"
               "q(X) :- if_(1 = 1, X = y, X = n).\n:- end_module(dg7b).\n")
    assert _answers(tree.load("dg7b"), "q", Var()) == ["y"]


def test_route7c_the_py_redirect_is_refused_at_load(tree):
    """(c) ``use_module(py/datetime, ...)`` reaches a Python adapter: refused
    at load (§4b), pointing at the library facade."""
    tree.write("dg7c.clausal", ":- module(dg7c, [q/1]).\n"
               ":- use_module(py/datetime, [date_add/3]).\nq(1).\n"
               ":- end_module(dg7c).\n")
    with pytest.raises(SyntaxError) as ei:
        tree.load("dg7c")
    assert "permission_error(access, python_module, py.datetime)" in str(
        ei.value)


def test_route7e_term_expansion_is_not_applied_to_clausal_prolog(tree):
    """(e) the native front end has no term_expansion: a Clausal Prolog
    ``term_expansion/2`` is an ordinary predicate, nothing rewrites the
    module's clauses, so no expansion can smuggle in another dialect."""
    tree.write("dg7e.clausal", ":- module(dg7e, [q/1, term_expansion/2]).\n"
               "term_expansion(r(X), q(X)).\nr(7).\nq(1).\n"
               ":- end_module(dg7e).\n")
    assert _answers(tree.load("dg7e"), "q", Var()) == [1]


def test_route7f_a_tabled_predicate_is_gated_like_any_other(tree):
    """(f) tabling wraps a row's own dispatch: a tabled Clausal Prolog
    predicate calling into .pl is refused like an untabled one."""
    _lib(tree, ".pl", "dg7f_pl")
    tree.write("dg7f.clausal", ":- module(dg7f, [q/1]).\n:- table(q/1).\n"
               "q(X) :- dg7f_pl:p(X).\n:- end_module(dg7f).\n")
    _denied(tree.load("dg7f"), "q", Var(), target="dg7f_pl")


def test_route7g_the_exporter_emits_pl_the_allowed_direction():
    """(g) the exporter writes .pl FROM Clausal source -- the allowed
    direction; it has no route back."""
    from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
    assert "p(1)." in clausal_source_to_prolog("p(1),\n")
