"""A partial list's tail bound to a non-list is an IMPROPER tail (D50,
2026-10-13).

``X = [a|T], T = foo`` gave ``"afoo"`` -- since atoms became ``str``, the
partial list's walk read the atom bound to its hole as TEXT and spliced its
characters -- and ``L = [x|V], V = 1`` raised PartialTermError.  Bound
BEFORE the list was built, ``T = foo, X = [a|T]`` gave ``[a,foo]`` (the
translator) or ``[a,f,o,o]``.  ISO, Scryer and Trealla give ``[a|foo]`` and
``[x|1]``: the cons cells ``'.'(H, T)`` the native reader builds.  A tail
that is a list, ``[]`` or text still makes a proper list.

``assertz`` of a partial list (``assertz(r([a|T]))``) raised
NotImplementedError, and stored the caller's hole variable.

Every expected line below is what Scryer and Trealla print.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

PROGRAM = """\
:- set_prolog_flag(double_quotes, {dq}).
v(atom, foo).
v(num, 1).
v(cmp, f(b)).
v(nil, []).
v(lst, [b,c]).
v(cons, [b|c]).
v(str, "bc").
after(K, X) :- X = [a|T], v(K, V), T = V.
before(K, X) :- v(K, V), T = V, X = [a|T].
calld(K, X) :- call(after, K, X).
fa(K, X) :- findall(Y, after(K, Y), [X]).
fb(K, X) :- findall(Y, before(K, Y), [X]).
two(K, X) :- X = [a,b|T], v(K, V), T = V.
show(P) :- v(K, _), call(P, K, X), writeq(P-K-X), nl, fail.
show(_).
main :- show(after), show(before), show(calld), show(fa), show(fb), show(two).
"""

TAILS = {"atom": "|foo]", "num": "|1]", "cmp": "|f(b)]", "nil": "]",
         "lst": ",b,c]", "cons": ",b|c]"}
STR_TAIL = {"chars": ",b,c]", "codes": ",98,99]", "atom": "|bc]"}


def _expected(dq):
    out = []
    for p in ("after", "before", "calld", "fa", "fb", "two"):
        head = "[a,b" if p == "two" else "[a"
        for k in ("atom", "num", "cmp", "nil", "lst", "cons", "str"):
            tail = STR_TAIL[dq] if k == "str" else TAILS[k]
            out.append(f"{p}-{k}-{head}{tail}")
    return out


FRONT_ENDS = [("prog.pl", "translator"), ("prog.pl", "native"),
              ("prog.clausal", None)]


def _run(tmp_path, name, frontend, source, *argv):
    (tmp_path / name).write_text(source)
    env = dict(os.environ)
    env.pop("CLAUSAL_PL_FRONTEND", None)
    if frontend:
        env["CLAUSAL_PL_FRONTEND"] = frontend
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-W", "ignore", "-m", "clausal", *argv, name],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)


@pytest.mark.parametrize("front", FRONT_ENDS, ids=lambda f: f[1] or "clausal")
@pytest.mark.parametrize("dq", ["chars", "codes", "atom"])
def test_a_hole_bound_to_a_non_list_is_the_tail(tmp_path, dq, front):
    r = _run(tmp_path, *front, PROGRAM.format(dq=dq))
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines() == _expected(dq), r.stdout


G_SOURCE = """\
:- dynamic(r/1).
hd([H|T], H, T).
"""


@pytest.mark.parametrize("front", FRONT_ENDS, ids=lambda f: f[1] or "clausal")
@pytest.mark.parametrize("goal, out", [
    ("X = [a|T], T = foo, writeq(X)", "[a|foo]"),
    ("T = foo, X = [a|T], writeq(X)", "[a|foo]"),
    ("L = [x|V], V = 1, writeq(L)", "[x|1]"),
    ("X = [a,b|T], T = 1, X = [_|R], writeq(R)", "[b|1]"),
    ("X = [a|T], T = foo, X == [a|foo], writeq(yes)", "yes"),
    ("X = [a|T], T = foo, X \\== [a,f,o,o], writeq(yes)", "yes"),
    ("X = [a|T], T = foo, X \\= [a,f,o,o], writeq(yes)", "yes"),
    ("X = [a|T], T = foo, hd(X, H, R), writeq(H-R)", "a-foo"),
    ("append([x], V, L), V = foo, L == [x|foo], writeq(L)", "[x|foo]"),
    ("X = [a|T], T = foo, \\+ length(X, _), writeq(yes)", "yes"),
    ("X = [a|T], T = foo, \\+ is_list(X), writeq(yes)", "yes"),
    ("X = [a|T], T = [], is_list(X), writeq(X)", "[a]"),
    ("X = [a|T], T = foo, copy_term(X, Y), writeq(Y)", "[a|foo]"),
    ("X = [a|T], T = foo, catch(msort(X, _), error(E, _), true), writeq(E)",
     "type_error(list,[a|foo])"),
    # assertz copies a partial list: the stored hole is not the caller's.
    ("assertz(r([a|T])), r([_|R]), \\+ R == T, writeq(yes)", "yes"),
    ("assertz(r([a|T])), r(Y), Y = [a,b], var(T), writeq(Y)", "[a,b]"),
])
def test_g_partial_list_tails(tmp_path, front, goal, out):
    r = _run(tmp_path, *front, G_SOURCE, "--once", "-g", goal + ", nl")
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines()[0] == out, r.stdout


# ── Fix round 2 (2026-10-13): every list builtin reads a hole-built improper
# list as the literal, and a cyclic partial list no longer raises. ─────────

AUDIT = """\
:- use_module(library(lists)).
mk(X) :- X = [a|T], T = foo.
mkl(X) :- X = [a|foo].
mkn(X) :- X = [1|T], T = foo.
mknl(X) :- X = [1|foo].
r(Tag, O, G) :- catch(findall(O, G, L), error(E, _), L = err(E)), writeq(Tag-L), nl.
t(P, N) :-
  r(memberchk, x, (call(P, X), memberchk(a, X))),
  r(member, M, (call(P, X), member(M, X))),
  r(append_split, A-B, (call(P, X), append(A, B, X))),
  r(append_foo, Q, (call(P, X), append(Q, foo, X))),
  r(append_front, Z, (call(P, X), append([z], X, Z))),
  r(length, x, (call(P, X), length(X, _))),
  r(nth0_0, E, (call(P, X), nth0(0, X, E))),
  r(nth0_1, E, (call(P, X), nth0(1, X, E))),
  r(nth1_1, E, (call(P, X), nth1(1, X, E))),
  r(nth0_var, I-E, (call(P, X), nth0(I, X, E))),
  r(nth0_4, E-R, (call(P, X), nth0(0, X, E, R))),
  r(last, La, (call(P, X), last(X, La))),
  r(msort, S, (call(P, X), msort(X, S))),
  r(sort, S, (call(P, X), sort(X, S))),
  r(sum_list, S, (call(N, X), sum_list(X, S))),
  r(reverse, S, (call(P, X), reverse(X, S))),
  r(select, S-R, (call(P, X), select(S, X, R))),
  r(univ, T, (call(P, X), T =.. X)),
  r(univ_f, T, (call(P, X), T =.. [f|X])),
  r(atom_codes, T, (call(P, X), atom_codes(T, X))),
  r(atom_chars, T, (call(P, X), atom_chars(T, X))),
  r(number_codes, T, (call(P, X), number_codes(T, X))).
