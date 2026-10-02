"""Tests for the truth-literal hint on undeclared-atom diagnostics.

A bare undeclared atom raises the same generic five-remedy ``NameError``
whatever its name, and for the JSON/Python vocabulary of absent-or-unknown —
``null``, ``none``, ``nil``, ``maybe`` — not one of the five remedies is the
right answer.  The right answer is ``Undefined``.  See
``todo/lowercase-true-false-null-should-name-the-True-False-Unknown-literals.md``:
in a measured authoring study, ``true``/``false``/``null`` were roughly a
quarter of the undeclared-atom mentions — a model writing the Python/JSON
spelling of a value the language already has.

``true``, ``false`` and ``undefined`` are no longer part of that set: they are
parse-time aliases for ``True``, ``False`` and ``Undefined`` and load without a
diagnostic at all, which is the stronger fix for the two largest buckets.  The
tests at the bottom of this file guard that, so a regression in the aliases
surfaces here as well as in ``test_truth_value_aliases.py``.

``unknown`` stays in the hint set on purpose: it was ``Undefined``'s name
before the rename to the XSB/SWI spelling, so it is a name authors and older
documents still reach for, and binding it as a second alias would restore the
ambiguity the rename removed.
"""

from __future__ import annotations

import os
import tempfile

import pytest

import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.atom_diagnostics import truth_literal_hint_lines
from clausal.import_hook import _load_module
from tests._suffix import SEAM


# ── The pure helper ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name,literal",
    [
        ("null", "Undefined"),
        ("none", "Undefined"),
        ("nil", "Undefined"),
        ("unknown", "Undefined"),
        ("maybe", "Undefined"),
    ],
)
def test_each_spelling_names_its_literal(name, literal):
    """Every name in the match set is steered to exactly one literal."""
    lines = truth_literal_hint_lines([name])
    assert lines, f"{name!r} produced no hint"
    joined = "\n".join(lines)
    assert f"`{name}`" in joined
    assert f"did you mean `{literal}`?" in joined


@pytest.mark.parametrize("name", ["true", "false", "undefined"])
def test_alias_spellings_are_not_hinted(name):
    """The aliases resolve, so they must never reach the hint set — a hint for
    a spelling that works would be actively misleading."""
    assert truth_literal_hint_lines([name]) == []


def test_unrelated_name_yields_no_hint():
    """The helper must stay silent for ordinary atoms, so every non-boolean
    diagnostic keeps today's wording byte-for-byte."""
    assert truth_literal_hint_lines(["filing_status"]) == []
    assert truth_literal_hint_lines([]) == []


def test_match_is_case_insensitive():
    """``NULL`` is the same mistake as ``null``.  The working spellings are
    already bound and never reach a raise site, so case-insensitivity cannot
    shadow a name that works."""
    assert "did you mean `Undefined`?" in "\n".join(
        truth_literal_hint_lines(["NULL"])
    )


def test_hint_names_all_three_truth_values():
    """The hint spells out the whole vocabulary, not just the one replacement:
    ``Undefined`` is titlecase, the least guessable part of the language."""
    joined = "\n".join(truth_literal_hint_lines(["null"]))
    assert "`True`" in joined
    assert "`False`" in joined
    assert "`Undefined`" in joined


def test_hint_mentions_the_lowercase_aliases():
    """An author who reached for ``null`` came from JSON or Prolog; naming the
    lowercase aliases tells them the spelling they know is available."""
    joined = "\n".join(truth_literal_hint_lines(["null"]))
    assert "`true`/`false`" in joined
    assert "`undefined`" in joined


def test_explanation_appears_once_but_every_name_gets_an_arrow():
    """Two synonyms of the same literal must not repeat the whole three-value
    paragraph.  They must still get an arrow each: collapsing on the literal
    would leave `nil` unmentioned, so the author would fix `null`, re-run, and
    hit `nil` on the next pass."""
    joined = "\n".join(truth_literal_hint_lines(["null", "nil"]))
    assert joined.count("well-founded semantics") == 1
    assert joined.count("the boolean literals are") == 1
    assert joined.count("did you mean") == 2
    assert "`null`" in joined
    assert "`nil`" in joined


def test_single_name_arrow_stays_unqualified():
    """The overwhelmingly common case is one bad name.  Its arrow must stay
    the bare `-> did you mean \\`Undefined\\`?` — no per-name qualifier noise."""
    lines = truth_literal_hint_lines(["null"])
    assert lines[-1].strip() == "-> did you mean `Undefined`?"


def test_only_matching_names_are_hinted():
    """Given a mix, the helper hints the truth-value spellings and says nothing
    about the rest — the caller still appends its own remedy list."""
    joined = "\n".join(truth_literal_hint_lines(["foo_bar", "null"]))
    assert "`null`" in joined
    assert "foo_bar" not in joined


