# Dicts and Sets

Clausal Prolog has first-class support for dictionaries and sets as logic terms. Unlike plain Python `dict` and `set`, `DictTerm` and `SetTerm` participate in unification — dict values can contain logic variables that bind during search, and sets unify by element equality.

!!! note "Clausal Prolog and the seam"

    [Clausal Prolog](clausal_prolog.md) (`.clausal`) reaches dicts and sets
    through **predicates only**: build a dict with `dict_pairs/2` and a set
    with `set_list/2`, then use the `dict_*`, `set_*`, `get/3,4`,
    `get_strict/3`, `tri_get/3` and `delete/3` builtins below. The
    examples of those builtins are `.clausal`. The *literal* syntax —
    `{k: v}` dicts, `{a, b}` sets, `P["k"]` subscripts, `D.k` dot access
    and `{**old, k: v}` splats — belongs to the [seam](syntax.md),
    Clausal's Python-syntax surface, and has no `.clausal` spelling; the
    sections that describe it say so and keep the seam spelling. A dict
    prints as `{a:1,b:2}` and a set as `{1,2,3}`.

---

## DictTerm

`DictTerm` is a unification-aware dictionary. Keys must be ground and hashable — an atom (`k`, `'k'`), a string, an int, or any other hashable ground term. An atom key and the same-spelled string key are **distinct** (see [Key kinds](#the-python-dict-surface) below). Values may be logic variables.

!!! note "A double-quoted key is a STRING key"
    A double-quoted literal is a string (the default since 2026-09-26), so
    `{"x": 0}` is keyed by the string `"x"`. Dot access (`D.x`) and the dicts
    the `py.*` wrappers return are keyed by **atoms**, so prefer atom keys
    (`{'x': 0}`, or a declared bare `x`) for record-like data. The examples
    below use string keys only where the point does not depend on the key kind.
    (That is the seam's literal; in `.clausal`, `dict_pairs(D, ["x"-0])` is
    the string-keyed dict and `dict_pairs(D, [x-0])` the atom-keyed one.)

### Syntax

In [seam (`.seam`) files](syntax.md), Python dict literals `{k: v, ...}` are automatically wrapped as `DictTerm`. (In `.clausal`, `dict_pairs(D, [x-0, y-0])` builds the same dict; there is no literal.) The `python` blocks in this section and the next ones, up to [Backtracking](#backtracking), are seam; the `clausal` blocks beside them are the same examples in `.clausal`:

```python
# Fact with a ground dict
point_type({"x": 0, "y": 0}, "origin"),

# Clause head with variable values — X and Y bind on unification
get_x({"x": X, "y": Y_}, X),

# Dict construction in body
make_point(X, Y, P) <- (P is {"x": X, "y": Y})
```

### Unification semantics

Two `DictTerm`s unify iff:

1. They have the **same set of keys**
2. Values for each key unify pairwise

```clausal
test("dicts unify key by key") :-
    dict_pairs(D, [a-1, b-2]),
    dict_pairs(E, [a-X, b-Y]),
    D = E,
    X == 1,
    Y == 2.

test("different key sets do not unify") :-
    dict_pairs(D, [a-1]),
    dict_pairs(E, [b-1]),
    \+ D = E.

test("a value mismatch does not unify") :-
    dict_pairs(D, [a-1]),
    dict_pairs(E, [a-2]),
    \+ D = E.
```

In the seam, with literals:

```python
# Succeeds: same keys, values unify
{"a": 1, "b": 2} is {"a": X, "b": Y}   # X=1, Y=2

# Fails: different key sets
not ({"a": 1} is {"b": 1})

# Fails: value mismatch
not ({"a": 1} is {"a": 2})
```

A `DictTerm` also unifies with a plain Python `dict` of the same keys (one
passed in through `++`), and the two compare equal.

A logic variable unifies with a `DictTerm` by binding to it:

```python
X is {"key": "val"}   # X binds to DictTerm({"key": "val"})
```

### Nested dicts

Dicts can be nested, and unification recurses into nested values:

```python
get_city({"address": {"city": CITY}}, CITY),

# Query:
get_city({"address": {"city": "London"}}, C)   # C = "London"
```

### Head pattern matching

when a `DictTerm` appears in a clause head, the compiler generates a wildcard capture plus a unification guard. The guard:

1. Pre-allocates `Var()` objects for variable positions in the dict values
2. Constructs the expected `DictTerm` with those variables
3. Calls `unify(captured_arg, expected_dict, trail)`

This means dict patterns in heads work bidirectionally — they match incoming `DictTerm` arguments and also bind when the argument is an unbound variable.

### Body construction

Dict literals in clause bodies construct `DictTerm` objects at runtime. Logic variables in values are dereferenced at construction time if bound, or remain as `Var` objects if unbound.

### Splat sugar

Python's dict unpacking syntax `{**old, "k": v}` is supported in clause bodies. It constructs a new `DictTerm` by merging:

```python
# Add or overwrite a key
update_name(OLD, NAME, NEW) <- (NEW is {**OLD, "name": NAME})

# Merge two dicts (right side wins on conflict)
merge_defaults(DEFAULTS, OVERRIDES, RESULT) <-
    (RESULT is {**DEFAULTS, **OVERRIDES})
```

This compiles to `DictTerm({**deref(OLD).data, "name": NAME})` at runtime. The splat argument must be a bound `DictTerm` at call time.

### Partial dict matching — `sub_dict/2`

`sub_dict(Pattern, Dict)` succeeds when `Pattern`'s keys are a subset of `Dict`'s keys and the values for those keys unify pairwise. Extra keys in `Dict` are ignored.

```python
# Extract the name field from any dict
get_name(PERSON, NAME) <- sub_dict({"name": NAME}, PERSON)

# Check role without caring about other fields
is_admin(PERSON) <- sub_dict({"role": "admin"}, PERSON)
```

Compare with full unification:

```python
# Full unification: PERSON must have EXACTLY these two keys
exact(PERSON, NAME) <- (PERSON is {"name": NAME, "role": "admin"})

# Partial match: PERSON may have any other keys
partial(PERSON, NAME) <- sub_dict({"name": NAME, "role": "admin"}, PERSON)
```

### Backtracking

`DictTerm` unification is fully backtrackable. If a pairwise value unification fails partway through, all bindings made so far are undone via the trail. See [Lists](lists.md) for the set operations available on plain lists.

---

## The Python dict surface

Alongside the KEY-first `dict_*` family below, dicts carry a first-class
surface that mirrors Python's own dict API one-to-one. These are always
available — no import required — and each maps onto the Python operation a
reader already knows:

| Operation | Seam form | Python analogue | On an absent key |
|---|---|---|---|
| read (strict) | `V is P["k"]` | `d[k]` | **throws** `existence_error(dict_key, …)` |
| read (strict, predicate form) | `get_strict(P, "k", V)` | `d[k]` | **throws** `existence_error(dict_key, …)` |
| read (soft) | `get(P, "k", V)` | `d.get(k)` | **fails** the clause |
| read (defaulted) | `get(P, "k", V, Default)` | `d.get(k, default)` | binds `Default` |
| read (Kleene) | `tri_get(P, "k", V)` | — | binds `Undefined` |
| membership | `"k" in P` | `k in d` | fails |
| set (functional) | `P2 is {**P, "k": V}` | `{**d, k: v}` | always succeeds; last-wins |
| default-merge | `P2 is {"k": Default, **P}` | `{k: default, **d}` | `P` wins if present |
| delete (functional) | `delete(P, 'k', P2)` | `del d[k]` | **throws** |

In the seam:

```seam
role_of(PROFILE, R) <- (R is PROFILE['role'])

city_or_default(PROFILE, C) <- get(PROFILE, 'city', C, 'unknown')

promote(PROFILE, P2) <- (P2 is {**PROFILE, 'role': 'admin'})

drop_draft(PROFILE, P2) <- delete(PROFILE, 'draft', P2)
```

In Clausal Prolog (`.clausal`), as in ISO syntax (a `.pl` file on the
native front end), dicts have **predicate forms only** — no dict literal
and no subscript: build with `dict_pairs/2`, read with `get/3` (soft),
`get_strict/3` (strict), `get/4` (defaulted) or `tri_get/3`, update with
`dict_put/4` and `dict_put_pairs/3`, delete with `delete/3`. The same four
rules in `.clausal`:

```clausal
role_of(PROFILE, R) :-
    get_strict(PROFILE, role, R).

city_or_default(PROFILE, C) :-
    get(PROFILE, city, C, unknown).

promote(PROFILE, P2) :-
    dict_put(role, admin, PROFILE, P2).

drop_draft(PROFILE, P2) :-
    delete(PROFILE, draft, P2).

test("profile reads and updates") :-
    dict_pairs(P, [draft-true, role-user]),
    role_of(P, R),
    R == user,
    city_or_default(P, C),
    C == unknown,
    promote(P, P2),
    get(P2, role, admin),
    drop_draft(P, P3),
    dict_pairs(P3, [role-user]).

test("strict and soft reads of an absent key") :-
    dict_pairs(P, [role-admin]),
    catch(get_strict(P, city, _), error(existence_error(dict_key, K), _), true),
    K == city,
    \+ get(P, city, _),
    tri_get(P, city, U),
    U == undefined.
```

Choosing a read: the strict subscript (or `get_strict/3`) is for keys the clause is entitled to
assume (a typo should be loud); `get/3` is for keys whose absence should just
fail this one rule rather than abort the query; `get/4` when a default is
the honest answer; `tri_get/3` when absence means the three-valued
`Undefined`, not failure.

Keys may be atoms, strings, or ints. An atom key and the same-spelled **string**
key are **distinct** — atoms and strings are disjoint kinds and never unify
([Syntax § Atoms vs strings](syntax.md#atoms-vs-strings)) — exactly as in
head-position dict patterns above:

```seam
--8<-- "tests/fixtures/docs/dicts_sets_sigs.txt:atom_vs_string_keys"
```

The same in `.clausal`, where a bare `k` is an atom without a declaration:

```clausal
config(D) :-
    dict_pairs(D, [k-1]).       % atom key

labels(D) :-
    dict_pairs(D, ["k"-1]).     % string key -- a DIFFERENT dict

test("atom and string keys are distinct") :-
    config(D),
    \+ labels(D),
    get(D, k, V),
    V == 1,
    \+ get(D, "k", _).
```

A `"k"` key is a string (under a module's temporary
[`-double_quotes(atom)`](directives.md#-double_quotes) setting it is the atom
instead); a bare `k` or a single-quoted `'k'` is always an atom. Dot access `D.k` looks
up the **atom** `k`, so the dot syntax and a bare-key literal agree. Result
dicts built by the `py.*` wrappers (`py.json.parse/2`, `py.process`,
`py.url.parse/2`, `py.csv`) key by **atoms**, which is what makes `R.stdout`
and `get(R, stdout, V)` work.

All of these accept a plain Python `dict` argument wherever a `DictTerm` is
accepted (the two unify and compare equal), as does the whole `dict_*`/`set_*`
family below. `length/2` does **not** count dict keys — a dict is not a
sequence (`length(D, N)` fails); use `dict_size/2`.

---

## SetTerm

`SetTerm` is a unification-aware set. Elements must be ground (hashable). Backed by `frozenset` for immutability.

### Syntax

In seam (`.seam`) files, Python set literals `{a, b, c}` produce `SetTerm` objects when the elements are ground constants. (In `.clausal`, `set_list(S, [1, 2, 3])` builds the set; there is no literal.)

```python
colors({1, 2, 3}),
primary({"red", "green", "blue"}),
```

### Unification semantics

Two `SetTerm`s unify iff they contain the **same elements** (order irrelevant, since they are sets):

```clausal
test("sets unify by elements") :-
    set_list(A, [1, 2, 3]),
    set_list(B, [3, 1, 2]),
    A = B.

test("different elements do not unify") :-
    set_list(A, [1, 2]),
    set_list(B, [1, 2, 3]),
    \+ A = B.
```

In the seam, with literals:

```python
# Succeeds: same elements regardless of order
{1, 2, 3} is {3, 1, 2}

# Fails: different elements
not ({1, 2} is {1, 2, 3})
```

A logic variable unifies with a `SetTerm` by binding to it.

### Variables in sets

**Not supported.** Set elements must be ground because `frozenset` requires hashable elements. A set containing an unbound logic variable would break hashing. For patterns with variable elements, use `gen_set/2` to enumerate elements.

---

## Dict builtins

All dict builtins are in `clausal/logic/builtins/dict_set.py`. They accept a `DictTerm` (or, from the seam, a plain Python `dict` passed in with `++`) for any dict argument.

### `is_dict/1`
```text
--8<-- "tests/fixtures/docs/dicts_sets_sigs.txt:is_dict_1"
```
Succeeds if `Term` is a `DictTerm`.

### `is_dict_t/2`
```text
--8<-- "tests/fixtures/docs/dicts_sets_sigs.txt:is_dict_t_2"
```
The reified `is_dict/1`: `T` is `true` if `Term` is a dict (a `DictTerm`, or a
plain Python `dict` from the seam), `false` for any other nonvar term, with
one answer and no choice point. An unbound `Term` raises
`instantiation_error`; a bound `T` makes it a test (a `T` that is neither
`true` nor `false` fails, as it does for `dif_t/3`). `if_/3` from
library(reif) calls it with `T` appended, so it can choose a branch:

```clausal
:- use_module(library(reif)).

shape(P, S) :-
    if_(is_dict_t(P), S = dict, S = other).

test("a dict is true, anything else false") :-
    dict_pairs(D, [a-1]),
    is_dict_t(D, T),
    T == true,
    is_dict_t([], F),
    F == false.

test("is_dict_t/2 as an if_/3 condition") :-
    dict_pairs(D, []),
    shape(D, S1),
    S1 == dict,
    shape([a-1], S2),
    S2 == other.

test("one answer, no choice point") :-
    findall(T, is_dict_t(a, T), Ts),
    Ts == [false].
```

### `dict_size/2`
```text
--8<-- "tests/fixtures/docs/dicts_sets_sigs.txt:dict_size_2"
```
`N` is the number of keys in `Dict`.

### `dict_keys/2`
```text
--8<-- "tests/fixtures/docs/dicts_sets_sigs.txt:dict_keys_2"
```
`Keys` is the sorted list of keys. Keys are sorted by `repr` for determinism across key types.

### `dict_values/2`
```text
--8<-- "tests/fixtures/docs/dicts_sets_sigs.txt:dict_values_2"
```
`Values` is the list of values in key-sorted order (same ordering as `dict_keys`).

### `dict_pairs/2`
```text
--8<-- "tests/fixtures/docs/dicts_sets_sigs.txt:dict_pairs_2"
```
Bidirectional conversion between a `DictTerm` and a list of `Key-Value`
pairs: the `'-'(Key, Value)` cell, as in the [pairs library](pairs.md). In the
dict→pairs direction the pairs are sorted by key.

```clausal
test("dict to pairs") :-
    dict_pairs(D, [b-2, a-1]),
    dict_pairs(D, PAIRS),
    PAIRS == [a-1, b-2].

test("pairs to dict") :-
    dict_pairs(DICT, [x-10, y-20]),
    dict_get(y, DICT, 20).
```

### `dict_get/3`
```text
--8<-- "tests/fixtures/docs/dicts_sets_sigs.txt:dict_get_3"
```
Semidet: succeeds if `Key` is in `Dict` and `Value` unifies with `Dict[Key]`. Fails if the key is absent or `Key` is unbound.

```clausal
test("dict_get") :-
    dict_pairs(D, [name-"Alice", age-30]),
    dict_get(name, D, NAME),
    NAME == "Alice".
```

### `dict_put/4`
```text
--8<-- "tests/fixtures/docs/dicts_sets_sigs.txt:dict_put_4"
```
`NewDict` is `OldDict` with `Key → Value` inserted or overwritten. Returns a new `DictTerm`; the original is unchanged.

```clausal
test("dict_put") :-
    dict_pairs(D, [a-1, b-0]),
    dict_put(b, 99, D, NEW),
    dict_pairs(NEW, [a-1, b-99]),
    dict_get(b, D, 0).
```

### `dict_put_pairs/3`
```text
--8<-- "tests/fixtures/docs/dicts_sets_sigs.txt:dict_put_pairs_3"
```
Bulk update: `Pairs` is a list of `Key-Value` pairs, equivalent to calling
`dict_put/4` for each pair in order.

```clausal
test("bulk update") :-
    dict_pairs(D, [a-1]),
    dict_put_pairs([b-2, c-3], D, NEW),
    dict_pairs(NEW, [a-1, b-2, c-3]).
```

### `dict_remove/3`
```text
--8<-- "tests/fixtures/docs/dicts_sets_sigs.txt:dict_remove_3"
```
`NewDict` is `OldDict` without `Key`. Fails if `Key` is not present.

```clausal
test("dict_remove") :-
    dict_pairs(D, [a-1, b-2, c-3]),
    dict_remove(b, D, NEW),
    dict_pairs(NEW, [a-1, c-3]).

test("dict_remove of an absent key fails") :-
    dict_pairs(D, [a-1]),
    \+ dict_remove(b, D, _).
```

### `dict_merge/3`
```text
--8<-- "tests/fixtures/docs/dicts_sets_sigs.txt:dict_merge_3"
```
`Merged` is the union of `D1` and `D2`. Where keys conflict, `D2`'s value wins.

```clausal
test("dict_merge") :-
    dict_pairs(D1, [a-1, b-0]),
    dict_pairs(D2, [b-99, c-3]),
    dict_merge(D1, D2, MERGED),
    dict_pairs(MERGED, [a-1, b-99, c-3]).
```

### `gen_dict/3`
```text
--8<-- "tests/fixtures/docs/dicts_sets_sigs.txt:gen_dict_3"
```
Nondeterministic: on backtracking, enumerates all key-value pairs in `Dict` (the dict analogue of `gen_assoc/3` in Scryer's `library(assoc)`).

```clausal
% Enumerate all pairs: KEY = a, VALUE = 1; then KEY = b, VALUE = 2
test("gen_dict enumerates") :-
    dict_pairs(D, [a-1, b-2]),
    findall(KEY-VALUE, gen_dict(KEY, D, VALUE), L),
    L == [a-1, b-2].

% Select by key: one solution
test("gen_dict by key") :-
    dict_pairs(D, [a-1, b-2]),
    findall(VALUE, gen_dict(a, D, VALUE), L),
    L == [1].
```

### `sub_dict/2`
```text
--8<-- "tests/fixtures/docs/dicts_sets_sigs.txt:sub_dict_2"
```
Partial dict matching: succeeds when every key in `Pattern` is also in `Dict`, and the corresponding values unify. Extra keys in `Dict` are ignored.

```clausal
test("sub_dict binds") :-
    dict_pairs(P, [name-NAME]),
    dict_pairs(D, [name-"Alice", age-30]),
    sub_dict(P, D),
    NAME == "Alice".

test("sub_dict ignores extra keys") :-
    dict_pairs(P, [role-admin]),
    dict_pairs(D, [name-"Bob", role-admin, dept-eng]),
    sub_dict(P, D).

test("sub_dict fails on a value mismatch") :-
    dict_pairs(P, [role-admin]),
    dict_pairs(D, [name-"Alice", role-user]),
    \+ sub_dict(P, D).

test("sub_dict fails on an absent key") :-
    dict_pairs(P, [z-1]),
    dict_pairs(D, [x-1, y-2]),
    \+ sub_dict(P, D).
```

---

## Set builtins

### `is_set/1`
```text
--8<-- "tests/fixtures/docs/dicts_sets_sigs.txt:is_set_1"
```
Succeeds if `Term` is a `SetTerm`.

### `set_size/2`
```text
--8<-- "tests/fixtures/docs/dicts_sets_sigs.txt:set_size_2"
```
`N` is the cardinality of `Set`.

### `set_list/2`
```text
--8<-- "tests/fixtures/docs/dicts_sets_sigs.txt:set_list_2"
```
Bidirectional conversion between a `SetTerm` and a sorted list.

```clausal
% List -> set (duplicates removed), set -> list (sorted)
test("set_list") :-
    set_list(SET, [3, 1, 2, 1]),
    set_size(SET, 3),
    set_list(SET, LIST),
    LIST == [1, 2, 3].
```

### `set_union/3`
```text
--8<-- "tests/fixtures/docs/dicts_sets_sigs.txt:set_union_3"
```
`union` is the set union of `S1` and `S2`.

### `set_intersection/3`
```text
--8<-- "tests/fixtures/docs/dicts_sets_sigs.txt:set_intersection_3"
```
`Inter` is the set intersection of `S1` and `S2`.

### `set_subtract/3`
```text
--8<-- "tests/fixtures/docs/dicts_sets_sigs.txt:set_subtract_3"
```
`Diff` is `S1` minus `S2` (elements in `S1` not in `S2`).

### `set_sym_diff/3`
```text
--8<-- "tests/fixtures/docs/dicts_sets_sigs.txt:set_sym_diff_3"
```
`Sym` is the symmetric difference of `S1` and `S2` (elements in exactly one of the two sets).

### `set_subset/2`
```text
--8<-- "tests/fixtures/docs/dicts_sets_sigs.txt:set_subset_2"
```
Succeeds if every element of `Sub` is also in `Super`. An empty set is a subset of any set.

### `set_disjoint/2`
```text
--8<-- "tests/fixtures/docs/dicts_sets_sigs.txt:set_disjoint_2"
```
Succeeds if `S1` and `S2` have no elements in common.

### `set_add/3`
```text
--8<-- "tests/fixtures/docs/dicts_sets_sigs.txt:set_add_3"
```
`NewSet` is `OldSet` with `Elem` added. If `Elem` is already present, `NewSet = OldSet`.

### `set_remove/3`
```text
--8<-- "tests/fixtures/docs/dicts_sets_sigs.txt:set_remove_3"
```
`NewSet` is `OldSet` with `Elem` removed. If `Elem` is absent, `NewSet = OldSet`.

```clausal
test("set algebra") :-
    set_list(A, [1, 2]),
    set_list(B, [2, 3]),
    set_union(A, B, U), set_list(U, [1, 2, 3]),
    set_intersection(A, B, I), set_list(I, [2]),
    set_subtract(A, B, D), set_list(D, [1]),
    set_sym_diff(A, B, X), set_list(X, [1, 3]).

test("set_add and set_remove") :-
    set_list(A, [1]),
    set_add(2, A, B), set_list(B, [1, 2]),
    set_remove(1, B, C), set_list(C, [2]),
    set_add(1, A, A2), A2 == A,
    set_remove(5, A, A3), A3 == A.
```

### `gen_set/2`
```text
--8<-- "tests/fixtures/docs/dicts_sets_sigs.txt:gen_set_2"
```
Nondeterministic: on backtracking, enumerates all elements of `Set` in a deterministic order (sorted by `repr`).

```clausal
% ELEM = a; ELEM = b; ELEM = c (on backtracking)
test("gen_set") :-
    set_list(S, [c, a, b]),
    findall(ELEM, gen_set(ELEM, S), L),
    L == [a, b, c].
```

---

## The `__unify__` protocol

DictTerm and SetTerm unification is powered by a generic extension point in the C unifier. Any Python object can define a `__unify__(self, other, trail)` method:

- Return `True` — unification succeeded (bindings made on `trail`)
- Return `False` — unification failed
- Return `NotImplemented` — fall through to the default `==` comparison

The C extension calls `__unify__` after checking tuples and lists, before the `==` fallback. Two companion protocols are also supported:

- `__walk__(self)` — called by `walk()` to substitute bound variables inside the term
- `__occurs_check__(self, var)` — called by occurs-check to detect circular references

These protocols allow custom term types to participate in unification without modifying the C extension.

---

## Python API

`DictTerm` and `SetTerm` are **not** part of the 1.0 public API
([Public API](public-api.md)): the covered way to read one that comes back
from a query is `clausal.to_python`, which gives a `dict` or a `frozenset`.
The classes themselves, for code that works below that line:

```python
from clausal.terms import DictTerm, SetTerm

# Construction
d = DictTerm({"x": 1, "y": 2})
s = SetTerm([1, 2, 3])

# DictTerm access
d["x"]          # 1
d.keys()        # dict_keys(["x", "y"])
d.values()      # dict_values([1, 2])
d.items()       # dict_items([("x", 1), ("y", 2)])
len(d)          # 2
"x" in d        # True

# SetTerm access
len(s)          # 3
1 in s          # True
list(s)         # [1, 2, 3] (iteration order unspecified)

# Unification (C-level)
from clausal.logic.variables import Var, Trail, unify, deref

t = Trail()
x = Var()
unify(DictTerm({"a": x, "b": 2}), DictTerm({"a": 42, "b": 2}), t)
deref(x)  # 42
```

---

## Current status

| Feature | Status |
|---|---|
| `DictTerm`/`SetTerm` classes, `__walk__`/`__occurs_check__` hooks | Done |
| `__unify__` protocol in C, AST transform (`visit_Dict` → `DictTerm`), compiler head/body support | Done |
| Dict builtins: `is_dict`, `dict_size`, `dict_keys`, `dict_values`, `dict_pairs`, `dict_get`, `dict_put`, `dict_put_pairs`, `dict_remove`, `dict_merge`, `gen_dict`, `sub_dict` | Done |
| Set builtins: `is_set`, `set_size`, `set_list`, `set_union`, `set_intersection`, `set_subtract`, `set_sym_diff`, `set_subset`, `set_disjoint`, `set_add`, `set_remove`, `gen_set` | Done |
| Splat sugar: `{**old, "k": v}` in clause bodies | Done |
| `trail.record(callable)` — generic callback hook for backtrackable mutable state | Done |

---

## Limitations

- **Keys must be bound when the dict is built**: in the seam, `(K is 'k', D is {K: 1})` works, but `{X: 1}` with `X` unbound raises `error(instantiation_error, '{key}'/1)`. In `.clausal`, `dict_pairs(D, [K-1])` with `K` unbound fails.
- **No variable set elements**: Set elements must be ground/hashable.
- **Splat requires a bound dict** (seam): `{**OLD, 'k': V}` requires `OLD` to be bound to a dict at runtime. Unbound `OLD` raises `error(instantiation_error, '{**}'/1)`.
- **No mutable variants**: Mutable dict/set types were considered and rejected — the [`++()` Python escape](python_integration.md) covers accumulation patterns with idiomatic, explicit syntax. Use `trail.record()` directly if you need backtrackable undo of custom mutable state.

---

*See also: [Python Interop](python_integration.md) — `++()` escape for dict/set mutation patterns · [Builtins](builtins.md) — full predicate index including dict and set predicates.*
