"""Arithmetic written as a plain CELL is evaluable, and ``eval_/2`` evaluates.

Slices A1 and A2 of the Compound retirement plan (ruling R9, 2026-09-27):

* A1 -- the evaluator accepts ``('+', 1, 2)`` (and ``Compound('+', (1, 2))``)
  through ONE closed evaluable table keyed ``(name, arity)``, the same table
  the operator nodes (``Add`` & co.) dispatch through, so a cell and a node
  have one semantics.  A cell whose ``name/arity`` is not in the table raises
  ``type_error(evaluable, Name/Arity)`` (ISO 13211-1 7.9.2, 9.1).
* A2 -- ``eval_/2`` evaluates an operand that arrives bound in a variable, and
  raises ``type_error(evaluable, Name/Arity)`` on a non-evaluable term instead
  of handing the term back.

Every row is exercised twice where it can be: from the Python API, and from
SOURCE, where ``unpack/2`` (``=..``) builds the cell at runtime -- the path
that never crosses the Python boundary and so cannot be fixed at ``to_clausal``.
"""
from __future__ import annotations

import itertools
from fractions import Fraction

import pytest

from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call, solve
from clausal.logic.variables import Var, walk
from clausal.terms import Add, Compound, term_str

_N = itertools.count()


def _module(tmp_path, body: str, heads: list[str], extra: str = ""):
    name = f"_arith_cells_{next(_N)}"
    src = (f"-module({name}, [{', '.join(heads)}])\n-allow_singletons\n"
           f"{extra}{body}\n")
    p = tmp_path / f"{name}.clausal"
    p.write_text(src)
    return _load_module(name, str(p)).__dict__["$module"]


def _answers(mod, pred, n=1):
    outs = [Var() for _ in range(n)]
    got = [tuple(walk(o) for o in outs) for _ in call(pred, *outs, module=mod)]
    return [g[0] if n == 1 else g for g in got]


def _error_text(fn) -> str:
    with pytest.raises(LogicException) as e:
        fn()
    text = term_str(e.value.term).replace(" ", "")
    assert text, "an empty rendering could never fail an assertion"
    return text


def _culprit_rendered(indicator: str) -> str:
    """``foo/1`` as ``term_str`` renders the ISO culprit inside
    ``type_error(evaluable, foo/1)`` (canonical form, spaces stripped)."""
    name, arity = indicator.rsplit("/", 1)
    return f"type_error(evaluable,/({name},{arity}))"


@pytest.fixture
def api_mod(tmp_path):
    return _module(tmp_path, "z(1),", ["z(X)"])


def _run(mod, goal, out):
    return [walk(out) for _ in solve(goal, module=mod)]


# ---------------------------------------------------------------------------
# A1 from the Python API: cell, Compound and node spellings agree.
# ---------------------------------------------------------------------------

_SPELLINGS = {
    "cell": lambda: ("+", 1, 2),
    "Compound": lambda: Compound("+", (1, 2)),
    "Add": lambda: Add(None, 1, 2),
}


@pytest.mark.parametrize("spelling", sorted(_SPELLINGS))
class TestA1PythonApi:
    def test_is(self, api_mod, spelling):
        X = Var()
        assert _run(api_mod, ("is", X, _SPELLINGS[spelling]()), X) == [3]

    @pytest.mark.parametrize("op,expected", [
        ("=:=", True), ("=\\=", False), ("<", False), (">", False),
        ("=<", True), (">=", True)])
    def test_iso_comparisons(self, api_mod, spelling, op, expected):
        got = _run(api_mod, (op, _SPELLINGS[spelling](), 3), None)
        assert bool(got) is expected

    def test_eval_(self, api_mod, spelling):
        X = Var()
        assert _run(api_mod, ("eval_", _SPELLINGS[spelling](), X), X) == [3]

    def test_between(self, api_mod, spelling):
        X = Var()
        assert _run(api_mod, ("between", 1, _SPELLINGS[spelling](), X), X) == [1, 2, 3]

    def test_clpfd_eq(self, api_mod, spelling):
        X = Var()
        assert _run(api_mod, ("#=", X, _SPELLINGS[spelling]()), X) == [3]

    def test_clpfd_lt(self, api_mod, spelling):
        assert _run(api_mod, ("#<", _SPELLINGS[spelling](), 4), None)
        assert not _run(api_mod, ("#<", _SPELLINGS[spelling](), 3), None)


