# An atom is a string

**Landed 2026-09-18. What Python code that reads engine terms must know.**

This is the migration note for code written before the change. For the
current rules as a whole, see [Python Integration](python_integration.md#crossing-the-boundary-atoms-and-strings)
and [Terms are tuples](terms-are-tuples.md).

## The change is a SWAP, in both directions

|                    | before        | after                 |
|--------------------|---------------|-----------------------|
| an **atom**        | `('x',)`      | `'x'` — a plain `str` |
| a **string**       | `'some text'` | `('$chars', 'some text')` |

They exchanged representations. `('x',)` is now RESERVED and is not an atom.

```python
from clausal.logic.atoms import is_atom, mint
from clausal.logic.cells import chars

mint("some_name")   # -> 'some_name'                 is_atom -> True
chars("some text")  # -> ('$chars', 'some text')     is_atom -> False
```

## THE HAZARD THAT DOES NOT RAISE

**`isinstance(value, str)` did not stop working. It inverted.**

|                          | before  | after  |
|--------------------------|---------|--------|
| `isinstance(atom, str)`  | False   | **True**  |
| `isinstance(string, str)`| True    | **False** |

It asked "is this a STRING?" and it now asks "is this an ATOM?". It does not
raise, it does not return empty, it answers a different question — correctly,
for the other question. **A test that only checks final answers cannot see
this**, which is why it is first in this document rather than last.

Every pre-flip `isinstance(v, str)` over a value that came out of the engine is
a site to READ, not to rewrite mechanically: whether it meant "string" or
"atom" is a question about that caller's intent, and only the caller knows.

## Three failure shapes, in the order they are easy to miss

1. **A 1-tuple atom test.** `isinstance(v, tuple) and len(v) == 1` answers
   False for every atom now. Where it GUARDS a parse it raises; where it
   FILTERS inside a collector the walk silently returns EMPTY — a correct-looking
   answer with its citations, provenance or atom list quietly gone.
2. **A string reaching code that expects `str`.** A string is a 2-tuple now, so
   it lands in dict keys, `sorted()` and `set()` operations as a tuple. Surfaces
   as `TypeError: '<' not supported between instances of 'tuple' and 'str'`, or
   as two key spaces that never meet.
3. **The inversion above.** Silent, and not findable from final answers alone.

Shapes 1 and 2 are mechanical once found. Shape 3 is a read per site.

## What to write instead

```python
from clausal.logic.atoms import is_atom, spelling      # atom test, atom -> text
from clausal.logic.cells import is_chars, chars_text   # string test, string -> text
from clausal import to_python                          # a whole term -> Python values
```

`to_python` converts deeply: an atom and a string both become their text, a
compound becomes a tuple of converted elements. Use it where you want Python
values and no longer care which kind of text a value was.

Prefer these to a local copy. If a local helper is unavoidable — an independent
reference implementation, say — spell it **`type(value) is str`**, which is the
engine's own definition verbatim. A helper that is merely *equivalent*
(`isinstance`, which also matches `str` subclasses) drifts from the engine the
first time either side changes.

## Checking a body you did not write

```python
is_atom(v)      # an atom
is_chars(v)     # a string
type(v) is tuple and len(v) == 1     # RESERVED — not an atom, not a string
```

`isinstance(v, atom)` with `clausal.logic.atoms.atom` — the 2026-09-21
boundary class, deprecated 2026-09-27 and removed in 2.0 — is `False` for
every value the engine hands out now; replace it with `is_atom(v)`.
`tools/atom_class_census/census.py` finds those sites (see
`docs/python_integration.md`).

And grep your own tree for the three shapes above before trusting a green run:
an answers-only check cannot see shape 3, and it sees shape 1 only where the
code happened to validate instead of filter.

## See also

* [Strict atoms migration](strict-atoms-migration.md) — how a bare name becomes a declared atom.
* [Terms are tuples](terms-are-tuples.md) — compound terms as functor-first tuples.
* [Python Integration](python_integration.md) — the `--`/`++` seams and the converters.
