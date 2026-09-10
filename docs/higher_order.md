# Higher-Order Predicates

Higher-order predicates take a goal (predicate or lambda) as an argument and
apply it to [list](lists.md) elements. Combined with [lambdas](lambdas.md), they give
Clausal a functional programming feel.

---

## Quick Example

```clausal
double(X, Y) <- (Y == X * 2)

test("double all") <- (
    maplist(double, [1, 2, 3], [2, 4, 6])
)

test("keep evens") <- (
    include((X <- (X % 2 == 0)), [1, 2, 3, 4, 5, 6], [2, 4, 6])
)
```

---

## Calling Goals

### call/1..8 and call_goal/1..8

`call(Goal)` invokes a goal. `call(Goal, A1, ..., AN)` appends extra arguments.
`call_goal` is an alias.

```clausal
test("call/1") <- call((X <- (X == 42)), 42)

test("call/2") <- (
    call(((X, Y) <- (Y == X * 2)), 5, 10)
)
```

The goal can be a lambda, a predicate name, or a predicate instance.

---

## Mapping

### maplist/2

`maplist(Goal, List)` — test `Goal(Elem)` for every element. Succeeds if the
goal succeeds for all elements.

```clausal
positive(X) <- (X > 0)

test("all positive") <- maplist(positive, [1, 2, 3])
```

### maplist/3

`maplist(Goal, Xs, Ys)` — transform each element via `Goal(X, Y)`.

```clausal
square(X, Y) <- (Y == X ** 2)

test("squares") <- (
    maplist(square, [1, 2, 3, 4], [1, 4, 9, 16])
)
```

With an inline lambda:

```clausal
test("squares inline") <- (
    maplist(((X, Y) <- (Y == X ** 2)), [1, 2, 3, 4], [1, 4, 9, 16])
)
```

---

## Filtering

### include/3

`include(Goal, List, Included)` — keep elements where `Goal(Elem)` succeeds.

```clausal
test("filter") <- include((X <- (X > 3)), [1, 5, 2, 8, 3], [5, 8])
```

### exclude/3

`exclude(Goal, List, Kept)` — keep elements where `Goal(Elem)` *fails*.
The inverse of include.

```clausal
test("exclude") <- exclude((X <- (X > 3)), [1, 5, 2, 8, 3], [1, 2, 3])
```

### filter_map/3

`filter_map(Goal, List, Result)` — map and filter in one pass. Keep the output
value when `Goal(Elem, Out)` succeeds; skip elements where it fails.

```clausal
safe_sqrt(X, Y) <- (X >= 0, Y == X ** 0.5)

test("filtermap") <- filter_map(safe_sqrt, [4, -1, 9, -2, 16], [2.0, 3.0, 4.0])
```

---

## Folding

### foldl/4

`foldl(Goal, List, V0, V)` — left fold. Applies `Goal(Elem, Acc, NewAcc)`
across the list, threading an accumulator from `V0` to `V`.

```clausal
add_step(X, ACC, OUT) <- (OUT == ACC + X)

test("sum") <- (
    foldl(add_step, [1, 2, 3, 4], 0, 10)
)
```

With an inline lambda:

```clausal
test("sum inline") <- (
    foldl(((X, ACC, OUT) <- (OUT == ACC + X)), [1, 2, 3, 4], 0, 10)
)
```

---

## Prefix & Suffix

### take_while/3

`take_while(Goal, List, Prefix)` — longest prefix where `Goal(Elem)` succeeds.

```clausal
test("takewhile") <- take_while((X <- (X < 5)), [1, 3, 7, 2, 4], [1, 3])
```

### drop_while/3

`drop_while(Goal, List, Suffix)` — drop the prefix where `Goal(Elem)` succeeds.

```clausal
test("dropwhile") <- drop_while((X <- (X < 5)), [1, 3, 7, 2, 4], [7, 2, 4])
```

### span/4

`span(Goal, List, Yes, No)` — take_while + drop_while in one pass.

```clausal
test("span") <- (
    span((X <- (X < 5)), [1, 3, 7, 2, 4], [1, 3], [7, 2, 4])
)
```

---

## Grouping & Sorting

### group_by/3

`group_by(Goal, List, Groups)` — group *consecutive* elements by key.
`Goal(Elem, Key)` extracts the grouping key.

```clausal
first_char(S, C) <- (C is ++S[0])

test("group by first char") <- (
    group_by(first_char, ["apple", "avocado", "banana", "blueberry", "cherry"], [["apple", "avocado"], ["banana", "blueberry"], ["cherry"]])
)
```

Note: groups are consecutive runs, not global grouping. sort first if you need
global groups.

### sort_by/3

`sort_by(Goal, List, Sorted)` — sort by projected key.

```clausal
abs_key(X, K) <- (abs_(X, K))

test("sort by abs") <- (
    sort_by(abs_key, [3, -1, -4, 2], [-1, 2, 3, -4])
)
```

### max_by/3, min_by/3

`max_by(Goal, List, max_)` / `min_by(Goal, List, min_)` — element with the
largest/smallest projected key.

```clausal
str_len(S, K) <- (K is ++len(S))    # see [Python interop](python_integration.md)

test("longest") <- (
    max_by(str_len, ["hi", "hello", "hey"], "hello")
)
```

---

## Patterns & Recipes

### Map then filter (pipeline)

```clausal
sq(X, Y) <- (Y == X * X)

test("pipeline") <- (
    maplist(sq, [1, 2, 3, 4, 5], SQUARES),
    include((X <- (X > 10)), SQUARES, BIG),
    BIG == [16, 25]
)
```

### flatten via foldl

```clausal
test("flat") <- (
    foldl(((CHUNK, ACC, OUT) <- append(ACC, CHUNK, OUT)),
        [[1, 2], [3], [4, 5]],
        [],
        [1, 2, 3, 4, 5])
)
```

### Count occurrences

```clausal
count(PRED, LIST, N) <- (
    include(PRED, LIST, MATCHED),
    length(MATCHED, N)
)

test("count evens") <- count((X <- (X % 2 == 0)), [1, 2, 3, 4, 5, 6], 3)
```

---

## Gotchas

- **Goal argument order matters** — `maplist/3` calls `Goal(X, Y)` where X is
  input, Y is output. `foldl/4` calls `Goal(Elem, AccIn, AccOut)`.
- **`group_by` groups consecutive runs** — not global grouping. sort first if
  needed.
- **Lambdas are committed-choice** — `include` tests each element once (first
  solution only). It does not backtrack into the goal.
- **Lambda syntax** — single-arg: `(X <- (body))`. Multi-arg: `((X, Y) <- (body))`
  with extra outer parens for the tuple. See [Lambdas](lambdas.md) for details.
- **`call/N` appends arguments** — `call(foo, 1, 2)` calls `foo(1, 2)`.

---

*See also: [Lambdas](lambdas.md) — goal closure syntax,
[Meta-Predicates](meta_predicates.md) — findall, bagof, setof,
[Lists](lists.md) — list operations.*
