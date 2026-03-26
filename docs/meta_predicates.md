# Meta-Predicates & Higher-Order

Clausal provides meta-predicates for collecting solutions and higher-order list predicates for functional-style list processing. Meta-predicates are compiler special forms (compiled inline); higher-order list predicates are builtins that take goal closures.


---

## Meta-Predicates (Compiler Special Forms)

These are compiled inline by the compiler — they are not dispatched as builtins.

### FindAll/3

`FindAll(Template, Goal, Bag)` — collect all instances of Template for which Goal succeeds.

```clausal
squares(NS, SQS) <- (
    FindAll(
        SQ,
        (In(X, NS), SQ == X * X),
        SQS,
    )
)
```

If Goal has no solutions, Bag is unified with `[]`.

### BagOf/3

`BagOf(Template, Goal, Bag)` — like FindAll, but **fails** if Goal has no solutions (FindAll returns `[]` instead).

```clausal
adults(PEOPLE, ADULTS) <- (
    BagOf(P, (In(P, PEOPLE), age(P, A), A >= 18), ADULTS)
)
```

#### BagOf vs FindAll

The only difference between BagOf and FindAll is how they handle the empty case:

```clausal
age("alice", 30),
age("bob", 25),
age("carol", 30),

all_people(PEOPLE) <- BagOf(NAME, age(NAME, _), PEOPLE)

Test("bag of people") <- (
    all_people(PEOPLE),
    Length(PEOPLE, 3)
)
```

Use BagOf when you want failure on empty results, FindAll when you always want a list.

### SetOf/3

`SetOf(Template, Goal, Set)` — like BagOf, but returns a **sorted list with duplicates removed**. Also fails on no solutions.

```clausal
unique_members(XS, US) <- SetOf(X, In(X, XS), US)
```

#### SetOf vs Sort(FindAll(...))

Both produce sorted, deduplicated results. The differences:

| | `SetOf(T, G, S)` | `FindAll(T, G, S0)` + `Sort(S0, S)` |
|---|---|---|
| Empty result | **Fails** | Succeeds with `S = []` |
| Deduplication | Yes (sorted set) | Only if you call `Sort` |
| Use when | You want failure on empty | You always want a list |

```clausal
Test("setof unique") <- (
    SetOf(X, In(X, [3, 1, 2, 1, 3]), XS),
    Length(XS, 3)
)

# SetOf fails if no solutions; FindAll always succeeds (returns []):
Test("findall empty ok") <- (
    FindAll(X, (In(X, []), X > 0), BAG),
    BAG == []
)
```

### ForAll/2

`ForAll(Condition, Action)` — succeeds if for every solution of Condition, Action also succeeds. Equivalent to `not (Condition, not Action)`.

```clausal
all_positive(XS) <- ForAll(In(X, XS), X > 0)
```

#### ForAll Patterns

**Validate all elements**:

```clausal
all_in_range(XS, LO, HI) <- ForAll(In(X, XS), (X >= LO, X <= HI))
```

**Check a property across a collection**:

```clausal
all_connected(NODES, GRAPH) <- (
    ForAll(
        (In(A, NODES), In(B, NODES), Dif(A, B)),
        reachable(A, B, GRAPH)
    )
)
```

**Guard before processing**:

```clausal
safe_sum(XS, TOTAL) <- (
    ForAll(In(X, XS), IsNumber(X)),
    SumList(XS, TOTAL)
)
```

---

## Call/N

`Call/1..8` invokes a goal closure with 0–7 extra arguments. `CallGoal/1..8` are aliases.

```clausal
apply(GOAL, X) <- Call(GOAL, X)
apply2(GOAL, X, Y) <- Call(GOAL, X, Y)
```

These are primarily used with [lambdas](lambdas.md):

```clausal
test(R) <- Call((X <- (R == X + 1)), 5)
```

---

## Higher-Order List Predicates

These builtins take a goal as their first argument — either a **lambda** (goal closure) or a **predicate reference** (builtin or user-defined). All use **committed choice** — they take the first solution from the goal for each element.

### MapList/2

`MapList(Goal, List)` — succeeds if Goal succeeds for every element of List.

```clausal
# With a lambda
all_positive(XS) <- MapList((X <- (X > 0)), XS)

# With a builtin predicate
all_numbers(XS) <- MapList(IsNumber, XS)
```

### MapList/3

`MapList(Goal, List, ResultList)` — apply a binary goal to each element, collecting results.

```clausal
doubles(XS, YS) <- MapList(((X, Y) <- (Y == X * 2)), XS, YS)
```

### Filter/3

`Filter(Goal, List, Filtered)` — keep elements for which Goal succeeds.

