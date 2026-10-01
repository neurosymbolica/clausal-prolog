# Clausal — HTTP & URL Modules (`http`, `url`)

## Overview

Two modules for HTTP requests and URL manipulation, wrapping Python's `urllib`
stdlib. Zero third-party dependencies.

```seam
-import_from(py.http, [get, json_get, post, request])
-import_from(py.url, [encode, decode, parse, join])

fetch_page(URL, BODY) <- get(URL, BODY)

fetch_api(URL, DATA) <- json_get(URL, DATA)
```

Or via [module import](import.md):

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

## `py.http` — HTTP Requests

```seam
-import_from(py.http, [get, post, request, json_get, json_post])
```

### Simple requests

| Predicate | Mode | Description |
|-----------|------|-------------|
| `get(Url, Body)` | `+Url, -Body` | GET request, body as string. Fails on HTTP errors (4xx/5xx). |
| `get(Url, Headers, Body)` | `+Url, +Headers, -Body` | GET with custom headers (DictTerm). |
| `post(Url, Data, Body)` | `+Url, +Data, -Body` | POST string data, response as string. |
| `post(Url, Data, Headers, Body)` | `+Url, +Data, +Headers, -Body` | POST with custom headers. |

```seam
--8<-- "tests/fixtures/docs/http_sigs.txt:simple_request_examples"
```

### General request

| Predicate | Mode | Description |
|-----------|------|-------------|
| `request(Options, Status, Body)` | `+Options, -Status, -Body` | General HTTP request with full control. |

`Options` is a [`DictTerm`](dicts_sets.md) with keys:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `url` | string or atom | *required* | request URL |
| `method` | string or atom | `"GET"` | HTTP method |
| `headers` | DictTerm | `{}` | request headers |
| `data` | string | `None` | request body |
| `timeout` | number | `30` | Timeout in seconds |

The keys are names: write them bare (declared) or single-quoted (`'url'`);
a double-quoted `"url"` is matched by its text too.

Unlike `get` and `post`, `request` does **not** fail on 4xx/5xx — it returns
the status code so you can handle errors explicitly.

```seam
--8<-- "tests/fixtures/docs/http_sigs.txt:general_request_example"
```

### JSON requests

| Predicate | Mode | Description |
|-----------|------|-------------|
| `json_get(Url, Term)` | `+Url, -Term` | GET + parse JSON → DictTerm/list |
| `json_post(Url, Term, Response)` | `+Url, +Term, -Response` | POST JSON + parse response |

JSON objects are converted to [`DictTerm`](dicts_sets.md) (atom keys), arrays to lists and
JSON strings to strings, using the same conversion as the [`py.json`](json.md) module.
Read a field as `USER.name` or `py.json.get(USER, name, NAME)` (with `-import_module(py.json)`
and `name` declared); a string key `"name"` does not match an atom key and the goal fails.

```seam
--8<-- "tests/fixtures/docs/http_sigs.txt:json_request_examples"
```

---

## `py.url` — URL Utilities

```seam
-import_from(py.url, [encode, decode, parse, join])
```

| Predicate | Mode | Description |
|-----------|------|-------------|
| `encode(String, Encoded)` | `+String, -Encoded` | URL-encode (`%20` for spaces, etc.) |
| `decode(Encoded, String)` | `+Encoded, -String` | URL-decode |
| `parse(Url, Parts)` | `+Url, -Parts` | parse URL into DictTerm |
| `join(Parts, Url)` | `+Parts, -Url` | Assemble URL from DictTerm |

### encode / decode

```seam
--8<-- "tests/fixtures/docs/http_sigs.txt:url_encode_examples"
```

encode uses `safe=""` — all special characters are encoded.

### parse / join

`parse` returns a DictTerm keyed by the atoms `scheme`, `host`, `port`, `path`,
`query`, `fragment` — so `PARTS.scheme` reads a part, and `join` consumes the
same dict unchanged. Port is an integer (0 if not specified).

```seam
--8<-- "tests/fixtures/docs/http_sigs.txt:url_parse_examples"
```

---

??? example "Examples"

    ### Build a query URL

    ```seam
    --8<-- "tests/fixtures/docs/http_sigs.txt:build_query_url"
    ```

    ### Check API health

    ```seam
    --8<-- "tests/fixtures/docs/http_sigs.txt:health_check"
    ```

---

*See also: [JSON](json.md) — JSON parsing and DictTerm integration ·
[Dicts & Sets](dicts_sets.md) — DictTerm construction and access ·
[Python Interop](python_integration.md) — `++()` for advanced HTTP with `requests`.*