# ── Call site 1: the bare-atom-reference diagnostic ────────────────────────


def _load_inline_clausal(name: str, source: str):
    """Write `source` to a temp .clausal file and try to load it.

    Mirrors the helper in ``test_global_atoms_default.py``: must-fail-to-load
    fixtures cannot live under ``tests/fixtures/`` or pytest's ``.clausal``
    collector surfaces them as <load> failures.
    """
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


def test_bare_lowercase_true_loads():
    """The reproduction from the todo, inverted.  ``true`` used to list five
    remedies none of which was the right answer; it is now an alias and the
    file simply loads."""
    mod = _load_inline_clausal("_truth_alias_true_test", "flag(true),\n")
    assert mod is not None


def test_bare_null_names_the_Undefined_literal():
    with pytest.raises(NameError) as exc_info:
        _load_inline_clausal("_truth_literal_null_test", "tri(null),\n")
    assert "did you mean `Undefined`?" in str(exc_info.value)


def test_bare_unknown_still_names_the_Undefined_literal():
    """The pre-rename name is a diagnostic, not an alias — it must land the
    author on ``Undefined`` rather than silently working."""
    with pytest.raises(NameError) as exc_info:
        _load_inline_clausal("_truth_literal_unknown_test", "tri(unknown),\n")
    assert "did you mean `Undefined`?" in str(exc_info.value)


def test_mixed_undeclared_keeps_both_hint_and_remedies():
    """When only some undeclared names are truth-value spellings, the author
    still needs the five remedies to fix the others."""
    with pytest.raises(NameError) as exc_info:
        _load_inline_clausal(
            "_truth_literal_mixed_test",
            "flag(null),\ncolor(truthlit_mixed_beta),\n",
        )
    msg = str(exc_info.value)
    assert "did you mean `Undefined`?" in msg
    assert "truthlit_mixed_beta" in msg
    assert "bare atom references must be one of:" in msg
    # All five remedies, not a sample: the author still has to fix the
    # non-boolean name, and a regression that dropped one should fail here.
    assert "- listed in -module(" in msg
    assert "- listed in -private([atom, ...])" in msg
    assert "- imported via -import_from(from_module, [atom])" in msg
    assert "- qualified (e.g. other_module.atom)" in msg
    assert "- obtained via global_atom('atom', Atom)" in msg


def test_ordinary_undeclared_atom_message_is_unchanged():
    """The regression guard: no hint may leak into a diagnostic whose names
    are all ordinary atoms."""
    with pytest.raises(NameError) as exc_info:
        _load_inline_clausal(
            "_truth_literal_plain_test", "color(truthlit_plain_red),\n"
        )
    msg = str(exc_info.value)
    assert "did you mean" not in msg
    assert "is not a literal in Clausal" not in msg
    assert "bare atom references must be one of:" in msg


# ── Call site 2: the dict-key path ─────────────────────────────────────────


def test_dict_key_true_loads():
    """``{true: 1}`` used to raise from its own site with its own message.  The
    alias is resolved in key position too, so it now loads."""
    mod = _load_inline_clausal(
        "_truth_alias_dictkey_test", "row({true: 1}),\n"
    )
    assert mod is not None


def test_dict_key_null_names_the_Undefined_literal():
    """The dict-key raise site keeps its own steer for the names that are still
    mistakes."""
    with pytest.raises(NameError) as exc_info:
        _load_inline_clausal(
            "_truth_literal_dictkey_null_test", "row({null: 1}),\n"
        )
    assert "did you mean `Undefined`?" in str(exc_info.value)


# ── An atom applied as a functor ───────────────────────────────────────────


def test_an_atom_applied_as_a_functor_is_refused_at_load():
    """P3-3 Task 4 (todo/done/atom-declared-name-applied-as-functor-is-silent):
    post-P3-1 a ``-private`` atom is a ``str``, so ``bound2(G)`` in a clause
    lowered to ``Call(func='bound2', ...)`` -- a shape every downstream
    ``isinstance(func, LoadName)`` branch skips.  In a head the clause was
    present, indexed and never matched (a "total" predicate silently losing a
    case); in a body the compiler's own AST node escaped into user data.
    Both are now a load-time error that names the remedy."""
    with pytest.raises(SyntaxError) as exc_info:
        _load_inline_clausal(
            "_t4_atom_as_functor_head",
            "-module(t4_atom_as_functor_head, [C(X)])\n"
            "-private([bound2])\n"
            "C(bound2(G)) <- (G is 2)\n",
        )
    message = str(exc_info.value)
    assert "bound2" in message and "atom" in message


