# Clausal Prolog — HTTP & URL Modules (`http`, `url`)

!!! note "Clausal Prolog examples"

    Examples on this page are [Clausal Prolog](clausal_prolog.md)
    (`.clausal`), which uses ISO Prolog syntax. Clausal Prolog reaches
    Python only through a `.seam` module, so it imports these modules
    through their facades `library(http)` and `library(url)`; the
    [seam](syntax.md) imports `py.http` and `py.url` directly
    (`-import_from(py.http, [...])`).

## Overview

Two modules for HTTP requests and URL manipulation, wrapping Python's `urllib`
stdlib. Zero third-party dependencies.

```clausal
:- use_module(library(http), [get/2, json_get/2, post/3, request/3]).
:- use_module(library(url), [encode/2, decode/2, parse/2, join/2]).

fetch_page(URL, BODY) :-
    get(URL, BODY).

fetch_api(URL, DATA) :-
    json_get(URL, DATA).
```

Or import the whole module and qualify each call with the module name:

```clausal
:- use_module(library(http)).

page(BODY) :-
    http:get("http://example.com", BODY).
```

The seam can also drive such a predicate from Python code in the same file;
that is seam-only (Clausal Prolog never escapes into Python), so this is
the seam spelling:

```seam
-import_module(py.http)
-import_module(py.url)

from clausal import to_python

page(BODY) <- py.http.get("http://example.com", BODY)

def main():
    for BODY in --page(BODY):
        print(to_python(BODY))      # BODY is a string; to_python gives the str
```

URLs, headers and bodies may be written as strings or atoms. Every body the
module hands back is a **string** (the `('$chars', text)` carrier in
Python), and a parsed JSON object is a `DictTerm` whose keys are **atoms**.

---

## `library(http)` — HTTP Requests

```clausal
:- use_module(library(http), [get/2, get/3, post/3, post/4, request/3,
                              json_get/2, json_post/3]).

% A string that is not a URL is the caller's error, raised before any
% network access: domain_error(url, Url).
test("not a url") :-
    catch(get("notaurl", _), error(domain_error(url, URL), _), true),
    URL == "notaurl".
```

!!! warning "`get/2,3` here hides the dict `get/3`"

    Importing `get/2` or `get/3` from `library(http)`, or the whole module,
    makes every `get/3` call in the file the HTTP request, so the dict read
    `get(Dict, Key, Value)` raises `type_error(text, Dict)` there. In such a
    file read dicts with `get_strict/3`, or import only the HTTP predicates
    you need and write `http:get(...)` for a request.

### Simple requests

