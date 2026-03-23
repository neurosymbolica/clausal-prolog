# Pairs

Pair predicates work with lists of two-element lists `[Key, Value]`, providing
key-value processing operations.

---

## Quick Example

```clausal
Test("unzip") <- (
    Unzip([[1, "a"], [2, "b"], [3, "c"]], KEYS, VALUES),
    KEYS == [1, 2, 3],
    VALUES == ["a", "b", "c"]
)
```

---

## Predicates

### Unzip/3

`Unzip(Pairs, Keys, Values)` — bidirectional conversion between a list of pairs
and separate key/value lists.

**Decompose mode** (Pairs bound):

```clausal
Test("decompose") <- (
    Unzip([["name", "alice"], ["age", 30]], KS, VS),
    KS == ["name", "age"],
    VS == ["alice", 30]
)
```

**Construct mode** (Keys + Values bound):

```clausal
Test("construct") <- (
    Unzip(PAIRS, ["x", "y", "z"], [1, 2, 3]),
    PAIRS == [["x", 1], ["y", 2], ["z", 3]]
)
```

Keys and Values must have equal length when constructing.

### PairKeys/2

`PairKeys(Pairs, Keys)` — extract the first element from each pair.

```clausal
Test("keys") <- PairKeys([[1, "a"], [2, "b"], [3, "c"]], [1, 2, 3])
```

### PairValues/2

`PairValues(Pairs, Values)` — extract the second element from each pair.

```clausal
Test("values") <- PairValues([[1, "a"], [2, "b"], [3, "c"]], ["a", "b", "c"])
```

---

## Patterns & Recipes

### Lookup by key

```clausal
lookup(KEY, PAIRS, VALUE) <- In([KEY, VALUE], PAIRS)

Test("lookup") <- lookup("b", [["a", 1], ["b", 2], ["c", 3]], 2)
```

### Sort pairs by key

```clausal
Test("sort by key") <- (
    SortBy((P, K) <- GetItem(0, P, K), [["b", 2], ["a", 1], ["c", 3]], SORTED),
    PairKeys(SORTED, ["a", "b", "c"])
)
```

### Invert a mapping

```clausal
swap_pair([K, V], [V, K]),

invert(PAIRS, INVERTED) <- (
    MapList(swap_pair, PAIRS, INVERTED)
)

Test("invert") <- invert([["a", 1], ["b", 2]], [[1, "a"], [2, "b"]])
```

---

*See also: [Lists](lists.md) — general list operations,
[Dicts & Sets](dicts_sets.md) — DictTerm for proper key-value mapping,
[Higher-Order](higher_order.md) — MapList, SortBy for pair processing.*
