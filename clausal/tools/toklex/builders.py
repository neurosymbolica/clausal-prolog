"""ISO value builders for toklex tokens.

Each builder is a ``Callable[[str], object]`` taking a token's raw
*lexeme* (the exact matched text) and returning the value the token
should carry (``Tok.value``). The default builder (used when a token
rule declares no ``value(...)`` builder, or the driver is given no
override) is ``lexeme`` -- identity.

The escape-decoding logic here is a deliberate bit-parity mirror of
``clausal.tools.prolog_tokenizer.Tokenizer._read_escape`` /
``_SIMPLE_ESCAPES`` (ISO 6.4.2 quoted-token escapes): simple map incl.
``\\e`` and ``\\s``, ``\\x...\\`` hex (closing backslash optional),
``\\NNN\\`` octal (closing backslash optional), doubled delimiter,
``\\<newline>`` removed (line continuation), and an unknown escape kept
verbatim as backslash+char (lenient -- the tokenizer never raises on
this path; malformed escapes at the far end of input are a driver-level
'unterminated'/'no_token' error, not a builder concern).
"""

from __future__ import annotations

_SIMPLE_ESCAPES = {
    "a": "\a", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t",
    "v": "\v", "e": "\x1b", "s": " ", "\\": "\\", "'": "'", '"': '"',
    "`": "`",
}

_HEX_DIGITS = set("0123456789abcdefABCDEF")
_OCT_DIGITS = set("01234567")


def _decode_escape(s: str, i: int) -> tuple[str, int]:
    """Decode one escape sequence from `s` starting at index `i`, where
    `s[i]` is the character right after the backslash. Returns
    (decoded_text, next_index). `decoded_text` is '' for a line
    continuation (the backslash-newline is simply removed)."""
    nxt = s[i]
    if nxt == "\n":
        return "", i + 1
    if nxt == "x":
        j = i + 1
        digits = ""
        while j < len(s) and s[j] in _HEX_DIGITS:
            digits += s[j]
            j += 1
        if not digits:
            return "\\x", i + 1
        if j < len(s) and s[j] == "\\":
            j += 1  # optional closing backslash
        return chr(int(digits, 16)), j
    if nxt in _OCT_DIGITS:
        j = i + 1
        digits = nxt
        while j < len(s) and s[j] in _OCT_DIGITS:
            digits += s[j]
            j += 1
        if j < len(s) and s[j] == "\\":
            j += 1  # optional closing backslash
        return chr(int(digits, 8)), j
    mapped = _SIMPLE_ESCAPES.get(nxt)
    if mapped is not None:
        return mapped, i + 1
    # Unknown escape: keep the backslash and the char (lenient).
    return "\\" + nxt, i + 1


def _decode_quoted(inner: str, quote_char: str) -> str:
    """Decode the body (delimiters already stripped) of a quoted-atom or
    string lexeme: doubled `quote_char` -> literal, backslash -> ISO
    escape, else literal char."""
    out: list[str] = []
    i, n = 0, len(inner)
    while i < n:
        ch = inner[i]
        if ch == quote_char:
            if i + 1 < n and inner[i + 1] == quote_char:
                out.append(quote_char)
                i += 2
            else:
                out.append(quote_char)
                i += 1
        elif ch == "\\":
            decoded, i = _decode_escape(inner, i + 1)
            out.append(decoded)
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def quoted_atom_val(lexeme: str) -> str:
    """Strip the surrounding `'...'` and decode ISO 6.4.2 escapes."""
    return _decode_quoted(lexeme[1:-1], "'")


def string_val(lexeme: str) -> str:
    """Strip the surrounding `"..."` and decode ISO 6.4.2 escapes."""
    return _decode_quoted(lexeme[1:-1], '"')


def int_10(lexeme: str) -> int:
    return int(lexeme.replace("_", ""))


def _strip_prefix(lexeme: str, prefix: str) -> str:
    return lexeme[2:] if lexeme[:2].lower() == prefix else lexeme


def int_16(lexeme: str) -> int:
    return int(_strip_prefix(lexeme, "0x").replace("_", ""), 16)


def int_8(lexeme: str) -> int:
    return int(_strip_prefix(lexeme, "0o").replace("_", ""), 8)


def int_2(lexeme: str) -> int:
    return int(_strip_prefix(lexeme, "0b").replace("_", ""), 2)


def float_of(lexeme: str) -> float:
    return float(lexeme.replace("_", ""))


def char_code(lexeme: str) -> int:
    """Decode `0'c` (incl. `0'''` -> 39 and `0'\\n`-style escapes) to its
    character code, mirroring `prolog_tokenizer._read_number`'s `0'`
    branch."""
    body = lexeme[2:]  # strip the leading "0'"
    ch = body[0]
    if ch == "\\":
        decoded, _ = _decode_escape(body, 1)
        return ord(decoded) if decoded else 0
    if ch == "'" and len(body) > 1 and body[1] == "'":
        return ord("'")
    return ord(ch)


def lexeme(text: str) -> str:
    """Identity builder: the value is the lexeme itself."""
    return text


ISO_BUILDERS: dict[str, object] = {
    "quoted_atom_val": quoted_atom_val,
    "string_val": string_val,
    "int_10": int_10,
    "int_16": int_16,
    "int_8": int_8,
    "int_2": int_2,
    "float_of": float_of,
    "char_code": char_code,
    "lexeme": lexeme,
}
