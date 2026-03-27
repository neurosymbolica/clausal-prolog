# Clausal for Python Programmers

You know Python. You know functions, loops, classes, list comprehensions. This
page bridges that knowledge to logic programming — what's different, what maps
to what, and why you'd want to use it.

---

## The thirty-second version

in_ Python, you write **functions** that compute results from inputs. in_
Clausal, you write **[relations](thinking_relationally.md)** that describe when something is true about
their arguments. A relation has no fixed inputs or outputs — the same
definition can compute, verify, generate, and enumerate.

```clausal
# A relation between a list, a prefix, and a suffix
append([], SUFFIX, SUFFIX),
append([HEAD, *TAIL], SUFFIX, [HEAD, *REST]) <- (
    append(TAIL, SUFFIX, REST)
)
```

This single definition can concatenate two lists, split a list into all
possible prefix/suffix pairs, verify that three lists are related, or generate
completions from partial information. No separate functions needed.

---

## What stays the same

**The syntax is Python.** Every `.clausal` file is valid Python syntax — no
new parser, no foreign notation. Your editor's syntax highlighting, linting,
and autocompletion work out of the box.

**Data types are Python.** Numbers are Python numbers. [Lists](lists.md) are Python
lists. [Dicts](dicts_sets.md) are Python dicts. Strings remain strings. Declared atoms
(symbolic constants) are lightweight classes with identity semantics.
There is no marshalling, no conversion, no foreign data model.

**The runtime is Python.** Clausal runs on the Python VM. You can call any
Python library from within a logic predicate using `++()`, and call logic
predicates from Python using `clausal.query()`.

**Import works as expected.** `from my_module import my_predicate` loads
`my_module.clausal` through Python's [import system](import.md). Bytecode is [cached](caching.md) in
`__pycache__` like any other Python module.

---

## What's different

### Variables are unknowns, not containers

in_ Python, a variable holds a value:

```python
x = 5       # x is now 5
x = x + 1   # x is now 6
```

in_ Clausal, a logic variable is an **unknown** — it starts unbound and gets
bound through unification. once bound, it cannot be reassigned (within that
branch of search). Logic variables are written in ALLCAPS:

```clausal
# X is unbound; unification with "hello" binds it
greeting(X) <- (X is "hello")
```

This is closer to variables in algebra than variables in Python: `X` stands
for some value, and the system finds what that value must be.

### No return values — relations hold or don't

A Python function returns a value. A Clausal predicate either **holds** (is
true for the given arguments) or **doesn't hold**. Instead of returning
results, you add an argument:

```python
# Python: function returns a value
def square(n):
    return n * n
```

```clausal
# Clausal: relation holds between n and its square
square(N, SQ) <- (SQ == N * N)
```

### Multiple answers via backtracking

A Python function produces one result. A Clausal predicate can produce
**multiple answers** by having multiple clauses or through nondeterministic
search:

```clausal
color(red),
color(green),
color(blue),
```

```python
# From Python, iterate over all answers:
from my_module import color
for solution in clausal.query(color(X)):
    print(solution[X])  # red, green, blue
```

This replaces explicit loops and generators. Instead of writing code that
searches, you describe what you're looking for and let the system search.

### Pattern matching is bidirectional unification

Python 3.10+ has `match` statements, but they are one-directional: you match a
value against patterns. Clausal's unification is bidirectional — variables on
**both sides** can be bound:

```clausal
# Both HEAD and TAIL are bound by unifying with the list
first_and_rest([HEAD, *TAIL], HEAD, TAIL),
```

This bidirectionality is what makes relations work in all directions.

### Atoms are symbolic constants

in_ logic programming, an **atom** is a symbolic constant — like an enum value
with identity. when you declare atoms in `-private` or `-module`, Clausal
creates zero-arity classes:

```clausal
-private([red, green, blue, Color(C)])

Color(red),
Color(green),
Color(blue),
```

From the Python side, `red`, `green`, and `blue` are class objects (not
strings). They have identity: `red is red` and `red is not blue`. Calling
them returns themselves: `red() is red`.

```python
# From Python:
from my_module import red, green, Color
red is red          # True — identity, not equality
red() is red        # True — zero-arity call returns the class itself
isinstance(red, type)  # True — it's a class
```

You can also create atoms dynamically:

```python
from clausal.logic.predicate import make_atom, is_atom

ok = make_atom("ok")
err = make_atom("err")
is_atom(ok)   # True
ok() is ok    # True
```