def test_an_atom_applied_as_a_functor_in_a_body_is_refused_too():
    with pytest.raises(SyntaxError) as exc_info:
        _load_inline_clausal(
            "_t4_atom_as_functor_body",
            "-module(t4_atom_as_functor_body, [C(Y)])\n"
            "-private([bound2])\n"
            "C(Y) <- (Y is bound2(5))\n",
        )
    assert "bound2" in str(exc_info.value)


def test_a_name_declared_as_BOTH_atom_and_functor_applies_as_the_functor():
    """Fix round 1, I-1.  ``-module(c2, [dual, dual(G), c(X)])`` declares the
    same spelling as a 0-arity atom AND as a 1-ary functor -- a legal, live
    configuration: ``dual/1`` answers.  The applied form must lower as the
    FUNCTOR, so the refusal above (which reads only the atom set) must not
    fire, and the remedy it prescribes must not be the declaration the module
    already carries.  The previous bare-``str`` lowering was the bug here, not
    the dual declaration."""
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref

    mod = _load_inline_clausal(
        "_t4f1_dual_declared",
        "-module(t4f1_dual_declared, [dual, dual(G), c(X)])\n"
        "dual(1),\n"
        "c(X) <- dual(X),\n",
    )
    x = Var()
    assert [deref(x) for _ in call(mod.c, x)] == [1]


def test_a_dual_declared_name_nested_in_a_head_arg_builds_the_functor_term():
    """The other half of I-1: nested in a head argument, the dual-declared
    name must build the functor's own term, not leak a ``Call`` AST node the
    way the pre-fix silent lowering did (``c(dual(1))`` answered
    ``Call(func='dual', args=[1], kwargs=[])``)."""
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref
    from clausal.pythonic_ast.nodes import Call as CallNode
    from clausal.logic.builtins._helpers import functor_arity

    mod = _load_inline_clausal(
        "_t4f1_dual_nested",
        "-module(t4f1_dual_nested, [dual, dual(G), c(X)])\n"
        "dual(1),\n"
        "c(dual(1)),\n",
    )
    x = Var()
    answers = [deref(x) for _ in call(mod.c, x)]
    assert len(answers) == 1
    assert not isinstance(answers[0], CallNode), (
        f"compiler AST node leaked into user data: {answers[0]!r}")
    # The functor's own term, whichever representation the declaration gave
    # it -- a dual declaration keeps ``dual`` bound to its minted class, so
    # this is a class instance rather than a cell.  What matters is that it
    # is the ``dual/1`` term and not a compiler node.
    assert functor_arity(answers[0]) == ("dual", 1)


def test_an_atom_only_name_applied_as_a_functor_still_raises():
    """The refusal keeps firing for a name declared as an atom and NOT as a
    functor -- the case the todo filed."""
    with pytest.raises(SyntaxError) as exc_info:
        _load_inline_clausal(
            "_t4f1_atom_only",
            "-module(t4f1_atom_only, [C(X)])\n"
            "-private([lonely])\n"
            "C(lonely(G)) <- (G is 2)\n",
        )
    assert "lonely" in str(exc_info.value)


def _fixture_path(filename: str) -> str:
    return os.path.join(os.path.dirname(__file__), "fixtures", filename)


def test_an_imported_functor_shadowed_by_a_local_atom_decl_applies_as_the_functor():
    """Fix round 1, the ``-import_from`` half of I-1, re-pinned end-to-end in
    fix round 2 (O2): the round-1 version asserted on unparsed AST against a
    module that does not exist, so it could not see what the owner declares.
    Real owner + importer fixtures now: ``wrapf`` is a FUNCTOR in its owner
    and an ATOM locally, so the applied form must lower as the owner's
    functor and answer."""
    from clausal.import_hook import _load_module
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref
    from clausal.logic.builtins._helpers import functor_arity

    _load_module("tests.fixtures.t4f2_owner_functor",
                 _fixture_path("t4f2_owner_functor.seam"))
    mod = _load_module("tests.fixtures.t4f2_import_functor_shadow",
                       _fixture_path("t4f2_import_functor_shadow.seam"))
    x = Var()
    answers = [deref(x) for _ in call(mod.c, x)]
    assert len(answers) == 1
    assert functor_arity(answers[0]) == ("wrapf", 1)


