"""Colour schemes for the ``?-`` top-level's answers.

A scheme is a predicate over the answer text: it returns the text with ANSI
colour escapes in it.  The top-level cycles through :data:`SCHEMES` on a key
(``c`` at the answer prompt, F2 or Ctrl-X c at ``?-``).

* ``off`` -- the text as it is.
* ``variables`` -- each variable name has one colour, wherever it appears:
  the name is hashed (BLAKE2b, salted so that the common one-letter names
  get different colours; it is the same in every process and every session)
  into a palette of 24 colours that read on a dark and on a light
  background.

``CLAUSAL_COLOUR`` (a scheme name) sets the scheme a session starts with.
"""
from __future__ import annotations

import hashlib
import re

#: xterm-256 colours that are bright enough on a dark background and still
#: readable on a light one, spread around the hue circle.
PALETTE: tuple[int, ...] = (
    203, 209, 215, 221,       # red, orange, amber, yellow
    191, 155, 119, 84,        # lime to green
    48, 50, 45, 39,           # sea green to cyan
    75, 111, 105, 141,        # blues
    177, 171, 213, 207,       # violet to pink
    174, 180, 150, 110,       # muted rose, sand, sage, steel
)

#: Chosen so that the common one-letter names (A-H, L, N, R, X-Z) land on
#: different colours: no two of them share one.
_SALT = (2736).to_bytes(2, "big")

RESET = "\x1b[0m"

# What the answer text is made of, for painting variables only: quoted
# atoms and strings and character codes are left alone, numbers are
# skipped whole (``1.0e10``), and what remains of a name starting with a
# capital letter or ``_`` is a variable.
_TOKEN = re.compile(
    r"""'(?:[^'\\]|\\.|'')*'"""            # quoted atom
    r'''|"(?:[^"\\]|\\.|"")*"'''           # string
    r"""|`(?:[^`\\]|\\.)*`"""              # back-quoted
    r"""|0'(?:\\.|''|.)"""                 # character code
    r"""|\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?"""   # number
    r"""|[A-Za-z_][A-Za-z0-9_]*""",        # name
    re.S)


def colour_of(name: str) -> int:
    """The palette colour of the variable *name*: a stable hash of it."""
    digest = hashlib.blake2b(name.encode("utf-8"), digest_size=4,
                             salt=_SALT).digest()
    return PALETTE[int.from_bytes(digest, "big") % len(PALETTE)]


def paint_variables(text: str) -> str:
    """*text* with each variable name in its own colour."""
    def paint(m: "re.Match[str]") -> str:
        tok = m.group(0)
        if tok[0].isupper() or tok[0] == "_":
            return f"\x1b[38;5;{colour_of(tok)}m{tok}{RESET}"
        return tok
    return _TOKEN.sub(paint, text)


def _plain(text: str) -> str:
    return text


class Scheme:
    """A named colouring predicate over answer text."""

    __slots__ = ("name", "paint")

    def __init__(self, name: str, paint):
        self.name = name
        self.paint = paint


#: The schemes the key cycles through, in order.
SCHEMES: tuple[Scheme, ...] = (
    Scheme("off", _plain),
    Scheme("variables", paint_variables),
)


def scheme_named(name: str) -> int:
    """The index in :data:`SCHEMES` of the scheme called *name* (0 = off if
    there is none)."""
    for i, s in enumerate(SCHEMES):
        if s.name == name.strip().lower():
            return i
    return 0
