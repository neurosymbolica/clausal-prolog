"""clausal.modules.py.http — HTTP request predicates for Clausal.

Provides relational predicates for HTTP requests.
Import via::

    -import_from(py.http, [get, post, request, json_get, json_post])

Primary backend: ``urllib.request`` (stdlib, zero deps).
"""

from __future__ import annotations

from clausal.modules.py import (
    text_result,   # stage 1: a str result is the chars carrier
    ModulePredicate,
    _import_stdlib,
    expect_type,
    option,
    raise_domain_error,
    raise_http_status,
    raise_os_error,
    raise_syntax_error,
    require_text,
    simple_to_trampoline,
    text_or_str,
    to_bytes,
    to_text,
)
_urllib_request = _import_stdlib("urllib.request")
_urllib_error = _import_stdlib("urllib.error")
_urllib_parse = _import_stdlib("urllib.parse")
_json_mod = _import_stdlib("json")
_http_client = _import_stdlib("http.client")

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.exceptions import (
    LogicException, instantiation_error, type_error)
from clausal.terms import DictTerm

# JSON conversion helpers from py.json module
from clausal.modules.py.json import _python_to_clausal, _clausal_to_python
from clausal.modules.py.json import _dumps as _json_dumps


# ── Internal helpers ─────────────────────────────────────────────────────

# Expose for mocking in tests
_urlopen = _urllib_request.urlopen


def _dict_term_to_headers(dt):
    """Convert a DictTerm to a dict of string headers."""
    if not isinstance(dt, DictTerm):
        return {}
    # Spec §9.4: a header name or value is a string OR an atom, and both
    # cross as the same ``str`` -- never ``str()``, which would send the
    # arity-0 cell's tuple repr over the wire.
    return {text_or_str(k): text_or_str(deref(v)) for k, v in dt.data.items()}


def _do_request(url, method="GET", headers=None, data=None, timeout=30, *,
                pred="request/3", url_term=None):
    """Perform an HTTP request; return ``(status, raw)``, *raw* the
    response body as BYTES -- or, for an error status whose body could not
    be read, the exception that stopped the read.  :func:`_body_text` turns
    it into text, AFTER the caller has dealt with the status, so an error
    status outranks a body that is not text.

    A URL ``urllib`` cannot use at all -- no scheme, an unknown scheme, a
    malformed host -- is the caller's value, not the network's answer, so it
    raises ``domain_error(url, Url)`` for *pred* (RULED 2026-10-02);
    *url_term* is the term the caller wrote.  A network failure RAISES too
    (RULED 2026-10-02, ``raise_os_error``): a host that does not resolve is
    ``existence_error(source_sink, Url)``, a refused or reset connection
    ``system_error(connection_refused | connection_reset | ...)``, a timeout
    ``resource_error(timeout)``, a TLS failure ``system_error(tls_failure)``,
    a malformed response ``system_error(http_protocol_error)``.  An HTTP
    error STATUS is returned with its body: ``request/3`` answers it as a
    value, the body-only predicates raise it (``raise_http_status``).
    """
    culprit = url if url_term is None else url_term
    if headers is None:
        headers = {}
    data_bytes = None
    if data is not None:
        # Spec §9.4: a request body is TEXT or bytes, and text is a string
        # OR an atom -- ``to_bytes`` is the funnel for exactly that pair.
        data_bytes = to_bytes(data)
    try:
        req = _urllib_request.Request(url, data=data_bytes, method=method)
    except ValueError as e:
        # "unknown url type": no scheme, or a scheme urllib cannot use
        # (F018) -- text that parses but is not a URL a request can use,
        # domain_error(url, U).  Anything else ("Invalid IPv6 URL") is text
        # that does not parse as a URL: syntax_error(invalid_url) (RULED
        # 2026-10-02; it was domain_error(url, U)).
        if str(e).startswith("unknown url type"):
            raise_domain_error("url", culprit, pred, arg=1)
        raise_syntax_error("invalid_url", pred,
                           f"the URL does not parse: {e}", cause=e)
    try:
        for k, v in headers.items():
            req.add_header(k, v)
        with _urlopen(req, timeout=timeout) as resp:
            raw, status = resp.read(), resp.status
    except _urllib_error.HTTPError as e:
        try:
            raw = e.read()
        except Exception as read_exc:     # noqa: BLE001 -- see _body_text
            raw = read_exc               # raised only if the body is asked for
        return e.code, raw
    except _urllib_error.URLError as e:
        if _is_url_rejection(e):
            raise_domain_error("url", culprit, pred, arg=1)
        reason = e.reason
        if not isinstance(reason, OSError):
            reason = OSError(str(reason))      # no errno: system_error(io_error)
        raise_os_error(reason, culprit, pred)
    except ValueError as e:
        # A malformed authority: a non-numeric port (http.client.InvalidURL)
        # or "Invalid IPv6 URL" -- text that does not parse as a URL,
        # syntax_error(invalid_url) (RULED 2026-10-02; it was
        # domain_error(url, U)).  Any other ValueError (a header value with
        # CR/LF) is not the URL's and propagates as itself.
        if (isinstance(e, _http_client.InvalidURL)
                or "IPv6" in str(e)):
            raise_syntax_error("invalid_url", pred,
                               f"the URL does not parse: {e}", cause=e)
        raise
    except _http_client.HTTPException as e:
        if isinstance(e, _http_client.InvalidURL):     # the caller's URL
            raise_syntax_error("invalid_url", pred,
                               f"the URL does not parse: {e}", cause=e)
        if isinstance(e, OSError):             # RemoteDisconnected: a reset
            raise_os_error(e, culprit, pred)
        from clausal.logic.exceptions import system_error  # noqa: PLC0415
        raise LogicException(system_error(
            "http_protocol_error", f"{pred}: {type(e).__name__}: {e}")) from e
    except OSError as e:                       # a timeout while reading, ...
        raise_os_error(e, culprit, pred)
    return status, raw


