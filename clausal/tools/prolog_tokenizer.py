"""Prolog tokenizer (Phase 3.1).

Generated behavior: ``tokenize()`` is a thin shim over the toklex
incremental lexer compiled from the ISO token spec at
``clausal/tools/toklex/specs/iso.toklex.pl`` (design doc:
``implementation_plans/toklex-token-formalism-design.md``). The actual
lexical rules (quoted atoms, character codes, graphic tokens, nested block
comments, the dot-as-terminator rule) live in that spec, not in this module.

The spec file itself is read by a separate frozen bootstrap reader,
``clausal/tools/toklex/_bootstrap.py`` -- the design doc's "bootstrapping"
story: the original hand-written tokenizer/parser reads the spec that
generates its own replacement. It has to be a separate module: this
module's ``tokenize()`` cannot read the spec that builds it without
recursing into itself.

Public API:
    tokenize(source, *, nested_comments=True) -> list[Token]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TokenType(Enum):
    ATOM = "atom"
    VAR = "var"
    INTEGER = "integer"
    FLOAT = "float"
    STRING = "string"
    LPAREN = "("
    RPAREN = ")"
    LBRACKET = "["
    RBRACKET = "]"
    LCURLY = "{"
    RCURLY = "}"
    BAR = "|"
    COMMA = ","
    DOT = "."
    END = "end"


@dataclass(frozen=True, slots=True)
class Token:
    type: TokenType
    value: str | int | float
    line: int
    col: int
    quoted: bool = False  # True for a quoted atom ('foo') — F035
    # Position just past the token (F029/F037). Internal span metadata, excluded
    # from equality/repr so existing Token(...) comparisons stay valid.
    end_line: int = field(default=0, compare=False, repr=False)
    end_col: int = field(default=0, compare=False, repr=False)

    def __repr__(self) -> str:
        return f"Token({self.type.value!r}, {self.value!r}, {self.line}:{self.col})"


class TokenizeError(Exception):
    """Raised when the tokenizer encounters invalid input."""

    def __init__(self, message: str, line: int, col: int):
        self.line = line
        self.col = col
        super().__init__(f"{message} at {line}:{col}")


_KIND_MAP = {
    "lparen": TokenType.LPAREN, "rparen": TokenType.RPAREN,
    "lbracket": TokenType.LBRACKET, "rbracket": TokenType.RBRACKET,
    "lcurly": TokenType.LCURLY, "rcurly": TokenType.RCURLY,
    "bar": TokenType.BAR, "comma": TokenType.COMMA, "end": TokenType.DOT,
    "name_atom": TokenType.ATOM, "graphic_tok": TokenType.ATOM,
    "cut": TokenType.ATOM, "semicolon": TokenType.ATOM,
    "quoted_atom": TokenType.ATOM, "variable": TokenType.VAR,
    "integer": TokenType.INTEGER, "hex_int": TokenType.INTEGER,
    "oct_int": TokenType.INTEGER, "bin_int": TokenType.INTEGER,
    "char_code": TokenType.INTEGER, "float_num": TokenType.FLOAT,
    "string": TokenType.STRING,
}


def _end_of_source_pos(source: str) -> tuple[int, int]:
    """The (line, col) just past the last character of `source`, using the
    same 1-based line/col cursor convention `_Tokenizer._advance` used (a
    newline moves to the next line at col 1; every other char, including
    trailing whitespace/comments, advances col by one). Computed directly
    from the source text (not driver internals) so the END token's
    position matches today's behavior regardless of what the driver
    consumed as trivia."""
    nl_count = source.count("\n")
    if nl_count == 0:
        return 1, len(source) + 1
    last_nl = source.rfind("\n")
    return nl_count + 1, len(source) - last_nl


def tokenize(source: str, *, nested_comments: bool = True) -> list[Token]:
    """Tokenize Prolog source text into a list of tokens.

    Generated behavior: the token stream is produced by the toklex
    incremental lexer compiled from the ISO token spec at
    ``clausal/tools/toklex/specs/iso.toklex.pl`` (batch-driven via
    ``IncrementalLexer.run``), then mapped onto this module's ``Token``
    stream via ``_KIND_MAP``. This function is a thin shim: the actual
    lexical rules (quoting, escapes, numbers, nested comments, the
    dot-as-terminator rule) live in the spec, not here.

    Parameters
    ----------
    source : str
        Prolog source text.
    nested_comments : bool
        If True (default, SWI-compatible), ``/* */`` comments may nest.
        If False (strict ISO), nested ``/*`` inside a comment is ignored.

    Returns
    -------
    list[Token]
        Token list ending with a single END token.
    """
    # Deferred import: clausal.tools.toklex.spec parses spec files with
    # clausal.tools.prolog_parser, which imports this module for Token /
    # TokenType / tokenize -- an eager module-level import here would be
    # circular. By the time tokenize() is first called this module is
    # already fully initialized, so the cycle resolves fine.
    from clausal.tools.toklex import IncrementalLexer, load_lexer
    from clausal.tools.toklex.regex_target import RegexLexer
    from clausal.tools.toklex.spec import SpecError

    lexer = load_lexer()
    try:
        # fast path: the spec rendered as one `re` master pattern (the
        # per-char loop runs in C); parity with the table driver is
        # enforced by tests/toklex/test_regex_target.py's differentials.
        inc = RegexLexer(lexer, nested_comments=nested_comments)
    except SpecError:
        # a spec using constructs the regex renderer can't express
        # (general but_not) falls back to the reference table driver
        inc = IncrementalLexer(lexer, nested_comments=nested_comments)
    toks = inc.run(source)

    result: list[Token] = []
    for t in toks:
        if t.kind == "error":
            reason, culprit = t.value
            line, col = t.start[1], t.start[2]
            if reason == "unterminated":
                if t.lexeme.startswith('"'):
                    raise TokenizeError("Unterminated string", line, col)
                raise TokenizeError("Unterminated quoted atom", line, col)
            if reason == "no_token":
                raise TokenizeError(f"Unexpected character {culprit!r}", line, col)
            if reason == "bad_token":
                # A value builder raised on this lexeme (driver.py's
                # defense-in-depth catch in `_emit`, e.g. a malformed
                # `0x_`/`0'\...` shape) -- `culprit` is the lexeme itself.
                raise TokenizeError(f"malformed token {culprit!r}", line, col)
            # 'invalid_encoding' -- unreachable when driving from a str
            # source (no feed_bad calls occur in this batch shim), kept
            # only so an error Tok never falls through silently.
            raise TokenizeError(f"Invalid input {culprit!r}", line, col)

        result.append(Token(
            _KIND_MAP[t.kind], t.value, t.start[1], t.start[2],
            quoted=(t.kind == "quoted_atom"),
            end_line=t.end[1], end_col=t.end[2],
        ))

    end_line, end_col = _end_of_source_pos(source)
    result.append(Token(
        TokenType.END, "", end_line, end_col,
        end_line=end_line, end_col=end_col,
    ))
    return result

