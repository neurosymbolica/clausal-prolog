# A compound term is a tuple

**What Python code that reads engine terms needs to know.**

A compound term is a **cell**: the functor-first tuple `(name, *args)`.
An atom is a Python `str`, and a string is the carrier `('$chars', text)`
(see [An atom is a string](atoms-are-strings.md)).

| Clausal Prolog source | Python value |
|---|---|
| `point(1, 2)` | `('point', 1, 2)` |
| `edge(a, b)` | `('edge', 'a', 'b')` |
| `f("text")` | `('f', ('$chars', 'text'))` |
| `[1, g(x)]` | `[1, ('g', 'x')]` |

There is no compound class. `Compound` and the keyword-term class `KWTerm`
were deleted, with `compound_as_cell`, `list_to_cons`, `cons_to_list` and
`extend/3`; a predicate is no longer a Python class either (`PredicateMeta`
and `make_predicate` are gone). A keyword-argument term, `point(x=1, y=2)`, is
a load-time `SyntaxError`: build terms positionally.

## Reading and building one

**Positions, not attributes.** `clausal` exports three helpers:

```python
from clausal import cell_functor, cell_args, make_cell

t = make_cell("point", 1, 2)    # ('point', 1, 2)
cell_functor(t)                 # 'point'
cell_args(t)                    # (1, 2)
```

`cell_functor` and `cell_args` read the slots raw and do not check the shape,
so test the shape first. A compound is a tuple of two or more elements that
is not a string carrier:

```python
from clausal.logic.cells import is_chars

def is_compound(t):
    return type(t) is tuple and len(t) >= 2 and not is_chars(t)
```

To turn a whole term into plain Python values instead — every atom and
string to its text, every cell to a tuple of converted elements — call
`clausal.to_python(term)`. In a `.seam` file, compare an answer against a
term written with `--`: `if V == --point(1, 2):`. See
[Python Integration](python_integration.md).

An error term is a cell too: `error(type_error(atom, 1), atom_length/2)` is
`('error', ('type_error', 'atom', 1), ('/', 'atom_length', 2))`, read with the
same helpers (see [Exceptions](exceptions.md)).

## Three things that bite

1. **A cell is a tuple, so anything that treats a tuple structurally
   catches terms.** `isinstance(x, tuple)`, `len(x) == 2`, `a, b = x` — a
   generic tuple branch placed ahead of a specific one will swallow a term.
   Put the specific branch first.
2. **`getattr(term, "field", default)` answers the DEFAULT.** It does not
   raise. The caller proceeds with a wrong-but-plausible value and nothing
   reports it. Read positions, or fail loudly.
3. **The 1-tuple `('x',)` is reserved.** It is not an atom, not a compound,
   and must not be built. A type test that sits in a dispatch chain should
   answer False for it rather than raise.

## Predicates are not terms

A module attribute for a predicate is the predicate's **handle**, a `str`, so
`m.pred(X)` is `TypeError: 'str' object is not callable`. Query with `--pred(X)`
in a `.seam` file, or run a plain cell against the module with
`solve(("pred", X), module=m)` — see
[Querying from Python](python_integration.md#querying-from-python).
