# Tutorial

Welcome to Clausal Prolog — logic programming embedded in Python. This
tutorial introduces the core concepts: defining relations, querying them, and
understanding how unification connects goals to clauses. No Prolog experience
required.

!!! note "Clausal Prolog and other Prologs"

    This tutorial is based on material from [The Power of Prolog](https://www.metalevel.at/prolog).
    Clausal Prolog (`.clausal` files) uses ISO Prolog syntax, so most examples
    there read the same here. The main difference: Clausal Prolog is
    **cut-free** — `!`, `->` and `*->` are refused; use `dif/2`, `if_/3` and
    constraints instead (see [Clausal Prolog](clausal_prolog.md)). A module
    file must end with `:- end_module(Name).`.
    If you have existing ISO Prolog `.pl` files, see
    [Importing Prolog](importing_prolog.md).

---

## Your first .clausal file

Create a file called `hello.clausal`:

```prolog
:- module(hello, [greeting/1]).

greeting(hello).
greeting(hi).
greeting('hey there').

:- end_module(hello).
```

Each `greeting(...)` line is a **fact** — an unconditional statement that
something is true. Every clause ends with a full stop. The first line declares
a module named `hello` that exports `greeting/1` (the predicate `greeting`
with one argument); the last line closes it.

`hello`, `hi` and `'hey there'` are **atoms**, symbolic constants. An atom
that starts with a lower-case letter needs no quotes; any other spelling is
quoted with `'...'`.

Query it from Python. Next to `hello.clausal`, create `ask.seam`. A `.seam`
file is Python source that can also ask goals — the **seam**, the boundary
between Python and Clausal Prolog:

```python
# ask.seam
-import_from(hello, [greeting])
-private([hello])

if --greeting(hello):
    print("yes")

for X in --greeting(X):
    print(X)
```

and run it:

```bash
python -c "import clausal, ask"
```

(`import clausal` installs the import hook that loads `.clausal` and `.seam`
files as Python modules.)

`-import_from` imports `greeting/1` from `hello.clausal`. The seam is Python
syntax, so an atom used bare in it must be declared: `-private([hello])` does
that for `hello`. In the seam, variables are written in ALL-CAPS.

`--` marks a goal inside Python. After `if`, the goal is asked once:
`greeting(hello)` holds, so this prints `yes`. After `for ... in`, every
solution is produced in turn, and `X` comes back as an ordinary Python
variable: `hello`, `hi`, `hey there`.

From a plain `.py` file, where `--` is not available, the same questions go
through `solve`: a goal is a **cell** — a tuple of the predicate's name
followed by its arguments (a Python `str` is the atom of that spelling) — run
against the module you pass:

```python
from clausal import Var, solve
import hello

for trail in solve(("greeting", "hello"), module=hello):
    print("yes")

for trail in solve(("greeting", X := Var()), module=hello):
    print(X.value)
```

Read `X.value` inside the loop — the binding is undone before the next
solution. See
[Python Integration](python_integration.md#querying-from-python) for both
forms.

??? tip "Thinking relationally"

    In Clausal Prolog, every predicate defines a **relation** — it describes
    when something is true about its arguments. This is different from
    functions, which map inputs to outputs. A single relation can often be used
    in multiple directions: to compute, to verify, to generate. See
    [Thinking Relationally](thinking_relationally.md) for a deeper exploration
    of this idea.

---

## Facts and rules

Let's model a small family tree. Create `family.clausal`:

```prolog
:- module(family, [parent/2, grandparent/2]).

parent(alice, bob).
parent(alice, carol).
parent(bob, dave).
parent(bob, eve).

grandparent(Grandparent, Grandchild) :-
    parent(Grandparent, Middle),
    parent(Middle, Grandchild).

:- end_module(family).
```

The four `parent` clauses are **facts**: `parent(alice, bob)` means "alice is
a parent of bob".

The `grandparent` clause is a **rule**. Read it as: "Grandparent is a
grandparent of Grandchild if there exists some Middle such that Grandparent is
a parent of Middle and Middle is a parent of Grandchild."

`:-` means "is true if". Goals in the body are separated by **commas**, which
read as "and".

Query it from Python:

```python
# app.seam
-import_from(family, [grandparent])
-private([alice])

for GRANDCHILD in --grandparent(alice, GRANDCHILD):
    print(GRANDCHILD)
```

Result: `dave` then `eve` — both of alice's grandchildren.

### Multiple solutions and backtracking

Clausal Prolog finds all clauses whose heads unify with the goal — these
represent logical alternatives. If a condition in the body does not hold, the
engine explores the remaining alternatives.

`for X in --goal:` iterates every solution; `if --goal:` takes just the first
one, and its variables stay bound after the `if`. The plain-`.py`
equivalents are `solve(goal, module=…)` and `once(goal, module=…)`.

---

## Logic variables

Variables start with an **upper-case letter** or an underscore: `X`, `Parent`,
`Child`, `Result`, `Head`, `Tail`. Anything starting with a lower-case letter
is an atom.

```prolog
sibling(A, B) :-
    parent(Parent, A),
    parent(Parent, B),
    dif(A, B).
```

`A` and `B` are logic variables — they stand for any term at all. When the
engine searches for clauses whose heads unify with a goal, variables are bound
to make the terms identical: if `A` is unbound and unifies with `bob`, then
`A` becomes `bob` for the rest of that branch. `dif(A, B)` states that `A`
and `B` are different, so nobody is their own sibling.

The **anonymous variable** `_` unifies with anything and is never reported in
results:

```prolog
has_child(Person) :- parent(Person, _).
```

"Person has a child" — we don't care what the child's name is.

Added to `family.clausal` (and exported), these can be checked with tests —
see [Testing your code](#testing-your-code):

```prolog
test("dave and eve are siblings") :- sibling(dave, eve).
test("nobody is their own sibling", fail) :- sibling(dave, dave).
test("bob has a child") :- has_child(bob).
test("dave has no child", fail) :- has_child(dave).
```

### How unification works

Unification finds the most general way to make two terms identical. Both terms
can contain variables, and variables on **either side** can be bound. This
bidirectionality is what makes relations work in all directions. The goal
`X = Y` unifies `X` and `Y`.

When you query `parent(alice, Child)`, the engine searches for clauses whose
heads unify with the goal. The clause `parent(alice, bob)` unifies when
`Child` is bound to `bob`. No assignment, no mutation — each branch of the
search has its own consistent set of bindings.

---

## [Lists](lists.md)

Lists are written with square brackets: `[]` (empty), `[1, 2, 3]`, `[a, b]`.
(`a` is an atom, a symbolic constant; `"a"` is a string, text.)
The head/tail pattern uses a bar:

```prolog
first(Head, [Head|_]).

rest(Tail, [_|Tail]).
```

`[Head|Tail]` unifies with any non-empty list, binding `Head` to the first
element and `Tail` to the list of remaining elements.

### member/2 and append/3

These are built-in predicates. `member(X, List)` describes the membership
relation — it holds for each element of `List` in turn:

```prolog
contains_three(List) :- member(3, List).
```

`append(Prefix, Suffix, Whole)` relates three lists such that `Prefix`
concatenated with `Suffix` gives `Whole`. You can use it forwards (build a
list) or backwards (split one):

```prolog
last_element(Element, List) :- append(_, [Element], List).
```

### Describing list relations in clause heads

Clause heads can describe the structure of list arguments directly, which is
often cleaner than stating the structure as a separate condition in the body:

```prolog
list_sum([], 0).
list_sum([Head|Tail], Total) :-
    list_sum(Tail, Subtotal),
    Total #= Subtotal + Head.
```

The first clause states that the sum of the empty list is 0. The second states
that the sum of `[Head|Tail]` is `Total` when the sum of `Tail` is `Subtotal`
and `Total` equals `Subtotal + Head`.

```prolog
double_list([], []).
double_list([Head|Tail], [Doubled|Rest]) :-
    Doubled #= Head * 2,
    double_list(Tail, Rest).
```

Each clause describes a different case in which the relation holds. Clauses are
logical alternatives — the engine searches for those whose heads unify with
the goal.

`#=` is an arithmetic constraint from `library(clpz)`, so a module that uses
these predicates starts with `:- use_module(library(clpz)).` — more on this
in the next section.

---

## [Arithmetic](arithmetic.md)

Write integer arithmetic with [CLP(ℤ)](constraints.md) constraints from
`library(clpz)`. `#=` states that two expressions are equal:

```prolog
:- module(arith, [square/2, factorial/2]).
:- use_module(library(clpz)).

square(N, Sq) :- Sq #= N * N.

factorial(0, 1).
factorial(N, F) :-
    N #> 0,
    N1 #= N - 1,
    F #= N * F1,
    factorial(N1, F1).

test("square") :- square(7, 49).
test("factorial(5)") :- factorial(5, 120).

:- end_module(arith).
```

Supported operators include `+`, `-`, `*`, `//`, `mod`, `rem` and `^`.
[Operators](operators.md) has the full table.

A constraint works in all directions — even when variables are unbound:

```prolog
:- module(succ, [successor/2]).
:- use_module(library(clpz)).

successor(N, M) :- M #= N + 1.

test("forwards") :- successor(3, M), M == 4.
test("backwards") :- successor(N, 4), N == 3.

:- end_module(succ).
```

`=` is **unification**, not arithmetic: `X = 1 + 2` binds `X` to the term
`1 + 2`, while `X #= 1 + 2` binds it to `3`. ISO Prolog's `is/2` is also
available: `X is 1 + 2` evaluates the right-hand side, which must already be
known, so `successor(N, 4)` written with `is` would raise an instantiation
error instead of answering. For rationals and reals, see CLP(ℚ) and CLP(ℝ)
in the [constraints guide](constraints.md).

### Comparisons

The standard comparison operators work directly as goals:

```prolog
positive(N) :- N #> 0.

in_range(Low, High, N) :-
    N #>= Low,
    N #=< High.
```

The CLP(ℤ) comparisons are `#<`, `#>`, `#>=`, `#=<`, and `#=` and `#\=` for
equality and inequality. (The ISO comparisons `<`, `>`, `>=`, `=<`, `=:=` and
`=\=` also work, but need both sides known.)

### A worked example: fizzbuzz

```prolog
:- module(fizzbuzz, [fizzbuzz/2]).
:- use_module(library(clpz)).

fizzbuzz(N, fizzbuzz) :- N mod 15 #= 0.
fizzbuzz(N, fizz) :- N mod 3 #= 0, N mod 5 #\= 0.
fizzbuzz(N, buzz) :- N mod 5 #= 0, N mod 3 #\= 0.
fizzbuzz(N, N) :- N mod 3 #\= 0, N mod 5 #\= 0.

test("15 is fizzbuzz") :- fizzbuzz(15, fizzbuzz).
test("9 is fizz") :- fizzbuzz(9, fizz).
test("9 is only fizz", fail) :- fizzbuzz(9, 9).

:- end_module(fizzbuzz).
```

Each clause states exactly when it holds, so every number has one label.
Query it from a `.seam` file, passing each Python `n` in with `++`:

```python
# labels.seam
-import_from(fizzbuzz, [fizzbuzz])

def labels(upto):
    results = []
    for n in range(1, upto + 1):
        if --fizzbuzz(++n, LABEL):
            results.append(LABEL)
    return results
```

`labels(15)` is `[1, 2, 'fizz', 4, 'buzz', 'fizz', 7, 8, 'fizz', 'buzz', 11, 'fizz', 13, 14, 'fizzbuzz']`.

`++expr` evaluates a Python expression and passes its value into the goal. It
exists only in the seam: Clausal Prolog itself does not run Python. See
[Python Integration](python_integration.md) for the seam.

---

## Negation

`\+ Goal` is **negation as failure**: it succeeds if `Goal` has no solutions.

```prolog
safe_to_delete(File) :- \+ important(File).
```

### When to use it

Negation as failure is appropriate when you want to express "there is no evidence
that...". It works correctly when all the relevant facts are already known — the
classic **closed-world assumption**.

```prolog
bachelor(Person) :-
    male(Person),
    \+ married(Person).
```

If `married(bob)` is not in the database, `\+ married(bob)` succeeds.

### When not to use it

Avoid `\+ Goal` when the variables inside `Goal` are unbound. This query:

```text
?- \+ member(5, List).
```

fails, because `member(5, List)` succeeds by instantiating `List` to a list
that contains 5. Instead, make sure any variables in the negated goal are
already bound before the check:

```prolog
no_fives(List) :- \+ member(5, List).
```

is fine when `List` is passed in fully instantiated; it is not a generator of
lists that avoid 5.

For a "not equal" that stays correct on partially-instantiated terms, use
`dif/2` (see the [constraints guide](constraints.md)); for a condition that
chooses between two branches, use `if_/3` from `library(reif)` (see
[If-Then-Else](reified_ite.md)).

!!! note "Monotonicity"

    Negation as failure is inherently non-monotonic — binding a variable can
    cause a previously successful negation to fail. For monotonic alternatives
    that preserve [logical purity](purity.md), use `dif/2` for disequality and
    CLP(ℤ) constraints for arithmetic.

---

## Testing your code

Clausal Prolog has a lightweight convention for inline tests: `test/1` clauses
whose goal must succeed, and `test/2` with the option `fail` for a goal that
must have no solution. Create `mymodule.clausal`:

```prolog
:- module(mymodule, [list_sum/2]).
:- use_module(library(clpz)).

list_sum([], 0).
list_sum([Head|Tail], Total) :-
    list_sum(Tail, Subtotal),
    Total #= Subtotal + Head.

test("sum [1,2,3,4] = 10") :-
    list_sum([1, 2, 3, 4], Total),
    Total == 10.

test("sum [] = 0") :-
    list_sum([], 0).

test("[1,2] does not sum to 4", fail) :-
    list_sum([1, 2], 4).

:- end_module(mymodule).
```

Run one file's tests with the standalone runner, or the whole suite with
pytest:

```bash
python -m clausal.testing -v mymodule.clausal
python -m pytest
```

The pytest plugin collects the `test` clauses of `.seam`, `.clausal` and `.pl`
files automatically.

A Python test can also run one `test/1` clause by its description. The
description `"sum [1,2,3,4] = 10"` is a **string**, so from a `.py` file build
it with `chars` (a plain Python `str` would be the atom of that spelling, a
different term):

```python
from clausal import once
from clausal.logic.cells import chars
import mymodule

def test_sum():
    assert once(("test", chars("sum [1,2,3,4] = 10")), module=mymodule) is not None
```

A wrapper that runs more than a couple of goals should build them through one
helper function of its own rather than repeating the tuple and the `module=`
at every call site — see
[Driving Clausal from a test suite](python_integration.md#driving-clausal-from-a-test-suite).

See [Testing](testing.md) for the full testing guide, including how to use fixtures
and parametrize.

---

## A complete example: graph reachability

Let's put it all together with a classic logic programming problem — finding reachable
nodes in a directed graph. Create `graph.clausal`:

```prolog
:- module(graph, [reachable/2]).

edge(a, b).
edge(b, c).
edge(c, d).
edge(b, d).

reachable(Source, Dest) :- edge(Source, Dest).
reachable(Source, Dest) :-
    edge(Source, Mid),
    reachable(Mid, Dest).

test("a reaches d") :- reachable(a, d).
test("d reaches nothing", fail) :- reachable(d, _).

:- end_module(graph).
```

The first clause states that Source and Dest are reachable if there is a direct
edge between them. The second states that they are reachable if there is an edge
from Source to some Mid, and Mid and Dest are reachable. These two clauses are
logical alternatives — together they define the complete reachability relation.

Query it from a `.seam` file:

```python
# reach.seam
-import_from(graph, [reachable])
-private([a])

print(sorted({DEST for DEST in --reachable(a, DEST)}))
# ['b', 'c', 'd']
```

or from a plain `.py` file:

```python
from clausal import Var, solve
import graph

results = set()
for trail in solve(("reachable", "a", DEST := Var()), module=graph):
    results.add(DEST.value)
print(sorted(results))
# ['b', 'c', 'd']
```

(`b → d` and `b → c → d` both reach `d`, so `d` is found twice; the set keeps
one.)

For graphs with cycles this search would not terminate. Add the directive
`:- table(reachable/2).` to enable tabling (memoised search) — see
[Tabling](tabling.md).

---

## Where to go next

- **[Clausal Prolog](clausal_prolog.md)** — the `.clausal` surface and its
  rules
- **[Thinking Relationally](thinking_relationally.md)** — the most important
  idea in logic programming: predicates as relations, not functions
- **[Purity and Monotonicity](purity.md)** — why pure code has better
  properties and how to write it
- **[Constraints](constraints.md)** — `dif/2` for structural inequality; CLP(ℤ) for
  integer constraint solving (N-queens, Sudoku, SEND+MORE=MONEY)
- **[DCGs](dcg.md)** — Definite Clause Grammars (`-->`) for parsing and string
  generation
- **[Python Integration](python_integration.md)** — querying from Python and
  the seam
- **[Examples](examples.md)** — worked examples: map colouring, Sudoku, graph
  algorithms, and more
- **[Predicate index](builtins.md)** — every built-in predicate with examples
