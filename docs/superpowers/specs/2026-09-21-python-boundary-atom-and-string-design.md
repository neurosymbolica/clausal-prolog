# The Python boundary: `atom` out, text in

**RULED by the operator 2026-09-21. NOT IMPLEMENTED — this is the spec, not a
description of the engine.**

> **SUPERSEDED** by the dumb seam (2026-09-26): values cross in the engine's
> raw form, an atom is the plain `str`. The `atom` class this spec introduced
> is DEPRECATED as of 2026-09-27 (step (f)) and removed in 2.0 — see
> `docs/python_integration.md`, "Deprecated: the `atom` boundary class".

## The ruling

| | `--` (out, to Python) | `++` (in, to a term) |
|---|---|---|
| **atom** | `atom('x')` — a `str` SUBCLASS, advisory | an `atom` becomes the atom |
| **string** | `'text'` — a plain Python `str` | a plain `str` becomes the string |

In clausal source, quote style discriminates — `atom` and `'quoted atom'` are
atoms, `"text"` is a string. Python has one string form, so the `++` direction
cannot discriminate lexically and discriminates by TYPE instead. `atom` is the
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
  True for both, and the question "is this an atom" is `isinstance(v, atom)`,
  which has one meaning and always did.

## `atom` — ADVISORY (amended 2026-09-21, after the strict form was costed)

Lower case: a Python class at the same level as `str`.

```python
class atom(str):
    """An atom at the Python boundary: a str that is TAGGED as an atom."""
    __slots__ = ()
    _interned: dict = {}

    def __new__(cls, spelling):
        got = cls._interned.get(spelling)
        if got is None:
            got = cls._interned[spelling] = str.__new__(cls, spelling)
        return got
```

**`atom('a') == 'a'` is TRUE.** The discriminator is the TYPE:

```python
isinstance(value, atom)     # an atom
type(value) is str          # text
```

### Why advisory, and why the strict form was rejected

`++` reads the TYPE, so equality is not the mechanism and a strict `__eq__`
buys nothing for the round trip. It only costs: **1007 `==`/`!=` comparisons
against plain string literals, across ALL 82 downstream bodies**, every
atom-side one of which would silently flip True to False. Introducing a
comparison that quietly changes its answer is the exact defect class this
boundary exists to remove.

The strict form also carried two traps that no longer exist: `__eq__` had to
compare through `str.__eq__` or recurse to the stack limit, and `__ne__` had to
be defined explicitly because `str` supplies its own — an omission that failed
ONE-SIDED (`atom('a') != 'a'` True while `'a' != atom('a')` False). Both are
gone with the overrides. Recorded here because a future reader may reach for
strict equality again, and these are what it costs.

### The tag is a hint, and it is fragile

It survives being STORED and MOVED — dict value, dict key, list, tuple,
`sorted`, a function argument — and is LOST by anything that builds a new
string: `.upper()`, a slice, an f-string, `''.join`, `+`, `str()`.

**That is a property of subclassing `str`, not a cost of being advisory**: a
strict class loses the tag in exactly the same places. Derive a new spelling
and you have text; tag it again with `atom(...)` if you meant an atom.

### One consequence to be deliberate about

An atom and its text are **one** dict key, not two. That follows from advisory
equality and inherited hashing, and it is wanted: a split key space is what
made a downstream failure silent in the first place.

## THE LEAK RULE

`type(term) is str` IS the engine's `is_atom`, and it is False for an `atom`.
So:

> **`atom` exists only at the boundary. `++` normalises it to a plain `str` on
> the way in, and no term ever holds one.**

An `atom` that reaches term space is invisible to `is_atom` and is a fourth
failure class of the same family as the three above. This wants a test that
asserts no `atom` survives into a term, not a comment saying it must not.

## Implementation notes

The conversion registry (`clausal/logic/python_terms.py`, ruled 2026-09-15)
is the hook: `TO_TERM` gains `str` (-> the string) and `atom` (-> the atom).
Keyed by EXACT type, which this design needs anyway — `atom` is a `str`
subclass, and an `isinstance` walk would match it as `str` and lose it.

`FROM_TERM` is keyed by FUNCTOR, which covers the string carrier but not an
atom: an atom has no functor, it is the bare value. The `--` direction
therefore needs an atom case outside the functor table.

## Not ruled here

* whether `sorted()` mixing `atom` and `str` by text is the wanted order (it
  is what falls out; it means a sort cannot be relied on to separate them);
* migration sequencing downstream, which needs the count of sites currently
  using a string as a dict key or set member.

## SUPERSEDED 2026-09-26 — the dumb seam (operator GO)

Kept as history. The operator ruled the seam "dumb": **terms come out in
their internal form**, and are converted explicitly or compared against other
`--`-wrapped terms. What changes against the table at the top of this spec:

| | `--` (out, to Python) | `++` (in, to a term) |
|---|---|---|
| **atom** | the plain `str` — no tag | a plain `str` is the atom (main's meaning, kept) |
| **string** | `('$chars', text)` — the carrier, unconverted | a carrier is the string |
| compound / dict | the cell / the `DictTerm`, nothing inside converted | raw |

* `seam.export` no longer converts (`_to_boundary` is gone). It derefs,
  refuses an unbound constrained variable as before, and hands the value out
  BY IDENTITY only when it is proven to hold no `Var` object: atomic, a
  compiled constant (`cells.is_compiled_constant`, registered by
  `codegen.functiondef_to_function` — a tuple baked into a clause can hold
  no Var and is the same object every call), or walked completely within a
  bounded probe; otherwise it deref-walks a copy. (A first cut read the
  trail — "only the goal's own variables were bound" — and was unsound for
  `P is pair(A, A), between(1, 2, A)`; roborev 243.)
* Python text is `clausal.to_python(T)`; the deep IN converter is
  `clausal.to_clausal(obj)`; the sort key is `clausal.term_key`. All three
  are driven by the `python_terms` registry (one table, both directions).
* The leak rule survives and is now applied at every door: `wrap_text` (`++`
  values), the seam's bare-name lookup (`seam.build`), and a Python caller's
  goal at `solve`/`once`/`call` (`to_python.strip_atom_tags`, deep).
* Why: with the tagged boundary the STRING round trip `++(--T)` was broken
  on main (export flattened the carrier to a str and `++` read the str as an
  atom), and the tagged export was not deep (DictTerm/SetTerm values crossed
  raw anyway). Raw out is the only form under which both `++(--X)` round
  trips are identity.
* The `atom` class remains for now (its retirement is a later step); the
  `-double_quotes` default is unchanged here.

