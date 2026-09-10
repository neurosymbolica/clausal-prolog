"""TitleCase is a logic VARIABLE in term position, still an error as a functor.

The ISO reading: a capital-initial identifier standing where a value goes is a
logic variable.  ``p(Foo) <- (bar(Foo))`` loads and ``Foo`` binds, exactly as
``P``/``FOO``/``_foo`` always did.

The asymmetry, deliberately kept: a capital-initial identifier in FUNCTOR
position -- a clause head's functor, or a call in a body -- is still a
load-time ``SyntaxError`` carrying the ``++Name`` remedy.  A variable in
functor position is not ``call/N`` in this language, it is the unit-annotation
sugar, so letting the functor case through would turn a bare Python class in a
clause body from a clear load error into a units expression that dies much
later with a message about SI prefixes.  See the comment on
``_lint_titlecase``'s walk.
"""
import textwrap
import warnings

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.templating.term_rewriting import ClausalSingletonWarning


def _load(tmp_path, name, text):
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(text).lstrip())
    return _load_module(f"ttiav_{name}", str(path))


def _module(mod):
    return mod.__dict__["$module"]


def _answers(mod, functor, arity=1):
    """Every solution's argument values, snapshotted INSIDE the iteration.

    A binding is undone when the solver backtracks past it, so reading the
    ``Var`` after the generator is exhausted always shows it unbound -- the
    value has to be copied out while the solution is current.
    """
    args = [Var() for _ in range(arity)]
    out = []
    for _ in call(functor, *args, module=_module(mod)):
        out.append(tuple(deref(a) for a in args))
    return out


# ── TERM position: a capital-initial name is a logic variable ───────────────

def test_titlecase_in_term_position_loads_and_binds(tmp_path):
    """The point of the change: not merely "it loads" -- ``Foo`` must be a
    VARIABLE, so the solution carries the fact's argument back out."""
    mod = _load(tmp_path, "bind", """
        -module(ttiav_bind, [p(X)])
        bar(1),
        p(Foo) <- (bar(Foo))
    """)
    assert _answers(mod, "p") == [(1,)]


def test_titlecase_and_allcaps_are_the_same_variable_when_spelled_alike(tmp_path):
    """Two occurrences of one TitleCase name in a clause are one variable --
    the join, which is what distinguishes a variable from a fresh ``_``."""
    mod = _load(tmp_path, "join", """
        -module(ttiav_join, [q(X)])
        edge(1, 1),
        edge(1, 2),
        q(N) <- (edge(Same, Same), N == Same)
    """)
    assert _answers(mod, "q") == [(1,)]


def test_titlecase_singleton_gets_the_singleton_warning(tmp_path):
    """A TitleCase name is a variable like any other, so the singleton lint
    reaches it -- the lint is keyed on the variable classifier, so this is the
    check that the classifier really did widen (rather than the name merely
    slipping past the TitleCase lint)."""
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        _load(tmp_path, "single", """
            -module(ttiav_single, [p(X, Y)])
            p(X, Once) <- (X == 1)
        """)
    msgs = [str(w.message) for w in rec
            if issubclass(w.category, ClausalSingletonWarning)]
    assert any("Once" in m for m in msgs), msgs


# ── FUNCTOR position: still a load-time error ──────────────────────────────

def test_titlecase_clause_head_functor_is_still_a_load_error(tmp_path):
    with pytest.raises(SyntaxError) as exc_info:
        _load(tmp_path, "head", """
            bar(1),
            Foo(X) <- (bar(X))
        """)
    message = str(exc_info.value)
    assert "Foo" in message
    assert "TitleCase" in message


def test_python_class_called_in_a_body_is_still_a_load_error(tmp_path):
    """The shape the functor rule exists for.  Were ``Fraction`` read as a
    variable here it would become the unit-annotation sugar and fail at
    RUNTIME complaining about SI prefixes; it must stay a load error that
    names the ``++`` escape."""
    with pytest.raises(SyntaxError) as exc_info:
        _load(tmp_path, "pyclass", """
            bar(1),
            p(X) <- (bar(Fraction(1, 3)))
        """)
    message = str(exc_info.value)
    assert "Fraction" in message
    assert "++Fraction" in message


def test_the_functor_error_survives_a_titlecase_variable_in_the_same_clause(tmp_path):
    """Narrowing the lint to functor position must not narrow it to "the first
    name in the clause": the head argument ``Arg`` is a variable now, and the
    body call ``Helper`` must still be refused."""
    with pytest.raises(SyntaxError) as exc_info:
        _load(tmp_path, "mixed", """
            p(Arg) <- (Helper(Arg))
        """)
    assert "Helper" in str(exc_info.value)


# ── The shapes that must not have moved ────────────────────────────────────

def test_all_caps_term_position_unchanged(tmp_path):
    mod = _load(tmp_path, "allcaps", """
        -module(ttiav_allcaps, [p(X)])
        bar(1),
        p(FOO) <- (bar(FOO))
    """)
    assert _answers(mod, "p") == [(1,)]


