# Meta-Predicates & Higher-Order

Clausal Prolog provides meta-predicates for collecting solutions and higher-order list predicates for functional-style list processing. Meta-predicates take an ordinary goal as an argument (in the seam they are compiler special forms, compiled inline); higher-order list predicates are builtins that take goal closures.

!!! note "Clausal Prolog and the seam"

    Examples on this page are [Clausal Prolog](clausal_prolog.md)
    (`.clausal`, ISO Prolog syntax). Their lambdas are `library(lambda)`'s
    `\X^Goal` (see [Lambdas](lambdas.md)); the [seam](syntax.md) writes a
    lambda as an anonymous clause, `X <- Goal`.

---

## Meta-Predicates

Each takes an ordinary goal as an argument. In the seam they are compiler special forms, compiled inline rather than dispatched as builtins.

### findall/3

`findall(Template, Goal, Bag)` — collect all instances of Template for which Goal succeeds.

```clausal
:- use_module(library(clpz)).

squares(Ns, Sqs) :-
    findall(Sq, (in_(X, Ns), Sq #= X * X), Sqs).

test("squares") :-
    squares([1, 2, 3], Sqs),
    Sqs == [1, 4, 9].
```

If Goal has no solutions, Bag is unified with `[]`.

### bagof/3

`bagof(Template, Goal, Bag)` — like findall, but **fails** if Goal has no
solutions (findall returns `[]` instead), and it collects one bag per binding
of the goal's **free variables**: the variables of `Goal` that are neither in
`Template` nor marked existential with `Var ^ Goal`. It backtracks over the
bags in the standard order of those bindings, as ISO specifies and Scryer
does. With no free variables it is findall that fails on empty.

```clausal
age(alice, 30).
age(bob, 25).
age(dan, 12).

adults(People, Adults) :-
    bagof(P, A ^ (in_(P, People), age(P, A), A >= 18), Adults).

test("adults") :-
    adults([alice, bob, dan], Adults),
    Adults == [alice, bob].
```

Without the `A ^`, `A` is free and `adults` would answer one bag per age.

#### bagof vs findall

The only difference between bagof and findall is how they handle the empty case:

```clausal
age(alice, 30).
age(bob, 25).
age(carol, 30).

all_people(People) :-
    bagof(Name, Age ^ age(Name, Age), People).

test("bag of people") :-
    all_people(People),
    length(People, 3).

test("bagof fails on empty, findall does not") :-
    \+ bagof(X, in_(X, []), _),
    findall(X, in_(X, []), Bag),
    Bag == [].
```

Use bagof when you want failure on empty results, findall when you always want a list.

#### Free variables and `^`

```clausal
age(alice, 30).
age(bob, 25).
age(carol, 30).

test("one bag per age") :-
    findall(Age-Names, bagof(Name, age(Name, Age), Names), Bags),
    Bags == [25-[bob], 30-[alice, carol]].

test("an anonymous variable is free too") :-
    findall(L, bagof(N, age(N, _), L), Ls),
    Ls == [[bob], [alice, carol]].
```

An anonymous `_` in the goal is a free variable too: `bagof(N, age(N, _), L)`
answers one bag per age. `V ^ Goal` may be nested (`X ^ Y ^ p(X, Y, Z)`), and
a goal built at run time is read the same way
(`G = (Y ^ p(Y)), call(bagof(X, G, L))`). Solutions whose free-variable
bindings are variants share a bag.

### setof/3

`setof(Template, Goal, Set)` — like bagof (one set per binding of the free
variables, `^` for existential ones), but each bag is a **sorted list with
duplicates removed**. Also fails on no solutions.

```clausal
unique_members(Xs, Us) :-
    setof(X, in_(X, Xs), Us).

test("unique members") :-
    unique_members([b, a, b], Us),
    Us == [a, b].
```

#### setof vs sort(findall(...))

Both produce sorted, deduplicated results. The differences:

| | `setof(T, G, S)` | `findall(T, G, S0)` + `sort(S0, S)` |
|---|---|---|
| Empty result | **Fails** | Succeeds with `S = []` |
| Deduplication | Yes (sorted set) | Only if you call `sort` |
| Use when | You want failure on empty | You always want a list |

```clausal
test("setof unique") :-
    setof(X, in_(X, [3, 1, 2, 1, 3]), Xs),
    Xs == [1, 2, 3].

% setof fails if no solutions; findall always succeeds (returns []):
test("setof empty fails") :-
    \+ setof(X, (in_(X, []), X > 0), _).

test("findall empty ok") :-
    findall(X, (in_(X, []), X > 0), Bag),
    Bag == [].
```

### forall/2

`forall(Condition, Action)` — succeeds if for every solution of Condition, Action also succeeds. equivalent to `\+ (Condition, \+ Action)`. Like `once/1` and `\+`, it is a transition construct: **supported but discouraged**, because it is negation as failure underneath and so not monotone. It works, and is being phased out.

