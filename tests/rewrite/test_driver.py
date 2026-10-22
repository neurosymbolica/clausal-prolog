"""The rewrite driver: fixpoint application, node-reuse splicing, comment
conservation, arrow safety.

The comment tests are the point of the whole design.  A rewriter that works on
text has to guess where a comment went; this one does not rewrite text at all.
Goals the rule kept are the SAME ``ast`` nodes they were, so their comments were
never in question, and a goal the rule deleted has to be given somewhere for its
comments to go or the format run fails.
"""

import textwrap

import pytest

from clausal.fmt import format_source
from clausal.rewrite.driver import RewriteError, rewrite_source
from tests._suffix import SEAM


def test_folds_and_reformats(head_fold_rules):
    src = "r(K, S) <- (m(K, M), S is unknown(M))\n"
    result = rewrite_source(src, head_fold_rules)
    assert result.text == "r(K, unknown(M)) <- (\n    m(K, M)\n)\n"
    assert len(result.fired) == 1


def test_untouched_file_is_exactly_fmt_output(head_fold_rules):
    src = "p(X) <- (m(X), r(X))\n\nband(1, 2),\nband(2, 3),\n"
    result = rewrite_source(src, head_fold_rules)
    assert result.text == format_source(src)
    assert result.fired == []


def test_clause_folds_to_fact_with_trailing_comma(head_fold_rules):
    result = rewrite_source("p(X) <- (X is 5)\n", head_fold_rules)
    assert result.text == "p(5),\n"


def test_fixpoint_folds_two_variables_in_one_clause(head_fold_rules):
    src = "r(A, B) <- (m(K), A is tag(K), B is ok)\n"
    result = rewrite_source(src, head_fold_rules)
    assert result.text == "r(tag(K), ok) <- (\n    m(K)\n)\n"
    assert len(result.fired) == 2


def test_a_directive_is_left_alone(head_fold_rules):
    src = "-module(m, [p(A)])\n\np(X) <- (X is 5)\n"
    result = rewrite_source(src, head_fold_rules)
    assert result.text == "-module(m, [p(A)])\n\np(5),\n"


def test_a_comma_separated_clause_series_is_left_alone(head_fold_rules):
    """Two clauses written as one comma-separated statement are exempt.

    The driver rewrites a statement that IS one clause.  A series is one
    statement holding several, and splicing into it would have to rebuild the
    series and re-derive which comma belongs to which clause -- so it is left
    byte-stable instead.  No file in this repo's corpus writes clauses that
    way, which is why it costs nothing today.
    """
    src = "p(X) <- (X is 5), r(1),\n"
    result = rewrite_source(src, head_fold_rules)
    assert result.fired == []
    assert result.text == src  # byte-stable, formatting included


def test_a_keyword_head_is_left_alone(head_fold_rules):
    """Reification drops a head's keyword NAMES; a rewrite would too.

    ``p(A=X, B=2)`` reifies as ``Goal("p", [X, 2], [])``, so re-rendering the
    head after a fold would emit ``p(5, 2)`` and quietly change what callers
    may write.  The driver leaves such clauses byte-stable rather than trade a
    fold for the predicate's interface.
    """
    result = rewrite_source("p(A=X, B=2) <- (X is 5)\n", head_fold_rules)
    assert result.fired == []
    assert "A=X" in result.text


def test_comments_on_surviving_goals_stay_put(head_fold_rules):
    src = (
        "# the requirement clause\n"
        "r(K, S) <- (\n"
        "    # look up the missing keys\n"
        "    m(K, M),  # trailing note\n"
        "    S is unknown(M)\n"
        ")\n"
    )
    result = rewrite_source(src, head_fold_rules)
    assert result.text == (
        "# the requirement clause\n"
        "r(K, unknown(M)) <- (\n"
        "    # look up the missing keys\n"
        "    m(K, M)  # trailing note\n"
        ")\n"
    )


def test_deleted_goal_comments_move_above_the_clause_marked_stale(head_fold_rules):
    # The relocated comment described a goal that no longer exists, so it is
    # flagged for the comment-repair pass (operator call, 2026-08-15).
    src = (
        "r(K, S) <- (\n"
        "    m(K, M),\n"
        "    # the verdict is unknown when keys are missing\n"
        "    S is unknown(M)\n"
        ")\n"
    )
    result = rewrite_source(src, head_fold_rules)
    assert result.text == (
        "# the verdict is unknown when keys are missing (maybe stale?)\n"
        "r(K, unknown(M)) <- (\n"
        "    m(K, M)\n"
        ")\n"
    )


