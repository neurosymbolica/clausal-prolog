"""Tests for ``clause_source/2`` — render a reified term back to ``.clausal``
source text from Clausal.

Companion to :mod:`test_reflection_op_node`.  The renderer itself
(:func:`clausal.reflection.render_source`) is Python-only; ``clause_source``
is the Clausal-callable wrapper, so a rulebase that took a clause apart and
rebuilt it (``op_node/3`` + ``replace_subterm/4``) can *quote* what it built
without dropping into Python.  See
``todo/clause-source-predicate-for-clausal-callers.md``.
"""

import pytest

from clausal.logic.atoms import char_atom, mint
from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


@pytest.fixture(autouse=True)
def _clear_query_cache():
    from clausal.logic import solve

    getattr(solve, "_query_cache", {}).clear()
    yield


_MATCHERS = """\
-import_from(reflection, [
    reified_item, reified_clause, reified_subterm,
    op_node, replace_subterm, clause_source,
])

# render a clause of a source text back to text
Source(SRC, TEXT) <- (
    reified_clause(SRC, CLAUSE),
    clause_source(CLAUSE, TEXT)
)

# the auditor flow this builtin exists for: rewrite a clause structurally,
# then quote the result — all in Clausal
SwappedSource(SRC, TEXT) <- (
    reified_clause(SRC, CLAUSE),
    reified_subterm(CLAUSE, SUB),
    op_node(SUB, "GtE", ARGS),
    op_node(NEW, "Gt", ARGS),
    replace_subterm(CLAUSE, SUB, NEW, CLAUSE2),
    clause_source(CLAUSE2, TEXT)
)

# TERM unbound -> instantiation_error
Unbound(TEXT) <- clause_source(_, TEXT)

# a rendered text that does not match a bound TEXT -> clean failure
Mismatch(SRC) <- (
    reified_clause(SRC, CLAUSE),
    clause_source(CLAUSE, "not the source")
)
"""


@pytest.fixture(scope="module")
def matchers(tmp_path_factory):
    path = tmp_path_factory.mktemp("clause_source") / "matchers.clausal"
    path.write_text(_MATCHERS)
    mod = _load_module("_test_clause_source_matchers", str(path))
    return mod.__dict__["$module"]


def _solutions(functor, *args, module):
    var_positions = [i for i, a in enumerate(args) if isinstance(a, Var)]
    out = []
    for _ in call(functor, *args, module=module):
        out.append(tuple(deref(args[i]) for i in var_positions))
    return out


def test_renders_a_rule_clause(matchers):
    text = Var()
    sols = _solutions("Source", "Small(X) <- (X >= 1)\n", text, module=matchers)
    assert [t for (t,) in sols] == ["Small(X) <- (X >= 1)"]


def test_renders_a_fact(matchers):
    text = Var()
    sols = _solutions("Source", "Edge(1, 2),\n", text, module=matchers)
    assert [t for (t,) in sols] == ["Edge(1, 2),"]


def test_quotes_a_rebuilt_clause(matchers):
    """The motivating flow: op-swap a clause via replace_subterm, then render
    the rebuilt clause — a term that never came from source text."""
    text = Var()
    sols = _solutions(
        "SwappedSource", "Small(X) <- (X >= 1)\n", text, module=matchers)
    assert [t for (t,) in sols] == ["Small(X) <- (X > 1)"]


def test_unbound_term_raises_instantiation_error(matchers):
    text = Var()
    with pytest.raises(LogicException, match="instantiation_error"):
        _solutions("Unbound", text, module=matchers)


def test_bound_text_mismatch_fails_cleanly(matchers):
    sols = _solutions("Mismatch", "Edge(1, 2),\n", module=matchers)
    assert sols == []


def test_rendered_text_re_reifies(matchers):
    """clause_source output is real source: it reifies back to a clause with
    the same head functor."""
    from clausal.reflection import Clause, reify_source

    text = Var()
    [(rendered,)] = _solutions(
        "Source", "Path(A, B) <- (Edge(A, B),)\n", text, module=matchers)
    (again,) = [i for i in reify_source(rendered + "\n")
                if isinstance(i, Clause)]
    assert deref(again.head).name == "Path"
