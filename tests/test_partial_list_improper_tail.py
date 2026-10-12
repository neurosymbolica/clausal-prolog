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
c11 :- X = f(X), Y = f(Y), \\+ X \\== Y, write(yes), nl.
c12 :- X = [a|X], memberchk(a, X), write(yes), nl.
c13 :- X = [a|X], \\+ X = [], write(yes), nl.
c14 :- X = f(X,1), Y = f(Y,2), \\+ X == Y, write(yes), nl.
c17 :- X = [a|X], Y = [a|Y], X == Y, write(yes), nl.
c18 :- X = [a,b|X], Y = [a|Y], \\+ X == Y, write(yes), nl.
c19 :- X = f(X,1), Y = f(Y,1.0), X \\== Y, write(yes), nl.
main :- c1, c2, c3, c4, c5, c6, c7, c8, c10, c11, c12, c13, c14,
        c17, c18, c19.
"""


@pytest.mark.parametrize("front", FRONT_ENDS, ids=lambda f: f[1] or "clausal")
def test_cyclic_lists_and_terms(tmp_path, front):
    # Scryer and Trealla: every probe succeeds (c1 prints a).  At the fix
    # range's first head, c5 raised "RecursionError: cyclic partial list";
    # two DISTINCT cyclic terms (c11, c14, c17, c19) raised in ==.
    r = _run(tmp_path, *front, CYCLIC, "--once", "-g", "main")
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines() == ["a"] + ["yes"] * 15 + ["true."], r.stdout


@pytest.mark.parametrize("goal, answer", [
    ("_X = [a|_X], _X = [H|_]", "H = a."),
    ("_X = [a|_X], \\+ _X = [b|_]", "true."),
    ("_X = [a|_X], \\+ _X = []", "true."),
    ("_X = [a|_X], \\+ _X == [a]", "true."),
    ("_X = [a|_X], memberchk(a, _X)", "true."),
    ("_X = [a|_X], _Y = [b|_Y], dif(_X, _Y)", "true."),
    ("_X = f(_X), _Y = f(_Y), _X == _Y", "true."),
    ("_X = [a|_X], _Y = [a|_Y], _X == _Y", "true."),
    ("_X = f(_X, 1), _Y = f(f(_Y, 1), 1), _X == _Y", "true."),
])
def test_g_cyclic(tmp_path, goal, answer):
    r = _run(tmp_path, "prog.pl", None, "p.\n", "--once", "-g", goal)
    assert r.stdout == answer + "\n", (r.stdout, r.stderr)
