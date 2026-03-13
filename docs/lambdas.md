# Lambdas (Goal Closures)

Lambdas are anonymous goal closures that use Python's native `lambda` syntax. They capture variables from the enclosing clause by implicit closure — no special declarations are needed. Lambdas are the primary mechanism for higher-order logic programming in clausal.

The implementation lives in `clausal/logic/compiler.py` (codegen), `clausal/templating/term_rewriting.py` (term transformation), and `clausal/logic/builtins.py` (`call_goal` builtins). Added in V2-9.

---

## Basic syntax

A lambda is written exactly as a Python lambda, where the body is a goal (or conjunction of goals):

```
# Zero-arg lambda (goal closure)
run_goal(Result_) <- call_goal((lambda: Result_ is 42))

# One-arg lambda
apply_val(Result_, Val_) <- call_goal((lambda X_: Result_ is X_), Val_)

# Two-arg lambda with arithmetic
test(R_) <- call_goal((lambda X_, Y_: Y_ := X_ + 1), 5, R_)
```

Lambda parameters are logic variables (trailing underscore or ALL-CAPS). The body can be any goal expression — unification, arithmetic evaluation, predicate calls, or conjunctions.

### Conjunction bodies

Multiple goals in a lambda body are joined with `and` (not commas — commas would be parsed as Python tuple syntax):

```
test(R_) <- call_goal((lambda X_, Y_: (T_ := X_ + 1 and Y_ := T_ * 2)), 5, R_)
```

Parentheses around the conjunction body are required for the same reason as in clause bodies — they prevent Python's parser from mis-parsing the operator precedence.

---

## Variable capture

Lambdas capture variables from the enclosing clause implicitly, using Python's native closure semantics. No `in` declaration or explicit free-variable marking is needed.

```
# Z_ and Result_ are captured from the enclosing clause head.
# X_ is a lambda parameter.
captured_add(Z_, Result_) <- call_goal((lambda X_: Result_ := X_ + Z_), 10)
```

When queried as `captured_add(3, R_)`, this yields `R_ = 13`: the lambda captures `Z_` (bound to 3) and `Result_` from the clause, receives `X_` = 10 as a parameter, and evaluates `Result_ := 10 + 3`.

### How capture works

Variables fall into three categories inside a lambda body:

| Category | Example | How it works |
|---|---|---|
| **Parameter** | `X_` in `lambda X_: ...` | Function argument of the compiled lambda |
| **Captured** | `Z_` used in body but defined in enclosing clause | Python closure over the enclosing scope's Var |
| **Body-local** | `T_` first appearing inside the lambda body | Fresh `Var()` allocated inside the lambda function |

Captured variables share the same `Var` object as the enclosing clause. When the enclosing clause binds `Z_` to a value, the lambda sees that binding through the shared reference. This is correct because Python closures capture by reference, and logic variables are mutable (via trail-based binding).

### Parameter shadowing

If a lambda parameter has the same name as an enclosing variable, the parameter shadows it:

```
# X_ in the lambda body refers to the parameter, not the clause-head X_
test(X_) <- call_goal((lambda X_: X_ is 42), _)
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
call_goal((lambda X_: X_ > 0), 5)

# lambda receives X_ = 5, Y_ = Result_
call_goal((lambda X_, Y_: Y_ := X_ * 2), 5, Result_)
```

### Multi-solution lambdas

A lambda can produce multiple solutions. If the lambda body calls a multi-solution predicate, each solution is propagated to the caller:

```
color("red"),
color("green"),
color("blue"),

get_color(C_) <- call_goal((lambda X_: color(X_) and C_ is X_), _)
```

Querying `get_color(C_)` yields three solutions: `C_ = "red"`, `C_ = "green"`, `C_ = "blue"`.

---

## Calling predicates from lambdas

Lambda bodies can call user-defined predicates. Internally, this works through the `_tramp_call` bridge, which adapts between the lambda's simple-mode execution and the predicate's trampoline-mode dispatch:

```
double(X_, Y_) <- (Y_ := X_ + X_)

apply_double(Val_, Result_) <- call_goal((lambda X_: double(X_, Result_)), Val_)
```

This is transparent — no special syntax is needed. The bridge (`_tramp_call`) handles the protocol mismatch automatically.

---

## Compilation

Lambdas compile to **simple-mode** Python generator functions. A lambda like:

```
lambda X_, Y_: Y_ := X_ + Z_
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
get_color(C_) <- call_goal((lambda X_: color(X_) and C_ is X_), _)
```

Here `_` as the second arg to `call_goal` is a fresh throwaway variable.

---

## Limitations

- **Lambdas are only supported as predicate call arguments.** Using a lambda in other positions (e.g., `X_ is (lambda Y_: ...)`) raises `NotImplementedError`.
- **Nested lambdas are supported** for variable capture but are an edge case. Inner lambdas can reference outer lambda parameters via closure.
- **No pattern-matching on parameters.** Lambda parameters are positional arguments, not patterns. `lambda [H_, *T_]: ...` is not supported — use a predicate clause for pattern matching.

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

- **TermTransformer** (Phase 1): param generates LoadName (not Var), captures enclosing Var, body vars don't leak, nested lambda capture, anonymous `_`
- **Compiler** (Phase 2): produces FunctionDef, params as function args, captured vars as closure refs, conjunction flattening
- **Runtime** (Phase 3): `call_goal/1,2,3` with zero/one/two-arg closures, failing closure, multi-solution closure
- **Compiled execution** (Phase 2+3): lambda with arithmetic body, captured var, unification body, failing body, conjunction body
- **Import integration** (Phase 4): `.clausal` file with lambda + unification, captured head var, conjunction, zero-arg lambda, lambda calling user predicate, lambda calling multi-solution predicate