def test_deleted_goal_trailing_comment_is_marked_stale_too(head_fold_rules):
    # The diversity trial's lint pragmas ride as trailing comments; they move
    # to the statement and carry the marker.
    src = (
        "r(K, S) <- (\n"
        "    m(K, M),\n"
        "    S is unknown(M)  # lint: do not fold\n"
        ")\n"
    )
    result = rewrite_source(src, head_fold_rules)
    assert "# lint: do not fold (maybe stale?)" in result.text


def test_surviving_goal_comments_are_not_marked(head_fold_rules):
    src = (
        "r(K, S) <- (\n"
        "    m(K, M),  # stays accurate\n"
        "    S is unknown(M)\n"
        ")\n"
    )
    result = rewrite_source(src, head_fold_rules)
    assert "# stays accurate\n" in result.text
    assert "stays accurate (maybe stale?)" not in result.text


def test_inline_lambda_in_a_surviving_goal_keeps_its_arrow(head_fold_rules):
    src = (
        "t(B, S) <- (\n"
        "    maplist(((X, V) <- (V == X * 2)), B),\n"
        "    S is found(B)\n"
        ")\n"
    )
    result = rewrite_source(src, head_fold_rules)
    assert "((X, V) <- (V == X * 2))" in result.text or "(X, V) <- (V == X * 2)" in result.text
    assert "< -" not in result.text
    assert "found(B)" in result.text.splitlines()[0]


def test_runaway_rule_hits_the_bound(tmp_path, head_fold_rules):
    runaway = tmp_path / f"runaway{SEAM}"
    runaway.write_text(textwrap.dedent("""\
        -double_quotes(chars)
        -import_from(reflection, [Clause])

        rewrite_clause(Clause(H, G, P), Clause(H, G, P)),
        """))
    with pytest.raises(RewriteError, match="20"):
        rewrite_source("p(X) <- (m(X))\n", [runaway])


def test_a_rule_that_invents_a_goal_is_refused_loudly(tmp_path):
    """Splicing reuses nodes, so a goal with no original has no node to reuse.

    Inventing goals is a real thing to want; it needs a rendering path and a
    decision about where its comments come from.  Until then the driver says
    so rather than mis-splicing.
    """
    inventive = tmp_path / f"inventive{SEAM}"
    inventive.write_text(textwrap.dedent("""\
        -double_quotes(chars)
        -import_from(reflection, [Clause, Goal])

        rewrite_clause(Clause(H, [G], P), Clause(H, [G, Goal("extra", [], [])], P)),
        """))
    with pytest.raises(RewriteError, match="splice"):
        rewrite_source("p(X) <- (m(X))\n", [inventive])


def test_a_rule_that_puts_a_lambda_in_the_head_is_refused(tmp_path):
    """``render_ast`` marks a rendered lambda arrow with a sentinel.

    Only the text-level renderer strips it, and the driver splices NODES, so a
    head carrying one would be written out with ``__clausal_lambda_arrow__``
    in it.  No shipped rule can produce that -- which is exactly why the guard
    has to be tested with one that can, or it is dead code.  It was: the guard
    matched a constant that never appears.
    """
    lambda_head = tmp_path / f"lambda_head{SEAM}"
    lambda_head.write_text(textwrap.dedent("""\
        -double_quotes(chars)
        -import_from(reflection, [Clause, Goal])

        # carry the lambda term out of the body goal and into the head
        rewrite_clause(Clause(Goal(NAME, ARGS, KW), [Goal(_, [LAM], _)], POS), Clause(Goal(NAME, [*ARGS, LAM], KW), [], POS)),
        """))
    with pytest.raises(RewriteError, match="lambda"):
        rewrite_source("p(X) <- (m(((Y) <- q(Y))))\n", [lambda_head])


def test_a_head_that_cannot_be_rendered_at_all_is_refused(tmp_path):
    """A rule may bind a head argument to something with no source form.

    An escape builds a Python callable, which the renderer refuses outright.
    That is a rule bug and is reported as one, not as a traceback escaping
    the driver.
    """
    callable_head = tmp_path / f"callable_head{SEAM}"
    callable_head.write_text(textwrap.dedent("""\
        -double_quotes(chars)
        -import_from(reflection, [Clause, Goal])

        rewrite_clause(Clause(Goal(NAME, ARGS, KW), GOALS, POS), Clause(HEAD2, GOALS, POS)) <- (
            LAM is ((X) <- p(X)),
            HEAD2 is Goal(NAME, [*ARGS, LAM], KW)
        )
        """))
    with pytest.raises(RewriteError, match="cannot be rendered"):
        rewrite_source("p(X) <- (m(X))\n", [callable_head])


# ---- modified goals: the positional correspondence -------------------------
#
# When a rule keeps the goal COUNT, the correspondence is positional: each
# output goal is its input goal verbatim or modified in place.  A modified
# goal is rendered to a fresh node; its comments ride across WITHOUT the
# stale marker, because the goal survives.


