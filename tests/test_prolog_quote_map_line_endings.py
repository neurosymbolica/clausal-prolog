"""The translator's quote map must survive a blank line.

``build_quote_map`` feeds ``tokenize`` through ``readline`` and so needs the
source's lines WITH their endings (its docstring says so; the engine's
EmbedTransformer passes them that way). The translator passed
``source.splitlines()``, without endings, and tokenize reads a bare ``""`` --
any blank line -- as end of file. The map was cut short at the first blank
line, which in practice means EMPTY for most files (measured 2026-09-26: lost
in 555 of 760 downstream sources). Every quote lookup then answered "unknown"
and the literal rule fell back to the -double_quotes MODE, so a single-quoted
atom -- an atom in EVERY mode -- was exported as a string wherever the mode
is chars.

Today that already mis-exported two literals downstream; under the default's
flip to chars it would turn every `'?'` meta mode in a library's
-meta_predicate into `"?"`, which Scryer refuses outright
(``syntax_error(invalid_meta_predicate_decl)``).
"""

from clausal.tools.clausal_to_prolog import clausal_source_to_prolog


def _meta(out):
    return [line for line in out.splitlines() if "meta_predicate" in line]


def test_a_single_quoted_atom_after_a_blank_line_stays_an_atom_under_chars():
    # nv
    out = clausal_source_to_prolog(
        "-double_quotes(chars)\n"
        "\n"
        "p(X) <- (X == 'kept_as_atom')\n")
    assert "'kept_as_atom'" not in out and "kept_as_atom" in out
    assert '"kept_as_atom"' not in out


def test_a_double_quoted_literal_after_a_blank_line_is_still_a_string_under_chars():
    """The fix must not turn the rule around: `"..."` under chars IS a string."""
    # nv
    out = clausal_source_to_prolog(
        "-double_quotes(chars)\n"
        "\n"
        'p(X) <- (X == "a_string")\n')
    assert '"a_string"' in out


def test_meta_modes_after_a_leading_blank_line_stay_atoms_under_chars():
    """The shape that breaks a whole library: a meta declaration whose `'?'`
    modes sit after a blank line in a chars-mode file."""
    # nv
    out = clausal_source_to_prolog(
        "\n"
        "-double_quotes(chars)\n"
        "-meta_predicate(foo('?', 1))\n\n"
        "foo(A, B) <- (call(B, A))\n")
    assert _meta(out) == [":- meta_predicate(foo(?, 1))."]
