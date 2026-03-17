# Clausal — Syntax Design

Clausal does not follow ISO Prolog syntax. It uses Python syntax throughout — all clausal code is valid Python, acceptable to the Python parser without modification. No separate parser is needed. This was a fundamental design decision: Python programmers should not have to learn a foreign syntax to use logic programming.

The tradeoffs this creates (mainly around the unification operator and some operators) are documented below, with the reasoning behind each choice.

---

## The key rule

**Expression statements ending in `,` are interpreted as logical terms (facts or goals).**

In standard Python, an expression statement that produces a tuple has no effect whatsoever. This means trailing commas can be used as delimiters without disturbing any existing Python code. It also means logic terms are easy to cut, copy, paste, and indent — they don't require `.` terminators that would conflict with Python's attribute access syntax.

---

## Escape operators

Three double-prefix operators demarcate the boundary between Python and logic code. They must not be split with spaces (e.g. `- -` would be parsed as double negation).

| Operator | Meaning |
|---|---|
| `--expr` | Python expression embedded inside a logic term |
| `++expr` | In Python context: logic term inside a Python expression. In `.clausal` context: evaluate Python expression at search time (V2-16) |
| `~~expr` | Capture expression as a `simple_ast` AST node (works anywhere) |

`--` was chosen because:
- it doesn't introduce a new keyword or clobber any identifier
- double negation is rare in Python code (and where it occurs, spacing makes it legible)
- it is visually prominent and quick to type

Example:
```python
# Logic term containing a Python value:
point(--x_coord, --y_coord),

# Python expression containing a logic term:
my_term = ++foo(X, bar(Y))

# Capture Python code as AST without running it:
ast_node = ~~(x + y * z)

# Capture a block of statements as AST:
with ... as block:
    result = f(x)
    return result
```

---

## Logic variables

Two conventions are recognised:

**Trailing single underscore** — any identifier whose last character is `_`, excluding dunders (`__`) and the bare anonymous variable `_`:

```python
X_, HEAD_, rest_   # logic variables (trailing-underscore style)
```

**ALL-CAPS** — any identifier where every cased character is uppercase and there is at least one cased character (underscores and digits are allowed inside):

```python
X, HEAD, REST, N1, MAX_OF   # logic variables (ALL-CAPS style)
```

Both styles may be used in the same file. ALL-CAPS is the preferred style for new code; trailing-underscore remains valid.