def _rename_rule(tmp_path):
    """old(...) becomes new(...) -- a one-goal modification, same goal count."""
    rule = tmp_path / f"rename{SEAM}"
    rule.write_text(textwrap.dedent("""\
        -double_quotes(chars)
        -private([old, new])
        -import_from(reflection, [Clause, Goal])

        rewrite_clause(Clause(H, GOALS, P), Clause(H, GOALS2, P)) <- (
            rename_goal(GOALS, GOALS2)
        )
        rename_goal([Goal(old, A, K), *GS], [Goal(new, A, K), *GS]),
        rename_goal([G, *GS], [G, *GS2]) <- rename_goal(GS, GS2)
        """))
    return [rule]


def test_modified_goal_is_spliced_in_place(tmp_path):
    src = "p(X) <- (m(X), old(X, 5))\n"
    result = rewrite_source(src, _rename_rule(tmp_path))
    assert result.text == "p(X) <- (\n    m(X),\n    new(X, 5)\n)\n"
    assert len(result.fired) == 1


def test_modified_goal_comments_ride_across_unmarked(tmp_path):
    src = (
        "p(X) <- (\n"
        "    m(X),\n"
        "    # still describes the call\n"
        "    old(X, 5)  # and so does this\n"
        ")\n"
    )
    result = rewrite_source(src, _rename_rule(tmp_path))
    assert result.text == (
        "p(X) <- (\n"
        "    m(X),\n"
        "    # still describes the call\n"
        "    new(X, 5)  # and so does this\n"
        ")\n"
    )
    assert "maybe stale" not in result.text


def test_modified_goal_keeps_a_surviving_inline_lambda_arrow(tmp_path):
    """The arrow route: a modified goal is rendered to TEXT and re-parsed, so
    a lambda that survives inside it must come back as ``<-``, never ``< -``.
    """
    src = "p(B) <- (old(((X, V) <- (V == X * 2)), B))\n"
    result = rewrite_source(src, _rename_rule(tmp_path))
    assert "new(((X, V) <- (V == X * 2)), B)" in result.text
    assert "< -" not in result.text


def test_modified_goal_keeps_a_genuine_less_than_negative(tmp_path):
    """The other half of the arrow rule: a real ``A < -B`` inside a modified
    goal renders spaced and is NOT registered as an arrow."""
    src = "p(A, B) <- (old(A < -B))\n"
    result = rewrite_source(src, _rename_rule(tmp_path))
    assert "new(A < -B)" in result.text
    assert "<- B" not in result.text.replace("p(A, B) <- (", "")


def test_modified_goal_keeps_a_quoted_atom_argument(tmp_path):
    """A modified goal is rendered to text and re-parsed: the renderer writes
    an atom single-quoted and a string double-quoted, and the formatter must
    write each back as rendered -- the quote character is the term."""
    src = "-double_quotes(chars)\np(X) <- (old(X, '=..', \"text\"))\n"
    result = rewrite_source(src, _rename_rule(tmp_path))
    assert "new(X, '=..', \"text\")" in result.text


def test_a_surviving_quoted_atom_goal_is_not_requoted(tmp_path):
    src = "-private([p(_)])\np(X) <- ('=='(X, a), old(X, 5))\n"
    result = rewrite_source(src, _rename_rule(tmp_path))
    assert "'=='(X, a)" in result.text
    assert '"=="' not in result.text


def test_equal_count_reorder_is_refused(tmp_path):
    """Swapping two goals keeps the count; the positional correspondence must
    not read the swap as two modifications and shuffle their comments."""
    swap = tmp_path / f"swap{SEAM}"
    swap.write_text(textwrap.dedent("""\
        -double_quotes(chars)
        -import_from(reflection, [Clause])

        rewrite_clause(Clause(H, [G1, G2], P), Clause(H, [G2, G1], P)),
        """))
    with pytest.raises(RewriteError, match="REORDER"):
        rewrite_source("p(X) <- (m(X), r(X))\n", [swap])


def test_modification_with_count_change_is_refused(tmp_path):
    """Modify one goal AND drop another: neither correspondence covers it."""
    mixed = tmp_path / f"mixed{SEAM}"
    mixed.write_text(textwrap.dedent("""\
        -double_quotes(chars)
        -private([old, new])
        -import_from(reflection, [Clause, Goal])

        rewrite_clause(Clause(H, [Goal(old, A, K), _], P), Clause(H, [Goal(new, A, K)], P)),
        """))
    with pytest.raises(RewriteError, match="splice"):
        rewrite_source("p(X) <- (old(X), m(X))\n", [mixed])