def _body_text(raw, culprit, pred):
    """The response body *raw* (from :func:`_do_request`) as text.

    A body that is not UTF-8 RAISES ``syntax_error(invalid_data)`` (RULED
    2026-10-02: raise) -- Scryer's term for bytes that are not UTF-8 on a
    text stream.  It used to fail the goal, or, for an error status, read
    as the empty text.  A body whose read failed raises that failure.
    """
    if isinstance(raw, BaseException):
        if isinstance(raw, OSError):
            raise_os_error(raw, culprit, pred)
        from clausal.logic.exceptions import system_error  # noqa: PLC0415
        raise LogicException(system_error(
            "http_protocol_error",
            f"{pred}: {type(raw).__name__}: {raw}")) from raw
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise_syntax_error("invalid_data", pred,
                           f"the response body is not UTF-8 text: {e}",
                           cause=e)


def _json_body(body_str, pred):
    """The response body *body_str* parsed as JSON.  Text that is not JSON
    RAISES ``syntax_error(invalid_json)`` (RULED 2026-10-02: raise); it
    used to fail the goal."""
    try:
        return _json_mod.loads(body_str)
    except ValueError as e:             # json.JSONDecodeError
        raise_syntax_error("invalid_json", pred,
                           f"the response body is not JSON: {e}", cause=e)


def _is_url_rejection(exc) -> bool:
    """Whether a ``URLError`` is urllib refusing the URL itself (a scheme it
    has no handler for, no host) rather than a network failure."""
    reason = getattr(exc, "reason", "")
    return isinstance(reason, str) and (
        reason.startswith("unknown url type") or reason == "no host given")



# ── Predicate implementations ────────────────────────────────────────────


def _get_2(url, body, trail, k):
    """get/2: get(Url, Body) — GET request, body as string."""
    url_d = require_text(deref(url), "get/2")
    if url_d is None:
        return
    result = _do_request(url_d, pred="get/2", url_term=deref(url))
    status, raw = result
    if status >= 400:
        raise_http_status(status, deref(url), "get/2")
    body_str = _body_text(raw, deref(url), "get/2")
    if unify(body, text_result(body_str), trail):
        yield None


def _get_3(url, headers, body, trail, k):
    """get/3: get(Url, Headers, Body) — GET with custom headers."""
    url_d = require_text(deref(url), "get/3")
    headers_d = deref(headers)
    if url_d is None:
        return
    # An unbound Headers still means none; a bound non-dict raises.
    if not is_var(headers_d):
        expect_type(headers_d, DictTerm, "get/3", arg=2)
    hdrs = _dict_term_to_headers(headers_d) if not is_var(headers_d) else {}
    result = _do_request(url_d, headers=hdrs, pred="get/3",
                         url_term=deref(url))
    status, raw = result
    if status >= 400:
        raise_http_status(status, deref(url), "get/3")
    body_str = _body_text(raw, deref(url), "get/3")
    if unify(body, text_result(body_str), trail):
        yield None


def _post_3(url, data, body, trail, k):
    """post/3: post(Url, Data, Body) — POST text or bytes data."""
    url_d = require_text(deref(url), "post/3")
    data_d = deref(data)
    if url_d is None:
        return
    # Data that is neither text (a string or an ATOM, §9.4) nor bytes
    # raises (RULED 2026-10-02) -- it used to send a body-less POST.
    if to_bytes(data_d) is None:
        expect_type(data_d, (str, bytes), "post/3", arg=2)   # raises
    result = _do_request(url_d, method="POST", data=data_d, pred="post/3",
                         url_term=deref(url))
    status, raw = result
    if status >= 400:
        raise_http_status(status, deref(url), "post/3")
    body_str = _body_text(raw, deref(url), "post/3")
    if unify(body, text_result(body_str), trail):
        yield None


def _post_4(url, data, headers, body, trail, k):
    """post/4: post(Url, Data, Headers, Body) — POST with custom headers."""
    url_d = require_text(deref(url), "post/4")
    data_d = deref(data)
    headers_d = deref(headers)
    if url_d is None:
        return
    # See post/3.  An unbound Headers still means none.
    if to_bytes(data_d) is None:
        expect_type(data_d, (str, bytes), "post/4", arg=2)   # raises
    if not is_var(headers_d):
        expect_type(headers_d, DictTerm, "post/4", arg=3)
    hdrs = _dict_term_to_headers(headers_d) if not is_var(headers_d) else {}
    result = _do_request(url_d, method="POST", data=data_d, headers=hdrs,
                         pred="post/4", url_term=deref(url))
    status, raw = result
    if status >= 400:
        raise_http_status(status, deref(url), "post/4")
    body_str = _body_text(raw, deref(url), "post/4")
    if unify(body, text_result(body_str), trail):
        yield None


