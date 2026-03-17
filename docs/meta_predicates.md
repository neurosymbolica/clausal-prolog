# Meta-Predicates & Higher-Order

Clausal provides meta-predicates for collecting solutions and higher-order list predicates for functional-style list processing. Meta-predicates are compiler special forms (compiled inline); higher-order list predicates are builtins that take goal closures.

Added in V2-10 (meta-predicates) and V2-11 (higher-order list builtins).

---

## Meta-Predicates (Compiler Special Forms)

These are compiled inline by the compiler — they are not dispatched as builtins.

### FindAll/3

`FindAll(Template, Goal, Bag)` — collect all instances of Template for which Goal succeeds.

```
squares(Ns_, Sqs_) <- (
    FindAll(
        Sq_,
        (In(X_, Ns_) and (Sq_ := X_ * X_)),
        Sqs_,
    )
)
```

If Goal has no solutions, Bag is unified with `[]`.

### BagOf/3

`BagOf(Template, Goal, Bag)` — like FindAll, but **fails** if Goal has no solutions. Also respects `^` (existential quantification) for free variables.

```
adults(People_, Adults_) <- (
    BagOf(P_, (In(P_, People_) and age(P_, A_) and A_ >= 18), Adults_)
)
```

### SetOf/3

`SetOf(Template, Goal, Set)` — like BagOf, but returns a **sorted list with duplicates removed**.

```
unique_members(Xs_, Us_) <- SetOf(X_, In(X_, Xs_), Us_)
```

### ForAll/2

`ForAll(Condition, Action)` — succeeds if for every solution of Condition, Action also succeeds.

```
all_positive(Xs_) <- ForAll(In(X_, Xs_), X_ > 0)
```

---

## Call/N

`Call/1..8` invokes a goal closure with 0–7 extra arguments. `CallGoal/1..8` are aliases.

```
apply(Goal_, X_) <- Call(Goal_, X_)
apply2(Goal_, X_, Y_) <- Call(Goal_, X_, Y_)
```

These are primarily used with [lambdas](lambdas.md):

```
test(R_) <- Call((X_ <- (R_ := X_ + 1)), 5)
```

---

## Higher-Order List Predicates

These builtins take goal closures (lambdas) as arguments. All use **committed choice** — they take the first solution from the goal for each element.

### MapList/2

`MapList(Goal, List)` — succeeds if Goal succeeds for every element of List.

```
all_positive(Xs_) <- MapList((X_ <- (X_ > 0)), Xs_)
```

### MapList/3

`MapList(Goal, List, ResultList)` — apply a binary goal to each element, collecting results.

```
doubles(Xs_, Ys_) <- MapList(((X_, Y_) <- (Y_ := X_ * 2)), Xs_, Ys_)
```

### Filter/3

`Filter(Goal, List, Filtered)` — keep elements for which Goal succeeds.

```
positives(Xs_, Ps_) <- Filter((X_ <- (X_ > 0)), Xs_, Ps_)
```

### Exclude/3

`Exclude(Goal, List, Remaining)` — keep elements for which Goal fails (complement of Filter).

```
remove_zeros(Xs_, Rs_) <- Exclude((X_ <- (X_ is 0)), Xs_, Rs_)
```

### FoldLeft/4

`FoldLeft(Goal, List, Acc0, Result)` — left fold with a ternary goal closure.

```
fold_sum(Xs_, S_) <- FoldLeft(((E_, A_, R_) <- (R_ := A_ + E_)), Xs_, 0, S_)
fold_product(Xs_, P_) <- FoldLeft(((E_, A_, R_) <- (R_ := A_ * E_)), Xs_, 1, P_)
```

### TakeWhile/3

`TakeWhile(Goal, List, Prefix)` — longest prefix where Goal succeeds for each consecutive element.

```
take_pos(Xs_, Ps_) <- TakeWhile((X_ <- (X_ > 0)), Xs_, Ps_)
# take_pos([3, 1, -2, 4], Ps_) → Ps_ = [3, 1]
```

### DropWhile/3

`DropWhile(Goal, List, Suffix)` — suffix after dropping the longest prefix where Goal succeeds.

```
drop_pos(Xs_, Rs_) <- DropWhile((X_ <- (X_ > 0)), Xs_, Rs_)
# drop_pos([3, 1, -2, 4], Rs_) → Rs_ = [-2, 4]
```

### Span/4

`Span(Goal, List, Yes, No)` — TakeWhile + DropWhile in one pass.

```
split_pos(Xs_, Yes_, No_) <- Span((X_ <- (X_ > 0)), Xs_, Yes_, No_)
```

### GroupBy/3

`GroupBy(Goal, List, Groups)` — group consecutive elements by key projected via `Goal(Elem, Key)`.

```
by_sign(Xs_, Gs_) <- GroupBy(((X_, K_) <- If(X_ > 0, K_ is "pos", K_ is "neg")), Xs_, Gs_)
```

### SortBy/3

`SortBy(Goal, List, Sorted)` — sort by key projected via `Goal(Elem, Key)`. Stable sort.

```
sort_by_abs(Xs_, Ss_) <- SortBy(((X_, K_) <- (K_ := abs(X_))), Xs_, Ss_)
```

### MaxBy/3, MinBy/3

`MaxBy(Goal, List, Max)` / `MinBy(Goal, List, Min)` — element with largest/smallest key. Fails on empty list.

### FilterMap/3

`FilterMap(Goal, List, Result)` — map + filter in one pass. Calls `Goal(Elem, Out)` for each element; keeps Out when goal succeeds, skips when it fails.

```
double_positives(Xs_, Rs_) <- FilterMap(
    ((X_, Y_) <- (X_ > 0 and (Y_ := X_ * 2))),
    Xs_, Rs_
)
```

### Additional List Predicates

| Builtin | Arity | Description |
|---|---|---|
| `Unzip` | 3 | `Unzip(Pairs, Keys, Values)` — split list of pairs |
| `PairKeys` | 2 | `PairKeys(Pairs, Keys)` — extract keys from pairs |
| `PairValues` | 2 | `PairValues(Pairs, Values)` — extract values from pairs |

---

## Combining Meta-Predicates with Lambdas

Meta-predicates take inline goal expressions (not closures), so lambdas aren't needed:

```
# FindAll with inline goal — no lambda required
squares(Ns_, Sqs_) <- FindAll(Sq_, (In(X_, Ns_) and (Sq_ := X_ * X_)), Sqs_)

# ForAll with inline condition and action
all_positive(Ns_) <- ForAll(In(X_, Ns_), X_ > 0)
```

Higher-order list predicates take closures, so lambdas are the natural fit:

```
# Filter with lambda
positives(Xs_, Ps_) <- Filter((X_ <- (X_ > 0)), Xs_, Ps_)
```

See [Lambdas](lambdas.md) for full lambda syntax and semantics.

---

## Test Coverage

- `tests/test_meta.py` (23 tests): FindAll, BagOf, SetOf, ForAll, Call/N, `.clausal` integration
- `tests/test_higher_order.py` (28 tests): MapList/2,3, Filter/3, Exclude/3, FoldLeft/4
