# JSON Module

The `py.json` standard library module provides relational predicates for parsing, generating, and querying JSON data. JSON objects map to `DictTerm` for unification-aware access.

The implementation lives in `clausal/modules/py/json.py`.

---

## Import

```clausal
-import_from(py.json, [Parse, Generate, PrettyGenerate, Get, ReadFile, WriteFile])
```

Or via module import:

```clausal
-import_module(py.json)
# then use py.json.Parse(S_, T_), py.json.Get(T_, "key", V_), etc.
```

---

## Type Mapping

| JSON | Clausal |
|---|---|
| `{}` object | `DictTerm` |
| `[]` array | Python `list` |
| `"string"` | Python `str` |
| `123` / `1.5` | Python `int` / `float` |
| `true`/`false` | Python `True`/`False` |
| `null` | Python `None` |

Conversion is recursive: nested JSON objects produce nested DictTerms.

---

## Predicates

### Parse/2

`Parse(String, Term)` — parse a JSON string into Clausal terms. Fails on invalid JSON or unbound String.

```clausal
parse_config(S, CONFIG) <- Parse(S, CONFIG)
```

### Generate/2

`Generate(Term, String)` — serialize a Clausal term to a compact JSON string. Fails if the term contains unbound variables.

```clausal
to_json(DATA, JSON) <- Generate(DATA, JSON)
```

### PrettyGenerate/2

`PrettyGenerate(Term, String)` — like Generate but with 2-space indentation.

### Get/3

`Get(Term, Key, Value)` — extract a value from a DictTerm by key.

- **Key bound**: direct lookup, unify Value. Fails if key not found.
- **Key unbound**: enumerate all key-value pairs via backtracking.

```clausal
-import_from(py.json, [Parse, Get])

get_name(JSON_STRING, NAME) <- (
    Parse(JSON_STRING, DATA),
    Get(DATA, "name", NAME)
)
```

### ReadFile/2

`ReadFile(Path, Term)` — read and parse a JSON file. Fails on file or parse error.

```clausal
load_config(CONFIG) <- ReadFile("config.json", CONFIG)
```

### WriteFile/2

`WriteFile(Path, Term)` — serialize a term and write to a JSON file (2-space indented). Fails if term contains unbound variables.

---

## Example

```clausal
-import_from(py.json, [Parse, Generate, Get, ReadFile])

load_config(CONFIG) <- ReadFile("config.json", CONFIG)

get_setting(CONFIG, KEY, VALUE) <- Get(CONFIG, KEY, VALUE)

config_to_json(CONFIG, JSON) <- Generate(CONFIG, JSON)
```
