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
        suffix=".clausal", mode="w", delete=False
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
    mod = _load_inline_clausal("_truth_alias_true_test", "Flag(true),\n")
    assert mod is not None


def test_bare_null_names_the_Undefined_literal():
    with pytest.raises(NameError) as exc_info:
        _load_inline_clausal("_truth_literal_null_test", "Tri(null),\n")
    assert "did you mean `Undefined`?" in str(exc_info.value)


def test_bare_unknown_still_names_the_Undefined_literal():
    """The pre-rename name is a diagnostic, not an alias — it must land the
    author on ``Undefined`` rather than silently working."""
    with pytest.raises(NameError) as exc_info:
        _load_inline_clausal("_truth_literal_unknown_test", "Tri(unknown),\n")
    assert "did you mean `Undefined`?" in str(exc_info.value)


def test_mixed_undeclared_keeps_both_hint_and_remedies():
    """When only some undeclared names are truth-value spellings, the author
    still needs the five remedies to fix the others."""
    with pytest.raises(NameError) as exc_info:
        _load_inline_clausal(
            "_truth_literal_mixed_test",
            "Flag(null),\nColor(truthlit_mixed_beta),\n",
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
    assert '- obtained via global_atom("atom", Atom)' in msg


def test_ordinary_undeclared_atom_message_is_unchanged():
    """The regression guard: no hint may leak into a diagnostic whose names
    are all ordinary atoms."""
    with pytest.raises(NameError) as exc_info:
        _load_inline_clausal(
            "_truth_literal_plain_test", "Color(truthlit_plain_red),\n"
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
        "_truth_alias_dictkey_test", "Row({true: 1}),\n"
    )
    assert mod is not None


def test_dict_key_null_names_the_Undefined_literal():
    """The dict-key raise site keeps its own steer for the names that are still
    mistakes."""
    with pytest.raises(NameError) as exc_info:
        _load_inline_clausal(
            "_truth_literal_dictkey_null_test", "Row({null: 1}),\n"
        )
    assert "did you mean `Undefined`?" in str(exc_info.value)
