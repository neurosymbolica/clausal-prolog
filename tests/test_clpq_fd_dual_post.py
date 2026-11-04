"""A #-constraint over variables that carry BOTH CLP(FD) and CLP(Q) state
posts to both stores.

docs/clpq.md ("FD<->Q coexistence"), DEVIATIONS.md D20/D29: an FD
variable that enters CLP(Q) keeps its FD attribute.  clpfd's comparisons
sent every post that touched a variable with CLP(Q) state to CLP(Q) alone,
so its FD domain was never narrowed and clpfd never fixed it:
``X #>= 0, X #=< 5, {X + Y = 7}, X #> 4`` left X unbound (X > 4 in the
relaxation only), where Scryer, which runs clpz and clpq side by side,
answers X = 5, Y = 2.  A linear #-constraint with integer coefficients
whose variables all have FD state, and one of them CLP(Q) state, now
posts to CLP(Q) (the relaxation) and to CLP(FD) (the domains); an FD
domain that becomes a singleton binds the variable, and CLP(Q) sees the
binding (todo/done/clpq-fd-constraint-on-a-shared-variable-posts-to-q-only-2026-11-04.md).

Unchanged: a #-constraint with a variable that has CLP(Q) state and no FD
state (a rational variable, or a fresh one) stays CLP(Q)'s alone, and
CLP(Q)'s own {}/1 does not narrow an FD domain (``X in 1..5, {X > 4}``
leaves X unbound, as Scryer does).

Runs under the solver ``CLAUSAL_CLPQ`` selects; run the file under both.
"""
import json
import os
import pathlib
import subprocess
import sys

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import _query_cache, call
from clausal.logic.variables import Var, deref, is_var

ROOT = pathlib.Path(__file__).resolve().parents[1]

PL = """\
:- use_module(library(clpq)).
:- use_module(library(clpz)).
gt(X, Y) :- X #>= 0, X #=< 5, {X + Y = 7}, X #> 4.
ge(X, Y) :- X in 0..5, {X + Y = 7}, X #>= 5.
lt(X, Y) :- X in 0..5, {X + Y = 7}, X #< 1.
le(X, Y) :- X in 0..5, {X + Y = 7}, 0 #>= X.
ne(X, Y) :- X in 4..5, {X + Y = 7}, X #\\= 5.
eq_expr(X, Y) :- X in 0..9, {X + Y = 7}, 2*X #= 8.
linked(X, Y, W) :- X in 0..5, W in 0..5, {X + Y = 7},
    X #= W + 4, W #> 0.
labelled(X, Y) :- X in 0..5, {X + Y = 7, Y >= 3}, X #> 2, label([X]).
not_integral(X) :- X in 0..9, {X + _Y = 7}, 2*X #= 5.
diff_after(D) :- X in 1..5, Y in 1..5, {D = X - Y}, X #= Y + 3.
max_after(D) :- X in 1..5, Y in 1..5, {D = X - Y}, X #= Y + 3, maximize(D).
q_only(X) :- {X >= 0, X =< 10}, 2*X #> 1, minimize(X).
reverse(X) :- X in 1..5, {X > 4}.
reverse_label(X) :- X in 1..5, {X > 4}, label([X]).
"""


def _module(tmp_path, suffix):
    path = tmp_path / f"fd_dual{suffix}"
    path.write_text(PL, encoding="utf-8")
    return _load_module(path.stem, path)


def _answers(module, name, arity):
    _query_cache.clear()
    args = [Var() for _ in range(arity)]
    try:
        return [tuple(None if is_var(deref(a)) else deref(a) for a in args)
                for _ in call(name, *args, module=module)]
    finally:
        _query_cache.clear()


# name, arity, the answers (None: left unbound).  Scryer (clpz + clpq
# loaded together) gives the same answers for every row it can answer
# alike; see test_the_oracle_agrees below.
CASES = [
    ("gt", 2, [(5, 2)]),
    ("ge", 2, [(5, 2)]),
    ("lt", 2, [(0, 7)]),
    ("le", 2, [(0, 7)]),
    ("ne", 2, [(4, 3)]),
    ("eq_expr", 2, [(4, 3)]),
    ("linked", 3, [(5, 2, 1)]),
    ("labelled", 2, [(3, 4), (4, 3)]),
    ("not_integral", 1, []),
    ("diff_after", 1, [(3,)]),
    ("max_after", 1, [(3,)]),
]


