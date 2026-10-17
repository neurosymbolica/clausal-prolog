# Predicates & Rules

Predicates are the core building block of Clausal Prolog programs. A predicate defines a **relation** between its arguments — it describes when something is true. Each predicate is defined by one or more **clauses**: either facts (unconditionally true) or rules (true when certain conditions hold). See [Thinking Relationally](thinking_relationally.md) for a deeper treatment of this idea.

!!! note "Clausal Prolog and the seam"

    Examples on this page are [Clausal Prolog](clausal_prolog.md)
    (`.clausal`): ISO Prolog syntax, where a clause ends with `.` and a rule
    is `Head :- Body`. The [seam](syntax.md), Clausal's Python-syntax
    surface, writes the same predicates with `<-` and Python syntax; a few
    features on this page (field names, `-private`) exist only there, and
    the page says so.

---

## Quick Example

```clausal
% Facts: edge/2 is true for these pairs
edge(1, 2).
edge(2, 3).
edge(1, 3).

% Rule: reach/2 is true when there is a path
reach(X, Y) :-
    edge(X, Y).
reach(X, Y) :-
    edge(X, Z),
    reach(Z, Y).

test("reach") :-
    reach(1, 3).
```

Query it from a plain `.py` file with `solve(("reach", 1, Y), module=m)`,
which answers `Y` = 2, 3, 3 — see
[Querying from Python](python_integration.md#querying-from-python). A
`.seam` file that hosts Python can put the goal in goal position (`--`):

```python
if --reach(1, 3):
    print("reachable")        # succeeds (both directly and via node 2)
for Y in --reach(1, Y):
    print(Y)                  # 2, 3, 3
```

---

## Facts

A fact is a clause with no body — it is unconditionally true. Facts end with a period:

```clausal
color(red, warm).
color(blue, cool).
color(green, cool).
```

Facts define the base data of your program. Think of them as rows in a database table.

Multiple facts for the same predicate are logical alternatives. The engine searches for those that unify with the goal, in source order. `color(X, cool)` unifies with `color(blue, cool)` first, then `color(green, cool)`.

A bare `red` is an atom, as in ISO; a quoted `'red'` is the same atom. A
double-quoted `"red"` is a **string**, not an atom. (In the seam a bare
atom must be declared first — see [Atoms](syntax.md#atoms).)

---

## Rules

A rule has a **head** (the conclusion) and a **body** (the conditions). The head holds when all conditions in the body hold:

```clausal
color(red, warm).

warm_color(C) :-
    color(C, warm).
```

Read this as: "C is a warm color if `color(C, warm)` holds."

### Multi-Goal Bodies

when a rule has multiple goals, they are comma-separated:

```clausal
friend_of_friend(A, C) :-
    friend(A, B),
    friend(B, C),
    dif(A, C).
```

The conditions in the body must all hold for the head to hold. If a condition does not hold, the engine explores the remaining clause alternatives.

---

## Clause Alternatives

A predicate can have multiple clauses — facts and rules mixed freely. These are logical alternatives; the engine searches for those whose heads unify with the goal, in source order:

```clausal
:- use_module(library(clpz)).

factorial(0, 1).
factorial(N, F) :-
    N > 0,
    N1 #= N - 1,
    factorial(N1, F1),
    F #= N * F1.

test("fact 5") :-
    factorial(5, 120).
```

The first clause states that the factorial of 0 is 1. The second clause states the recursive relationship: the factorial of N is F when N is positive, and F is N-1's factorial times N. These clauses are logical alternatives.

### Guards

Guards are conditions in the rule body that state when a clause holds:

```clausal
classify(N, positive) :-
    N > 0.
classify(0, zero).
classify(N, negative) :-
    N < 0.
```

The condition `N > 0` ensures the first clause only holds for positive numbers. Without it, the clause head would unify with any N.

### Source Order

when multiple clause heads unify with the goal, the engine explores them in source order:

```clausal
maximum(X, Y, X) :-
    X >= Y.
maximum(X, Y, Y) :-
    X < Y.

test("max 3 5") :-
    maximum(3, 5, R),
    R == 5.

test("max 7 2") :-
    maximum(7, 2, R),
    R == 7.
```

For `maximum(3, 5, R)`: the first clause's condition `3 >= 5` does not hold, so the engine explores the second clause, which holds with `R = 5`.

---

## Building Up a Program

Start with a simple family tree:

```clausal
parent(alice, bob).
parent(bob, carol).
parent(carol, dave).
```

**Direct parent query**: `parent(alice, bob)` succeeds.

**Ancestor relation** — generalize parent to any depth:

```clausal
ancestor(X, Y) :-
    parent(X, Y).
ancestor(X, Y) :-
    parent(X, Z),
    ancestor(Z, Y).
```

Now `ancestor(alice, dave)` holds — the relation connects them through the chain alice → bob → carol → dave.

**Add metadata** — track the generation distance:

```clausal
:- use_module(library(clpz)).

ancestor(X, Y, 1) :-
    parent(X, Y).
ancestor(X, Y, N) :-
    parent(X, Z),
    ancestor(Z, Y, N1),
    N #= N1 + 1.

parent(alice, bob).
parent(bob, carol).
parent(carol, dave).

test("generations") :-
    ancestor(alice, dave, N),
    N == 3.
```

`ancestor(alice, dave, N)` yields `N = 3`.

This pattern — base case as a fact, recursive case as a rule — is the fundamental building block of Clausal Prolog programs.

---

## Recursive Predicates

Recursive predicates define relations over inductively structured data (like lists or natural numbers). The pattern is: a base clause and a recursive clause:

```clausal
:- use_module(library(clpz)).

length([], 0).
length([_|REST], N) :-
    length(REST, N1),
    N #= N1 + 1.

test("length 0") :-
    length([], 0).

test("length 3") :-
    length([1, 2, 3], N),
    N == 3.
```

For [list](lists.md) relations, the base clause typically holds for the empty list `[]`, and the recursive clause relates a non-empty list `[HEAD|TAIL]` to its parts (the seam writes it `[HEAD, *TAIL]`, like Python).

---

## Private Predicates

A module's export list is its surface: a predicate the `:- module(Name, Exports)` list does not name is internal to the module:

```clausal
:- module(calc, [compute/2]).
:- use_module(library(clpz)).

% Documented surface: other modules are meant to call this
compute(X, R) :-
    helper(X, TEMP),
    R #= TEMP * 2.

% Internal: an implementation detail of compute/2
helper(X, Y) :-
    Y #= X + 1.

test("compute") :-
    compute(3, 8).

:- end_module(calc).
```

Leave a predicate out of the export list when it is an implementation detail that other modules should not depend on. Importing it by name is refused: `:- use_module(calc, [helper/2])` fails to load with `permission_error(access, private_procedure, helper/2)`, and after `:- use_module(calc)` an unqualified `helper(3, R)` is an `existence_error`. A module-qualified call still reaches it: `calc:helper(3, R)` answers `R = 4`.

!!! warning "In the seam, `-private` is advisory, not enforced"
    The seam marks an internal predicate with the `-private([helper(X, Y)])` directive. A `-private` predicate is **still importable**. `-import_from(this_module, [helper])` succeeds and binds this module's `helper` predicate (its handle). The seam has no access control — the marker discourages coupling, it does not prevent it, exactly like a leading underscore in Python. See [Directives § `-private`](directives.md#-private) for the full meaning of the directive.

---

## Fields and Arity

In the seam, predicate fields are inferred from clause heads — no separate declaration needed:

```seam
# point/2 has fields ('arg_0', 'arg_1'): no head variable names them
point(0, 0),
point(1, 1),

# distance/3 has fields ('x1', 'x2', 'd'): named after the head variables
distance(X1, X2, D) <- (
    DX == X2 - X1,
    abs_(DX, D)
)
```

A `-module` export list or a `-private([name(field, ...)])` declaration names
the fields explicitly (see [Term Inspection § Fields by name](term_inspection.md#fields-by-name)).
Field names are a seam feature: a `.clausal` predicate's arguments are
positional, as in ISO, and its heads record no field names.

The **arity** is the number of arguments. `point/2` means "point with 2 arguments." Different arities define different predicates: `foo/1` and `foo/2` are unrelated.

That holds **in one file** too, as in ISO: `foo(a, b).` and `foo(a).` in the
same file define `foo/2` and `foo/1`, two procedures, one clause each. Neither
absorbs the other: the short head is never padded to `foo(a, _)`. A DCG
nonterminal works the same way: `state//1` and `state//2` are `state/3` and
`state/4`. A bare `foo` in a data position is the atom `foo`, whatever arities
`foo` has, and `foo(1, 2)` in a data position is the compound at the arity
written.

In the seam, a name whose **field names are declared** -- a `-private([point(x, y)])`
entry, a `-module(m, [f(A)])` template entry -- has exactly the arities its
declarations name, each with its own field names. One list may declare
several:

```seam
-module(lib, [q(X), q(X, Y)])
q(1),
q(1, 2),
```

A clause head at an arity no declaration names fails at load, naming both
sites (this catches a head written with one argument too many or too few):

- *functor f/2 conflicts with the declaration of f/1 in the same file*, or,
  for a shorter head, *... a clause head is not a partial term*. A position
  that really means "anything" must be spelled `_`.

To give such a name another arity, declare that arity too: `f(A, B)` beside
`f(A)` in the list, or ISO's predicate indicator `f/2` (no field names).
An `-edcg_pred` name keeps one arity per file. (A keyword argument,
`foo(a=1)`, is a load-time `SyntaxError` in a head or a term: terms are built
positionally. A Python seam or `-constants` value that builds a term by field
name picks the arity written, positional plus keyword count; when that arity
is not declared and the keywords fit more than one declared arity, it raises
`AmbiguousArityConstructionError` rather than guess.)

A term is never padded anywhere: write every argument, using `_` for one you
leave open.

Calling a predicate at an arity it does not have is an error, and it is reported
as one:

```
citation takes 3 arguments, but this call passes 2
  citation/3 is defined at citations.seam:14.
  -> pass 3 arguments to citation, or define citation/2: a citation clause
     head with 2 arguments is a procedure of its own, unrelated to citation/3
     (as in ISO).
```

This is a `PredicateArityMismatchError`, which is a `TypeError` and, since
2026-09-25, also a `LogicException` carrying the ISO term Scryer raises for the
same call: `error(existence_error(procedure, citation/2), citation/2)` -- the
indicator at the *called* arity, with the message above as `.message`. So
`catch(G, error(existence_error(procedure, PI), _), Recovery)` catches it, as do
`except TypeError` in Python and a `++TypeError` catcher. If the name is
not in scope at *any* arity, the failure is a `PredicateNotFoundError` instead
and the message lists what is reachable — see [Importing](import.md).

---

## Defining Predicates in `.clausal` Files

Clausal Prolog files use [ISO Prolog syntax](clausal_prolog.md), without cut:

```clausal
% Comments start with %

% Facts end with a period
color(red, warm).
color(blue, cool).

% Rules use :- (implication)
warm_color(C) :-
    color(C, warm).

% Multi-goal bodies are comma-separated
nice_color(C) :-
    color(C, cool),
    dif(C, blue).
```

The same predicates in the seam, which uses [Python syntax](syntax.md):

```seam
# Comments start with #

# Facts end with a comma
color('red', 'warm'),
color('blue', 'cool'),

# Rules use <- (implication arrow)
warm_color(C) <- color(C, 'warm')

# Multi-goal bodies are parenthesized, comma-separated
nice_color(C) <- (
    color(C, 'cool'),
    dif(C, 'blue')
)
```

Files are loaded via Python's [import system](import.md). `import my_module` loads `my_module.seam` and compiles all predicates (a `my_module.clausal` or `my_module.pl` loads the same way; in one directory `.seam` beats `.clausal`, which beats `.pl`).

---

## Python API (advanced)

> For most use cases, define predicates in `.clausal` or `.seam` files and query them with the goal-position seam (`for X in --pred(X):`) from Python hosted in a `.seam` file. This section covers the lower-level API for a plain `.py` file, which cannot use `--`, and for goals built at runtime. The 1.0 surface is listed in [Public API](public-api.md).

### Predicates from Python

A loaded module's attribute for a predicate is the predicate's **handle**: a
`str` naming the module that owns it and the predicate. It names the
predicate; it is not a class and not something to call. To run a predicate,
build a goal **cell** — its name followed by its arguments — and pass the
module (see [Querying from Python](python_integration.md#querying-from-python)):

```python
from clausal import Var, solve
from clausal.examples import fibonacci

for trail in solve(("fib", 10, F := Var()), module=fibonacci):
    print(F.value)  # 55
```

### Rows and signatures

A predicate's state — its clauses, its compiled dispatch, whether it is
locked — lives on its row in the module's `Database`, and its field names are
recorded there too. Ask the database, by name and arity:

```python
from clausal.examples import fibonacci
from clausal.logic.predicate import resolve_predicate_row

db = fibonacci.__clausal_module__.db
row = db.row("fib", 2)
row.locked                       # True  — not declared -dynamic
len(row.clauses)                 # 3
db.field_names_at("fib", 2)      # ('N', 'F') — from the -module declaration

# From a handle, e.g. one a module imported: the OWNER's row
resolve_predicate_row(fibonacci.fib, arity=2) is row   # True
```

### Locking

Predicates are locked after module loading — `assertz`/`retract` on one raise the ISO `permission_error(modify, static_procedure, Name/Arity)`. Use `-dynamic(pred/arity)` to allow runtime modification; from Python, run the builtin as a goal: `once(("assertz", ("counter", 1)), module=m)`. See [Directives](directives.md) and [Database Operations](database_ops.md).

---

??? info "Test coverage"

    - `tests/test_compiled_programs.py` (41 tests): graph reachability, fibonacci, N-queens, NAF
    - `tests/test_predicate_meta.py`: predicate rows, handles and locking
    - `tests/fixtures/edge_graph.seam`: example fact + rule predicate file

---

*See also: [Directives](directives.md) — `-dynamic`, `-table`, `-private`, and other predicate property declarations.*
*See also: [If-Then-Else](reified_ite.md) — conditional expressions within rule bodies.*
*See also: [Lambdas](lambdas.md) — anonymous predicates (goal closures).*
