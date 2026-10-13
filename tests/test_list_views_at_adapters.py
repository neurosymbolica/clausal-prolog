"""The rest of a long list reaches a Python-backed module as a list.

Matching ``[_|Rest]`` against a list of 64 or more elements binds ``Rest`` to
a list view (``terms.SegListView``), a window onto the same list rather than
a copy.  A view is not a Python ``list``, so an adapter that tested
``isinstance(x, list)`` refused it -- or, in graphs, silently skipped it --
once the list was long enough.  The Python-backed modules read their
arguments through ``terms.plain_deref``, which hands a view out as a list
(operator ruling 2026-10-12, extending D38).  Each case runs at 30 elements
(a copied rest) and at 100 (a view): the answers must agree.
"""
from __future__ import annotations

import pytest

from clausal.logic.solve import solve
from clausal.logic.variables import Var, deref
from clausal.testing import load_clausal_module

_SRC = """\
:- use_module(library(py_random), [choice/2]).
:- use_module(library(json), [generate/2]).
:- use_module(library(graphs), [vertices/2]).
rest(N, Rest) :- numlist(0, N, L), L = [_|Rest].
choice_in(N, X) :- rest(N, R), choice(R, X), integer(X).
json_of(N, T) :- rest(N, R), generate(R, T).
edge_count(N, K) :- numlist(0, N, L), findall([X, x], member(X, L), [_|Es]), vertices(Es, Vs), length(Vs, K).
"""


_CSV_SRC = """\
:- use_module(library(py_csv), [generate/2]).
csv_of(N, T) :- numlist(0, N, L), findall([X], member(X, L), [_|Rows]), generate(Rows, T).
"""


@pytest.fixture(scope="module")
def csv_mod(tmp_path_factory):
    p = tmp_path_factory.mktemp("listviews_csv") / "listviews_csv.clausal"
    p.write_text(_CSV_SRC)
    return load_clausal_module(p)


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    p = tmp_path_factory.mktemp("listviews") / "listviews.clausal"
    p.write_text(_SRC)
    return load_clausal_module(p)


def _one(mod, goal, n):
    v = Var()
    assert next(solve((goal, n, v), mod), None) is not None, (goal, n)
    return deref(v)


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
@pytest.mark.parametrize("n", [30, 100])
def test_choice_takes_the_rest_of_a_long_list(mod, n):
    assert 1 <= _one(mod, "choice_in", n) <= n


@pytest.mark.parametrize("n", [30, 100])
def test_json_generate_takes_the_rest_of_a_long_list(mod, n):
    from clausal.logic.cells import chars
    assert _one(mod, "json_of", n) == chars("[" + ", ".join(map(str, range(1, n + 1))) + "]")


@pytest.mark.parametrize("n", [30, 100])
def test_csv_generate_takes_the_rest_of_a_long_list_of_rows(csv_mod, n):
    from clausal.logic.cells import chars_text
    text = chars_text(_one(csv_mod, "csv_of", n))
    assert text.split() == [str(i) for i in range(1, n + 1)]


@pytest.mark.parametrize("n", [30, 100])
def test_graph_vertices_take_the_rest_of_a_long_edge_list(mod, n):
    assert _one(mod, "edge_count", n) == n + 1      # 1..n and x


def test_no_package_adapter_reads_its_arguments_with_the_engine_deref():
    """The optional packages' Python-backed modules take the same boundary:
    ``plain_deref``, never the engine's view-keeping ``deref`` (operator
    ruling 2026-10-13).  Checked on the source, since most of their third-party
    dependencies are not installed where the engine suite runs; each
    package's own suite checks behaviour (packages/clausal-yaml's
    test_yaml_list_views.py)."""
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "packages"
    engine_deref = re.compile(
        r"^\s*from clausal\.logic\.variables import [^\n(]*\bderef\b", re.M)
    offenders = sorted(
        str(p.relative_to(root)) for p in root.glob("*/clausal/**/*.py")
        if engine_deref.search(p.read_text(encoding="utf-8")))
    assert offenders == []
