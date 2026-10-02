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
from clausal.logic.atoms import spelling
from clausal.logic.cells import chars
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from tests._suffix import SEAM


def _load(tmp_path, name, text):
    path = tmp_path / f"{name}{SEAM}"
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
        -double_quotes(atom)
        -private([red])
        -module(cvmit_slot_top, [p(S)])
        tree(red),
        p(S) <- (tree(Node), S is f"{--Node}")
    """)
    assert _answers(mod, "p") == [("red",)]


def test_marker_and_bare_name_agree_in_an_fstring_slot(tmp_path):
    """The additivity contract: one position, both spellings, one answer."""
    marked = _load(tmp_path, "slot_marked", """
        -double_quotes(atom)
        -private([red])
        -module(cvmit_slot_marked, [p(S)])
        tree(red),
        p(S) <- (tree(Node), S is f"{--Node}")
    """)
    bare = _load(tmp_path, "slot_bare", """
        -double_quotes(atom)
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
        -double_quotes(atom)
        -private([red])
        -module(cvmit_deep_marked, [p(S)])
        tree(red),
        p(S) <- (tree(Node), S is f"{str(--Node).upper()}")
    """)
    bare = _load(tmp_path, "deep_bare", """
        -double_quotes(atom)
        -private([red])
        -module(cvmit_deep_bare, [p(S)])
        tree(red),
        p(S) <- (tree(Node), S is f"{str(Node).upper()}")
    """)
    assert _answers(marked, "p") == _answers(bare, "p") == [("RED",)]


def test_marker_in_a_slot_carrying_a_format_spec(tmp_path):
    """A format spec applies to the VALUE, so the marker must survive one."""
    mod = _load(tmp_path, "slot_spec", """
        -double_quotes(atom)
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
            -double_quotes(atom)
            -module(cvmit_unbound, [p(S)])
            p(S) <- (S is f"{--Node}")
        """)
    message = str(excinfo.value)
    assert "--Node" in message, message
    # Located, with the offending line and a caret — the diagnostic has
    # to be reachable from the file, not just true.
    assert f"unbound{SEAM}, line 3" in message, message
    assert 'f"{--Node}"' in message, message

    bare = _load(tmp_path, "unbound_bare", """
        -double_quotes(atom)
        -module(cvmit_unbound_bare, [p(S)])
        p(S) <- (S is f"{Node}")
    """)
    [(rendered,)] = _answers(bare, "p")
    assert spelling(rendered).startswith("<class "), rendered


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
            -double_quotes(atom)
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
        -double_quotes(atom)
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


# ── The marker sees the whole clause, like the bare name does ──────────────

def test_two_markers_and_a_bare_name_in_one_thunk(tmp_path):
    """More than one marker per thunk, mixed with a bare occurrence of a
    marked name — the lambda has ONE parameter namespace, so a spelling that
    is captured must be captured for every occurrence in the body."""
    mod = _load(tmp_path, "two", """
        -double_quotes(atom)
        -private([red, blue])
        -module(cvmit_two, [p(S)])
        tree(red),
        sky(blue),
        p(S) <- (tree(Node), sky(Match), S is f"{--Node}/{--Match}/{Node}")
    """)
    assert _answers(mod, "p") == [("red/blue/red",)]


def test_a_marker_in_the_head_sees_what_the_body_binds(tmp_path):
    """A clause is visited as one root per head argument and then the body,
    so a HEAD thunk is lowered before the body's names would be known.  The
    up-front note is what lets the marker in a head argument load at all --
    without it this is the "no goal binds `Node`" error.

    The ANSWER is an unbound variable, because head unification happens
    before ``tree/1`` runs; the point is that the marker and the bare name
    agree about that, rather than one of them refusing to load."""
    marked = _load(tmp_path, "head_marked", """
        -double_quotes(atom)
        -private([red])
        -module(cvmit_head_marked, [p(S)])
        tree(red),
        p(f"{--Node}") <- (tree(Node))
    """)
    bare = _load(tmp_path, "head_bare", """
        -double_quotes(atom)
        -private([red])
        -module(cvmit_head_bare, [p(S)])
        tree(red),
        p(f"{Node}") <- (tree(Node))
    """)
    [(from_marked,)] = _answers(marked, "p")
    [(from_bare,)] = _answers(bare, "p")
    assert spelling(from_marked).startswith("_") and spelling(from_bare).startswith("_"), (
        from_marked, from_bare)
    assert "class" not in spelling(from_marked), from_marked


# ── The promise holds everywhere the marker can be typed ───────────────────

def test_a_marker_in_a_format_spec_is_a_load_error(tmp_path):
    """The one position where the marker could be SILENTLY misread.

    A nested slot in a format spec is a `JoinedStr` on
    ``FormattedValue.format_spec``, and nothing walks ``format_spec``: not
    the implicit collector, not the marker collector, not the stripper.  So
    a marker there reached the lambda body as literal ``--Match`` and found
    the module-namespace class, dying at QUERY time with ``bad operand type
    for unary -: 'type'`` and no load diagnostic at all.

    The marker is sold as the spelling that cannot be silently misread, so
    the position where it could be is refused at load time.  Refused rather
    than made to work, because the BARE spelling captures nothing in a
    format spec either; honouring only the marker would split the two
    spellings apart in exactly the place a reader reaches for the marker."""
    with pytest.raises(SyntaxError) as excinfo:
        _load(tmp_path, "spec_marker", """
            -double_quotes(atom)
            -private([red])
            -module(cvmit_spec_marker, [p(S)])
            tree(red),
            width(5),
            p(S) <- (tree(Node), width(Width), S is f"{Node:>{--Width}}")
        """)
    message = str(excinfo.value)
    assert "--Width" in message, message
    assert "format spec" in message, message
    assert f"spec_marker{SEAM}, line 6" in message, message


def test_the_format_spec_refusal_fires_on_an_unbindable_name_too(tmp_path):
    """The shape that used to die at query time as `'type'`: `Match` is a
    module-namespace class and no goal binds it, so neither the marker's own
    check nor anything else would have spoken."""
    with pytest.raises(SyntaxError) as excinfo:
        _load(tmp_path, "spec_class", """
            -double_quotes(atom)
            -private([red])
            -module(cvmit_spec_class, [p(S)])
            tree(red),
            p(S) <- (tree(Node), S is f"{Node:>{--Match}}")
        """)
    assert "--Match" in str(excinfo.value)


def test_a_marker_in_the_value_slot_of_a_formatted_value_still_works(
        tmp_path):
    """The refusal is scoped to the SPEC.  A marker in the value slot of a
    slot that also carries a spec is untouched -- pinned so the refusal
    cannot widen into the position the feature is for."""
    mod = _load(tmp_path, "spec_value_ok", """
        -double_quotes(atom)
        -private([red])
        -module(cvmit_spec_value_ok, [p(S)])
        tree(red),
        p(S) <- (tree(Node), S is f"{--Node:>5}")
    """)
    assert _answers(mod, "p") == [("  red",)]


# ── The block form bears markers; the inline seam does not ─────────────────

def test_the_dash_dash_block_form_bears_a_marker():
    """`with --{} as clauses:` is a block DELIMITER, not a seam operand: its
    statements are Clausal terms, not hosted Python handed back to a Python
    visitor, so there is no competing reading of `--` inside a thunk there.
    The marker is live, and this pins that rather than leaving it to
    whichever transformer flag happened to be set."""
    from clausal.templating.term_rewriting import EmbedTransformer, unparse
    tree = ast.parse(
        'with --{} as clauses:\n    tree(Node)\n    bar(f"{--Node}")\n')
    ast.fix_missing_locations(tree)
    out = EmbedTransformer().visit(tree)
    ast.fix_missing_locations(out)
    rendered = unparse(out)
    # Stripped to the bare name and captured as a lambda parameter.
    # (the body is the chars carrier of the f-string: ruling R2)
    assert "lambda Node: ('$chars', f'{Node}')" in rendered, rendered


def test_the_block_forms_marker_is_checked_like_any_other():
    """And the check travels with it -- the block's statements are one
    scope, so a marked name no statement binds is the same load error."""
    from clausal.templating.term_rewriting import EmbedTransformer
    tree = ast.parse('with --{} as clauses:\n    bar(f"{--Node}")\n')
    ast.fix_missing_locations(tree)
    with pytest.raises(SyntaxError) as excinfo:
        EmbedTransformer().visit(tree)
    assert "--Node" in str(excinfo.value)
