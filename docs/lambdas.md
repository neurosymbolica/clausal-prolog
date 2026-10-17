# Lambdas (Goal Closures)

Lambdas are anonymous goals that can be passed as arguments to [higher-order predicates](higher_order.md). In [Clausal Prolog](clausal_prolog.md) (`.clausal`, the syntax of the examples on this page) a lambda is a term of Ulrich Neumerkel's `library(lambda)`, as in Scryer Prolog: `\X^Goal` takes a parameter `X`, and `Free+\X^Goal` also shares the variables of `Free` with the enclosing clause. It is applied with `call/N`, like any other goal.

The [seam](syntax.md) has its own lambda: an anonymous clause, `head <- body`, which captures the enclosing clause's variables implicitly and compiles to a Python generator. The sections marked *seam* below describe it.

The implementation lives in `clausal/logic/builtins/lambda_lib.py` (`library(lambda)`); for the seam's arrow lambdas, in `clausal/logic/compiler/` (codegen), `clausal/templating/term_rewriting.py` (term transformation), and `clausal/logic/builtins/` (`call_goal` builtins).

---

## Syntax

`\X1^...^Xn^Goal` is a lambda with parameters `X1` ... `Xn`:

```clausal
:- use_module(library(lambda)).
:- use_module(library(clpz)).

% One-arg lambda; Result is shared, so it is named in Free
apply_val(Result, Val) :-
    call(Result+\X^(Result = X), Val).

% Two-arg lambda with arithmetic
succ_of(R) :-
    call(\X^Y^(Y #= X + 1), 5, R).

% Zero-arg lambda
run_goal(Result) :-
    call(Result+\(Result = 42)).

% Variables of the enclosing clause, shared through Free
add_z(Z, R) :-
    call([Z, R]+\X^(R #= X + Z), 10).

test("one arg") :-
    apply_val(R, 7),
    R == 7.

test("two args") :-
    succ_of(R),
    R == 6.

test("zero args") :-
    run_goal(R),
    R == 42.

test("shared variables") :-
    add_z(3, R),
    R == 13.
```

The parameters come first, each followed by `^`; the body is any goal —
unification, arithmetic, predicate calls, or conjunctions. A lambda is an
ordinary term (`\X^(X > 0)` is the term `\(X^(X > 0))`), so it can be stored,
passed around and inspected like any other.

### Conjunction bodies

Multiple goals are separated with `,` inside `(...)`:

```clausal
:- use_module(library(lambda)).
:- use_module(library(clpz)).

transform(R) :-
    call(\X^Y^(T #= X + 1, Y #= T * 2), 5, R).

test("conjunction") :-
    transform(R),
    R == 12.
```

### The seam's arrow lambdas (seam)

The seam writes a lambda as an anonymous clause, `head <- body`, in the same
syntax as its clause definitions. The head is a variable (single param) or a
tuple of variables (multiple params). This is seam syntax:

```seam
# One-arg lambda
apply_val(RESULT, VAL) <- call_goal((X <- (RESULT is X)), VAL)

# Two-arg lambda with arithmetic
succ_of(R) <- call_goal(((X, Y) <- (Y == X + 1)), 5, R)

# Zero-arg lambda
run_goal(RESULT) <- call_goal((() <- (RESULT is 42)))

# Captured variable from enclosing clause
add_z(Z, R) <- call_goal((X <- (R == X + Z)), 10)

# Clause definition (statement level)
double(X, Y) <- (Y == X + X)

# Anonymous clause (expression level) — same syntax
apply_double(V, R) <- call_goal((X <- (double(X, R))), V)
```

Python's `lambda` syntax is not supported in `.seam` files.

---

## Variable capture

A `library(lambda)` lambda is **copied** each time it is called: its
parameters and every other unbound variable in it are fresh in the copy,
so a lambda called twice never carries a binding from the first call into
the second. A variable that is already bound when the lambda is called
keeps its value (the copy has the value, not the variable). To share an
unbound variable with the enclosing clause, typically an output, name it
in `Free`:

