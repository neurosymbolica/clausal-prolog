"""clausal.modules.py.url — URL utility predicates for Clausal.

Provides relational predicates for URL encoding, decoding, parsing, and joining.
Import via::

    -import_from(py.url, [encode, decode, parse, join])

Wraps Python's ``urllib.parse`` module.
"""

from __future__ import annotations

from clausal.modules.py import _import_stdlib, ModulePredicate, simple_to_trampoline
_urllib_parse = _import_stdlib("urllib.parse")

from clausal.logic.variables import deref, is_var, unify
from clausal.terms import DictTerm


# ── Predicate implementations ────────────────────────────────────────────


def _encode_2(string, encoded, trail, k):
    """encode/2: encode(String, Encoded) — URL-encode."""
    s = deref(string)
    if is_var(s) or not isinstance(s, str):
        return
    result = _urllib_parse.quote(s, safe="")
    if unify(encoded, result, trail):
        yield None


def _decode_2(encoded, string, trail, k):
    """decode/2: decode(Encoded, String) — URL-decode."""
    e = deref(encoded)
    if is_var(e) or not isinstance(e, str):
        return
    result = _urllib_parse.unquote(e)
    if unify(string, result, trail):
        yield None


def _parse_2(url, parts, trail, k):
    """parse/2: parse(Url, Parts) — parse URL into DictTerm."""
    u = deref(url)
    if is_var(u) or not isinstance(u, str):
        return
    try:
        # urlparse itself raises ValueError on e.g. an unclosed IPv6 bracket
        # ("http://[::1"); .port raises on an out-of-range port — both are
        # malformed input and fail cleanly (F017).
        parsed = _urllib_parse.urlparse(u)
        port = parsed.port  # int or None
    except ValueError:
        return
    result = DictTerm({
        "scheme": parsed.scheme,
        "host": parsed.hostname or "",
        "port": port if port is not None else 0,
        "path": parsed.path,
        "query": parsed.query,
        "fragment": parsed.fragment,
    })
    if unify(parts, result, trail):
        yield None


def _join_2(parts, url, trail, k):
    """join/2: join(Parts, Url) — assemble URL from DictTerm parts."""
    p = deref(parts)
    if is_var(p) or not isinstance(p, DictTerm):
        return
    d = p.data
    scheme = str(deref(d.get("scheme", "")))
    host = str(deref(d.get("host", "")))
    port = deref(d.get("port", 0))
    path = str(deref(d.get("path", "")))
    query = str(deref(d.get("query", "")))
    fragment = str(deref(d.get("fragment", "")))

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
