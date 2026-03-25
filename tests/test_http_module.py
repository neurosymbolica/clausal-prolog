"""Tests for Phase 7d HTTP and URL modules: py.http, py.url."""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.trampoline import DONE
from clausal.terms import DictTerm

from clausal.modules.py.http import (
    Get, Post, Request, JSONGet, JSONPost,
    _get_2, _get_3, _post_3, _post_4, _request_3,
    _json_get_2, _json_post_3,
)
from clausal.modules.py.url import (
    Encode, Decode, Parse, Join,
    _encode_2, _decode_2, _parse_2, _join_2,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def simple_solutions(fn, *args):
    """Run a simple-mode builtin and collect solutions."""
    trail = Trail()
    results = list(fn(*args, trail, None))
    return results, trail


def trampoline_solutions(pred, *args):
    """Run a trampoline-protocol predicate and collect solution snapshots."""
    trail = Trail()
    dispatch = pred._get_dispatch()
    gen = dispatch(None, None, *args, trail)
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


# ── Get/2,3 ──────────────────────────────────────────────────────────────


class TestHttpGet:

    @patch("clausal.modules.py.http._urlopen")
    def test_get_200(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(b"hello")
        body = Var()
        sols, trail = simple_solutions(_get_2, "http://example.com", body)
        assert len(sols) == 1
        assert deref(body) == "hello"

    @patch("clausal.modules.py.http._urlopen")
    def test_get_404_fails(self, mock_urlopen):
        from urllib.error import HTTPError
        mock_urlopen.side_effect = HTTPError(None, 404, "Not Found", {}, None)
        body = Var()
        sols, _ = simple_solutions(_get_2, "http://example.com", body)
        assert len(sols) == 0

    def test_unbound_url_fails(self):
        body = Var()
        sols, _ = simple_solutions(_get_2, Var(), body)
        assert len(sols) == 0

    @patch("clausal.modules.py.http._urlopen")
    def test_get_with_headers(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(b"ok")
        headers = DictTerm({"Authorization": "Bearer token"})
        body = Var()
        sols, trail = simple_solutions(_get_3, "http://example.com", headers, body)
        assert len(sols) == 1
        assert deref(body) == "ok"


# ── Post/3,4 ─────────────────────────────────────────────────────────────


class TestHttpPost:

    @patch("clausal.modules.py.http._urlopen")
    def test_post_200(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(b"created")
        body = Var()
        sols, trail = simple_solutions(_post_3, "http://example.com", "data", body)
        assert len(sols) == 1
        assert deref(body) == "created"

    @patch("clausal.modules.py.http._urlopen")
    def test_post_data_sent(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(b"ok")
        body = Var()
        simple_solutions(_post_3, "http://example.com", "payload", body)
        # Verify the request was created with correct data
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        assert req.data == b"payload"

    @patch("clausal.modules.py.http._urlopen")
    def test_post_with_headers(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(b"ok")
        headers = DictTerm({"Content-Type": "text/plain"})
        body = Var()
        sols, _ = simple_solutions(_post_4, "http://example.com", "data", headers, body)
        assert len(sols) == 1

    def test_post_unbound_data_fails(self):
        body = Var()
        sols, _ = simple_solutions(_post_3, "http://example.com", Var(), body)
        assert len(sols) == 0


# ── Request/3 ────────────────────────────────────────────────────────────


class TestHttpRequest:

    @patch("clausal.modules.py.http._urlopen")
    def test_returns_status_code(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(b"ok", status=200)
        opts = DictTerm({"url": "http://example.com"})
        status = Var()
        body = Var()
        sols, trail = simple_solutions(_request_3, opts, status, body)
        assert len(sols) == 1
        assert deref(status) == 200

    @patch("clausal.modules.py.http._urlopen")
    def test_non_200_still_succeeds(self, mock_urlopen):
        """Request/3 does NOT fail on 4xx/5xx — returns status code."""
        from urllib.error import HTTPError
        import io
        err = HTTPError(None, 500, "Server Error", {}, io.BytesIO(b"error"))
        mock_urlopen.side_effect = err
        opts = DictTerm({"url": "http://example.com"})
        status = Var()
        body = Var()
        sols, trail = simple_solutions(_request_3, opts, status, body)
        assert len(sols) == 1
        assert deref(status) == 500


# ── JSONGet/2, JSONPost/3 ────────────────────────────────────────────────


class TestHttpJson:

    @patch("clausal.modules.py.http._urlopen")
    def test_json_get_parses_dict(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(b'{"key": "value"}')
        term = Var()
        sols, trail = simple_solutions(_json_get_2, "http://example.com/api", term)
        assert len(sols) == 1
        result = deref(term)
        assert isinstance(result, DictTerm)
        assert result.data["key"] == "value"

    @patch("clausal.modules.py.http._urlopen")
    def test_json_get_parses_list(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(b'[1, 2, 3]')
        term = Var()
        sols, trail = simple_solutions(_json_get_2, "http://example.com/api", term)
        assert len(sols) == 1
        assert deref(term) == [1, 2, 3]

    @patch("clausal.modules.py.http._urlopen")
    def test_json_post_serializes_and_parses(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(b'{"status": "ok"}')
        payload = DictTerm({"name": "test"})
        result = Var()
        sols, trail = simple_solutions(_json_post_3, "http://example.com/api", payload, result)
        assert len(sols) == 1
        r = deref(result)
        assert isinstance(r, DictTerm)
        assert r.data["status"] == "ok"

    @patch("clausal.modules.py.http._urlopen")
    def test_invalid_json_fails(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response(b"not json")
        term = Var()
        sols, _ = simple_solutions(_json_get_2, "http://example.com", term)
        assert len(sols) == 0


# ── URL Encode/Decode ────────────────────────────────────────────────────


class TestUrlEncode:

    def test_encode_special_chars(self):
        """Encode("hello world", E) → "hello%20world"."""
        e = Var()
        sols, trail = simple_solutions(_encode_2, "hello world", e)
        assert len(sols) == 1
        assert deref(e) == "hello%20world"

    def test_encode_preserves_safe(self):
        """Encode encodes everything (safe="")."""
        e = Var()
        simple_solutions(_encode_2, "a/b", e)
        assert deref(e) == "a%2Fb"

    def test_decode(self):
        s = Var()
        sols, trail = simple_solutions(_decode_2, "hello%20world", s)
        assert len(sols) == 1
        assert deref(s) == "hello world"

    def test_round_trip(self):
        e = Var()
        s = Var()
        simple_solutions(_encode_2, "test value&more", e)
        simple_solutions(_decode_2, deref(e), s)
        assert deref(s) == "test value&more"

    def test_unbound_fails(self):
        sols, _ = simple_solutions(_encode_2, Var(), Var())
        assert len(sols) == 0


# ── URL Parse/Join ───────────────────────────────────────────────────────


class TestUrlParse:

    def test_parse_full_url(self):
        """Parse("https://example.com:8080/path?q=1#frag", P) → DictTerm."""
        p = Var()
        sols, trail = simple_solutions(_parse_2, "https://example.com:8080/path?q=1#frag", p)
        assert len(sols) == 1
        result = deref(p)
        assert isinstance(result, DictTerm)
        assert result.data["scheme"] == "https"
        assert result.data["host"] == "example.com"
        assert result.data["port"] == 8080
        assert result.data["path"] == "/path"
        assert result.data["query"] == "q=1"
        assert result.data["fragment"] == "frag"

    def test_parse_simple_url(self):
        p = Var()
        sols, _ = simple_solutions(_parse_2, "http://example.com", p)
        assert len(sols) == 1
        result = deref(p)
        assert result.data["scheme"] == "http"
        assert result.data["host"] == "example.com"

    def test_unbound_fails(self):
        sols, _ = simple_solutions(_parse_2, Var(), Var())
        assert len(sols) == 0


class TestUrlJoin:

    def test_join_basic(self):
        parts = DictTerm({
            "scheme": "https",
            "host": "example.com",
            "port": 8080,
            "path": "/path",
            "query": "q=1",
            "fragment": "frag",
        })
        url = Var()
        sols, trail = simple_solutions(_join_2, parts, url)
        assert len(sols) == 1
        assert deref(url) == "https://example.com:8080/path?q=1#frag"

    def test_join_no_port(self):
        parts = DictTerm({
            "scheme": "http",
            "host": "example.com",
            "port": 0,
            "path": "/",
            "query": "",
            "fragment": "",
        })
        url = Var()
        sols, trail = simple_solutions(_join_2, parts, url)
        assert len(sols) == 1
        assert "example.com" in deref(url)

    def test_unbound_fails(self):
        sols, _ = simple_solutions(_join_2, Var(), Var())
        assert len(sols) == 0
