"""A SINGLE-quoted name in functor position is an ATOM, so it is legal.

ISO 13211-1 names a functor with an *atom*, and a single-quoted token is an
atom by construction — its spelling is data, not an identifier, so the
capitalisation conventions that decide what a BARE token means never apply to
it.  Checked against Trealla: ``X = 'Foo'(1)`` answers with the compound
``Foo(1)``, while the unquoted ``Foo(1)`` is a
``syntax_error(variable_cannot_be_functor)``.

Clausal used to refuse both.  The quoted form was closed as a bypass of the
TitleCase lint at a time when TitleCase had no legitimate reading anywhere;
once a capital-initial BARE name became a logic variable, the quoted spelling
became the one unambiguous way to *say* the atom, and refusing it was the
remaining deviation.  So the asymmetry is now exactly ISO's:

    'Foo'(1),                  # an atom names the predicate Foo/1
    Foo(X) <- (bar(X))         # a variable cannot be a functor

The rest of this file pins what did NOT move with it: the double-quote
refusal (ISO 6.3.3), the fact-head plain-name limit, and the guard against a
predicate name the same file also reads as a variable.
"""

from __future__ import annotations

import textwrap

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


def _kind(item):
    """The reified item's KIND.

    P2: a reified item is a CELL, so `type(item).__name__` is
    "tuple" for every one of them; the kind is the functor."""
    from clausal.logic.cells import compound_cell_shape

    is_cell, functor = compound_cell_shape(item)
    return functor if is_cell else type(item).__name__


def _load(tmp_path, name, text):
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(text).lstrip())
    return _load_module(f"tests_qaf_{name}", str(path))


def _answers(mod, pred, arity):
    """Every answer for *pred*/*arity*, as tuples of dereferenced bindings."""
    args = [Var() for _ in range(arity)]
    return [tuple(deref(a) for a in args)
            for _ in call(pred, *args, module=mod.__dict__["$module"])]


# ── The three positions that must now load, and MEAN Foo/1 ────────────────


class TestQuotedTitleCaseFunctorIsAnAtom:
    """All three functor positions the sugar reaches, each asserting the
    ANSWER — loading is not enough, the clause has to be Foo/1's."""

    def test_fact_head(self, tmp_path):
        mod = _load(tmp_path, "fact", "'Foo'(1),\n")
        assert _answers(mod, "Foo", 1) == [(1,)]

    def test_body_goal(self, tmp_path):
        mod = _load(tmp_path, "body", """
            'Foo'(7),
            p(X) <- ('Foo'(X))
        """)
        assert _answers(mod, "p", 1) == [(7,)]

    def test_clause_head(self, tmp_path):
        mod = _load(tmp_path, "head", """
            bar(3),
            'Foo'(X) <- (bar(X))
        """)
        assert _answers(mod, "Foo", 1) == [(3,)]

    def test_the_quoted_and_bare_lowercase_spellings_are_one_predicate(
            self, tmp_path):
        """``'Foo'`` names an atom, and the atom is the predicate's name —
        so a clause written one way is reachable from the other."""
        mod = _load(tmp_path, "same", """
            'Foo'(1),
            'Foo'(2) <- (true)
        """)
        assert _answers(mod, "Foo", 1) == [(1,), (2,)]


# ── No-regression pins ────────────────────────────────────────────────────


def test_capitalised_quoted_atom_in_argument_position_still_works(tmp_path):
    """An argument was never a functor position, so this always loaded; it is
    pinned because the change is about how a quoted spelling is READ."""
    mod = _load(tmp_path, "arg", "kind('Oral'),\n")
    assert _answers(mod, "kind", 1) == [("Oral",)]


def test_lowercase_quoted_functor_is_unchanged(tmp_path):
    mod = _load(tmp_path, "lower", """
        'foo'(1),
        q(X) <- ('foo'(X))
    """)
    assert _answers(mod, "foo", 1) == [(1,)]
    assert _answers(mod, "q", 1) == [(1,)]


