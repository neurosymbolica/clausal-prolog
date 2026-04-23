# Std Modules Phase 3 — Random, JSON & CSV

**Status: COMPLETE**

**Depends on:** DictTerm (terms.py), module infrastructure (clausal/modules/py/)

**Goal:** Add three batteries-included utility modules wrapping Python's `random`,
`json`, and `csv` standard library modules. These are thin relational wrappers
that bring Python's data-format and randomness facilities into the logic
programming world — predicates participate in unification and backtracking where
it makes sense.

**Non-goal:** Re-implementing Python's full API surface. Each module exposes only
the predicates that benefit from relational semantics or are common enough to
warrant a named predicate. Everything else is one `++()` call away.

---

## Design Principles

1. **Module adapter pattern.** Each module defines a `_XxxPredicate` adapter
   class (same pattern as `_UuidPredicate`, `_DateTimePredicate`). Simple-mode
   functions are wrapped via `_simple_to_trampoline()`.

2. **DictTerm for JSON objects.** JSON objects map to `DictTerm`, arrays to
   Python lists, scalars to Python scalars, `null` to `None`. This means
   JSON round-trips through Clausal's unification-aware dict type.

3. **Deterministic predicates.** Random and data-format predicates are
   inherently functional (one answer per call). They succeed once or fail.
   No backtracking enumeration needed except `RandomMember/2` which
   non-deterministically picks elements.

4. **Safe stdlib import.** Use `_import_stdlib()` from `clausal.modules.py`
   to avoid circular imports (e.g. `py/random.py` shadowing stdlib `random`).

5. **Clausal naming conventions.** TitleCase predicates, expanded names.

---

## 3a — Random Module

**Files:** `clausal/modules/py/random.py` (new), `clausal/modules/random_mod.py`
(alias), `tests/test_random_module.py` (new)

### Predicates

| Predicate | Description |
|---|---|
| `Random/1` | `Random(X)` — bind X to a random float in [0.0, 1.0). |
| `RandomFloat/3` | `RandomFloat(Low, High, X)` — bind X to a random float in [Low, High). |
| `RandomInteger/3` | `RandomInteger(Low, High, X)` — bind X to a random integer in [Low, High]. |
| `RandomMember/2` | `RandomMember(List, X)` — bind X to a randomly chosen element. Deterministic (one solution). |
| `RandomPermutation/2` | `RandomPermutation(List, Shuffled)` — bind Shuffled to a random permutation. |
| `RandomSample/3` | `RandomSample(List, K, Sample)` — bind Sample to K randomly chosen elements (no replacement). |
| `RandomSeed/1` | `RandomSeed(Seed)` — set the PRNG seed for reproducibility. Always succeeds. |
| `Maybe/0` | `Maybe` — succeeds with probability 0.5, fails otherwise. |
| `Maybe/1` | `Maybe(P)` — succeeds with probability P (float in [0.0, 1.0]). |

### Implementation notes

- Wrap Python `random` module. Use a **module-local `random.Random` instance**
  rather than the global `random` functions — avoids polluting global state and
  allows `RandomSeed/1` to be scoped.
- `RandomMember/2`: deref the list, pick `random.choice(list)`, unify with X.
  Fail if list is empty or unbound.
- `Maybe/0` and `Maybe/1` are the only predicates that can fail
  non-exceptionally — they succeed or silently fail based on the coin flip.
- All other predicates fail only on type errors (unbound required args).

### Semantics detail

```
Random(X)                       % X = random float [0, 1)
RandomFloat(0.0, 10.0, X)      % X = random float [0, 10)
RandomInteger(1, 6, X)          % X = random int [1, 6]
RandomMember([a, b, c], X)      % X = one of a, b, c (one solution)
RandomPermutation([1,2,3], P)   % P = some permutation of [1,2,3]
RandomSample([1,2,3,4,5], 3, S) % S = 3 elements without replacement
RandomSeed(42)                  % deterministic from here on
Maybe                           % 50% chance of success
Maybe(0.3)                      % 30% chance of success
```

### Test plan (~25 tests)

- `Random/1`: result is float in [0, 1).
- `RandomFloat/3`: result in range; Low > High fails.
- `RandomInteger/3`: result is int in range; boundaries inclusive.
- `RandomMember/2`: result is element of list; empty list fails; unbound list fails.
- `RandomPermutation/2`: result is a permutation (same elements, same length).
- `RandomSample/3`: result length = K; all elements from original; K > len fails.
- `RandomSeed/1`: seeded sequence is reproducible.
- `Maybe/0`: over 1000 trials, succeeds roughly 50% (within tolerance).
- `Maybe/1`: P=1.0 always succeeds; P=0.0 always fails.
- Unbound required args fail gracefully (no exception).

---

