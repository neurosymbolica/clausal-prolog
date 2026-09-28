# Clausal — YAML (`yaml_module` module)

## Overview

The `yaml_module` module provides predicates for parsing and generating YAML, backed by Python's PyYAML library (`yaml.safe_load` / `yaml.safe_dump`). Data is represented as native Python objects — no custom term types. For JSON data, see the [JSON](json.md) module.

```clausal
-import_from(yaml_module, [Read, write, Get])

parse_config(PATH, HOST, PORT) <- (
    read_file(PATH, D),
    Get(D, ["server", "host"], HOST),
    Get(D, ["server", "port"], PORT)
)
```

Or via [module import](import.md):

```clausal
-import_module(yaml_module)

parse_config(PATH, HOST) <- (
    yaml_module.ReadFile(PATH, D),
    yaml_module.Get(D, ["server", "host"], HOST)
)
```

---

## Import

```clausal
-import_from(yaml_module, [Read, write, ReadAll, WriteAll,
                            read_file, WriteFile, Get])
```

The module name is `yaml_module` (not `yaml`) to avoid shadowing Python's PyYAML package in the import machinery.

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

### `Read/2`

```clausal
--8<-- "tests/fixtures/docs/yaml_sigs.txt:read_sig"
```

Parse a YAML string into a Python object. Fails on invalid YAML.

```clausal
-import_from(yaml_module, [Read, Get])

test("parse mapping") <- (
    Read("name: alice\nage: 30", D),
    Get(D, "name", "alice")
)
```

### `ReadAll/2`

```clausal
--8<-- "tests/fixtures/docs/yaml_sigs.txt:read_all_sig"
```

Parse a multi-document YAML string (documents separated by `---`) into a list of Python objects.

```clausal
-import_from(yaml_module, [ReadAll])

test("multi-doc") <- (
    ReadAll("a: 1\n---\nb: 2", DOCS),
    LEN is ++len(DOCS),
    LEN == 2
)
```

### `read_file/2`

```clausal
--8<-- "tests/fixtures/docs/yaml_sigs.txt:read_file_sig"
```

Read and parse a YAML file from disk. Fails if the file does not exist or contains invalid YAML.

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
-import_from(yaml_module, [Read, write, Get])

test("serialize") <- (
    DATA is ++{"x": 1, "y": 2},
    write(DATA, S),
    Read(S, D),
    Get(D, "x", VAL),
    VAL == 1
)
```

### `WriteAll/2`

```clausal
--8<-- "tests/fixtures/docs/yaml_sigs.txt:write_all_sig"
```

Serialize a list of Python objects to a multi-document YAML string with `---` separators.

### `WriteFile/2`

```clausal
--8<-- "tests/fixtures/docs/yaml_sigs.txt:write_file_sig"
```

write a Python object as YAML to a file. Always succeeds if the write completes; fails on I/O errors.

---

## Navigation predicate

### `Get/3`

```clausal
--8<-- "tests/fixtures/docs/yaml_sigs.txt:get_sig"
```

Navigate a nested dict/list structure by key path. `Path` can be:

- A single key: `Get(D, "name", V)` — looks up `D["name"]`
- A single index: `Get(D, 0, V)` — looks up `D[0]`
- A list of keys/indices: `Get(D, ["server", "port"], V)` — walks `D["server"]["port"]`

Fails if any key is missing or index is out of range.

```clausal
-import_from(yaml_module, [Read, Get])

test("nested access") <- (
    Read("items:\n  - name: first\n  - name: second", D),
    Get(D, ["items", 1, "name"], "second")
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

    - **Module:** `clausal/modules/yaml_module.py`
    - **Adapter class:** `_YamlPredicate` (same pattern as `_RegexPredicate`)
    - **Backend:** PyYAML (`yaml.safe_load`, `yaml.safe_dump`)
    - **Tests:** `tests/test_yaml_module.py` (45 tests), `tests/fixtures/yaml_basic.clausal` (10 fixture tests)

    ---

??? abstract "Design decisions"

    1. **Native Python data** — `Read` returns Python dicts/lists/scalars directly. No conversion to term objects. Users access nested data via `Get/3` or [`++()`](python_integration.md) interop. This is the most Pythonic approach and avoids inventing a parallel data representation.
    2. **`safe_load` only** — prevents arbitrary code execution from YAML tags. This is the standard security practice.
    3. **`Get/3` for navigation** — a convenience predicate that avoids verbose `++()` chains for deep nested access. Accepts both single keys and key-path lists.
    4. **Module name is `yaml_module`** — avoids shadowing PyYAML's `yaml` package in the Python import machinery. With `-import_from`, the predicates are used without any prefix: `Read(...)`, `write(...)`, `Get(...)`.
    5. **All predicates are deterministic** — YAML parsing produces exactly one result (or fails). No backtracking.
    6. **Block-style output** — `write/2` uses `default_flow_style=False` for human-readable YAML output by default.

---

*See also: [Dicts & Sets](dicts_sets.md) — working with dict terms · [Python Interop](python_integration.md) — direct YAML via `++()` escape.*