@pytest.mark.parametrize("suffix", [".pl", ".clausal"])
@pytest.mark.parametrize("name, arity, expected", CASES)
def test_a_shared_variable_takes_the_constraint_in_both_stores(
        tmp_path, suffix, name, arity, expected):
    assert _answers(_module(tmp_path, suffix), name, arity) == expected


@pytest.mark.parametrize("suffix", [".pl", ".clausal"])
def test_a_variable_with_q_state_only_stays_rational(tmp_path, suffix):
    """X has no FD state: 2*X #> 1 is CLP(Q)'s, X stays rational; the
    infimum is not attained, so minimize fails as in 1.3.3."""
    assert _answers(_module(tmp_path, suffix), "q_only", 1) == []


@pytest.mark.parametrize("suffix", [".pl", ".clausal"])
def test_q_s_own_post_does_not_narrow_the_fd_domain(tmp_path, suffix):
    """{X > 4} is CLP(Q)'s alone, as in Scryer: X stays unbound, and
    labelling finds the one value."""
    module = _module(tmp_path, suffix)
    assert _answers(module, "reverse", 1) == [(None,)]
    assert _answers(module, "reverse_label", 1) == [(5,)]


_TWIN = r'''
import json, sys
sys.modules["clausal.logic._clpfd_propagate"] = None   # clpfd's Python twin
import pathlib
from clausal.import_hook import _load_module
from clausal.logic.solve import _query_cache, call
from clausal.logic.variables import Var, deref, is_var
path = pathlib.Path(sys.argv[1])
module = _load_module(path.stem, path)
out = {}
for name, arity in json.loads(sys.argv[2]):
    _query_cache.clear()
    args = [Var() for _ in range(arity)]
    out[name] = [[None if is_var(deref(a)) else str(deref(a)) for a in args]
                 for _ in call(name, *args, module=module)]
print(json.dumps(out))
'''


def test_the_python_twin_posts_to_both_stores_too(tmp_path):
    path = tmp_path / "fd_dual_twin.pl"
    path.write_text(PL, encoding="utf-8")
    names = [["gt", 2], ["ne", 2], ["linked", 3], ["lt", 2], ["max_after", 1],
             ["reverse", 1]]
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    r = subprocess.run([sys.executable, "-c", _TWIN, str(path), json.dumps(names)],
                       cwd=ROOT, env=env, capture_output=True, text=True,
                       timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    assert json.loads(r.stdout) == {
        "gt": [["5", "2"]], "ne": [["4", "3"]], "linked": [["5", "2", "1"]],
        "lt": [["0", "7"]], "max_after": [["3"]], "reverse": [[None]]}


# ---- the oracle -------------------------------------------------------
#
# Scryer runs clpz and clpq as two attribute modules: clpz narrows and
# binds, clpq sees the binding.  It agrees with the rows above where its
# clpq knows the variables: it has no FD-to-Q bound promotion (D29), so
# diff_after's D is left as D = X - Y with X, Y bound by clpz only after
# labelling, and max_after fails (D is unbounded to its clpq).

# Scryer's toplevel helper prints the first answer of each.
ORACLE = [
    ("gt(X, Y)", "X = 5, Y = 2"), ("ge(X, Y)", "X = 5, Y = 2"),
    ("lt(X, Y)", "X = 0, Y = 7"), ("le(X, Y)", "X = 0, Y = 7"),
    ("ne(X, Y)", "X = 4, Y = 3"), ("eq_expr(X, Y)", "X = 4, Y = 3"),
    ("linked(X, Y, W)", "X = 5, Y = 2, W = 1"),
    ("labelled(X, Y)", "X = 3, Y = 4"), ("not_integral(X)", "false"),
    ("q_only(X)", "false"), ("reverse(X)", "X>4, clpz:(X in 1..5)"),
    ("reverse_label(X)", "X = 5"),
]


def test_the_oracle_agrees(tmp_path):
    from tests._oracles import SCRYER, run_scryer
    if not os.path.exists(SCRYER):
        pytest.skip("no Scryer oracle")
    path = tmp_path / "fd_dual_oracle.pl"
    path.write_text(PL, encoding="utf-8")
    mismatches = []
    for goal, expected in ORACLE:
        out = run_scryer(path, [goal + "."], timeout=60).stdout
        first = [ln.strip() for ln in out.splitlines()
                 if ln.strip() and not ln.strip().startswith(";")]
        got = first[0].rstrip(".").rstrip() if first else None
        if got != expected:
            mismatches.append((goal, got, expected))
    assert not mismatches, mismatches
