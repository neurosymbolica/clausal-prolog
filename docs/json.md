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
# then use py.json.parse(S_, T_), py.json.get(T_, key, V_), etc.
```

---

## Type Mapping

| JSON | Clausal |
|---|---|
| `{}` object | [`DictTerm`](dicts_sets.md) with **atom** keys |
| `[]` array | Python `list` |
| `"string"` (a value) | a **string** (in Python, the `('$chars', text)` carrier) |
| `123` / `1.5` | Python `int` / `float` |
| `true`/`false` | Python `True`/`False` |
| `null` | Python `None` |

An object **key** is a name, so it comes back as an atom: `D.name` and
`get(D, name, V)` read a parsed object (declare `name`, or write `'name'`).
A string key `get(D, "name", V)` does not match the atom key, and the goal
fails. A string **value** is text, so it
comes back as a string. `parse/3`'s `atoms(...)` option (below) is how you
promote chosen values to atoms as well.

Generating is the mirror: an atom serialises as the JSON string of its
spelling, a string as itself, and a compound cell — which has no JSON
counterpart — raises `type_error(json_term, Cell)`.

Conversion is recursive: nested JSON objects produce nested DictTerms, and
the `atoms` vocabulary reaches every nested string value.

---

## Predicates

### parse/2

`parse(String, Term)` — parse a JSON string into Clausal terms. Fails on invalid JSON or unbound String.

```clausal
parse_config(S, CONFIG) <- parse(S, CONFIG)
```

### parse/3

`parse(String, Term, Options)` — `parse/2` plus a vocabulary of string values
that should come back as **atoms**. The only option is `atoms(Spellings)`,
where `Spellings` is a list of the texts to mint; anything else raises
`domain_error(json_option, Opt)`.

```clausal
--8<-- "tests/fixtures/docs/json_examples.clausal:parse_atoms"
```

Use it when a JSON document carries a closed vocabulary — a status, a colour,
an enum — that the program wants to reason about as symbols rather than as
text. Everything not listed stays a string.

### generate/2

`generate(Term, String)` — serialize a Clausal term to a compact JSON string. Fails if the term contains unbound [variables](syntax.md). An atom serialises as the JSON string of its spelling; a compound cell raises `type_error(json_term, Cell)`.

```clausal
to_json(DATA, JSON) <- generate(DATA, JSON)
```

```clausal
--8<-- "tests/fixtures/docs/json_examples.clausal:generate_kinds"
```

### pretty_generate/2

`pretty_generate(Term, String)` — like generate but with 2-space indentation.

### get/3

`get(Term, Key, Value)` — extract a value from a DictTerm by key.

- **Key bound**: direct lookup, unify Value. Fails if key not found. Keys of a parsed object are atoms.
- **Key unbound**: enumerate all key-value pairs via backtracking.

```clausal
-import_from(py.json, [parse, get])

get_name(JSON_STRING, NAME) <- (
    parse(JSON_STRING, DATA),
    get(DATA, 'name', NAME)        # the atom key; "name" would fail
)
```

Given the text `{"name": "Ann"}`, `NAME` is the string `"Ann"`; with `KEY`
unbound, `get(DATA, KEY, V)` enumerates `KEY = name, V = "Ann"`.

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