```clausal
:- use_module(library(lambda)).
:- use_module(library(clpz)).

% Z is bound when the lambda runs; Result is the output, so it is in Free.
captured_add(Z, Result) :-
    call(Result+\X^(Result #= X + Z), 10).

% Without Free, the binding of Result stays inside the copy.
lost_add(Z, Result) :-
    call(\X^(Result #= X + Z), 10).

test("captured") :-
    captured_add(3, R),
    R == 13.

test("not shared") :-
    lost_add(3, R),
    var(R).
```

When queried as `captured_add(3, R)`, this yields `R = 13`: the lambda
receives `X` = 10 as a parameter, sees `Z` = 3, and shares `Result` with
the clause.

### How capture works (seam)

The seam's arrow lambdas capture the enclosing clause's variables
**implicitly**, by reference, with no `Free` term. Variables fall into three
categories inside a seam lambda body:

| Category | Example | How it works |
|---|---|---|
| **Parameter** | `X` in `X <- (...)` | Function argument of the compiled lambda |
| **Captured** | `Z` used in body but defined in enclosing clause | Python closure over the enclosing scope's Var |
| **Body-local** | `T` first appearing inside the lambda body | Fresh `Var()` allocated inside the lambda function |

Captured variables share the same `Var` object as the enclosing clause. when the enclosing clause binds `Z` to a value, the lambda sees that binding through the shared reference. This is correct because Python closures capture by reference, and logic variables are mutable (via trail-based binding).

### Parameter shadowing

A lambda parameter with the same name as an enclosing variable is a
different variable: the copy renames it.

```clausal
:- use_module(library(lambda)).

% X in the lambda is the parameter, not the clause-head X
shadowed(X) :-
    call(\X^(X = 42), _).

test("the head X stays unbound") :-
    shadowed(X),
    var(X).
```

---

## Calling lambdas

