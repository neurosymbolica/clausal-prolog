# Clausal — HTTP & URL Modules (`http`, `url`)

## Overview

Two modules for HTTP requests and URL manipulation, wrapping Python's `urllib`
stdlib. Zero third-party dependencies.

```clausal
-import_from(py.http, [Get, JSONGet, Post, Request])
-import_from(py.url, [Encode, Decode, Parse, Join])

FetchPage(URL, BODY) <- Get(URL, BODY)

FetchApi(URL, DATA) <- JSONGet(URL, DATA)
```

Or via [module import](import.md):

```clausal
-import_module(py.http)
-import_module(py.url)

Main <- (
    py.http.Get("http://example.com", BODY),
    ++print(BODY)
)
```

---

## `py.http` — HTTP Requests

```clausal
-import_from(py.http, [Get, Post, Request, JSONGet, JSONPost])
```

### Simple requests

| Predicate | Mode | Description |
|-----------|------|-------------|
| `Get(Url, Body)` | `+Url, -Body` | GET request, body as string. Fails on HTTP errors (4xx/5xx). |
| `Get(Url, Headers, Body)` | `+Url, +Headers, -Body` | GET with custom headers (DictTerm). |
| `Post(Url, Data, Body)` | `+Url, +Data, -Body` | POST string data, response as string. |
| `Post(Url, Data, Headers, Body)` | `+Url, +Data, +Headers, -Body` | POST with custom headers. |

```clausal
--8<-- "tests/fixtures/docs/http_sigs.txt:simple_request_examples"
```

### General request

| Predicate | Mode | Description |
|-----------|------|-------------|
| `Request(Options, Status, Body)` | `+Options, -Status, -Body` | General HTTP request with full control. |

`Options` is a [`DictTerm`](dicts_sets.md) with keys:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `"url"` | string | *required* | Request URL |
| `"method"` | string | `"GET"` | HTTP method |
| `"headers"` | DictTerm | `{}` | Request headers |
| `"data"` | string | `None` | Request body |
| `"timeout"` | number | `30` | Timeout in seconds |

Unlike `Get` and `Post`, `Request` does **not** fail on 4xx/5xx — it returns
the status code so you can handle errors explicitly.

```clausal
--8<-- "tests/fixtures/docs/http_sigs.txt:general_request_example"
```

### JSON requests

| Predicate | Mode | Description |
|-----------|------|-------------|
| `JSONGet(Url, Term)` | `+Url, -Term` | GET + parse JSON → DictTerm/list |
| `JSONPost(Url, Term, Response)` | `+Url, +Term, -Response` | POST JSON + parse response |

JSON objects are converted to [`DictTerm`](dicts_sets.md), arrays to lists, using the same
conversion as the [`py.json`](json.md) module.

```clausal
--8<-- "tests/fixtures/docs/http_sigs.txt:json_request_examples"
```

---

## `py.url` — URL Utilities

```clausal
-import_from(py.url, [Encode, Decode, Parse, Join])
```

| Predicate | Mode | Description |
|-----------|------|-------------|
| `Encode(String, Encoded)` | `+String, -Encoded` | URL-encode (`%20` for spaces, etc.) |
| `Decode(Encoded, String)` | `+Encoded, -String` | URL-decode |
| `Parse(Url, Parts)` | `+Url, -Parts` | Parse URL into DictTerm |
| `Join(Parts, Url)` | `+Parts, -Url` | Assemble URL from DictTerm |

### Encode / Decode

```clausal
--8<-- "tests/fixtures/docs/http_sigs.txt:url_encode_examples"
```

Encode uses `safe=""` — all special characters are encoded.

### Parse / Join

`Parse` returns a DictTerm with keys: `scheme`, `host`, `port`, `path`, `query`,
`fragment`. Port is an integer (0 if not specified).

```clausal
--8<-- "tests/fixtures/docs/http_sigs.txt:url_parse_examples"
```

---

??? example "Examples"

    ### Build a query URL

    ```clausal
    --8<-- "tests/fixtures/docs/http_sigs.txt:build_query_url"
    ```

    ### Check API health

    ```clausal
    --8<-- "tests/fixtures/docs/http_sigs.txt:health_check"
    ```

---

*See also: [JSON](json.md) — JSON parsing and DictTerm integration ·
[Dicts & Sets](dicts_sets.md) — DictTerm construction and access ·
[Python Interop](python_integration.md) — `++()` for advanced HTTP with `requests`.*
