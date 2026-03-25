"""clausal.modules.py.http — HTTP request predicates for Clausal.

Provides relational predicates for HTTP requests.
Import via::

    -import_from(py.http, [Get, Post, Request, JSONGet, JSONPost])

Primary backend: ``urllib.request`` (stdlib, zero deps).
"""

from __future__ import annotations

from clausal.modules.py import _import_stdlib
_urllib_request = _import_stdlib("urllib.request")
_urllib_error = _import_stdlib("urllib.error")
_urllib_parse = _import_stdlib("urllib.parse")
_json_mod = _import_stdlib("json")

from typing import Callable

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.terms import DictTerm

# JSON conversion helpers from py.json module
from clausal.modules.py.json import _python_to_clausal, _clausal_to_python


# ── Dispatch adapter ──────────────────────────────────────────────────────


class _HttpPredicate:
    """Adapter with ``_get_dispatch()`` for an HTTP predicate."""

    __slots__ = ("_name", "_dispatch_fns")

    def __init__(self, name: str) -> None:
        self._name = name
        self._dispatch_fns: dict[int, Callable] = {}

    def _register(self, arity: int, fn: Callable) -> None:
        self._dispatch_fns[arity] = fn

    def _get_dispatch(self) -> Callable:
        if len(self._dispatch_fns) == 1:
            return next(iter(self._dispatch_fns.values()))
        return self._multi_dispatch

    def _multi_dispatch(self, this_generator, parent, *args):
        arity = len(args) - 1  # exclude trail
        fn = self._dispatch_fns.get(arity)
        if fn is None:
            yield (parent, DONE)
            return
        yield from fn(this_generator, parent, *args)

    def __repr__(self) -> str:
        arities = sorted(self._dispatch_fns)
        return f"http.{self._name}/{arities}"


def _simple_to_trampoline(simple_fn):
    def trampoline_fn(this_generator, parent, *args):
        for _ in simple_fn(*args, None):
            yield (parent, None)
        yield (parent, DONE)
    return trampoline_fn


# ── Internal helpers ─────────────────────────────────────────────────────

# Expose for mocking in tests
_urlopen = _urllib_request.urlopen


def _dict_term_to_headers(dt):
    """Convert a DictTerm to a dict of string headers."""
    if not isinstance(dt, DictTerm):
        return {}
    return {str(k): str(deref(v)) for k, v in dt.data.items()}


def _do_request(url, method="GET", headers=None, data=None, timeout=30):
    """Perform an HTTP request, return (status, body_str) or None on error."""
    if headers is None:
        headers = {}
    data_bytes = None
    if data is not None:
        if isinstance(data, str):
            data_bytes = data.encode("utf-8")
        elif isinstance(data, bytes):
            data_bytes = data
    req = _urllib_request.Request(url, data=data_bytes, method=method)
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with _urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, body
    except _urllib_error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")
        except Exception:
            body = ""
        return e.code, body
    except (OSError, _urllib_error.URLError):
        return None


# ── Predicate implementations ────────────────────────────────────────────


def _get_2(url, body, trail, k):
    """Get/2: Get(Url, Body) — GET request, body as string."""
    url_d = deref(url)
    if is_var(url_d) or not isinstance(url_d, str):
        return
    result = _do_request(url_d)
    if result is None:
        return
    status, body_str = result
    if status >= 400:
        return  # fail on HTTP errors
    if unify(body, body_str, trail):
        yield None


def _get_3(url, headers, body, trail, k):
    """Get/3: Get(Url, Headers, Body) — GET with custom headers."""
    url_d = deref(url)
    headers_d = deref(headers)
    if is_var(url_d) or not isinstance(url_d, str):
        return
    hdrs = _dict_term_to_headers(headers_d) if not is_var(headers_d) else {}
    result = _do_request(url_d, headers=hdrs)
    if result is None:
        return
    status, body_str = result
    if status >= 400:
        return
    if unify(body, body_str, trail):
        yield None


