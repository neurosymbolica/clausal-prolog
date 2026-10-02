"""py.http: a response body that is not text, or not JSON, RAISES.

RULED 2026-10-02 ("raise").  Each case below failed the goal before -- or,
for an error status answered by ``request/3``, read the body as the empty
text:

- a body that is not UTF-8 -> ``syntax_error(invalid_data)``, Scryer's
  term for bytes that are not UTF-8 on a text stream (``get_char/2`` on
  such a file throws ``error(syntax_error(invalid_data), get_char/2)``);
- a body ``json_get/2`` / ``json_post/3`` cannot parse as JSON ->
  ``syntax_error(invalid_json)``.

An error STATUS still outranks the body in the body-only predicates, and
``request/3`` still answers a status as a value -- but its body must be
text.  The YAML package's tests live with it
(``packages/clausal-yaml/tests``).

The bodies come from a local ``http.server``; a sandbox that forbids
sockets skips those tests.  The mocked cases need no socket.
"""

from __future__ import annotations

import http.server
import textwrap
import threading
import urllib.error
from io import BytesIO
from unittest.mock import patch

import pytest

from clausal.logic.atoms import mint
from clausal.logic.cells import chars
from clausal.logic.exceptions import LogicException
from clausal.logic.variables import Trail, Var, deref
from clausal.modules.py import http as phttp
from clausal.terms import DictTerm


def _sockets_allowed() -> bool:
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        s.close()
        return True
    except OSError:
        return False


_needs_sockets = pytest.mark.skipif(
    not _sockets_allowed(), reason="the sandbox forbids sockets")


def raised(fn, *args):
    with pytest.raises(LogicException) as info:
        list(fn(*args, Trail(), None))
    return info.value.term


def solutions(fn, *args):
    return list(fn(*args, Trail(), None))


def _err(formal, name, arity):
    return ("error", formal, ("/", name, arity))


def _syntax(kind):
    return ("syntax_error", kind)


_BAD_UTF8 = b"ab\xff\xfecd"

#: path -> (status, body)
_ROUTES = {
    "/bad-utf8": (200, _BAD_UTF8),
    "/bad-utf8-500": (500, _BAD_UTF8),
    "/bad-utf8-404": (404, _BAD_UTF8),
    "/not-json": (200, b"not json {"),
    "/json": (200, b'{"a": 1}'),
}


class _BodyHandler(http.server.BaseHTTPRequestHandler):
    def _answer(self):
        if self.command == "POST":
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
        status, body = _ROUTES[self.path]
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = _answer

    def log_message(self, *args):
        pass