def test_modified_goal_that_is_not_a_goal_is_refused(tmp_path):
    """A conjunction group reifies as a bare list, which renders as a LIST
    LITERAL -- no faithful node, so the driver refuses rather than corrupt."""
    grouping = tmp_path / f"grouping{SEAM}"
    grouping.write_text(textwrap.dedent("""\
        -double_quotes(chars)
        -import_from(reflection, [Clause, Goal])

        rewrite_clause(Clause(H, [G], P), Clause(H, [[G, Goal("extra", [], [])]], P)),
        """))
    with pytest.raises(RewriteError, match="not a plain Goal"):
        rewrite_source("p(X) <- (m(X))\n", [grouping])


def test_modified_goal_rewrite_is_idempotent(tmp_path):
    src = "p(X) <- (m(X), old(X, 5))\n"
    rules = _rename_rule(tmp_path)
    once = rewrite_source(src, rules)
    again = rewrite_source(once.text, rules)
    assert again.text == once.text
    assert again.fired == []


def test_folds_a_single_char_atom(head_fold_rules):
    # The file pins ``-double_quotes(atom)`` explicitly: ``"t"`` is the
    # ATOM ("t",), and the folded head writes it back as the file spelled
    # it.  (It used to render as the bare name ``t``, which is the same
    # atom only where ``t`` is declared, and a load error elsewhere.)
    result = rewrite_source('-double_quotes(atom)\np(TAG) <- (TAG is "t", m(1))\n', head_fold_rules)
    assert result.text == '-double_quotes(atom)\n\np("t") <- (\n    m(1)\n)\n'
    assert len(result.fired) == 1


def test_the_file_mode_reaches_each_clause_segment(head_fold_rules):
    """The driver reifies each clause from its own SEGMENT, which never
    contains the file's ``-double_quotes`` directive, so the mode is tracked
    statement by statement and handed to the reifier.  Without that a
    chars file's ``"t"`` reified as an atom (before the flip) and an atom
    file's as a string (after it), and the folded head came back respelled
    -- the corpus idempotency test caught it on the first flipped run."""
    result = rewrite_source('-double_quotes(chars)\np(TAG) <- (TAG is "t", m(1))\n', head_fold_rules)
    assert result.text == '-double_quotes(chars)\n\np("t") <- (\n    m(1)\n)\n'
    result = rewrite_source('-double_quotes(atom)\np(TAG) <- (TAG is "t", m(1))\n', head_fold_rules)
    # The atom-mode ``"t"`` is written back as spelled: the same atom, and
    # not the bare ``t`` that only a declaration makes loadable.
    assert result.text == '-double_quotes(atom)\n\np("t") <- (\n    m(1)\n)\n'


def test_a_mid_file_directive_governs_only_the_clauses_below_it(head_fold_rules):
    """Tracked statement by statement: the clause above the directive folds
    under the default (chars), the clause below it under the declared
    atom mode."""
    src = ('p(TAG) <- (TAG is "t", m(1))\n'
           '-double_quotes(atom)\n'
           'q(TAG) <- (TAG is "u", m(2))\n')
    result = rewrite_source(src, head_fold_rules)
    assert 'p("t") <- (' in result.text
    assert 'q("u") <- (' in result.text     # the atom "u", spelled as the file spells it


def test_reify_ast_reads_a_segment_under_the_mode_it_is_handed():
    """The ``double_quotes=`` parameter itself, without the driver."""
    import ast
    from clausal.reflection import reify_ast, Clause, is_v, vfield
    stmt = ast.parse('p(X) <- (X is "t")\n').body[0]
    seen = {}
    for mode in ("atom", "chars"):
        clause = reify_ast(stmt, source='p(X) <- (X is "t")', double_quotes=mode)
        assert is_v(clause, Clause)
        (unify,) = vfield(clause, "goals")
        seen[mode] = unify.right
    assert seen["atom"] == ("Atom", "t"), seen
    assert seen["chars"] == "t", seen      # the carrier reifies as its plain str


def test_an_unknown_mode_is_left_to_the_loader(head_fold_rules):
    """``-double_quotes(codes)`` is a load error; the driver neither adopts
    it nor pretends it is atom mode -- the clause below it still reads
    under the mode in force (the default)."""
    import ast
    from clausal.rewrite.driver import _double_quotes_directive
    stmt = ast.parse("-double_quotes(codes)\n").body[0]
    assert _double_quotes_directive(stmt) is None
    src = '-double_quotes(codes)\np(TAG) <- (TAG is "t", m(1))\n'
    result = rewrite_source(src, head_fold_rules)
    assert 'p("t") <- (' in result.text


def test_folds_a_single_char_string(head_fold_rules):
    # The chars twin, written as the STRING the ``is`` goal binds.  What this
    # pins is the renderer's half: a folded STRING head argument comes back
    # DOUBLE-quoted, and is not demoted to an atom.
    from clausal.reflection import Clause, Goal, render_source
    folded = Clause(Goal("p", ["t"], []), [Goal("m", [1], [])], None)
    assert render_source(folded) == 'p("t") <- (m(1))'


