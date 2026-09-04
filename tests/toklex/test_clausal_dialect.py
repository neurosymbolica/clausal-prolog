from clausal.tools.toklex import load_lexer
from clausal.tools.toklex.driver import IncrementalLexer


def lex(text):
    return IncrementalLexer(load_lexer("clausal")).run(text)


def test_no_end_token_dot_is_graphic():
    kinds = [t.kind for t in lex("a. ")]
    assert kinds == ["name_atom", "graphic_tok"]      # no 'end' anywhere


def test_directive_surface_tokens():
    toks = lex("-module(m, [f])\n-allow_singletons\n")
    assert [(t.kind, t.lexeme) for t in toks[:3]] == [
        ("graphic_tok", "-"), ("name_atom", "module"), ("lparen", "("),
    ]
    assert toks[2].glue == "glued"                     # -module( is compound-open


def test_reserved_codepoint_rejected_everywhere():
    # R1 (P3-1 atom-pivot plan): the reserved ⟨SEP⟩ codepoint is U+E000,
    # matching clausal.toklex.pl's `reserved` class and
    # clausal.logic.atoms.HIDDEN_SEP — was the U+0001 placeholder pre-R1.
    for src in ["ab ", "'ab' ", '"ab" ', "% cc\na "]:
        kinds = [t.kind for t in lex(src)]
        assert "error" in kinds, src


def test_optional_module_level_comma_is_just_a_token():
    # NOTE: the brief's literal input "f(a), g(b)\n" contains only one
    # comma character, which can never satisfy count == 2 regardless of
    # dialect content -- a typo in the brief, unrelated to the dialect
    # spec. Fixed here by adding a second (trailing, optional)
    # module-level comma; the assertion itself is untouched. See
    # task-11-report.md for the full justification.
    kinds = [t.kind for t in lex("f(a), g(b),\n")]
    assert kinds.count("comma") == 2                   # L1 policy, not lexer's business


def test_iso_lexer_unaffected():
    kinds = [t.kind for t in IncrementalLexer(load_lexer("iso")).run("a. ")]
    assert kinds == ["name_atom", "end"]
