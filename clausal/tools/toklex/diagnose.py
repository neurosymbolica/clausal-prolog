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
    detail = quoted_fault_detail(text, off)
    if detail is None:
        return None
    return detail.message, detail.at


class QuotedFault:
    """What :func:`quoted_fault_detail` found: the *message* and the
    *at* offset :func:`quoted_fault` returns, and besides them *code* --
    ``newline`` (a raw newline before the closing quote), ``bad_escape``
    (an escape outside the ISO set), ``escape_nodigits`` (``\\x`` with no
    hex digit), ``escape_unclosed`` (an octal or hex escape without its
    closing backslash), ``control`` (a raw control character) -- *found*,
    the offending text itself (the escape, the
    character), and *kind*, the token's kind as the message names it
    (``quoted atom``, ``string`` or ``0' character code``)."""

    __slots__ = ("message", "at", "code", "found", "kind")

    def __init__(self, message, at, code, found, kind):
        self.message = message
        self.at = at
        self.code = code
        self.found = found
        self.kind = kind


def quoted_fault_detail(text: str, off: int) -> QuotedFault | None:
    """:func:`quoted_fault` with the fault's code, offending text and the
    token's kind (a :class:`QuotedFault`), for a caller that maps the
    fault to an error term as well as to a message."""
    q = text[off:off + 1]
    kind = _KIND.get(q)
    if kind is None:
        return None
    fault = _scan(text, off, q, kind)
    if fault is None:
        return None
    msg, at, code, found = fault
    first = at == off + 1 or (code == "newline" and text[off + 1:off + 2] == "\n")
    if (first and q == "'" and off >= 1 and text[off - 1] == "0"
            and (off < 2 or not (text[off - 2].isalnum() or text[off - 2] in "_."))):
        # `0'` + a bad first character: the lexer backed up to the integer
        # `0` and the quote opened an atom, but the writer meant a char
        # code. (A fault further in is in a real quoted atom: `0'\<newline>`
        # starts one, Ulrich #213.)  A newline right after `0'` keeps the
        # "unterminated quoted atom" message -- that is what the lexer saw
        # -- but is a char code's fault for the error term.
        if code != "newline":
            msg = msg.replace(kind, "0' character code")
        kind = "0' character code"
    return QuotedFault(msg, at, code, found, kind)


def _show_escape(seq: str) -> str:
    """``\\z`` as ``'\\z'``; a backslash before an invisible or control
    character as ``\\ followed by U+0009``."""
    c = seq[1:2]
    if c.isprintable() and not c.isspace():
        return f"'{seq}'"
    return f"\\ followed by U+{ord(c):04X}"


def _scan(text: str, off: int, q: str, kind: str) -> tuple | None:
    """``(message, at, code, found)`` of the first fault, or None."""
    i, n = off + 1, len(text)
    while i < n:
        c = text[i]
        if c == q:
            if i + 1 < n and text[i + 1] == q:
                i += 2
                continue
            return None
        if c == "\n":
            return f"unterminated {kind}", off, "newline", "\n"
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
                    # `\x` with no hex digit: an escape left incomplete
                    # rather than one outside the set (`\0`-`\7` cannot
                    # get here: the digit itself is the first octal digit).
                    return (f"invalid escape sequence {_show_escape(text[i:i + 2])} in {kind}",
                            i, "escape_nodigits", text[i:i + 2])
                if k < n and text[k] == "\\":
                    i = k + 1
                    continue
                name = "hex" if e == "x" else "octal"
                return ((f"{name} escape '{text[i:k]}' needs a closing backslash "
                         f"in {kind}"), i, "escape_unclosed", text[i:k])
            return (f"invalid escape sequence {_show_escape(text[i:i + 2])} in {kind}",
                    i, "bad_escape", text[i:i + 2])
        if unicodedata.category(c) == "Cc":
            return ((f"raw control character U+{ord(c):04X} in {kind} "
                     f"(write it as an escape)"), i, "control", c)
        i += 1
    return None
