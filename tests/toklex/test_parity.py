"""Old-vs-new tokenizer differential + the swapped tokenize() contract.

The public ``tokenize()`` (``clausal.tools.prolog_tokenizer``) is now a
shim over the toklex-generated lexer (``clausal/tools/toklex/specs/iso.toklex.pl``).
This module is the parity proof: the ``NASTY`` shapes test, an exact-stream
regression sample, the error-raising contract, a differential corpus sweep
against ``/workspace/scryer-prolog/src/lib/*.pl``, and the small set of
KNOWN, RATIFIED behavioral divergences from the old hand-written
``_Tokenizer`` (now frozen at ``clausal/tools/toklex/_bootstrap.py``, used
only to bootstrap-parse ``.toklex.pl`` spec files -- see that module's
docstring).

Differential methodology (scratchpad evidence, not re-run here): every file
under ``/workspace/scryer-prolog/src/lib/**/*.pl`` (60, recursive) plus the
``NASTY`` list below was tokenized with the OLD tokenizer and pickled
(``old_capture.pkl``), then replayed against the NEW ``tokenize()``.

**History** (full traces in task-10-report.md):

- Round 1: 5 of 86 entries mismatched. 2 (non-ASCII ``Ll``/``Lu`` letters as
  atom-start characters, e.g. Greek delta in scryer's ``numerics/``
  predicates) were fixed by extending ``iso.toklex.pl``'s
  ``small``/``capital`` classes with ``unicode('Ll')``/``unicode('Lu')``.
  The other 3 were one root cause ("Class A"): an escape's optional closing
  backslash immediately adjacent to the enclosing quoted-atom/string's own
  closing delimiter raced against the driver's Task-8 commit-region rule,
  which unconditionally reported "unterminated" once a stuck attempt had
  crossed into a proven-unbounded-backup DFA region, even when a perfectly
  good shorter accept was already recorded (e.g. ``'\\x41\\'.``).
- Round 2: ``driver.py::_resolve``'s commit branch was made distance-gated
  -- it only forces "unterminated" when the stuck point is farther from the
  longest recorded accept than ``lexer.max_backup``; within that bound it
  falls through to the normal accept-history walk. Fixed the isolated
  synthetic ``'\\x41\\'.`` case but not the same construct embedded in real
  code (the ambiguous "second escape" reading can travel arbitrarily far
  before finding a stray rescuing quote, same shape as Task 8's
  quote-doubling case) -- 2 corpus files (``charsio.pl``,
  ``serialization/abnf.pl``) still mismatched.
- Round 3: grammar surgery in ``iso.toklex.pl`` -- split the old, unlooped
  ``escape`` def (kept only for ``char_code``'s single, non-repeated
  ``0'\\...`` construct) into ``esc_term`` (digit/hex escape WITH its
  closing backslash -- unambiguous, the mandatory trailing backslash pins
  the digit run's length) and ``esc_open_hex``/``esc_open_oct`` (the same
  escape WITHOUT a closing backslash, usable mid-string before ordinary
  content/a doubled delimiter, or at the very end before the token's own
  closing delimiter) plus ``esc_other`` (everything else ``\\c`` can mean).
  This encodes ``prolog_tokenizer.py``'s actual 1-character-lookahead
  greedy rule declaratively: an unterminated escape run may not be
  immediately followed by another backslash-led item in the same
  repetition step. The FIRST version of this surgery still had a hole:
  ``hexdig*``/``octdig*`` could stop at any prefix of the available
  digits, not just the maximal one, so ``'\\x41\\'`` could ALSO be read as
  a short ``esc_open_hex="\\x4"`` + leftover ``"1"`` reinterpreted as
  ordinary content + a fresh escape at the interior backslash swallowing
  the real closing quote -- reproducing the bug through a different split
  of the same input. Closed by pairing ``esc_open_hex``/``esc_open_oct``
  ONLY with ``qplain_no_hex``/``qplain_no_oct`` (``qplain`` with the
  corresponding digit class also excluded from what it may match): a
  non-maximal digit-run split always leaves a hexdig/octdig character
  immediately after it, and the restricted qplain variants refuse to match
  that character, so only the maximal split survives. **Result: 0
  unexplained mismatches** across all 86 differential entries. Only the
  two divergences the brief pre-approved (``0x.``, ``1.5e.``) remain in
  ``EXPECTED_DIVERGENCES`` below.
"""
import glob

