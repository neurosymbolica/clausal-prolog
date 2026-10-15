"""retract/1 and clause/2 (ISO 8.9.3, 8.8.1): a clause's own body can call
ANY predicate -- declared or not, static or dynamic -- without the
construction that reads the body back for matching caring which.

Found 2026-10-15 via Ciao's ``iso_tests`` (``retract_test3``/``retract_test4``
in Ulrich Neumerkel's corpus, run against Clausal's native ``.pl`` frontend):
``retract((p(X, 2) :- T))`` raised ``permission_error(access,
private_procedure, p/2)`` whenever ``T`` unified with a call to ``bird/1``
-- a LOCAL, UNEXPORTED, static predicate (``bird(_) :- fail.``, no
``-dynamic``, no export) -- but not when it called a dynamic one or an
undefined one.  ``clause/2`` (which shares the same body-reconstruction
machinery, ``clause_ops.clause_terms``) showed the identical split.

ROOT CAUSE: ``clause_ops._needs_cell`` decides whether an ordinary call
inside the body must be explicitly rewritten to the cell it denotes
(``TupleLiteral`` -> ``("p", Args...)``) before the body is recompiled as a
construction query, or whether the general compiler already builds that
cell on its own.  The latter needs the functor to have a DECLARATION
(an export list, ``-private``, or ``-dynamic``) giving it a signature;
without one, construction through an ordinary ``Call`` node raises
``existence_error(procedure, ...)`` ("nothing declares the functor")
instead of building the cell -- read by both ``retract/1`` and ``clause/2``
as "this clause has no term form", and refused with the private-procedure
permission error: a refusal nominally about the CLAUSE BEING INSPECTED,
actually triggered by an undeclared, incidental property of what its body
happens to call.  An EXPORTED or IMPORTED static predicate already has a
declaration elsewhere and read back fine even before this fix; only a
local, unexported static one didn't.

Fixed in ``_needs_cell`` by also requiring the rewrite for a right-arity
binding whose row is locked and not dynamic -- a superset of "undeclared"
(it also, harmlessly, rewrites an exported/imported static callee, which
builds the identical cell construction would have built on its own) that
needs no new way to ask the compiler for a functor's declaration.

retract/1's permission check must depend only on the clause being
retracted -- its own head functor/arity, and whether that functor is a
protected control-construct/static/grammar-rule indicator -- never on what
a defined, callable, well-formed body happens to invoke.

A zero-arity callee needed its own fix in ``_spell_as_cells``: wrapping it
in a ``TupleLiteral`` of one element built the reserved 1-tuple
``("zst",)``, not the atom ``zst`` -- a pre-existing bug that only a 0-arity
LOCAL predicate could reach before this change made every local static
predicate (0-arity included) take this path for the first time.
"""
from __future__ import annotations

import itertools
import textwrap
import warnings

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.cells import cell_args, cell_functor
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import solve
from clausal.logic.variables import Var, deref
from clausal.terms import term_writeq

_N = itertools.count()


def _load(tmp_path, monkeypatch, pl_src: str, name: str | None = None):
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", "native")
    name = name or f"retract_static_body{next(_N)}"
    path = tmp_path / f"{name}.pl"
    path.write_text(textwrap.dedent(pl_src))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # singleton-variable lint
        return _load_module(name, str(path))


def _first_term(mod, goal_name: str):
    """``deref`` of the one answer ``goal_name(R)`` binds *R* to, or raise
    if it fails (there must be exactly one, or the test is wrong)."""
    r = Var()
    for _ in itertools.islice(solve((goal_name, r), mod), 1):
        return deref(r)
    raise AssertionError(f"{goal_name}/1 failed; expected one solution")


def _answers(mod, goal_name: str, limit: int = 5) -> list[str]:
    r = Var()
    out = []
    for _ in itertools.islice(solve((goal_name, r), mod), limit):
        out.append(term_writeq(deref(r), local_vars=True))
    return out