| Predicate | Mode | Description |
|-----------|------|-------------|
| `get(Url, Body)` | `+Url, -Body` | GET request, body as string. An HTTP error status (4xx/5xx) raises; see [Errors](#errors). |
| `get(Url, Headers, Body)` | `+Url, +Headers, -Body` | GET with custom headers (DictTerm). |
| `post(Url, Data, Body)` | `+Url, +Data, -Body` | POST string data, response as string. |
| `post(Url, Data, Headers, Body)` | `+Url, +Data, +Headers, -Body` | POST with custom headers. |

```text
--8<-- "tests/fixtures/docs/http_sigs.txt:simple_request_examples"
```

### General request

| Predicate | Mode | Description |
|-----------|------|-------------|
| `request(Options, Status, Body)` | `+Options, -Status, -Body` | General HTTP request with full control. |

`Options` is a [`DictTerm`](dicts_sets.md), built with `dict_pairs/2`, with keys:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `url` | string or atom | *required* | request URL |
| `method` | string or atom | `"GET"` | HTTP method |
| `headers` | DictTerm | `{}` | request headers |
| `data` | string | `None` | request body |
| `timeout` | number | `30` | Timeout in seconds |

The keys are names: write them as atoms (`url`, or quoted `'url'`);
a double-quoted `"url"` is matched by its text too.

Unlike `get` and `post`, `request` does **not** raise on 4xx/5xx — it
returns the status code as a value so you can handle it explicitly (as
Scryer's `http_open/3` does). A network failure raises in `request` too,
and so does a body that is not UTF-8 text, whatever the status.

### Errors

A network failure or an HTTP error status **raises** (ruled 2026-10-02; it
used to fail). ISO has no network error; where Scryer has a term it is
used, otherwise the engine's `system_error(Code)` / `resource_error(R)`:

| Failure | Error |
|---|---|
| the host does not resolve | `existence_error(source_sink, Url)` |
| a DNS failure that is not "no such host" | `system_error(host_lookup_failed)` |
| connection refused / reset | `system_error(connection_refused)` / `system_error(connection_reset)` |
| host or network unreachable | `system_error(host_unreachable)` / `system_error(network_unreachable)` |
| the timeout passed | `resource_error(timeout)` |
| a TLS failure; a malformed response | `system_error(tls_failure)`; `system_error(http_protocol_error)` |
| status 404, 410 (`get`, `post`, `json_get`, `json_post`) | `existence_error(source_sink, Url)` |
| status 401, 403, 407 | `permission_error(open, source_sink, Url)` |
| any other status >= 400 | `system_error(http_status(Status))` |
| a response body that is not UTF-8 text | `syntax_error(invalid_data)` |
| a body `json_get` / `json_post` cannot parse as JSON | `syntax_error(invalid_json)` |

An error status is answered first: a 404 whose body is not text raises
the 404. The body errors (ruled 2026-10-02; they used to fail, and
`request` read an undecodable error body as `""`) are ISO's term for input
text that cannot be read (`syntax_error`); `invalid_data` is Scryer's kind
for bytes that are not UTF-8 on a text stream.

Wrap a call in `catch/3` for the old failure:
`catch(get(U, B), error(existence_error(source_sink, _), _), fail)`.

```text
--8<-- "tests/fixtures/docs/http_sigs.txt:general_request_example"
```

### JSON requests

| Predicate | Mode | Description |
|-----------|------|-------------|
| `json_get(Url, Term)` | `+Url, -Term` | GET + parse JSON → DictTerm/list |
| `json_post(Url, Term, Response)` | `+Url, +Term, -Response` | POST JSON + parse response |

JSON objects are converted to [`DictTerm`](dicts_sets.md) (atom keys), arrays to lists and
JSON strings to strings, using the same conversion as the [JSON](json.md) module.
Read a field with the dict builtin `get(USER, name, NAME)` (or `get_strict/3`
in a file that imports HTTP `get`; the seam also writes `USER.name`); a
string key `"name"` does not match an atom key and the goal fails.

```text
--8<-- "tests/fixtures/docs/http_sigs.txt:json_request_examples"
```

---

## `library(url)` — URL Utilities

```clausal
:- use_module(library(url), [encode/2, decode/2, parse/2, join/2]).

test("encode") :-
    encode("hello world", E),
    E == "hello%20world".
```

| Predicate | Mode | Description |
|-----------|------|-------------|
| `encode(String, Encoded)` | `+String, -Encoded` | URL-encode (`%20` for spaces, etc.) |
| `decode(Encoded, String)` | `+Encoded, -String` | URL-decode |
| `parse(Url, Parts)` | `+Url, -Parts` | parse URL into DictTerm |
| `join(Parts, Url)` | `+Parts, -Url` | Assemble URL from DictTerm |

### encode / decode

```text
--8<-- "tests/fixtures/docs/http_sigs.txt:url_encode_examples"
```

encode uses `safe=""` — all special characters are encoded.

### parse / join

`parse` returns a DictTerm keyed by the atoms `scheme`, `host`, `port`, `path`,
`query`, `fragment`, and `join` consumes the
same dict unchanged. Port is an integer (0 if not specified). Read a part
with the dict builtin `get/3`, e.g. `get(PARTS, scheme, S)` (the seam also
writes `PARTS.scheme`).

```text
--8<-- "tests/fixtures/docs/http_sigs.txt:url_parse_examples"
```

---

??? example "Examples"

    ### Build a query URL

    ```text
    --8<-- "tests/fixtures/docs/http_sigs.txt:build_query_url"
    ```

    ### Check API health

    ```text
    --8<-- "tests/fixtures/docs/http_sigs.txt:health_check"
    ```

---

*See also: [JSON](json.md) — JSON parsing and DictTerm integration ·
[Dicts & Sets](dicts_sets.md) — DictTerm construction and access ·
[Python Interop](python_integration.md) — the seam's `++()` for advanced HTTP with `requests`.*
