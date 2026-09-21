# The Python boundary: `Atom` out, text in

**RULED by the operator 2026-09-21. NOT IMPLEMENTED — this is the spec, not a
description of the engine.**

## The ruling

| | `--` (out, to Python) | `++` (in, to a term) |
|---|---|---|
| **atom** | `Atom('x')` — a `str` SUBCLASS | an `Atom` becomes the atom |
| **string** | `'text'` — a plain Python `str` | a plain `str` becomes the string |

In clausal source, quote style discriminates — `atom` and `'quoted atom'` are
atoms, `"text"` is a string. Python has one string form, so the `++` direction
cannot discriminate lexically and discriminates by TYPE instead. `Atom` is the
missing lexical form.

## Why

**No term space in hand-written source.** The seam exists so that code inside
Python can be written as Prolog, and the internal representation has already
changed several times and will change again. Everything going in is behind
`--(...)`; outputs are tested the same way — `if output == --(pattern)`, which
already works today. A boundary that hands out the internal encoding invites
exactly the hand-rolled shape tests that make the next representation change a
migration.

That is not hypothetical. The 2026-09-18 atoms-as-str flip cost a downstream
sweep several days, and every one of its three failure classes came from code
inspecting terms by hand rather than through the seam. Under this ruling all
three become impossible rather than merely discouraged:

* a pre-flip 1-tuple shape test — there is no shape to test;
* a string reaching `sorted`/`set`/dict-key code as a tuple — a string is a
  plain `str` at the boundary and behaves;
* `isinstance(v, str)` silently changing which question it answers — it stays
  True for both, and the question "is this an atom" is `isinstance(v, Atom)`,
  which has one meaning and always did.

## `Atom`

```python
class Atom(str):
    """An atom at the Python boundary. Text-shaped, but never equal to text."""
    __slots__ = ()
    _interned = {}

    def __new__(cls, spelling):
        got = cls._interned.get(spelling)
        if got is None:
            got = cls._interned[spelling] = str.__new__(cls, spelling)
        return got

    def __eq__(self, other):
        return isinstance(other, Atom) and str.__eq__(self, other)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return str.__hash__(self)
```

Acceptance test, as the operator wrote it:

```python
def test_atom_class(Atom):
    assert Atom('a') == Atom('a')
    assert Atom('a') != 'a'
    assert 'a' != Atom('a')
```

Measured properties: interned, so `Atom('a') is Atom('a')`; distinct dict keys
and set members from the same text; text-shaped for `.upper()`, `join`,
f-strings and `sorted`; `isinstance(x, str)` True; `type(x) is str` False.

### Two traps, both load-bearing

1. **`return str == atom` recurses forever.** `==` re-enters `Atom.__eq__`.
   Compare through `str.__eq__(self, other)`.
2. **`__eq__` alone is NOT enough when subclassing `str`, and the failure is
   one-sided.** `str` defines its own `__ne__`, which `Atom` inherits without
   overriding — so the reflected-operand priority rule does not fire, and
   `'a' != Atom('a')` runs `str.__ne__` and answers False while
   `Atom('a') != 'a'` answers True. `__ne__` must be defined explicitly.

`__eq__` returns `False` rather than `NotImplemented` deliberately:
`NotImplemented` hands the comparison back to `str.__eq__`, which answers True.

## THE LEAK RULE

`type(term) is str` IS the engine's `is_atom`, and it is False for an `Atom`.
So:

> **`Atom` exists only at the boundary. `++` normalises it to a plain `str` on
> the way in, and no term ever holds one.**

An `Atom` that reaches term space is invisible to `is_atom` and is a fourth
failure class of the same family as the three above. This wants a test that
asserts no `Atom` survives into a term, not a comment saying it must not.

## Implementation notes

The conversion registry (`clausal/logic/python_terms.py`, ruled 2026-09-15)
is the hook: `TO_TERM` gains `str` (-> the string) and `Atom` (-> the atom).
Keyed by EXACT type, which this design needs anyway — `Atom` is a `str`
subclass, and an `isinstance` walk would match it as `str` and lose it.

`FROM_TERM` is keyed by FUNCTOR, which covers the string carrier but not an
atom: an atom has no functor, it is the bare value. The `--` direction
therefore needs an atom case outside the functor table.

## Not ruled here

* the explicit constructor's spelling — `atom('x')` vs `Atom('x')`;
* whether `sorted()` mixing `Atom` and `str` by text is the wanted order (it
  is what falls out; it means a sort cannot be relied on to separate them);
* migration sequencing downstream, which needs the count of sites currently
  using a string as a dict key or set member.
