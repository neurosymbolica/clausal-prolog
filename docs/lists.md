# Lists

Lists are the fundamental data structure in logic programming. Clausal uses
Python's native list syntax — no cons cells, no special notation.

!!! tip "Strings work too"

    All list predicates accept strings as character lists. `append("hel", "lo", X)`
    yields `X = "hello"`, `in_('e', "hello")` succeeds, and `reverse("hello", X)`
    yields `X = "olleh"`. See [Strings as Lists](strings_as_lists.md) for the full
    story.

---

## Quick Example

```clausal
palindrome(XS) <- (reverse(XS, XS))

test("palindrome") <- palindrome([1, 2, 1])
test("not palindrome") <- (not palindrome([1, 2, 3]))
```

---

## List Syntax

```clausal
--8<-- "tests/fixtures/docs/lists_sigs.txt:list_syntax"
```

Clause heads can describe list structure using `[HEAD, *TAIL]`, relating the
whole list to its parts (see [Syntax](syntax.md) for the full pattern language):

```clausal
list_sum([], 0),
list_sum([X, *XS], TOTAL) <- (
    list_sum(XS, REST),
    TOTAL == X + REST
)
```

---

## Membership

### in_/2

`in_(Elem, List)` — the membership relation. Holds for each element in `List`
on backtracking.

```clausal
test("member") <- in_(2, [1, 2, 3])
test("generate") <- (in_(X, ['a', 'b', 'c']), X == 'b')
```

### in_check/2

`in_check(Elem, List)` — deterministic membership. Holds at most once (first
unifying element only). Use when you need to confirm membership without
enumerating alternatives.

```clausal
test("check") <- in_check('b', ['a', 'b', 'c'])
```

---

## Building & Joining

### append/3

`append(L1, L2, L3)` — relates three lists such that `L3` is `L1` followed by
`L2`. Works in the three modes shown below — concatenation (`L1`, `L2`
bound), splitting a bound `L3`, and extracting the remainder from a bound
`L1` and `L3`. (Open partial-list mode — `L1` bound with `L2` and `L3`
unbound — is not supported.)

```clausal
# Concatenate
test("concat") <- append([1, 2], [3, 4], [1, 2, 3, 4])

# Split — enumerate all ways to split a list
test("split") <- (
    append(LEFT, RIGHT, [1, 2, 3]),
    LEFT == [1],
    RIGHT == [2, 3]
)

# Suffix extraction
test("suffix") <- (
    append([1, 2], REST, [1, 2, 3, 4, 5]),
    REST == [3, 4, 5]
)
```

### replicate/3

`replicate(N, Elem, List)` — `List` is `N` copies of `Elem`.

```clausal
test("replicate") <- replicate(3, 'x', ['x', 'x', 'x'])
```

### zip_/3

`zip_(L1, L2, Pairs)` — pair up corresponding elements. Stops at the shorter
list.

```clausal
test("zip") <- zip_([1, 2, 3], ['a', 'b', 'c'], [[1, 'a'], [2, 'b'], [3, 'c']])
```

---

## Access & Slicing

### length/2

`length(List, N)` — relates a list to its length. Can also generate a list of
`N` fresh variables.

```clausal
test("length") <- length([10, 20, 30], 3)
```

### list_item/3

`list_item(N, List, Elem)` — relates a 0-based index, a list, and an element.

```clausal
test("get") <- list_item(1, ['a', 'b', 'c'], 'b')
test("enumerate") <- (list_item(I, [10, 20, 30], 20), I == 1)
```

### last/2

`last(List, Elem)` — the last element.

```clausal
test("last") <- last([1, 2, 3], 3)
```

### take/3

`take(N, List, Taken)` — first `N` elements.

```clausal
test("take") <- take(2, [1, 2, 3, 4], [1, 2])
```

### drop/3

`drop(N, List, Rest)` — everything after the first `N` elements.

```clausal
test("drop") <- drop(2, [1, 2, 3, 4], [3, 4])
```

### split_at/4

`split_at(N, List, Left, Right)` — split at index `N`.

```clausal
test("split_at") <- split_at(2, [1, 2, 3, 4], [1, 2], [3, 4])
```

---

## Reordering

### reverse/2

`reverse(List, Rev)` — reverse a list.

```clausal
test("reverse") <- reverse([1, 2, 3], [3, 2, 1])
```

### sort/2