**Strings still work as data.** String literals like `"hello"` flow through
unification as-is. The distinction is: declared atoms have identity (checked
with `is`), while strings have value equality (checked with `==`). Use atoms
for symbolic constants (colors, states, tags); use strings for text data.

| Type check | What it tests |
|---|---|
| `atom(X)` | Declared atom (zero-arity class) |
| `is_str(X)` | Python string |
| `callable_(X)` | Atom, string, or compound term |

---

## Mapping Python patterns to Clausal

### For-loops become recursive relations

```python
# Python: loop over a list
def sum_list(lst):
    total = 0
    for x in lst:
        total += x
    return total
```

```clausal
# Clausal: relation between a list and its sum
list_sum([], 0),
list_sum([HEAD, *TAIL], TOTAL) <- (
    list_sum(TAIL, SUBTOTAL),
    TOTAL == SUBTOTAL + HEAD
)
```

Read it declaratively: "The sum of the empty list is 0. The sum of
[HEAD, *TAIL] is TOTAL when the sum of TAIL is SUBTOTAL and TOTAL is
SUBTOTAL + HEAD."

### If/else becomes multiple clauses

```python
# Python
def classify(n):
    if n > 0: return "positive"
    elif n == 0: return "zero"
    else: return "negative"
```

```clausal
# Clausal: three clauses, three cases
classify(N, "positive") <- (N > 0)
classify(0, "zero"),
classify(N, "negative") <- (N < 0)
```

Each clause is a logical alternative — a separate condition under which the
relation holds.

### List comprehensions become search with [meta-predicates](meta_predicates.md)

```python
# Python: filter and transform
squares_of_evens = [x**2 for x in range(10) if x % 2 == 0]
```

```clausal
# Clausal: describe the relation, collect with findall
square_of_even(N, SQ) <- (
    between(0, 9, N),
    N % 2 == 0,
    SQ == N * N
)

Test("squares") <- (
    findall(SQ, square_of_even(_, SQ), SQUARES),
    SQUARES == [0, 4, 16, 36, 64]
)
```

### Dictionaries become facts

```python
# Python: dictionary lookup
capitals = {"france": "paris", "germany": "berlin", "japan": "tokyo"}
```

```clausal
# Clausal: facts that can be queried in any direction
capital("france", "paris"),
capital("germany", "berlin"),
capital("japan", "tokyo"),
```

The Clausal version can be queried both ways: "What is the capital of France?"
and "Which country has Paris as its capital?"

---

## Why bother?

### Constraint solving for free

Need to solve a Sudoku, schedule a timetable, or find valid configurations?
in_ Python, you'd reach for a solver library or write custom search. in_
Clausal, you describe the constraints and let CLP(ℤ) search:

```clausal
-import_from(clpfd, [all_different, Labeling]),

send_more_money([S, E, N, D, M, O, R, Y]) <- (
    [S, E, N, D, M, O, R, Y] ins 0..9,
    all_different([S, E, N, D, M, O, R, Y]),
    S != 0, M != 0,
                1000*S + 100*E + 10*N + D
              + 1000*M + 100*O + 10*R + E
    #= 10000*M + 1000*O + 100*N + 10*E + Y,
    Labeling([leftmost], [S, E, N, D, M, O, R, Y])
)
```

### Parsing with grammars

[DCGs](dcg.md) (Definite Clause Grammars) let you describe grammars declaratively —
and the same grammar can parse, generate, and validate:

```clausal
greeting >> [hello], name,
name >> [world],
name >> [clausal],
```

### Transparent integration with Python

You never leave the Python ecosystem. Call pandas, numpy, scikit-learn, or
any Python library from within your logic predicates:

```clausal
dataframe_mean(DF, COL, MEAN) <- (
    MEAN is ++DF[COL].mean()
)
```

---

## Getting started

1. Install: `pip install clausal`
2. Read the [Tutorial](tutorial.md) — it builds from simple facts to
   recursive relations
3. Read [Thinking Relationally](thinking_relationally.md) — the mental shift
   that makes everything click
4. Browse the [Predicate Index](builtins.md) for available builtins
5. Try the [Constraints](constraints.md) for your first "wow" moment

---

*See also: [Tutorial](tutorial.md) — learn Clausal step by step.*

*See also: [Python Integration](python_integration.md) — the `++()` escape
and query API.*

*See also: [Thinking Relationally](thinking_relationally.md) — the mindset
behind logic programming.*