def _post_3(url, data, body, trail, k):
    """Post/3: Post(Url, Data, Body) — POST string data."""
    url_d = deref(url)
    data_d = deref(data)
    if is_var(url_d) or not isinstance(url_d, str):
        return
    if is_var(data_d):
        return
    result = _do_request(url_d, method="POST", data=data_d)
    if result is None:
        return
    status, body_str = result
    if status >= 400:
        return
    if unify(body, body_str, trail):
        yield None


def _post_4(url, data, headers, body, trail, k):
    """Post/4: Post(Url, Data, Headers, Body) — POST with custom headers."""
    url_d = deref(url)
    data_d = deref(data)
    headers_d = deref(headers)
    if is_var(url_d) or not isinstance(url_d, str):
        return
    if is_var(data_d):
        return
    hdrs = _dict_term_to_headers(headers_d) if not is_var(headers_d) else {}
    result = _do_request(url_d, method="POST", data=data_d, headers=hdrs)
    if result is None:
        return
    status, body_str = result
    if status >= 400:
        return
    if unify(body, body_str, trail):
        yield None


def _request_3(options, status_out, body_out, trail, k):
    """Request/3: general request. Options is DictTerm with url, method, headers, data, timeout."""
    opts = deref(options)
    if is_var(opts) or not isinstance(opts, DictTerm):
        return
    url = deref(opts.data.get("url"))
    if url is None or is_var(url) or not isinstance(url, str):
        return
    method = deref(opts.data.get("method", "GET"))
    if is_var(method):
        method = "GET"
    hdrs_raw = opts.data.get("headers")
    hdrs = _dict_term_to_headers(deref(hdrs_raw)) if hdrs_raw is not None else {}
    data_raw = opts.data.get("data")
    data = deref(data_raw) if data_raw is not None else None
    if is_var(data) if data is not None else False:
        data = None
    timeout_raw = opts.data.get("timeout")
    timeout = 30
    if timeout_raw is not None:
        t = deref(timeout_raw)
        if isinstance(t, (int, float)):
            timeout = t
    result = _do_request(url, method=str(method), headers=hdrs, data=data, timeout=timeout)
    if result is None:
        return
    status, body_str = result
    if unify(status_out, status, trail) and unify(body_out, body_str, trail):
        yield None


def _json_get_2(url, term_out, trail, k):
    """JSONGet/2: GET + parse JSON response into DictTerm/list."""
    url_d = deref(url)
    if is_var(url_d) or not isinstance(url_d, str):
        return
    result = _do_request(url_d, headers={"Accept": "application/json"})
    if result is None:
        return
    status, body_str = result
    if status >= 400:
        return
    try:
        parsed = _json_mod.loads(body_str)
    except (ValueError, TypeError):
        return
    term = _python_to_clausal(parsed)
    if unify(term_out, term, trail):
        yield None


def _json_post_3(url, term_in, term_out, trail, k):
    """JSONPost/3: POST JSON body + parse JSON response."""
    url_d = deref(url)
    term_d = deref(term_in)
    if is_var(url_d) or not isinstance(url_d, str):
        return
    if is_var(term_d):
        return
    try:
        json_str = _json_mod.dumps(_clausal_to_python(term_d))
    except (ValueError, TypeError):
        return
    result = _do_request(
        url_d, method="POST", data=json_str,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    if result is None:
        return
    status, body_str = result
    if status >= 400:
        return
    try:
        parsed = _json_mod.loads(body_str)
    except (ValueError, TypeError):
        return
    term = _python_to_clausal(parsed)
    if unify(term_out, term, trail):
        yield None


# ── Build and export predicate objects ───────────────────────────────────

Get = _HttpPredicate("Get")
Get._register(2, _simple_to_trampoline(_get_2))
Get._register(3, _simple_to_trampoline(_get_3))

Post = _HttpPredicate("Post")
Post._register(3, _simple_to_trampoline(_post_3))
Post._register(4, _simple_to_trampoline(_post_4))

Request = _HttpPredicate("Request")
Request._register(3, _simple_to_trampoline(_request_3))

JSONGet = _HttpPredicate("JSONGet")
JSONGet._register(2, _simple_to_trampoline(_json_get_2))

JSONPost = _HttpPredicate("JSONPost")
JSONPost._register(3, _simple_to_trampoline(_json_post_3))