`sort(List, Sorted)` — sort and remove duplicates.

```clausal
test("sort") <- sort([3, 1, 2, 1], [1, 2, 3])
```

### msort/2

`msort(List, Sorted)` — sort preserving duplicates.

```clausal
test("msort") <- msort([3, 1, 2, 1], [1, 1, 2, 3])
```

### permutation/2

`permutation(List, Perm)` — the permutation relation. Holds for each
permutation of `List` on backtracking.

```clausal
test("perm") <- permutation([1, 2, 3], [3, 1, 2])
```

### flatten/2

`flatten(List, Flat)` — recursively flatten nested lists.

```clausal
test("flatten") <- flatten([[1, [2]], [3, 4]], [1, 2, 3, 4])
```

---

## Selection

### select/3

`select(Elem, List, Rest)` — relates an element, a list containing it, and
the list without it. Holds for each element on backtracking.

```clausal
test("select") <- select(2, [1, 2, 3], [1, 3])
```

This is useful for constraint-style problems where you need to choose from a
pool:

```clausal
assign([], []),
assign([SLOT, *SLOTS], POOL) <- (
    select(CHOICE, POOL, REMAINING),
    SLOT == CHOICE,
    assign(SLOTS, REMAINING)
)
```

### split_with/3

`split_with(Sep, List, Parts)` — split a list by separator value, or join parts
with a separator.

```clausal
# Split mode
test("split_with") <- split_with(0, [1, 2, 0, 3, 4, 0, 5], [[1, 2], [3, 4], [5]])
```

---

## Set Operations

These operate on plain lists, treating them as sets.

### list_to_set/2

`list_to_set(List, Set)` — remove duplicates, preserving order.

```clausal
test("to_set") <- list_to_set([1, 2, 1, 3, 2], [1, 2, 3])
```

### union/3

`union(S1, S2, Result)` — `S1` followed by the elements of `S2` not already
in `S1` (SWI-consistent). `S1`'s own duplicates are preserved
(`union([1,1], [], U)` gives `[1,1]`); run `list_to_set/2` first for a true
set.

```clausal
test("union") <- union([1, 2, 3], [2, 3, 4], [1, 2, 3, 4])
```

### intersection/3

`intersection(S1, S2, Result)` — elements in both sets.

```clausal
test("intersection") <- intersection([1, 2, 3], [2, 3, 4], [2, 3])
```

### subtract/3

`subtract(S1, S2, Result)` — elements in `S1` but not in `S2`.

```clausal
test("subtract") <- subtract([1, 2, 3, 4], [2, 4], [1, 3])
```

---

## Aggregation

### sum_list/2

`sum_list(List, Total)` — sum all numbers in a list.

```clausal
test("sum") <- sum_list([1, 2, 3, 4], 10)
```

### max_list/2

`max_list(List, max_)` — maximum element.

```clausal
test("max") <- max_list([3, 1, 4, 1, 5], 5)
```

### min_list/2

`min_list(List, min_)` — minimum element.

```clausal
test("min") <- min_list([3, 1, 4, 1, 5], 1)
```

---

## Patterns & Recipes

### Rotate a list

```clausal
rotate([FIRST, *REST], YS) <- (
    append(REST, [FIRST], YS)
)
```

### partition by predicate

Using [Call/N](higher_order.md#calln) to apply a predicate argument:

```clausal
--8<-- "tests/fixtures/docs/lists_examples.clausal:partition_example"
```

### Sliding window

```clausal
window(N, LIST, WINDOW) <- (
    append(WINDOW, _, AFTER),
    append(_, AFTER, LIST),
    length(WINDOW, N)
)
```

---

## Gotchas

- **`sort` removes duplicates** — use `msort` if you need to keep them.
- **`list_item` is 0-based** — unlike Prolog's `nth1` which is 1-based.
- **`in_` yields multiple solutions** — if you only need to confirm membership
  once, use `in_check`.
- **`flatten` is fully recursive** — `[1, [2, [3]]]` becomes `[1, 2, 3]`, not
  `[1, 2, [3]]`.

---

*See also: [Strings as Lists](strings_as_lists.md) — strings behave as character lists,
[Pairs](pairs.md) — key-value pair operations,
[Higher-Order](higher_order.md) — maplist, include, foldl over lists,
[Dicts & Sets](dicts_sets.md) — dictionary and set data structures.*
