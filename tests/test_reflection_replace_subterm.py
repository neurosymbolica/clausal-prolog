"""Tests for ``replace_subterm/4`` — position-preserving single-site structural
subterm rewrite.

``replace_subterm(TERM, OLD, NEW, RESULT)`` binds RESULT to TERM with ONE
occurrence of a subterm unifying OLD replaced by NEW; nondeterministic over
occurrences in depth-first order (consistent with ``reified_subterm/2``).  It is
the write-side companion to ``reified_subterm`` and the clause-rebuild step the
Clausal-AST mutation auditor needs around ``op_node/3`` — reified ``goals``/``args``
are Python lists that tooling Clausal cannot traverse position-preservingly.
See ``todo/done/replace-subterm-reflection-primitive.md``.
"""

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.logic.predicate import make_predicate
from clausal.terms import Compound
from clausal.pythonic_ast import nodes as simple_ast
from clausal import reflection as R


@pytest.fixture(autouse=True)
def _clear_query_cache():
    from clausal.logic import solve

    getattr(solve, "_query_cache", {}).clear()
    yield


# atoms and a helper for building f(a, g(a))-style ground compounds
_a = make_predicate("a", [])
_b = make_predicate("b", [])
_c = make_predicate("c", [])


def _g(x):
    return Compound("g", (x,))


def _resolve(term):
    """Deep-deref into Compounds so ``str`` shows bound-var values, not ``_``."""
    term = deref(term)
    if isinstance(term, Compound):
        return Compound(term.functor, tuple(_resolve(a) for a in term.args))
    return term


def _replace(term, old, new):
    """Enumerate every RESULT of replace_subterm(term, old, new, RESULT)."""
    from clausal.modules import reflection as refl

    result = Var()
    out = []
    for _ in call(refl.replace_subterm, term, old, new, result):
        out.append(_resolve(result))  # resolve before backtracking unbinds vars
    return out


class TestStructuralRewrite:
    def test_two_occurrences_enumerate_in_dfs_order(self):
        term = Compound("f", (_a, _g(_a)))
        results = _replace(term, _a, _b)
        assert [str(r) for r in results] == ["f(b, g(a))", "f(a, g(b))"]

    def test_zero_occurrences_fails_cleanly(self):
        term = Compound("f", (_a, _g(_a)))
        assert _replace(term, _c, _b) == []  # no `c` anywhere -> no solutions

    def test_whole_term_can_be_the_occurrence(self):
        term = Compound("f", (_a,))
        results = _replace(term, term, _b)  # OLD unifies the whole term
        assert [str(r) for r in results] == ["b"]

    def test_old_pattern_vars_bind_and_new_reuses_them(self):
        # OLD = g(X) is a pattern; each match captures the operand and NEW = box(X)
        # rebuilds around it — the pattern-rewrite path (no op_node needed).
        x = Var()
        term = Compound("outer", (_g(_a), _g(_b)))
        results = _replace(term, Compound("g", (x,)), Compound("box", (x,)))
        assert [str(r) for r in results] == [
            "outer(box(a), g(b))", "outer(g(a), box(b))"
        ]

    def test_unaffected_variable_keeps_identity(self):
        x = Var()
        term = Compound("f", (x, _a))
        results = _replace(term, _a, _b)
        assert len(results) == 1
        r = results[0]
        # the untouched first arg is the *same* Var object, not a copy
        assert r.args[0] is x
        assert str(r.args[1]) == "b"


class TestOtherTermKinds:
    """Coverage for the non-Compound branches of the walk."""

    def _all(self, term, old, new):
        from clausal.modules import reflection as refl

        result = Var()
        out = []
        for _ in call(refl.replace_subterm, term, old, new, result):
            out.append(str(deref(result)))  # these kinds have no bound-var operands
        return out

    def test_kwterm_value_is_rewritten_position_preservingly(self):
        from clausal.terms import KWTerm

        term = KWTerm("g", x=_a, y=_b)
        assert self._all(term, _a, _c) == ["KWTerm('g', x=c, y=b)"]

    def test_plain_dict_value_is_rewritten(self):
        assert self._all({"k": _a, "j": _b}, _a, _c) == ["{'k': c, 'j': b}"]

    def test_unbound_old_matches_every_non_var_subterm(self):
        # OLD is an unbound var: it unifies every ground subterm (root included),
        # but not bare vars.  f(a, g(b)) has 4 ground subterms.
        results = _replace(Compound("f", (_a, _g(_b))), Var(), _c)
        assert len(results) == 4


class TestNonGroundTermSemantics:
    """A var nested inside a *matched* subterm binds (unification), for a
    non-ground TERM — documented behavior; the intended input is ground."""

    def test_var_nested_in_matched_subterm_binds(self):
        y = Var()
        # OLD = g(a) matches g(Y) by binding Y=a; the second (unaffected) slot,
        # which shares Y, is instantiated as a result of that same match.
        results = _replace(Compound("f", (_g(y), y)), _g(_a), _b)
        assert [str(r) for r in results] == ["f(b, a)"]


class TestReifiedClauseRewrite:
    """The auditor use case: swap a relop node inside a clause's goals Python
    list, position-preservingly, driven entirely from Clausal."""

    _MATCHERS = """\
-import_from(reflection, [
    reified_clause, reified_subterm, op_node, replace_subterm,
])

# swap a `>=` node to `>` over the same operands, rebuilding the clause in place
SwapGtEtoGt(SRC, NEWCLAUSE) <- (
    reified_clause(SRC, CLAUSE),
    reified_subterm(CLAUSE, OLD),
    op_node(OLD, "GtE", ARGS),
    op_node(NEW, "Gt", ARGS),
    replace_subterm(CLAUSE, OLD, NEW, NEWCLAUSE)
)
"""

    @pytest.fixture(scope="class")
    def matchers(self, tmp_path_factory):
        path = tmp_path_factory.mktemp("replace_subterm") / "m.clausal"
        path.write_text(self._MATCHERS)
        mod = _load_module("_test_replace_subterm_matchers", str(path))
        return mod.__dict__["$module"]

    def test_relop_swap_is_position_preserving(self, matchers):
        src = "Small(P) <- (get(P, k, V), V >= 1)\n"
        new_clause = Var()
        rendered = []
        for _ in call("SwapGtEtoGt", src, new_clause, module=matchers):
            rendered.append(R.render_source(deref(new_clause)))
        # exactly one relop; `get(...)` stays first, `V >= 1` becomes `V > 1`
        assert rendered == ["Small(P) <- ((get(P, k, V), V > 1))"]
