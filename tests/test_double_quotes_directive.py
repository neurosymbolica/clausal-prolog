"""``-double_quotes/1`` — the strings-migration RATCHET (step 2 of the
strings/atom-tag program; see
``todo/strings-lost-in-the-atom-pivot-double-quotes-are-char-lists-2026-09-06.md``
R-S4 in canonical).

This commit lands ONLY the directive's acceptance so downstream modules can
carry ``-double_quotes(atom)`` BEFORE the engine flips ``"..."`` to a
char-list string.  Semantics are unchanged here: ``"x"`` still denotes the
atom ``x`` whether or not the directive is present.  ``chars`` — the future
default — is refused until the flip lands, so no module can claim string
semantics it does not get.  The directive is scheduled for DELETION once
every module has dropped it; it is a migration ratchet, not a compatibility
flag.
"""

import os
import tempfile

import pytest

import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.solve import solve


def _load_inline_clausal(name: str, source: str):
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


def test_double_quotes_atom_is_accepted_and_is_a_no_op():
    """``-double_quotes(atom)`` loads, and a double-quoted literal keeps
    today's meaning (the atom)."""
    mod = _load_inline_clausal(
        "_dq_ratchet_atom",
        '-double_quotes(atom)\n'
        'dq_ratchet_probe("hello"),\n',
    )
    answers = list(solve(("dq_ratchet_probe", "hello"), mod))
    assert len(answers) == 1


def test_double_quotes_chars_is_refused_until_the_flip():
    with pytest.raises(SyntaxError) as exc_info:
        _load_inline_clausal(
            "_dq_ratchet_chars",
            '-double_quotes(chars)\n'
            'dq_ratchet_probe2("hello"),\n',
        )
    msg = str(exc_info.value)
    assert "-double_quotes(chars)" in msg
    assert "not yet supported" in msg


@pytest.mark.parametrize(
    "directive",
    ["-double_quotes", "-double_quotes()", "-double_quotes(codes)",
     '-double_quotes("atom")', "-double_quotes(atom, chars)"],
)
def test_double_quotes_other_forms_are_refused(directive):
    with pytest.raises(SyntaxError) as exc_info:
        _load_inline_clausal("_dq_ratchet_bad", directive + "\n")
    assert "-double_quotes" in str(exc_info.value)
