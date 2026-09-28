# Pairs

Pair predicates work with [lists](lists.md) of `Key-Value` pairs, as in Scryer's
`library(pairs)`. For proper key-value mappings with unification support, see
[Dicts & Sets](dicts_sets.md).

!!! note "How a pair is spelled"
    A pair is the term `Key-Value`: the cell `'-'(Key, Value)`. The pair
    predicates also read a pair written in source as `k - v`, but that spelling
    is the arithmetic node, which `==` and unification do not identify with the
    cell. A pair the predicates **build** is always the cell, so compare one
    against `'-'(k, v)`, not `k - v`.

These predicates are Scryer's, clause for clause. They raise no errors: an
argument that is not a list, or an element that is not a pair, makes them fail.
An unbound argument or a partial list enumerates, as the Prolog definition does.

---

## Quick Example

```clausal
test("unzip") <- (
    pairs_keys_values([1 - 'a', 2 - 'b', 3 - 'c'], KEYS, VALUES),
    KEYS == [1, 2, 3],
    VALUES == ['a', 'b', 'c']
)
```

---

## Predicates

### pairs_keys_values/3

`pairs_keys_values(Pairs, Keys, Values)` — relates a list of pairs to its keys and
its values, in every direction.

**Decompose mode** (Pairs bound):

```clausal
test("decompose") <- (
    pairs_keys_values(['name' - 'alice', 'age' - 30], KS, VS),
    KS == ['name', 'age'],
    VS == ['alice', 30]
)
```

**Construct mode** (Keys and Values bound):

```clausal
test("construct") <- (
    pairs_keys_values(PAIRS, ['x', 'y', 'z'], [1, 2, 3]),
    PAIRS == ['-'('x', 1), '-'('y', 2), '-'('z', 3)]
)
```

Any one proper list fixes the length: `pairs_keys_values(P, ['x', 'y'], V)` gives
`P = ['-'('x', _A), '-'('y', _B)]` and `V = [_A, _B]`.

```clausal
test("not a pair fails") <- (not pairs_keys_values([1 - 'a', 'b'], _K, _V))
```

### pairs_keys/2

`pairs_keys(Pairs, Keys)` — the keys: `pairs_keys_values(Pairs, Keys, _)`.

```clausal
test("keys") <- pairs_keys([1 - 'a', 2 - 'b', 3 - 'c'], [1, 2, 3])
```

### pairs_values/2

`pairs_values(Pairs, Values)` — the values: `pairs_keys_values(Pairs, _, Values)`.

```clausal
test("values") <- pairs_values([1 - 'a', 2 - 'b', 3 - 'c'], ['a', 'b', 'c'])
```

### group_pairs_by_key/2

`group_pairs_by_key(Pairs, Groups)` — groups **adjacent** pairs whose keys are
identical (`==`). Each group is `Key-Values`. It does not sort, so a key that
comes back after another key starts a new group:

```clausal
test("adjacent groups") <- (
    group_pairs_by_key(['a' - 1, 'a' - 2, 'b' - 3, 'a' - 4], GROUPS),
    GROUPS == ['-'('a', [1, 2]), '-'('b', [3]), '-'('a', [4])]
)
```

Sort the pairs first to collect every occurrence of a key:

```clausal
test("sort then group") <- (
    msort(['b' - 2, 'a' - 1, 'b' - 3], SORTED),
    group_pairs_by_key(SORTED, GROUPS),
    GROUPS == ['-'('a', [1]), '-'('b', [2, 3])]
)
```

### map_list_to_pairs/3

`map_list_to_pairs(Goal, List, Pairs)` — pairs each element `E` of `List` with
a key: `Pairs` is `[K1-E1, K2-E2, ...]` where `call(Goal, Ei, Ki)`. Every
solution of each call is an answer on backtracking. With `msort/2` and
`pairs_values/2` it sorts a list by a computed key:

```clausal
test("pair with a key") <- (
    map_list_to_pairs(length, [[1, 2, 3], [4], [5, 6]], PAIRS),
    PAIRS == ['-'(3, [1, 2, 3]), '-'(1, [4]), '-'(2, [5, 6])]
)

test("sort by length") <- (
    map_list_to_pairs(length, [[1, 2, 3], [4], [5, 6]], PAIRS),
    msort(PAIRS, SORTED),
    pairs_values(SORTED, BY_LENGTH),
    BY_LENGTH == [[4], [5, 6], [1, 2, 3]]
)
```

---

## Patterns & Recipes

### Lookup by key

```clausal
lookup(KEY, PAIRS, VALUE) <- in_('-'(KEY, VALUE), PAIRS)

test("lookup") <- lookup('b', ['-'('a', 1), '-'('b', 2), '-'('c', 3)], 2)
```

`in_/2` unifies, so the list holds cells here: a `k - v` element would not
unify with `'-'(KEY, VALUE)`.

### Sort pairs by key

Standard order compares the key first, so `msort/2` sorts pairs by key (and
by value within a key):

```clausal
test("sort by key") <- (
    msort(['-'('b', 2), '-'('a', 1), '-'('c', 3)], SORTED),
    pairs_keys(SORTED, ['a', 'b', 'c'])
)
```

### Invert a mapping (using [maplist](higher_order.md))

```clausal
swap_pair('-'(K, V), '-'(V, K)),

invert(PAIRS, INVERTED) <- (
    maplist(swap_pair, PAIRS, INVERTED)
)

test("invert") <- invert(['-'('a', 1), '-'('b', 2)], ['-'(1, 'a'), '-'(2, 'b')])
```

---

*See also: [Lists](lists.md) — general list operations,
[Dicts & Sets](dicts_sets.md) — DictTerm for proper key-value mapping (`dict_pairs/2`
reads and builds the same `Key-Value` pairs),
[Higher-Order](higher_order.md) — maplist, sort_by.*