main :- write('--mk'), nl, t(mk, mkn), write('--mkl'), nl, t(mkl, mknl).
"""

# Trealla's answers (Scryer's too, where its library has the predicate).
AUDIT_EXPECTED = [
    "memberchk-[x]",
    "member-[a]",
    "append_split-[[]-[a|foo],[a]-foo]",
    "append_foo-[[a]]",
    "append_front-[[z,a|foo]]",
    "length-[]",
    "nth0_0-[a]",
    "nth0_1-[]",
    "nth1_1-[a]",
    "nth0_var-[0-a]",
    "nth0_4-[a-foo]",
    "last-[]",
    "msort-err(type_error(list,[a|foo]))",
    "sort-err(type_error(list,[a|foo]))",
    "sum_list-[]",
    "reverse-[]",
    "select-[a-foo]",
    "univ-err(type_error(list,[a|foo]))",
    "univ_f-err(type_error(list,[f,a|foo]))",
    "atom_codes-err(type_error(list,[a|foo]))",
    "atom_chars-err(type_error(list,[a|foo]))",
    "number_codes-err(type_error(list,[a|foo]))",
]

# The translator cannot load the audit program itself (findall over a
# variable goal is refused there); the builtins are shared by every front end.
AUDIT_FRONT_ENDS = [("prog.pl", "native"), ("prog.clausal", None)]


@pytest.mark.parametrize("front", AUDIT_FRONT_ENDS,
                         ids=lambda f: f[1] or "clausal")
def test_list_builtins_read_a_hole_built_improper_list_as_the_literal(
        tmp_path, front):
    r = _run(tmp_path, *front, AUDIT, "--once", "-g", "main")
    assert r.returncode == 0, r.stderr
    lines = [ln for ln in r.stdout.splitlines() if ln != "true."]
    assert lines == ["--mk", *AUDIT_EXPECTED, "--mkl", *AUDIT_EXPECTED], lines


CYCLIC = """\
c1 :- X = [a|X], X = [H|_], write(H), nl.
c2 :- X = [a|X], Y = [b|Y], \\+ X = Y, write(yes), nl.
c3 :- X = [a|X], Y = [b|Y], \\+ X == Y, write(yes), nl.
c4 :- X = [a|X], \\+ X == [a], write(yes), nl.
c5 :- X = [a|X], \\+ X = foo, write(yes), nl.
c6 :- X = [a|X], X = [_,_,_|_], write(yes), nl.
c7 :- X = [a|X], \\+ is_list(X), write(yes), nl.
c8 :- X = [a|X], X == X, write(yes), nl.
c10 :- X = f(X), X == X, write(yes), nl.
c12 :- X = [a|X], memberchk(a, X), write(yes), nl.
c13 :- X = [a|X], \\+ X = [], write(yes), nl.
main :- c1, c2, c3, c4, c5, c6, c7, c8, c10, c12, c13.
"""


@pytest.mark.parametrize("front", FRONT_ENDS, ids=lambda f: f[1] or "clausal")
def test_cyclic_lists_and_terms(tmp_path, front):
    # Scryer and Trealla: every probe succeeds (c1 prints a).  At the fix
    # range's first head, c5 raised "RecursionError: cyclic partial list".
    # (== on two DISTINCT cyclic terms is not here: it raises, as on base;
    # see test_identity_never_answers_wrongly.)
    r = _run(tmp_path, *front, CYCLIC, "--once", "-g", "main")
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines() == ["a"] + ["yes"] * 10 + ["true."], r.stdout


@pytest.mark.parametrize("goal, answer", [
    ("_X = [a|_X], _X = [H|_]", "H = a."),
    ("_X = [a|_X], \\+ _X = [b|_]", "true."),
    ("_X = [a|_X], \\+ _X = []", "true."),
    ("_X = [a|_X], \\+ _X == [a]", "true."),
    ("_X = [a|_X], memberchk(a, _X)", "true."),
    ("_X = [a|_X], _Y = [b|_Y], dif(_X, _Y)", "true."),
])
def test_g_cyclic(tmp_path, goal, answer):
    r = _run(tmp_path, "prog.pl", None, "p.\n", "--once", "-g", goal)
    assert r.stdout == answer + "\n", (r.stdout, r.stderr)


# ── Fix round 3 (2026-10-13) ─────────────────────────────────────────────

UNSOUND = """\
mk(0, L, L).
mk(N, L, f(T)) :- N > 0, N1 is N-1, mk(N1, L, T).
u1 :- X = f(X, [1,2,3]), Y = f(Y, [1,2,4]), X == Y.
u3 :- X = [a|X], Y = [a|Y], A = g(X, [1,2,3]), B = g(Y, [1,2,4]), A == B.
u4 :- X = f(X, [1,2,3]), Y = f(Y, [1,2,4]), \\+ X \\== Y.
v1 :- mk(100000, [1,2,3], A), mk(100000, [1,2,4], B), A == B.
v5 :- X = f(X, g(1,2,3)), Y = f(Y, g(1,2,4)), X == Y.
"""


@pytest.mark.parametrize("goal", ["u1", "u3", "u4", "v1", "v5"])
def test_identity_never_answers_wrongly(tmp_path, goal):
    # Each pair DIFFERS (Scryer and Trealla: ==/2 false, \\==/2 true), so
    # each goal must not succeed.  Round 2's coinductive fallback answered
    # TRUE for them (its seen set keyed on ids of objects it had created and
    # freed).  ==/2 on two distinct cyclic terms, or on terms deep enough to
    # overflow, RAISES -- as on base; an exception is acceptable, a wrong
    # answer is not.
    r = _run(tmp_path, "prog.pl", "native", UNSOUND, "--once", "-g", goal)
    assert "true." not in r.stdout, (r.stdout, r.stderr)
    assert r.returncode != 0, (r.stdout, r.stderr)


BUILD = """\
u1 :- X = [b|T], T = foo, Y = [a|X], writeq(Y), nl.
u2 :- X = [b|T], T = foo, Y = [a,c|X], Y = [_,_,_|R], writeq(R), nl.
u3 :- X = [b|T], T = foo, Y = [a|X], Y == [a,b|foo], writeq(eq), nl.
u4 :- X = [a|X], Y = [b|X], Y = [P,Q|_], writeq(P-Q), nl.
n1 :- X = [a,b|X], nth0(5, X, E), writeq(E), nl.
n2 :- X = [a,b|X], nth1(3, X, E), writeq(E), nl.
n3 :- X = [a,b|X], nth0(1, X, E, R), R = [P,Q|_], writeq(E-P-Q), nl.
n4 :- X = [a|X], catch(length(X, _), error(E, _), true), writeq(E), nl.
n5 :- X = [a|X], \\+ length(X, 3), writeq(no), nl.
main :- u1, u2, u3, u4, n1, n2, n3, n4, n5.
"""


@pytest.mark.parametrize("front", FRONT_ENDS, ids=lambda f: f[1] or "clausal")
def test_a_list_built_onto_a_hole_built_improper_or_cyclic_list(tmp_path,
                                                                front):
    # Scryer and Trealla.  u1 crashed the native front end
    # (AttributeError: 'tuple' object has no attribute 'segments'); n1-n3
    # answered false on a cyclic list; length/2 on one is Scryer's
    # resource_error(finite_memory) with N unbound and fails with N bound.
    r = _run(tmp_path, *front, BUILD, "--once", "-g", "main")
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines() == [
        "[a,b|foo]", "foo", "eq", "b-a", "b", "a", "b-a-a",
        "resource_error(finite_memory)", "no", "true."], r.stdout


IDENTITY = """\
t(1) :- X = [a|T], T = 1.0, X == [a|1].
t(2) :- X = [a|T], T = 1, X \\== [a|1.0].
t(3) :- X = [a|T], T = f(1), Y = [a|U], U = f(1.0), X \\== Y.
t(4) :- X0 = [g(1,2,3)|X1], X1 = 1, Y0 = [g(1,2,3)|Y1], Y1 = 1.0, X0 \\== Y0.
t(5) :- X0 = [[1,2,3]|X1], X1 = 1.0, Y0 = [[1,2,3]|Y3], Y3 = 1, X0 \\== Y0.
t(6) :- X = [a|T], T = [1], X == [a,1.0].
t(7) :- X = [a|T], T = [1], X \\== [a,1.0].
t(8) :- X = [a|T], T = 1.0, X == [a|1.0].
t(9) :- X = [a|T], T = [1], X == [a,1].
t(10) :- X = [1|T], X == [1.0|T].
t(11) :- X = [1|T], X \\== [1.0|T].
t(12) :- X = [1|T], Y = [1.0|T], X == Y.
t(13) :- X = [a|T], T = [1], Y = [a|U], U = [1.0], X \\== Y.
t(14) :- X = [a|T], T = 1, Y = [a|U], U = 1.0, X == Y.
t(15) :- X = [a|T], T = [1], Y = [a|U], U = [1.0], X == Y.
t(16) :- X = [a|T], T = 1, [a|1.0] == X.
t(17) :- X = [a|T], T = 1, f(X) == f([a|1.0]).
t(18) :- X = [a|T], T = [1], X == [a|T].
t(19) :- X = [a|T], T = 1, X == [a|T].
t(20) :- X = [a|T], T = 1, compare(O, X, [a|1.0]), compare(O, [a|1], [a|1.0]), O \\== (=).
t(21) :- X = [a|T], T = [1], compare(O, X, [a,1.0]), compare(O, [a,1], [a,1.0]), O \\== (=).
t(22) :- X = [a|T], T = 1, msort([[a|1.0], X], S), msort([[a|1.0], [a|1]], S), S = [P, Q], P \\== Q.
t(23) :- X = [a|T], T = [1], msort([[a,1.0], X], S), msort([[a,1.0], [a,1]], S), S = [P, Q], P \\== Q.
t(24) :- X = [a|T], T = 1, Y = [a|U], U = 1.0, sort([X, Y, [a|1], [a|1.0]], S), length(S, 2).
t(25) :- X = [a|T], T = [1], Y = [a|U], U = [1.0], sort([X, Y, [a,1], [a,1.0]], S), length(S, 2).
t(26) :- X = [a|T], T = 1, X == [a|1], \\+ X @< [a|1], \\+ X @> [a|1].
p(K) :- catch(t(K), E, (write(K), write('-err '), write(E), nl, fail)), write(K), write('-yes'), nl.
p(K) :- \\+ catch(t(K), _, fail), write(K), write('-no'), nl.
main :- p(1), p(2), p(3), p(4), p(5), p(6), p(7), p(8), p(9), p(10), p(11), p(12), p(13),
        p(14), p(15), p(16), p(17), p(18), p(19), p(20), p(21), p(22), p(23), p(24), p(25), p(26).
