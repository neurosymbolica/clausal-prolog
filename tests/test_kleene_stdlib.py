"""Tests for clausal/stdlib/kleene.seam — n-ary strong-Kleene connectives.

Covers the acceptance criteria of todo/kleene-nary-connectives-and4-or4.md:
- binary tables (and3/or3/not3), fixed arities 4..9, and list folds;
- ground forward evaluation (one deterministic solution);
- backward enumeration counts (19 for and4(A,B,C,False), 1 for all-True);
- list-fold unit (True for and, False for or) and mid-chain solving;
- no leftover choicepoints on ground queries (proxied by len(results) == 1,
  the established pattern in TestMemberdT).

The module is loaded ONCE per test class and reused. Truth values are the
Python ``True``/``False`` and the ``Undefined`` builtin singleton (from
``clausal.terms``); ``Undefined`` carries process-wide identity, so queries just
reference the imported singleton — no module-scoped-atom dance.
"""

import os

import pytest

from clausal.terms import Var, Undefined


def _load_stdlib_kleene():
    from clausal.import_hook import _load_module
    path = os.path.join(
        os.path.dirname(__file__), os.pardir,
        "clausal", "stdlib", "kleene.seam",
    )
    path = os.path.normpath(path)
    return _load_module("_test_stdlib_kleene", path)


class _KleeneBase:
    """Shared loader + query helpers.

    Loads the module a single time (class attribute) so repeated tests reuse
    one loaded module (loading a .clausal twice in one process duplicates its
    module-scoped atoms; the truth values here are process-wide, but the reuse
    keeps the load cost down and matches the established pattern).
    """

    _mod = None

    @classmethod
    def _module(cls):
        if _KleeneBase._mod is None:
            _KleeneBase._mod = _load_stdlib_kleene()
        return _KleeneBase._mod

    @classmethod
    def _unknown(cls):
        # The Undefined builtin is a process-wide singleton (clausal.terms.Undefined);
        # the clauses in kleene.seam unify against this same object.
        return Undefined

    @classmethod
    def _solve(cls, name, args):
        """Run kleene predicate *name* with *args*.

        Each element of *args* is either a concrete value or the sentinel
        ``None`` meaning "fresh output variable". Returns a list of dicts
        mapping the positional var name (``v0``, ``v1``, ...) to its bound
        value, in solution order.
        """
        from clausal.logic.solve import query
        from clausal.pythonic_ast.nodes import Call, LoadName

        mod = cls._module()
        logic_mod = mod.__dict__["$module"]
        bindings = {}
        call_args = []
        for a in args:
            if a is _OUT:
                v = Var()
                key = f"v{len(bindings)}"
                bindings[key] = v
                call_args.append(v)
            else:
                call_args.append(a)
        goal = Call(func=LoadName(name=name), args=call_args, kwargs=[])
        return list(query(goal, bindings, logic_mod))

    @classmethod
    def _results_of(cls, name, args):
        """List of the single output variable's values (queries with one OUT)."""
        rows = cls._solve(name, args)
        out = []
        for r in rows:
            assert len(r) == 1, "expected exactly one output variable"
            out.append(next(iter(r.values())))
        return out


# Sentinel marking an output-variable position in _solve/_results_of.
_OUT = object()


class TestBinaryTables(_KleeneBase):
    """and3/or3/not3 ground truth tables."""

    def test_and3_ground(self):
        U = self._unknown()
        assert self._results_of("and3", [True, True, _OUT]) == [True]
        assert self._results_of("and3", [True, False, _OUT]) == [False]
        assert self._results_of("and3", [True, U, _OUT]) == [U]
        assert self._results_of("and3", [False, U, _OUT]) == [False]
        assert self._results_of("and3", [U, U, _OUT]) == [U]

    def test_or3_ground(self):
        U = self._unknown()
        assert self._results_of("or3", [True, False, _OUT]) == [True]
        assert self._results_of("or3", [False, False, _OUT]) == [False]
        assert self._results_of("or3", [False, U, _OUT]) == [U]
        assert self._results_of("or3", [True, U, _OUT]) == [True]
        assert self._results_of("or3", [U, U, _OUT]) == [U]

    def test_not3_ground(self):
        U = self._unknown()
        assert self._results_of("not3", [True, _OUT]) == [False]
        assert self._results_of("not3", [False, _OUT]) == [True]
        assert self._results_of("not3", [U, _OUT]) == [U]

    def test_and3_ground_is_deterministic(self):
        # A fully-ground query yields exactly one solution (no leftover
        # choicepoints): the tables are pairwise-disjoint.
        assert len(self._solve("and3", [True, True, True])) == 1
        assert len(self._solve("and3", [False, True, False])) == 1

    def test_and3_full_table_enumeration(self):
        # All 9 assignments enumerate with no duplicates.
        rows = self._solve("and3", [_OUT, _OUT, _OUT])
        assert len(rows) == 9
        seen = {tuple(r.values()) for r in rows}
        assert len(seen) == 9