import pytest

from clausal.tools.prolog_tokenizer import Token, TokenType, TokenizeError, tokenize

NASTY = [
    "foo(X) :- bar(X).", "X =.. L.", "a. ", "1. ", "1.5.", "1.0e7. ", "0'a.",
    "0'''.", "'qu''ote'.", '"str".', "% c\na.", "/* x /* y */ z */a.",
    "[1,2|T].", "{a}.", "a;b.", "!.", "1_000.", "0x1F.", "0o17.", "0b101.",
    "'\\x41\\'.", "'\\q'.", "p :- q, r.", "- 1.", "-1.", "f(-1).",
]


class TestTokenStream:
    @pytest.mark.parametrize("src", NASTY)
    def test_nasty_inputs_produce_expected_shapes(self, src):
        toks = tokenize(src)
        assert toks[-1].type == TokenType.END
        assert all(isinstance(t, Token) for t in toks)

    def test_escape_closing_backslash_adjacent_to_delimiter_backs_up(self):
        # Round-2/3 pin: an escape's optional closing backslash immediately
        # followed by the quoted-atom's own closing quote (`'\x41\'.`) used
        # to unconditionally hit the commit-region "unterminated" branch
        # (round 1). Fixed by the distance-gated commit (round 2) plus the
        # esc_term/esc_open_hex/esc_open_oct grammar surgery (round 3),
        # which now correctly resolves to the shorter, valid `quoted_atom`
        # accept, matching the old hand-written tokenizer exactly.
        toks = tokenize("'\\x41\\'.")
        assert [(t.type, t.value, t.quoted) for t in toks] == [
            (TokenType.ATOM, "A", True),
            (TokenType.DOT, ".", False),
            (TokenType.END, "", False),
        ]

    def test_escape_closing_backslash_adjacent_to_delimiter_embedded(self):
        # The construct from the test above, but embedded in real
        # surrounding code rather than truncated at end-of-input -- this is
        # exactly what rounds 1/2 could NOT close (the "second escape"
        # reading could travel arbitrarily far looking for a rescuing
        # quote character before the distance-gated commit fix alone).
        # Round 3's grammar surgery (forcing the escape's digit run to be
        # read maximally) removes the rival reading at the grammar level,
        # so this now succeeds regardless of what follows.
        toks = tokenize(
            "foo(X) :- X = '\\x41\\', bar(X), baz(Y, Z), qux(1,2,3).\n"
        )
        got = [(t.type, t.value) for t in toks]
        assert (TokenType.ATOM, "A") in got
        assert toks[-1].type == TokenType.END

    def test_exact_stream_sample(self):
        toks = tokenize("foo(X) :- 'b ar', 1.5e2. ")
        got = [(t.type, t.value) for t in toks]
        assert got == [
            (TokenType.ATOM, "foo"), (TokenType.LPAREN, "("), (TokenType.VAR, "X"),
            (TokenType.RPAREN, ")"), (TokenType.ATOM, ":-"), (TokenType.ATOM, "b ar"),
            (TokenType.COMMA, ","), (TokenType.FLOAT, 150.0), (TokenType.DOT, "."),
            (TokenType.END, ""),
        ]
        assert toks[5].quoted is True

    def test_errors_still_raise(self):
        with pytest.raises(TokenizeError):
            tokenize("'unterminated")
        with pytest.raises(TokenizeError):
            tokenize('"unterminated')
        with pytest.raises(TokenizeError):
            tokenize("\x01")


# ── Known, ratified divergences from the old hand-written tokenizer ──────
#
# Each entry: src -> callable(toks) that asserts the NEW behavior and
# documents why it differs from the OLD tokenizer. As of round 3's grammar
# surgery, this is the COMPLETE set -- the differential sweep shows 0
# unexplained mismatches (see module docstring).

def _assert_lexes_0x_no_digits(toks):
    assert [(t.type, t.value) for t in toks[:3]] == [
        (TokenType.INTEGER, 0), (TokenType.ATOM, "x"), (TokenType.DOT, "."),
    ]


