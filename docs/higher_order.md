# Higher-Order Predicates

Higher-order predicates take a goal (predicate or lambda) as an argument and
apply it to list elements. Combined with [lambdas](lambdas.md), they give
Clausal a functional programming feel.

---

## Quick Example

```clausal
double(X, Y) <- (Y := X * 2)

Test("double all") <- (
    MapList(double, [1, 2, 3], [2, 4, 6])
)

Test("keep evens") <- (
    Filter((X <- (X % 2 == 0)), [1, 2, 3, 4, 5, 6], [2, 4, 6])
)
```

---

## Calling Goals

### Call/1..8 and CallGoal/1..8

`Call(Goal)` invokes a goal. `Call(Goal, A1, ..., AN)` appends extra arguments.
`CallGoal` is an alias.

```clausal
Test("call/1") <- Call((X <- (X == 42)), 42)

Test("call/2") <- (
    Call(((X, Y) <- (Y := X * 2)), 5, 10)
)
```

The goal can be a lambda, a predicate name, or a predicate instance.

---

## Mapping

### MapList/2

`MapList(Goal, List)` — test `Goal(Elem)` for every element. Succeeds if the
goal succeeds for all elements.

```clausal
positive(X) <- (X > 0)

Test("all positive") <- MapList(positive, [1, 2, 3])
```

### MapList/3

`MapList(Goal, Xs, Ys)` — transform each element via `Goal(X, Y)`.

```clausal
square(X, Y) <- (Y := X ** 2)

Test("squares") <- (
    MapList(square, [1, 2, 3, 4], [1, 4, 9, 16])
)
```

With an inline lambda:

```clausal
Test("squares inline") <- (
    MapList(((X, Y) <- (Y := X ** 2)), [1, 2, 3, 4], [1, 4, 9, 16])
)
```

---

## Filtering

### Filter/3

`Filter(Goal, List, Included)` — keep elements where `Goal(Elem)` succeeds.

```clausal
Test("filter") <- Filter((X <- (X > 3)), [1, 5, 2, 8, 3], [5, 8])
```

### Exclude/3

`Exclude(Goal, List, Kept)` — keep elements where `Goal(Elem)` *fails*.
The inverse of Filter.

```clausal
Test("exclude") <- Exclude((X <- (X > 3)), [1, 5, 2, 8, 3], [1, 2, 3])
```

### FilterMap/3

`FilterMap(Goal, List, Result)` — map and filter in one pass. Keep the output
value when `Goal(Elem, Out)` succeeds; skip elements where it fails.

```clausal
safe_sqrt(X, Y) <- (X >= 0, Y := X ** 0.5)

Test("filtermap") <- FilterMap(safe_sqrt, [4, -1, 9, -2, 16], [2.0, 3.0, 4.0])
```

---

## Folding

### FoldLeft/4

`FoldLeft(Goal, List, V0, V)` — left fold. Applies `Goal(Elem, Acc, NewAcc)`
across the list, threading an accumulator from `V0` to `V`.

```clausal
add_step(X, ACC, OUT) <- (OUT := ACC + X)

Test("sum") <- (
    FoldLeft(add_step, [1, 2, 3, 4], 0, 10)
)
```

With an inline lambda:

```clausal
Test("sum inline") <- (
    FoldLeft(((X, ACC, OUT) <- (OUT := ACC + X)), [1, 2, 3, 4], 0, 10)
)
```

---

## Prefix & Suffix

### TakeWhile/3

`TakeWhile(Goal, List, Prefix)` — longest prefix where `Goal(Elem)` succeeds.

```clausal
Test("takewhile") <- TakeWhile((X <- (X < 5)), [1, 3, 7, 2, 4], [1, 3])
```

### DropWhile/3

`DropWhile(Goal, List, Suffix)` — drop the prefix where `Goal(Elem)` succeeds.

```clausal
Test("dropwhile") <- DropWhile((X <- (X < 5)), [1, 3, 7, 2, 4], [7, 2, 4])
```

### Span/4

`Span(Goal, List, Yes, No)` — TakeWhile + DropWhile in one pass.

```clausal
Test("span") <- (
    Span((X <- (X < 5)), [1, 3, 7, 2, 4], [1, 3], [7, 2, 4])
)
```

---

## Grouping & Sorting

### GroupBy/3

`GroupBy(Goal, List, Groups)` — group *consecutive* elements by key.
`Goal(Elem, Key)` extracts the grouping key.

```clausal
first_char(S, C) <- (C := ++S[0])

Test("group by first char") <- (
    GroupBy(first_char, ["apple", "avocado", "banana", "blueberry", "cherry"], [["apple", "avocado"], ["banana", "blueberry"], ["cherry"]])
)
```

Note: groups are consecutive runs, not global grouping. Sort first if you need
global groups.

### SortBy/3

`SortBy(Goal, List, Sorted)` — sort by projected key.

```clausal
abs_key(X, K) <- (Abs(X, K))

Test("sort by abs") <- (
    SortBy(abs_key, [3, -1, -4, 2], [-1, 2, 3, -4])
)
```

### MaxBy/3, MinBy/3

`MaxBy(Goal, List, Max)` / `MinBy(Goal, List, Min)` — element with the
largest/smallest projected key.

```clausal
str_len(S, K) <- (K := ++len(S))

Test("longest") <- (
    MaxBy(str_len, ["hi", "hello", "hey"], "hello")
)
```

---

## Patterns & Recipes

### Map then filter (pipeline)

```clausal
sq(X, Y) <- (Y := X * X)

Test("pipeline") <- (
    MapList(sq, [1, 2, 3, 4, 5], SQUARES),
    Filter((X <- (X > 10)), SQUARES, BIG),
    BIG == [16, 25]
)
```

### Flatten via FoldLeft

```clausal
Test("flat") <- (
    FoldLeft(((CHUNK, ACC, OUT) <- Append(ACC, CHUNK, OUT)),
        [[1, 2], [3], [4, 5]],
        [],
        [1, 2, 3, 4, 5])
)
```

### Count occurrences

```clausal
count(PRED, LIST, N) <- (
    Filter(PRED, LIST, MATCHED),
    Length(MATCHED, N)
)

Test("count evens") <- count((X <- (X % 2 == 0)), [1, 2, 3, 4, 5, 6], 3)
```

---

## Gotchas

- **Goal argument order matters** — `MapList/3` calls `Goal(X, Y)` where X is
  input, Y is output. `FoldLeft/4` calls `Goal(Elem, AccIn, AccOut)`.
- **`GroupBy` groups consecutive runs** — not global grouping. Sort first if
  needed.
- **Lambdas are committed-choice** — `Filter` tests each element once (first
  solution only). It does not backtrack into the goal.
- **Lambda syntax** — single-arg: `(X <- (body))`. Multi-arg: `((X, Y) <- (body))`
  with extra outer parens for the tuple.
- **`Call/N` appends arguments** — `Call(foo, 1, 2)` calls `foo(1, 2)`.

---

*See also: [Lambdas](lambdas.md) — goal closure syntax,
[Meta-Predicates](meta_predicates.md) — FindAll, BagOf, SetOf,
[Lists](lists.md) — list operations.*
