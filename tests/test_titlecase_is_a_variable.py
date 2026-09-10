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