# ---- atom spellings: a rewrite keeps 'Foo' an atom ------------------------
#
# ``'Foo'``, ``"Foo"`` and ``Foo`` are three terms in the seam and ONE
# vocabulary term, ``Atom("Foo")``.  The re-render used to write any
# identifier-shaped atom bare, so a rewrite that touched the goal turned
# ``'Foo'`` into a variable and ``'None'`` into Python's ``None``
# (todo/done/rewrite-rerender-spells-a-quoted-atom-bare-2026-10-21.md).  Each
# clause is now reified with its atoms' spellings and rendered back through
# them, and the output is read back and compared with what the rule meant.

_LITERALS = ["'a'", "'Foo'", "'_x'", "'None'", "'True'", "'if'", "'a.b'",
             "'foo bar'", '"a"']


@pytest.mark.parametrize("literal", _LITERALS)
def test_a_passed_through_literal_keeps_its_spelling(literal, unnecessary_lambda_rules):
    """The rule rewrites the lambda beside the literal and never touches the
    literal, which still has to be re-rendered with the goal."""
    src = f"p(R) <- (pass_through(((X) <- q(X)), {literal}, R))\n"
    result = rewrite_source(src, unnecessary_lambda_rules)
    assert len(result.fired) == 1
    assert f"pass_through(q, {literal}, R)" in result.text


@pytest.mark.parametrize("literal", ["'Foo'", "'None'", "'a.b'", "'a'"])
def test_a_folded_literal_keeps_its_spelling(literal, head_fold_rules):
    """head_fold moves the literal into a re-rendered HEAD."""
    src = f"r(K, S) <- (m(K, M), S is {literal})\n"
    result = rewrite_source(src, head_fold_rules)
    assert result.text == f"r(K, {literal}) <- (\n    m(K, M)\n)\n"


def test_an_atom_mode_double_quoted_atom_keeps_its_quotes(unnecessary_lambda_rules):
    src = '-double_quotes(atom)\n\np(R) <- (pass_through(((X) <- q(X)), "a", R))\n'
    result = rewrite_source(src, unnecessary_lambda_rules)
    assert 'pass_through(q, "a", R)' in result.text


def test_a_rule_built_atom_is_spelled_to_read_back_as_itself(tmp_path):
    """An atom the rule's template built has no source spelling.  It is bare
    only where the item itself spells that name bare (``m``, the goal's own
    functor) or it is a dotted name that reads back bare (``a.b``, a
    qualified reference); every other one is quoted -- ``'score'`` as much
    as ``'Foo'``, because whether a bare ``score`` is an atom, a predicate,
    an imported module or a load error is the file's decision -- and a name
    whose NFKC form differs (``ǅx`` would read back as the variable
    ``Džx``) is never bare."""
    builder = tmp_path / f"builder{SEAM}"
    builder.write_text(textwrap.dedent("""\
        -double_quotes(chars)
        -import_from(reflection, [Clause, Goal, Atom])

        rewrite_clause(Clause(H, [Goal('m', [_], KW)], P), Clause(H, [Goal('m', [Atom('Foo'), Atom('None'), Atom('if'), Atom('score'), Atom('a.b'), Atom('m'), Atom('ǅx'), Atom('a.ǅx')], KW)], P)),
        """))
    result = rewrite_source("p(X) <- (m(X))\n", [builder])
    assert "m('Foo', 'None', 'if', 'score', a.b, m, 'ǅx', 'a.ǅx')" in result.text


def test_a_callee_the_body_spells_bare_comes_out_bare(unnecessary_lambda_rules):
    """``Atom(CALLEE)`` is rule-built, and bare because the lambda body
    spelled the callee bare as a functor; a dotted callee likewise."""
    result = rewrite_source("t(L) <- (maplist(((X) <- add_one(X)), L))\n", unnecessary_lambda_rules)
    assert "maplist(add_one, L)" in result.text
    result = rewrite_source("t(L) <- (maplist(((X) <- mod.add_one(X)), L))\n", unnecessary_lambda_rules)
    assert "maplist(mod.add_one, L)" in result.text


# The four shapes where the by-name table alone is of two minds -- the item
# spells one name both ways -- and only the CELL can say which is which.
# ``_resolved`` keeps the cell a rule passed through, so each comes back as
# written; before, every one of these came out as the bare name twice.

def test_a_mixed_spelling_item_keeps_each_spelling(unnecessary_lambda_rules):
    src = "p(R) <- (pass_through(((X) <- q(X)), 'a', a, R))\n"
    assert "pass_through(q, 'a', a, R)" in rewrite_source(src, unnecessary_lambda_rules).text


