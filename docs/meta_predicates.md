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
        (In(X, NS) and (SQ := X * X)),
        SQS,
    )
)
```

If Goal has no solutions, Bag is unified with `[]`.

### BagOf/3

`BagOf(Template, Goal, Bag)` — like FindAll, but **fails** if Goal has no solutions. Also respects `^` (existential quantification) for free variables.

```clausal
adults(PEOPLE, ADULTS) <- (
    BagOf(P, (In(P, PEOPLE) and age(P, A) and A >= 18), ADULTS)
)
```

### SetOf/3

`SetOf(Template, Goal, Set)` — like BagOf, but returns a **sorted list with duplicates removed**.

```clausal
unique_members(XS, US) <- SetOf(X, In(X, XS), US)
```

### ForAll/2

`ForAll(Condition, Action)` — succeeds if for every solution of Condition, Action also succeeds.

```clausal
all_positive(XS) <- ForAll(In(X, XS), X > 0)
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
test(R) <- Call((X <- (R := X + 1)), 5)
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
doubles(XS, YS) <- MapList(((X, Y) <- (Y := X * 2)), XS, YS)
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
fold_sum(XS, S) <- FoldLeft(((ELEM, ACC, R) <- (R := ACC + ELEM)), XS, 0, S)
fold_product(XS, P) <- FoldLeft(((ELEM, ACC, R) <- (R := ACC * ELEM)), XS, 1, P)
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
sort_by_abs(XS, SS) <- SortBy(((X, K) <- (K := abs(X))), XS, SS)
```

### MaxBy/3, MinBy/3

`MaxBy(Goal, List, Max)` / `MinBy(Goal, List, Min)` — element with largest/smallest key. Fails on empty list.

### FilterMap/3

`FilterMap(Goal, List, Result)` — map + filter in one pass. Calls `Goal(Elem, Out)` for each element; keeps Out when goal succeeds, skips when it fails.

```clausal
double_positives(XS, RS) <- FilterMap(
    ((X, Y) <- (X > 0 and (Y := X * 2))),
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
    # FindAll with inline goal — no lambda required
    squares(NS, SQS) <- FindAll(SQ, (In(X, NS) and (SQ := X * X)), SQS)

    # ForAll with inline condition and action
    all_positive(NS) <- ForAll(In(X, NS), X > 0)
    ```

    Higher-order list predicates take either lambdas or predicate references:

    ```clausal
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
