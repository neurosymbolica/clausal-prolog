"""A partial list's tail bound to a non-list is an IMPROPER tail (D50,
2026-10-13).

``X = [a|T], T = foo`` gave ``"afoo"`` -- since atoms became ``str``, the
partial list's walk read the atom bound to its hole as TEXT and spliced its
characters -- and ``L = [x|V], V = 1`` raised PartialTermError.  Bound
BEFORE the list was built, ``T = foo, X = [a|T]`` gave ``[a,foo]`` (the
translator) or ``[a,f,o,o]``.  ISO, Scryer and Trealla give ``[a|foo]`` and
``[x|1]``: the cons cells ``'.'(H, T)`` the native reader builds.  A tail
that is a list, ``[]`` or text still makes a proper list.

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
])
def test_g_partial_list_tails(tmp_path, front, goal, out):
    r = _run(tmp_path, *front, G_SOURCE, "--once", "-g", goal + ", nl")
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines()[0] == out, r.stdout
