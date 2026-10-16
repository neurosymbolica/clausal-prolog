"""Name the first ISO fault inside a quoted token the lexer refused.

When a quoted atom or string breaks a rule of ISO 6.4.2.1 (an escape outside
the closed set, an octal/hex escape without its closing backslash, a raw
control character), the DFA has no accept for it, and the driver reports a
``no_token`` error at the OPENING quote: ``Unexpected character "'"``. That
is correct but unhelpful. ``quoted_fault`` re-scans the token from the quote
with the same rules as ``specs/iso.toklex.pl`` and returns a message and the
offset of the first offending character, so callers can point at it.

It only refines a diagnosis the lexer has already made. It never decides
whether a token is valid.
"""

from __future__ import annotations

import unicodedata

#: ``symbolic_escape`` in iso.toklex.pl: the characters allowed after a
#: backslash, besides octal digits, ``x`` and a newline.
_SYMBOLIC = frozenset("abfnrtv\\'\"`")
_OCT = frozenset("01234567")
_HEX = frozenset("0123456789abcdefABCDEF")

_KIND = {"'": "quoted atom", '"': "string"}


def quoted_fault(text: str, off: int) -> tuple[str, int] | None:
    """For the quoted token opening at ``text[off]``, return
    ``(message, fault_offset)`` naming its first ISO 6.4.2.1 fault, or
    ``None`` when ``text[off]`` is not a quote or no fault is found before
    the closing quote or the end of the text.

    A raw newline inside the token is reported as the token being
    unterminated, at the opening quote: a quote left open at the end of a
    line is the usual cause.
    """
    q = text[off:off + 1]
    kind = _KIND.get(q)
    if kind is None:
        return None
    fault = _scan(text, off, q, kind)
    if fault is None:
        return None
    msg, at = fault
    if (at == off + 1 and q == "'" and off >= 1 and text[off - 1] == "0"
            and (off < 2 or not (text[off - 2].isalnum() or text[off - 2] in "_."))):
        # `0'` + a bad first character: the lexer backed up to the integer
        # `0` and the quote opened an atom, but the writer meant a char
        # code. (A fault further in is in a real quoted atom: `0'\<newline>`
        # starts one, Ulrich #213.)
        msg = msg.replace(kind, "0' character code")
    return msg, at


def _show_escape(seq: str) -> str:
    """``\\z`` as ``'\\z'``; a backslash before an invisible or control
    character as ``\\ followed by U+0009``."""
    c = seq[1:2]
    if c.isprintable() and not c.isspace():
        return f"'{seq}'"
    return f"\\ followed by U+{ord(c):04X}"


def _scan(text: str, off: int, q: str, kind: str) -> tuple[str, int] | None:
    i, n = off + 1, len(text)
    while i < n:
        c = text[i]
        if c == q:
            if i + 1 < n and text[i + 1] == q:
                i += 2
                continue
            return None
        if c == "\n":
            return f"unterminated {kind}", off
        if c == "\\":
            if i + 1 >= n:
                return None
            e = text[i + 1]
            if e == "\n" or e in _SYMBOLIC:
                i += 2
                continue
            if e in _OCT or e == "x":
                j = i + 2 if e == "x" else i + 1
                digits = _HEX if e == "x" else _OCT
                k = j
                while k < n and text[k] in digits:
                    k += 1
                if k == j:
                    return f"invalid escape sequence {_show_escape(text[i:i + 2])} in {kind}", i
                if k < n and text[k] == "\\":
                    i = k + 1
                    continue
                name = "hex" if e == "x" else "octal"
                return (f"{name} escape '{text[i:k]}' needs a closing backslash "
                        f"in {kind}"), i
            return f"invalid escape sequence {_show_escape(text[i:i + 2])} in {kind}", i
        if unicodedata.category(c) == "Cc":
            return (f"raw control character U+{ord(c):04X} in {kind} "
                    f"(write it as an escape)"), i
        i += 1
    return None
