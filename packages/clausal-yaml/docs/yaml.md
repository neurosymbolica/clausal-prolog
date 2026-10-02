# Clausal — YAML (`yaml` module)

## Overview

The `yaml` module provides predicates for parsing and generating YAML, backed by Python's PyYAML library (`yaml.safe_load` / `yaml.safe_dump`). Data is represented as native Python objects — no custom term types. For JSON data, see the [JSON](json.md) module.

```clausal
-import_from(yaml, [read, write, get])

parse_config(PATH, HOST, PORT) <- (
    read_file(PATH, D),
    get(D, ["server", "host"], HOST),
    get(D, ["server", "port"], PORT)
)
```

Or via [module import](import.md):

```clausal
-import_module(yaml)

parse_config(PATH, HOST) <- (
    yaml.read_file(PATH, D),
    yaml.get(D, ["server", "host"], HOST)
)
```

---

## Import

```clausal
-import_from(yaml, [read, write, read_all, write_all,
                            read_file, write_file, get])
```

The module is `py.yaml`; `-import_from(yaml, ...)` is rewritten to it. The predicate names are lower_snake_case (`read`, `read_all`, `read_file`, `write`, `write_all`, `write_file`, `get`): TitleCase names such as `Read` are no longer valid predicate names, and there are no aliases.

---

## Data representation

YAML data maps directly to Python types:

| YAML construct | Python type |
|----------------|-------------|
| Mapping (`key: value`) | `dict` |
| sequence (`- item`) | `list` |
| String | `str` |
| Integer | `int` |
| Float | `float` |
| Boolean (`true`/`false`) | `bool` |
| Null (`null`, `~`) | `None` |

These are the exact objects produced by `yaml.safe_load`. Any Python method can be called on them via [`++()`](python_integration.md) interop — e.g., `KEYS is ++(D.keys())` or `LEN is ++len(ITEMS)`.

---

## Security

Only `yaml.safe_load` is used — no arbitrary Python object construction from YAML tags. This prevents the well-known code execution vulnerability in `yaml.load`.

---

## Parsing predicates

### `read/2`

```clausal
--8<-- "tests/fixtures/docs/yaml_sigs.txt:read_sig"
```

