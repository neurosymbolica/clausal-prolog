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
    assert _answers(mod, "kind", 1) == [(("Oral",),)]


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


def test_non_identifier_quoted_fact_head_is_still_refused(tmp_path):
    """A Clausal implementation limit, not an ISO rule, and out of scope
    here: a fact head is compiled to a functor class whose name is emitted
    as Python source.  Pinned so it cannot decay into a parse error blamed
    on generated code the author never wrote."""
    with pytest.raises(SyntaxError) as exc_info:
        _load(tmp_path, "spacey", "'foo bar'(1),\n")
    message = str(exc_info.value)
    assert "'foo bar' is not a plain name" in message
    assert "cannot head a fact" in message


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