def _raises(mod, goal_name: str) -> tuple:
    r = Var()
    with pytest.raises(LogicException) as info:
        list(itertools.islice(solve((goal_name, r), mod), 1))
    return deref(info.value.term)


# The Ciao/ISO corpus program, trimmed to the two predicates under test:
# ``animal/1`` and ``bird/1`` are LOCAL, UNEXPORTED and static (no
# ``-dynamic``), always fail, and are the thing the retracted clauses'
# bodies call; ``p_insect/1`` is DYNAMIC, the known-green control that must
# keep working either way.
_SRC = """
animal(_) :- fail.
bird(_) :- fail.

:- dynamic(p_insect/1).
p_insect(ant).
p_insect(bee).

:- dynamic(legs/2).
legs(A, 4) :- animal(A).
legs(A, 6) :- p_insect(A).
legs(spider, 8).
legs(B, 2) :- bird(B).

retract_static(X, T) :- retract((legs(X, 2) :- T)).
retract_static_wrap(R) :- retract_static(X, T), T = bird(X), R = X-T.
retract_all_bodies(Result) :-
    findall([X, Y, Z], retract((legs(X, Y) :- Z)), Result).

clause_static(B) :- clause(legs(_, 4), B).
clause_dynamic(B) :- clause(legs(_, 6), B).
"""


@pytest.fixture
def mod(tmp_path, monkeypatch):
    return _load(tmp_path, monkeypatch, _SRC)


def test_retract_body_calling_static_predicate_succeeds(mod):
    """retract_test3 (Ciao/Ulrich): the clause ``legs(B, 2) :- bird(B)`` is
    retracted and the pattern binds, though its body calls the LOCAL,
    UNEXPORTED static ``bird/1`` -- it must not raise
    permission_error(access, private_procedure, legs/2)."""
    result = _first_term(mod, "retract_static_wrap")
    # R = X-T with T = bird(X): a structural check (not a string split) --
    # the top functor is '-', its second argument is bird/1 applied to
    # exactly the same variable as the first argument.
    assert cell_functor(result) == "-"
    x_val, t_val = (deref(a) for a in cell_args(result))
    assert cell_functor(t_val) == "bird"
    (bird_arg,) = cell_args(t_val)
    assert deref(bird_arg) is deref(x_val)


def test_retract_all_bodies_regardless_of_callee(mod):
    """retract_test4 (Ciao/Ulrich): retracting every clause of legs/2 and
    collecting (Head-args, Body) must see all four -- the two whose body
    calls a LOCAL UNEXPORTED static predicate (animal/1, bird/1), the one
    calling the DYNAMIC p_insect/1, and the plain fact -- identically."""
    got = _answers(mod, "retract_all_bodies", limit=1)
    assert len(got) == 1
    # Order follows the clause list; bird/1's clause is last in the source.
    assert got[0] == (
        "[[_1,4,animal(_1)],[_2,6,p_insect(_2)],[spider,8,true],"
        "[_3,2,bird(_3)]]"
    )


def test_clause_2_shares_the_fix(mod):
    """clause/2 shares clause_ops.clause_terms with retract/1: the same
    construction powers both, so the same static-callee body must answer
    here too, not raise."""
    assert _answers(mod, "clause_static") == ["animal(_)"]
    assert _answers(mod, "clause_dynamic") == ["p_insect(_)"]


def test_static_callee_is_never_actually_invoked(tmp_path, monkeypatch):
    """The fix must read the body back as a TERM, not run it: a predicate
    the retracted clause's body calls must see no call at all -- no
    increment of a counter it would otherwise bump."""
    src = """
    :- dynamic(counter/1).
    counter(0).
    bump :- retract(counter(N)), N1 is N + 1, assertz(counter(N1)).
    watched(_) :- bump, fail.
    :- dynamic(p/2).
    p(A, 4) :- watched(A).
    run(B) :- retract((p(_, 4) :- B)).
    """
    mod = _load(tmp_path, monkeypatch, src)
    got = _answers(mod, "run", limit=1)
    assert got == ["watched(_)"]
    assert _answers(mod, "counter", limit=1) == ["0"]