# ── What must still be refused ────────────────────────────────────────────


def test_bare_titlecase_functor_is_still_refused(tmp_path):
    """ISO's ``variable_cannot_be_functor``: a capital-initial BARE name is a
    variable, and this is the whole point of the asymmetry."""
    with pytest.raises(SyntaxError) as exc_info:
        _load(tmp_path, "bare", """
            bar(1),
            Foo(X) <- (bar(X))
        """)
    message = str(exc_info.value)
    assert "`Foo` is TitleCase" in message
    assert "bare.clausal:2" in message


def test_bare_titlecase_body_goal_is_still_refused(tmp_path):
    with pytest.raises(SyntaxError, match="`Foo` is TitleCase"):
        _load(tmp_path, "barebody", """
            bar(1),
            p(X) <- (Foo(X))
        """)


@pytest.mark.parametrize("name, text", [
    ("dqfact", '"Foo"(1),\n'),
    ("dqbody", 'bar(1),\np(X) <- ("Foo"(X))\n'),
    ("dqlower", '"foo"(1),\n'),
])
def test_double_quoted_functor_is_still_refused_by_iso_633(
        tmp_path, name, text):
    """A double-quoted literal is not an atom spelling, so it can never name
    a functor — and now that the TitleCase lint no longer fires first, the
    capitalised case gets the SAME ISO 6.3.3 message the lowercase one
    always got, rather than advice about renaming an identifier."""
    with pytest.raises(SyntaxError) as exc_info:
        _load(tmp_path, name, text)
    message = str(exc_info.value)
    assert "a double-quoted string is never a functor (ISO 6.3.3)" in message
    assert "TitleCase" not in message


@pytest.mark.parametrize("name, text, shape", [
    ("spacey_fact", "'foo bar'(1),\n", "fact"),
    ("spacey_rule", "bar(3),\n'foo bar'(X) <- (bar(X))\n", "clause"),
    ("spacey_dcg", "'foo bar'(X) >> ([X])\n", "DCG rule"),
    ("keyword_rule", "bar(3),\n'class'(X) <- (bar(X))\n", "clause"),
])
def test_non_identifier_quoted_head_is_still_refused(
        tmp_path, name, text, shape):
    """A Clausal implementation limit, not an ISO rule, and out of scope
    here: a head is compiled to a functor class whose name is emitted as
    Python source.  Pinned so it cannot decay into a parse error blamed on
    generated code the author never wrote — for every head shape, since
    they now share one reading of the quoted functor."""
    with pytest.raises(SyntaxError) as exc_info:
        _load(tmp_path, name, text)
    message = str(exc_info.value)
    assert "is not a plain name" in message
    assert f"cannot head a {shape}" in message


def test_a_quoted_dcg_head_names_the_same_predicate(tmp_path):
    """A DCG head is a head: it reads the quoted functor as the other two
    do, rather than falling through to hosted Python."""
    mod = _load(tmp_path, "dcg", "'Foo'(X) >> ([X])\n")
    assert _answers(mod, "Foo", 3) != []


# ── The var-shaped-name guard still discriminates ─────────────────────────


class TestVarShapedPredicateNameGuard:
    """``_check_var_shaped_predicate_names`` rejects a predicate whose name
    the same file ALSO reads as a variable, because a bare ``Foo(...)`` in a
    body is a fresh Var rather than a call and the module global gets
    rebound.  Quoting the functor removes the ambiguity at the call sites,
    but it cannot remove it from a file that still writes the bare name
    somewhere a value goes."""

    def test_quoted_only_file_is_coherent_and_loads(self, tmp_path):
        mod = _load(tmp_path, "quotedonly", """
            'Foo'(1),
            q(X) <- ('Foo'(X))
        """)
        assert _answers(mod, "q", 1) == [(1,)]

    def test_quoted_head_plus_a_bare_variable_read_is_still_refused(
            self, tmp_path):
        with pytest.raises(SyntaxError) as exc_info:
            _load(tmp_path, "quotedplusvar", """
                'Foo'(1),
                q(X) <- ('Foo'(X))
                r(Foo) <- (Foo > 0)
            """)
        message = str(exc_info.value)
        assert "also read as a logic variable" in message
        assert "'Foo'" in message
        assert "'AttVar' object is not callable" in message
        assert "capital-initial name is a logic variable" in message


