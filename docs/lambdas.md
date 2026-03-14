# Lambdas (Goal Closures)

Lambdas are anonymous clauses that can be passed as arguments to higher-order predicates. They use the same `head <- body` arrow syntax as clause definitions. Variables from the enclosing clause are captured implicitly — no special declarations are needed. Lambdas are the primary mechanism for higher-order logic programming in clausal.

The implementation lives in `clausal/logic/compiler.py` (codegen), `clausal/templating/term_rewriting.py` (term transformation), and `clausal/logic/builtins.py` (`call_goal` builtins). Added in V2-9.

---

## Syntax

Arrow lambdas use `head <- body` — the same syntax as clause definitions, making them anonymous clauses:

```
# One-arg lambda
apply_val(Result_, Val_) <- call_goal((X_ <- (Result_ is X_)), Val_)

# Two-arg lambda with arithmetic
test(R_) <- call_goal(((X_, Y_) <- (Y_ := X_ + 1)), 5, R_)

# Zero-arg lambda
run_goal(Result_) <- call_goal((() <- (Result_ is 42)))

# Captured variable from enclosing clause
add_z(Z_, R_) <- call_goal((X_ <- (R_ := X_ + Z_)), 10)
```

The head is a variable (single param) or tuple of variables (multiple params). The body is any goal expression — unification, arithmetic evaluation, predicate calls, or conjunctions.

### Conjunction bodies

Multiple goals are joined with `and`. Parenthesize each `:=` subgoal separately:

```
transform(R_) <- call_goal(((X_, Y_) <- ((T_ := X_ + 1) and (Y_ := T_ * 2))), 5, R_)
```

### Why arrow syntax?

Arrow lambdas are homoiconic — they look like the clause definitions they represent:

```
# Clause definition (statement level)
double(X_, Y_) <- (Y_ := X_ + X_)

# Anonymous clause (expression level) — same syntax
apply_double(V_, R_) <- call_goal((X_ <- (double(X_, R_))), V_)
```

Python's `lambda` syntax is not supported in `.clausal` files.

---

## Variable capture

Lambdas capture variables from the enclosing clause implicitly, using Python's native closure semantics. No `in` declaration or explicit free-variable marking is needed.

```
# Z_ and Result_ are captured from the enclosing clause head.
# X_ is a lambda parameter.
captured_add(Z_, Result_) <- call_goal((X_ <- (Result_ := X_ + Z_)), 10)
```

When queried as `captured_add(3, R_)`, this yields `R_ = 13`: the lambda captures `Z_` (bound to 3) and `Result_` from the clause, receives `X_` = 10 as a parameter, and evaluates `Result_ := 10 + 3`.

### How capture works

Variables fall into three categories inside a lambda body:

| Category | Example | How it works |
|---|---|---|
| **Parameter** | `X_` in `X_ <- (...)` | Function argument of the compiled lambda |
| **Captured** | `Z_` used in body but defined in enclosing clause | Python closure over the enclosing scope's Var |
| **Body-local** | `T_` first appearing inside the lambda body | Fresh `Var()` allocated inside the lambda function |

Captured variables share the same `Var` object as the enclosing clause. When the enclosing clause binds `Z_` to a value, the lambda sees that binding through the shared reference. This is correct because Python closures capture by reference, and logic variables are mutable (via trail-based binding).

### Parameter shadowing

If a lambda parameter has the same name as an enclosing variable, the parameter shadows it:

```
# X_ in the lambda body refers to the parameter, not the clause-head X_
test(X_) <- call_goal((X_ <- (X_ is 42)), _)
```

---

## Calling lambdas

Lambdas are invoked with the `call_goal` builtin, which takes a goal closure and optional extra arguments:

| Builtin | Usage |
|---|---|
| `call_goal/1` | `call_goal(Goal)` — call a zero-arg closure |
| `call_goal/2` | `call_goal(Goal, Arg1)` — call with one extra arg |
| `call_goal/3` | `call_goal(Goal, Arg1, Arg2)` — call with two extra args |

The extra arguments are passed as positional parameters to the lambda:

```
# lambda receives X_ = 5
call_goal((X_ <- (X_ > 0)), 5)

# lambda receives X_ = 5, Y_ = Result_
call_goal(((X_, Y_) <- (Y_ := X_ * 2)), 5, Result_)
```

### Multi-solution lambdas

A lambda can produce multiple solutions. If the lambda body calls a multi-solution predicate, each solution is propagated to the caller:

```
color("red"),
color("green"),
color("blue"),

get_color(C_) <- call_goal((X_ <- (color(X_) and C_ is X_)), _)
```

Querying `get_color(C_)` yields three solutions: `C_ = "red"`, `C_ = "green"`, `C_ = "blue"`.

---

## Calling predicates from lambdas

Lambda bodies can call user-defined predicates. Internally, this works through the `_tramp_call` bridge, which adapts between the lambda's simple-mode execution and the predicate's trampoline-mode dispatch:

```
double(X_, Y_) <- (Y_ := X_ + X_)

apply_double(Val_, Result_) <- call_goal((X_ <- (double(X_, Result_))), Val_)
```

This is transparent — no special syntax is needed. The bridge (`_tramp_call`) handles the protocol mismatch automatically.

---

## Compilation

Lambdas compile to **simple-mode** Python generator functions. A lambda like:

```
(X_, Y_) <- (Y_ := X_ + Z_)
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

When a lambda appears as an argument to a predicate call, the compiler **hoists** it: the `FunctionDef` is emitted before the call statement, and the lambda argument is replaced with a reference to the generated function name. This means the lambda is compiled once and called by reference.

---

## Anonymous variables

`_` in a lambda body is the anonymous variable — each occurrence is a fresh `Var()`:

```
get_color(C_) <- call_goal((X_ <- (color(X_) and C_ is X_)), _)
```

Here `_` as the second arg to `call_goal` is a fresh throwaway variable.

---

## Limitations

- **Lambdas are only supported as predicate call arguments.** Using a lambda in other positions (e.g., `X_ is (X_ <- ...)`) raises `NotImplementedError`.
- **Nested lambdas are supported** for variable capture but are an edge case. Inner lambdas can reference outer lambda parameters via closure.
- **No pattern-matching on parameters.** Lambda parameters are positional arguments, not patterns. Use a predicate clause for pattern matching.

---

## Python API

Lambdas are a `.clausal` file feature — they are compiled from source by the term transformer and compiler. From pure Python, you can construct the equivalent term tree manually:

```python
from clausal.pythonic_ast import nodes as sa
from clausal.terms import Evaluate, Add, LoadName
from clausal.logic.variables import Var

result = Var()
lam = sa.Lambda(
    params=sa.Params(params=[sa.PosOrKwParam(name="X_")]),
    body=Evaluate(left=result, right=Add(left=LoadName(name="X_"), right=1)),
)
```

In practice, lambdas are most naturally written in `.clausal` files where the term transformer handles the translation automatically.

---

## Test coverage

Tests are in `tests/test_lambdas.py`.

- **TermTransformer**: arrow syntax produces Lambda nodes, param generates LoadName (not Var), captures enclosing Var, body vars don't leak, nested lambda capture, anonymous `_`, Python lambda rejected
- **Compiler**: produces FunctionDef, params as function args, captured vars as closure refs, conjunction flattening
- **Runtime**: `call_goal/1,2,3` with zero/one/two-arg closures, failing closure, multi-solution closure
- **Compiled execution**: lambda with arithmetic body, captured var, unification body, failing body, conjunction body
- **Import integration**: `.clausal` file with unification, captured head var, conjunction, zero-arg, predicate calls, multi-solution, `:=` arithmetic
