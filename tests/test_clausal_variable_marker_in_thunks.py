"""``--X`` inside a thunk is an EXPLICIT "the Clausal variable X" marker.

An f-string slot and a ``++`` operand are verbatim Python, so a bare ``X``
written there is captured as a clause variable only by NAME, against a
module-namespace exclusion set.  That set is what five rounds of defects were
spent on.  ``--X`` says it outright, and — the part the bare spelling cannot
do — it is CHECKED: a marked name no goal binds is a load error, where the
bare spelling silently renders a module-namespace class.

Purely ADDITIVE.  Bare ``X`` keeps working exactly as it did, and wherever
the marker is accepted the two spellings give the SAME answer — which is what
these tests pair.

EVERY fixture here binds a NON-NUMERIC value, deliberately.  ``--X`` used to
be Python double negation, and double negation of a number is the identity:
a numeric fixture passes on the unmodified engine and proves nothing.  With
an atom it raised ``TypeError: bad operand type for unary -: 'str'``, which
is the state these tests were written red against.
"""
import ast
import textwrap

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


def _load(tmp_path, name, text):
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(text).lstrip())
    return _load_module(f"cvmit_{name}", str(path))


def _module(mod):
    return mod.__dict__["$module"]


def _answers(mod, functor, arity=1):
    """Every solution's argument values, snapshotted INSIDE the iteration."""
    args = [Var() for _ in range(arity)]
    out = []
    for _ in call(functor, *args, module=_module(mod)):
        out.append(tuple(deref(a) for a in args))
    return out


# ``Node`` is the fixture spelling throughout: it is a real TitleCase name in
# the module namespace (``clausal.pythonic_ast.nodes.Node``), so it is in the
# Python-scope exclusion set and the implicit rule has to decide about it.
# That makes it the spelling where the marker has something to say.


# ── The marker in an f-string slot ─────────────────────────────────────────

def test_marker_at_the_top_of_an_fstring_slot(tmp_path):
    """The headline shape.  ``red`` is an atom, so the pre-change reading
    (double unary minus) raised ``TypeError: bad operand type for unary -``
    rather than quietly agreeing the way a numeric fixture would."""
    mod = _load(tmp_path, "slot_top", """
        -private([red])
        -module(cvmit_slot_top, [p(S)])
        tree(red),
        p(S) <- (tree(Node), S is f"{--Node}")
    """)
    assert _answers(mod, "p") == [("red",)]


def test_marker_and_bare_name_agree_in_an_fstring_slot(tmp_path):
    """The additivity contract: one position, both spellings, one answer."""
    marked = _load(tmp_path, "slot_marked", """
        -private([red])
        -module(cvmit_slot_marked, [p(S)])
        tree(red),
        p(S) <- (tree(Node), S is f"{--Node}")
    """)
    bare = _load(tmp_path, "slot_bare", """
        -private([red])
        -module(cvmit_slot_bare, [p(S)])
        tree(red),
        p(S) <- (tree(Node), S is f"{Node}")
    """)
    assert _answers(marked, "p") == _answers(bare, "p") == [("red",)]


def test_marker_below_the_top_of_a_slot_and_its_bare_twin(tmp_path):
    """THE SCOPE DECISION, pinned: the marker is recognised ANYWHERE inside a
    slot or operand, not only at its top.

    Slot-top-only looked safer and is the rule that makes the feature
    useless: a thunk body is almost always a call, so the marker would be
    unwritable in ``f"{str(Node).upper()}"`` or ``++len(Node)`` — the very
    places a reader most needs telling which names are variables.

    What slot-top-only would have dodged is that ``a <- -b`` and ``a < --b``
    parse to the IDENTICAL AST, so a nested double-``USub`` is ambiguous in
    general.  Adjacency settles it instead, which is the test ``++`` already
    used — see ``test_the_arrow_lookalike_is_not_a_marker``."""
    marked = _load(tmp_path, "deep_marked", """
        -private([red])
        -module(cvmit_deep_marked, [p(S)])
        tree(red),
        p(S) <- (tree(Node), S is f"{str(--Node).upper()}")
    """)
    bare = _load(tmp_path, "deep_bare", """
        -private([red])
        -module(cvmit_deep_bare, [p(S)])
        tree(red),
        p(S) <- (tree(Node), S is f"{str(Node).upper()}")
    """)
    assert _answers(marked, "p") == _answers(bare, "p") == [("RED",)]


def test_marker_in_a_slot_carrying_a_format_spec(tmp_path):
    """A format spec applies to the VALUE, so the marker must survive one."""
    mod = _load(tmp_path, "slot_spec", """
        -private([red])
        -module(cvmit_slot_spec, [p(S)])
        tree(red),
        p(S) <- (tree(Node), S is f"{--Node:>5}")
    """)
    assert _answers(mod, "p") == [("  red",)]


# ── The marker in a ``++`` operand ─────────────────────────────────────────

def test_marker_in_a_plus_plus_operand_and_its_bare_twin(tmp_path):
    """The mirror position.  ``++`` operands are where the marker earns its
    keep: the operand is nearly always a call, so the name sits below the
    top and slot-top-only would not have reached it."""
    marked = _load(tmp_path, "pp_marked", """
        -private([red])
        -module(cvmit_pp_marked, [p(S)])
        tree(red),
        p(S) <- (tree(Node), S is ++str(--Node).upper())
    """)
    bare = _load(tmp_path, "pp_bare", """
        -private([red])
        -module(cvmit_pp_bare, [p(S)])
        tree(red),
        p(S) <- (tree(Node), S is ++str(Node).upper())
    """)
    assert _answers(marked, "p") == _answers(bare, "p") == [("RED",)]