Lambdas are invoked with `call/N`, which takes a goal and extra arguments
(the seam's `call_goal/N` is the same builtin):

| Builtin | Usage |
|---|---|
| `call/1` | `call(Goal)` — call a zero-arg closure |
| `call/2` | `call(Goal, Arg1)` — call with one extra arg |
| `call/3` | `call(Goal, Arg1, Arg2)` — call with two extra args |
| `call/4..8` | Higher arities, same pattern |
| `call_goal/1..8` | Aliases for `call/1..8` |

The extra arguments are passed as the lambda's parameters, in order:

```clausal
:- use_module(library(lambda)).
:- use_module(library(clpz)).

% the lambda receives X = 5
test("one parameter") :-
    call(\X^(X > 0), 5).

% the lambda receives X = 5, Y = Result
test("two parameters") :-
    call(\X^Y^(Y #= X * 2), 5, Result),
    Result == 10.
```

### Multi-solution lambdas

A lambda can produce multiple solutions. If the lambda body calls a multi-solution predicate, each solution is propagated to the caller:

```clausal
:- use_module(library(lambda)).

color(red).
color(green).
color(blue).

get_color(C) :-
    call(C+\X^(color(X), C = X), _).

test("three solutions") :-
    findall(C, get_color(C), Cs),
    Cs == [red, green, blue].
```

---

## Calling predicates from lambdas

Lambda bodies can call user-defined predicates, resolved in the calling
module:

```clausal
:- use_module(library(lambda)).
:- use_module(library(clpz)).

double(X, Y) :-
    Y #= X + X.

apply_double(Val, Result) :-
    call(Result+\X^double(X, Result), Val).

test("apply double") :-
    apply_double(5, R),
    R == 10.
```

This is transparent — no special syntax is needed. (In the seam, a call from
an arrow lambda's body goes through the `_tramp_call` bridge, which adapts
between the lambda's simple-mode execution and the predicate's
trampoline-mode dispatch.)

---

## Compilation (seam)

The seam's arrow lambdas compile to **simple-mode** Python generator functions. A lambda like (seam syntax):

```seam
--8<-- "tests/fixtures/docs/lambdas_sigs.txt:compilation_example"
```

compiles to approximately:

```python
def _lambda_0(X_, Y_, trail, k):
    # body compilation (simple mode)
    _arith_result = eval_arith(X_) + eval_arith(Z_)  # Z_ is a closure var
    _m = trail.mark()
    if unify(Y_, _arith_result, trail):
        yield None  # solution
    trail.undo(_m)
    return; yield  # ensure generator
```

Key details:
- Parameters become function arguments (not Var allocations)
- Captured variables are Python closure references to the enclosing scope's Vars
- Body-local variables get fresh `Var()` allocations inside the function
- The function yields `None` per solution (simple-mode protocol)
- Predicate calls in the body go through `_tramp_call` to bridge to trampoline mode

### Lambda hoisting

when a seam arrow lambda appears as an argument to a predicate call, the compiler **hoists** it: the `FunctionDef` is emitted before the call statement, and the lambda argument is replaced with a reference to the generated function name. This means the lambda is compiled once and called by reference.

---

## Anonymous variables

`_` in a lambda is the anonymous variable — each occurrence is a fresh variable:

```clausal
:- use_module(library(lambda)).

color(red).
color(green).

get_color(C) :-
    call(C+\X^(color(X), C = X), _).

test("anonymous argument") :-
    findall(C, get_color(C), Cs),
    Cs == [red, green].
```

Here `_` as the second arg to `call` is a fresh throwaway variable.

---

## Lambdas with meta-predicates

Lambdas combine naturally with [findall, bagof, setof, and forall](meta_predicates.md). The goal argument to these meta-predicates can be any goal expression, including lambda calls:

```clausal
:- use_module(library(clpz)).

% Collect squares of a list
squares(Ns, Sqs) :-
    findall(Sq, (in_(X, Ns), Sq #= X * X), Sqs).

% include with forall
all_positive(Ns) :-
    forall(in_(X, Ns), X > 0).

test("squares") :-
    squares([1, 2, 3], S),
    S == [1, 4, 9].

test("forall") :-
    all_positive([1, 2]),
    \+ all_positive([0, 1]).
```

The goal argument of `findall` and friends is an ordinary goal, so any goal
expression works directly as the second argument, without wrapping it in a
lambda. (In the seam they are compiler special forms and the goal is compiled
inline.)

---

## Lambdas with higher-order list predicates

The [higher-order list builtins](higher_order.md) — `maplist`, `include`, `exclude`, `foldl` — take a **callable goal** as a runtime argument. This can be a lambda or a **predicate reference** (builtin or user-defined):

```clausal
% Builtin predicates can be passed directly — no lambda needed
all_numbers(Xs) :-
    maplist(number, Xs).

keep_ints(Xs, Is) :-
    include(integer, Xs, Is).

incremented(Xs, Ys) :-
    maplist(succ, Xs, Ys).

test("predicate references") :-
    all_numbers([1, 2.0]),
    keep_ints([1, a, 2.0, 3], Is),
    Is == [1, 3],
    incremented([1, 2], Ys),
    Ys == [2, 3].
```

when the goal logic is more complex than a single predicate call, lambdas are the natural choice:

```clausal
:- use_module(library(lambda)).
:- use_module(library(clpz)).

% maplist/3 — double every element
doubles(Xs, Ys) :-
    maplist(\X^Y^(Y #= X * 2), Xs, Ys).

% maplist/2 — check all positive
all_pos(Xs) :-
    maplist(\X^(X > 0), Xs).

% include/3 — filter positive elements
positives(Xs, Ps) :-
    include(\X^(X > 0), Xs, Ps).

% exclude/3 — remove even elements
remove_evens(Xs, Rs) :-
    exclude(\X^(0 is X mod 2), Xs, Rs).

% foldl/4 — sum a list
fold_sum(Xs, S) :-
    foldl(\E^A^R^(R #= A + E), Xs, 0, S).

test("maplist/3") :-
    doubles([1, 2, 3], Ys),
    Ys == [2, 4, 6].

test("maplist/2") :-
    all_pos([1, 2]),
    \+ all_pos([1, -2]).

test("include/3") :-
    positives([1, -2, 3], Ps),
    Ps == [1, 3].

test("exclude/3") :-
    remove_evens([1, 2, 3, 4], Rs),
    Rs == [1, 3].

test("foldl/4") :-
    fold_sum([1, 2, 3], S),
    S == 6.
```

`maplist` and `foldl` backtrack into the goal, as ISO's (Scryer's) do:
`maplist(\X^in_(X, [1, 2]), [A, B])` has four answers, `A = 1, B = 1`;
`A = 1, B = 2`; `A = 2, B = 1`; `A = 2, B = 2`. `include/3` and `exclude/3`
test each element once, keeping its first solution. (The seam's arrow
lambdas behave the same.)

