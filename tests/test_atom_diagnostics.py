"""Tests for the truth-literal hint on undeclared-atom diagnostics.

A bare undeclared atom raises the same generic five-remedy ``NameError``
whatever its name, and for ``true`` / ``false`` / ``null`` not one of the five
remedies is the right answer — the right answer is ``True`` / ``False`` /
``Unknown``.  See
``todo/lowercase-true-false-null-should-name-the-True-False-Unknown-literals.md``:
in study 11, those three names are 63 of the 241 undeclared-atom mentions (26%),
a quarter of the incidents being a model writing the Python/JSON spelling of a
value the language already has.

The hint names ``Unknown`` even when the misspelling is ``true`` or ``false``,
because titlecase is the part a reader is least likely to guess — every other
atom in the language is lowercase, and titlecase normally reads as a variable.
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
        ("true", "True"),
        ("false", "False"),
        ("null", "Unknown"),
        ("none", "Unknown"),
        ("nil", "Unknown"),
        ("unknown", "Unknown"),
        ("undefined", "Unknown"),
        ("maybe", "Unknown"),
    ],
)
def test_each_spelling_names_its_literal(name, literal):
    """Every name in the match set is steered to exactly one literal."""
    lines = truth_literal_hint_lines([name])
    assert lines, f"{name!r} produced no hint"
    joined = "\n".join(lines)
    assert f"`{name}`" in joined
    assert f"did you mean `{literal}`?" in joined


def test_unrelated_name_yields_no_hint():
    """The helper must stay silent for ordinary atoms, so every non-boolean
    diagnostic keeps today's wording byte-for-byte."""
    assert truth_literal_hint_lines(["filing_status"]) == []
    assert truth_literal_hint_lines([]) == []


def test_match_is_case_insensitive():
    """``TRUE`` is the same mistake as ``true``.  The working spellings
    ``True``/``False``/``Unknown`` are already bound and never reach a raise
    site, so case-insensitivity cannot shadow a name that works."""
    assert "did you mean `True`?" in "\n".join(truth_literal_hint_lines(["TRUE"]))
    assert "did you mean `Unknown`?" in "\n".join(
        truth_literal_hint_lines(["NULL"])
    )


def test_hint_names_all_three_truth_values():
    """Even for ``true``, the hint spells out ``Unknown`` — titlecase is the
    least guessable part of the language's vocabulary."""
    joined = "\n".join(truth_literal_hint_lines(["true"]))
    assert "`True`" in joined
    assert "`False`" in joined
    assert "`Unknown`" in joined


def test_only_matching_names_are_hinted():
    """Given a mix, the helper hints the boolean spellings and says nothing
    about the rest — the caller still appends its own remedy list."""
    joined = "\n".join(truth_literal_hint_lines(["foo_bar", "true"]))
    assert "`true`" in joined
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


def test_bare_lowercase_true_names_the_True_literal():
    """The reproduction from the todo: bare ``true`` in a strict file listed
    five remedies, none of them the right answer."""
    with pytest.raises(NameError) as exc_info:
        _load_inline_clausal(
            "_truth_literal_true_test", "Flag(true),\n"
        )
    msg = str(exc_info.value)
    assert "did you mean `True`?" in msg
    assert "`Unknown`" in msg


def test_bare_null_names_the_Unknown_literal():
    with pytest.raises(NameError) as exc_info:
        _load_inline_clausal("_truth_literal_null_test", "Tri(null),\n")
    assert "did you mean `Unknown`?" in str(exc_info.value)


def test_mixed_undeclared_keeps_both_hint_and_remedies():
    """When only some undeclared names are boolean spellings, the author still
    needs the five remedies to fix the others."""
    with pytest.raises(NameError) as exc_info:
        _load_inline_clausal(
            "_truth_literal_mixed_test",
            "Flag(true),\nColor(truthlit_mixed_beta),\n",
        )
    msg = str(exc_info.value)
    assert "did you mean `True`?" in msg
    assert "truthlit_mixed_beta" in msg
    assert "bare atom references must be one of:" in msg
    assert "-import_from" in msg
    assert "global_atom" in msg


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


def test_dict_key_true_names_the_True_literal():
    """``{true: 1}`` raises from a different site with its own message and
    deserves the same steer."""
    with pytest.raises(NameError) as exc_info:
        _load_inline_clausal(
            "_truth_literal_dictkey_test",
            "Row({true: 1}),\n",
        )
    msg = str(exc_info.value)
    assert "did you mean `True`?" in msg
