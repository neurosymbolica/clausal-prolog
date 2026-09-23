"""A MANGLED predicate handle (``module<US>name``, the ``-hide`` spelling,
``HIDDEN_SEP`` = ``\\x1f``) that fails to resolve -- its owning module was
never loaded, or the module loaded but the predicate is not defined in it --
used to surface three different, all-malformed shapes depending on which of
the three entry points (``solve``'s goal normalisation, ``call/N``,
``_dispatch_at``) reached it first: a raw ``\\x1f`` control character inside
a CATCHABLE term, a culprit that was a stringified Python tuple ``repr``
rather than a Prolog term, and (the loaded-but-missing case) no logic term
at all (``PredicateNotFoundError``/``KeyError``, ``e.term`` absent).  See
``todo/mangled-goal-culprit-terms-are-malformed-2026-09-23.md``.

Ruling (operator, 2026-09-24): BOTH situations raise
``LogicException(error(existence_error(procedure, Name/Arity), Context))``.
One vocabulary (``procedure``, never ``module``); the mangled spelling is
demangled before the term is built and so never appears in anything a
``catch/3`` pattern can match; the module-not-loaded vs.
loaded-but-missing distinction lives only in the context/message, never in
the culprit.

Fixture: ``tests/fixtures/hide_owner.clausal`` declares ``holds/1``,
``label/1``, ``same/2`` -- a real loaded module with no ``nosuchpred``.
"""
from __future__ import annotations

import os

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.atoms import HIDDEN_SEP, mangle
from clausal.logic.exceptions import LogicException
from clausal.logic.predicate import _dispatch_at
from clausal.logic.solve import call, solve


def _fixture_path(filename: str) -> str:
    return os.path.join(os.path.dirname(__file__), "fixtures", filename)


@pytest.fixture(scope="module")
def hide_owner():
    """The real, loaded ``hide_owner`` module -- ``nosuchpred`` is genuinely
    absent from it (it declares only ``holds/1``, ``label/1``, ``same/2``)."""
    return _load_module("hide_owner_dangling_handle_fixture",
                         _fixture_path("hide_owner.clausal"))


def _walk_for_hidden_sep(term) -> bool:
    """True iff HIDDEN_SEP appears in any string leaf reachable from *term*.

    Structural, not a rendered-string substring check (a term that merely
    PRINTS the escape -- e.g. an atom spelled ``"a\\\\x1fb"`` some renderer
    escapes to the two characters backslash-x-1-f -- must not pass this: the
    check has to look at the actual leaf strings, not at ``str(term)``).
    """
    if isinstance(term, str):
        return HIDDEN_SEP in term
    if hasattr(term, "functor") and hasattr(term, "args"):  # Compound
        if isinstance(term.functor, str) and HIDDEN_SEP in term.functor:
            return True
        return any(_walk_for_hidden_sep(a) for a in term.args)
    if isinstance(term, (tuple, list)):
        return any(_walk_for_hidden_sep(e) for e in term)
    if isinstance(term, dict):
        return any(_walk_for_hidden_sep(k) or _walk_for_hidden_sep(v)
                   for k, v in term.items())
    return False


def _assert_clean_procedure_existence_error(exc, expected_name, expected_arity):
    """Shared shape assertions for every (entry point x situation) case."""
    assert isinstance(exc, LogicException), (
        "must be a LogicException -- catchable via catch/3, not a bare "
        "Python KeyError with no .term"
    )
    term = exc.term
    assert term is not None, "the loaded-but-missing case must carry a real term"
    assert not _walk_for_hidden_sep(term), (
        f"the mangled \\x1f spelling must never appear in a catchable term: {term!r}"
    )
    assert term.functor == "error"
    inner = term.args[0]
    assert inner.functor == "existence_error"
    obj_type, culprit = inner.args
    assert obj_type == "procedure", "ruled vocabulary: procedure, never module"
    # The culprit is a proper Prolog indicator Name/Arity, not a Python repr
    # string and not a module-qualified compound (":"/2) -- the module lives
    # in the context/message only.
    assert not isinstance(culprit, str), (
        f"culprit must be a Name/Arity indicator term, not a repr string: {culprit!r}"
    )
    assert culprit.functor == "/", f"expected an unqualified Name/Arity indicator, got {culprit!r}"
    name, arity = culprit.args
    assert name == expected_name
    assert arity == expected_arity


# ── solve's goal normalisation ───────────────────────────────────────────────


def test_solve_not_loaded_module_raises_clean_procedure_existence_error():
    handle = mangle("no_such_mod_zz_errshape", "whatever")
    with pytest.raises(LogicException) as info:
        list(solve((handle, 1)))
    _assert_clean_procedure_existence_error(info.value, "whatever", 1)


def test_solve_loaded_missing_predicate_raises_clean_procedure_existence_error(hide_owner):
    handle = mangle("hide_owner_dangling_handle_fixture", "nosuchpred")
    with pytest.raises(LogicException) as info:
        list(solve((handle, 1)))
    _assert_clean_procedure_existence_error(info.value, "nosuchpred", 1)


# ── call/N ────────────────────────────────────────────────────────────────────


def test_call_not_loaded_module_raises_clean_procedure_existence_error():
    handle = mangle("no_such_mod_zz_errshape", "whatever")
    with pytest.raises(LogicException) as info:
        list(call(handle, 1))
    _assert_clean_procedure_existence_error(info.value, "whatever", 1)


def test_call_loaded_missing_predicate_raises_clean_procedure_existence_error(hide_owner):
    handle = mangle("hide_owner_dangling_handle_fixture", "nosuchpred")
    with pytest.raises(LogicException) as info:
        list(call(handle, 1))
    _assert_clean_procedure_existence_error(info.value, "nosuchpred", 1)


# ── _dispatch_at ──────────────────────────────────────────────────────────────


def test_dispatch_at_not_loaded_module_raises_clean_procedure_existence_error():
    handle = mangle("no_such_mod_zz_errshape", "whatever")
    with pytest.raises(LogicException) as info:
        _dispatch_at(handle, 1)
    _assert_clean_procedure_existence_error(info.value, "whatever", 1)


def test_dispatch_at_loaded_missing_predicate_raises_clean_procedure_existence_error(hide_owner):
    handle = mangle("hide_owner_dangling_handle_fixture", "nosuchpred")
    with pytest.raises(LogicException) as info:
        _dispatch_at(handle, 1)
    _assert_clean_procedure_existence_error(info.value, "nosuchpred", 1)