A single `_` is the anonymous variable — it never stores a value, and unification against it always succeeds (matching Python's existing convention).

Logic variables are not declared; they come into existence by appearing in logical context. They work differently from Python variables: they can be unbound, and their bindings are undone on backtracking. This difference warrants a clear visual marker.

Why not titlecase (the Prolog convention)?
- Python programmers associate titlecase with class names — static, global, noun-like. This is actually close to how atoms behave, not variables.
- ALL-CAPS is used in many languages for constants and distinguished names; here it marks the variable role in the logic sense.
- Single letters like `X`, `Y`, `N` are universally understood as logic variables from mathematics.

---

## Atoms

Inside a logical term:
- identifiers in `TitleCase` or `lowercase` that are not logic variable names are atoms
- string literals are atoms (except those prefixed with `u"..."`)

```python
# These are equivalent:
Atom is 'Atom',
(x is not 2) is 'is not'(x, 2),
```

Atoms that conflict with Python built-ins or that use non-identifier characters are written as strings: `'+'`, `'is not'`, `'max'`.

---

## Builtin predicate naming

All built-in predicates use **PascalCase** (e.g. `FindAll`, `In`, `Assert`, `IsVar`). This is a deliberate design choice — not aesthetic — with two goals:

1. **Avoid Python keyword conflicts.** Many natural predicate names are Python reserved words: `not`, `in`, `is`, `and`, `or`, `if`, `for`, `assert`, `lambda`, `global`, `return`, `yield`. A Prolog-style lowercase predicate named `in` or `not` would be a syntax error the moment it appears as a function call in a clause body.

2. **Avoid Python builtin conflicts.** Names like `abs`, `all`, `any`, `callable`, `filter`, `float`, `int`, `map`, `max`, `min`, `set`, `str`, `sum`, `var` are Python builtins that shadow (or would shadow) predicates if used lowercase.

PascalCase keeps the builtin namespace cleanly separate from both Python keywords and user-defined (lowercase) predicates. User predicates are written in `lowercase` or `snake_case` as usual; they never conflict with builtins.

---

## Unification

Unification is written with `is`:

```python
X is 42,
X is Y,
X is not Y,   # disequality constraint (dif/2)
```

Why `is` rather than `=`?
- `=` is Python's assignment operator and cannot appear in expressions
- `is` expresses the same concept in English — two things being the same — and Python programmers understand it

`X is not Y` posts a disequality constraint (`dif/2`): X and Y must end up with different values. This is lazily checked — the constraint is re-evaluated each time either variable gets bound. If they become equal, the constraint fails and the search backtracks. If they remain different, the constraint is satisfied and dropped. See [constraints.md](constraints.md) for details.

`not (X is Y)` is the immediate check (Prolog `\=/2`): it fails if X and Y *can* unify right now, regardless of future bindings. Use this when you want point-in-time semantics.

The corresponding AST node is `Unify(left, right)`. Disequality is `DoesNotUnify(left, right)`.

---

## Arithmetic binding

To evaluate an arithmetic expression and bind the result to a variable, use the walrus operator `:=`:

```python
fib(N, RESULT) <- (
    N > 1,
    N1 := N - 1,
    N2 := N - 2,
    fib(N1, A),
    fib(N2, B),
    RESULT := A + B
)
```

`N1 := N - 1` evaluates `N - 1` as Python arithmetic and unifies the result with `N1`. This is equivalent to Prolog's `is` operator. No extra parentheses are needed: clause bodies are already inside `(...)`, and `:=`'s RHS is a `test` expression in Python's grammar so it does not consume the comma that follows.

The distinction from `is`:
- `X is Y` — pure structural unification; neither side is evaluated arithmetically
- `(X := expr)` — `expr` is evaluated as arithmetic before unification; `X` should be unbound

The corresponding AST node is `Evaluate(left, right)`. The compiler applies `arith_to_ast_expr` to the right side, producing native Python arithmetic that is evaluated before `unify` is called.

---

## Comparison operators (CLP(FD))

The comparison operators `==`, `!=`, `<`, `>`, `<=`, `>=` are CLP(FD) (Constraint Logic Programming over Finite Domains) operators. They post constraints on integer variables rather than performing immediate checks.

```python
bounded(X) <- (
    InDomain(X, 1, 10)
    and X > 3
    and X < 8
    and Label([X])
)
```

When both sides are ground (no unbound Vars), the operators fall back to direct Python comparison — `3 == 3` is True, `3 < 2` is False — so existing ground arithmetic code works unchanged.

When at least one side is an unbound Var, a CLP(FD) constraint is posted:
- `X == 5` narrows X's domain to `{5}` (and binds it)
- `1 <= X` and `X <= 10` constrain X's domain to `[1, 10]`
- `X != 3` removes 3 from X's domain
- `X < Y` narrows X's upper bound and Y's lower bound

| Operator | CLP(FD) meaning |
|---|---|
| `==` | Arithmetic equality constraint |
| `!=` | Arithmetic disequality constraint |
| `<` `>` `<=` `>=` | Comparison constraints (narrow domain bounds) |

The old structural-equality behaviour of `==` is available as the builtin `Equivalent(X, Y)`. Use `Equivalent` when comparing non-integer terms where CLP(FD) semantics are not appropriate.

See [constraints.md](constraints.md) for the full CLP(FD) design, including domain representation, propagation, and labeling.

---

## Horn clauses

```python
Head <- Body,
```

The `<-` operator denotes a Horn clause (rule). It will never be added to Python's expression grammar because it conflicts with `x < -y` (less-than applied to a negated value) — but only when there is no surrounding whitespace. With whitespace, it is unambiguous and parseable.

### Body style

The body after `<-` must be one of:

- **A single call** — no parentheses needed:
  ```python
  sorted_asc([_]),
  palindrome(XS) <- reverse(XS, XS),
  ```

- **A bare name** — no parentheses needed:
  ```python
  always_true <- true,
  ```

- **Anything else** — parenthesized:
  ```python
  safe_max(X, Y, X) <- (X >= Y),
  fib(N, RESULT) <- (
      N > 1,
      N1 := N - 1,
      N2 := N - 2,
      fib(N1, A),
      fib(N2, B),
      RESULT := A + B
  )
  ```

This rule exists because Python's parser sees `<-` as `<` followed by unary `-`. When the body contains operators (`+`, `<`, `and`, `or`, `not`, etc.), the `-` gets absorbed into the body expression and the AST is silently mangled. Parentheses force Python to treat the body as a single grouped expression, keeping the `-` at the top where the term rewriter can find it. Calls and bare names are safe without parentheses because they bind tighter than unary `-`.

Attempting to write an unparenthesized operator body produces a clear error:

```
SyntaxError: clause body must be parenthesized or a single call:
    write  head <- (body)  or  head <- goal(X)
```

### Conjunction style

Multiple goals in a body are separated by commas, with each goal on its own line:

```python
is_permutation(XS, YS) <- (
    Length(XS, N),
    Length(YS, N),
    Sort(XS, S),
    Sort(YS, S)
)
```

Inside sub-expressions like `not (...)` or `... or ...`, use `and` instead of commas — commas inside these would be parsed as Python tuples:

```python
test("fails") <- (not (X is 1 and X is 2)),
test("either") <- (X is 1 or X is 2),
```

Facts (trivially true rules) are written without a body:

```python
parent(tom, bob),
parent(bob, ann),
```

Grammar rules (Definite Clause Grammars):

```python
Rule > ListDescription,
```

---

## Lists

```python
[]               # empty list (singleton)
[a, 1, X]        # a simple list
[FIRST, *REST]   # head/tail decomposition
[*BEFORE, PIVOT, *AFTER]  # multiple spread patterns
```

Partial lists (Prolog `[H|T]` where `T` is a variable) use Python's `*` spread syntax rather than `|`. The empty list is a singleton — unlike Python, two `[]` literals are the same object.

---

## Dicts

Python dict literals in `.clausal` files create `DictTerm` objects — unification-aware dictionaries. Keys must be ground; values may be logic variables.

```python
# Ground dict fact
point({"x": 0, "y": 0}),

# Dict pattern in head — X binds during unification
get_x({"x": X, "y": Y_}, X),

# Dict construction in body
make_point(X, Y, P) <- (P is {"x": X, "y": Y})

# Nested dicts
get_city({"address": {"city": C}}, C),
```

Two dicts unify iff they have the same keys and values unify pairwise. A variable unifies with a dict by binding to it.

See [dicts_sets.md](dicts_sets.md) for the full design.

---

## Sets

Python set literals in `.clausal` files create `SetTerm` objects — unification-aware sets. Elements must be ground (hashable).

```python
colors({1, 2, 3}),
primary({"red", "green", "blue"}),
```

Two sets unify iff they contain the same elements (order irrelevant). Variables in set elements are not supported.

See [dicts_sets.md](dicts_sets.md) for details.

---

## Strings

Strings prefixed with `u""` are lists of character atoms:

```python
u"ABC" is [A, B, C] is ['A', 'B', 'C'],
```

All list operations apply to strings. Plain string literals (without `u`) are atoms.

---

## F-strings

Python f-strings work naturally in `.clausal` files. Logic variables are auto-dereferenced at search time — bound variables interpolate their value, unbound variables show `_N`.

```python
greet(NAME) <- Writeln(f"Hello, {NAME}!"),

show_pair(X, Y) <- Writeln(f"{X} and {Y}"),

# Format specs work too
show_price(ITEM, PRICE) <- Writeln(f"{ITEM}: ${PRICE:.2f}"),
```

Under the hood, f-strings in `.clausal` files are compiled to deferred `PyThunk` lambdas during AST transformation. Logic variable names become lambda parameters; the compiler emits calls with `deref()`'d values at search time.

Simple variable references like `f"{X_}"` and `f"{NAME}"` work correctly. Format specs (`:.2f`, `:>10`, etc.) and conversions (`!r`, `!s`) are fully supported. Python expressions inside f-strings (like `f"{len(L_)}"` or `f"{S_.upper()}"`) also work — the entire f-string is wrapped in a lambda that receives dereferenced values.

---

## Python interop — `++()` escape (V2-16)

The `++()` operator evaluates an arbitrary Python expression at search time. Logic variables inside the expression are automatically dereferenced.

**As a value** (inside `is`):

```python
# Call a Python builtin
list_len(L_, N_) <- (N_ is ++len(L_)),

# Method call on a dereferenced variable
to_upper(S_, R_) <- (R_ is ++S_.upper()),

# Arithmetic
inc(X_, R_) <- (R_ is ++(X_ + 1)),

# Subscript access
first(L_, R_) <- (R_ is ++L_[0]),

# Dict access
get_key(D_, K_, R_) <- (R_ is ++D_[K_]),

# Multiple logic variables
add_len(A_, B_, R_) <- (R_ is ++(len(A_) + len(B_))),

# No logic variables (pure Python)
get_pi(R_) <- (R_ is ++(3.14159)),
```

**As a goal** (side effects):

```python
# Print as a goal
show(X_) <- ++print(X_),

# Goal followed by continuation
process(X_, R_) <- (
    ++print(X_),
    R_ is ++(X_ * 2)
),
```

Under the hood, `++expr` wraps the Python expression in a lambda whose parameters shadow the module-scope Var names. The compiler emits `thunk_fn(deref(v0), deref(v1), ...)`. Any Python expression works — method calls, builtins, arithmetic, subscripts, etc.

---

## Compound terms and goals

```python
goal(A, B),            # compound goal
A.goal(B),             # equivalent infix form (syntactic sugar)
A .goal,               # postfix form of goal(A)
not goal,              # negation as failure
```

The infix and postfix forms allow natural English-style reading of predicates that take a "subject" argument.

---

## Immediate goals

```python
+ goal,     # assert/call immediately ('+' distinguishes from a fact)
- term,     # retract term
```

---

## Module qualification

```python
module/(Terms),
```

---

## Lambdas

Lambdas are anonymous clauses — goal closures passed as arguments to higher-order predicates. They use the same `head <- body` arrow syntax as clause definitions:

```python
# One-arg lambda — X_ is a parameter, Result_ is captured
apply(Result_, Val_) <- CallGoal((X_ <- (Result_ := X_ + 1)), Val_)

# Two-arg lambda
apply_add(A_, B_, R_) <- CallGoal(((X_, Y_) <- (R_ := X_ + Y_)), A_, B_)

# Zero-arg lambda
run_goal(Result_) <- CallGoal((() <- (Result_ is 42)))

# Captured variable from enclosing clause
add_z(Z_, R_) <- CallGoal((X_ <- (R_ := X_ + Z_)), 10)

# Conjunction body — parenthesize each := subgoal
transform(R_) <- CallGoal(((X_, Y_) <- ((T_ := X_ + 1) and (Y_ := T_ * 2))), 5, R_)
```

Parameters are lambda arguments; captured variables share the enclosing clause's `Var` objects. Body-local variables (first appearing inside the lambda) get fresh `Var()` allocations. Lambdas are called via the `CallGoal/1..8` builtins (or `Call/1..8`).

See [lambdas.md](lambdas.md) for the full design, compilation details, and examples.

---

## Definite Clause Grammars — `>>` (V2-17)

DCG rules provide syntactic sugar for difference-list grammars. Each `>>` rule compiles to an ordinary `<-` clause with two extra hidden arguments (input list, remaining list) threaded through the body. This is the same approach as Prolog's `-->`, using Python's `>>` operator instead.

### Basic syntax

```python
# Terminal — consume literal tokens from the input list
greeting >> (["hello", "world"])

# Non-terminal — call another DCG rule (state threaded automatically)
sentence >> (noun_phrase, verb_phrase, noun_phrase)

# Empty terminal (epsilon — matches without consuming)
epsilon >> ([])
```

### Extra arguments and inline goals

DCG predicates can have extra arguments beyond the hidden state:

```python
# Extra arg D, plus inline goals {D >= 0} and {D <= 9}
digit(D) >> ([D], {D >= 0}, {D <= 9})
```

Inline goals are written with `{...}` (Python set literal syntax). They execute without consuming input — the state passes through unchanged. Multiple consecutive inline goals are optimised to avoid generating unnecessary intermediate state variables.

### Conjunction and disjunction

```python
# Conjunction — comma-separated tuple (primary style)
rule >> (a, b, c)

# Conjunction — 'and' also works
rule >> (a and b and c)

# Disjunction
letter >> (["a"] or ["b"] or ["c"])
```

### Negation

```python
# Negation as failure — state passes through
not_a >> (not ["a"], [X])
```

### Pushback / semicontext

The LHS can be a tuple `(head, [pushback_tokens])` to push tokens back onto the input after matching:

```python
# Peek at next token without consuming it
(look_ahead(T), [T]) >> ([T])
```

After the body matches `[T]`, the pushback `[T]` is prepended to the remainder.

### Invoking DCGs with `phrase`

Use `phrase/2` or `phrase/3` to call DCG rules from regular predicates:

```python
# phrase/2 — must consume the entire input list
valid_sentence(S) <- phrase(sentence, S)

# phrase/3 — partial parse, remaining input bound to REST
phrase(digit(D), [3, "plus", 4], REST)
```

`phrase/2` passes `[]` as the expected remainder, so the rule must consume all input. `phrase/3` leaves the remainder as a logic variable for partial parsing.

### Module exports

When using `-module(...)`, DCG predicates must be declared with their full signature including the two hidden state arguments:

```python
# Correct: PredicateMeta classes created with proper field counts
-module(my_grammar, [greeting(S0, S), digit(D, S0, S)])

# Wrong: creates string atom assignments, not predicate classes
-module(my_grammar, [greeting, digit])
```

### How it works

The `>>` rewriting is purely syntactic — it transforms DCG rules into ordinary `<-` clauses before the compiler sees them:

```python
# This DCG rule:
greeting >> (["hello", "world"])

# Rewrites to this ordinary clause:
greeting(S0, S) <- (S0 is ["hello", "world", *S])
```

```python
# This DCG rule:
digit(D) >> ([D], {D >= 0}, {D <= 9})

# Rewrites to:
digit(D, S0, S) <- (S0 is [D, *S] and D >= 0 and D <= 9)
```

No changes to the compiler, database, or runtime are needed.

### DCGs as general state-passing

DCGs are not just for parsing — they are a **general state-passing mechanism**. The difference-list pair can carry any state encoded as a single-element list `[State]`. Terminals read state, pushback writes it back, and `phrase/3` sets initial/final state. (For a good explanation of this pattern, see [Markus Triska's DCG tutorial](https://www.metalevel.at/prolog/dcg).)

#### `state/1` and `state/2` helper nonterminals

Two reusable nonterminals form the core of state-passing DCGs:

```python
# Read current state (passthrough — state is not modified)
(state(S), [S]) >> ([S])

# Read old state S0, replace with S
(state(S0, S), [S]) >> ([S0])
```

`state/1` reads the current state value into `S` without modifying it. `state/2` reads the old state into `S0` and writes `S` as the new state. Copy these into any module that needs state threading.

#### Counter example

Thread a counter through `phrase/3`:

```python
# Increment: read counter, add 1, write new counter
inc >> (state(N0), {N := N0 + 1}, state(_, N))

# Chain three increments
count3 >> (inc, inc, inc)
```

```python
# Call from Python:
phrase(count3, [0], [N])  # → N = 3
phrase(count3, [10], [N])  # → N = 13
```

#### Tree leaf counting

```python
# Trees as "leaf" or [Left, Right]
count_leaves("leaf") >> (state(N0), {N := N0 + 1}, state(_, N))
count_leaves([L, R]) >> (count_leaves(L), count_leaves(R))

# API: wrap with phrase/3
num_leaves(T, N) <- phrase(count_leaves(T), [0], [N])
```

```python
num_leaves("leaf", N)                     # → N = 1
num_leaves(["leaf", ["leaf", "leaf"]], N)  # → N = 3
```

#### Accumulator: collecting items

```python
# Push item onto accumulator state
push(X) >> (state(Acc0), {Acc is [X, *Acc0]}, state(_, Acc))

# Push all items from a list
push_all([]) >> ([])
push_all([X, *Xs]) >> (push(X), push_all(Xs))
```

```python
phrase(push_all([1, 2, 3]), [[]], Rest)  # → Rest = [[3, 2, 1]]
```

#### Key points

- **State is encoded as `[Value]`** — a single-element list. `phrase/3` sets `[InitialState]` and receives `[FinalState]`.
- **Multiple states** → use a compound value: `[state(Count, Items)]` or `[[Count, Items]]`.
- **State-only DCG** (no token parsing): use `phrase/3` where the "list" is just a state wrapper. There is no requirement that the threaded state be a token list.
- **Chaining**: DCG nonterminal calls naturally compose — `inc_then_double >> (inc, double)` threads the state through both operations sequentially.

---

## Extended DCGs — EDCGs

Standard DCGs thread a single state (the difference list). **Extended DCGs** add support for **multiple named accumulators** and **read-only passed arguments**, all threaded automatically through `>>` rules. This eliminates the boilerplate of manually encoding multiple states into a single compound value.

EDCGs are based on Peter Van Roy's 1989 design and use three directives to declare the threading:

### Declaring accumulators

An accumulator has a name and a **joiner goal** that relates a pushed value to the input/output state:

```python
# Numeric counter: Out = In + Value
-edcg_acc(counter, X_, In_, Out_, {Out_ := In_ + X_})

# List accumulator: prepend items
-edcg_acc(items, Item_, In_, Out_, {Out_ is [Item_, *In_]})

# Product accumulator: Out = In * Value
-edcg_acc(product, X_, In_, Out_, {Out_ := In_ * X_})
```

The joiner goal can be any clausal goal wrapped in `{braces}`. The variable names (`X_`, `In_`, `Out_`) are placeholders — they get substituted with actual variables during rewriting.

### Declaring passed arguments

A **passed argument** is a read-only value threaded unchanged through all sub-calls:

```python
-edcg_pass(config)
-edcg_pass(scale)
```

### Declaring predicates

Each EDCG predicate must declare its **visible arity** and which accumulators/passes it uses:

```python
-edcg_pred(inc, 0, [counter])           # 0 visible args, uses counter
-edcg_pred(process, 1, [counter, items]) # 1 visible arg, uses counter + items
-edcg_pred(parse, 0, [counter, dcg])     # uses counter + standard DCG list
-edcg_pred(scaled_inc, 0, [counter, scale])  # accumulator + passed arg
```

The special name `dcg` refers to the standard DCG difference-list accumulator. Include it when your EDCG rule also parses tokens.

### EDCG rule syntax

EDCG rules use `>>` just like standard DCGs, with additional operators:

```python
# Push a value to a named accumulator: [value] // acc_name
inc >> ([1] // counter)

# Read current accumulator value: acc_name / Var_
get_and_inc(V_) >> (counter / V_, [1] // counter)

# Read a passed argument: pass_name / Var_
scaled_inc >> (scale / S_, [S_] // counter)

# Terminal list (requires 'dcg' in the predicate's accumulator list)
token(T_) >> ([T_], [1] // counter)

# Inline goals don't thread accumulators
inc_if_positive >> (counter / N_, {N_ >= 0}, [1] // counter)

# Sub-calls: accumulators are threaded automatically
count3 >> (inc, inc, inc)

# Empty body: all accumulators pass through unchanged
noop >> ([])
```

The `//` operator pushes a value through the accumulator's joiner goal. The `/` operator reads the current state without modifying it.

### Multiple accumulators

A single rule can update multiple accumulators simultaneously:

```python
-edcg_acc(counter, X_, In_, Out_, {Out_ := In_ + X_})
-edcg_acc(items, Item_, In_, Out_, {Out_ is [Item_, *In_]})
-edcg_pred(process, 1, [counter, items])

# Each push targets a specific accumulator by name
process(X_) >> ([1] // counter, [X_] // items)
```

When a sub-call uses fewer accumulators than the caller, only the shared ones are threaded:

```python
-edcg_pred(inc_only, 0, [counter])          # only counter
-edcg_pred(do_both, 1, [counter, items])    # counter + items

inc_only >> ([1] // counter)
do_both(X_) >> (inc_only, [X_] // items)    # inc_only threads counter only
```

### Calling EDCG predicates

EDCG predicates are compiled to ordinary predicates with hidden arguments appended in declaration order: 2 per accumulator (in, out) + 1 per pass. You can call them from regular `<-` clauses using keyword syntax:

```python
# -edcg_pred(count_elems, 1, [len])
# Compiled arity: 1 (visible) + 2 (len_in, len_out) = 3
my_length(L_, N_) <- count_elems(L_, _edcg_len_in_=0, _edcg_len_out_=N_)
```

Or positionally — hidden args follow visible args in the order declared:

```python
# count_elems(List, len_in, len_out)
my_length(L_, N_) <- count_elems(L_, 0, N_)
```

### Complete example: counter with scale factor

```python
-module(example, [run_scaled(List_, Scale_, Count_, Items_)])

-edcg_acc(counter, X_, In_, Out_, {Out_ := In_ + X_})
-edcg_acc(items, Item_, In_, Out_, {Out_ is [Item_, *In_]})
-edcg_pass(scale)

-edcg_pred(scaled_inc, 0, [counter, scale])
-edcg_pred(collect_and_count, 1, [counter, items, scale])
-edcg_pred(process_list, 1, [counter, items, scale])

scaled_inc >> (scale / S_, [S_] // counter)
collect_and_count(X_) >> (scaled_inc, [X_] // items)

process_list([]) >> ([])
process_list([X_, *Xs_]) >> (collect_and_count(X_), process_list(Xs_))

run_scaled(List_, Scale_, Count_, Items_) <- (
    process_list(List_, _edcg_counter_in_=0, _edcg_counter_out_=Count_,
                 _edcg_items_in_=[], _edcg_items_out_=Items_,
                 _edcg_scale_=Scale_)
)
```

### Design notes

- **Purely syntactic**: EDCG `>>` rules are rewritten to ordinary `<-` clauses before compilation. No runtime support needed.
- **Backward compatible**: Rules without `-edcg_pred` declarations continue to use standard DCG rewriting.
- **`//` for push, `/` for read**: These use Python's floor-division and division operators respectively.
- **Accumulator order matters**: Hidden args are appended in the order listed in `-edcg_pred`. When calling from `<-` clauses, match this order.

---

## Meta-predicates

Meta-predicates are higher-order predicates that take goals as arguments. They are compiled as special forms — the goal argument is compiled inline, not passed as a runtime value.

### All-solutions predicates

```python
# Collect all X where In(X, [1,2,3]) into Bag
FindAll(X_, In(X_, [1, 2, 3]), Bag_),

# Same but with a filter — only X > 1
FindAll(X_, (In(X_, [1, 2, 3]) and X_ > 1), Bag_),

# Cartesian product — template can be any term
FindAll([X_, Y_], (In(X_, [a, b]) and In(Y_, [1, 2])), Bag_),

# BagOf fails if no solutions (FindAll succeeds with [])
BagOf(X_, In(X_, List_), Bag_),

# SetOf deduplicates results (preserving first-occurrence order)
SetOf(X_, In(X_, [1, 1, 2, 2, 3]), Bag_),   # Bag_ = [1, 2, 3]
```

| Predicate | Empty result |
|---|---|
| `FindAll/3` | Succeeds with `Bag = []` |
| `BagOf/3` | Fails |
| `SetOf/3` | Fails |

### Universal quantification

```python
# Succeeds iff Action holds for every solution of Cond
ForAll(In(X_, [2, 4, 6]), X_ > 0),   # succeeds
ForAll(In(X_, [2, -1, 6]), X_ > 0),  # fails
```

`ForAll(Cond, Action)` is equivalent to `not (Cond and not Action)`.

### Call/N

`Call/N` invokes a goal closure with extra arguments. It is an alias for `CallGoal/N`:

```python
CallGoal((X_ <- (X_ > 0)), 5),        # CallGoal/2: succeeds
Call(Goal_, Arg1_, Arg2_),             # Call/3: invoke Goal_ with two extra args
```

`Call/1` through `Call/8` are available (as are `CallGoal/1` through `CallGoal/8`).

### Higher-order list predicates (V2-11)

These predicates take a goal closure and apply it across a list. All use committed choice (first solution per element).

```python
# MapList/2 — check Goal(Elem) succeeds for every element
MapList((X_ <- (X_ > 0)), [1, 2, 3]),              # succeeds

# MapList/3 — map Goal(X, Y) over list, collect results
MapList(((X_, Y_) <- (Y_ := X_ * 2)), [1, 2, 3], Ys_),  # Ys_ = [2, 4, 6]

# Filter/3 — keep elements where Goal(Elem) succeeds
Filter((X_ <- (X_ > 0)), [1, -2, 3, -4], R_),      # R_ = [1, 3]

# Exclude/3 — keep elements where Goal(Elem) fails
Exclude((X_ <- (X_ > 0)), [1, -2, 3, -4], R_),     # R_ = [-2, -4]

# FoldLeft/4 — left fold with Goal(Elem, Acc0, Acc1)
FoldLeft(((E_, A_, R_) <- (R_ := A_ + E_)), [1, 2, 3], 0, Sum_),  # Sum_ = 6
```

---

## Constraint logic programming

Arithmetic operators inside a constraint domain imply constraints, not evaluation. The domain is applied using the `--` escape:

```python
(--clpz)(
    X < 43,
    42 <= X,
)
```

Shorthand constraint operators (usable in single goals):

| Operator | Meaning |
|---|---|
| `==+`, `!=+`, `>+`, `<+`, `>=+`, `<=+` | numeric comparison |
| `==~`, `!=~`, `>~`, `<~`, `>=~`, `<=~` | standard order of terms |

Note: `<=` always means less-than-or-equal in constraint context. Implication uses `implies` or the `<-` arrow.

---

## Why not allow free intermingling of Python and logic namespaces?

Three main reasons:

1. **Ambiguity.** It is impossible at compile time to distinguish a Python global from an atom without tracking all imports. Old compiled code could silently become wrong when a new name is imported. With explicit `--` escaping, the boundary is always visible.

2. **Term representation efficiency.** Compound terms are most efficiently represented as instances of generated classes (enabling `match`/`case` to work directly on them). Atoms need to be class objects for structural matching. Allowing arbitrary Python objects as functors requires a boxing wrapper, which is heavier.

3. **Logic variables must be visually distinct.** They are declared implicitly, work differently from Python names, and their bindings are reverted on backtracking. A clear syntactic marker (ALL-CAPS or trailing underscore) avoids confusion without requiring explicit `declare` statements.

The escape mechanisms (`--`, `++`) cover all cases where interop is genuinely needed. Explicit is better than implicit.

---

## Python functions as predicates

Any Python function that contains logical terms is treated as a predicate. Python code within the body becomes embedded and backtrackable. An implicit `backtracking` flag allows cleanup on backtrack:

```python
def head(ARG1, ARG2):
    goal(...),
    if not backtracking:
        # forward path: acquire resource, open file, etc.
        ...
    else:
        # backtrack path: release resource, etc.
        ...
    another_goal(...)
```

This gives a symmetric and concise way to integrate Python side effects with Prolog-style backtracking. The programmer takes responsibility for correctness.

---

## Syntax cheat sheet

```python
# Variables (ALL-CAPS preferred; trailing-underscore also valid)
X, HEAD, REST          # ALL-CAPS logic variables
X_, head_, rest_       # trailing-underscore style (also valid)
_                      # anonymous variable (always unifies, stores nothing)

# Atoms
Atom, 'an atom', '+'   # atoms (titlecase or quoted string)
--python_obj           # any Python object used as an atom

# Lists
[]                     # empty list
[a, 1, X]              # simple list
[FIRST, *REST]         # head/tail

# Strings
u"hello"               # list of character atoms

# Dicts (DictTerm — keys ground, values may be Vars)
{"x": 1, "y": 2}              # ground dict
{"x": X, "y": Y_}             # dict with variable values
{"addr": {"city": C}}         # nested dict

# Sets (SetTerm — elements must be ground)
{1, 2, 3}                     # set of integers
{"red", "green", "blue"}      # set of strings

# Unification
X is Y,                # unify
X is not Y,            # dif constraint (must stay different)
not (X is Y),          # immediate check (don't unify right now)

# Arithmetic
(N := X + 1),          # evaluate RHS, unify with LHS

# CLP(FD) constraints (V2-6)
X == Y,                # arithmetic equality constraint
X != Y,                # arithmetic disequality constraint
X < Y,                 # less-than constraint
X <= Y,                # less-or-equal constraint
InDomain(X, 1, 10),    # post finite domain
AllDifferent([X,Y,Z]), # pairwise disequality
Label([X, Y, Z]),      # enumerate solutions (first-fail)
Equivalent(X, Y),      # structural equality (old == behavior)

# Rules and facts
Head <- call(X),       # single-call body (no parens needed)
Head <- (Body),        # operator body (parens required)
Fact,                  # fact (trivially true)
Rule > ListDescription,    # DCG rule

# Goals
goal(A, B),            # compound goal
A.goal(B),             # infix sugar
not goal,              # negation as failure
+ goal,                # immediate goal
- term,                # retract

# Module qualification
module/(Terms),

# Escaping
--python_expr          # Python inside logic term
++logic_term           # logic term inside Python expression
~~python_expr          # capture as AST node

# Constraint domains
(--clpz)(X > 0, X < 10),

# Lambdas (anonymous clauses)
CallGoal((X_ <- (R_ := X_ + 1)), 5)                             # R_ = 6
CallGoal(((X_, Y_) <- (R_ := X_ + Y_)), A_, B_)                 # multi-param

# Meta-predicates (V2-10)
FindAll(X_, In(X_, [1,2,3]), Bag_),          # Bag_ = [1,2,3]
BagOf(X_, In(X_, List_), Bag_),              # fails if List_ empty
SetOf(X_, In(X_, Xs_), Bag_),               # deduplicates
ForAll(In(X_, Ns_), X_ > 0),               # universal quantification
Call(Goal_, Arg1_),                          # Call/2 (alias for CallGoal/2)

# F-strings (V2-15) — logic variables auto-deref at search time
Writeln(f"Hello, {NAME}!"),            # prints bound value of NAME
Writeln(f"{X:.2f}"),                   # format specs work
S_ := f"{X} and {Y}",                 # capture as string

# DCGs (V2-17) — >> defines grammar rules with difference lists
greeting >> (["hello", "world"]),          # terminal sequence
sentence >> (noun_phrase, verb_phrase),    # non-terminal chain
digit(D) >> ([D], {D >= 0}, {D <= 9}),    # args + inline goals
letter >> (["a"] or ["b"] or ["c"]),      # disjunction
not_a >> (not ["a"], [X]),                # negation
(peek(T), [T]) >> ([T]),                  # pushback/semicontext
phrase(greeting, ["hello", "world"]),     # phrase/2 — must consume all
phrase(digit(D), [3], REST),              # phrase/3 — partial parse

# EDCGs — extended DCGs with named accumulators
-edcg_acc(counter, X_, In_, Out_, {Out_ := In_ + X_})  # declare accumulator
-edcg_pass(config)                                       # declare passed arg
-edcg_pred(inc, 0, [counter])                            # declare pred's hidden args
inc >> ([1] // counter)                   # [value] // acc — push to accumulator
get(V_) >> (counter / V_)                 # acc / Var — read current value
scaled >> (scale / S_, [S_] // counter)   # pass / Var — read passed arg

# Python interop (V2-16) — ++() evaluates Python at search time
N_ is ++len(L_),                       # call Python builtin
R_ is ++S_.upper(),                    # method call on deref'd var
R_ is ++(X_ + 1),                      # Python arithmetic
R_ is ++L_[0],                         # subscript access
R_ is ++D_[K_],                        # dict access
++print(X_),                           # side-effect goal

# Higher-order list predicates (V2-11)
MapList(Goal_, [1, 2, 3]),                   # check Goal_ on each element
MapList(Goal_, Xs_, Ys_),                    # map Goal_(X, Y) over list
Filter(Goal_, List_, Kept_),                 # keep where Goal_ succeeds
Exclude(Goal_, List_, Removed_),             # keep where Goal_ fails
FoldLeft(Goal_, List_, Acc0_, Result_),      # left fold with Goal_(Elem, Acc, Next)
GetItem(Index_, List_, Elem_),               # 0-based index access
InCheck(Elem_, List_),                       # deterministic membership check
Unpack(Term_, List_),                        # decompose/construct term
```
