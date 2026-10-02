"""``true``/``false``/``undefined`` are aliases, not separate values.

Clausal borrows Python's parser, so its canonical truth-value spellings are
``True``/``False`` (parsed as constants) and ``Undefined`` (an injected runtime
binding).  ISO Prolog writes ``true``/``false`` and XSB/SWI write ``undefined``,
and an author arriving from either wrote the lowercase form and met an
undeclared-atom error.  The aliases are folded in
``clausal.templating.term_rewriting.EmbedTransformer`` at the single point where
a bare ``Name`` is classified, so nothing downstream sees a second spelling.

That is the property these tests pin: not merely that the lowercase spellings
*work*, but that they are **indistinguishable** from the canonical ones — same
object, same unification, same goal behaviour, same dict key, same Prolog
output.  A regression that made ``true`` a distinct atom would leave most
"does it load" assertions passing, so every test here crosses the spellings.
"""

from __future__ import annotations

import os
import tempfile

import pytest

import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.terms import Undefined
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.testing import collect_tests, run_test
from tests._suffix import SEAM


def _load(name: str, source: str):
    with tempfile.NamedTemporaryFile(
        suffix=SEAM, mode="w", delete=False
    ) as f:
        f.write(source)
        f.flush()
        path = f.name
    try:
        return _load_module(name, path)
    finally:
        os.unlink(path)


def _only_arg(mod, functor: str):
    """The single argument of the one ``functor/1`` fact in *mod*.

    Read by solving rather than by reaching into the clause store: the stored
    head is not necessarily the runtime term (declarations and lazy stubs both
    live there), and it is the *solved* binding whose identity matters.
    """
    lm = mod.__clausal_module__
    X = Var()
    seen = [deref(X) for _ in call(functor, X, module=lm)]
    assert len(seen) == 1, f"expected one {functor}/1 answer, got {seen}"
    return seen[0]


def _run_all(mod) -> list[tuple[str, bool]]:
    return [(t, run_test(mod, t)) for t in collect_tests(mod)]


# ── Identity: the alias resolves to the very same object ───────────────────


def test_undefined_alias_is_the_singleton():
    """Not "a value that compares equal" — the same object.  Unification of the
    third truth value is by identity, so a second instance would silently fail
    to unify with the one the engine and stdlib use."""
    mod = _load(
        "_alias_identity_undefined",
        "-private([t(X)])\nt(undefined),\n",
    )
    assert _only_arg(mod, "t") is Undefined


@pytest.mark.parametrize("spelling,value", [("true", True), ("false", False)])
def test_boolean_alias_is_the_python_bool(spelling, value):
    """``true`` must be the ``True`` object, not an atom that prints like it."""
    mod = _load(
        f"_alias_identity_{spelling}",
        f"-private([t(X)])\nt({spelling}),\n",
    )
    arg = _only_arg(mod, "t")
    assert arg is value
    assert isinstance(arg, bool)


# ── Cross-spelling unification ─────────────────────────────────────────────


def test_spellings_unify_across_the_divide():
    """A fact asserted in one spelling must be found by a query in the other,
    in both directions and for all three values."""
    mod = _load(
        "_alias_cross_unify",
        "-double_quotes(atom)\n-private([f(X), g(X)])\n"
        "f(true),\n"
        "f(false),\n"
        "f(undefined),\n"
        "g(True),\n"
        "g(False),\n"
        "g(Undefined),\n"
        'test("lower fact, upper query") <- (f(True), f(False), f(Undefined)),\n'
        'test("upper fact, lower query") <- (g(true), g(false), g(undefined)),\n',
    )
    results = _run_all(mod)
    assert results and all(ok for _, ok in results), results


# ── Goal position: ISO true/0 and fail/0 ───────────────────────────────────


def test_true_and_false_in_goal_position():
    """``true`` is the conjunction unit and ``false`` fails, exactly as ISO
    ``true/0`` and ``fail/0`` — this falls out of aliasing to the literals,
    which the goal lowering already handles."""
    mod = _load(
        "_alias_goal_position",
        "-double_quotes(atom)\n-private([p(X)])\n"
        "p(1),\n"
        'test("true is the unit") <- (true, p(1), true),\n'
        'test("false fails") <- (not (false)),\n'
        'test("false truncates a conjunction") <- (not ((p(1), false))),\n',
    )
    results = _run_all(mod)
    assert results and all(ok for _, ok in results), results


def test_undefined_in_goal_position_is_rejected():
    """Deliberate divergence from XSB/SWI, which have a callable ``undefined/0``
    denoting a third goal outcome.  Clausal has two goal outcomes, so the
    lowercase alias must be refused exactly as ``Undefined`` is — and the
    message must say so, because an author from XSB wrote it on purpose."""
    from clausal.logic.compiler.terms_to_goalop import BareGoalUndefinedError

    with pytest.raises(BareGoalUndefinedError) as exc_info:
        _load(
            "_alias_goal_undefined",
            "-private([p(X)])\np(1),\nq(X) <- (undefined, p(X)),\n",
        )
    msg = str(exc_info.value)
    assert "not a callable goal" in msg
    assert "XSB" in msg


