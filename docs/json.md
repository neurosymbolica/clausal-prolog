# JSON Module

The `py.json` standard library module provides relational predicates for parsing, generating, and querying JSON data. JSON objects map to [`DictTerm`](dicts_sets.md) for unification-aware access.

The implementation lives in `clausal/modules/py/json.py`.

---

## Import

```clausal
-import_from(py.json, [parse, generate, pretty_generate, get, read_file, write_file])
```

Or via [module import](import.md):

```clausal
-import_module(py.json)
# then use py.json.parse(S_, T_), py.json.get(T_, "key", V_), etc.
```

---

## Type Mapping

| JSON | Clausal |
|---|---|
| `{}` object | [`DictTerm`](dicts_sets.md) |
| `[]` array | Python `list` |
| `"string"` | Python `str` |
| `123` / `1.5` | Python `int` / `float` |
| `true`/`false` | Python `True`/`False` |
| `null` | Python `None` |

Conversion is recursive: nested JSON objects produce nested DictTerms.

---

## Predicates

### parse/2

`parse(String, Term)` — parse a JSON string into Clausal terms. Fails on invalid JSON or unbound String.

```clausal
parse_config(S, CONFIG) <- parse(S, CONFIG)
```

### generate/2

`generate(Term, String)` — serialize a Clausal term to a compact JSON string. Fails if the term contains unbound [variables](syntax.md).

```clausal
to_json(DATA, JSON) <- generate(DATA, JSON)
```

### pretty_generate/2

`pretty_generate(Term, String)` — like generate but with 2-space indentation.

### get/3

`get(Term, Key, Value)` — extract a value from a DictTerm by key.

- **Key bound**: direct lookup, unify Value. Fails if key not found.
- **Key unbound**: enumerate all key-value pairs via backtracking.

```clausal
-import_from(py.json, [parse, get])

get_name(JSON_STRING, NAME) <- (
    parse(JSON_STRING, DATA),
    get(DATA, "name", NAME)
)
```

### read_file/2

`read_file(Path, Term)` — read and parse a JSON file. Fails on file or parse error.

```clausal
load_config(CONFIG) <- read_file("config.json", CONFIG)
```

### write_file/2

`write_file(Path, Term)` — serialize a term and write to a JSON file (2-space indented). Fails if term contains unbound variables.

---

## Example

```clausal
-import_from(py.json, [parse, generate, get, read_file])

load_config(CONFIG) <- read_file("config.json", CONFIG)

get_setting(CONFIG, KEY, VALUE) <- get(CONFIG, KEY, VALUE)

config_to_json(CONFIG, JSON) <- generate(CONFIG, JSON)
```