```clausal
:- use_module(library(lambda)).

test("maplist backtracks into the goal") :-
    findall(A-B, maplist(\X^in_(X, [1, 2]), [A, B]), Answers),
    Answers == [1-1, 1-2, 2-1, 2-2].

test("include keeps one answer per element") :-
    findall(L, include(\X^in_(X, [1, 1]), [1], L), Ls),
    Ls == [[1]].
```

---

## Limitations

- **A lambda copies its unbound variables.** An output must be named in
  `Free` (`R+\X^...`), or its binding stays inside the copy.
- **No pattern-matching on parameters.** Lambda parameters are positional,
  not patterns. Use a predicate clause for pattern matching.
- *Seam:* an arrow lambda is meant as a predicate call argument. In other
  positions (e.g., `X is (Y <- ...)`) it is not a term: `X` is bound to the
  compiled Python function, which no other predicate can inspect. Nested
  arrow lambdas are supported for variable capture but are an edge case:
  inner lambdas can reference outer lambda parameters via closure.

---

??? example "Python API"

    Arrow lambdas are a `.seam` file feature — they are compiled from source by the term transformer and compiler. From pure Python you can construct the equivalent AST tree manually (internal API, not part of [the 1.0 surface](public-api.md)):

    ```python
    from clausal.pythonic_ast import nodes as sa
    from clausal.terms import Evaluate, Add, LoadName
    from clausal.logic.variables import Var
    
    result = Var()
    lam = sa.Lambda(
        params=sa.Params(params=[sa.PosOrKwParam(name="_x")]),
        body=Evaluate(left=result, right=Add(left=LoadName(name="_x"), right=1)),
    )
    ```

    In practice, lambdas are most naturally written in `.seam` files where the term transformer handles the translation automatically.

    ---

??? info "Test coverage"

    Tests are in `tests/test_lambdas.py` and `tests/test_higher_order.py`.

    - **TermTransformer**: arrow syntax produces Lambda nodes, param generates LoadName (not Var), captures enclosing Var, body vars don't leak, nested lambda capture, anonymous `_`, Python lambda rejected
    - **Compiler**: produces FunctionDef, params as function args, captured vars as closure refs, conjunction flattening
    - **Runtime**: `call_goal/1..8` and `call/1..8` with zero to seven extra-arg closures, failing closure, multi-solution closure
    - **Compiled execution**: lambda with arithmetic body, captured var, unification body, failing body, conjunction body
    - **Import integration**: `.seam` file with unification, captured head var, conjunction, zero-arg, predicate calls, multi-solution, `==` arithmetic
    - **Higher-order builtins**: maplist/2 (all succeed, one fails, empty list, non-list, non-callable), maplist/3 (double, empty, fail mid-list), include/3 (filter positive, all/none match, empty), exclude/3 (mirror of include), foldl/4 (sum, product, empty, fail mid-fold)

---

*See also: [Higher-Order](higher_order.md) — `maplist`, `include`, `foldl` and friends · [Meta-Predicates](meta_predicates.md) — `findall`, `bagof`, `setof`, `forall`, `call/N` · [Python Interop](python_integration.md) — the seam's `++()` escape for calling Python from clause bodies.*