def test_an_imported_ATOM_shadowed_by_a_local_atom_decl_is_refused():
    """Fix round 2, O2.  The round-1 import bypass fired on ``_import_remap``
    membership alone, so a name that is an ATOM in its owner too got the
    dotted lowering, loaded, and died at the first call with an unlocated
    ``TypeError: 'str' object is not callable``.  The deciding fact is whether
    the imported name carries a FUNCTOR SIGNATURE in the importer's own
    registry (which ``-import_from`` copies across only for functors); no
    signature means no functor anywhere, so the located refusal stands."""
    from clausal.import_hook import _load_module

    _load_module("tests.fixtures.t4f2_owner_atom",
                 _fixture_path("t4f2_owner_atom.seam"))
    with pytest.raises(SyntaxError) as exc_info:
        _load_module("tests.fixtures.t4f2_import_atom_shadow",
                     _fixture_path("t4f2_import_atom_shadow.seam"))
    message = str(exc_info.value)
    assert "verdict" in message
    assert "t4f2_import_atom_shadow.seam:9" in message, message
    assert "t4f2_owner_atom" in message, message


def test_a_functor_established_AFTER_its_first_use_is_not_refused():
    """Fix round 2, O1.  ``_seen_functors`` is the walk-time set, so a functor
    established by a clause LATER in the file was invisible at the moment the
    refusal fired -- the same program with the two statements swapped loaded
    fine.  The decision is now made after the module walk is complete, so it
    is order-independent."""
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref

    mod = _load_inline_clausal(
        "_t4f2_order_use_first",
        "-module(t4f2_order_use_first, [dual, c(X)])\n"
        "c(X) <- dual(X),\n"
        "dual(1),\n",
    )
    x = Var()
    assert [deref(x) for _ in call(mod.c, x)] == [1]


def test_the_other_declaration_order_still_loads():
    """The mirror of the above -- the functor established BEFORE its use --
    was already accepted; pinned so the fix cannot regress it."""
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref

    mod = _load_inline_clausal(
        "_t4f2_order_decl_first",
        "-module(t4f2_order_decl_first, [dual, c(X)])\n"
        "dual(1),\n"
        "c(X) <- dual(X),\n",
    )
    x = Var()
    assert [deref(x) for _ in call(mod.c, x)] == [1]


def test_an_atom_only_name_is_still_refused_wherever_it_appears():
    """The refusal must survive the deferral: a name declared as an atom and
    NOT as a functor anywhere in the file is still refused, with its own
    file:line."""
    with pytest.raises(SyntaxError) as exc_info:
        _load_inline_clausal(
            "_t4f2_atom_only_deferred",
            "-module(t4f2_atom_only_deferred, [solo, c(X)])\n"
            "c(X) <- solo(X),\n",
        )
    message = str(exc_info.value)
    assert "solo" in message
    assert ":2" in message, message


def test_a_hidden_atom_inside_a_lambda_body_keeps_its_mangled_spelling():
    """Fix round 2, P1.  Round 1 threaded ``hidden_atoms``/``module_name``
    into the arrow-lambda sub-transformer, which had been building its terms
    without them -- so a ``-hide``-en atom written inside a lambda body
    lowered to the PLAIN spelling and did not unify with the same atom
    written at clause level.  Answer-level pin: the lambda-side atom and the
    clause-level one must be the same term."""
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref

    mod = _load_inline_clausal(
        "_t4f2_hide_in_lambda",
        "-module(t4f2_hide_in_lambda, [same(R)])\n"
        "-hide([hsecret])\n"
        "same(R) <- call_goal((V <- ((V == hsecret) and (R == 1))), hsecret)\n",
    )
    r = Var()
    assert [deref(r) for _ in call(mod.same, r)] == [1]


def test_the_deferred_item_never_reaches_reflection_output():
    """Fix round 3, R1.  The deferred candidate list is a compile-time
    worklist, and for a LEGAL file (an imported functor shadowed by a local
    atom declaration) it stays in ``module_items`` for good -- so
    ``reify_source`` rendered it as a ``ModuleDirective`` named
    ``AtomAppliedAsFunctor`` carrying an absolute path and a would-be error
    message.  ``BareAtomRefs`` is skipped for exactly this reason; so is
    this.  The fixture is loaded as well as reified, so the pin cannot pass
    by the item having quietly stopped being emitted."""
    from clausal.reflection import reify_source, ModuleDirective, is_v, vfield
    from clausal.import_hook import _load_module
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref
    from clausal.logic.builtins._helpers import functor_arity

    path = _fixture_path("t4f2_import_functor_shadow.seam")
    with open(path, encoding="utf-8") as fh:
        source = fh.read()
    items = reify_source(source)
    leaked = [d for d in items
              if is_v(d, ModuleDirective)
              and vfield(d, "name") == "AtomAppliedAsFunctor"]
    assert not leaked, leaked

    _load_module("tests.fixtures.t4f2_owner_functor",
                 _fixture_path("t4f2_owner_functor.seam"))
    mod = _load_module("tests.fixtures.t4f2_import_functor_shadow", path)
    x = Var()
    answers = [deref(x) for _ in call(mod.c, x)]
    assert [functor_arity(a) for a in answers] == [("wrapf", 1)]