## 3b — JSON Module

**Files:** `clausal/modules/py/json.py` (new), `clausal/modules/json_mod.py`
(alias), `tests/test_json_module.py` (new)

### Predicates

Predicates are unprefixed — the module namespace (`py.json`) provides the
context. Import via `-import_from(py.json, [Parse, Generate, Get, ...])` or
use qualified: `py.json.Parse(S, T)`.

| Predicate | Description |
|---|---|
| `Parse/2` | `Parse(String, Term)` — parse JSON string into Clausal terms. Objects → DictTerm, arrays → list, scalars → Python scalars, null → None. |
| `Generate/2` | `Generate(Term, String)` — serialize Clausal term to JSON string. Inverse of Parse. |
| `PrettyGenerate/2` | `PrettyGenerate(Term, String)` — like Generate but with indentation (2-space). |
| `Get/3` | `Get(Term, Key, Value)` — extract a value from a DictTerm by key. Shorthand for dict access. |
| `ReadFile/2` | `ReadFile(Path, Term)` — read and parse a JSON file. |
| `WriteFile/2` | `WriteFile(Path, Term)` — serialize and write a JSON file. |

### Type mapping

| JSON | Clausal |
|---|---|
| `{}` object | `DictTerm({"key": value, ...})` |
| `[]` array | Python `list` |
| `"string"` | Python `str` |
| `123` / `1.5` | Python `int` / `float` |
| `true`/`false` | Python `True`/`False` |
| `null` | Python `None` |

### Implementation notes

- **`Parse/2`**: `json.loads(string)` then `_python_to_clausal(obj)` recursive
  converter that wraps dicts as `DictTerm`. Lists and scalars pass through as-is
  (they already unify naturally).
- **`Generate/2`**: `_clausal_to_python(term)` recursive converter that
  unwraps `DictTerm` → dict, then `json.dumps()`. Must `deref()` all values
  before serialization. Unbound Vars raise an instantiation error.
- **`Get/3`**: deref the DictTerm, look up Key in `.data`, unify Value.
  If Key is unbound, enumerate all key-value pairs (non-deterministic).
- **`ReadFile/2`**: open + `json.load()` + convert. Fail on file/parse error.
- **`WriteFile/2`**: convert + `json.dump()` + write. Fail on serialization error.
- **Nested DictTerms**: the converters must be recursive — a JSON object
  containing objects produces nested DictTerms.

### Bidirectionality

`Parse/2` is primarily `String → Term` and `Generate/2` is `Term → String`.
They are NOT bidirectional (unlike atom_concat). Parsing requires a ground string;
generation requires a ground term. This matches the inherently asymmetric nature
of serialization.

`Get/3` with unbound Key enumerates all key-value pairs via backtracking —
this is the one relational predicate in the module.

### Test plan (~30 tests)

**Parse/2:**
- Parse simple object → DictTerm with correct keys/values.
- Parse nested object → nested DictTerms.
- Parse array → Python list.
- Parse scalars: string, int, float, bool, null.
- Parse empty object `{}` → empty DictTerm.
- Parse empty array `[]` → empty list.
- Unbound string arg fails.
- Invalid JSON string fails (no exception, just failure).

**Generate/2:**
- Generate from DictTerm → valid JSON string.
- Generate from nested DictTerm → nested JSON.
- Generate from list → JSON array.
- Generate from scalars.
- Unbound Var in term raises instantiation error.
- Round-trip: `Parse(S, T), Generate(T, S2)` — S and S2 are equivalent JSON.

**PrettyGenerate/2:**
- Output contains newlines and indentation.

**Get/3:**
- Key bound → extract value.
- Key not in dict → fail.
- Key unbound → enumerate all pairs.

**ReadFile/2, WriteFile/2:**
- Round-trip via temp file.
- Non-existent file fails.

---

## 3c — CSV Module

**Files:** `clausal/modules/py/csv.py` (new), `clausal/modules/csv_mod.py`
(alias), `tests/test_csv_module.py` (new)

### Predicates

Predicates are unprefixed — the module namespace (`py.csv`) provides the
context. Import via `-import_from(py.csv, [Parse, ParseRow, ReadFile, ...])` or
use qualified: `py.csv.Parse(S, Rows)`.

| Predicate | Description |
|---|---|
| `ParseRow/2` | `ParseRow(String, Row)` — parse a single CSV line into a list of strings. |
| `Parse/2` | `Parse(String, Rows)` — parse a multi-line CSV string into a list of rows (each row a list of strings). |
| `ParseRecords/3` | `ParseRecords(String, Headers, Records)` — parse CSV with first row as headers; each record is a DictTerm. |
| `Generate/2` | `Generate(Rows, String)` — serialize a list of rows (lists of values) to CSV string. |
| `GenerateRecords/3` | `GenerateRecords(Headers, Records, String)` — serialize DictTerm records with header row. |
| `ReadFile/2` | `ReadFile(Path, Rows)` — read and parse a CSV file into list of rows. |
| `ReadRecords/2` | `ReadRecords(Path, Records)` — read CSV file with headers → list of DictTerms. |
| `WriteFile/2` | `WriteFile(Path, Rows)` — serialize rows and write to CSV file. |