```clausal
all_positive(Xs) :-
    forall(in_(X, Xs), X > 0).

test("all positive") :-
    all_positive([1, 2, 3]),
    \+ all_positive([1, -2]).
```

#### forall Patterns

**Validate all elements**:

```clausal
all_in_range(Xs, Lo, Hi) :-
    forall(in_(X, Xs), (X >= Lo, X =< Hi)).

test("in range") :-
    all_in_range([1, 5, 3], 1, 5),
    \+ all_in_range([1, 6], 1, 5).
```

**Check a property across a collection**:

```clausal
% dif — see Constraints (constraints.md)
all_connected(Nodes, Graph) :-
    forall((in_(A, Nodes), in_(B, Nodes), dif(A, B)),
           reachable(A, B, Graph)).

reachable(A, B, Graph) :-
    in_(A-B, Graph).
reachable(A, B, Graph) :-
    in_(A-C, Graph),
    reachable(C, B, Graph).

test("connected") :-
    all_connected([a, b], [a-b, b-a]),
    \+ all_connected([a, b], [a-b]).
```

**Guard before processing**:

```clausal
safe_sum(Xs, Total) :-
    forall(in_(X, Xs), number(X)),
    sum_list(Xs, Total).

test("safe sum") :-
    safe_sum([1, 2, 3], Total),
    Total == 6,
    \+ safe_sum([1, a], _).
```

---

## call/N

`call/1..8` invokes a goal closure with 0–7 extra arguments. `call_goal/1..8` are aliases.

```clausal
apply(Goal, X) :-
    call(Goal, X).

apply2(Goal, X, Y) :-
    call(Goal, X, Y).

test("apply") :-
    apply(integer, 3),
    apply2(succ, 3, Y),
    Y == 4.
```

These are primarily used with [lambdas](lambdas.md):

```clausal
:- use_module(library(lambda)).
:- use_module(library(clpz)).

% R is the output, so it is shared through Free (R+\...)
plus_one(R) :-
    call(R+\X^(R #= X + 1), 5).

test("plus one") :-
    plus_one(R),
    R == 6.
```

---

## Higher-Order List Predicates

These builtins take a goal as their first argument — either a [lambda](lambdas.md) or a **predicate reference** (builtin or user-defined). `maplist` and `foldl` backtrack into the goal, as ISO's do (`maplist(\X^in_(X, [1, 2]), [A, B])` has four answers); `include` and `exclude` test each element once. See [Higher-Order](higher_order.md) for the dedicated reference page.

### maplist/2

`maplist(Goal, List)` — succeeds if Goal succeeds for every element of List.

```clausal
:- use_module(library(lambda)).

% With a lambda
all_positive(Xs) :-
    maplist(\X^(X > 0), Xs).

% With a builtin predicate
all_numbers(Xs) :-
    maplist(number, Xs).

test("maplist/2") :-
    all_positive([1, 2]),
    \+ all_positive([1, 0]),
    all_numbers([1, 2.5]).
```

### maplist/3

`maplist(Goal, List, ResultList)` — apply a binary goal to each element, collecting results.

```clausal
:- use_module(library(lambda)).
:- use_module(library(clpz)).

doubles(Xs, Ys) :-
    maplist(\X^Y^(Y #= X * 2), Xs, Ys).

test("doubles") :-
    doubles([1, 2, 3], Ys),
    Ys == [2, 4, 6].
```

### include/3

`include(Goal, List, Filtered)` — keep elements for which Goal succeeds.

```clausal
:- use_module(library(lambda)).

% With a lambda
positives(Xs, Ps) :-
    include(\X^(X > 0), Xs, Ps).

% With a builtin predicate
keep_numbers(Xs, Ns) :-
    include(number, Xs, Ns).

test("include") :-
    positives([1, -2, 3], Ps),
    Ps == [1, 3],
    keep_numbers([1, a, 2], Ns),
    Ns == [1, 2].
```

### exclude/3

`exclude(Goal, List, Remaining)` — keep elements for which Goal fails (complement of include).

```clausal
:- use_module(library(lambda)).

remove_zeros(Xs, Rs) :-
    exclude(\X^(X = 0), Xs, Rs).

test("exclude") :-
    remove_zeros([0, 1, 0, 2], Rs),
    Rs == [1, 2].
```

### foldl/4

`foldl(Goal, List, Acc0, Result)` — left fold with a ternary goal closure.

```clausal
:- use_module(library(lambda)).
:- use_module(library(clpz)).

fold_sum(Xs, S) :-
    foldl(\Elem^Acc^R^(R #= Acc + Elem), Xs, 0, S).

fold_product(Xs, P) :-
    foldl(\Elem^Acc^R^(R #= Acc * Elem), Xs, 1, P).

test("foldl") :-
    fold_sum([1, 2, 3], S),
    S == 6,
    fold_product([2, 3, 4], P),
    P == 24.
```

