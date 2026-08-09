# Clausal — Syntax Design

Clausal uses Python's parser, and so it conforms to Python's grammar. Like Prolog, it describes Horn Clauses - simple constructs that facilitate the representation of facts and rules, backed by strong mathematical formalisms, to facilitate high-level reasoning with useful guarantees.

Clausal uses 'grammatical holes' which are and must remain syntactically valid, but have no semantic purpose in Python, and are therefore never used in practice. Clausal uses a very small set of these 'holes' to allow the free mixing of logic code with Python code. Python and logic programming code in the same file means better code cohesion, easing development.

> **Quick navigation:** [Variables](#logic-variables) · [Escape operators](#escape-operators) · [Unification](#unification) · [Clauses](#horn-clauses) · [Lists](#lists) · [Arithmetic](#arithmetic-binding) · [Constraints](#comparison-operators-clpℤ) · [DCGs](#definite-clause-grammars--) · [Lambdas](#lambdas) · [Meta-predicates](#meta-predicates) · [Cheatsheet](#syntax-cheat-sheet)

---

## Trailing comma rule

**Expression statements ending in `,` are interpreted as logical terms (facts or goals).**

In standard Python, an expression statement that ends in a comma produces a tuple which is then discarded. So this is never used despite being valid (a grammatical hole). It also means these logic terms are easy to cut, copy, paste, and indent — unlike Prolog, they don't require `.` terminators.

---

## Escape operators

Three double-prefix operators demarcate the boundary between Python and logic code. They must not be split with spaces (e.g. `- -` would be parsed as double negation).

| Operator | Meaning |
|---|---|
| `--expr` | Python expression embedded inside a logic term |
| `++expr` | In a Python context: logic term inside a Python expression. In a `.clausal` context: evaluate Python expression at search time |
| `~~expr` | Capture expression as a `simple_ast` AST node (works anywhere) |

`--` was chosen because:
- it doesn't introduce a new keyword or clobber any identifier
- double negation is rare in Python code (and if you really want it, type it as '- -x')
- it is visually prominent and quick to type

Example:
```clausal
--8<-- "tests/fixtures/docs/syntax_sigs.txt:escape_operators"
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

This is a deliberate departure from Prolog, where variables start with an uppercase letter (`Foo`, `Bar`). In Python, TitleCase names are conventionally class names, so Clausal reserves TitleCase for atoms and compound-term functors (`Red`, `Point(X, Y)`); predicates themselves are lowercase (`findall`, `in_`, `length`). Reusing TitleCase for variables as well would create ambiguity: in `Foo(Bar)`, is `Bar` the atom `Bar` or a logic variable? ALL-CAPS resolves this cleanly — `findall(X, in_(X, LIST), BAG)` is unambiguous.

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
--8<-- "tests/fixtures/docs/syntax_sigs.txt:atoms"
```

An identifier that collides with a Python keyword or builtin (`not`, `is`, `max`) cannot be written as a bare atom. Quoting it — `'not'` — yields a **string**, not a declared atom (see [Atoms vs strings](#atoms-vs-strings-there-are-no-string-atoms)): it works as a symbolic *value*, but `atom/1` will not match it. If you need a true `PredicateMeta` atom, pick a non-colliding identifier (e.g. `not_`) or mint one dynamically with `make_atom("not")`.

Every atom is reified at compile time as a zero-arity `PredicateMeta` class — atoms are first-class values you can pass around, store in dicts, and compare with `is`. Unification on atoms is class identity.

!!! info "Strict by default; global identity when resolved"
    An undeclared bare atom reference is a compile-time `NameError` by default —
    matching Python's treatment of undefined names. A bare `red` that has not been
    declared (via `-module`, `-private`, or `-import_from`) or reached via
    `global_atom/2` will not compile.

    Files that want Prolog-style ceremony-free tag atoms opt out with
    [`-implicit_atoms`](directives.md#-implicit_atoms).

    Once an atom **is** resolved — declared in `-module([...])` (public),
    `-private([...])` (private), imported, or reached via `global_atom/2` —
    it has **process-wide global identity**: every module that resolves the same
    name to the global atom gets the identical `PredicateMeta` class, matching
    Prolog's convention.

    ```clausal
    --8<-- "tests/fixtures/docs/syntax_sigs.txt:atoms_global_default"
    ```

    A module opts an atom into **module-local** identity (a class distinct from
    the global one) by listing it in `-module([...])` or [`-private([...])`](directives.md#-private).
    The two lists differ only in whether the name is advertised as part of the
    module's surface — a `-private` atom is still importable:

    ```clausal
    --8<-- "tests/fixtures/docs/syntax_sigs.txt:atoms_module_local"
    ```

    Resolution order for a bare reference inside a module: `-private` → `-module` → `-import_from` → global fallthrough.

    The full design is in the [global-atoms-default spec](https://gitlab.com/MikeAmy/clausal/-/blob/main/implementation_plans/atoms_refactor/GLOBAL_ATOMS_DEFAULT.md).

Predicates with arity ≥ 1 do **not** participate in the global default: they remain module-local-by-default and must be listed in `-module` / `-private` (or imported via `-import_from`) to be shared across modules. The asymmetry between atoms (global default) and predicates (local default) is principled — Prolog itself treats atoms as global and predicates as module-scoped.

---

## Builtin predicate naming

Built-in predicates are lowercase `snake_case` (e.g. `findall`, `assertz`, `var`, `read_file`). Where a natural name collides with Python, a **trailing underscore** disambiguates. This is a deliberate design choice — not aesthetic — with two goals:

1. **Avoid Python keyword conflicts.** Many natural predicate names are Python reserved words: `in`, `is`, `not`, `and`, `or`, `if`, `for`, `assert`, `lambda`, `global`, `return`, `yield`. A predicate named `in` would be a syntax error the moment it appears as a call in a clause body — so membership is spelled `in_`.

2. **Avoid Python builtin conflicts.** Names like `abs`, `all`, `any`, `filter`, `float`, `int`, `map`, `max`, `min`, `set`, `str`, `sum` are Python builtins that would shadow (or be shadowed by) a same-named predicate — so these take a trailing underscore: `abs_`, `float_`, `max_`, `min_`, `sum_`, `divmod_`.

The trailing underscore keeps the builtin namespace cleanly separate from Python keywords and builtins. User predicates follow the same `snake_case` convention, and only need the underscore where they would hit the same collision.

3. **A few engine-provided type names are reserved.** For convenience in embedded Python, `Var`, `Trail`, `Compound`, `PredicateMeta`, `DictTerm`, `SetTerm`, `PyThunk`, and `Quantity` are injected into every module's namespace, so a predicate named after one of these (e.g. `Var/2`) collides. The engine *functions* `walk`, `deref`, and `unify` used to be reserved the same way, but no longer are — they are now injected under an internal `$`-prefix, so `walk/2`, `deref/2`, and `unify/2` are free for user predicates.

---

## Unification

Unification is written with `is`:

```clausal
--8<-- "tests/fixtures/docs/syntax_sigs.txt:unification"
```

Why `is` rather than `=`?
- `=` is Python's assignment operator and cannot appear in expressions
- `is` expresses the same concept in English — two things being the same — and Python programmers understand it. Clausal generalises this concept; in 'X is Y', if we don't know X or Y, we are describing that they must be same whatever they are, and when either become known, they both become known.

Conversely, `X is not Y` posts a disequality constraint (`dif/2`): X and Y must end up with different values. This is lazily checked — the constraint is re-evaluated each time either variable gets bound. If they become equal, the constraint fails and the search backtracks. If they remain different, the constraint is satisfied and dropped. See [constraints.md](constraints.md) for details.

`not (X is Y)` is the immediate check (Prolog `\=/2`): it fails if X and Y *can* unify right now, regardless of future bindings. Use this when you want point-in-time semantics.

The corresponding AST node is `Unify(left, right)`. Disequality is `DoesNotUnify(left, right)`.

### Inline naming with `is`-chains

Python's comparison chaining gives Clausal unification chains: `A is B is C`
unifies pairwise, and the shared middle operand is evaluated **once**. This
names a term and uses it in the same goal — where Python code would reach for
the walrus operator:

```clausal
Test("name a term inline") <- (
    D is {"k": [1, 2]},
    VALUE is [1, X] is D["k"],
    X == 2
)
```

Here `[1, X]` is constructed once, named `VALUE`, and unified with `D["k"]` —
binding `X` to `2` in the process. Chains of any length work; each link is an
independent unification of the adjacent operands.

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
- `eval_(expr, X)` — eager arithmetic evaluation; evaluates `expr` as an arithmetic expression with Python semantics and binds the result to `X` (Prolog's `is/2`). See [Arithmetic](arithmetic.md) for when to prefer it over `==`.

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

`==` and `!=` post CLP(ℤ) arithmetic constraints (Prolog `=:=/2` and `=\=/2`). For true structural equality (Prolog `==/2`) — comparing deref'd terms without binding or evaluating — use the builtin `structural_eq(X, Y)`, or `not structural_eq(X, Y)` for inequality.

See [constraints.md](constraints.md) for the full CLP(ℤ) design, including domain representation, propagation, and labeling.

---

## Horn clauses

```clausal
--8<-- "tests/fixtures/docs/syntax_sigs.txt:horn_clauses"
```

The `<-` operator denotes a Horn clause (rule). It will never be added to Python's expression grammar because it conflicts with `x < -y` (less-than applied to a negated value) — but only when there is no surrounding whitespace. With whitespace, it is unambiguous and parseable.

### Body style

The body after `<-` must be one of:

- **A single call** — no parentheses needed:
  ```clausal
  --8<-- "tests/fixtures/docs/syntax_sigs.txt:body_style_ex2"
  ```

- **A bare name** — no parentheses needed:
  ```clausal
  --8<-- "tests/fixtures/docs/syntax_sigs.txt:body_style_ex3"
  ```

- **Anything else** — parenthesized:
  ```clausal
  --8<-- "tests/fixtures/docs/syntax_sigs.txt:body_style_ex4"
  ```

This rule exists because Python's parser sees `<-` as `<` followed by unary `-`. when the body contains operators (`+`, `<`, `and`, `or`, `not`, etc.), the `-` gets absorbed into the body expression and the AST is silently mangled. Parentheses force Python to treat the body as a single grouped expression, keeping the `-` at the top where the term rewriter can find it. Calls and bare names are safe without parentheses because they bind tighter than unary `-`.

To keep things safe, attempting to write an unparenthesized operator body produces a clear error:

```clausal
--8<-- "tests/fixtures/docs/syntax_sigs.txt:body_style"
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
--8<-- "tests/fixtures/docs/syntax_sigs.txt:conjunction_style"
```

---

## Lists

```clausal
--8<-- "tests/fixtures/docs/syntax_sigs.txt:lists"
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

Every string literal — `"…"`, `'…'`, or `u"…"` — is a Python `str`, and a `str`
behaves as a **list of character atoms** under unification (the classical Prolog *chars*
model). See [strings as lists](strings_as_lists.md):

```clausal
--8<-- "tests/fixtures/docs/syntax_sigs.txt:strings"
```

All list operations apply to strings. A string is **not** a declared (`PredicateMeta`)
atom — `atom/1` rejects it, `is_str/1` accepts it. The analogous `b"…"` byte literal is a
[list of integer codes](bytes_as_lists.md) (`0–255`); `str` and `bytes` are distinct
domains and never cross-unify.

!!! note "Quote style, and the `u"…"` prefix, carry no meaning"
    Single vs double quotes are indistinguishable — Python's parser erases the quote
    character before Clausal sees the term. The `u` prefix is likewise inert: `u"abc"`,
    `"abc"`, and `'abc'` all produce the same `str`. Clausal keys on the value's *type*
    (`str` vs `bytes`), never on how it was written.

---

## Atoms vs strings: there are no "string atoms"

Clausal deliberately keeps two disjoint kinds where Prolog blurs them behind quoting:

| | **Symbol** | **Text / data** |
|---|---|---|
| written as | identifier — `red`, `café`, `δικαίωμα` | string — `"hello world"`, `'Reg (XX) 2020/123'` |
| reifies as | interned zero-arity `PredicateMeta` class | Python `str` (a list of character atoms) |
| identity | global class identity; `is` works | value equality; also unifies as a char-list |
| typo-safe? | yes, under [`-strict_atoms`](directives.md#-strict_atoms) | no (it's data) |
| `atom/1` | matches | does **not** match (use `is_str/1`) |

Unlike Prolog, a **quoted string never denotes an atom** — it is always text. This is a
conscious choice, not a missing feature. Prolog's quoted atoms (`'hello world'`) exist for
exactly one reason: to give a *symbol* a human-readable name with spaces or punctuation
that a bare token can't carry. Clausal covers that need two other ways, so the construct
earns nothing:

- **Any-language names, unquoted.** Identifiers accept the full Unicode *is-letter* set
  (they ride Python's identifier rules), so `café`, `größe`, `δικαίωμα`, and CJK names are
  ordinary atoms — no quoting required. Only spaces, punctuation, and leading digits remain
  out of reach, and those belong to *display text*, not symbol identity.
- **Human-readable display lives in the translation layer.** Verbatim, punctuated,
  multilingual text (e.g. a citation `Regulation (XX) 2020/123, Art 6`) is held in the
  translation lexicon keyed by an identifier atom — so the logic depends on the typo-safe
  symbol while presentation stays free-form.

Adding string atoms would also actively *harm* the model: because a `str` already unifies
as a list of characters, a quoted "atom" could not simultaneously be a distinct symbol and
a char-list without new disambiguating syntax — reintroducing precisely the `str`-vs-symbol
confusion this split removes.

**If you genuinely need an atom whose name isn't a valid identifier** (e.g. interning
symbols imported from an external system), mint it at runtime with `make_atom("any name")`
rather than quoting a literal. Prefer the identifier-plus-lexicon pattern for everything
else.

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
--8<-- "tests/fixtures/docs/syntax_sigs.txt:unit_literal_sugar"
```

when a **logic variable** is used as the callable instead, `X(Unit)` becomes a
goal that posts a dimension constraint on `X`:

```clausal
--8<-- "tests/fixtures/docs/syntax_sigs.txt:unit_literal_sugar_ex2"
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
--8<-- "tests/fixtures/docs/syntax_sigs.txt:immediate_goals"
```

---

## Module qualification

Predicates from imported modules are called with dotted notation after loading the module:

```clausal
--8<-- "tests/fixtures/docs/syntax_sigs.txt:module_qualification"
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
--8<-- "tests/fixtures/docs/syntax_sigs.txt:invoking_dcgs_with_phrase"
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
--8<-- "tests/fixtures/docs/syntax_sigs.txt:dcgs_as_general_state_passing"
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
# Numeric counter: Out = in + Value
-edcg_acc(counter, X, IN, OUT, {OUT == IN + X})

# List accumulator: prepend items
-edcg_acc(items, ITEM, IN, OUT, {OUT is [ITEM, *IN]})

# Product accumulator: Out = in * Value
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
--8<-- "tests/fixtures/docs/syntax_sigs.txt:declaring_predicates"
```

The special name `dcg` refers to the standard DCG difference-list accumulator. Include it when your EDCG rule also parses tokens.

### EDCG rule syntax

EDCG rules use `>>` just like standard DCGs, with additional operators:

```clausal
--8<-- "tests/fixtures/docs/syntax_sigs.txt:edcg_rule_syntax"
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
--8<-- "tests/fixtures/docs/syntax_sigs.txt:multiple_accumulators"
```

### Calling EDCG predicates

EDCG predicates are compiled to ordinary predicates with hidden arguments appended in declaration order: 2 per accumulator (in, out) + 1 per pass. You can call them from regular `<-` clauses using keyword syntax:

```clausal
--8<-- "tests/fixtures/docs/syntax_sigs.txt:calling_edcg_predicates"
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
--8<-- "tests/fixtures/docs/syntax_sigs.txt:call_n"
```

`call/1` through `call/8` are available (as are `call_goal/1` through `call_goal/8`).

### [Higher-order list predicates](higher_order.md)

These predicates take a goal closure and apply it across a list. All use committed choice (first solution per element).

```clausal
--8<-- "tests/fixtures/docs/syntax_sigs.txt:higher_order_list_predicates"
```

---

## [Constraint logic programming](constraints.md)

Clausal supports [CLP(ℤ)](constraints.md) (integer constraints) and [CLP(B)](clpb.md) (Boolean constraints). Constraint operators are used directly in clause bodies — no special escape or domain wrapper is needed.

```clausal
--8<-- "tests/fixtures/docs/syntax_sigs.txt:constraint_logic_programming"
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
--8<-- "tests/fixtures/docs/syntax_sigs.txt:syntax_cheat_sheet"
```

---

## When the syntax is wrong

`.clausal` is Python surface syntax, so a malformed clause is reported by
CPython's parser — and a parser reports where it *gave up*, not where the
mistake is. For a rule body that is almost always the closing `)`, one or more
lines below the defect. The loader therefore prints the source itself
(`clausal/syntax_diagnostics.py`, hooked into the parse in
`clausal/import_hook.py`):

```text
invalid syntax (m.clausal, line 6)
    3 | f(X) <- (
    4 |     X > 1,
    5 |     Y is
      |         ^ `is` has no right-hand side
    6 | )
      | ^ parse gave up here
  -> complete the expression, or delete the goal — a Clausal goal cannot end
     on an operator.
```

Read it bottom-up: line 6 is where the parser stopped and is marked as such;
line 5 is the line to edit. Up to three preceding lines are shown, plus the
enclosing clause head when it falls outside that window (with `...N lines
omitted`), so a long body cannot bury the diagnosis.

The construct is named where it can be inferred with confidence — a dangling
operator (`is`, `+`, `>`, `=`) with no right-hand side, a `<-` whose
multi-goal body is not parenthesised, a goal not followed by `,`, an unclosed
`(`, an unterminated string, and the two Prolog habits `head :- body` and a
trailing `).`. When nothing can be inferred the source and caret are still
shown and no guess is offered.

Everything CPython set is preserved: the message's first line is its own, and
`msg`, `lineno`, `offset`, `text` and the exception class (`SyntaxError`,
`IndentationError`, `TabError`) are unchanged. Genuine `.py` files are not
touched — their errors are Python's to report.

---

*See also: [Tutorial](tutorial.md) — hands-on introduction to Clausal · [Predicates & Rules](predicates.md) — clause forms, dispatch, and guards · [Builtins](builtins.md) — full predicate reference.*
