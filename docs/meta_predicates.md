# Meta-Predicates & Higher-Order

Clausal Prolog provides meta-predicates for collecting solutions and higher-order list predicates for functional-style list processing. Meta-predicates are compiler special forms (compiled inline); higher-order list predicates are builtins that take goal closures.


---

## Meta-Predicates (Compiler Special Forms)

These are compiled inline by the compiler — they are not dispatched as builtins.

### findall/3

`findall(Template, Goal, Bag)` — collect all instances of Template for which Goal succeeds.

```seam
squares(NS, SQS) <- (
    findall(
        SQ,
        (in_(X, NS), SQ == X * X),
        SQS,
    )
)
```

If Goal has no solutions, Bag is unified with `[]`.

### bagof/3

`bagof(Template, Goal, Bag)` — like findall, but **fails** if Goal has no
solutions (findall returns `[]` instead), and it collects one bag per binding
of the goal's **free variables**: the variables of `Goal` that are neither in
`Template` nor marked existential with `Var ^ Goal`. It backtracks over the
bags in the standard order of those bindings, as ISO specifies and Scryer
does. With no free variables it is findall that fails on empty.

```seam
adults(PEOPLE, ADULTS) <- (
    bagof(P, A ^ (in_(P, PEOPLE), age(P, A), A >= 18), ADULTS)
)
```

Without the `A ^`, `A` is free and `adults` would answer one bag per age.

#### bagof vs findall

The only difference between bagof and findall is how they handle the empty case:

```seam
age('alice', 30),
age('bob', 25),
age('carol', 30),

all_people(PEOPLE) <- bagof(NAME, AGE ^ age(NAME, AGE), PEOPLE)

test("bag of people") <- (
    all_people(PEOPLE),
    length(PEOPLE, 3)
)
```

Use bagof when you want failure on empty results, findall when you always want a list.

#### Free variables and `^`

```seam
test("one bag per age") <- (
    findall([AGE, NAMES], bagof(NAME, age(NAME, AGE), NAMES), BAGS),
    BAGS is [[25, ['bob']], [30, ['alice', 'carol']]]
)
```

An anonymous `_` in the goal is a free variable too: `bagof(N, age(N, _), L)`
answers one bag per age. `V ^ Goal` may be nested (`X ^ Y ^ p(X, Y, Z)`), and
a goal built at run time is read the same way
(`G is (Y ^ p(Y)), call(bagof(X, G, L))`). Solutions whose free-variable
bindings are variants share a bag.

### setof/3

`setof(Template, Goal, Set)` — like bagof (one set per binding of the free
variables, `^` for existential ones), but each bag is a **sorted list with
duplicates removed**. Also fails on no solutions.

```seam
unique_members(XS, US) <- setof(X, in_(X, XS), US)
```

#### setof vs sort(findall(...))

Both produce sorted, deduplicated results. The differences:

| | `setof(T, G, S)` | `findall(T, G, S0)` + `sort(S0, S)` |
|---|---|---|
| Empty result | **Fails** | Succeeds with `S = []` |
| Deduplication | Yes (sorted set) | Only if you call `sort` |
| Use when | You want failure on empty | You always want a list |

```seam
test("setof unique") <- (
    setof(X, in_(X, [3, 1, 2, 1, 3]), XS),
    length(XS, 3)
)

# setof fails if no solutions; findall always succeeds (returns []):
test("findall empty ok") <- (
    findall(X, (in_(X, []), X > 0), BAG),
    BAG == []
)
```

### forall/2

`forall(Condition, Action)` — succeeds if for every solution of Condition, Action also succeeds. equivalent to `not (Condition, not Action)`.

```seam
all_positive(XS) <- forall(in_(X, XS), X > 0)
```

#### forall Patterns

**Validate all elements**:

```seam
all_in_range(XS, LO, HI) <- forall(in_(X, XS), (X >= LO, X <= HI))
```

**Check a property across a collection**:

```seam
all_connected(NODES, GRAPH) <- (
    forall(
        (in_(A, NODES), in_(B, NODES), dif(A, B)),   # dif — see [Constraints](constraints.md)
        reachable(A, B, GRAPH)
    )
)
```

**Guard before processing**:

```seam
safe_sum(XS, TOTAL) <- (
    forall(in_(X, XS), number(X)),
    sum_list(XS, TOTAL)
)
```

---

## call/N

`call/1..8` invokes a goal closure with 0–7 extra arguments. `call_goal/1..8` are aliases.

```seam
apply(GOAL, X) <- call(GOAL, X)
apply2(GOAL, X, Y) <- call(GOAL, X, Y)
```

These are primarily used with [lambdas](lambdas.md):

```seam
plus_one(R) <- call((X <- (R == X + 1)), 5)
```

---

## Higher-Order List Predicates

These builtins take a goal as their first argument — either a [lambda](lambdas.md) (goal closure) or a **predicate reference** (builtin or user-defined). All use **committed choice** — they take the first solution from the goal for each element. See [Higher-Order](higher_order.md) for the dedicated reference page.

