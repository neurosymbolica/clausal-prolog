# Lambdas (Goal Closures)

Lambdas are anonymous clauses that can be passed as arguments to [higher-order predicates](higher_order.md). They use the same `head <- body` arrow syntax as clause definitions. Variables from the enclosing clause are captured implicitly — no special declarations are needed. Lambdas are the primary mechanism for higher-order logic programming in clausal.

The implementation lives in `clausal/logic/compiler.py` (codegen), `clausal/templating/term_rewriting.py` (term transformation), and `clausal/logic/builtins.py` (`call_goal` builtins).

---

## Syntax

Arrow lambdas use `head <- body` — the same syntax as clause definitions, making them anonymous clauses:

```clausal
# One-arg lambda
apply_val(RESULT, VAL) <- call_goal((X <- (RESULT is X)), VAL)

# Two-arg lambda with arithmetic
test(R) <- call_goal(((X, Y) <- (Y == X + 1)), 5, R)

# Zero-arg lambda
run_goal(RESULT) <- call_goal((() <- (RESULT is 42)))

# Captured variable from enclosing clause
add_z(Z, R) <- call_goal((X <- (R == X + Z)), 10)
```

The head is a variable (single param) or tuple of variables (multiple params). The body is any goal expression — unification, arithmetic evaluation, predicate calls, or conjunctions.

### Conjunction bodies

Multiple goals are separated with `,` inside `(...)`:

```clausal
transform(R) <- call_goal(((X, Y) <- (T == X + 1, Y == T * 2)), 5, R)
```

### Why arrow syntax?

Arrow lambdas are homoiconic — they look like the clause definitions they represent:

```clausal
# Clause definition (statement level)
double(X, Y) <- (Y == X + X)

# Anonymous clause (expression level) — same syntax
apply_double(V, R) <- call_goal((X <- (double(X, R))), V)
```

Python's `lambda` syntax is not supported in `.clausal` files.

---

## Variable capture

Lambdas capture variables from the enclosing clause implicitly, using Python's native closure semantics. No `in` declaration or explicit free-variable marking is needed.

```clausal
# Z and RESULT are captured from the enclosing clause head.
# X is a lambda parameter.
captured_add(Z, RESULT) <- call_goal((X <- (RESULT == X + Z)), 10)
```

when queried as `captured_add(3, R)`, this yields `R = 13`: the lambda captures `Z` (bound to 3) and `RESULT` from the clause, receives `X` = 10 as a parameter, and evaluates `RESULT == 10 + 3`.

### How capture works

Variables fall into three categories inside a lambda body:

| Category | Example | How it works |
|---|---|---|
| **Parameter** | `X` in `X <- (...)` | Function argument of the compiled lambda |
| **Captured** | `Z` used in body but defined in enclosing clause | Python closure over the enclosing scope's Var |
| **Body-local** | `T` first appearing inside the lambda body | Fresh `Var()` allocated inside the lambda function |

Captured variables share the same `Var` object as the enclosing clause. when the enclosing clause binds `Z` to a value, the lambda sees that binding through the shared reference. This is correct because Python closures capture by reference, and logic variables are mutable (via trail-based binding).

### Parameter shadowing

If a lambda parameter has the same name as an enclosing variable, the parameter shadows it:

```clausal
# X in the lambda body refers to the parameter, not the clause-head X
test(X) <- call_goal((X <- (X is 42)), _)
```

---

## Calling lambdas

Lambdas are invoked with the `call_goal` builtin, which takes a goal closure and optional extra arguments:

| Builtin | Usage |
|---|---|
| `call_goal/1` | `call_goal(Goal)` — call a zero-arg closure |
| `call_goal/2` | `call_goal(Goal, Arg1)` — call with one extra arg |
| `call_goal/3` | `call_goal(Goal, Arg1, Arg2)` — call with two extra args |
| `call_goal/4..8` | Higher arities, same pattern |
| `call/1..8` | Aliases for `call_goal/1..8` |

The extra arguments are passed as positional parameters to the lambda:

```clausal
--8<-- "tests/fixtures/docs/lambdas_sigs.txt:call_goal_examples"
```

### Multi-solution lambdas

A lambda can produce multiple solutions. If the lambda body calls a multi-solution predicate, each solution is propagated to the caller:

```clausal
color("red"),
color("green"),
color("blue"),

get_color(C) <- call_goal((X <- (color(X), C is X)), _)
```

Querying `get_color(C)` yields three solutions: `C = "red"`, `C = "green"`, `C = "blue"`.

---

## Calling predicates from lambdas

Lambda bodies can call user-defined predicates. Internally, this works through the `_tramp_call` bridge, which adapts between the lambda's simple-mode execution and the predicate's trampoline-mode dispatch:

```clausal
double(X, Y) <- (Y == X + X)

apply_double(VAL, RESULT) <- call_goal((X <- (double(X, RESULT))), VAL)
```

