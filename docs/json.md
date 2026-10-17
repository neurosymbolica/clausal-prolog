# JSON Module

The JSON library (`library(json)`, the Python module `py.json`) provides relational predicates for parsing, generating, and querying JSON data. JSON objects map to [`DictTerm`](dicts_sets.md) for unification-aware access.

The implementation lives in `clausal/modules/py/json.py`.

Examples on this page are [Clausal Prolog](clausal_prolog.md) (`.clausal`). They
reach the Python module through its `library(json)` facade; the
[seam](syntax.md) imports the module itself, `-import_from(py.json, [...])`,
and also has dict literals and `D.key` access, which Clausal Prolog writes
with `dict_pairs/2` and `get/3`.

---

## Import

```clausal
:- use_module(library(json), [parse/2, parse/3, generate/2, pretty_generate/2,
                              get/3, read_file/2, write_file/2]).
```

Or import every predicate, and call them module-qualified if you like:

```clausal
:- use_module(library(json)).

% then call parse(S, T), or json:parse(S, T), json:get(T, key, V), etc.
first_key(S, K) :-
    json:parse(S, T),
    json:get(T, K, _).

test("module-qualified") :-
    first_key("{\"a\": 1}", K),
    K == a.
```

---

## Type Mapping

| JSON | Clausal Prolog |
|---|---|
| `{}` object | [`DictTerm`](dicts_sets.md) with **atom** keys |
| `[]` array | a list |
| `"string"` (a value) | a **string** (in Python, the `('$chars', text)` carrier) |
| `123` / `1.5` | an integer / a float |
| `true`/`false` | the atoms `true`/`false` (in Python, `True`/`False`) |
| `null` | Python `None` |

`null` comes back as Python's `None`, which is not an atom and has no
Clausal Prolog spelling: `parse("null", N)` succeeds, but `N == null` and
`N == 'None'` both fail, and `generate(null, S)` writes the JSON string
`"null"`, not JSON `null`.

An object **key** is a name, so it comes back as an atom: `get(D, name, V)`
reads a parsed object (the seam also writes `D.name`).
A string key `get(D, "name", V)` does not match the atom key, and the goal
fails. A string **value** is text, so it
comes back as a string. `parse/3`'s `atoms(...)` option (below) is how you
promote chosen values to atoms as well.

Generating is the mirror: an atom serialises as the JSON string of its
spelling (except `true` and `false`, which generate JSON `true`/`false`), a string as itself, and a compound cell — which has no JSON
counterpart — raises `type_error(json_term, Cell)`.

Conversion is recursive: nested JSON objects produce nested DictTerms, and
the `atoms` vocabulary reaches every nested string value.

---

## Predicates

### parse/2

`parse(String, Term)` — parse a JSON string into Clausal Prolog terms. Text that is not JSON raises `syntax_error(invalid_json)` (ruled 2026-10-02; it was `domain_error(json_text, S)`); an unbound String raises `instantiation_error`.

```clausal
:- use_module(library(json), [parse/2]).

parse_config(S, CONFIG) :-
    parse(S, CONFIG).

test("not JSON is a syntax error") :-
    catch(parse_config("{oops", _), error(E, _), true),
    E == syntax_error(invalid_json).
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

`generate(Term, String)` — serialize a Clausal Prolog term to a compact JSON string. Fails if the term contains unbound [variables](syntax.md). An atom serialises as the JSON string of its spelling; a compound cell raises `type_error(json_term, Cell)`.

```clausal
:- use_module(library(json), [generate/2]).

to_json(DATA, JSON) :-
    generate(DATA, JSON).

test("a list") :-
    to_json([1, 2.5, "x"], JSON),
    JSON == "[1, 2.5, \"x\"]".
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
:- use_module(library(json), [parse/2, get/3]).

get_name(JSON_STRING, NAME) :-
    parse(JSON_STRING, DATA),
    get(DATA, name, NAME).        % the atom key; "name" would fail

test("get by key") :-
    get_name("{\"name\": \"Ann\"}", NAME),
    NAME == "Ann".

test("enumerate keys") :-
    parse("{\"name\": \"Ann\"}", DATA),
    findall(KEY-V, get(DATA, KEY, V), PAIRS),
    PAIRS == [name-"Ann"].

test("a string key does not match", fail) :-
    parse("{\"name\": \"Ann\"}", DATA),
    get(DATA, "name", _).
```

Given the text `{"name": "Ann"}`, `NAME` is the string `"Ann"`; with `KEY`
unbound, `get(DATA, KEY, V)` enumerates `KEY = name, V = "Ann"`.

### read_file/2

`read_file(Path, Term)` — read and parse a JSON file. A file that is not JSON raises `syntax_error(invalid_json)`, one that is not UTF-8 `syntax_error(invalid_data)` (both were `domain_error(json_file, Path)`); a file-system failure raises the ISO error ([files](files.md): `existence_error(source_sink, Path)`, ...).

```clausal
:- use_module(library(json), [read_file/2]).

load_config(CONFIG) :-
    read_file("config.json", CONFIG).
```

### write_file/2

`write_file(Path, Term)` — serialize a term and write to a JSON file (2-space indented). Fails if term contains unbound variables.

---

## Example

```clausal
:- use_module(library(json), [generate/2, get/3, read_file/2, write_file/2]).
:- use_module(library(py_files), [temp_directory/1, join_path/3]).

load_config(PATH, CONFIG) :-
    read_file(PATH, CONFIG).

get_setting(CONFIG, KEY, VALUE) :-
    get(CONFIG, KEY, VALUE).

config_to_json(CONFIG, JSON) :-
    generate(CONFIG, JSON).

test("write, load, read a setting") :-
    temp_directory(DIR),
    join_path(DIR, "config.json", PATH),
    dict_pairs(CONFIG0, [debug-true, level-3]),
    write_file(PATH, CONFIG0),
    load_config(PATH, CONFIG),
    get_setting(CONFIG, level, LEVEL),
    LEVEL == 3,
    config_to_json(CONFIG, JSON),
    JSON == "{\"debug\": true, \"level\": 3}".
```
