# Clausal — YAML (`yaml_module` module)

## Overview

The `yaml_module` module provides predicates for parsing and generating YAML, backed by Python's PyYAML library (`yaml.safe_load` / `yaml.safe_dump`). Data is represented as native Python objects — no custom term types.

```clausal
-import_from(yaml_module, [Read, Write, Get])

ParseConfig(Path_, Host_, Port_) <- (
    ReadFile(Path_, D_) and
    Get(D_, ["server", "host"], Host_) and
    Get(D_, ["server", "port"], Port_)
)
```

Or via module import:

```clausal
-import_module(yaml_module)

ParseConfig(Path_, Host_) <- (
    yaml_module.ReadFile(Path_, D_) and
    yaml_module.Get(D_, ["server", "host"], Host_)
)
```

---

## Import

```clausal
-import_from(yaml_module, [Read, Write, ReadAll, WriteAll,
                            ReadFile, WriteFile, Get])
```

The module name is `yaml_module` (not `yaml`) to avoid shadowing Python's PyYAML package in the import machinery.

---

## Data representation

YAML data maps directly to Python types:

| YAML construct | Python type |
|----------------|-------------|
| Mapping (`key: value`) | `dict` |
| Sequence (`- item`) | `list` |
| String | `str` |
| Integer | `int` |
| Float | `float` |
| Boolean (`true`/`false`) | `bool` |
| Null (`null`, `~`) | `None` |

These are the exact objects produced by `yaml.safe_load`. Any Python method can be called on them via `++()` interop — e.g., `Keys_ is ++(D_.keys())` or `Len_ is ++len(Items_)`.

---

## Security

Only `yaml.safe_load` is used — no arbitrary Python object construction from YAML tags. This prevents the well-known code execution vulnerability in `yaml.load`.

---

## Parsing predicates

### `Read/2`

```
Read(+YamlString, -Data)
```

Parse a YAML string into a Python object. Fails on invalid YAML.

```clausal
Test("parse mapping") <- (
    Read("name: alice\nage: 30", D_) and
    Get(D_, "name", "alice")
)
```

### `ReadAll/2`

```
ReadAll(+YamlString, -DocList)
```

Parse a multi-document YAML string (documents separated by `---`) into a list of Python objects.

```clausal
Test("multi-doc") <- (
    ReadAll("a: 1\n---\nb: 2", Docs_) and
    Docs_ == [{"a": 1}, {"b": 2}]
)
```

### `ReadFile/2`

```
ReadFile(+Path, -Data)
```

Read and parse a YAML file from disk. Fails if the file does not exist or contains invalid YAML.

```clausal
LoadConfig(Path_, Cfg_) <- ReadFile(Path_, Cfg_)
```

---

## Serialization predicates

### `Write/2`

```
Write(+Data, -YamlString)
```

Serialize a Python object to a YAML string. Uses block style (`default_flow_style=False`) for human-readable output.

```clausal
Test("serialize") <- (
    Write({"x": 1, "y": 2}, S_) and
    Read(S_, D_) and
    Get(D_, "x", 1)
)
```

### `WriteAll/2`

```
WriteAll(+DocList, -YamlString)
```

Serialize a list of Python objects to a multi-document YAML string with `---` separators.

### `WriteFile/2`

```
WriteFile(+Path, +Data)
```

Write a Python object as YAML to a file. Always succeeds if the write completes; fails on I/O errors.

---

## Navigation predicate

### `Get/3`

```
Get(+Data, +Path, -Value)
```

Navigate a nested dict/list structure by key path. `Path` can be:

- A single key: `Get(D_, "name", V_)` — looks up `D_["name"]`
- A single index: `Get(D_, 0, V_)` — looks up `D_[0]`
- A list of keys/indices: `Get(D_, ["server", "port"], V_)` — walks `D_["server"]["port"]`

Fails if any key is missing or index is out of range.

```clausal
Test("nested access") <- (
    Read("items:\n  - name: first\n  - name: second", D_) and
    Get(D_, ["items", 1, "name"], "second")
)
```

---

??? example "Examples"

    ### Parse a config file

    ```clausal
    -import_from(yaml_module, [ReadFile, Get])
    
    DbConfig(Path_, Host_, Port_, Name_) <- (
        ReadFile(Path_, Cfg_) and
        Get(Cfg_, ["database", "host"], Host_) and
        Get(Cfg_, ["database", "port"], Port_) and
        Get(Cfg_, ["database", "name"], Name_)
    )
    ```

    ### Round-trip

    ```clausal
    -import_from(yaml_module, [Read, Write, Get])
    
    RoundTrip(Yaml_, Key_, Val_) <- (
        Read(Yaml_, D_) and
        Write(D_, S_) and
        Read(S_, D2_) and
        Get(D2_, Key_, Val_)
    )
    ```

    ### Multi-document Kubernetes manifests

    ```clausal
    -import_from(yaml_module, [ReadAll, Get])
    
    ServiceNames(Yaml_, Names_) <- (
        ReadAll(Yaml_, Docs_) and
        MapList([D_, N_] >> Get(D_, ["metadata", "name"], N_), Docs_, Names_)
    )
    ```

    ### Python interop for complex access

    ```clausal
    -import_from(yaml_module, [Read])
    
    AllKeys(Yaml_, Keys_) <- (
        Read(Yaml_, D_) and
        Keys_ is ++(list(D_.keys()))
    )
    ```

    ---

??? abstract "Implementation"

    - **Module:** `clausal/modules/yaml_module.py`
    - **Adapter class:** `_YamlPredicate` (same pattern as `_RegexPredicate`)
    - **Backend:** PyYAML (`yaml.safe_load`, `yaml.safe_dump`)
    - **Tests:** `tests/test_yaml_module.py` (45 tests), `tests/fixtures/yaml_basic.clausal` (10 fixture tests)

    ---

??? abstract "Design decisions"

    1. **Native Python data** — `Read` returns Python dicts/lists/scalars directly. No conversion to `KWTerm` or `Compound`. Users access nested data via `Get/3` or `++()` interop. This is the most Pythonic approach and avoids inventing a parallel data representation.
    2. **`safe_load` only** — prevents arbitrary code execution from YAML tags. This is the standard security practice.
    3. **`Get/3` for navigation** — a convenience predicate that avoids verbose `++()` chains for deep nested access. Accepts both single keys and key-path lists.
    4. **Module name is `yaml_module`** — avoids shadowing PyYAML's `yaml` package in the Python import machinery. With `-import_from`, the predicates are used without any prefix: `Read(...)`, `Write(...)`, `Get(...)`.
    5. **All predicates are deterministic** — YAML parsing produces exactly one result (or fails). No backtracking.
    6. **Block-style output** — `Write/2` uses `default_flow_style=False` for human-readable YAML output by default.