def test_a_mixed_spelling_atom_mode_item_keeps_each_spelling(unnecessary_lambda_rules):
    src = '-double_quotes(atom)\np(R) <- (pass_through(((X) <- q(X)), \'a\', R), m("a"))\n'
    result = rewrite_source(src, unnecessary_lambda_rules).text
    assert "pass_through(q, 'a', R)" in result
    assert 'm("a")' in result


def test_a_folded_atom_beside_its_bare_twin_keeps_its_quotes(head_fold_rules):
    src = "r('a', S) <- (m(S2, M, a), S is 'a')\n"
    assert rewrite_source(src, head_fold_rules).text == "r('a', 'a') <- (\n    m(S2, M, a)\n)\n"


def test_a_folded_compound_keeps_the_spelling_of_each_atom_inside(head_fold_rules):
    src = "r(S) <- (m(M), S is g('Foo', [a, 'a']))\n"
    assert rewrite_source(src, head_fold_rules).text == "r(g('Foo', [a, 'a'])) <- (\n    m(M)\n)\n"


def test_a_lambda_kept_beside_the_rewrite_keeps_its_atom_and_its_parameter(unnecessary_lambda_rules):
    """``Y`` is the parameter and ``'Y'`` the atom; both ride through by cell."""
    src = "p(R) <- (pass_through(((X) <- q(X)), ((Y) <- r(Y, 'Y')), R))\n"
    assert "pass_through(q, ((Y,) <- r(Y, 'Y')), R)" in rewrite_source(src, unnecessary_lambda_rules).text


def test_an_imported_module_name_and_its_atom_stay_apart(unnecessary_lambda_rules):
    """Bare ``reflection`` is the module under ``-import_module``; the
    quoted one is the atom.  Neither may become the other."""
    src = "-import_module(reflection)\np(R) <- (pass_through(((X) <- q(X)), reflection, 'reflection', R))\n"
    assert "pass_through(q, reflection, 'reflection', R)" in rewrite_source(src, unnecessary_lambda_rules).text


def test_nfkc_sensitive_atoms_stay_quoted(unnecessary_lambda_rules):
    """Bare ``ǅx`` would read back as the variable ``Džx`` and bare ``ﬁle``
    as ``file``: the parser normalises identifiers."""
    src = "p(R) <- (pass_through(((X) <- q(X)), 'ǅx', 'ﬁle', R))\n"
    assert "pass_through(q, 'ǅx', 'ﬁle', R)" in rewrite_source(src, unnecessary_lambda_rules).text


# ---- dict-literal keys keep their spelling --------------------------------
#
# A dict whose keys are all constants reifies as a RAW dict, keyed by the
# atom's str (``'a'``) or the string's carrier (``"a"`` under
# ``-double_quotes(chars)``) -- not by an ``Atom`` cell, which the renderer
# could have spelled.  The re-render wrote an atom key as the string
# ``"a"`` and could not write a string key at all, and a bare key
# (``{a: 1}``) came back quoted, which reads back as the raw dict rather than
# the ``DictLiteral`` it was.  The read-back check refused each of these: a
# false refusal, never a silent edit.

_DICT_LITERALS = [
    "{'a': 1}",                    # constant
    "{'a': R}",                    # non-constant value, still a raw dict
    "{'Foo': 1, 'None': 2, 'a.b': 3, 'foo bar': 4}",
    '{"a": 1}',                    # a STRING key stays a string
    "{'a': 1, \"a\": 2}",          # the atom and the string of one name
    "{a: 1}",                      # a bare key: the DictLiteral form
    "{'a': R, b: 2}",              # quoted and bare keys in one DictLiteral
    "{'a': 1, K: 2}",              # a variable key
    "{'a': {'b': R}}",             # nested
]


@pytest.mark.parametrize("literal", _DICT_LITERALS)
def test_a_passed_through_dict_keeps_its_key_spellings(literal, unnecessary_lambda_rules):
    src = f"p(R, K) <- (pass_through(((X) <- q(X)), {literal}, R, K))\n"
    result = rewrite_source(src, unnecessary_lambda_rules)
    assert len(result.fired) == 1
    assert f"pass_through(q, {literal}, R, K)" in result.text


@pytest.mark.parametrize("literal", ['{"a": 1}', "{'a': 1}", '{"a": 1, \'b\': 2}'])
def test_an_atom_mode_dict_keeps_its_key_spellings(literal, unnecessary_lambda_rules):
    src = f"-double_quotes(atom)\n\np(R) <- (pass_through(((X) <- q(X)), {literal}, R))\n"
    result = rewrite_source(src, unnecessary_lambda_rules)
    assert f"pass_through(q, {literal}, R)" in result.text


