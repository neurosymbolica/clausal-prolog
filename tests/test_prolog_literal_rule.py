"""The translator's literal rule: a str literal lowers by the MODULE's
``-double_quotes`` mode AND by its own quote character.

Item J of todo/strings-lost-in-the-atom-pivot-double-quotes-are-char-lists-
2026-09-06.md (operator go 2026-09-07). The rule is the compiler's own
(``term_rewriting.visit_Constant`` reading ``_quote_of_positioned`` and the
position-sensitive ``-double_quotes`` mode), so translator and runtime agree
by construction:

* ``'...'`` is an ATOM in every mode (ISO 6.4.2 quoted token);
* ``"..."`` is a STRING -- a Prolog double-quoted token, ``double_quotes=chars``
  on both target engines -- under ``chars`` mode (the engine default since
  2026-09-26) and an ATOM under ``atom`` mode, the opt-out;
* the mode governs the literals BELOW the directive (position-sensitive,
  the same shape as the compiler's).

Before this rule the candidate's translator emitted EVERY str literal as a
Prolog string, so under atom mode an atom in the engine became a char list
in the export -- the silent wrong answer bda6b039 fixed, reversed -- and
gate 5's ledger reader (which accepts only atoms for unit ids) went blind.
"""
from clausal.tools.clausal_to_prolog import clausal_source_to_prolog


def _t(src: str) -> str:
    return clausal_source_to_prolog(src, strict=True)


# ── atom mode (the default) ─────────────────────────────────────────────

def test_double_quoted_is_an_atom_in_default_mode():
    assert "p(x)." in _t('-double_quotes(atom)\np("x"),\n')


def test_double_quoted_text_is_a_quoted_atom_in_default_mode():
    assert "p('a b')." in _t('-double_quotes(atom)\np("a b"),\n')


def test_single_quoted_is_an_atom_in_default_mode():
    assert "q(x)." in _t("q('x'),\n")


def test_default_mode_newline_is_escaped_inside_the_quoted_atom():
    # class G: a RAW newline inside a quoted token is syntax_error(missing_quote)
    out = _t('-double_quotes(atom)\np("a\\nb"),\n')
    assert "p('a\\nb')." in out
    assert "\np(" not in out.replace("\np('a\\nb')", "")


# ── chars mode ──────────────────────────────────────────────────────────

def test_double_quoted_is_a_string_in_chars_mode():
    assert 'p("x").' in _t('-double_quotes(chars)\np("x"),\n')


def test_single_quoted_is_an_atom_in_chars_mode_too():
    assert "q(x)." in _t("-double_quotes(chars)\nq('x'),\n")


def test_chars_mode_is_emitted_as_the_iso_flag_not_a_bare_directive():
    """Scryer rejects ``:- double_quotes(chars).`` outright
    (domain_error(directive, double_quotes/1)) and Trealla warns -- both fail
    G2's warnings-as-errors consult. ``:- set_prolog_flag(double_quotes,
    chars).`` consults clean on both (measured 2026-09-07)."""
    out = _t('-double_quotes(chars)\np("x"),\n')
    assert ":- set_prolog_flag(double_quotes, chars)." in out
    assert ":- double_quotes(chars)." not in out


def test_atom_mode_directive_emits_nothing():
    """``-double_quotes(atom)`` is the migration ratchet's no-op: every
    literal below it is emitted as an atom, so there is no string for the
    target engine to misread and nothing to declare."""
    out = _t('-double_quotes(atom)\np("x"),\n')
    assert "double_quotes" not in out
    assert "p(x)." in out


# ── position sensitivity ────────────────────────────────────────────────

def test_the_mode_governs_only_the_literals_below_the_directive():
    # The default is chars (2026-09-26): p's literal is a string, and only
    # q's, below the directive, is an atom.
    out = _t('p("x"),\n-double_quotes(atom)\nq("x"),\n')
    assert 'p("x").' in out
    assert "q(x)." in out


def test_the_flag_directive_is_emitted_where_the_mode_changes():
    out = _t('-double_quotes(atom)\np("x"),\n-double_quotes(chars)\nq("x"),\n')
    assert out.index("p(x).") < out.index("set_prolog_flag") < out.index('q("x").')


def test_an_explicit_leading_chars_directive_still_emits_the_flag():
    """``-double_quotes(chars)`` at the top says what the default already
    says, and the literal lowers identically -- but the directive is a
    statement of the module's dependency, and its flag is transcribed
    (pinned here so the flip did not silently change the emission)."""
    declared = _t('-double_quotes(chars)\np("x"),\n')
    assert 'p("x").' in declared
    assert declared.index(":- set_prolog_flag(double_quotes, chars).") < declared.index('p("x").')


def test_the_default_needs_no_flag_directive():
    """A module that declares nothing emits its ``"..."`` literals as Prolog
    strings and NO ``set_prolog_flag``: both target engines already read a
    double-quoted token as chars, which is the engine default too."""
    out = _t('p("x"),\n')
    assert 'p("x").' in out
    assert "set_prolog_flag" not in out
