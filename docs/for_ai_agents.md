# Clausal Prolog for AI Agents

This page is for large language models, AI coding assistants, and autonomous
agents. It explains why generating Clausal Prolog code is often a better strategy than
generating imperative Python — and how to do it well.

---

## Which surface to write

**Write [Clausal Prolog](clausal_prolog.md): `.clausal` files, ISO Prolog
syntax without cut.** It is the default surface, and the examples on this
page are `.clausal`. Its syntax is the ISO Prolog you have seen most of
(`:-`, `[H|T]`, `X = Y`, `X is E`, `\+ G`). The differences are a few
deliberate rules, checked when the file loads: no cut, and a module ends
with `end_module/1` ([the list](#rules-that-are-easy-to-get-wrong)).

The [seam](syntax.md) (`.seam` files, Python syntax) is the boundary with
Python. Write a `.seam` module only for what `.clausal` cannot do:

- **calling Python** from a goal, with the `++expr` escape (the
  [bridge pattern](#pattern-bridge-to-python) below);
- **hosting Python** that asks questions with `--goal` in goal position
  (the [querying pattern](#pattern-querying-from-python) below).

A `.clausal` module reaches Python only through the engine's `library(...)`
facades (`library(json)`, `library(py_process)`, …) or by importing a
`.seam` module; see
[Python only through the seam](clausal_prolog.md#python-only-through-the-seam).
Plain `.py` code queries either kind of module with `solve`/`once`.

---

## Why logic programming is a natural fit for LLMs

### You already think declaratively

when you reason about a problem, you think about **what must hold** — the
constraints, the relationships, the conditions. You don't naturally think about
loop indices, mutable state, or memory allocation. Logic programming matches
this: you state what holds, and the system derives consequences.

This means the gap between your reasoning and the generated code is smaller.
Less translation means fewer bugs.

### Correctness is easier to verify

A Clausal Prolog predicate is a set of logical statements. Each clause says: "this
relation holds when these conditions hold." This makes it straightforward to
verify:

- **Read each clause independently.** Clauses are logical alternatives — they
  can be checked in isolation. You don't need to trace execution through the
  whole program.
- **Test with queries.** A test is just a query that should hold. No mock
  objects, no test fixtures, no setup/teardown.
- **Use the most general query.** If `predicate(X, Y)` with all fresh
  variables gives meaningful answers, the predicate is correct in all modes.

```clausal
:- use_module(library(clpz)).

% The definition
list_length([], 0).
list_length([_|REST], N) :-
    list_length(REST, N1),
    N #= N1 + 1.

% Tests are just queries that should hold
test("empty") :-
    list_length([], 0).

test("three") :-
    list_length([1, 2, 3], 3).
```

### Fewer ways to be wrong

Imperative code has many failure modes: off-by-one errors, forgotten edge
cases, incorrect state mutation, resource leaks, race conditions. Pure Clausal Prolog
code eliminates most of these:

- **No mutable state.** Variables are bound once through unification, never
  reassigned.
- **No loop errors.** Recursion with clause alternatives replaces explicit
  loops — base cases are separate clauses, not `if` checks inside a loop body.
- **No null/None errors.** Logic variables are either bound or unbound — there
  is no null pointer.
- **Automatic search.** You describe what you want; the system searches. No
  hand-written search algorithms to get wrong.

### Compositionality

Clausal Prolog predicates compose naturally. A predicate that describes one relation
can be used as a condition in another predicate's body. There is no need to
manage state, threading, or data flow between components:

```clausal
parent(ann, bob).
parent(ann, cat).

ancestor(X, Y) :-
    parent(X, Y).
ancestor(X, Y) :-
    parent(X, Z),
    ancestor(Z, Y).

same_lineage(A, B) :-
    ancestor(ROOT, A),
    ancestor(ROOT, B).

test("siblings share a lineage") :-
    same_lineage(bob, cat).
```

Each predicate is self-contained and can be understood, tested, and reused
independently.

---

## when to generate Clausal Prolog instead of Python

### Good candidates for Clausal Prolog

- **Rule-based logic**: business rules, access control policies, validation,
  eligibility checks — anything expressible as "X holds when Y and Z hold"
- **Constraint satisfaction**: scheduling, configuration, resource allocation,
  puzzle solving — describe the [constraints](constraints.md), let CLP(ℤ) search
- **Search problems**: pathfinding, graph traversal, planning — describe what
  constitutes a solution, not how to find one
- **Data validation and transformation**: describe the relation between input
  and valid output
- **Parsing and grammar**: [DCGs](dcg.md) describe grammars declaratively — the same
  grammar parses, generates, and validates
- **Knowledge representation**: facts and rules that encode domain knowledge

### when to stay in Python

- **Numerical computation**: numpy, scipy, pandas — use Python for heavy
  numerics, and call them through a `.seam` bridge module (`++()`)
- **I/O-heavy workflows**: file processing, network requests, database queries
  — use Python for side effects, Clausal Prolog for the logic
- **Performance-critical inner loops**: Python with C extensions will be faster
  for raw computation

The sweet spot is **hybrid**: use Clausal Prolog for the logic and rules, Python for
the computation and I/O.

---

## How to write good Clausal Prolog code

### Think relationally

Every predicate describes a relation between its arguments. Ask: "when does
this relation hold?" — not "What should this function do?"

```clausal
:- use_module(library(clpz)).

% Good: describes a relation
list_sorted([], []).
list_sorted([X], [X]).
list_sorted([X, Y|REST], SORTED) :-
    X #=< Y,
    list_sorted([Y|REST], SORTED_TAIL),
    SORTED = [X|SORTED_TAIL].

test("sorted") :-
    list_sorted([1, 2, 2, 5], [1, 2, 2, 5]).

test("unsorted fails") :-
    \+ list_sorted([2, 1], _).
```

### Name predicates after what they relate

Use nouns that describe the arguments, not verbs that describe an action:

| Avoid | Prefer |
|---|---|
| `get_length(List, N)` | `list_length(LIST, N)` |
| `compute_path(A, B, P)` | `path(A, B, P)` |
| `check_valid(X)` | `valid(X)` |
| `find_matches(Pattern, List, Matches)` | `list_matches(LIST, PATTERN, MATCHES)` |

### Read each clause as a statement

Before generating a clause, formulate it as a sentence:

- "The length of the empty list is 0."
- "The length of `[_|REST]` is N when the length of REST is N1 and N is
  N1 + 1."

If you can state it clearly in natural language, the clause will be correct.

### Use constraints for arithmetic

when the [arithmetic](arithmetic.md) direction isn't fixed, use [CLP(ℤ)](constraints.md) constraints instead of
eager ISO `is/2` evaluation:

```clausal
:- use_module(library(clpz)).

% Only works forward (N must be known):
double(N, D) :-
    D is N * 2.

% Works in all directions:
double_fd(N, D) :-
    D #= N * 2.

test("runs forwards") :-
    double(5, D),
    D == 10.

test("runs backwards") :-
    double_fd(N, 10),
    N == 5.
```

### Test with the most general query

After generating a predicate, verify it by asking: "Does `predicate(X, Y)`
with all fresh variables give meaningful answers?" If it does, the predicate
is truly relational.

---

## Code generation patterns

### Pattern: fact database

when the user provides structured data, encode it as facts:

```clausal
:- use_module(library(clpz)).

employee(alice, engineering, 95000).
employee(bob, marketing, 72000).
employee(carol, engineering, 105000).

department_employee(DEPT, NAME) :-
    employee(NAME, DEPT, _).

high_earner(NAME) :-
    employee(NAME, _, SALARY),
    SALARY #> 90000.

test("engineers") :-
    findall(N, department_employee(engineering, N), NS),
    NS == [alice, carol].

test("high earners") :-
    findall(N, high_earner(N), NS),
    NS == [alice, carol].
```

### Pattern: recursive relation

For problems over recursive structures (lists, trees, graphs):

```clausal
:- use_module(library(clpz)).

% Base clause: state when the relation trivially holds
tree_depth(leaf, 0).

% Recursive clause: state the relationship between the whole and its parts
tree_depth(node(LEFT, RIGHT), DEPTH) :-
    tree_depth(LEFT, D1),
    tree_depth(RIGHT, D2),
    max_(D1, D2, DMAX),
    DEPTH #= DMAX + 1.

test("depth 2") :-
    tree_depth(node(node(leaf, leaf), leaf), 2).
```

### Pattern: constraint model

For constraint satisfaction problems, separate the model from the search:

```clausal
:- use_module(library(clpz)).

% Model: describe what must hold
schedule([A, B, C]) :-
    in_domain([A, B, C], 1, 3),
    all_different([A, B, C]),
    A #< B.

% Search: how to find solutions (separate from the model)
solution(TASKS) :-
    schedule(TASKS),
    label(TASKS).

test("three slots") :-
    findall(T, solution(T), [[1, 2, 3], [1, 3, 2], [2, 3, 1]]).
```

### Pattern: bridge to [Python](python_integration.md)

For hybrid tasks, use `++()` for Python and predicates for logic. `++` is
seam syntax, so this is a `.seam` module; a `.clausal` module that needs the
result imports it (a module that runs Python is a *Python bridge*, listed
in `[tool.clausal] python_bridges` of `pyproject.toml`; see
[Python only through the seam](clausal_prolog.md#python-only-through-the-seam)):

```seam
# Python does the computation
word_frequency(TEXT, WORD, COUNT) <- (
    WORDS is ++TEXT.lower().split(),
    in_(WORD, WORDS),
    COUNT is ++WORDS.count(WORD)
)

# Clausal does the reasoning
most_common(TEXT, WORD) <- (
    word_frequency(TEXT, WORD, COUNT),
    not (word_frequency(TEXT, _, HIGHER) and HIGHER > COUNT)
)

test("most common word") <- (
    findall(W, most_common("the cat and the dog", W), WS),
    WS is ['the', 'the']
)
```

### Pattern: querying from Python

Put the Python that asks questions in a `.seam` file, and write
the goal in goal position with `--`. The module it queries (`staff` below)
can be a `.clausal` file. Answers come back as the engine's own
terms: an atom is a `str`, a compound term is a tuple (`('node', 'leaf',
'leaf')`), a string is `('$chars', text)`; `clausal.to_python` converts one
deeply.

```python
# queries.seam
-import_module(staff)

def high_earners():
    return [NAME for NAME in --staff.high_earner(NAME)]

def is_high_earner(name):
    if --staff.high_earner(++name):
        return True
    return False
```

`++expr` hands a Python value in. From a plain `.py` file, where `--` is not
available, use `solve(("high_earner", NAME := Var()), module=staff)`. See
[Python Integration](python_integration.md#goal-position-if-goal-for-in-goal).

### Rules that are easy to get wrong

In Clausal Prolog (`.clausal`):

- There is no cut. `!`, `->` (if-then and if-then-else) and `*->` are
  refused when the file loads. Use separate clauses with exclusive guards,
  `dif/2`, constraints, and `if_/3` from `library(reif)`
  ([reified if-then-else](reified_ite.md)). `\+`, `once/1` and `forall/2`
  work but are discouraged.
- `"text"` is a **string** (a character list), not an atom; write `text` or
  `'text'` for an atom. Atoms need no declaration.
- `=` unifies, `==` is identity (not arithmetic), and `is` evaluates.
  Arithmetic relations are CLP(ℤ): `X #= EXPR`, `#\=`, `#<`, `#=<`, …,
  after `:- use_module(library(clpz)).` Without that directive `#=` is a
  syntax error.
- A module is `:- module(Name, [p/1, q/2]).` and must end with
  `:- end_module(Name).`; import with `:- use_module(Mod, [p/1])` or
  `:- use_module(library(Lib), [...])`.
- `assertz`/`retract` need the predicate declared
  `:- dynamic(name/arity).`
- There is no lambda syntax: pass a named predicate to `maplist`, `foldl`
  and the other higher-order predicates.
- Python is not reachable from a `.clausal` goal except through a library
  facade or an imported `.seam` module. A `.clausal` module may not import
  a `.pl` module.
- Tests are `test("name") :- Goal.` clauses in the same file.
- Error terms are ISO `error(Formal, Context)`, in Scryer's form
  (`error(type_error(atom,1),atom_length/2)`); see [Exceptions](exceptions.md).

In the seam (`.seam`), when you do write one:

- `"text"` is a **string** (a character list), not an atom; write `'text'`
  for an atom. See [Atoms vs strings](syntax.md#atoms-vs-strings).
- A bare atom or functor must be declared (`-module`, `-private`,
  `-import_from`) or quoted (`'leaf'`).
- `#` starts a Python comment: write CLP(ℤ) as `==`, `!=`, `<`, `<=`
  (see [Operators](operators.md)).
- `X is Y` is unification. Arithmetic is `X == EXPR` (a constraint) or
  `eval_(EXPR, X)` (eager); see [Arithmetic](arithmetic.md).
- `assertz`/`retract` need the predicate declared `-dynamic(name/arity)`.
- There is no cut either.

---

## Key advantages for AI-generated code

1. **Declarative = less to get wrong.** You state what holds, not how to
   compute it. The system handles search, backtracking, and unification.

2. **Self-[testing](testing.md).** Tests are just queries. Generate the predicate and its
   tests in one pass.

3. **Compositional.** Each predicate is independent. You can generate
   predicates one at a time and compose them without worrying about shared
   state.

4. **Explainable.** Every clause can be read as an English sentence. The
   user can verify the logic without understanding execution details.

5. **Verifiable.** [Pure](purity.md) predicates have formal properties (monotonicity,
   commutativity) that can be checked mechanically.

---

*See also: [Clausal Prolog](clausal_prolog.md) — the `.clausal` rules and
how they differ from the seam.*

*See also: [Tutorial](tutorial.md) — learn the syntax.*

*See also: [Thinking Relationally](thinking_relationally.md) — the mental
model.*

*See also: [Predicate Index](builtins.md) — available builtins.*

*See also: [Python Integration](python_integration.md) — calling Python from
Clausal Prolog and vice versa.*