### maplist/2

`maplist(Goal, List)` — succeeds if Goal succeeds for every element of List.

```seam
# With a lambda
all_positive(XS) <- maplist((X <- (X > 0)), XS)

# With a builtin predicate
all_numbers(XS) <- maplist(number, XS)
```

### maplist/3

`maplist(Goal, List, ResultList)` — apply a binary goal to each element, collecting results.

```seam
doubles(XS, YS) <- maplist(((X, Y) <- (Y == X * 2)), XS, YS)
```

### include/3

`include(Goal, List, Filtered)` — keep elements for which Goal succeeds.

```seam
# With a lambda
positives(XS, PS) <- include((X <- (X > 0)), XS, PS)

# With a builtin predicate
keep_numbers(XS, NS) <- include(number, XS, NS)
```

### exclude/3

`exclude(Goal, List, Remaining)` — keep elements for which Goal fails (complement of include).

```seam
remove_zeros(XS, RS) <- exclude((X <- (X is 0)), XS, RS)
```

### foldl/4

`foldl(Goal, List, Acc0, Result)` — left fold with a ternary goal closure.

```seam
fold_sum(XS, S) <- foldl(((ELEM, ACC, R) <- (R == ACC + ELEM)), XS, 0, S)
fold_product(XS, P) <- foldl(((ELEM, ACC, R) <- (R == ACC * ELEM)), XS, 1, P)
```

### take_while/3

`take_while(Goal, List, Prefix)` — longest prefix where Goal succeeds for each consecutive element.

```seam
take_pos(XS, PS) <- take_while((X <- (X > 0)), XS, PS)
# take_pos([3, 1, -2, 4], PS) → PS = [3, 1]
```

### drop_while/3

`drop_while(Goal, List, Suffix)` — suffix after dropping the longest prefix where Goal succeeds.

```seam
drop_pos(XS, RS) <- drop_while((X <- (X > 0)), XS, RS)
# drop_pos([3, 1, -2, 4], RS) → RS = [-2, 4]
```

### span/4

`span(Goal, List, Yes, No)` — take_while + drop_while in one pass.

```seam
split_pos(XS, YES, NO) <- span((X <- (X > 0)), XS, YES, NO)
```

### group_by/3

`group_by(Goal, List, Groups)` — group consecutive elements by key projected via `Goal(Elem, Key)`.

```seam
by_sign(XS, GS) <- group_by(((X, K) <- if_(X > 0, K is 'pos', K is 'neg')), XS, GS)
```

### sort_by/3

`sort_by(Goal, List, Sorted)` — sort by key projected via `Goal(Elem, Key)`. Stable sort.

```seam
sort_by_abs(XS, SS) <- sort_by(((X, K) <- abs_(X, K)), XS, SS)
```

### max_by/3, min_by/3

`max_by(Goal, List, max_)` / `min_by(Goal, List, min_)` — element with largest/smallest key. Fails on empty list.

### filter_map/3

`filter_map(Goal, List, Result)` — map + filter in one pass. Calls `Goal(Elem, Out)` for each element; keeps Out when goal succeeds, skips when it fails.

```seam
--8<-- "tests/fixtures/docs/meta_predicates_sigs.txt:filter_map_example"
```

### Additional List Predicates

| Builtin | Arity | Description |
|---|---|---|
| `pairs_keys_values` | 3 | `pairs_keys_values(Pairs, Keys, Values)` — split list of [pairs](pairs.md) |
| `pairs_keys` | 2 | `pairs_keys(Pairs, Keys)` — extract keys from [pairs](pairs.md) |
| `pairs_values` | 2 | `pairs_values(Pairs, Values)` — extract values from [pairs](pairs.md) |

---

??? tip "Combining Meta-Predicates with Lambdas"

    Meta-predicates take inline goal expressions (not closures), so lambdas aren't needed:

    ```seam
    --8<-- "tests/fixtures/docs/meta_predicates_sigs.txt:meta_with_inline"
    ```

    Higher-order list predicates take either lambdas or predicate references:

    ```seam
    --8<-- "tests/fixtures/docs/meta_predicates_sigs.txt:higher_order_with_lambda"
    ```

    See [Lambdas](lambdas.md) for full lambda syntax and semantics.

??? info "Test coverage"

    - `tests/test_meta.py`: findall, bagof, setof, forall, call/N, `.seam` integration
    - `tests/test_higher_order.py` (34 tests): maplist/2,3, include/3, exclude/3, foldl/4, builtin predicates as arguments
    - `tests/fixtures/builtin_as_arg.seam` (5 tests): include/maplist with builtin predicates (number, integer, succ)

---

*See also: [Lambdas](lambdas.md) — goal closures used with higher-order predicates,
[Lists](lists.md) — list predicates that pair well with meta-predicates,
[Higher-Order](higher_order.md) — dedicated page for maplist, include, foldl, etc.*