def test_leading_underscore_term_position_unchanged(tmp_path):
    mod = _load(tmp_path, "under", """
        -module(ttiav_under, [p(X)])
        bar(1),
        p(_foo) <- (bar(_foo))
    """)
    assert _answers(mod, "p") == [(1,)]


def test_lowercase_functor_and_atom_unchanged(tmp_path):
    """The ordinary case: a lowercase name is still a functor, not a
    variable."""
    mod = _load(tmp_path, "lower", """
        -module(ttiav_lower, [p(X)])
        bar(1),
        p(Y) <- (bar(Y))
    """)
    assert _answers(mod, "p") == [(1,)]


# ── Python-by-definition contexts keep the Python reading ──────────────────

def test_fstring_interpolation_of_a_python_class_still_evaluates(tmp_path):
    """An f-string body is Python, exactly like a ``++`` operand.

    Both compile to a lambda whose PARAMETERS are the clause variables the
    body mentions, so classifying a capital-initial Python name there as a
    variable binds a fresh ``Var`` over the module global and the
    interpolation dies at query time with ``'AttVar' object is not
    callable``.  This is WORKING CODE, not a diagnostic: it evaluates on
    main, and `_lint_titlecase` returns early on ``JoinedStr``, so there is
    no load-time complaint to fall back on either."""
    mod = _load(tmp_path, "fstr", """
        from fractions import Fraction
        -module(ttiav_fstr, [p(S)])
        p(S) <- (S is f"{Fraction(1, 3)}")
    """)
    assert _answers(mod, "p") == [("1/3",)]


def test_fstring_still_captures_an_ordinary_clause_variable(tmp_path):
    """The other half: excluding TitleCase from the capture must not stop an
    ordinary variable being captured."""
    mod = _load(tmp_path, "fstrvar", """
        -module(ttiav_fstrvar, [p(N, S)])
        p(N, S) <- (S is f"n={N}")
    """)
    out = []
    for _ in call("p", 7, (v := Var()), module=_module(mod)):
        out.append(deref(v))
    assert out == ["n=7"]


# ── Zero-arity heads are functor positions too ────────────────────────────

def test_zero_arity_rule_head_is_still_a_load_error(tmp_path):
    """``Foo <- (...)`` defines a predicate named ``Foo``: a functor
    position, and a bare ``Name`` rather than a ``Call``, so the walk needs
    telling.  Without it the clause loaded and registered the predicate with
    no lint at all -- the functor invariant silently escaped."""
    with pytest.raises(SyntaxError) as exc_info:
        _load(tmp_path, "zerorule", """
            bar(1),
            Foo <- (bar(X))
        """)
    assert "Foo" in str(exc_info.value)
    assert "TitleCase" in str(exc_info.value)


def test_zero_arity_dcg_head_is_still_a_load_error(tmp_path):
    with pytest.raises(SyntaxError) as exc_info:
        _load(tmp_path, "zerodcg", """
            bar(1),
            Foo >> (bar(X))
        """)
    assert "Foo" in str(exc_info.value)
    assert "TitleCase" in str(exc_info.value)


def test_lowercase_zero_arity_rule_head_still_loads(tmp_path):
    """The control: narrowing must not refuse the ordinary spelling."""
    mod = _load(tmp_path, "zerook", """
        -module(ttiav_zerook, [foo()])
        bar(1),
        foo <- (bar(1))
    """)
    assert len(list(call("foo", module=_module(mod)))) == 1


# ── A name the file's HOSTED PYTHON binds is still a term-position variable ─

def test_hosted_python_binding_does_not_carve_a_name_out_of_the_rule(
        tmp_path):
    """The line this change draws, pinned so it cannot move unnoticed.

    A CLAUSAL binding -- an ``-import_from`` list -- carves its names out of
    the variable rule, because that directive binds into the Clausal
    namespace and the units deprecation window depends on it.  A HOSTED
    PYTHON binding (``from fractions import Fraction`` at the top of the
    file) does not: Clausal code reaches Python through ``++``, so
    ``P is Fraction`` reads ``Fraction`` as an ordinary logic variable.

    It used to be a load error naming ``++Fraction``.  It is now a fresh
    unbound variable, which is the same shape the operator ruled acceptable
    for ``catch(G, ValueError, R)``: a user error with the correct spelling
    (``++Fraction``) one character away.  Pinned, not special-cased."""
    mod = _load(tmp_path, "hosted", """
        from fractions import Fraction
        -module(ttiav_hosted, [q(P)])
        q(P) <- (P is Fraction)
    """)
    [(answer,)] = _answers(mod, "q")
    assert isinstance(answer, Var) or "Var" in type(answer).__name__, answer
    # And the ``++`` spelling -- the one the lint names -- does work.
    mod2 = _load(tmp_path, "hosted_ok", """
        from fractions import Fraction
        -module(ttiav_hosted_ok, [q(P)])
        q(P) <- (P is ++Fraction(1, 3))
    """)
    from fractions import Fraction as _F
    assert _answers(mod2, "q") == [(_F(1, 3),)]
