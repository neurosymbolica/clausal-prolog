"""Tests for Phase 7d HTTP and URL modules: py.http, py.url."""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from clausal.logic.atoms import mint
from clausal.logic.cells import chars, chars_text
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.trampoline import DONE
from clausal.terms import DictTerm

from clausal.modules.py.http import (
    get, post, request, json_get, json_post,
    _get_2, _get_3, _post_3, _post_4, _request_3,
    _json_get_2, _json_post_3,
)
from clausal.modules.py.url import (
    encode, decode, parse, join,
    _encode_2, _decode_2, _parse_2, _join_2,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def simple_solutions(fn, *args):
    """Run a simple-mode builtin and collect solutions."""
    trail = Trail()
    results = list(fn(*args, trail, None))
    return results, trail


def raised(fn, *args):
    """The error term a simple-mode builtin raises.  RULED 2026-10-02: an
    argument of the wrong type raises type_error, an unbound required one
    instantiation_error -- neither fails the goal."""
    from clausal.logic.exceptions import LogicException
    with pytest.raises(LogicException) as info:
        list(fn(*args, Trail(), None))
    return info.value.term


def trampoline_solutions(pred, *args):
    """Run a trampoline-protocol predicate and collect solution snapshots."""
    trail = Trail()
    dispatch = pred._get_dispatch()
    gen = dispatch(None, None, None, None, *args, trail)
    solutions = []
    for parent, value in gen:
        if value is DONE:
            break
        solutions.append(value)
    return solutions, trail


def _mock_response(body=b"hello", status=200):
    """Create a mock HTTP response with context manager support."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.status = status
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


# ── get/2,3 ──────────────────────────────────────────────────────────────


class TestHttpGet:

    @patch("clausal.modules.py.http._urlopen")
    def test_get_200(self, mock_urlopen):
        # nv
        mock_urlopen.return_value = _mock_response(b"hello")
        body = Var()
        sols, trail = simple_solutions(_get_2, chars("http://example.com"), body)
        assert len(sols) == 1
        assert deref(body) == chars("hello")

    @patch("clausal.modules.py.http._urlopen")
    def test_get_404_raises_existence_error(self, mock_urlopen):
        # RULED 2026-10-02: an HTTP error status raises (it failed).
        from urllib.error import HTTPError
        mock_urlopen.side_effect = HTTPError(None, 404, "Not Found", {}, None)
        u = chars("http://example.com")
        term = raised(_get_2, u, Var())
        assert term == ('error', ('existence_error', 'source_sink', u),
                        ('/', 'get', 2))

    def test_unbound_url_raises(self):
        # nv
        body = Var()
        term = raised(_get_2, Var(), body)
        assert term == ('error', 'instantiation_error', ('/', 'get', 2))

    @patch("clausal.modules.py.http._urlopen")
    def test_get_with_headers(self, mock_urlopen):
        # nv
        mock_urlopen.return_value = _mock_response(b"ok")
        headers = DictTerm({chars("Authorization"): chars("Bearer token")})
        body = Var()
        sols, trail = simple_solutions(_get_3, chars("http://example.com"), headers, body)
        assert len(sols) == 1
        assert deref(body) == chars("ok")


# ── post/3,4 ─────────────────────────────────────────────────────────────


class TestHttpPost:

    @patch("clausal.modules.py.http._urlopen")
    def test_post_200(self, mock_urlopen):
        # nv
        mock_urlopen.return_value = _mock_response(b"created")
        body = Var()
        sols, trail = simple_solutions(_post_3, chars("http://example.com"), chars("data"), body)
        assert len(sols) == 1
        assert deref(body) == chars("created")

    @patch("clausal.modules.py.http._urlopen")
    def test_post_data_sent(self, mock_urlopen):
        # nv
        mock_urlopen.return_value = _mock_response(b"ok")
        body = Var()
        simple_solutions(_post_3, chars("http://example.com"), chars("payload"), body)
        # Verify the request was created with correct data
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        assert req.data == b"payload"

    @patch("clausal.modules.py.http._urlopen")
    def test_post_with_headers(self, mock_urlopen):
        # nv
        mock_urlopen.return_value = _mock_response(b"ok")
        headers = DictTerm({chars("Content-Type"): chars("text/plain")})
        body = Var()
        sols, _ = simple_solutions(_post_4, chars("http://example.com"), chars("data"), headers, body)
        assert len(sols) == 1

    def test_post_unbound_data_raises(self):
        # nv
        body = Var()
        term = raised(_post_3, chars("http://example.com"), Var(), body)
        assert term == ('error', 'instantiation_error', ('/', 'post', 3))


# ── request/3 ────────────────────────────────────────────────────────────


class TestHttpRequest:

    @patch("clausal.modules.py.http._urlopen")
    def test_returns_status_code(self, mock_urlopen):
        # nv
        mock_urlopen.return_value = _mock_response(b"ok", status=200)
        opts = DictTerm({"url": chars("http://example.com")})
        status = Var()
        body = Var()
        sols, trail = simple_solutions(_request_3, opts, status, body)
        assert len(sols) == 1
        assert deref(status) == 200

    @patch("clausal.modules.py.http._urlopen")
    def test_non_200_still_succeeds(self, mock_urlopen):
        """request/3 does NOT fail on 4xx/5xx — returns status code."""
        # nv
        from urllib.error import HTTPError
        import io
        err = HTTPError(None, 500, "Server Error", {}, io.BytesIO(b"error"))
        mock_urlopen.side_effect = err
        opts = DictTerm({"url": chars("http://example.com")})
        status = Var()
        body = Var()
        sols, trail = simple_solutions(_request_3, opts, status, body)
        assert len(sols) == 1
        assert deref(status) == 500


# ── json_get/2, json_post/3 ────────────────────────────────────────────────


class TestHttpJson:

    @patch("clausal.modules.py.http._urlopen")
    def test_json_get_parses_dict(self, mock_urlopen):
        # nv
        mock_urlopen.return_value = _mock_response(b'{"key": "value"}')
        term = Var()
        sols, trail = simple_solutions(_json_get_2, chars("http://example.com/api"), term)
        assert len(sols) == 1
        result = deref(term)
        assert isinstance(result, DictTerm)
        # spec §9.2: JSON object keys parse as ATOMS; string values stay strings.
        assert result.data[mint("key")] == chars("value")

    @patch("clausal.modules.py.http._urlopen")
    def test_json_get_parses_list(self, mock_urlopen):
        # nv
        mock_urlopen.return_value = _mock_response(b'[1, 2, 3]')
        term = Var()
        sols, trail = simple_solutions(_json_get_2, chars("http://example.com/api"), term)
        assert len(sols) == 1
        assert deref(term) == [1, 2, 3]

    @patch("clausal.modules.py.http._urlopen")
    def test_json_post_serializes_and_parses(self, mock_urlopen):
        # nv
        mock_urlopen.return_value = _mock_response(b'{"status": "ok"}')
        payload = DictTerm({"name": chars("test")})
        result = Var()
        sols, trail = simple_solutions(_json_post_3, chars("http://example.com/api"), payload, result)
        assert len(sols) == 1
        r = deref(result)
        assert isinstance(r, DictTerm)
        assert r.data[mint("status")] == chars("ok")

    @patch("clausal.modules.py.http._urlopen")
    def test_invalid_json_raises_syntax_error(self, mock_urlopen):
        # nv
        # RULED 2026-10-02: a body that is not JSON raises
        # syntax_error(invalid_json) (it used to fail the goal).
        mock_urlopen.return_value = _mock_response(b"not json")
        assert raised(_json_get_2, chars("http://example.com"), Var()) == (
            "error", ("syntax_error", "invalid_json"), ("/", "json_get", 2))


# ── URL encode/decode ────────────────────────────────────────────────────


class TestUrlEncode:

    def test_encode_special_chars(self):
        """encode("hello world", E) → "hello%20world"."""
        # nv
        e = Var()
        sols, trail = simple_solutions(_encode_2, chars("hello world"), e)
        assert len(sols) == 1
        assert deref(e) == chars("hello%20world")

    def test_encode_preserves_safe(self):
        """encode encodes everything (safe="")."""
        # nv
        e = Var()
        simple_solutions(_encode_2, chars("a/b"), e)
        assert deref(e) == chars("a%2Fb")

    def test_decode(self):
        # nv
        s = Var()
        sols, trail = simple_solutions(_decode_2, chars("hello%20world"), s)
        assert len(sols) == 1
        assert deref(s) == chars("hello world")

    def test_round_trip(self):
        # nv
        e = Var()
        s = Var()
        simple_solutions(_encode_2, chars("test value&more"), e)
        simple_solutions(_decode_2, deref(e), s)
        assert deref(s) == chars("test value&more")

    def test_unbound_raises(self):
        # nv
        term = raised(_encode_2, Var(), Var())
        assert term == ('error', 'instantiation_error', ('/', 'encode', 2))


# ── URL parse/join ───────────────────────────────────────────────────────


class TestUrlParse:

    def test_parse_full_url(self):
        """parse("https://example.com:8080/path?q=1#frag", P) → DictTerm."""
        # nv
        p = Var()
        sols, trail = simple_solutions(_parse_2, chars("https://example.com:8080/path?q=1#frag"), p)
        assert len(sols) == 1
        result = deref(p)
        assert isinstance(result, DictTerm)
        # Task 12c: the parts dict is built for SOURCE, so its keys are
        # ATOMS (§6.8) — ``P.scheme`` looks up ``("scheme",)``.  The values
        # stay text (§9.4).
        assert result.data[mint("scheme")] == chars("https")
        assert result.data[mint("host")] == chars("example.com")
        assert result.data[mint("port")] == 8080
        assert result.data[mint("path")] == chars("/path")
        assert result.data[mint("query")] == chars("q=1")
        assert result.data[mint("fragment")] == chars("frag")

    def test_parse_simple_url(self):
        # nv
        p = Var()
        sols, _ = simple_solutions(_parse_2, chars("http://example.com"), p)
        assert len(sols) == 1
        result = deref(p)
        assert result.data[mint("scheme")] == chars("http")
        assert result.data[mint("host")] == chars("example.com")

    def test_unbound_raises(self):
        # nv
        term = raised(_parse_2, Var(), Var())
        assert term == ('error', 'instantiation_error', ('/', 'parse', 2))


class TestUrlJoin:

    def test_join_basic(self):
        # nv
        parts = DictTerm({
            "scheme": chars("https"),
            "host": chars("example.com"),
            "port": 8080,
            "path": chars("/path"),
            "query": chars("q=1"),
            "fragment": chars("frag"),
        })
        url = Var()
        sols, trail = simple_solutions(_join_2, parts, url)
        assert len(sols) == 1
        assert deref(url) == chars("https://example.com:8080/path?q=1#frag")

    def test_join_no_port(self):
        # nv
        parts = DictTerm({
            "scheme": chars("http"),
            "host": chars("example.com"),
            "port": 0,
            "path": chars("/"),
            "query": chars(""),
            "fragment": chars(""),
        })
        url = Var()
        sols, trail = simple_solutions(_join_2, parts, url)
        assert len(sols) == 1
        assert "example.com" in chars_text(deref(url))

    def test_unbound_raises(self):
        # nv
        term = raised(_join_2, Var(), Var())
        assert term == ('error', 'instantiation_error', ('/', 'join', 2))


# ── Task 12c: the URL parts dict is keyed by ATOMS (spec §6.8) ──────────


class TestUrlPartsKeysAreAtoms:
    """``parse/2`` builds the parts dict and ``join/2`` consumes one, so both
    halves have to agree on what a key is.  While ``parse`` emitted ``str``
    keys, ``P.scheme`` raised ``existence_error(dict_key, scheme)`` and a
    source-written parts dict (atom keys, §6.8) joined to an empty URL —
    silently, because every part defaulted to ``""``."""

    def test_parse_emits_exactly_the_atom_key_set(self):
        # nv
        p = Var()
        sols, _ = simple_solutions(_parse_2, chars("https://example.com/x"), p)
        assert len(sols) == 1
        assert set(deref(p).data) == {
            mint("scheme"), mint("host"), mint("port"),
            mint("path"), mint("query"), mint("fragment")}

    def test_join_reads_an_atom_keyed_dict_with_atom_values(self):
        # nv
        parts = DictTerm({
            mint("scheme"): mint("https"),
            mint("host"): mint("example.com"),
            mint("port"): 8080,
            mint("path"): mint("/api"),
        })
        url = Var()
        sols, _ = simple_solutions(_join_2, parts, url)
        assert len(sols) == 1
        # ``str(("https",))`` would have spliced a tuple repr into the URL.
        assert deref(url) == chars("https://example.com:8080/api")

    def test_parse_join_round_trip(self):
        # nv
        p, url = Var(), Var()
        sols, _ = simple_solutions(
            _parse_2, chars("https://example.com:8080/path?q=1#frag"), p)
        assert len(sols) == 1
        sols, _ = simple_solutions(_join_2, deref(p), url)
        assert len(sols) == 1
        assert deref(url) == chars("https://example.com:8080/path?q=1#frag")


# ── Task 12b: atoms in the text and option positions (spec §9.4) ─────────


class TestAtomArguments:
    """A wrapper that takes text accepts a string OR an ATOM (spec §9.4).

    ``py.http`` was migrated onto ``to_text`` for header names and values
    only; the URL, the method and the whole ``request/3`` options dict still
    gated on ``isinstance(x, str)`` / looked options up under ``str`` keys.
    A source-written ``get("http://…", B)`` is an ATOM in the default
    ``-double_quotes(atom)`` mode, and a source-written options dict has
    ATOM keys (§6.8), so both silently failed.
    """

    @patch("clausal.modules.py.http._urlopen")
    def test_get_accepts_an_atom_url(self, mock_urlopen):
        # nv
        mock_urlopen.return_value = _mock_response(b"hello")
        body = Var()
        sols, _ = simple_solutions(_get_2, mint("http://example.com"), body)
        assert len(sols) == 1
        assert deref(body) == chars("hello")
        # The URL reached urllib as text, not as a tuple repr.
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://example.com"

    @patch("clausal.modules.py.http._urlopen")
    def test_request_reads_a_string_keyed_options_dict(self, mock_urlopen):
        """``{"url": ...}`` written in a module that declares no mode has
        chars-carrier keys (the default is chars since 2026-09-26); the
        option lookup matches them by text, as docs/http.md says."""
        mock_urlopen.return_value = _mock_response(b"ok")
        status, body = Var(), Var()
        opts = DictTerm({
            chars("url"): chars("http://example.com/s"),
            chars("method"): chars("POST"),
            chars("timeout"): 5,
        })
        sols, _ = simple_solutions(_request_3, opts, status, body)
        assert len(sols) == 1
        assert deref(body) == chars("ok")
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://example.com/s"
        assert req.get_method() == "POST"

    @patch("clausal.modules.py.http._urlopen")
    def test_request_reads_an_atom_keyed_options_dict(self, mock_urlopen):
        # nv
        mock_urlopen.return_value = _mock_response(b"ok")
        status, body = Var(), Var()
        opts = DictTerm({
            mint("url"): mint("http://example.com/a"),
            mint("method"): mint("POST"),
            mint("headers"): DictTerm({mint("X-Tag"): mint("t12b")}),
            mint("data"): mint("payload"),
            mint("timeout"): 5,
        })
        sols, _ = simple_solutions(_request_3, opts, status, body)
        assert len(sols) == 1
        assert deref(body) == chars("ok")
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://example.com/a"
        assert req.get_method() == "POST"
        assert req.data == b"payload"
        assert req.get_header("X-tag") == "t12b"

    @patch("clausal.modules.py.http._urlopen")
    def test_post_accepts_an_atom_body(self, mock_urlopen):
        # nv
        mock_urlopen.return_value = _mock_response(b"ok")
        body = Var()
        sols, _ = simple_solutions(
            _post_3, mint("http://example.com"), mint("payload"), body)
        assert len(sols) == 1
        assert mock_urlopen.call_args[0][0].data == b"payload"