"""

IDENTITY_EXPECTED = [
    "1-no", "2-yes", "3-yes", "4-yes", "5-yes", "6-no", "7-yes", "8-yes",
    "9-yes", "10-no", "11-yes", "12-no", "13-yes", "14-no", "15-no", "16-no",
    "17-no", "18-yes", "19-yes", "20-yes", "21-yes", "22-yes", "23-yes",
    "24-yes", "25-yes", "26-yes"]


@pytest.mark.parametrize("front", FRONT_ENDS, ids=lambda f: f[1] or "clausal")
def test_identity_keeps_int_and_float_apart_in_a_hole_built_list(tmp_path,
                                                                front):
    # ISO standard order: 1 and 1.0 are different terms, so ==/2 is false
    # and \\==/2 true across them.  Scryer and Trealla print every line
    # below (t(4) is fz_302 #34 and t(5) is fz_206 #49 of the round-3 fuzz).
    # A hole-built improper list (or a list spliced through a hole) must
    # answer exactly as the literal: round 3 answered 1-yes, 2-no, 3-no,
    # 4-no, 5-no, 6-yes, 7-no, 13-no, 14-yes, 15-no and 10-yes/12-yes.
    # t(20)-t(26) pin compare/3, msort/2, sort/2 and @</2 to the literal's
    # answer, whatever the int/float order is.
    r = _run(tmp_path, *front, IDENTITY, "--once", "-g", "main")
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines()[:-1] == IDENTITY_EXPECTED, r.stdout