# ── The ISO 6.3.3 hint must not name a second fault ───────────────────────


@pytest.mark.parametrize("name, spelling", [
    ("hint_tc", "Foo"),      # refused by the TitleCase lint
    ("hint_caps", "FOO"),    # silently the unit-annotation sugar
    ("hint_us", "_p"),       # ditto -- the callable carve-out is TitleCase-only
])
def test_double_quoted_message_offers_no_bare_variable_shaped_name(
        tmp_path, name, spelling):
    """The message offers the bare spelling when it is a plain name.  For a
    VARIABLE-shaped one it must not: bare in functor position that is either
    refused outright or read as a Quantity, so the suggested fix would be a
    second fault.  ``_p`` is the case a "capital initial" test would miss --
    ``_reads_as_variable``'s callable carve-out covers TitleCase only, which
    is why ``_p(N, X) <- (... _p(M, X))`` is refused as a variable read."""
    with pytest.raises(SyntaxError) as exc_info:
        _load(tmp_path, name, f'"{spelling}"(1),\n')
    message = str(exc_info.value)
    assert f"write '{spelling}'(...) for the atom" in message
    assert f"{spelling}(...) if it is a plain name" not in message


def test_a_plain_lowercase_name_still_gets_the_bare_hint(tmp_path):
    """The control: ``foo`` is not variable-shaped, so the bare form really
    is the alternative and the hint stays."""
    with pytest.raises(SyntaxError) as exc_info:
        _load(tmp_path, "hint_low", '"foo"(1),\n')
    assert "foo(...) if it is a plain name" in str(exc_info.value)


# ── Reflection ────────────────────────────────────────────────────────────


class TestReify:
    """``reify_source`` models more shapes than the compiler accepts, but
    not this one, and the reason is measurable rather than a matter of
    taste: reflection runs the same ``visit_Expr``, which mints the functor
    class by ``parse()``-ing its name.  So the plain-name limit binds it
    too, and the right answer is the attributed message rather than
    CPython's."""

    def test_a_quoted_titlecase_head_reifies_as_a_clause(self):
        from clausal.reflection import Clause, reify_source, is_v
        items = reify_source("'Foo'(X) <- (bar(X))\n")
        assert [_kind(i) for i in items] == ["Clause"]
        assert is_v(items[0], Clause)

    @pytest.mark.parametrize("src", [
        "'foo bar'(1),\n",
        "'foo bar'(X) <- (bar(X))\n",
        "'class'(X) >> ([X])\n",
    ])
    def test_a_non_plain_head_raises_the_ATTRIBUTED_message(self, src):
        """Not "invalid syntax ... (<unknown>, line 4)" -- that is what an
        exemption here produces, because the class name still reaches
        ``parse()``."""
        from clausal.reflection import ReifyError, reify_source, is_v
        with pytest.raises(ReifyError) as exc_info:
            reify_source(src)
        message = str(exc_info.value)
        assert "is not a plain name" in message
        assert "invalid syntax" not in message

    @pytest.mark.parametrize("src", [
        "p(X) <- ('foo bar'(X))\n",
        "p(X) <- ('class'(X))\n",
    ])
    def test_the_same_spelling_in_a_BODY_still_reifies(self, src):
        """A goal names an atom and mints no class, so nothing stops it --
        the asymmetry mirrors the representation, it is not an oversight."""
        from clausal.reflection import reify_source, is_v
        assert [_kind(i) for i in reify_source(src)] == ["Clause"]

    def test_a_double_quoted_head_still_reifies(self):
        """The ISO 6.3.3 refusal IS reify-exempt -- its reason (an atom
        spelling) is one reflection does not care about.  Pinned so the two
        rules stay distinguishable."""
        from clausal.reflection import reify_source, is_v
        assert reify_source('"foo"(1),\n') != []


