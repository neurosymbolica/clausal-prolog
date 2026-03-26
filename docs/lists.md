# Lists

Lists are the fundamental data structure in logic programming. Clausal uses
Python's native list syntax — no cons cells, no special notation.

---

## Quick Example

```clausal
palindrome(XS) <- (Reverse(XS, XS))

Test("palindrome") <- palindrome([1, 2, 1])
Test("not palindrome") <- (not palindrome([1, 2, 3]))
```

---

## List Syntax

```clausal
# skip
[]                     # empty list
[1, 2, 3]             # three elements
[HEAD, *TAIL]          # head/tail destructuring (like Prolog [H|T])
[A, B, *REST]          # first two elements + rest
```

Clause heads can describe list structure using `[HEAD, *TAIL]`, relating the
whole list to its parts:

```clausal
list_sum([], 0),
list_sum([X, *XS], TOTAL) <- (
    list_sum(XS, REST),
    TOTAL := X + REST
)
```

---

## Membership

### In/2

`In(Elem, List)` — the membership relation. Holds for each element in `List`
on backtracking.

```clausal
Test("member") <- In(2, [1, 2, 3])
Test("generate") <- (In(X, ["a", "b", "c"]), X == "b")
```

### InCheck/2

`InCheck(Elem, List)` — deterministic membership. Holds at most once (first
unifying element only). Use when you need to confirm membership without
enumerating alternatives.

```clausal
Test("check") <- InCheck("b", ["a", "b", "c"])
```

---

## Building & Joining

### Append/3

`Append(L1, L2, L3)` — relates three lists such that `L3` is `L1` followed by
`L2`. Works in all directions:

```clausal
# Concatenate
Test("concat") <- Append([1, 2], [3, 4], [1, 2, 3, 4])

# Split — enumerate all ways to split a list
Test("split") <- (
    Append(LEFT, RIGHT, [1, 2, 3]),
    LEFT == [1],
    RIGHT == [2, 3]
)

# Suffix extraction
Test("suffix") <- Append([1, 2], REST, [1, 2, 3, 4, 5])
```

### Replicate/3

`Replicate(N, Elem, List)` — `List` is `N` copies of `Elem`.

```clausal
Test("replicate") <- Replicate(3, "x", ["x", "x", "x"])
```

### Zip/3

`Zip(L1, L2, Pairs)` — pair up corresponding elements. Stops at the shorter
list.

```clausal
Test("zip") <- Zip([1, 2, 3], ["a", "b", "c"], [[1, "a"], [2, "b"], [3, "c"]])
```

---

## Access & Slicing

### Length/2

`Length(List, N)` — relates a list to its length. Can also generate a list of
`N` fresh variables.

```clausal
Test("length") <- Length([10, 20, 30], 3)
```

### GetItem/3

`GetItem(N, List, Elem)` — relates a 0-based index, a list, and an element.

```clausal
Test("get") <- GetItem(1, ["a", "b", "c"], "b")
Test("enumerate") <- (GetItem(I, [10, 20, 30], 20), I == 1)
```

### Last/2

`Last(List, Elem)` — the last element.

```clausal
Test("last") <- Last([1, 2, 3], 3)
```

### Take/3

`Take(N, List, Taken)` — first `N` elements.

```clausal
Test("take") <- Take(2, [1, 2, 3, 4], [1, 2])
```

### Drop/3

`Drop(N, List, Rest)` — everything after the first `N` elements.

```clausal
Test("drop") <- Drop(2, [1, 2, 3, 4], [3, 4])
```

### SplitAt/4

`SplitAt(N, List, Left, Right)` — split at index `N`.

```clausal
Test("split_at") <- SplitAt(2, [1, 2, 3, 4], [1, 2], [3, 4])
```

---

## Reordering

### Reverse/2

`Reverse(List, Rev)` — reverse a list.

```clausal
Test("reverse") <- Reverse([1, 2, 3], [3, 2, 1])
```

### Sort/2

`Sort(List, Sorted)` — sort and remove duplicates.

```clausal
Test("sort") <- Sort([3, 1, 2, 1], [1, 2, 3])
```

### MergeSort/2

`MergeSort(List, Sorted)` — sort preserving duplicates.

