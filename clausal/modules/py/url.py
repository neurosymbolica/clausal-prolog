"""clausal.modules.py.url — URL utility predicates for Clausal.

Provides relational predicates for URL encoding, decoding, parsing, and joining.
Import via::

    -import_from(py.url, [encode, decode, parse, join])

Wraps Python's ``urllib.parse`` module.
"""

from __future__ import annotations

from clausal.modules.py import (
    ModulePredicate,
    _import_stdlib,
    expect_type,
    note_rejected_call,
    option,
    simple_to_trampoline,
    text_or_str,
    to_text,
)
_urllib_parse = _import_stdlib("urllib.parse")

from clausal.logic.atoms import mint
from clausal.logic.variables import deref, is_var, unify
from clausal.terms import DictTerm


# ── Helpers ─────────────────────────────────────────────────────────────


def _require_text(val, pred, arg):
    """The ``str`` a Url/String argument denotes, or ``None`` (note recorded).

    Spec §9.4: a wrapper that takes text accepts a string or an ATOM, and both
    convert to the same ``str`` -- so ``encode('hello world', E)`` in a
    ``.clausal`` file works exactly as ``"hello world"`` does under
    ``-double_quotes(chars)``.  THE FLIP (2026-09-06-atoms-as-cells-strings)
    made the bare ``expect_type(x, str, ...)`` guards below reject every
    source-written argument, silently: in the default ``-double_quotes(atom)``
    mode a written ``"..."`` IS the arity-0 cell.

    A bound value that is not text keeps this module's existing behaviour --
    a recorded type-mismatch note and a clean failure, not a raise.
    """
    text = to_text(val)
    if text is not None:
        return text
    expect_type(val, str, pred, arg=arg)   # records the note; always False here
    return None


def _port_text(val):
    """The netloc port a Parts dict's ``port`` denotes: an int, or its text.

    ``parse/2`` answers an ``int`` (``0`` meaning "no port"), and a program
    writing a Parts dict by hand writes either an int or a name/string.  Text
    crosses through ``to_text`` (§9.4): ``str(("8080",))`` would have spliced
    ``example.com:('8080',)`` into the netloc.  A port that is neither an int
    nor text answers ``""``, which the caller's ``if port`` treats as absent
    -- dropping a nonsense port rather than pasting its repr into the URL.
    """
    v = deref(val)
    if isinstance(v, int) and not isinstance(v, bool):
        return v
    text = to_text(v)
    return text if text is not None else ""


# ── Predicate implementations ────────────────────────────────────────────


def _encode_2(string, encoded, trail, k):
    """encode/2: encode(String, Encoded) — URL-encode."""
    s = _require_text(deref(string), "encode/2", 1)
    if s is None:
        return
    result = _urllib_parse.quote(s, safe="")
    if unify(encoded, result, trail):
        yield None


def _decode_2(encoded, string, trail, k):
    """decode/2: decode(Encoded, String) — URL-decode."""
    e = _require_text(deref(encoded), "decode/2", 1)
    if e is None:
        return
    result = _urllib_parse.unquote(e)
    if unify(string, result, trail):
        yield None


def _parse_2(url, parts, trail, k):
    """parse/2: parse(Url, Parts) — parse URL into DictTerm.

    Parts is keyed by the ATOMS ``scheme``/``host``/``port``/``path``/
    ``query``/``fragment`` (spec §6.8: a dict written in source has atom
    keys, and an atom key is distinct from the string of the same spelling),
    so ``P.scheme`` reads it and ``join/2`` consumes it unchanged.  The
    VALUES stay text (§9.4).
    """
    u = _require_text(deref(url), "parse/2", 1)
    if u is None:
        return
    try:
        # urlparse itself raises ValueError on e.g. an unclosed IPv6 bracket
        # ("http://[::1"); .port raises on an out-of-range port — both are
        # malformed input and fail cleanly (F017).
        parsed = _urllib_parse.urlparse(u)
        port = parsed.port  # int or None
    except ValueError as exc:
        note_rejected_call("parse/2", exc)
        return
    result = DictTerm({
        mint("scheme"): parsed.scheme,
        mint("host"): parsed.hostname or "",
        mint("port"): port if port is not None else 0,
        mint("path"): parsed.path,
        mint("query"): parsed.query,
        mint("fragment"): parsed.fragment,
    })
    if unify(parts, result, trail):
        yield None


def _join_2(parts, url, trail, k):
    """join/2: join(Parts, Url) — assemble URL from DictTerm parts.

    The parts are read under either spelling of each name (see
    ``modules.py.option``): what ``parse/2`` answers — and what a program
    writes — has ATOM keys (§6.8), while a Python-built ``DictTerm`` in a
    test has ``str`` keys, and the documented ``parse``/``join`` round trip
    has to close over both.

    Every VALUE is text (§9.4), including the ``port``: ``parse/2`` answers
    an int, but a hand-written Parts dict may spell the port as a name, and
    ``str()`` on that atom spliced its tuple repr into the netloc.
    """
    p = deref(parts)
    if not expect_type(p, DictTerm, "join/2", arg=1):
        return
    d = p.data
    scheme = text_or_str(option(d, "scheme", ""))
    host = text_or_str(option(d, "host", ""))
    port = _port_text(option(d, "port", 0))
    path = text_or_str(option(d, "path", ""))
    query = text_or_str(option(d, "query", ""))
    fragment = text_or_str(option(d, "fragment", ""))

    # Build netloc
    if port and port != 0:
        netloc = f"{host}:{port}"
    else:
        netloc = host

    result = _urllib_parse.urlunparse((scheme, netloc, path, "", query, fragment))
    if unify(url, result, trail):
        yield None


# ── Build and export predicate objects ───────────────────────────────────

encode = ModulePredicate("encode")
encode._register(2, simple_to_trampoline(_encode_2))

decode = ModulePredicate("decode")
decode._register(2, simple_to_trampoline(_decode_2))

parse = ModulePredicate("parse")
parse._register(2, simple_to_trampoline(_parse_2))

join = ModulePredicate("join")
join._register(2, simple_to_trampoline(_join_2))