def test_marker_at_the_top_of_a_plus_plus_operand(tmp_path):
    """``++--X`` — the marker as the whole operand.  ``++`` is stripped
    first, so what the marker sees is the operand's top."""
    mod = _load(tmp_path, "pp_top", """
        -private([red])
        -module(cvmit_pp_top, [p(S)])
        tree(red),
        p(S) <- (tree(Node), S is ++(--Node))
    """)
    assert _answers(mod, "p") == [("red",)]


# ── The negative control: a marked name nothing in the clause binds ────────

def test_marker_on_a_name_no_goal_binds_is_a_load_error(tmp_path):
    """THE NEGATIVE CONTROL, and the marker's whole reason to exist.

    ``--X`` asserts that ``X`` is this clause's logic variable.  If no goal
    outside a thunk uses that spelling the assertion is false, and the silent
    outcomes — capturing a fresh unbound ``Var``, or resolving the module
    namespace instead — are exactly the class of defect an explicit marker is
    for.  So it is LOUD, at load time, and it names the name.

    The paired bare spelling below is the contrast: it loads, and formats
    ``<class 'clausal.pythonic_ast.nodes.Node'>`` with no diagnostic at all
    (``_lint_titlecase`` returns early on ``JoinedStr``)."""
    with pytest.raises(SyntaxError) as excinfo:
        _load(tmp_path, "unbound", """
            -module(cvmit_unbound, [p(S)])
            p(S) <- (S is f"{--Node}")
        """)
    message = str(excinfo.value)
    assert "--Node" in message, message
    # Located, with the offending line and a caret — the diagnostic has
    # to be reachable from the file, not just true.
    assert "unbound.clausal, line 2" in message, message
    assert 'f"{--Node}"' in message, message

    bare = _load(tmp_path, "unbound_bare", """
        -module(cvmit_unbound_bare, [p(S)])
        p(S) <- (S is f"{Node}")
    """)
    [(rendered,)] = _answers(bare, "p")
    assert rendered.startswith("<class "), rendered


def test_the_load_error_reaches_a_plus_plus_operand_too(tmp_path):
    """Both positions are checked, not just the f-string one."""
    with pytest.raises(SyntaxError) as excinfo:
        _load(tmp_path, "unbound_pp", """
            -module(cvmit_unbound_pp, [p(S)])
            p(S) <- (S is ++str(--Node))
        """)
    assert "--Node" in str(excinfo.value)


def test_the_load_error_names_the_bare_spelling_as_the_remedy(tmp_path):
    """The diagnostic has to be actionable: if the author meant the Python
    name, dropping the marker is the spelling that reaches it."""
    with pytest.raises(SyntaxError) as excinfo:
        _load(tmp_path, "unbound_remedy", """
            -module(cvmit_unbound_remedy, [p(S)])
            p(S) <- (S is f"{--Node}")
        """)
    assert "`Node`" in str(excinfo.value)


# ── What is NOT a marker ───────────────────────────────────────────────────

def test_the_arrow_lookalike_is_not_a_marker(tmp_path):
    """``a <- -b`` and ``a < --b`` parse to the IDENTICAL AST, so a blind
    double-``USub`` test is wrong in general.  ADJACENCY separates them — the
    same test ``visit_UnaryOp`` already applied to ``++``: the two operators
    must share a line and sit in neighbouring columns.

    Written with a SPACE here, which is the arrow's spacing.  ``Node`` is
    bound to an ATOM, so if the space were ignored the marker would fire and
    the answer would be ``red``; the ``TypeError`` is double negation, which
    is what a non-marker must still be."""
    mod = _load(tmp_path, "spaced", """
        -private([red])
        -module(cvmit_spaced, [p(S)])
        tree(red),
        p(S) <- (tree(Node), S is f"{- -Node}")
    """)
    with pytest.raises(TypeError):
        _answers(mod, "p")


def test_a_seams_plus_plus_operand_keeps_the_seam_reading_of_dash_dash():
    """THE SCOPE LIMIT, pinned.  Inside a seam, a ``++`` operand is hosted
    Python again, and there ``--expr`` is already THE SEAM — nesting to any
    depth, which ``visit_UnaryOp`` documents and depends on.  A marker
    reading would be a second, narrower meaning for one spelling in one
    context, which is not additive.  So the marker is recognised only where
    the thunk body is embedded verbatim, i.e. where there is no Python
    visitor to hand it back to."""
    from clausal.templating.term_rewriting import EmbedTransformer, unparse
    tree = ast.parse('x = --f(++g(--Inner))\n')
    ast.fix_missing_locations(tree)
    out = EmbedTransformer().visit(tree)
    ast.fix_missing_locations(out)
    rendered = unparse(out)
    # The inner ``--Inner`` is still lowered to a seam CALL inside the ``++``
    # thunk.  Under a marker reading the ``--`` would have been stripped and
    # the operand would read the bare name instead.
    assert "$seam(Inner, globals())" in rendered, rendered
