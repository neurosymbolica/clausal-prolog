"""The ``.pl`` translator builds an operator term in DATA position as the ISO
cell, not as the seam's arithmetic node (2026-10-20).

``foo/0`` written as an argument -- a catch/3 catcher, either side of ``==``
or ``=``, any term argument -- was emitted as the seam's ``'foo' / 0``, which
the seam reads as an arithmetic ``Div`` node, not the cell
``('/', 'foo', 0)`` that the engine's error terms and the native front end
carry.  So ``catch(call(foo), error(existence_error(procedure, foo/0), _),
true)`` re-raised instead of catching, ``E == existence_error(procedure,
[]/0)`` failed for an ``E`` with exactly that value, ``functor(foo/0, N, A)``
answered ``'Div'/3``, and a ``K-V`` pattern did not match the pairs
library(pairs) builds.  The same held for ``+``, ``-`` and ``*`` and the
prefix ``-``/``+``.

In ARITHMETIC position (``is``, ``=:=``, ``<``, ``#=``, ``{...}``, also
inside a meta-call's goal argument) the operators are still expressions.

Every expected line is what Scryer prints for the same program (``writeq/1``);
both front ends run it and must agree.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

PROGRAM = """\
:- use_module(library(pairs)).
r(G) :- catch(call(G), E, (writeq(G), write(' raised '), writeq(E), nl, fail)),
    writeq(G-yes), nl.
r(G) :- \\+ catch(call(G), _, fail), writeq(G-no), nl.

caught_foo :- catch(call(foo), error(existence_error(procedure, foo/0), _), true).
caught_bar :- catch(call(bar, 1),
                    error(existence_error(procedure, bar/1), _), true).
caught_nil :- catch(call('[]'),
                    error(existence_error(procedure, '[]'/0), _), true).
nil_identical :- catch(call([]), error(E, _), true),
    E == existence_error(procedure, []/0).
eq_identical :- catch(call(=), error(E, _), true),
    E == existence_error(procedure, (=)/0).
unify_cell :- X = foo/0, X = '/'(foo, 0).
unify_op_name :- X = (=)/2, X = '/'(=, 2).
unify_qualified :- X = m:foo/1, X = ':'(m, '/'(foo, 1)).
show(T) :- functor(T, N, A), writeq(N/A), write(' '), T =.. L, writeq(L), nl.
shapes :- show(foo/0), show(a-b), show(a+b), show(a*b), show(-(a)),
    show(+(a)), show(m:foo/1).
pairs :- pairs_keys_values(P, [a], [1]), P = [K-V], writeq(K-V), nl.
head_pattern(foo/N, N).
heads :- head_pattern('/'(foo, 3), N), writeq(N), nl.

arith :- X is 6/3, writeq(X), nl, Y = 7/2, Z is Y, writeq(Z), nl,
    1+1 =:= 2, 3 > 1+1, 2*3 =\\= 5, 6/3 =< 2, -(1) < 0.
arith_in_meta :- findall(X, (member(X, [1,2,3,4]), X > 1+1, X =\\= 2*2), L),
    writeq(L), nl.

main :- r(caught_foo), r(caught_bar), r(caught_nil), r(nil_identical),
    r(eq_identical), r(unify_cell), r(unify_op_name), r(unify_qualified),
    shapes, pairs, heads, arith, arith_in_meta.
"""

EXPECTED = [
    "caught_foo-yes",
    "caught_bar-yes",
    "caught_nil-yes",
    "nil_identical-yes",
    "eq_identical-yes",
    "unify_cell-yes",
    "unify_op_name-yes",
    "unify_qualified-yes",
    "(/)/2 [/,foo,0]",
    "(-)/2 [-,a,b]",
    "(+)/2 [+,a,b]",
    "(*)/2 [*,a,b]",
    "(-)/1 [-,a]",
    "(+)/1 [+,a]",
    "(:)/2 [:,m,foo/1]",
    "a-1",
    "3",
    "2.0",
    "3.5",
    "[3]",
]


def _run(tmp_path, frontend):
    (tmp_path / "opdata.pl").write_text(PROGRAM)
    env = dict(os.environ)
    env["CLAUSAL_PL_FRONTEND"] = frontend
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "clausal", "opdata.pl"], cwd=tmp_path, env=env,
        capture_output=True, text=True, timeout=120)


@pytest.mark.parametrize("frontend", ["translator", "native"])
def test_operator_terms_in_data_position_are_iso_cells(tmp_path, frontend):
    r = _run(tmp_path, frontend)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.splitlines() == EXPECTED, r.stdout


@pytest.mark.parametrize("source, emitted", [
    ("t :- X = foo/0, p(X).", "'/'(foo, 0)"),
    ("t :- p([]/0).", "'/'([], 0)"),
    ("t :- p(a-b).", "'-'(a, b)"),
    ("t :- p(-(a)).", "'-'(a)"),
    ("t :- X is A/B, p(X, A, B).", "eval_(A / B, X)"),
    ("t :- A+1 =:= B, p(A, B).", "A + 1 == B"),
])
def test_the_translator_text(source, emitted):
    from clausal.tools.prolog_dialect import Dialect
    from clausal.tools.prolog_to_clausal import prolog_to_clausal
    text = prolog_to_clausal(source, dialect=Dialect.scryer_reader())
    assert emitted in text, text