def test_an_atom_mode_item_spelling_one_key_two_ways_keeps_each(unnecessary_lambda_rules):
    """By name alone ``a`` is spelled two ways here; only the dict the rule
    passed through can say which key was which."""
    src = ("-double_quotes(atom)\n\n"
           "p(R) <- (pass_through(((X) <- q(X)), {\"a\": 1}, {'a': 2}, R))\n")
    result = rewrite_source(src, unnecessary_lambda_rules)
    assert "pass_through(q, {\"a\": 1}, {'a': 2}, R)" in result.text


@pytest.mark.parametrize("clause", ["p(X) <- (m(X))\n", "p(X) <- (m(X), n(a, 'b', b))\n"])
def test_a_rule_built_dict_keeps_its_key_kinds(clause, tmp_path):
    """A dict the rule's template builds arrives as a runtime ``DictTerm``
    with an atom key ``'a'`` and a string key ``"b"``.  Its atom key is
    always written quoted, whatever the item spells bare: a bare key would
    read back as a ``DictLiteral``, not as this dict."""
    builder = tmp_path / f"builder{SEAM}"
    builder.write_text(textwrap.dedent("""\
        -double_quotes(chars)
        -import_from(reflection, [Clause, Goal, Variable])

        rewrite_clause(Clause(H, [Goal('m', [Variable(N)], KW), *GS], P), Clause(H, [Goal('m', [{'a': Variable(N), "b": 2}], KW), *GS], P)),
        """))
    result = rewrite_source(clause, [builder])
    assert "m({'a': X, \"b\": 2})" in result.text


def test_a_rule_built_atom_named_like_a_lambda_parameter_is_refused():
    """Inside ``((Y) <- r(Y))`` the parameter reference and the atom ``Y``
    reify alike.  One the source wrote is spelled by its cell; one a rule
    built is ambiguous, and refused rather than guessed."""
    import dataclasses
    from clausal.reflection import Atom, AtomSpellings, RenderError, reify_source, render_source, vfield
    spellings = AtomSpellings()
    (clause,) = reify_source("p(R) <- (pass_through(((Y) <- r(Y)), R))\n", spellings=spellings)
    (goal,) = vfield(clause, "goals")
    lam = vfield(goal, "args")[0]
    assert "r(Y)" in render_source(goal, spellings)       # the source's own reference
    rebuilt = dataclasses.replace(lam, body=("Goal", "r", [Atom("Y")], []))
    with pytest.raises(RenderError, match="may be the parameter or the atom"):
        render_source(("Goal", "pass_through", [rebuilt, vfield(goal, "args")[1]], []), spellings)


def test_a_rule_built_atom_named_like_a_parameter_outside_its_lambda_is_quoted(tmp_path):
    """The parameter reference ``X`` inside the lambda is spelled by its cell
    only; it is not the item spelling the atom ``X`` bare, so a rule-built
    ``Atom('X')`` OUTSIDE the lambda is written ``'X'`` and not refused."""
    builder = tmp_path / f"builder{SEAM}"
    builder.write_text(textwrap.dedent("""\
        -double_quotes(chars)
        -import_from(reflection, [Clause, Goal, Atom, Variable])

        rewrite_clause(Clause(H, [Goal('m', [Variable(_)], KW), G], P), Clause(H, [Goal('m', [Atom('X')], KW), G], P)),
        """))
    src = "p(L) <- (m(L), maplist(((X) <- q(X, 1)), L))\n"
    result = rewrite_source(src, [builder])
    assert "m('X')" in result.text
    assert "maplist((X <- q(X, 1)), L)" in result.text     # the kept lambda, as the formatter writes it


def test_resolved_keeps_the_cells_a_rule_passed_through():
    """``_deref_walk`` rebuilds every tuple; the driver's walk returns an
    unchanged tuple itself, so a passed-through atom still answers by cell."""
    from clausal.logic.solve import _deref_walk
    from clausal.logic.variables import Trail, Var, unify
    from clausal.reflection import Atom, Goal
    from clausal.rewrite.driver import _resolved_keeping_cells
    atom = Atom("a")
    bound = Var()
    unify(bound, atom, Trail())
    answer = Goal("p", [bound, atom, [atom]], [])
    resolved = _resolved_keeping_cells(answer)
    assert resolved == Goal("p", [atom, atom, [atom]], [])
    assert all(cell is atom for cell in (resolved[2][0], resolved[2][1], resolved[2][2][0]))
    assert _deref_walk(answer)[2][1] is not atom