class TestA1Table:
    @pytest.mark.parametrize("cell,expected", [
        (("-", 7, 2), 5),
        (("*", 6, 7), 42),
        (("/", 1, 2), Fraction(1, 2)),
        (("/", 4, 2), 2),
        (("mod", -7, 2), 1),        # floored, sign of the divisor (ISO mod)
        (("div", -7, 2), -4),       # floored (ISO div; the FloorDiv node)
        (("**", 2, 3), 8),
        (("-", 5), -5),
        (("*", ("+", 1, 2), 2), 6),                 # nested cells
        (Add(None, ("+", 1, 2), 3), 6),             # a cell under a node
        (("+", Add(None, 1, 2), ("rdiv", 1, 3)), Fraction(10, 3)),  # exact-number cell leaf
        (("+", ("decimal", 150, 2), 1), None),      # checked by type below
    ])
    def test_cell_evaluates(self, api_mod, cell, expected):
        X = Var()
        got = _run(api_mod, ("is", X, cell), X)
        assert len(got) == 1
        if expected is None:
            from decimal import Decimal
            assert got == [Decimal("2.50")]
        else:
            assert got == [expected] and type(got[0]) is type(expected)

    @pytest.mark.parametrize("cell,culprit", [
        (("foo", 1), "foo/1"),
        (("+", 1, 2, 3), "+/3"),
        # ISO // truncates; the engine's floored FloorDiv node is ISO div, so
        # the ISO spelling is NOT aliased onto it (a silent -4 for -7 // 2
        # where ISO and Scryer answer -3).
        (("//", 7, 2), "///2"),
        (("*", ("foo", 1), 2), "foo/1"),
    ])
    def test_non_evaluable_cell_is_type_error_evaluable(self, api_mod, cell, culprit):
        X = Var()
        text = _error_text(lambda: _run(api_mod, ("is", X, cell), X))
        assert _culprit_rendered(culprit) in text, text

    def test_table_is_closed(self):
        from clausal.logic.exact_arith import EVALUABLE
        with pytest.raises(TypeError):
            EVALUABLE[("sin", 1)] = abs  # no registration API: read-only
        assert set(EVALUABLE) == {
            ("+", 2), ("-", 2), ("*", 2), ("/", 2), ("div", 2), ("mod", 2),
            ("**", 2), ("-", 1)}

    def test_node_and_cell_share_one_table(self):
        """Every evaluable operator node class maps onto a table key, so the
        node arms and the cell arms cannot drift apart."""
        from clausal.logic.clpfd import _NODE_KEYS, _ensure_term_imports
        from clausal.logic.exact_arith import EVALUABLE
        from clausal.logic.exceptions import ARITH_OPERATOR_TERMS
        _ensure_term_imports()
        assert set(_NODE_KEYS) == set(ARITH_OPERATOR_TERMS)
        assert set(_NODE_KEYS.values()) == set(EVALUABLE)


# ---------------------------------------------------------------------------
# A1 + A2 from SOURCE: unpack/2 builds the cell at runtime.
# ---------------------------------------------------------------------------

_SRC_ROWS = {
    # name: (body, expected answers)
    "g": ("(unpack(T, ['+', 1, 2]), eval_(T, X))", [3]),
    "j": ("(unpack(T, ['+', 1, 2]), 'is'(X, T))", [3]),
    "k": ("(unpack(T, ['+', 1, 2]), '=:='(T, 3), X == 1)", [1]),
    "i": ("(unpack(T, ['+', 1, 2]), X == T)", [3]),
    "q": ("(unpack(T, ['+', 1, 2]), X == 3, T >= X)", [3]),
    "r": ("(unpack(T, ['+', 1, 2]), between(1, T, X))", [1, 2, 3]),
    "n": ("(unpack(T, ['+', 1, 2]), clpq.rational(X == T))", [3]),
    "m": ("(Y is 1 + 2, eval_(Y, X))", [3]),
    # a cell / node reached through a variable INSIDE a literal expression
    "m2": ("(Y is 1 + 2, eval_(Y * 2, X))", [6]),
    "m3": ("(Y is 1 + 2, eval_(-Y, X))", [-3]),
    "m4": ("(unpack(T, ['+', 1, 2]), eval_(T // 2, X))", [1]),
    "m5": ("(unpack(T, ['+', 1, 2]), eval_(T ** 2, X))", [9]),
    "m6": ("(unpack(T, ['+', 1, 2]), eval_(T % 2, X))", [1]),
    "m7": ("(unpack(T, ['+', 1, 2]), X == T + 1)", [4]),
    # CLP(FD) posts over a cell holding an unbound variable
    "p1": ("(unpack(T, ['+', X, 2]), T == 5)", [3]),
    "p2": ("(unpack(T, ['+', X, 2]), in_domain(X, 0, 10), T < 4, label([X]))", [0, 1]),
    "p3": ("(unpack(T, ['+', 1, 2]), X == 1, T != 3)", []),
    "p4": ("(unpack(T, ['+', X, 2]), clpq.rational(T == 5))", [3]),
    "p6": ("(unpack(T, ['+', X, 2]), '#='(T, 5))", [3]),
}


