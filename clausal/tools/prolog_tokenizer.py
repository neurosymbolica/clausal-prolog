"""Prolog tokenizer (Phase 3.1).

Lexes Prolog source text into a stream of tokens suitable for the Pratt
parser.  Handles all standard Prolog token types including quoted atoms,
character codes, graphic tokens, nested block comments, and the tricky
dot-as-terminator rule.

Public API:
    tokenize(source, *, nested_comments=True) -> list[Token]
"""

from __future__ import annotations

import re
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


# Characters that can form graphic/symbolic atoms
_GRAPHIC_CHARS = frozenset("#$&*+-./:<=>?@\\^~")

# Characters that terminate a graphic token
_GRAPHIC_STOP = frozenset("()[]{},%\"' \t\n\r")


def tokenize(source: str, *, nested_comments: bool = True) -> list[Token]:
    """Tokenize Prolog source text into a list of tokens.

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
    tokenizer = _Tokenizer(source, nested_comments=nested_comments)
    return tokenizer.run()


class _Tokenizer:
    """Stateful Prolog tokenizer."""

    def __init__(self, source: str, *, nested_comments: bool = True):
        self._src = source
        self._pos = 0
        self._line = 1
        self._col = 1
        self._nested_comments = nested_comments
        self._tokens: list[Token] = []

    def run(self) -> list[Token]:
        while self._pos < len(self._src):
            self._skip_whitespace_and_comments()
            if self._pos >= len(self._src):
                break
            self._read_token()
        self._push(TokenType.END, "", self._line, self._col)
        return self._tokens

    # ── Character access ─────────────────────────────────────────────

    def _peek(self, offset: int = 0) -> str:
        i = self._pos + offset
        if i < len(self._src):
            return self._src[i]
        return ""

    def _advance(self) -> str:
        ch = self._src[self._pos]
        self._pos += 1
        if ch == "\n":
            self._line += 1
            self._col = 1
        else:
            self._col += 1
        return ch

    def _at_end(self) -> bool:
        return self._pos >= len(self._src)

    def _push(self, ttype, value, line, col, *, quoted: bool = False) -> None:
        """Append a token, recording its end position (current cursor)."""
        self._tokens.append(Token(
            ttype, value, line, col,
            quoted=quoted, end_line=self._line, end_col=self._col,
        ))

    # ── Whitespace & comments ────────────────────────────────────────

    def _skip_whitespace_and_comments(self) -> None:
        while self._pos < len(self._src):
            ch = self._peek()
            if ch in " \t\n\r":
                self._advance()
            elif ch == "%" and not self._is_directive_percent():
                # Line comment
                while self._pos < len(self._src) and self._peek() != "\n":
                    self._advance()
            elif ch == "/" and self._peek(1) == "*":
                self._skip_block_comment()
            else:
                break

    def _is_directive_percent(self) -> bool:
        """% is always a line comment in Prolog."""
        return False

    def _skip_block_comment(self) -> None:
        # Consume /*
        self._advance()  # /
        self._advance()  # *
        depth = 1
        while self._pos < len(self._src) and depth > 0:
            ch = self._peek()
            if ch == "/" and self._peek(1) == "*" and self._nested_comments:
                self._advance()
                self._advance()
                depth += 1
            elif ch == "*" and self._peek(1) == "/":
                self._advance()
                self._advance()
                depth -= 1
            else:
                self._advance()
        # If depth > 0, unterminated comment — we silently accept it

    # ── Token dispatch ───────────────────────────────────────────────

    def _read_token(self) -> None:
        line, col = self._line, self._col
        ch = self._peek()

        # Single-character structural tokens
        if ch == "(":
            self._advance()
            self._push(TokenType.LPAREN, "(", line, col)
            return
        if ch == ")":
            self._advance()
            self._push(TokenType.RPAREN, ")", line, col)
            return
        if ch == "[":
            self._advance()
            self._push(TokenType.LBRACKET, "[", line, col)
            return
        if ch == "]":
            self._advance()
            self._push(TokenType.RBRACKET, "]", line, col)
            return
        if ch == "{":
            self._advance()
            self._push(TokenType.LCURLY, "{", line, col)
            return
        if ch == "}":
            self._advance()
            self._push(TokenType.RCURLY, "}", line, col)
            return
        if ch == "|":
            self._advance()
            self._push(TokenType.BAR, "|", line, col)
            return
        if ch == ",":
            self._advance()
            self._push(TokenType.COMMA, ",", line, col)
            return

        # Quoted atom
        if ch == "'":
            self._read_quoted_atom(line, col)
            return

        # Double-quoted string
        if ch == '"':
            self._read_string(line, col)
            return

        # Number (digit or 0x/0b/0o/0')
        if ch.isdigit():
            self._read_number(line, col)
            return

        # Variable or anonymous
        if ch == "_" or ch.isupper():
            self._read_variable(line, col)
            return

        # Lowercase atom (identifier)
        if ch.islower():
            self._read_word_atom(line, col)
            return

        # Dot — possibly clause terminator
        if ch == ".":
            self._read_dot_or_graphic(line, col)
            return

        # Exclamation mark (cut) — special atom
        if ch == "!":
            self._advance()
            self._push(TokenType.ATOM, "!", line, col)
            return

        # Semicolon — operator atom
        if ch == ";":
            self._advance()
            self._push(TokenType.ATOM, ";", line, col)
            return

        # Graphic token (operator characters)
        if ch in _GRAPHIC_CHARS:
            self._read_graphic(line, col)
            return

        raise TokenizeError(f"Unexpected character {ch!r}", line, col)

    # ── Quoted atom ──────────────────────────────────────────────────

    # ── ISO 6.4.2 escape sequences ───────────────────────────────────
    _SIMPLE_ESCAPES = {
        "a": "\a", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t",
        "v": "\v", "e": "\x1b", "s": " ", "\\": "\\", "'": "'", '"': '"',
        "`": "`",
    }

    def _read_escape(self, line: int, col: int) -> str:
        """Read an ISO escape after the backslash; '' for a line continuation."""
        if self._at_end():
            raise TokenizeError("Unterminated escape sequence", line, col)
        nxt = self._advance()
        if nxt == "\n":
            return ""  # line continuation — the \<newline> is removed
        if nxt == "x":
            digits = ""
            while not self._at_end() and self._peek() in "0123456789abcdefABCDEF":
                digits += self._advance()
            if not digits:
                raise TokenizeError("Empty hex escape (\\x)", line, col)
            if self._peek() == "\\":
                self._advance()  # closing backslash
            return chr(int(digits, 16))
        if nxt in "01234567":
            digits = nxt
            while not self._at_end() and self._peek() in "01234567":
                digits += self._advance()
            if self._peek() == "\\":
                self._advance()  # closing backslash
            return chr(int(digits, 8))
        mapped = self._SIMPLE_ESCAPES.get(nxt)
        if mapped is not None:
            return mapped
        # Unknown escape: keep the backslash and the char (lenient).
        return "\\" + nxt

    def _read_quoted_atom(self, line: int, col: int) -> None:
        self._advance()  # opening '
        chars: list[str] = []
        while True:
            if self._at_end():
                raise TokenizeError("Unterminated quoted atom", line, col)
            ch = self._advance()
            if ch == "'":
                # Doubled quote → literal '
                if self._peek() == "'":
                    self._advance()
                    chars.append("'")
                else:
                    break
            elif ch == "\\":
                chars.append(self._read_escape(line, col))
            else:
                chars.append(ch)
        self._push(TokenType.ATOM, "".join(chars), line, col, quoted=True)

    # ── Double-quoted string ─────────────────────────────────────────

    def _read_string(self, line: int, col: int) -> None:
        self._advance()  # opening "
        chars: list[str] = []
        while True:
            if self._at_end():
                raise TokenizeError("Unterminated string", line, col)
            ch = self._advance()
            if ch == '"':
                # Doubled quote → literal "
                if self._peek() == '"':
                    self._advance()
                    chars.append('"')
                else:
                    break
            elif ch == "\\":
                chars.append(self._read_escape(line, col))
            else:
                chars.append(ch)
        self._push(TokenType.STRING, "".join(chars), line, col)

    # ── Numbers ──────────────────────────────────────────────────────

    def _to_number(self, conv, text: str, label: str, line: int, col: int):
        """Convert a numeric literal, raising a positioned TokenizeError.

        Malformed literals (``0x``, ``1e``, ``1.5e``) would otherwise surface a
        bare ValueError with no line/col, crashing callers that catch only
        TokenizeError/ParseError (F040).
        """
        try:
            return conv(text)
        except ValueError:
            raise TokenizeError(f"malformed {label} literal", line, col) from None

    def _read_number(self, line: int, col: int) -> None:
        start = self._pos

        # Check for 0x, 0b, 0o, 0' prefixes
        if self._peek() == "0" and self._pos + 1 < len(self._src):
            nxt = self._peek(1)
            if nxt in "xX":
                self._advance()  # 0
                self._advance()  # x
                hex_start = self._pos
                while not self._at_end() and self._peek() in "0123456789abcdefABCDEF_":
                    self._advance()
                digits = self._src[hex_start:self._pos].replace("_", "")
                value = self._to_number(lambda d: int(d, 16), digits, "hexadecimal", line, col)
                self._push(TokenType.INTEGER, value, line, col)
                return
            if nxt in "bB":
                self._advance()  # 0
                self._advance()  # b
                bin_start = self._pos
                while not self._at_end() and self._peek() in "01_":
                    self._advance()
                digits = self._src[bin_start:self._pos].replace("_", "")
                value = self._to_number(lambda d: int(d, 2), digits, "binary", line, col)
                self._push(TokenType.INTEGER, value, line, col)
                return
            if nxt in "oO":
                self._advance()  # 0
                self._advance()  # o
                oct_start = self._pos
                while not self._at_end() and self._peek() in "01234567_":
                    self._advance()
                digits = self._src[oct_start:self._pos].replace("_", "")
                value = self._to_number(lambda d: int(d, 8), digits, "octal", line, col)
                self._push(TokenType.INTEGER, value, line, col)
                return
            if nxt == "'":
                # Character code: 0'a → 97, 0'\n → 10, 0''' → 39 (doubled quote)
                self._advance()  # 0
                self._advance()  # '
                if self._at_end():
                    raise TokenizeError("Unexpected end after 0'", line, col)
                ch = self._advance()
                if ch == "\\":
                    esc = self._read_escape(line, col)
                    code = ord(esc) if esc else 0
                elif ch == "'" and self._peek() == "'":
                    self._advance()  # doubled '' → literal quote (ISO)
                    code = ord("'")
                else:
                    code = ord(ch)
                self._push(TokenType.INTEGER, code, line, col)
                return

        # Regular decimal number
        while not self._at_end() and (self._peek().isdigit() or self._peek() == "_"):
            self._advance()

        # Check for float: digit followed by . followed by digit
        is_float = False
        if not self._at_end() and self._peek() == ".":
            # Look ahead: must have a digit after the dot
            if self._pos + 1 < len(self._src) and self._src[self._pos + 1].isdigit():
                is_float = True
                self._advance()  # .
                while not self._at_end() and (self._peek().isdigit() or self._peek() == "_"):
                    self._advance()

        # Exponent
        if not self._at_end() and self._peek() in "eE":
            is_float = True
            self._advance()  # e/E
            if not self._at_end() and self._peek() in "+-":
                self._advance()
            while not self._at_end() and self._peek().isdigit():
                self._advance()

        text = self._src[start:self._pos].replace("_", "")
        if is_float:
            value = self._to_number(float, text, "float", line, col)
            self._push(TokenType.FLOAT, value, line, col)
        else:
            value = self._to_number(int, text, "integer", line, col)
            self._push(TokenType.INTEGER, value, line, col)

    # ── Variables ────────────────────────────────────────────────────

    def _read_variable(self, line: int, col: int) -> None:
        start = self._pos
        self._advance()
        while not self._at_end() and (self._peek().isalnum() or self._peek() == "_"):
            self._advance()
        name = self._src[start:self._pos]
        self._push(TokenType.VAR, name, line, col)

    # ── Word atoms (lowercase identifiers) ───────────────────────────

    def _read_word_atom(self, line: int, col: int) -> None:
        start = self._pos
        self._advance()
        while not self._at_end() and (self._peek().isalnum() or self._peek() == "_"):
            self._advance()
        name = self._src[start:self._pos]
        self._push(TokenType.ATOM, name, line, col)

    # ── Dot (clause terminator vs graphic) ───────────────────────────

    def _read_dot_or_graphic(self, line: int, col: int) -> None:
        # Dot is a clause terminator when followed by whitespace, EOF, or %
        nxt = self._peek(1)
        if nxt == "" or nxt in " \t\n\r" or nxt == "%":
            self._advance()  # consume the dot
            self._push(TokenType.DOT, ".", line, col)
            return
        # Dot followed by a digit → it's part of a graphic token (not a number
        # since we'd have entered _read_number first if it started with a digit)
        # Just read as graphic
        self._read_graphic(line, col)

    # ── Graphic tokens (operator character sequences) ─────────────────

    def _read_graphic(self, line: int, col: int) -> None:
        start = self._pos
        while not self._at_end() and self._peek() in _GRAPHIC_CHARS:
            self._advance()
        name = self._src[start:self._pos]

        # Special case: if graphic token is just "." and followed by
        # whitespace/EOF, treat as DOT
        if name == ".":
            nxt = self._peek()
            if nxt == "" or nxt in " \t\n\r" or nxt == "%":
                self._push(TokenType.DOT, ".", line, col)
                return

        self._push(TokenType.ATOM, name, line, col)