@pytest.fixture
def base():
    server = http.server.HTTPServer(("127.0.0.1", 0), _BodyHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


# ── a body that is not UTF-8 ─────────────────────────────────────────────


@_needs_sockets
def test_body_only_predicates_raise_on_a_non_utf8_body(base):
    u = chars(f"{base}/bad-utf8")
    for fn, args, name, arity in [
        (phttp._get_2, (Var(),), "get", 2),
        (phttp._get_3, (DictTerm({}), Var()), "get", 3),
        (phttp._post_3, (chars("x"), Var()), "post", 3),
        (phttp._post_4, (chars("x"), DictTerm({}), Var()), "post", 4),
        (phttp._json_get_2, (Var(),), "json_get", 2),
        (phttp._json_post_3, (DictTerm({mint("a"): 1}), Var()),
         "json_post", 3),
    ]:
        assert raised(fn, u, *args) == _err(
            _syntax("invalid_data"), name, arity), name


@_needs_sockets
@pytest.mark.parametrize("route", ["/bad-utf8", "/bad-utf8-500"])
def test_request_3_raises_on_a_non_utf8_body_whatever_the_status(base, route):
    # Before: a 200 failed the goal, a 500 answered the body as "".
    opts = DictTerm({mint("url"): chars(f"{base}{route}")})
    assert raised(phttp._request_3, opts, Var(), Var()) == _err(
        _syntax("invalid_data"), "request", 3)


@_needs_sockets
def test_an_error_status_outranks_a_non_utf8_body(base):
    # Guard (passes before and after): the status is the first answer.
    u = chars(f"{base}/bad-utf8-404")
    assert raised(phttp._get_2, u, Var()) == _err(
        ("existence_error", "source_sink", u), "get", 2)
    u = chars(f"{base}/bad-utf8-500")
    assert raised(phttp._json_get_2, u, Var()) == _err(
        ("system_error", ("http_status", 500)), "json_get", 2)


# ── a body that is not JSON ──────────────────────────────────────────────


@_needs_sockets
def test_json_predicates_raise_on_a_body_that_is_not_json(base):
    u = chars(f"{base}/not-json")
    assert raised(phttp._json_get_2, u, Var()) == _err(
        _syntax("invalid_json"), "json_get", 2)
    assert raised(phttp._json_post_3, u, DictTerm({mint("a"): 1}),
                  Var()) == _err(_syntax("invalid_json"), "json_post", 3)


@_needs_sockets
def test_a_json_body_still_answers(base):
    # Guard (passes before and after).
    out = Var()
    assert len(solutions(phttp._json_get_2, chars(f"{base}/json"), out)) == 1
    assert deref(out).data[mint("a")] == 1


# ── mocked: no socket needed ─────────────────────────────────────────────


def _resp(body, status=200):
    from unittest.mock import MagicMock
    r = MagicMock()
    r.read.return_value = body
    r.status = status
    r.__enter__ = lambda s: s
    r.__exit__ = MagicMock(return_value=False)
    return r


@patch("clausal.modules.py.http._urlopen")
def test_mocked_non_utf8_body_raises(mock_urlopen):
    mock_urlopen.return_value = _resp(_BAD_UTF8)
    assert raised(phttp._get_2, chars("http://example.com"), Var()) == _err(
        _syntax("invalid_data"), "get", 2)


@patch("clausal.modules.py.http._urlopen")
def test_mocked_error_status_with_a_non_utf8_body_in_request_3(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.HTTPError(
        "http://example.com", 500, "boom", {}, BytesIO(_BAD_UTF8))
    opts = DictTerm({mint("url"): chars("http://example.com")})
    assert raised(phttp._request_3, opts, Var(), Var()) == _err(
        _syntax("invalid_data"), "request", 3)


@patch("clausal.modules.py.http._urlopen")
def test_mocked_error_body_whose_read_is_reset(mock_urlopen):
    # The read of an error body failing is a network failure: request/3
    # raises it (it used to answer ""); a body-only predicate raises the
    # status, which comes first.
    class _Reset:
        def read(self, *a):
            raise ConnectionResetError(104, "reset")
        def close(self):
            pass
    mock_urlopen.side_effect = urllib.error.HTTPError(
        "http://example.com", 500, "boom", {}, _Reset())
    opts = DictTerm({mint("url"): chars("http://example.com")})
    assert raised(phttp._request_3, opts, Var(), Var()) == _err(
        ("system_error", "connection_reset"), "request", 3)
    mock_urlopen.side_effect = urllib.error.HTTPError(
        "http://example.com", 500, "boom", {}, _Reset())
    assert raised(phttp._get_2, chars("http://example.com"), Var()) == _err(
        ("system_error", ("http_status", 500)), "get", 2)


@patch("clausal.modules.py.http._urlopen")
def test_mocked_body_that_is_not_json_raises(mock_urlopen):
    mock_urlopen.return_value = _resp(b"not json")
    assert raised(phttp._json_get_2, chars("http://example.com"),
                  Var()) == _err(_syntax("invalid_json"), "json_get", 2)


# ── end to end: catch/3 in a program sees the term ───────────────────────


@patch("clausal.modules.py.http._urlopen")
def test_syntax_error_is_catchable_in_a_program(mock_urlopen, tmp_path):
    from clausal.import_hook import _load_module
    from clausal.logic.solve import call
    from tests._suffix import SEAM
    mock_urlopen.return_value = _resp(b"not json")
    p = tmp_path / f"bodycatch{SEAM}"
    p.write_text(textwrap.dedent("""
        -import_from(py.http, [json_get])

        caught(U, K) <- (
            catch(json_get(U, _), error(syntax_error(K), _), true)
        ),
    """).lstrip())
    mod = _load_module("bodycatch", str(p)).__dict__["$module"]
    k = Var()
    sols = [deref(k) for _ in call("caught", chars("http://example.com"), k,
                                   module=mod)]
    assert sols == ["invalid_json"]