def test_control_construct_refusal_still_applies(tmp_path, monkeypatch):
    """The pre-existing refusals this session's earlier fixes added must
    not regress: retracting a control-construct head is still
    permission_error(modify, static_procedure, ...)."""
    src = "run(B) :- retract(((a, b) :- true))."
    mod = _load(tmp_path, monkeypatch, src)
    term = _raises(mod, "run")
    assert term[0] == "error"
    assert term[1][:3] == ("permission_error", "modify", "static_procedure")


def test_dcg_rule_functor_still_refused_on_retract(tmp_path, monkeypatch):
    """And the ``(-->)/2`` grammar-rule refusal from this session's earlier
    commits (da0ffcd9/cb76ec73) must not regress either."""
    src = "run(B) :- retract((a --> b))."
    mod = _load(tmp_path, monkeypatch, src)
    term = _raises(mod, "run")
    assert term[0] == "error"
    assert term[1][:3] == ("permission_error", "modify", "static_procedure")
    assert term[1][3] == ("/", "-->", 2)


# ── F1 regression: a zero-arity callee ──────────────────────────────────────


def test_zero_arity_static_callee_reads_back_as_the_atom(tmp_path, monkeypatch):
    """``t(2, _) :- zst.`` with ``zst/0`` a LOCAL, UNEXPORTED, static
    (always-failing) predicate: the body must read back as the plain atom
    ``zst``, matching Scryer (``R = zst``) -- not raise a Python
    ``TypeError`` from building the reserved 1-tuple ``('zst',)``
    (``_spell_as_cells`` wrapped every 0-arity callee this way until this
    fix, and this change was the first to route a LOCAL static one there)."""
    src = """
    zst :- fail.
    :- dynamic(t/2).
    t(2, _) :- zst.
    c2(R) :- clause(t(2,_), R).
    r2(R) :- retract((t(2,_) :- R)).
    """
    mod = _load(tmp_path, monkeypatch, src)
    assert _answers(mod, "c2", limit=1) == ["zst"]
    # retract/1 goes through the identical body-reconstruction path.
    mod2 = _load(tmp_path, monkeypatch, src)
    assert _answers(mod2, "r2", limit=1) == ["zst"]


def test_zero_arity_undefined_callee_reads_back_as_the_atom(tmp_path, monkeypatch):
    """The same 1-tuple bug was already reachable, on base, for an
    UNDEFINED 0-arity callee (``_needs_cell`` was already True there before
    this change); the ``_spell_as_cells`` fix cures that case too, the same
    way."""
    src = """
    :- dynamic(t/2).
    t(1, _) :- undefined0.
    c1(R) :- clause(t(1,_), R).
    """
    mod = _load(tmp_path, monkeypatch, src)
    assert _answers(mod, "c1", limit=1) == ["undefined0"]


# ── F3: a static callee nested in a control construct ───────────────────────


_CONTROL_SRC = """
animal(_) :- fail.
:- dynamic(p_insect/1).
p_insect(ant).
:- dynamic(legs/2).
legs(A, disj) :- (animal(A) ; p_insect(A)).
legs(A, neg) :- \\+ animal(A).
legs(A, fa) :- findall(A, animal(A), _).
legs(A, ca) :- catch(animal(A), _, true).
legs(A, fo) :- forall(animal(A), true).
legs(A, conj) :- animal(A), p_insect(A).
cd(B) :- clause(legs(_, disj), B).
cn(B) :- clause(legs(_, neg), B).
cf(B) :- clause(legs(_, fa), B).
cca(B) :- clause(legs(_, ca), B).
cfo(B) :- clause(legs(_, fo), B).
cc(B) :- clause(legs(_, conj), B).
ud(B) :- clause(legs(A, disj), B), B = (animal(A) ; p_insect(A)).
un(B) :- clause(legs(A, neg), B), B = (\\+ animal(A)).
uc(B) :- clause(legs(A, conj), B), B = (animal(A), p_insect(A)).
"""