### take_while/3

`take_while(Goal, List, Prefix)` — longest prefix where Goal succeeds for each consecutive element.

```clausal
:- use_module(library(lambda)).

take_pos(Xs, Ps) :-
    take_while(\X^(X > 0), Xs, Ps).

% take_pos([3, 1, -2, 4], Ps) → Ps = [3, 1]
test("take_while") :-
    take_pos([3, 1, -2, 4], Ps),
    Ps == [3, 1].
```

### drop_while/3

`drop_while(Goal, List, Suffix)` — suffix after dropping the longest prefix where Goal succeeds.

```clausal
:- use_module(library(lambda)).

drop_pos(Xs, Rs) :-
    drop_while(\X^(X > 0), Xs, Rs).

% drop_pos([3, 1, -2, 4], Rs) → Rs = [-2, 4]
test("drop_while") :-
    drop_pos([3, 1, -2, 4], Rs),
    Rs == [-2, 4].
```

### span/4

`span(Goal, List, Yes, No)` — take_while + drop_while in one pass.

```clausal
:- use_module(library(lambda)).

split_pos(Xs, Yes, No) :-
    span(\X^(X > 0), Xs, Yes, No).

test("span") :-
    split_pos([3, 1, -2, 4], Yes, No),
    Yes == [3, 1],
    No == [-2, 4].
```

### group_by/3

`group_by(Goal, List, Groups)` — group consecutive elements by key projected via `Goal(Elem, Key)`.

```clausal
sign_key(X, pos) :- X > 0.
sign_key(X, neg) :- X =< 0.

by_sign(Xs, Gs) :-
    group_by(sign_key, Xs, Gs).

test("group_by") :-
    by_sign([1, 2, -1, 3], Gs),
    Gs == [[1, 2], [-1], [3]].
```

(The seam writes the key as a lambda over `if_/3`,
`((X, K) <- if_(X > 0, K is 'pos', K is 'neg'))`. In Clausal Prolog a
lambda can call `library(reif)`'s `if_/3` too, but `>` is not a reified
condition; with `library(clpz)` loaded, `\X^K^if_(0 #< X, K = pos, K = neg)`
is the same key.)

### sort_by/3

`sort_by(Goal, List, Sorted)` — sort by key projected via `Goal(Elem, Key)`. Stable sort.

```clausal
:- use_module(library(lambda)).

sort_by_abs(Xs, Ss) :-
    sort_by(\X^K^abs_(X, K), Xs, Ss).

test("sort_by") :-
    sort_by_abs([3, -1, 2], Ss),
    Ss == [-1, 2, 3].
```

### max_by/3, min_by/3

`max_by(Goal, List, Max)` / `min_by(Goal, List, Min)` — element with largest/smallest key. Fails on empty list.

```clausal
:- use_module(library(lambda)).

test("max_by and min_by") :-
    max_by(\X^K^(K is abs(X)), [3, -5, 2], Max),
    Max == -5,
    min_by(\X^K^(K is abs(X)), [3, -5, 2], Min),
    Min == 2,
    \+ max_by(\X^K^(K is abs(X)), [], _).
```

### filter_map/3

`filter_map(Goal, List, Result)` — map + filter in one pass. Calls `Goal(Elem, Out)` for each element; keeps Out when goal succeeds, skips when it fails.

```clausal
--8<-- "tests/fixtures/docs/meta_predicates_examples.clausal:filter_map_example"
```

### Additional List Predicates

| Builtin | Arity | Description |
|---|---|---|
| `pairs_keys_values` | 3 | `pairs_keys_values(Pairs, Keys, Values)` — split list of [pairs](pairs.md) |
| `pairs_keys` | 2 | `pairs_keys(Pairs, Keys)` — extract keys from [pairs](pairs.md) |
| `pairs_values` | 2 | `pairs_values(Pairs, Values)` — extract values from [pairs](pairs.md) |

```clausal
test("pairs") :-
    pairs_keys_values([a-1, b-2], Keys, Values),
    Keys == [a, b],
    Values == [1, 2],
    pairs_keys([a-1], [a]),
    pairs_values([a-1], [1]).
```

---

??? tip "Combining Meta-Predicates with Lambdas"

    The goal argument of a meta-predicate is an ordinary goal, so it needs no lambda:

    ```clausal
    --8<-- "tests/fixtures/docs/meta_predicates_examples.clausal:meta_with_inline"
    ```

    Higher-order list predicates take either lambdas or predicate references:

    ```clausal
    --8<-- "tests/fixtures/docs/meta_predicates_examples.clausal:higher_order_with_lambda"
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