```clausal
Test("msort") <- MergeSort([3, 1, 2, 1], [1, 1, 2, 3])
```

### Permutation/2

`Permutation(List, Perm)` — the permutation relation. Holds for each
permutation of `List` on backtracking.

```clausal
Test("perm") <- Permutation([1, 2, 3], [3, 1, 2])
```

### Flatten/2

`Flatten(List, Flat)` — recursively flatten nested lists.

```clausal
Test("flatten") <- Flatten([[1, [2]], [3, 4]], [1, 2, 3, 4])
```

---

## Selection

### Select/3

`Select(Elem, List, Rest)` — relates an element, a list containing it, and
the list without it. Holds for each element on backtracking.

```clausal
Test("select") <- Select(2, [1, 2, 3], [1, 3])
```

This is useful for constraint-style problems where you need to choose from a
pool:

```clausal
assign([], []),
assign([SLOT, *SLOTS], POOL) <- (
    Select(CHOICE, POOL, REMAINING),
    SLOT == CHOICE,
    assign(SLOTS, REMAINING)
)
```

### SplitWith/3

`SplitWith(Sep, List, Parts)` — split a list by separator value, or join parts
with a separator.

```clausal
# Split mode
Test("split_with") <- SplitWith(0, [1, 2, 0, 3, 4, 0, 5], [[1, 2], [3, 4], [5]])
```

---

## Set Operations

These operate on plain lists, treating them as sets.

### ToSet/2

`ToSet(List, Set)` — remove duplicates, preserving order.

```clausal
Test("to_set") <- ToSet([1, 2, 1, 3, 2], [1, 2, 3])
```

### Union/3

`Union(S1, S2, Result)` — elements in either set, no duplicates.

```clausal
Test("union") <- Union([1, 2, 3], [2, 3, 4], [1, 2, 3, 4])
```

### Intersection/3

`Intersection(S1, S2, Result)` — elements in both sets.

```clausal
Test("intersection") <- Intersection([1, 2, 3], [2, 3, 4], [2, 3])
```

### Subtract/3

`Subtract(S1, S2, Result)` — elements in `S1` but not in `S2`.

```clausal
Test("subtract") <- Subtract([1, 2, 3, 4], [2, 4], [1, 3])
```

---

## Aggregation

### SumList/2

`SumList(List, Total)` — sum all numbers in a list.

```clausal
Test("sum") <- SumList([1, 2, 3, 4], 10)
```

### MaxList/2

`MaxList(List, Max)` — maximum element.

```clausal
Test("max") <- MaxList([3, 1, 4, 1, 5], 5)
```

### MinList/2

`MinList(List, Min)` — minimum element.

```clausal
Test("min") <- MinList([3, 1, 4, 1, 5], 1)
```

---

## Patterns & Recipes

### Rotate a list

```clausal
rotate([FIRST, *REST], YS) <- (
    Append(REST, [FIRST], YS)
)
```

### Partition by predicate

```clausal
# skip
partition([], _, [], []),
partition([X, *XS], PRED, [X, *YES], NO) <- (
    Call(PRED, X),
    partition(XS, PRED, YES, NO)
),
partition([X, *XS], PRED, YES, [X, *NO]) <- (
    not Call(PRED, X),
    partition(XS, PRED, YES, NO)
)
```

### Sliding window

```clausal
window(N, LIST, WINDOW) <- (
    Append(WINDOW, _, AFTER),
    Append(_, AFTER, LIST),
    Length(WINDOW, N)
)
```

---

## Gotchas

- **`Sort` removes duplicates** — use `MergeSort` if you need to keep them.
- **`GetItem` is 0-based** — unlike Prolog's `nth1` which is 1-based.
- **`In` yields multiple solutions** — if you only need to confirm membership
  once, use `InCheck`.
- **`Flatten` is fully recursive** — `[1, [2, [3]]]` becomes `[1, 2, 3]`, not
  `[1, 2, [3]]`.

---

*See also: [Pairs](pairs.md) — key-value pair operations,
[Higher-Order](higher_order.md) — MapList, Filter, FoldLeft over lists,
[Dicts & Sets](dicts_sets.md) — dictionary and set data structures.*