@pytest.fixture
def control_mod(tmp_path, monkeypatch):
    return _load(tmp_path, monkeypatch, _CONTROL_SRC)


@pytest.mark.parametrize("goal, expected", [
    ("cd", "animal(_1);p_insect(_1)"),
    ("cn", "\\+animal(_)"),
    ("cf", "findall(_1,animal(_1),_)"),
    ("cca", "catch(animal(_),_,true)"),
    ("cfo", "forall(animal(_),true)"),
])
def test_static_callee_inside_a_control_construct(control_mod, goal, expected):
    """On base, a LOCAL static callee anywhere under ``;``, ``\\+``,
    ``findall``, ``catch`` or ``forall`` hit the same permission_error as a
    bare call; this fix cures all of them, the same way as the bare case."""
    assert _answers(control_mod, goal, limit=1) == [expected]


def test_static_callee_inside_a_conjunction(control_mod):
    """A conjunction body reads back as the ISO term ``','(A, B)`` -- the
    body as read, as clause/2 hands it back in Scryer -- and each conjunct
    is the expected call, sharing the head's variable."""
    result = _first_term(control_mod, "cc")
    assert cell_functor(result) == ","
    left, right = (deref(e) for e in cell_args(result))
    assert cell_functor(left) == "animal"
    assert cell_functor(right) == "p_insect"
    assert deref(cell_args(left)[0]) is deref(cell_args(right)[0])


@pytest.mark.parametrize("goal, expected", [
    ("ud", "animal(_1);p_insect(_1)"),
    ("un", "\\+animal(_)"),
    ("uc", "animal(_1),p_insect(_1)"),
])
def test_control_body_unifies_with_the_body_as_written(control_mod, goal,
                                                       expected):
    """Pure unification against the body as WRITTEN, over the head's own
    variable: ``clause(legs(A, K), B), B = <written body>`` succeeds once.
    Checked against Scryer (the same program and unifications succeed
    there; ``or/2`` and ``not/1`` do not unify with what it hands back)."""
    assert _answers(control_mod, goal, limit=2) == [expected]


# ── F3: an exported / imported static callee keeps working (control) ───────


def test_exported_static_callee_still_works(tmp_path, monkeypatch):
    """A static predicate EXPORTED from its own module already has a
    declaration (the export list) and read back fine before this fix; the
    row-based rewrite this fix adds is a superset that also rewrites it,
    harmlessly, to the identical cell -- confirm it still does."""
    src = """
    :- module(exp_static_mod, [ani/1, c1/1]).
    ani(_) :- fail.
    :- dynamic(t/2).
    t(1, B) :- ani(B).
    c1(R) :- clause(t(1,_), R).
    """
    mod = _load(tmp_path, monkeypatch, src, name="exp_static_mod")
    assert _answers(mod, "c1", limit=1) == ["ani(_)"]


def test_imported_static_callee_still_works(tmp_path, monkeypatch):
    """A static predicate IMPORTED from another module (``-use_module``)
    is declared there; it already read back fine on base too, through the
    adopted row.  Same control as the exported case, across two files."""
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", "native")
    monkeypatch.syspath_prepend(str(tmp_path))
    lib_name = f"implib{next(_N)}"
    (tmp_path / f"{lib_name}.pl").write_text(textwrap.dedent(f"""
    :- module({lib_name}, [ani/1]).
    ani(_) :- fail.
    """))
    imp_name = f"impmod{next(_N)}"
    imp_path = tmp_path / f"{imp_name}.pl"
    imp_path.write_text(textwrap.dedent(f"""
    :- use_module({lib_name}, [ani/1]).
    :- dynamic(t/2).
    t(1, B) :- ani(B).
    c1(R) :- clause(t(1,_), R).
    """))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mod = _load_module(imp_name, str(imp_path))
    assert _answers(mod, "c1", limit=1) == ["ani(_)"]