def test_a_rebuilt_atom_is_spelled_as_the_clause_spells_it(tmp_path):
    """``Atom(N)`` rebuilt from a name the rule took out of the clause is a
    NEW cell, so it has no spelling by identity; it is spelled the way the
    clause spells that name when the clause spells it one way."""
    doubler = tmp_path / f"doubler{SEAM}"
    doubler.write_text(textwrap.dedent("""\
        -double_quotes(chars)
        -import_from(reflection, [Clause, Goal, Atom])

        rewrite_clause(Clause(H, [Goal('m', [Atom(N)], KW)], P), Clause(H, [Goal('m', [Atom(N), Atom(N)], KW)], P)),
        """))
    assert "m('a', 'a')" in rewrite_source("p(1) <- (m('a'))\n", [doubler]).text
    assert "m(a, a)" in rewrite_source("p(1) <- (m(a))\n", [doubler]).text
    assert "m('Foo', 'Foo')" in rewrite_source("p(1) <- (m('Foo'))\n", [doubler]).text


def test_the_output_must_read_back_as_the_rule_meant(monkeypatch, unnecessary_lambda_rules):
    """The driver's own fence: the formatted output is reified again and held
    to the rule's term, so a renderer that respelled an atom -- here the old
    one, which wrote every identifier-shaped atom bare -- is refused rather
    than written.  Nothing short of this notices a bug in the splice or the
    emitter either."""
    import clausal.rewrite.driver as driver
    from clausal import reflection

    render = driver.render_source
    monkeypatch.setattr(driver, "render_source",
                        lambda term, spellings=None: render(term, None))
    monkeypatch.setattr(reflection, "_reads_back_bare",
                        reflection._is_dotted_identifier)
    src = "p(R) <- (pass_through(((X) <- q(X)), 'Foo', R))\n"
    with pytest.raises(RewriteError, match="does not read back") as caught:
        rewrite_source(src, unnecessary_lambda_rules)
    assert "('Atom', 'Foo')" in str(caught.value)
    assert "('Variable', 'Foo')" in str(caught.value)


class TestReadsBackAs:
    """The comparison behind the fence, on the pairs it must tell apart."""

    @staticmethod
    def _run(meant, read, meant_spellings=None, read_spellings=None):
        from clausal.reflection import AtomSpellings
        from clausal.rewrite.driver import _reads_back_as
        return _reads_back_as(meant, read,
                              meant_spellings or AtomSpellings(),
                              read_spellings or AtomSpellings())

    def test_an_atom_read_as_a_variable_a_constant_or_a_string_differs(self):
        from clausal.reflection import Atom, Goal, Variable
        for read in (Variable("Foo"), None, "Foo", Goal("Foo", [], [])):
            assert self._run(Goal("p", [Atom("Foo")], []),
                             Goal("p", [read], [])) == (Atom("Foo"), read)

    def test_a_passed_through_atom_must_keep_its_quote(self):
        from clausal.reflection import Atom, AtomSpellings
        meant, read = Atom("a"), Atom("a")
        meant_spellings, read_spellings = AtomSpellings(), AtomSpellings()
        meant_spellings.record(meant, "'")
        read_spellings.record(read, "")
        assert self._run(meant, read, meant_spellings, read_spellings) == (meant, read)
        read_spellings.record(read, "'")
        assert self._run(meant, read, meant_spellings, read_spellings) is None

    def test_a_rule_built_atom_accepts_whatever_spelling_read_back(self):
        from clausal.reflection import Atom, AtomSpellings
        read = Atom("score")
        read_spellings = AtomSpellings()
        read_spellings.record(read, "")
        assert self._run(Atom("score"), read, None, read_spellings) is None

    def test_positions_and_anonymous_numbering_are_not_differences(self):
        from clausal.reflection import Clause, Escape, Goal, Variable, vfield
        meant = Clause(Goal("p", [Variable("#anon1")], []),
                       [Escape("X + 1", [Variable("X")], (1, 5, 1, 9))], (1, 0, 1, 20))
        read = Clause(Goal("p", [Variable("#anon7")], []),
                      [Escape("X + 1", [Variable("X")], (3, 4, 3, 8))], (2, 0, 4, 1))
        assert self._run(meant, read) is None
        assert self._run(meant, Clause(Goal("p", [Variable("Y")], []),
                                       vfield(read, "goals"), None)) is not None

    def test_operator_nodes_are_walked_not_compared_whole(self):
        from clausal.reflection import Atom, AtomSpellings, reify_source
        meant_spellings, read_spellings = AtomSpellings(), AtomSpellings()
        (meant,) = reify_source("p(X) <- (X is 'a')\n", spellings=meant_spellings)
        (read,) = reify_source("p(X) <- (X is a)\n", spellings=read_spellings)
        assert self._run(meant, read, meant_spellings, read_spellings) == (Atom("a"), Atom("a"))
        (read,) = reify_source("p(X) <- (X is 'a')\n", spellings=read_spellings)
        assert self._run(meant, read, meant_spellings, read_spellings) is None