This is transparent — no special syntax is needed. The bridge (`_tramp_call`) handles the protocol mismatch automatically.

---

## Compilation

Lambdas compile to **simple-mode** Python generator functions. A lambda like:

```clausal
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

when a lambda appears as an argument to a predicate call, the compiler **hoists** it: the `FunctionDef` is emitted before the call statement, and the lambda argument is replaced with a reference to the generated function name. This means the lambda is compiled once and called by reference.

---

## Anonymous variables

`_` in a lambda body is the anonymous variable — each occurrence is a fresh `Var()`:

```clausal
get_color(C) <- call_goal((X <- (color(X), C is X)), _)
```

Here `_` as the second arg to `call_goal` is a fresh throwaway variable.

---

## Lambdas with meta-predicates

Lambdas combine naturally with [findall, bagof, setof, and forall](meta_predicates.md). The goal argument to these meta-predicates can be any goal expression, including lambda calls:

```clausal
# Collect squares of a list using a lambda
squares(NS, SQS) <- (
    findall(
        SQ,
        (in_(X, NS), SQ == X * X),
        SQS,
    )
)

# include with forall
all_positive(NS) <- forall(in_(X, NS), X > 0)
```

Since `findall` and friends are compiler special forms, the goal argument is compiled inline — it is not passed as a closure. This means any goal expression works directly as the second argument, without needing to wrap it in a lambda.

---

## Lambdas with higher-order list predicates

The [higher-order list builtins](higher_order.md) — `maplist`, `include`, `exclude`, `foldl` — take a **callable goal** as a runtime argument. This can be a lambda (goal closure) or a **predicate reference** (builtin or user-defined):

```clausal
--8<-- "tests/fixtures/docs/lambdas_sigs.txt:builtin_as_goal"
```

when the goal logic is more complex than a single predicate call, lambdas are the natural choice:

```clausal
# maplist/3 — double every element
doubles(XS, YS) <- maplist(((X, Y) <- (Y == X * 2)), XS, YS)

# maplist/2 — check all positive
all_pos(XS) <- maplist((X <- (X > 0)), XS)

# include/3 — filter positive elements
positives(XS, PS) <- include((X <- (X > 0)), XS, PS)

# exclude/3 — remove even elements
remove_evens(XS, RS) <- exclude((X <- (M == X % 2, M is 0)), XS, RS)

# foldl/4 — sum a list
fold_sum(XS, S) <- foldl(((E, A, R) <- (R == A + E)), XS, 0, S)
```

All higher-order list predicates use **committed choice** — they take the first solution from the goal for each element. This is consistent with the Pythonic philosophy and sufficient for lambda goals, which are typically deterministic.

---

## Limitations

- **Lambdas are only supported as predicate call arguments.** Using a lambda in other positions (e.g., `X is (X <- ...)`) raises `NotImplementedError`.
- **Nested lambdas are supported** for variable capture but are an edge case. Inner lambdas can reference outer lambda parameters via closure.
- **No pattern-matching on parameters.** Lambda parameters are positional arguments, not patterns. Use a predicate clause for pattern matching.

---

??? example "Python API"

    Lambdas are a `.clausal` file feature — they are compiled from source by the term transformer and compiler. From pure Python, you can construct the equivalent term tree manually:

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

    in_ practice, lambdas are most naturally written in `.clausal` files where the term transformer handles the translation automatically.

    ---

??? info "Test coverage"

    Tests are in `tests/test_lambdas.py` and `tests/test_higher_order.py`.

    - **TermTransformer**: arrow syntax produces Lambda nodes, param generates LoadName (not Var), captures enclosing Var, body vars don't leak, nested lambda capture, anonymous `_`, Python lambda rejected
    - **Compiler**: produces FunctionDef, params as function args, captured vars as closure refs, conjunction flattening
    - **Runtime**: `call_goal/1..8` and `call/1..8` with zero to seven extra-arg closures, failing closure, multi-solution closure
    - **Compiled execution**: lambda with arithmetic body, captured var, unification body, failing body, conjunction body
    - **Import integration**: `.clausal` file with unification, captured head var, conjunction, zero-arg, predicate calls, multi-solution, `==` arithmetic
    - **Higher-order builtins**: maplist/2 (all succeed, one fails, empty list, non-list, non-callable), maplist/3 (double, empty, fail mid-list), include/3 (filter positive, all/none match, empty), exclude/3 (mirror of include), foldl/4 (sum, product, empty, fail mid-fold)

---

*See also: [Higher-Order](higher_order.md) — `maplist`, `include`, `foldl` and friends · [Meta-Predicates](meta_predicates.md) — `findall`, `bagof`, `setof`, `forall`, `Call/N` · [Python Interop](python_integration.md) — `++()` escape for calling Python from clause bodies.*
