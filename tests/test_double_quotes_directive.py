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


# ─── The mode is threaded, and the ISO functor rule is enforced ──────────────
#
# Task 10 adds no literal-semantics change: ``'x'`` and ``"x"`` still both
# compile to the atom ``x``.  What it adds is the MACHINERY the flip needs —
# a quote map per file, a ``_double_quotes_mode`` on the EmbedTransformer that
# ``-double_quotes(Mode)`` sets in file order, and both of those threaded into
# every per-clause TermTransformer — plus the one rule that is mode-independent
# and can therefore land early: a double-quoted string is never a functor.


def test_double_quoted_string_as_functor_is_refused():
    with pytest.raises(SyntaxError) as exc_info:
        _load_inline_clausal("_dq_functor", 'p("foo"(1)),\n')
    assert "functor" in str(exc_info.value)


def test_single_quoted_functor_sugar_still_works():
    """``'name'(Args)`` keeps lowering to a name reference.

    The last clause is the operator spelling from the brief, ``'+'(1, 2)``:
    it is compiled (that is what this test pins) but never solved — building
    that term at run time wants a ``+/2`` term class in scope, which is a
    scoping question the sugar has never answered and this task does not
    change.
    """
    mod = _load_inline_clausal(
        "_sq_functor",
        "sq_probe(1),\n"
        "sq_run(X) <- 'sq_probe'(X),\n"
        "sq_op_term('+'(1, 2)),\n",
    )
    assert len(list(solve(("sq_run", 1), mod))) == 1


def test_double_quoted_functor_refusal_is_positioned():
    """The refusal carries the offending line, so the loader's caret window
    points at the literal rather than at the top of the file."""
    with pytest.raises(SyntaxError) as exc_info:
        _load_inline_clausal(
            "_dq_functor_pos",
            "p(1),\n"
            'r("foo"(1)),\n',
        )
    assert exc_info.value.lineno == 2
    assert "6.3.3" in str(exc_info.value)


def test_double_quoted_atom_argument_is_still_an_atom():
    """Stage A is additive: the refusal is about the FUNCTOR position only."""
    mod = _load_inline_clausal(
        "_dq_arg_ok",
        '-double_quotes(atom)\n'
        'dq_arg_probe("foo", \'foo\'),\n',
    )
    assert len(list(solve(("dq_arg_probe", "foo", "foo"), mod))) == 1


def test_directive_sets_the_mode_on_the_transformer():
    import ast as _ast

    from clausal.templating.term_rewriting import EmbedTransformer

    source = '-double_quotes(atom)\ndq_mode_probe(1),\n'
    transformer = EmbedTransformer(
        source_lines=source.splitlines(keepends=True), filename="<probe>")
    transformer.visit(_ast.parse(source))
    assert transformer._double_quotes_mode == "atom"


def test_mode_and_quote_map_reach_every_term_transformer():
    import ast as _ast

    from clausal.templating.term_rewriting import EmbedTransformer

    source = 'dq_thread_probe("x"),\n'
    transformer = EmbedTransformer(
        source_lines=source.splitlines(keepends=True), filename="<probe>")
    transformer.visit(_ast.parse(source))
    term_transformer = transformer._make_term_transformer()
    assert term_transformer._double_quotes_mode == "atom"
    assert term_transformer._quote_map == transformer._quote_map
    assert term_transformer._quote_map  # the file's one literal is in it


def test_no_source_lines_means_no_quote_map():
    """The REPL/IPython transform site passes no source_lines; the map
    degrades to empty and the functor refusal simply cannot fire there."""
    from clausal.templating.term_rewriting import EmbedTransformer

    transformer = EmbedTransformer(implicit_atoms_default=True, interactive=True)
    assert transformer._quote_map == {}
    assert transformer._double_quotes_mode == "atom"
