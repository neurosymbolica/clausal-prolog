# Clausal for Python Programmers

You know Python. You know functions, loops, classes, list comprehensions. This
page bridges that knowledge to logic programming — what's different, what maps
to what, and why you'd want to use it.

---

## The thirty-second version

In Python, you write **functions** that compute results from inputs. In
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

**Data types are mostly Python.** Numbers are Python numbers. [Lists](lists.md) are Python
lists. [Dicts](dicts_sets.md) are Python dicts. Declared atoms (symbolic constants) are
just interned Python `str`s — no wrapper class. A Python `str` crossing into
Clausal is always read as an atom; a logic *string* (the `"…"` chars-model
kind) is a related but distinct, list-shaped value — see
[Atoms are symbolic constants](#atoms-are-symbolic-constants) below.

**The runtime is Python.** Clausal runs on the Python VM. You can call any
Python library from within a logic predicate using `++()`, and call logic
predicates from Python with `solve(("my_predicate", X), module=my_module)` —
a goal is a tuple, run against the module that defines it.

**Import works as expected.** `import my_module` loads
`my_module.clausal` through Python's [import system](import.md). Bytecode is [cached](caching.md) in
`__pycache__` like any other Python module. The module's attribute for a
predicate is that predicate's handle, used to name it — not a function to
call.

---

## What's different

### Variables are unknowns, not containers

In Python, a variable holds a value:

```python
x = 5       # x is now 5
x = x + 1   # x is now 6
```

In Clausal, a logic variable is an **unknown** — it starts unbound and gets
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
from clausal import Var, solve
import my_module

for trail in solve(("color", X := Var()), module=my_module):
    print(X.value)  # red, green, blue
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

In logic programming, an **atom** is a symbolic constant — like an enum
value. An atom **is** the interned Python `str`: declaring one in `-private`
or `-module` doesn't wrap it in a class, it just interns the spelling:

```clausal
-private([red, green, blue, color(C)])

color(red),
color(green),
color(blue),
```

From the Python side, `red`, `green`, and `blue` are plain `str` objects.
Compare them with `==` — because atoms are interned, `is` happens to agree
too, but `==` is the test to write:

```python
# From Python:
from my_module import red, blue
from clausal.logic.atoms import mint, is_atom, spelling

red                  # 'red'
red == mint("red")   # True
red == blue          # False
is_atom(red)         # True
spelling(red)        # 'red'
```

**Every Python `str` is an atom** — there is no wrapper to opt in to.
`is_atom("ok")` is `True` for any Python `str`, declared or not; a Python `str`
crossing into Clausal (a `to_term` argument, a `++` result, a dict key) is
always read as the atom of that spelling. `mint` interns and hands back that
same value:

```python
from clausal.logic.atoms import mint, is_atom

ok = mint("ok")     # 'ok'
is_atom(ok)          # True
is_atom("ok")         # True — a raw str IS an atom
ok == "ok"             # True — the same value
```

If you specifically want a zero-arity `PredicateMeta` **class** — a 0-arity
predicate *value*, a different and rarer thing from an atom — that is
`make_predicate("ok", [])`. The class and the atom are disjoint kinds now
(no class is an atom), so a helper that used to answer either question no
longer does:

| Helper | Question |
|---|---|
| `clausal.logic.atoms.is_atom(x)` | Is this the **atom term** — an interned `str`? |
| `clausal.logic.predicate.is_zero_field_class(x)` | Is this a zero-field `PredicateMeta` **class**? |
| `clausal.logic.predicate.is_atom_value(x)` | The same question as `atoms.is_atom` — no class is an atom value |

`predicate.is_atom` is a **deprecated alias** for `is_zero_field_class` (the
class test, not the atom test) — import `is_zero_field_class` if you mean
the class and `clausal.logic.atoms.is_atom` if you mean the atom.

**Strings are the other kind — a list, not a bare `str`.** A `"hello"`
literal is a string only under [`-double_quotes(chars)`](directives.md#-double_quotes)
— today's default still reads it as the atom `hello` — and a string is the
list of its character atoms: internally a compact carrier around the text,
not literally a bare `str`. Atoms and strings never unify: under
`-double_quotes(chars)`, `atom(hello)` holds for the bare atom but
`atom("hello")` fails for the string. Compare atoms with `==` (interning
makes `is` agree, but `==` is the test); a string also compares — and
unifies — by value. Use atoms for symbolic constants (colours, states,
tags); use strings for text data.

| Type check | What it tests |
|---|---|
| `atom(X)` | An atom — the interned Python `str` |
| `string(X)` / `is_str(X)` | A string (a character sequence, not a bare `str`) |
| `atomic(X)` | An atom or a number — **not** a string, which is a list |
| `callable_(X)` | An atom or a compound term — **not** a string |

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

test("squares") <- (
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
In Python, you'd reach for a solver library or write custom search. In
Clausal, you describe the constraints and let CLP(ℤ) search:

```clausal
-import_from(clpfd, [all_different, labeling]),

send_more_money([S, E, N, D, M, O, R, Y]) <- (
    [S, E, N, D, M, O, R, Y] ins 0..9,
    all_different([S, E, N, D, M, O, R, Y]),
    S != 0, M != 0,
                1000*S + 100*E + 10*N + D
              + 1000*M + 100*O + 10*R + E
    #= 10000*M + 1000*O + 100*N + 10*E + Y,
    labeling([leftmost], [S, E, N, D, M, O, R, Y])
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
