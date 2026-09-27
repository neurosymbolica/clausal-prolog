# Lint idea: a string literal in a `catch/3` error pattern never matches

**Status: IDEA. Found 2026-09-27 during Compound retirement slice 2.**

## The trap

Under the default `-double_quotes(chars)`, `"atom"` in source is a CHAR LIST,
not an atom. Every engine error term carries atoms
(`error(type_error(atom, 1), atom_length/2)`), so a catcher written with a
string never unifies. The `catch/3` then silently does not catch, and the
error flies past it:

    s(R) <- (catch(catch(atom_length(1, _), error(type_error("atom", _), _), R is caught), _, R is missed)),
    a(R) <- (catch(catch(atom_length(1, _), error(type_error(atom, _), _), R is caught), _, R is missed)),

    s -> missed      (the string pattern did not match)
    a -> caught

Measured on main 03f70a71. Another example of the shape is
`domain_error("date", _)`.

## Proposed lint

At load time, walk the catcher argument of each `catch/3` whose catcher is an
`error(...)` term, or contains one of the ISO error-class functors
(`type_error/2`, `domain_error/2`, `existence_error/2`,
`permission_error/3`, `representation_error/1`, `evaluation_error/1`,
`resource_error/1`, `syntax_error/1`). Warn on any double-quoted literal in
it, and suggest the atom spelling. The lint is only sound when
`double_quotes` is `chars` or `codes`; under `atom` the literal is already an
atom.
