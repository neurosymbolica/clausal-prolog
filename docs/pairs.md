# Pairs

Pair predicates work with [lists](lists.md) of two-element lists `[Key, Value]`, providing
key-value processing operations. For proper key-value mappings with unification support, see [Dicts & Sets](dicts_sets.md).

---

## Quick Example

```clausal
Test("unzip") <- (
    pairs_keys_values([[1, "a"], [2, "b"], [3, "c"]], KEYS, VALUES),
    KEYS == [1, 2, 3],
    VALUES == ["a", "b", "c"]
)
```

---

## Predicates

### pairs_keys_values/3

`pairs_keys_values(Pairs, Keys, Values)` — bidirectional conversion between a list of pairs
and separate key/value lists.

**Decompose mode** (Pairs bound):

```clausal
Test("decompose") <- (
    pairs_keys_values([["name", "alice"], ["age", 30]], KS, VS),
    KS == ["name", "age"],
    VS == ["alice", 30]
)
```

**Construct mode** (Keys + Values bound):

```clausal
Test("construct") <- (
    pairs_keys_values(PAIRS, ["x", "y", "z"], [1, 2, 3]),
    PAIRS == [["x", 1], ["y", 2], ["z", 3]]
)
```

Keys and Values must have equal length when constructing.

### pairs_keys/2

`pairs_keys(Pairs, Keys)` — extract the first element from each pair.

```clausal
Test("keys") <- pairs_keys([[1, "a"], [2, "b"], [3, "c"]], [1, 2, 3])
```

### pairs_values/2

`pairs_values(Pairs, Values)` — extract the second element from each pair.

```clausal
Test("values") <- pairs_values([[1, "a"], [2, "b"], [3, "c"]], ["a", "b", "c"])
```

---

## Patterns & Recipes

### Lookup by key

```clausal
lookup(KEY, PAIRS, VALUE) <- in_([KEY, VALUE], PAIRS)

Test("lookup") <- lookup("b", [["a", 1], ["b", 2], ["c", 3]], 2)
```

### sort pairs by key

```clausal
Test("sort by key") <- (
    sort_by((P, K) <- get_item(0, P, K), [["b", 2], ["a", 1], ["c", 3]], SORTED),
    pairs_keys(SORTED, ["a", "b", "c"])
)
```

### Invert a mapping (using [maplist](higher_order.md))

```clausal
swap_pair([K, V], [V, K]),

invert(PAIRS, INVERTED) <- (
    maplist(swap_pair, PAIRS, INVERTED)
)

Test("invert") <- invert([["a", 1], ["b", 2]], [[1, "a"], [2, "b"]])
```

---

*See also: [Lists](lists.md) — general list operations,
[Dicts & Sets](dicts_sets.md) — DictTerm for proper key-value mapping,
[Higher-Order](higher_order.md) — maplist, sort_by for pair processing.*
