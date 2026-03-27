# Clausal — Syntax Design

Clausal uses Python's parser, and so it conforms to Python's grammar. Like Prolog, it describes Horn Clauses - simple constructs that facilitate the representation of facts and rules, backed by strong mathematical formalisms, to facilitate high-level reasoning with useful guarantees.

Clausal uses 'grammatical holes' which are and must remain syntactically valid, but have no semantic purpose in Python, and are therefore never used in practice. Clausal uses a very small set of these 'holes' to allow the free mixing of logic code with Python code. Python and logic programming code in the same file means better code cohesion, easing development.

> **Quick navigation:** [Variables](#logic-variables) · [Escape operators](#escape-operators) · [Unification](#unification) · [Clauses](#horn-clauses) · [Lists](#lists) · [Arithmetic](#arithmetic-binding) · [Constraints](#comparison-operators-clpℤ) · [DCGs](#definite-clause-grammars--) · [Lambdas](#lambdas) · [Meta-predicates](#meta-predicates) · [Cheatsheet](#syntax-cheat-sheet)

---

## Trailing comma rule

**Expression statements ending in `,` are interpreted as logical terms (facts or goals).**

in_ standard Python, an expression statement that ends in a comma produces a tuple which is then discarded. So this is never used despite being valid (a grammatical hole). It also means these logic terms are easy to cut, copy, paste, and indent — unlike Prolog, they don't require `.` terminators.

---

## Escape operators

Three double-prefix operators demarcate the boundary between Python and logic code. They must not be split with spaces (e.g. `- -` would be parsed as double negation).

| Operator | Meaning |
|---|---|
| `--expr` | Python expression embedded inside a logic term |
| `++expr` | in_ Python context: logic term inside a Python expression. in_ `.clausal` context: evaluate Python expression at search time |
| `~~expr` | Capture expression as a `simple_ast` AST node (works anywhere) |

`--` was chosen because:
- it doesn't introduce a new keyword or clobber any identifier
- double negation is rare in Python code (and if you really want it, type it as '- -x')
- it is visually prominent and quick to type

Example:
```clausal
# skip
# Logic term containing a Python value:
point(--x_coord, --y_coord),

# Python expression containing a logic term:
my_term = ++foo(X, bar(Y))

# Capture Python code as AST without running it:
ast_node = ~~(x + y * z)
```

---

## Logic variables

Two conventions are recognised:

**Leading single underscore** — any identifier whose first character is `_`, excluding dunders (`__`) and the bare anonymous variable `_`:

```python
_x, _head, _rest   # logic variables (leading-underscore style)
```

**ALL_CAPS** — any identifier where every cased character is uppercase and there is at least one cased character (underscores and digits are allowed inside):

```python
X, HEAD, REST, N1, MAX_OF   # logic variables (ALL-CAPS style)
```

Both styles may be used in the same file. ALL_CAPS is the preferred style for new code; leading-underscore is available when a lowercase variable name is desired.

A single `_` is the anonymous variable — it never stores a value, and unification against it always succeeds (matching Python's and Prolog's existing convention).

Logic variables are not declared; they come into existence by appearing in logical context. They work differently from Python variables: they can be unbound, and their bindings are undone on backtracking. This difference warrants a clear visual marker.

This is a deliberate departure from Prolog, where variables start with an uppercase letter (`Foo`, `Bar`). in_ Python, titlecase names are conventionally class names — and Clausal uses them for predicates and functors (e.g. `findall`, `in_`, `length`). Using titlecase for both variables and predicates would create ambiguity: is `Foo(Bar)` calling predicate `Foo` with atom `Bar`, or with variable `Bar`? ALL-CAPS resolves this cleanly — `findall(X, in_(X, LIST), BAG)` is unambiguous.

Why ALL-CAPS works well:
- Python programmers already associate titlecase with class names — static, global, noun-like. This is actually close to how atoms and predicates behave, not variables.
- ALL-CAPS is used in many languages for constants and distinguished names; here it marks the variable role in the logic sense.
- Single letters like `X`, `Y`, `N` are universally understood as logic variables from mathematics.
- Leading underscore (`_x`) aligns with ISO Prolog's `_Var` convention, making translation between Clausal and Prolog more natural. See [Prolog Translation](prolog_translation.md) for the full variable naming mapping.

---

## Atoms

Inside a logical term:
- identifiers in `TitleCase` or `lowercase` that are not logic variable names are atoms

```clausal
# skip
# These are atoms:
color(red),
status(active),
greeting("hello world"),
```

Atoms that conflict with Python keywords or builtins are written as strings: `'not'`, `'is'`, `'max'`.

---

## Builtin predicate naming

All built-in predicates use **PascalCase** (e.g. `findall`, `in_`, `assertz`, `var`). This is a deliberate design choice — not aesthetic — with two goals:

1. **Avoid Python keyword conflicts.** Many natural predicate names are Python reserved words: `not`, `in`, `is`, `and`, `or`, `if`, `for`, `assert`, `lambda`, `global`, `return`, `yield`. A Prolog-style lowercase predicate named `in` or `not` would be a syntax error the moment it appears as a function call in a clause body.

2. **Avoid Python builtin conflicts.** Names like `abs`, `all`, `any`, `callable`, `filter`, `float`, `int`, `map`, `max`, `min`, `set`, `str`, `sum`, `var` are Python builtins that shadow (or would shadow) predicates if used lowercase.

PascalCase keeps the builtin namespace cleanly separate from both Python keywords and user-defined (lowercase) predicates. User predicates are written in `lowercase` or `snake_case` as usual; they never conflict with builtins.

---

## Unification

Unification is written with `is`:

```clausal
# skip
X is 42,
X is Y,
X is not Y,   # disequality constraint (dif/2)
```

Why `is` rather than `=`?
- `=` is Python's assignment operator and cannot appear in expressions
- `is` expresses the same concept in English — two things being the same — and Python programmers understand it. Clausal generalises this concept; in 'X is Y', if we don't know X or Y, we are describing that they must be same whatever they are, and when either become known, they both become known.

Conversely, `X is not Y` posts a disequality constraint (`dif/2`): X and Y must end up with different values. This is lazily checked — the constraint is re-evaluated each time either variable gets bound. If they become equal, the constraint fails and the search backtracks. If they remain different, the constraint is satisfied and dropped. See [constraints.md](constraints.md) for details.

`not (X is Y)` is the immediate check (Prolog `\=/2`): it fails if X and Y *can* unify right now, regardless of future bindings. Use this when you want point-in-time semantics.

The corresponding AST node is `Unify(left, right)`. Disequality is `DoesNotUnify(left, right)`.

---

## Arithmetic binding

To constrain a variable to an arithmetic expression, use `==`:

```clausal
fib(N, RESULT) <- (
    N > 1,
    N1 == N - 1,
    N2 == N - 2,
    fib(N1, A),
    fib(N2, B),
    RESULT == A + B
)
```

`N1 == N - 1` posts an arithmetic constraint relating `N1` and `N`. Unlike Prolog's `is/2`, this works in all directions — even when `N` is unbound. No extra parentheses are needed: clause bodies are already inside `(...)`. This allows sophisticated reasoning about numbers, using the builtin constraint logic programmming (CLP) modules.

The distinction from `is`:
- `X is Y` — pure structural unification; neither side is evaluated arithmetically
- `(X == expr)` — posts an arithmetic constraint (CLP(ℤ) or CLP(ℝ))
- `(X := expr)` — eager arithmetic evaluation; evaluates `expr` as an arithmetic expression and binds the result to `X` (Prolog's `is/2`)

---

## Comparison operators (CLP(ℤ))

The comparison operators `==`, `!=`, `<`, `>`, `<=`, `>=` are CLP(ℤ) (Constraint Logic Programming over Integers) operators. They post constraints on integer variables rather than performing immediate checks.

```clausal
bounded(X) <- (
    in_domain(X, 1, 10),
    X > 3,
    X < 8,
    label([X])
)
```

when both sides are ground (no unbound Vars), the operators fall back to direct Python comparison — `3 == 3` is True, `3 < 2` is False — so existing ground arithmetic code works unchanged.

when at least one side is an unbound Var, a CLP(ℤ) constraint is posted:
- `X == 5` narrows X's domain to `{5}` (and binds it)
- `1 <= X` and `X <= 10` constrain X's domain to `[1, 10]`
- `X != 3` removes 3 from X's domain
- `X < Y` narrows X's upper bound and Y's lower bound

| Operator | CLP(ℤ) meaning |
|---|---|
| `==` | Arithmetic equality constraint |
| `!=` | Arithmetic disequality constraint |
| `<` `>` `<=` `>=` | Comparison constraints (narrow domain bounds) |

`==` and `!=` post CLP(ℤ) arithmetic constraints (Prolog `=:=/2` and `=\=/2`). For true structural equality (Prolog `==/2`) — comparing deref'd terms without binding or evaluating — use the builtin `equivalent(X, Y)`, or `not equivalent(X, Y)` for inequality.

See [constraints.md](constraints.md) for the full CLP(ℤ) design, including domain representation, propagation, and labeling.

---

## Horn clauses

```clausal
# skip
Head <- Body,
```

The `<-` operator denotes a Horn clause (rule). It will never be added to Python's expression grammar because it conflicts with `x < -y` (less-than applied to a negated value) — but only when there is no surrounding whitespace. With whitespace, it is unambiguous and parseable.

### Body style

The body after `<-` must be one of:

- **A single call** — no parentheses needed:
  ```clausal
# skip
  sorted_asc([_]),
  palindrome(XS) <- reverse(XS, XS)
  ```

- **A bare name** — no parentheses needed:
  ```clausal
# skip
  always_true <- True,
  ```

- **Anything else** — parenthesized:
  ```clausal
# skip
  safe_max(X, Y, X) <- (X >= Y)
  fib(N, RESULT) <- (
      N > 1,
      N1 == N - 1,
      N2 == N - 2,
      fib(N1, A),
      fib(N2, B),
      RESULT == A + B
  )
  ```

This rule exists because Python's parser sees `<-` as `<` followed by unary `-`. when the body contains operators (`+`, `<`, `and`, `or`, `not`, etc.), the `-` gets absorbed into the body expression and the AST is silently mangled. Parentheses force Python to treat the body as a single grouped expression, keeping the `-` at the top where the term rewriter can find it. Calls and bare names are safe without parentheses because they bind tighter than unary `-`.

To keep things safe, attempting to write an unparenthesized operator body produces a clear error:

```clausal
# skip
SyntaxError: clause body must be parenthesized or a single call:
    write  head <- (body)  or  head <- goal(X)
```

### Conjunction style

Multiple goals in a body are separated by commas, with each goal on its own line:

```clausal
is_permutation(XS, YS) <- (
    length(XS, N),
    length(YS, N),
    sort(XS, S),
    sort(YS, S)
)
```

This looks a bit like a Python function def doesn't it? But it is actually much more powerful. These clauses describe a relation. This can go in multiple directions, and this generality is fundamental to the power of logic programming.

As usual in programming, be careful about operator precedence: Inside sub-expressions like `not (...)` or `... or ...`, use `and` instead of commas — commas inside these would be parsed as Python tuples:

```clausal
test("fails") <- (not (X is 1 and X is 2))
test("either") <- (X is 1 or X is 2)
```

What if we just want to state a fact that always holds? We could do so by using a body that is always true, i.e. `True`.

```clausal
parent(tom, bob) <- True
```

But there is a shorthand for this. Facts (trivially true rules) are simply written without a body, only a trailing comma:

```clausal
parent(tom, bob),
parent(bob, ann),
```

Grammar rules (Definite Clause Grammars):

```clausal
# skip
Rule >> ListDescription,
```

---

## Lists

```clausal
# skip
[]               # empty list (singleton)
[a, 1, X]        # a simple list
[FIRST, *REST]   # head/tail decomposition
[*BEFORE, PIVOT, *AFTER]  # multiple spread patterns
```

Partial lists (Prolog `[H|T]` where `T` is a variable) use Python's `*` spread syntax rather than `|`. The empty list is a singleton — unlike Python, two `[]` literals are the same object.

---

## Dicts

Python dict literals in `.clausal` files create `DictTerm` objects — unification-aware dictionaries. Keys must be ground; values may be logic variables.

```clausal
# Ground dict fact
point({"x": 0, "y": 0}),

# Dict pattern in head — X binds during unification
get_x({"x": X, "y": Y}, X),

# Dict construction in body
make_point(X, Y, P) <- (P is {"x": X, "y": Y})

# Nested dicts
get_city({"address": {"city": C}}, C),
```

Two dicts unify iff they have the same keys and values unify pairwise. A variable unifies with a dict by binding to it.

See [Dicts & Sets](dicts_sets.md) for the full design.

---

## Sets

Python set literals in `.clausal` files create `SetTerm` objects — unification-aware sets. Elements must be ground (hashable).

```clausal
colors({1, 2, 3}),
primary({"red", "green", "blue"}),
```

Two sets unify iff they contain the same elements (order irrelevant). Variables in set elements are not supported.

See [Dicts & Sets](dicts_sets.md) for details.

---

## Strings

Strings prefixed with `u""` are [lists of character atoms](strings_as_lists.md):

```clausal
# skip
u"ABC" is [A, B, C] is ['A', 'B', 'C'],
```

All list operations apply to strings. Plain string literals (without `u`) are atoms.

---

## F-strings

Python f-strings work naturally in `.clausal` files. Logic variables are auto-dereferenced at search time — bound variables interpolate their value, unbound variables show `_N`.

```clausal
greet(NAME) <- writeln(f"Hello, {NAME}!")

show_pair(X, Y) <- writeln(f"{X} and {Y}")

# Format specs work too
show_price(ITEM, PRICE) <- writeln(f"{ITEM}: ${PRICE:.2f}")
```

Under the hood, f-strings in `.clausal` files are compiled to deferred `PyThunk` lambdas during AST transformation. Logic variable names become lambda parameters; the compiler emits calls with `deref()`'d values at search time.

Simple variable references like `f"{X}"` and `f"{NAME}"` work correctly. Format specs (`:.2f`, `:>10`, etc.) and conversions (`!r`, `!s`) are fully supported. Python expressions inside f-strings (like `f"{len(L)}"` or `f"{S.upper()}"`) also work — the entire f-string is wrapped in a lambda that receives dereferenced values.

---

## [Python interop](python_integration.md) — `++()` escape

The `++()` operator evaluates an arbitrary Python expression at search time. Logic variables inside the expression are automatically dereferenced.

**As a value** (inside `is`):

```clausal
# Call a Python builtin
list_len(L, N) <- (N is ++len(L))

# Method call on a dereferenced variable
to_upper(S, R) <- (R is ++S.upper())

# Arithmetic
inc(X, R) <- (R is ++(X + 1))

# Subscript access
first(L, R) <- (R is ++L[0])

# Dict access
get_key(D, K, R) <- (R is ++D[K])

# Multiple logic variables
add_len(A, B, R) <- (R is ++(len(A) + len(B)))

# No logic variables (pure Python)
get_pi(R) <- (R is ++(3.14159))
```

**As a goal** (side effects):

```clausal
# Print as a goal
show(X) <- ++print(X)

# Goal followed by continuation
process(X, R) <- (
    ++print(X),
    R is ++(X * 2)
)
```

Under the hood, `++expr` wraps the Python expression in a lambda whose parameters shadow the module-scope Var names. The compiler emits `thunk_fn(deref(v0), deref(v1), ...)`. Any Python expression works — method calls, builtins, arithmetic, subscripts, etc.

### Unit-literal sugar — `n(Unit)`

A special case of the `++()` pattern: when a numeric literal is used as the
callable with a single unit-predicate argument, it desugars to `++(Unit(n))`:

```clausal
# skip
5(Metre)          # → ++(Metre(5))    → Quantity(5, {Metre: 1})
9.8(Newton)       # → ++(Newton(9.8)) → Quantity(9.8, {kg:1, m:1, s:-2})
-3(Second)        # → Quantity(-3, {Second: 1})  (negation applied after)
```

when a **logic variable** is used as the callable instead, `X(Unit)` becomes a
goal that posts a dimension constraint on `X`:

```clausal
# skip
F(Newton)         # → has_units(F, Newton) — F must be bound to a Newton value
F is 9.8(Newton)  # binds F; hook checks dims match
```

See [Units](units.md) for the full reference.

---

## Compound terms and goals

```clausal
goal(A, B),            # compound goal
not goal,              # negation as failure
```

---

## Immediate goals *(planned)*

> **Note:** This syntax is not yet implemented. Use the `assertz(goal)` and `retract(term)` builtins directly.

```clausal
# skip
+ goal,     # assert/call immediately ('+' distinguishes from a fact)
- term,     # retract term
```

---

## Module qualification

Predicates from imported modules are called with dotted notation after loading the module:

```clausal
# skip
utils.Double(X, Y),    # qualified call after -import_module(utils)
```

See [Directives](directives.md) and [Import System](import.md) for details.

---

## Lambdas

Lambdas are anonymous clauses — goal closures passed as arguments to higher-order predicates. They use the same `head <- body` arrow syntax as clause definitions:

```clausal
# One-arg lambda — X is a parameter, RESULT is captured
apply(RESULT, VAL) <- call_goal((X <- (RESULT == X + 1)), VAL)

# Two-arg lambda
apply_add(A, B, R) <- call_goal(((X, Y) <- (R == X + Y)), A, B)

# Zero-arg lambda
run_goal(RESULT) <- call_goal((() <- (RESULT is 42)))

# Captured variable from enclosing clause
add_z(Z, R) <- call_goal((X <- (R == X + Z)), 10)

# Conjunction body
transform(R) <- call_goal(((X, Y) <- (T == X + 1, Y == T * 2)), 5, R)
```

Parameters are lambda arguments; captured variables share the enclosing clause's `Var` objects. Body-local variables (first appearing inside the lambda) get fresh `Var()` allocations. Lambdas are called via the `call_goal/1..8` builtins (or `call/1..8`).

See [Lambdas](lambdas.md) for the full design, compilation details, and examples.

---

## Definite Clause Grammars — `>>`

DCG rules provide syntactic sugar for difference-list grammars. Each `>>` rule compiles to an ordinary `<-` clause with two extra hidden arguments (input list, remaining list) threaded through the body. This is the same approach as Prolog's `-->`, using Python's `>>` operator instead.

### Basic syntax

```clausal
# Terminal — consume literal tokens from the input list
greeting >> (["hello", "world"])

# Non-terminal — call another DCG rule (state threaded automatically)
sentence >> (noun_phrase, verb_phrase, noun_phrase)

# Empty terminal (epsilon — matches without consuming)
epsilon >> ([])
```

### Extra arguments and inline goals

DCG predicates can have extra arguments beyond the hidden state:

```clausal
# Extra arg D, plus inline goals {D >= 0} and {D <= 9}
digit(D) >> ([D], {D >= 0}, {D <= 9})
```

Inline goals are written with `{...}` (Python set literal syntax). They execute without consuming input — the state passes through unchanged. Multiple consecutive inline goals are optimised to avoid generating unnecessary intermediate state variables.

### Conjunction and disjunction

```clausal
# Conjunction — comma-separated (canonical style)
rule >> (a, b, c)

# Disjunction
letter >> (["a"] or ["b"] or ["c"])
```

### Negation

```clausal
# Negation as failure — state passes through
not_a >> (not ["a"], [X])
```

### Pushback / semicontext

The LHS can be a tuple `(head, [pushback_tokens])` to push tokens back onto the input after matching:

```clausal
# Peek at next token without consuming it
(look_ahead(T), [T]) >> ([T])
```

After the body matches `[T]`, the pushback `[T]` is prepended to the remainder.

### Invoking DCGs with `phrase`

Use `phrase/2` or `phrase/3` to call DCG rules from regular predicates:

```clausal
# skip
# phrase/2 — must consume the entire input list
valid_sentence(S) <- phrase(sentence, S)

# phrase/3 — partial parse, remaining input bound to REST
phrase(digit(D), [3, "plus", 4], REST)
```

`phrase/2` passes `[]` as the expected remainder, so the rule must consume all input. `phrase/3` leaves the remainder as a logic variable for partial parsing.

### Module exports

when using `-module(...)`, DCG predicates must be declared with their full signature including the two hidden state arguments:

```clausal
# Correct: PredicateMeta classes created with proper field counts
-module(my_grammar, [greeting(S0, S), digit(D, S0, S)])

# Wrong: creates string atom assignments, not predicate classes
-module(my_grammar, [greeting, digit])
```

### How it works

The `>>` rewriting is purely syntactic — it transforms DCG rules into ordinary `<-` clauses before the compiler sees them:

```clausal
# This DCG rule:
greeting >> (["hello", "world"])

# Rewrites to this ordinary clause:
greeting(S0, S) <- (S0 is ["hello", "world", *S])
```

```clausal
# This DCG rule:
digit(D) >> ([D], {D >= 0}, {D <= 9})

# Rewrites to:
digit(D, S0, S) <- (S0 is [D, *S], D >= 0, D <= 9)
```

No changes to the compiler, database, or runtime are needed.

### DCGs as general state-passing

DCGs are not just for parsing — they are a **general state-passing mechanism**. The difference-list pair can carry any state encoded as a single-element list `[State]`. Terminals read state, pushback writes it back, and `phrase/3` sets initial/final state. (For a good explanation of this pattern, see [Markus Triska's DCG tutorial](https://www.metalevel.at/prolog/dcg).)

#### `state/1` and `state/2` helper nonterminals

Two reusable nonterminals form the core of state-passing DCGs:

```clausal
# skip
# Read current state (passthrough — state is not modified)
(state(S), [S]) >> ([S])

# Read old state S0, replace with S
(state(S0, S), [S]) >> ([S0])
```

`state/1` reads the current state value into `S` without modifying it. `state/2` reads the old state into `S0` and writes `S` as the new state. Copy these into any module that needs state threading.

#### Counter example

Thread a counter through `phrase/3`:

```clausal
# Increment: read counter, add 1, write new counter
inc >> (state(N0), {N == N0 + 1}, state(_, N))

# Chain three increments
count3 >> (inc, inc, inc)
```

```python
# Call from Python:
phrase(count3, [0], [N])  # → N = 3
phrase(count3, [10], [N])  # → N = 13
```

#### Tree leaf counting

```clausal
# Trees as "leaf" or [Left, Right]
count_leaves("leaf") >> (state(N0), {N == N0 + 1}, state(_, N))
count_leaves([L, R]) >> (count_leaves(L), count_leaves(R))

# API: wrap with phrase/3
num_leaves(T, N) <- phrase(count_leaves(T), [0], [N])
```

```python
num_leaves("leaf", N)                     # → N = 1
num_leaves(["leaf", ["leaf", "leaf"]], N)  # → N = 3
```

#### Accumulator: collecting items

```clausal
# Push item onto accumulator state
push(X) >> (state(ACC0), {ACC is [X, *ACC0]}, state(_, ACC))

# Push all items from a list
push_all([]) >> ([])
push_all([X, *XS]) >> (push(X), push_all(XS))
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

```clausal
# Numeric counter: Out = in_ + Value
-edcg_acc(counter, X, IN, OUT, {OUT == IN + X})

# List accumulator: prepend items
-edcg_acc(items, ITEM, IN, OUT, {OUT is [ITEM, *IN]})

# Product accumulator: Out = in_ * Value
-edcg_acc(product, X, IN, OUT, {OUT == IN * X})
```

The joiner goal can be any clausal goal wrapped in `{braces}`. The variable names (`X`, `IN`, `OUT`) are placeholders — they get substituted with actual variables during rewriting.

### Declaring passed arguments

A **passed argument** is a read-only value threaded unchanged through all sub-calls:

```clausal
-edcg_pass(config)
-edcg_pass(scale)
```

### Declaring predicates

Each EDCG predicate must declare its **visible arity** and which accumulators/passes it uses:

```clausal
# skip
-edcg_pred(inc, 0, [counter])           # 0 visible args, uses counter
-edcg_pred(process, 1, [counter, items]) # 1 visible arg, uses counter + items
-edcg_pred(parse, 0, [counter, dcg])     # uses counter + standard DCG list
-edcg_pred(scaled_inc, 0, [counter, scale])  # accumulator + passed arg
```

The special name `dcg` refers to the standard DCG difference-list accumulator. Include it when your EDCG rule also parses tokens.

### EDCG rule syntax

EDCG rules use `>>` just like standard DCGs, with additional operators:

```clausal
# skip
# Push a value to a named accumulator: [value] // acc_name
inc >> ([1] // counter)

# Read current accumulator value: acc_name / Var
get_and_inc(V) >> (counter / V, [1] // counter)

# Read a passed argument: pass_name / Var
scaled_inc >> (scale / S, [S] // counter)

# Terminal list (requires 'dcg' in the predicate's accumulator list)
token(T) >> ([T], [1] // counter)

# Inline goals don't thread accumulators
inc_if_positive >> (counter / N, {N >= 0}, [1] // counter)

# Sub-calls: accumulators are threaded automatically
count3 >> (inc, inc, inc)

# Empty body: all accumulators pass through unchanged
noop >> ([])
```

The `//` operator pushes a value through the accumulator's joiner goal. The `/` operator reads the current state without modifying it.

### Multiple accumulators

A single rule can update multiple accumulators simultaneously:

```clausal
-edcg_acc(counter, X, IN, OUT, {OUT == IN + X})
-edcg_acc(items, ITEM, IN, OUT, {OUT is [ITEM, *IN]})
-edcg_pred(process, 1, [counter, items])

# Each push targets a specific accumulator by name
process(X) >> ([1] // counter, [X] // items)
```

when a sub-call uses fewer accumulators than the caller, only the shared ones are threaded:

```clausal
# skip
-edcg_pred(inc_only, 0, [counter])          # only counter
-edcg_pred(do_both, 1, [counter, items])    # counter + items

inc_only >> ([1] // counter)
do_both(X) >> (inc_only, [X] // items)    # inc_only threads counter only
```

### Calling EDCG predicates

EDCG predicates are compiled to ordinary predicates with hidden arguments appended in declaration order: 2 per accumulator (in, out) + 1 per pass. You can call them from regular `<-` clauses using keyword syntax:

```clausal
# skip
# -edcg_pred(count_elems, 1, [len])
# Compiled arity: 1 (visible) + 2 (len_in, len_out) = 3
my_length(L, N) <- count_elems(L, _edcg_len_in_=0, _edcg_len_out_=N)
```

Or positionally — hidden args follow visible args in the order declared:

```clausal
# count_elems(List, len_in, len_out)
my_length(L, N) <- count_elems(L, 0, N)
```

### Complete example: counter with scale factor

```clausal
-module(example, [run_scaled(LIST, SCALE, COUNT, ITEMS)])

-edcg_acc(counter, X, IN, OUT, {OUT == IN + X})
-edcg_acc(items, ITEM, IN, OUT, {OUT is [ITEM, *IN]})
-edcg_pass(scale)

-edcg_pred(scaled_inc, 0, [counter, scale])
-edcg_pred(collect_and_count, 1, [counter, items, scale])
-edcg_pred(process_list, 1, [counter, items, scale])

scaled_inc >> (scale / S, [S] // counter)
collect_and_count(X) >> (scaled_inc, [X] // items)

process_list([]) >> ([])
process_list([X, *XS]) >> (collect_and_count(X), process_list(XS))

run_scaled(LIST, SCALE, COUNT, ITEMS) <- (
    process_list(LIST, _edcg_counter_in_=0, _edcg_counter_out_=COUNT,
                 _edcg_items_in_=[], _edcg_items_out_=ITEMS,
                 _edcg_scale_=SCALE)
)
```

### Design notes

- **Purely syntactic**: EDCG `>>` rules are rewritten to ordinary `<-` clauses before compilation. No runtime support needed.
- **Backward compatible**: Rules without `-edcg_pred` declarations continue to use standard DCG rewriting.
- **`//` for push, `/` for read**: These use Python's floor-division and division operators respectively.
- **Accumulator order matters**: Hidden args are appended in the order listed in `-edcg_pred`. when calling from `<-` clauses, match this order.

---

## Meta-predicates

Meta-predicates are higher-order predicates that take goals as arguments. They are compiled as special forms — the goal argument is compiled inline, not passed as a runtime value.

### [All-solutions predicates](meta_predicates.md)

```clausal
# Collect all X where in_(X, [1,2,3]) into Bag
findall(X, in_(X, [1, 2, 3]), BAG),

# Same but with a filter — only X > 1
findall(X, (in_(X, [1, 2, 3]) and X > 1), BAG),

# Cartesian product — template can be any term
findall([X, Y], (in_(X, [a, b]) and in_(Y, [1, 2])), BAG),

# bagof fails if no solutions (findall succeeds with [])
bagof(X, in_(X, LIST), BAG),

# setof deduplicates results (preserving first-occurrence order)
setof(X, in_(X, [1, 1, 2, 2, 3]), BAG),   # BAG = [1, 2, 3]
```

| Predicate | Empty result |
|---|---|
| `findall/3` | Succeeds with `Bag = []` |
| `bagof/3` | Fails |
| `setof/3` | Fails |

### Universal quantification

```clausal
# Succeeds iff Action holds for every solution of Cond
forall(in_(X, [2, 4, 6]), X > 0),   # succeeds
forall(in_(X, [2, -1, 6]), X > 0),  # fails
```

`forall(Cond, Action)` is equivalent to `not (Cond and not Action)`.

### Call/N

`Call/N` invokes a goal closure with extra arguments. It is an alias for `call_goal/N`:

```clausal
# skip
call_goal((X <- (X > 0)), 5),        # call_goal/2: succeeds
Call(GOAL, ARG1, ARG2),             # Call/3: invoke GOAL with two extra args
```

`call/1` through `call/8` are available (as are `call_goal/1` through `call_goal/8`).

### [Higher-order list predicates](higher_order.md)

These predicates take a goal closure and apply it across a list. All use committed choice (first solution per element).

```clausal
# skip
# maplist/2 — check Goal(Elem) succeeds for every element
maplist((X <- (X > 0)), [1, 2, 3]),              # succeeds

# maplist/3 — map Goal(X, Y) over list, collect results
maplist(((X, Y) <- (Y == X * 2)), [1, 2, 3], YS),  # YS = [2, 4, 6]

# include/3 — keep elements where Goal(Elem) succeeds
include((X <- (X > 0)), [1, -2, 3, -4], R),      # R = [1, 3]

# exclude/3 — keep elements where Goal(Elem) fails
exclude((X <- (X > 0)), [1, -2, 3, -4], R),     # R = [-2, -4]

# foldl/4 — left fold with Goal(Elem, Acc0, Acc1)
foldl(((E, A, R) <- (R == A + E)), [1, 2, 3], 0, SUM),  # SUM = 6
```

---

## [Constraint logic programming](constraints.md)

Clausal supports [CLP(ℤ)](constraints.md) (integer constraints) and [CLP(B)](clpb.md) (Boolean constraints). Constraint operators are used directly in clause bodies — no special escape or domain wrapper is needed.

```clausal
# skip
in_domain(X, 1, 9),
all_different([X, Y, Z]),
X + Y < Z,
label([X, Y, Z])
```

See [Constraints](constraints.md) for the full API.

---

## Why not allow free intermingling of Python and logic namespaces?

Three main reasons:

1. **Ambiguity.** It is impossible at compile time to distinguish a Python global from an atom without tracking all imports. Old compiled code could silently become wrong when a new name is imported. With explicit `--` escaping, the boundary is always visible.

2. **Term representation efficiency.** Compound terms are most efficiently represented as instances of generated classes (enabling `match`/`case` to work directly on them). Atoms need to be class objects for structural matching. Allowing arbitrary Python objects as functors requires a boxing wrapper, which is heavier.

3. **Logic variables must be visually distinct.** They are declared implicitly, work differently from Python names, and their bindings are reverted on backtracking. A clear syntactic marker (ALL-CAPS or leading underscore) avoids confusion without requiring explicit `declare` statements.

The escape mechanisms (`--`, `++`) cover all cases where interop is genuinely needed. Explicit is better than implicit.

---

---

## Syntax cheat sheet

```clausal
# skip
# Variables (ALL-CAPS preferred; leading-underscore also valid)
X, HEAD, REST          # ALL-CAPS logic variables
_x, _head, _rest       # leading-underscore style (also valid)
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
{"x": X, "y": Y}              # dict with variable values
{"addr": {"city": C}}         # nested dict

# Sets (SetTerm — elements must be ground)
{1, 2, 3}                     # set of integers
{"red", "green", "blue"}      # set of strings

# Unification
X is Y,                # unify
X is not Y,            # dif constraint (must stay different)
not (X is Y),          # immediate check (don't unify right now)

# Arithmetic / CLP(ℤ) constraints
(N == X + 1),          # arithmetic constraint
X == Y,                # arithmetic equality constraint
X != Y,                # arithmetic disequality constraint
X < Y,                 # less-than constraint
X <= Y,                # less-or-equal constraint
N := X + 1,            # eager arithmetic evaluation (Prolog is/2)
in_domain(X, 1, 10),    # post finite domain
all_different([X,Y,Z]), # pairwise disequality
label([X, Y, Z]),      # enumerate solutions (first-fail)
equivalent(X, Y),      # structural equality (Prolog ==/2)

# Rules and facts
Head <- call(X),       # single-call body (no parens needed)
Head <- (Body),        # operator body (parens required)
Fact,                  # fact (trivially true)
Rule >> ListDescription,   # DCG rule

# Goals
goal(A, B),            # compound goal
not goal,              # negation as failure
assertz(goal),          # assert fact/rule at runtime
retract(term),         # retract first matching clause

# Module qualification
utils.Double(X, Y),    # qualified call (after -import_module(utils))

# Escaping
--python_expr          # Python inside logic term
++logic_term           # logic term inside Python expression
~~python_expr          # capture as AST node

# Lambdas (anonymous clauses)
call_goal((X <- (R == X + 1)), 5)                             # R = 6
call_goal(((X, Y) <- (R == X + Y)), A, B)                 # multi-param

# Meta-predicates
findall(X, in_(X, [1,2,3]), BAG),          # BAG = [1,2,3]
bagof(X, in_(X, LIST), BAG),              # fails if LIST empty
setof(X, in_(X, XS), BAG),               # deduplicates
forall(in_(X, NS), X > 0),               # universal quantification
Call(GOAL, ARG1),                          # Call/2 (alias for call_goal/2)

# F-strings — logic variables auto-deref at search time
writeln(f"Hello, {NAME}!"),            # prints bound value of NAME
writeln(f"{X:.2f}"),                   # format specs work
write_to_string(f"{X} and {Y}", S),    # capture as string

# DCGs — >> defines grammar rules with difference lists
greeting >> (["hello", "world"]),          # terminal sequence
sentence >> (noun_phrase, verb_phrase),    # non-terminal chain
digit(D) >> ([D], {D >= 0}, {D <= 9}),    # args + inline goals
letter >> (["a"] or ["b"] or ["c"]),      # disjunction
not_a >> (not ["a"], [X]),                # negation
(peek(T), [T]) >> ([T]),                  # pushback/semicontext
phrase(greeting, ["hello", "world"]),     # phrase/2 — must consume all
phrase(digit(D), [3], REST),              # phrase/3 — partial parse

# EDCGs — Extended DCGs (multiple named accumulators + passed args)
-edcg_acc(counter, X, IN, OUT, {OUT == IN + X})  # declare accumulator
-edcg_pass(config)                                # declare passed arg
-edcg_pred(inc, 0, [counter])                     # declare pred's hidden args
inc >> ([1] // counter)                   # [value] // acc — push to accumulator
get(V) >> (counter / V)                   # acc / Var — read current value
scaled >> (scale / S, [S] // counter)     # pass / Var — read passed arg

# Python interop — ++() evaluates Python at search time
N is ++len(L),                       # call Python builtin
R is ++S.upper(),                    # method call on deref'd var
R is ++(X + 1),                      # Python arithmetic
R is ++L[0],                         # subscript access
R is ++D[K],                         # dict access
++print(X),                          # side-effect goal

# Higher-order list predicates
maplist(GOAL, [1, 2, 3]),                   # check GOAL on each element
maplist(GOAL, XS, YS),                      # map GOAL(X, Y) over list
include(GOAL, LIST, KEPT),                   # keep where GOAL succeeds
exclude(GOAL, LIST, REMOVED),               # keep where GOAL fails
foldl(GOAL, LIST, ACC0, RESULT),         # left fold with GOAL(Elem, Acc, Next)
get_item(INDEX, LIST, ELEM),                 # 0-based index access
in_check(ELEM, LIST),                        # deterministic membership check
unpack(TERM, LIST),                         # decompose/construct term
```

---

*See also: [Tutorial](tutorial.md) — hands-on introduction to Clausal · [Predicates & Rules](predicates.md) — clause forms, dispatch, and guards · [Builtins](builtins.md) — full predicate reference.*