# ── Dict keys ──────────────────────────────────────────────────────────────


def test_alias_dict_keys_match_canonical_keys():
    """Key position is a separate code path from value position (bare atom keys
    are interned rather than emitted as name references), so it needs its own
    guard or ``{true: 1}`` and ``{True: 1}`` would build non-unifying dicts."""
    mod = _load(
        "_alias_dict_keys",
        "-double_quotes(atom)\n-private([d(X)])\n"
        "d({true: 1, false: 2, undefined: 3}),\n"
        'test("canonical keys unify") <- d({True: 1, False: 2, Undefined: 3}),\n'
        'test("read back through aliases") <- '
        "(d(D), D[true] == 1, D[false] == 2, D[undefined] == 3),\n",
    )
    results = _run_all(mod)
    assert results and all(ok for _, ok in results), results


# ── The reserved-name cost ─────────────────────────────────────────────────


def test_alias_names_are_no_longer_usable_as_atoms():
    """The documented price of the aliases: ``true`` cannot also be an ordinary
    atom.  Declaring it does not fail, but it does not create an atom either —
    the name resolves to the literal.  Pinned so the cost stays visible."""
    mod = _load(
        "_alias_reserved_name",
        "-private([t(X)])\nt(true),\n",
    )
    assert _only_arg(mod, "t") is True


def test_unknown_is_not_an_alias():
    """``unknown`` was this value's name before the rename.  Binding it as a
    second alias would restore the two-names-for-one-value ambiguity the rename
    removed, so it stays a diagnostic."""
    with pytest.raises(NameError) as exc_info:
        _load("_alias_unknown_rejected", "-private([t(X)])\nt(unknown),\n")
    assert "did you mean `Undefined`?" in str(exc_info.value)


# ── Reserved: the truth values are builtins, not definable names ───────────


@pytest.mark.parametrize(
    "spelling", ["True", "False", "Undefined", "true", "false", "undefined"]
)
@pytest.mark.parametrize("directive", ["-private", "-module"])
def test_truth_values_cannot_be_declared(spelling, directive):
    """All six spellings are refused in a declaration list, in both the bare
    and the arity form.

    Before the guard this was the worst of the definition sites: a bool-valued
    entry matched neither parser branch and was dropped silently, so
    ``-private([True(X)])`` declared nothing and said nothing.
    """
    decl = (
        f"-private([{spelling}(X)])"
        if directive == "-private"
        else f"-module(_reserved_mod, [{spelling}(X)])"
    )
    with pytest.raises(SyntaxError) as exc_info:
        _load(f"_reserved_{directive[1:]}_{spelling}", decl + "\n")
    msg = str(exc_info.value)
    assert f"cannot declare `{spelling}`" in msg
    assert "builtins, not predicates or atoms" in msg


@pytest.mark.parametrize("head", ["true <- (1 is 1)", "false <- (1 is 1)",
                                  "undefined(1),"])
def test_alias_cannot_head_a_clause(head):
    """A clause head is the other way a name gets defined.  ``true`` and
    ``false`` are reserved at arity 0 (the truth values); ``undefined`` at
    every arity (D40, 2026-09-30, lifted true/N and false/N for N >= 1)."""
    spelling = head.split("(")[0].split(" ")[0]
    with pytest.raises(NameError) as exc_info:
        _load(f"_reserved_head_{spelling}", f"-private([p(X)])\n{head}\n")
    msg = str(exc_info.value)
    assert "reserved truth value name" in msg
    assert f"`{spelling}`" in msg


@pytest.mark.parametrize("spelling", ["true", "false"])
def test_true_n_and_false_n_can_head_a_clause(spelling):
    """D40 (operator ruling 2026-09-30): true/N and false/N (N >= 1) are
    ordinary procedures, as in ISO and Scryer, and a body call reaches
    them."""
    mod = _load(f"_d40_head_{spelling}",
                f"{spelling}(X) <- (X is 1)\nq(Y) <- {spelling}(Y)\n")
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref
    y = Var()
    assert [deref(y) for _ in call("q", y, module=mod)] == [1]


@pytest.mark.parametrize("spec", ["true/0", "false/0", "undefined/1"])
def test_alias_cannot_be_a_directive_target(spec):
    with pytest.raises(NameError) as exc_info:
        _load(f"_reserved_dyn_{spec.replace('/', '_')}", f"-dynamic({spec})\n")
    assert "reserved truth value name" in str(exc_info.value)


def test_reserved_diagnostic_lists_every_offender_at_once():
    """An author fixing a file with several must not discover them one re-run
    at a time."""
    with pytest.raises(NameError) as exc_info:
        _load(
            "_reserved_many",
            "-private([p(X)])\ntrue <- (1 is 1)\nfalse <- (1 is 1)\n"
            "undefined(3),\n",
        )
    msg = str(exc_info.value)
    assert "`true`" in msg and "`false`" in msg and "`undefined`" in msg