# ── A quoted entry in a declaration list is a real entry ───────────────────


class TestQuotedDeclarationEntry:
    """A quoted entry used to fall through to "other item shapes", which
    registers NOTHING -- no class, no signature, hence no arity check --
    while the file still loaded.  That was true of the lowercase spelling
    before any of this, so it is not TitleCase's fault; but a capitalised
    predicate has no bare spelling, so leaving it would have meant such a
    predicate could be defined and never declared.
    """

    @pytest.mark.parametrize("name, entry, head", [
        ("bare", "foo(A, B)", "foo(1),"),
        ("quoted", "'foo'(A, B)", "'foo'(1),"),
        ("quoted_tc", "'Foo'(A, B)", "'Foo'(1),"),
    ])
    def test_the_declared_arity_is_enforced_against_a_clause(
            self, tmp_path, name, entry, head):
        """The discriminating behaviour: a field-carrying entry fixes the
        signature, and a clause that contradicts it is refused.  A dropped
        entry shows up here as silence."""
        with pytest.raises(SyntaxError, match=r"conflicts with the declaration"):
            _load(tmp_path, f"arity_{name}",
                  f"-module(m, [{entry}])\n{head}\n")

    @pytest.mark.parametrize("name, entry, bound", [
        ("bare_call", "foo(A, B)", "foo"),
        ("bare_slash", "foo/2", "foo"),
        ("quoted_call", "'foo'(A, B)", "foo"),
        ("quoted_slash", "'foo'/2", "foo"),
        ("quoted_tc_call", "'Foo'(A, B)", "Foo"),
        ("quoted_tc_slash", "'Foo'/2", "Foo"),
    ])
    def test_a_clause_free_declaration_still_mints_the_predicate(
            self, tmp_path, name, entry, bound):
        """The second, independent discriminator: a declaration with no
        clause at all binds the name.  It answered False for every quoted
        spelling."""
        mod = _load(tmp_path, f"mint_{name}", f"-module(m, [{entry}])\n")
        assert bound in vars(mod)

    def test_a_capitalised_predicate_can_be_exported_and_used(self, tmp_path):
        mod = _load(tmp_path, "exported", """
            -module(m, ['Foo'(X)])
            'Foo'(1),
        """)
        assert _answers(mod, "Foo", 1) == [(1,)]

    def test_private_takes_the_quoted_entry_in_both_spellings(self, tmp_path):
        for name, entry in (("slash", "'Foo'/1"), ("call", "'Foo'(X)")):
            mod = _load(tmp_path, f"priv_{name}",
                        f"-private([{entry}])\n'Foo'(1),\n")
            assert _answers(mod, "Foo", 1) == [(1,)]

    @pytest.mark.parametrize("name, entry", [
        ("dq_call", '"foo"(X)'),
        ("dq_slash", '"foo"/1'),
    ])
    def test_a_double_quoted_entry_is_refused_by_iso_633(
            self, tmp_path, name, entry):
        with pytest.raises(SyntaxError,
                           match=r"never a functor \(ISO 6\.3\.3\)"):
            _load(tmp_path, name, f"-module(m, [{entry}])\n")

    @pytest.mark.parametrize("name, entry", [
        ("np_call", "'foo bar'(X)"),
        ("np_slash", "'class'/1"),
    ])
    def test_a_non_plain_entry_is_refused_and_says_so(
            self, tmp_path, name, entry):
        """An entry mints the same class a head does, so it owes the same
        limit — and it must SAY so rather than be quietly ignored."""
        with pytest.raises(SyntaxError) as exc_info:
            _load(tmp_path, name, f"-module(m, [{entry}])\n")
        message = str(exc_info.value)
        assert "is not a plain name" in message
        assert "cannot be declared" in message