### Implementation notes

- Wrap Python `csv` module. Use `csv.reader` / `csv.writer` with `io.StringIO`
  for in-memory parsing/generation.
- **`ParseRecords/3`**: uses `csv.DictReader`. Each record becomes a
  `DictTerm`. Headers bound to the header list.
- **`Generate/2`**: deref all values, write via `csv.writer` to `StringIO`,
  return the string.
- All values in CSV are strings by default. No automatic type coercion
  (users can use `++int(X)` or `number_chars` for conversion). This avoids
  surprising behavior.
- **Delimiter option**: initially hardcode comma delimiter. If custom delimiters
  are needed, add `Parse/3` with an options DictTerm later. YAGNI for now.

### Test plan (~25 tests)

**ParseRow/2:**
- Simple row: `"a,b,c"` → `["a", "b", "c"]`.
- Quoted fields: `'"hello, world",b'` → `["hello, world", "b"]`.
- Empty string → empty list or single empty field.

**Parse/2:**
- Multi-line string → list of rows.
- Empty input → empty list.
- Mixed quoted/unquoted fields.

**ParseRecords/3:**
- Headers extracted correctly.
- Records are DictTerms with header keys.
- Single row (headers only) → empty records list.

**Generate/2:**
- List of rows → CSV string.
- Values with commas get quoted.
- Round-trip: `Parse(S, R), Generate(R, S2)` — equivalent.

**GenerateRecords/3:**
- DictTerm records with headers → CSV string with header row.

**ReadFile/2, WriteFile/2:**
- Round-trip via temp file.
- Non-existent file fails.

**ReadRecords/2:**
- File with headers → DictTerm list.

---

## File Summary

### New files

| File | Purpose |
|---|---|
| `clausal/modules/py/random.py` | Random module implementation |
| `clausal/modules/py/json.py` | JSON module implementation |
| `clausal/modules/py/csv.py` | CSV module implementation |
| `clausal/modules/random_mod.py` | Backward-compatible alias |
| `clausal/modules/json_mod.py` | Backward-compatible alias |
| `clausal/modules/csv_mod.py` | Backward-compatible alias |
| `tests/test_random_module.py` | Random module tests (~25) |
| `tests/test_json_module.py` | JSON module tests (~30) |
| `tests/test_csv_module.py` | CSV module tests (~25) |
| `docs/random.md` | Random module docs |
| `docs/json.md` | JSON module docs |
| `docs/csv.md` | CSV module docs |

### Modified files

| File | Change |
|---|---|
| `clausal/modules/__init__.py` | Add py.random, py.json, py.csv to docstring |
| `clausal/modules/py/__init__.py` | Add import examples to docstring |
| `docs/index.md` | Link to new module docs |
| `mkdocs.yml` | Add nav entries |

---

## Implementation Order

1. **3a — Random** (simplest, no DictTerm involvement, good warmup)
2. **3b — JSON** (DictTerm integration, recursive converters)
3. **3c — CSV** (builds on JSON patterns, DictTerm for records)

Each sub-phase is independently testable and deployable.

---

## Usage Examples

### Random

```python
# clausal file
-import_from(py.random, [Random, RandomInteger, RandomMember, RandomSeed, Maybe])

roll_die(N) <- RandomInteger(1, 6, N)

pick_color(COLOR) <- RandomMember(["red", "green", "blue"], COLOR)

maybe_print(X) <- (Maybe, writeln(X))
```

### JSON

```python
# clausal file
-import_from(py.json, [Parse, Generate, Get, ReadFile])

load_config(CONFIG) <- ReadFile("config.json", CONFIG)

get_name(CONFIG, NAME) <- Get(CONFIG, "name", NAME)

config_to_json(CONFIG, JSON) <- Generate(CONFIG, JSON)
```

Or with qualified names (no import collisions):

```python
# clausal file
-import_module(py.json)
-import_module(py.csv)

load_config(CONFIG) <- py.json.ReadFile("config.json", CONFIG)

load_data(RECORDS) <- py.csv.ReadRecords("data.csv", RECORDS)
```

### CSV

```python
# clausal file
-import_from(py.csv, [ReadRecords, ParseRow])

load_data(RECORDS) <- ReadRecords("data.csv", RECORDS)

parse_line(LINE, ROW) <- ParseRow(LINE, ROW)
```
