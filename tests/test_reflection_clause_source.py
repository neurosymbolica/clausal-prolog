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

from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call
from clausal.logic.cells import chars, chars_text
from clausal.logic.variables import Var, deref
from tests._suffix import SEAM


@pytest.fixture(autouse=True)
def _clear_query_cache():
    from clausal.logic import solve

    getattr(solve, "_query_cache", {}).clear()
    yield


# DEFAULT-mode source (no ``-double_quotes(chars)``): the ``"GtE"``/``"Gt"``
# literals are class NAMES and must be atoms (§6.4).  The one genuinely TEXT
# position here — the rendered source a ``clause_source/2`` answer is compared
# against — is passed in from Python as a ``str`` instead of being written as a
# literal, because a text literal cannot be written in this mode.
_MATCHERS = """\
-double_quotes(atom)
-import_from(reflection, [
    reified_item, reified_clause, reified_subterm,
    op_node, replace_subterm, clause_source,
])

# render a clause of a source text back to text
source(SRC, TEXT) <- (
    reified_clause(SRC, CLAUSE),
    clause_source(CLAUSE, TEXT)
)

# the auditor flow this builtin exists for: rewrite a clause structurally,
# then quote the result — all in Clausal
swapped_source(SRC, TEXT) <- (
    reified_clause(SRC, CLAUSE),
    reified_subterm(CLAUSE, SUB),
    op_node(SUB, "GtE", ARGS),
    op_node(NEW, "Gt", ARGS),
    replace_subterm(CLAUSE, SUB, NEW, CLAUSE2),
    clause_source(CLAUSE2, TEXT)
)

# TERM unbound -> instantiation_error
unbound(TEXT) <- clause_source(_, TEXT)

# a rendered text that does not match a bound TEXT -> clean failure
mismatch(SRC, TEXT) <- (
    reified_clause(SRC, CLAUSE),
    clause_source(CLAUSE, TEXT)
)
"""


@pytest.fixture(scope="module")
def matchers(tmp_path_factory):
    path = tmp_path_factory.mktemp("clause_source") / f"matchers{SEAM}"
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
    sols = _solutions("source", chars("small(X) <- (X >= 1)\n"), text, module=matchers)
    assert [t for (t,) in sols] == [chars("small(X) <- (X >= 1)")]


def test_renders_a_fact(matchers):
    text = Var()
    sols = _solutions("source", chars("edge(1, 2),\n"), text, module=matchers)
    assert [t for (t,) in sols] == [chars("edge(1, 2),")]


def test_quotes_a_rebuilt_clause(matchers):
    """The motivating flow: op-swap a clause via replace_subterm, then render
    the rebuilt clause — a term that never came from source text."""
    text = Var()
    sols = _solutions(
        "swapped_source", chars("small(X) <- (X >= 1)\n"), text, module=matchers)
    assert [t for (t,) in sols] == [chars("small(X) <- (X > 1)")]


def test_unbound_term_raises_instantiation_error(matchers):
    text = Var()
    with pytest.raises(LogicException, match="instantiation_error"):
        _solutions("unbound", text, module=matchers)


def test_bound_text_mismatch_fails_cleanly(matchers):
    # TEXT is a genuine STRING (what render_source answers), so the mismatching
    # value is a Python ``str`` — it must not unify with the rendered text.
    sols = _solutions(
        "mismatch", chars("edge(1, 2),\n"), chars("not the source"), module=matchers)
    assert sols == []


def test_bound_text_match_succeeds(matchers):
    # The other side of the same position: the rendered STRING unifies with an
    # equal ``str``.  Without this the mismatch row above passes vacuously.
    sols = _solutions("mismatch", chars("edge(1, 2),\n"), chars("edge(1, 2),"), module=matchers)
    assert len(sols) == 1


def test_rendered_text_re_reifies(matchers):
    """clause_source output is real source: it reifies back to a clause with
    the same head functor."""
    from clausal.reflection import Clause, reify_source, is_v, vfield

    text = Var()
    [(rendered,)] = _solutions(
        "source", chars("path(A, B) <- (edge(A, B),)\n"), text, module=matchers)
    (again,) = [i for i in reify_source(chars_text(rendered) + "\n")
                if is_v(i, Clause)]
    assert vfield(deref(vfield(again, "head")), "name") == "path"
