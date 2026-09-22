# A declared atom overwrites hosted Python's binding of the same name, AFTER the module body has run

**Status: OPEN. Pre-existing — nothing to do with the boundary work; found
while measuring it 2026-09-22.**

## What happens

A module that declares an atom AND whose hosted Python binds the same name at
module level ends up with two different values for that name, depending on
WHEN you look:

    -module(m, [p(X)])
    -private([d, profile])

    p(d),

    profile = 5
    seen_right_after = profile          # -> 5
    trace.append(profile)               # -> 5   at module-exec time

    # after load:
    m.profile                           # -> 'profile'   the ATOM
    m.seen_right_after                  # -> 5

The author's assignment **takes effect while the module body runs** and is
**overwritten afterwards** by the generated atom binding. So the module body
sees `5`, and every later reader — a function in the same module called after
load, another module importing the name, a test — sees the atom.

## Why it is worth fixing rather than documenting

It is not a shadowing rule an author can learn and work with; it is the same
name having two values at two times, with no diagnostic either way. A function
defined in that module and called later reads the atom, not the value its own
file assigned three lines above.

Declared atoms live in BOTH places, which is what makes this possible:

* the MODULE GLOBALS, as a plain interned `str` — `-private([d])` emits
  `d = $mint('d')`, and that is what hosted Python reads;
* the registry `__clausal_declared_atoms__` (`cells.DECLARED_ATOMS_KEY`).

The generated assignment is emitted after the body, so it wins.

## What it is NOT

Not function-level shadowing, which behaves normally and correctly: a LOCAL
named `profile` shadows the atom for that function, and that is ordinary Python
scoping. The defect is module level only.

## The candidate fixes, unranked

* **Refuse at load.** A module that declares an atom and also binds that name
  in hosted Python is almost certainly a mistake; say so with both spellings
  named. Cheapest, and consistent with how the TitleCase lint treats a
  collision.
* **Emit the atom binding BEFORE the body**, so a later Python assignment wins
  — makes the name mean one thing, but silently flips which one, and a clause
  that reads the atom by name would then see the Python value.
* **Warn**, on the pattern the shadowed-variable lint already has a shape for.

Refusing looks right: there is no reading under which "this name is two
different values at two different times" is what the author wanted.

## Related, and the reason it was found

A compile-time fix for the boundary work was considered — tag `++name`
automatically when `name` is a declared atom — and this is half of why it does
NOT work. The other half is that at FUNCTION level a local shadows the atom
while the registry still lists the name, so the registry and the live binding
disagree and the compiler cannot tell from the name alone.