def _request_3(options, status_out, body_out, trail, k):
    """request/3: general request. Options is DictTerm with url, method, headers, data, timeout.

    Each option is read under either spelling of its name (see
    ``modules.py.option``): a dict written in source has ATOM keys (§6.8),
    so keying this table on ``str`` alone made every source-written options
    dict read as empty.
    """
    opts = deref(options)
    if not expect_type(opts, DictTerm, "request/3", arg=1):
        return
    url_raw = deref(option(opts.data, "url"))
    url = to_text(url_raw) if url_raw is not None else None
    if url is None:
        if url_raw is None:
            # No url key: the options dict is not one request/3 can run.
            raise_domain_error("http_request_options", opts, "request/3",
                               arg=1)
        # Unbound -> instantiation_error; not text -> type_error(text, U).
        expect_type(url_raw, str, "request/3", arg=1)
    method = deref(option(opts.data, "method", "GET"))
    if is_var(method):
        method = text_result("GET")    # a module default is text (review 2026-09-18)
    hdrs_raw = option(opts.data, "headers")
    hdrs = {}
    if hdrs_raw is not None and not is_var(deref(hdrs_raw)):
        # A bound headers option that is not a dict used to be dropped.
        expect_type(deref(hdrs_raw), DictTerm, "request/3", arg=1)
        hdrs = _dict_term_to_headers(deref(hdrs_raw))
    data_raw = option(opts.data, "data")
    data = deref(data_raw) if data_raw is not None else None
    if is_var(data) if data is not None else False:
        data = None
    timeout_raw = option(opts.data, "timeout")
    timeout = 30
    if timeout_raw is not None and not is_var(deref(timeout_raw)):
        # A bound timeout that is not a number used to be ignored, and a
        # negative one failed the request as if the network had.
        t = deref(timeout_raw)
        expect_type(t, (int, float), "request/3", arg=1)
        if t < 0:
            raise_domain_error("not_less_than_zero", t, "request/3", arg=1)
        timeout = t
    result = _do_request(url, method=text_or_str(method), headers=hdrs,
                         data=data, timeout=timeout, pred="request/3",
                         url_term=url_raw)
    status, raw = result
    # The status is a VALUE here, whatever it is; the body must be text.
    body_str = _body_text(raw, url_raw, "request/3")
    if unify(status_out, text_result(status), trail) and unify(body_out, text_result(body_str), trail):
        yield None


def _json_get_2(url, term_out, trail, k):
    """json_get/2: GET + parse JSON response into DictTerm/list."""
    url_d = require_text(deref(url), "json_get/2")
    if url_d is None:
        return
    result = _do_request(url_d, headers={"Accept": "application/json"},
                         pred="json_get/2", url_term=deref(url))
    status, raw = result
    if status >= 400:
        raise_http_status(status, deref(url), "json_get/2")
    parsed = _json_body(_body_text(raw, deref(url), "json_get/2"), "json_get/2")
    term = _python_to_clausal(parsed)
    if unify(term_out, term, trail):
        yield None


def _json_post_3(url, term_in, term_out, trail, k):
    """json_post/3: POST JSON body + parse JSON response."""
    url_d = require_text(deref(url), "json_post/3")
    term_d = deref(term_in)
    if is_var(term_d):
        raise LogicException(instantiation_error("json_post/3: argument 2"))
    # The converter raises for a term with no JSON counterpart
    # (type_error(json_term, _)) or a nested unbound variable.
    json_str = _json_dumps(_clausal_to_python(term_d, "py.http.json_post/3"))
    result = _do_request(
        url_d, method="POST", data=text_result(json_str),   # stage 1: our own text is text
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        pred="json_post/3", url_term=deref(url),
    )
    status, raw = result
    if status >= 400:
        raise_http_status(status, deref(url), "json_post/3")
    parsed = _json_body(_body_text(raw, deref(url), "json_post/3"), "json_post/3")
    term = _python_to_clausal(parsed)
    if unify(term_out, term, trail):
        yield None


# ── Build and export predicate objects ───────────────────────────────────

get = ModulePredicate("get")
get._register(2, simple_to_trampoline(_get_2))
get._register(3, simple_to_trampoline(_get_3))

post = ModulePredicate("post")
post._register(3, simple_to_trampoline(_post_3))
post._register(4, simple_to_trampoline(_post_4))

request = ModulePredicate("request")
request._register(3, simple_to_trampoline(_request_3))

json_get = ModulePredicate("json_get")
json_get._register(2, simple_to_trampoline(_json_get_2))

json_post = ModulePredicate("json_post")
json_post._register(3, simple_to_trampoline(_json_post_3))