@pytest.fixture(scope="module")
def src_mod(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("arith_src")
    body = "\n".join(f"{n}(X) <- {b}" for n, (b, _) in _SRC_ROWS.items())
    return _module(tmp, body, [f"{n}(X)" for n in _SRC_ROWS])


@pytest.mark.parametrize("name", list(_SRC_ROWS))
def test_source_row(src_mod, name):
    got = _answers(src_mod, name)
    assert got == _SRC_ROWS[name][1]


def _real_interval(mod, pred):
    """The CLP(R) interval of the one answer's variable.  CLP(R) narrows
    ``X == 1 + 2`` to the point interval and leaves X unbound -- for the NODE
    spelling too -- so the cell spelling is compared against that."""
    from clausal.logic.clpr import REAL_KEY
    from clausal.logic.variables import deref, get_attr, is_var
    X = Var()
    out = []
    for _ in call(pred, X, module=mod):
        v = deref(X)
        if is_var(v):
            st = get_attr(v, REAL_KEY)
            out.append(None if st is None else (st.lo, st.hi))
        else:
            out.append(v)
    return out


def test_clpr_cell_posts_like_the_node(tmp_path):
    """Row o of the plan: ``clpr.real(X == T)`` with T a cell was silently
    unposted (X had no real domain at all)."""
    mod = _module(tmp_path, (
        "cell(X) <- (unpack(T, ['+', 1, 2]), clpr.real(X == T))\n"
        "node(X) <- clpr.real(X == 1 + 2)\n"
        "cvar(X) <- (unpack(T, ['+', X, 2]), clpr.real(T == 5))\n"
        "nvar(X) <- clpr.real(X + 2 == 5)"), ["cell(X)", "node(X)", "cvar(X)", "nvar(X)"])
    node = _real_interval(mod, "node")
    assert len(node) == 1 and node[0] is not None, node        # the control
    lo, hi = node[0]
    assert lo <= 3.0 <= hi and hi - lo < 1e-9, node
    assert _real_interval(mod, "cell") == node
    nvar = _real_interval(mod, "nvar")
    assert nvar and nvar[0] is not None, nvar
    assert _real_interval(mod, "cvar") == nvar


# ---------------------------------------------------------------------------
# A2: eval_/2 raises on what is not evaluable, and keeps what it always did.
# ---------------------------------------------------------------------------

class TestA2Errors:
    @pytest.fixture(scope="class")
    def mod(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("arith_a2")
        rows = {
            "e1": "(unpack(T, ['foo', 1]), eval_(T, X))",
            "e2": "eval_(Y, X)",
            "e3": "eval_(Y + 1, X)",
            "e4": "eval_(bar, X)",
            "e5": "(unpack(T, ['foo', 1]), eval_(T + 1, X))",
            "e6": "(unpack(T, ['foo', 1]), clpq.rational(X == T))",
            "e7": "(unpack(T, ['foo', 1]), clpr.real(X == T))",
            "e8": "(unpack(T, ['foo', 1]), eval_(-T, X))",
            # an operator node outside the table used to come back as the
            # node itself (X = BitAnd(5, 3)); it is named by its operator
            "e9": "eval_(5 & 3, X)",
            "e10": "(Y == 5, eval_(Y & 3, X))",
        }
        body = "\n".join(f"{n}(X) <- {b}" for n, b in rows.items())
        return _module(tmp, body, [f"{n}(X)" for n in rows], extra="-private([bar])\n")

    @pytest.mark.parametrize("name,culprit", [
        ("e1", "foo/1"), ("e4", "bar/0"), ("e5", "foo/1"), ("e8", "foo/1"),
        ("e6", "foo/1"), ("e7", "foo/1"), ("e9", "&/2"), ("e10", "&/2")])
    def test_non_evaluable(self, mod, name, culprit):
        text = _error_text(lambda: _answers(mod, name))
        assert _culprit_rendered(culprit) in text, text

    @pytest.mark.parametrize("name", ["e2", "e3"])
    def test_unbound_operand_is_instantiation_error(self, mod, name):
        text = _error_text(lambda: _answers(mod, name))
        assert text.startswith("error(instantiation_error"), text


class TestA2Keeps:
    """What eval_ did for numbers, units and Python calls stays as it was."""

    @pytest.fixture(scope="class")
    def mod(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("arith_a2_keep")
        rows = {
            "k1": "(eval_(100(m), D), eval_(D, X))",
            "k2": "(eval_(100(m), D), eval_(D / 2, X))",
            "k3": "(eval_(100(m), D), eval_(-D, X))",
            "k4": "eval_(math.sqrt(4) + 1, X)",
            "k5": "(Y == 7, eval_(Y // 2, X))",
            "k6": "(Y == 1.5, eval_(Y, X))",
            "k7": "(unpack(T, ['decimal', 1001, 2]), eval_(T, X))",
            # Python values keep Python's operators (roborev job 265): a list
            # concatenates/repeats, a ++ escape formats
            "k8": "(L is [1, 2], eval_(L + [3], X))",
            "k9": "(L is [1, 2], eval_(L * 2, X))",
            "k10": "eval_(++(\"%d\") % 5, X)",
            "k11": "(L is [1, 2], eval_(L, X))",
        }
        body = "\n".join(f"{n}(X) <- {b}" for n, b in rows.items())
        return _module(tmp, body, [f"{n}(X)" for n in rows],
                       extra="-import_module(math)\n-import_from(py.units, [m])\n")

    def test_quantity_operand(self, mod):
        from clausal.terms import Quantity
        (q,) = _answers(mod, "k1")
        assert isinstance(q, Quantity) and q.value == 100
        (h,) = _answers(mod, "k2")
        assert isinstance(h, Quantity) and h.value == 50
        (n,) = _answers(mod, "k3")
        assert isinstance(n, Quantity) and n.value == -100

    def test_python_call_and_numbers(self, mod):
        assert _answers(mod, "k4") == [3.0]
        assert _answers(mod, "k5") == [3]
        assert _answers(mod, "k6") == [1.5]

    def test_python_lists_and_escapes(self, mod):
        assert _answers(mod, "k8") == [[1, 2, 3]]
        assert _answers(mod, "k9") == [[1, 2, 1, 2]]
        assert _answers(mod, "k10") == ["5"]
        assert _answers(mod, "k11") == [[1, 2]]

    def test_exact_number_cell_is_its_number(self, mod):
        from decimal import Decimal
        assert _answers(mod, "k7") == [Decimal("10.01")]

    def test_zero_division_still_raises_python_error(self, tmp_path):
        mod = _module(tmp_path, "t(X) <- (unpack(T, ['div', 1, 0]), eval_(T, X))", ["t(X)"])
        with pytest.raises(ZeroDivisionError):
            _answers(mod, "t")


def test_deep_sum_still_posts():
    """The cell rewrite at the CLP post boundary walks the operand tree; it
    must not hit the recursion limit before the solver's own walkers do
    (roborev job 265).  900 levels post on main as well."""
    from clausal.logic.clpfd import fd_eq
    from clausal.logic.variables import Trail
    vs = [Var() for _ in range(900)]
    e = vs[0]
    for v in vs[1:]:
        e = Add(None, e, v)
    assert fd_eq(e, 5, Trail())


def test_pow_cell_and_node_post_alike(api_mod):
    """``**`` is not folded ahead of the post for the node spelling, so the
    cell spelling must not be either (roborev job 265): both reach the
    solver as the Pow node and answer alike."""
    from clausal.pythonic_ast.nodes import Pow
    for goal_op in ("#=", "#<"):
        X = Var()
        node = _run(api_mod, (goal_op, X, Pow(None, 2, 3)), X) if goal_op == "#=" else \
            bool(_run(api_mod, (goal_op, Pow(None, 2, 3), 9), None))
        X = Var()
        cell = _run(api_mod, (goal_op, X, ("**", 2, 3)), X) if goal_op == "#=" else \
            bool(_run(api_mod, (goal_op, ("**", 2, 3), 9), None))
        assert cell == node, (goal_op, cell, node)


@pytest.mark.xfail(strict=True, reason=(
    "A3, not A1: `1 + 2` from source is an Add node, which ==/2 and compare/3 "
    "still treat as a different term from the cell +(1, 2) -- "
    "todo/compound-retirement-operator-nodes-are-a-second-spelling-2026-09-27.md"))
def test_structural_eq_cell_vs_source_arith_is_a3(tmp_path):
    mod = _module(tmp_path, "h(X) <- (unpack(T, ['+', 1, 2]), '=='(T, 1 + 2), X == 1)", ["h(X)"])
    assert _answers(mod, "h") == [1]