class TestFixedArities(_KleeneBase):
    """and4..and9 / or4..or9 chaining clauses."""

    def test_and4_ground_forward(self):
        U = self._unknown()
        assert self._results_of("and4", [True, True, False, _OUT]) == [False]
        assert self._results_of("and4", [True, U, True, _OUT]) == [U]
        assert self._results_of("and4", [True, True, True, _OUT]) == [True]

    def test_or5_ground_forward(self):
        U = self._unknown()
        assert self._results_of("or5", [False, False, U, False, _OUT]) == [U]
        assert self._results_of("or5", [False, False, False, True, _OUT]) == [True]
        assert self._results_of("or5", [False, False, False, False, _OUT]) == [False]

    def test_and4_backward_false_count(self):
        # 27 total - 1 all-True - 7 (no-False-but-some-unknown) = 19.
        rows = self._solve("and4", [_OUT, _OUT, _OUT, False])
        assert len(rows) == 19
        seen = {tuple(r.values()) for r in rows}
        assert len(seen) == 19, "no duplicate assignments"

    def test_and4_backward_true_count(self):
        # Only the all-True assignment yields True.
        rows = self._solve("and4", [_OUT, _OUT, _OUT, True])
        assert len(rows) == 1
        r = rows[0]
        assert list(r.values()) == [True, True, True]

    def test_or4_backward_true_count(self):
        # Dual of and4(...,False): exactly 19.
        rows = self._solve("or4", [_OUT, _OUT, _OUT, True])
        assert len(rows) == 19
        seen = {tuple(r.values()) for r in rows}
        assert len(seen) == 19

    def test_partial_absorption_still_enumerates(self):
        # and4(False, B, C, R): R=False in every solution, but B/C still
        # enumerate (9 solutions) because the tables are disjoint (no
        # short-circuit).
        rows = self._solve("and4", [False, _OUT, _OUT, _OUT])
        assert len(rows) == 9
        # v2 is the result variable (index 2 of the three OUT positions).
        for r in rows:
            assert r["v2"] is False

    def test_all_arities_ground_deterministic(self):
        # Every fixed arity leaves no choicepoint when fully ground.
        U = self._unknown()
        specs = [
            ("and3", [True, True], True),
            ("and4", [True, True, True], True),
            ("and5", [True, True, U, True], U),
            ("and6", [True] * 5, True),
            ("and7", [True] * 6, True),
            ("and8", [True] * 7, True),
            ("and9", [True] * 8, True),
            ("or3", [False, False], False),
            ("or4", [False, False, True], True),
            ("or5", [False] * 4, False),
            ("or6", [False] * 5, False),
            ("or7", [False] * 6, False),
            ("or8", [False] * 7, False),
            ("or9", [False] * 8, False),
        ]
        for name, operands, expected in specs:
            got = self._results_of(name, operands + [_OUT])
            assert got == [expected], f"{name}{tuple(operands)} -> {got}"


class TestListFolds(_KleeneBase):
    """and3_list / or3_list."""

    def test_empty_units(self):
        assert self._results_of("and3_list", [[], _OUT]) == [True]
        assert self._results_of("or3_list", [[], _OUT]) == [False]

    def test_and3_list_forward(self):
        U = self._unknown()
        assert self._results_of("and3_list", [[True, True, True], _OUT]) == [True]
        assert self._results_of("and3_list", [[True, False, True], _OUT]) == [False]
        assert self._results_of("and3_list", [[True, U, True], _OUT]) == [U]

    def test_or3_list_forward(self):
        U = self._unknown()
        assert self._results_of("or3_list", [[False, False, False], _OUT]) == [False]
        assert self._results_of("or3_list", [[False, True, False], _OUT]) == [True]
        assert self._results_of("or3_list", [[False, U, False], _OUT]) == [U]

    def test_and3_list_mid_chain_solve(self):
        # and3_list([True, unknown, X], False) has X = False among solutions.
        U = self._unknown()
        x = Var()
        from clausal.logic.solve import query
        from clausal.pythonic_ast.nodes import Call, LoadName

        mod = self._module()
        logic_mod = mod.__dict__["$module"]
        goal = Call(
            func=LoadName(name="and3_list"),
            args=[[True, U, x], False],
            kwargs=[],
        )
        results = list(query(goal, {"x": x}, logic_mod))
        xs = [r["x"] for r in results]
        assert False in xs

    def test_and3_list_ground_deterministic(self):
        assert len(self._solve("and3_list", [[True, True, True], True])) == 1
        assert len(self._solve("or3_list", [[False, False, False], False])) == 1


class TestExports(_KleeneBase):
    """Module export surface."""

    def test_unknown_is_builtin_singleton(self):
        # `Undefined` is now the process-wide builtin singleton, not a
        # module-scoped atom: it is NOT an attribute of the loaded module, and
        # the imported `Undefined` is the object the clauses unify against.
        from clausal.terms import Undefined as _Unknown
        U = self._unknown()
        assert U is _Unknown
        assert not hasattr(self._module(), "unknown")
        # Ground query confirms the clauses carry the same singleton.
        assert self._results_of("not3", [_Unknown, _OUT]) == [_Unknown]

    def test_predicates_exported(self):
        mod = self._module()
        for name in [
            "not3", "and3", "and9", "or3", "or9", "and3_list", "or3_list",
        ]:
            assert hasattr(mod, name), f"missing export: {name}"