```clausal
# With a lambda
positives(XS, PS) <- Filter((X <- (X > 0)), XS, PS)

# With a builtin predicate
keep_numbers(XS, NS) <- Filter(IsNumber, XS, NS)
```

### Exclude/3

`Exclude(Goal, List, Remaining)` — keep elements for which Goal fails (complement of Filter).

```clausal
remove_zeros(XS, RS) <- Exclude((X <- (X is 0)), XS, RS)
```

### FoldLeft/4

`FoldLeft(Goal, List, Acc0, Result)` — left fold with a ternary goal closure.

```clausal
fold_sum(XS, S) <- FoldLeft(((ELEM, ACC, R) <- (R == ACC + ELEM)), XS, 0, S)
fold_product(XS, P) <- FoldLeft(((ELEM, ACC, R) <- (R == ACC * ELEM)), XS, 1, P)
```

### TakeWhile/3

`TakeWhile(Goal, List, Prefix)` — longest prefix where Goal succeeds for each consecutive element.

```clausal
take_pos(XS, PS) <- TakeWhile((X <- (X > 0)), XS, PS)
# take_pos([3, 1, -2, 4], PS) → PS = [3, 1]
```

### DropWhile/3

`DropWhile(Goal, List, Suffix)` — suffix after dropping the longest prefix where Goal succeeds.

```clausal
drop_pos(XS, RS) <- DropWhile((X <- (X > 0)), XS, RS)
# drop_pos([3, 1, -2, 4], RS) → RS = [-2, 4]
```

### Span/4

`Span(Goal, List, Yes, No)` — TakeWhile + DropWhile in one pass.

```clausal
split_pos(XS, YES, NO) <- Span((X <- (X > 0)), XS, YES, NO)
```

### GroupBy/3

`GroupBy(Goal, List, Groups)` — group consecutive elements by key projected via `Goal(Elem, Key)`.

```clausal
by_sign(XS, GS) <- GroupBy(((X, K) <- If(X > 0, K is "pos", K is "neg")), XS, GS)
```

### SortBy/3

`SortBy(Goal, List, Sorted)` — sort by key projected via `Goal(Elem, Key)`. Stable sort.

```clausal
sort_by_abs(XS, SS) <- SortBy(((X, K) <- (K == abs(X))), XS, SS)
```

### MaxBy/3, MinBy/3

`MaxBy(Goal, List, Max)` / `MinBy(Goal, List, Min)` — element with largest/smallest key. Fails on empty list.

### FilterMap/3

`FilterMap(Goal, List, Result)` — map + filter in one pass. Calls `Goal(Elem, Out)` for each element; keeps Out when goal succeeds, skips when it fails.

```clausal
# skip
double_positives(XS, RS) <- FilterMap(
    ((X, Y) <- (X > 0, Y == X * 2))
    XS, RS
)
```

### Additional List Predicates

| Builtin | Arity | Description |
|---|---|---|
| `Unzip` | 3 | `Unzip(Pairs, Keys, Values)` — split list of pairs |
| `PairKeys` | 2 | `PairKeys(Pairs, Keys)` — extract keys from pairs |
| `PairValues` | 2 | `PairValues(Pairs, Values)` — extract values from pairs |

---

??? tip "Combining Meta-Predicates with Lambdas"

    Meta-predicates take inline goal expressions (not closures), so lambdas aren't needed:

    ```clausal
# skip
    # FindAll with inline goal — no lambda required
    squares(NS, SQS) <- FindAll(SQ, (In(X, NS), SQ == X * X), SQS)

    # ForAll with inline condition and action
    all_positive(NS) <- ForAll(In(X, NS), X > 0)
    ```

    Higher-order list predicates take either lambdas or predicate references:

    ```clausal
# skip
    # Filter with lambda
    positives(XS, PS) <- Filter((X <- (X > 0)), XS, PS)

    # Filter with a builtin predicate directly
    keep_ints(XS, IS) <- Filter(IsInt, XS, IS)
    ```

    See [Lambdas](lambdas.md) for full lambda syntax and semantics.

??? info "Test coverage"

    - `tests/test_meta.py` (23 tests): FindAll, BagOf, SetOf, ForAll, Call/N, `.clausal` integration
    - `tests/test_higher_order.py` (34 tests): MapList/2,3, Filter/3, Exclude/3, FoldLeft/4, builtin predicates as arguments
    - `tests/fixtures/builtin_as_arg.clausal` (5 tests): Filter/MapList with builtin predicates (IsNumber, IsInt, Succ)

---

*See also: [Lambdas](lambdas.md) — goal closures used with higher-order predicates.*
*See also: [Lists](lists.md) — list predicates that pair well with meta-predicates.*
*See also: [Higher-Order](higher_order.md) — dedicated page for MapList, Filter, FoldLeft, etc.*