Parse a YAML string into a Python object. Text that is not YAML raises `syntax_error(invalid_yaml)` (see [Errors](#errors)).

```clausal
-import_from(yaml, [read, get])

test("parse mapping") <- (
    read("name: alice\nage: 30", D),
    get(D, "name", "alice")
)
```

### `read_all/2`

```clausal
--8<-- "tests/fixtures/docs/yaml_sigs.txt:read_all_sig"
```

Parse a multi-document YAML string (documents separated by `---`) into a list of Python objects.

```clausal
-import_from(yaml, [read_all])

test("multi-doc") <- (
    read_all("a: 1\n---\nb: 2", DOCS),
    LEN is ++len(DOCS),
    LEN == 2
)
```

### `read_file/2`

```clausal
--8<-- "tests/fixtures/docs/yaml_sigs.txt:read_file_sig"
```

Read and parse a YAML file from disk. A missing file raises `existence_error(source_sink, Path)`, a file that is not YAML `syntax_error(invalid_yaml)` (see [Errors](#errors)).

```clausal
load_config(PATH, CFG) <- read_file(PATH, CFG)
```

---

## Serialization predicates

### `write/2`

```clausal
--8<-- "tests/fixtures/docs/yaml_sigs.txt:write_sig"
```

Serialize a Python object to a YAML string. Uses block style (`default_flow_style=False`) for human-readable output.

```clausal
-import_from(yaml, [read, write, get])

test("serialize") <- (
    DATA is ++{"x": 1, "y": 2},
    write(DATA, S),
    read(S, D),
    get(D, "x", VAL),
    VAL == 1
)
```

### `write_all/2`

```clausal
--8<-- "tests/fixtures/docs/yaml_sigs.txt:write_all_sig"
```

Serialize a list of Python objects to a multi-document YAML string with `---` separators.

### `write_file/2`

```clausal
--8<-- "tests/fixtures/docs/yaml_sigs.txt:write_file_sig"
```

write a Python object as YAML to a file. The object is serialised before the file is opened, so one YAML cannot represent leaves no file behind. A file-system failure raises (see [Errors](#errors)).

---

## Errors

Every predicate except `get/3` **raises** where it used to fail (ruled 2026-10-02):

| Failure | Error |
|---|---|
| the file does not exist (`read_file`), or its directory does not (`write_file`) | `existence_error(source_sink, Path)` |
| the file may not be opened; a directory where a file is needed | `permission_error(open, source_sink, Path)` |
| any other file-system failure | as [`py.files`](files.md): the same shared mapping |
| text that is not YAML (`read`, `read_all`, `read_file`) | `syntax_error(invalid_yaml)` |
| a file that is not UTF-8 (`read_file`) | `syntax_error(invalid_data)` |
| a path that is unbound / not text | `instantiation_error` / `type_error(text, Path)` |
| an object YAML cannot represent (`write`, `write_all`, `write_file`) | `type_error(yaml_term, Culprit)` |

`syntax_error` is ISO's term for input text that cannot be read, the family `py.http` raises for a body that is not JSON (`invalid_json`); `type_error(yaml_term, _)` matches `py.json`'s `type_error(json_term, _)`. `get/3` still fails on a missing key or index: that failure is its answer.

---

## Navigation predicate

### `get/3`

```clausal
--8<-- "tests/fixtures/docs/yaml_sigs.txt:get_sig"
```

Navigate a nested dict/list structure by key path. `Path` can be:

- A single key: `get(D, "name", V)` — looks up `D["name"]`
- A single index: `get(D, 0, V)` — looks up `D[0]`
- A list of keys/indices: `get(D, ["server", "port"], V)` — walks `D["server"]["port"]`

Fails if any key is missing or index is out of range.

```clausal
-import_from(yaml, [read, get])

test("nested access") <- (
    read("items:\n  - name: first\n  - name: second", D),
    get(D, ["items", 1, "name"], "second")
)
```

---

??? example "Examples"

    ### Parse a config file

    ```clausal
    --8<-- "tests/fixtures/docs/yaml_sigs.txt:parse_config"
    ```

    ### Round-trip

    ```clausal
    --8<-- "tests/fixtures/docs/yaml_sigs.txt:round_trip"
    ```

    ### Multi-document Kubernetes manifests

    ```clausal
    --8<-- "tests/fixtures/docs/yaml_sigs.txt:k8s_manifests"
    ```

    ### Python interop for complex access

    ```clausal
    --8<-- "tests/fixtures/docs/yaml_sigs.txt:python_interop"
    ```

    ---

??? abstract "Implementation"

    - **Module:** `clausal/modules/py/yaml.py`
    - **Adapter class:** `_YamlPredicate` (same pattern as `_RegexPredicate`)
    - **Backend:** PyYAML (`yaml.safe_load`, `yaml.safe_dump`)
    - **Tests:** `tests/test_yaml_module.py`, `tests/test_yaml_errors_iso.py`, `tests/fixtures/yaml_basic.seam`

    ---

??? abstract "Design decisions"

    1. **Native Python data** — `read` returns Python dicts/lists/scalars directly. No conversion to term objects. Users access nested data via `get/3` or [`++()`](python_integration.md) interop. This is the most Pythonic approach and avoids inventing a parallel data representation.
    2. **`safe_load` only** — prevents arbitrary code execution from YAML tags. This is the standard security practice.
    3. **`get/3` for navigation** — a convenience predicate that avoids verbose `++()` chains for deep nested access. Accepts both single keys and key-path lists.
    4. **Module path `py.yaml`** — the wrapper lives under `clausal.modules.py` and imports PyYAML through `_import_stdlib`, so it does not shadow it; `-import_from(yaml, ...)` is an alias. With `-import_from`, the predicates are used without any prefix: `read(...)`, `write(...)`, `get(...)`.
    5. **All predicates are deterministic** — YAML parsing produces exactly one result (or raises). No backtracking.
    6. **Block-style output** — `write/2` uses `default_flow_style=False` for human-readable YAML output by default.

---

*See also: [Dicts & Sets](dicts_sets.md) — working with dict terms · [Python Interop](python_integration.md) — direct YAML via `++()` escape.*