def _assert_lexes_1_5e_no_digits(toks):
    assert [(t.type, t.value) for t in toks[:3]] == [
        (TokenType.FLOAT, 1.5), (TokenType.ATOM, "e"), (TokenType.DOT, "."),
    ]


EXPECTED_DIVERGENCES = {
    # Old: TokenizeError("malformed hexadecimal literal at 1:1") -- the
    # hand-written `_read_number` required at least one hex digit after
    # `0x` and raised otherwise. New: toklex's `hex_int` token rule needs a
    # hex digit to match at all, so with none present the automaton simply
    # doesn't take that branch -- maximal munch instead falls back to the
    # `integer` rule (`0`) followed by a fresh `name_atom` (`x`). This is
    # the SWI-compatible reading (`0x` alone is `0` then the atom `x`), and
    # the brief pre-approved it explicitly.
    "0x.": _assert_lexes_0x_no_digits,
    # Same shape, the float/exponent case. Old: TokenizeError("malformed
    # float literal at 1:1") (`_read_number`'s exponent loop required a
    # digit after `e`/`E` and raised via `_to_number(float, ...)` when
    # there wasn't one, since by then it had already committed to
    # `is_float = True`). New: toklex's `float_num` rule's `exp` requires a
    # digit after `e` too, so with none present maximal munch falls back to
    # `integer`-then-dot semantics: `1.5` (float_num, no exponent) then a
    # fresh `name_atom` (`e`). Brief pre-approved.
    "1.5e.": _assert_lexes_1_5e_no_digits,
}


class TestExpectedDivergences:
    @pytest.mark.parametrize("src", sorted(EXPECTED_DIVERGENCES))
    def test_divergence_is_the_documented_one(self, src):
        toks = tokenize(src)
        EXPECTED_DIVERGENCES[src](toks)

    def test_no_divergence_for_underscore_in_exponent(self):
        # The brief's third check: `1e1_0` -- old's exponent loop is a bare
        # `isdigit()` scan (no `_` allowed), and toklex's `exp` def also
        # uses bare `digit` (not `udigits`) for its exponent run. Both stop
        # at `1e1`, leaving `_0` to lex separately as a VAR. No divergence.
        toks = tokenize("1e1_0.")
        got = [(t.type, t.value) for t in toks[:3]]
        assert got == [
            (TokenType.FLOAT, 10.0), (TokenType.VAR, "_0"), (TokenType.DOT, "."),
        ]


SCRYER_LIB = "/workspace/scryer-prolog/src/lib"


class TestScryerCorpus:
    """Differential against the reference corpus: every .pl file the OLD
    tokenizer could tokenize was replayed against the NEW one in the
    scratchpad differ (see module docstring); as of round 3's grammar
    surgery, all 46 top-level corpus files this test parametrizes over
    match exactly (0 unexplained mismatches across the full 86-entry sweep,
    corpus + NASTY). This in-repo test is the shallower structural gate the
    brief specifies: a file the new tokenizer can't handle skips rather
    than fails -- no file currently needs that fallback, but it's kept for
    robustness against dialect-outside-scope corpus files in general.

    ``len(toks) >= 1`` (not ``> 1``, the brief's original template): one
    corpus file, crypto.pl, has an unbalanced ``/*``/``*/`` count (16
    openers, 15 closers), so under nested-comment mode the entire file from
    that point on is silently swallowed as one still-open comment -- old
    AND new tokenizer agree exactly (both: just the END token, verified via
    the scratchpad differ's captured old-tokenizer pickle). That is
    faithfully-reproduced pre-existing behavior, not a Task 10 regression,
    so the assertion has to accept a legitimately-empty (comment-only)
    token stream rather than treating it as a sanity-check failure."""

    @pytest.mark.parametrize("path", sorted(glob.glob(SCRYER_LIB + "/*.pl")))
    def test_corpus_file(self, path):
        src = open(path, encoding="utf-8", errors="strict").read()
        try:
            toks = tokenize(src)
        except TokenizeError:
            pytest.skip("file uses syntax outside the dialect (also failed before)")
        assert toks[-1].type == TokenType.END and len(toks) >= 1
