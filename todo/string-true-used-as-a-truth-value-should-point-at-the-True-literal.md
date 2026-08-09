# `"true"` used as a truth value should point at the `True` literal

Split out of `todo/done/lowercase-true-false-null-should-name-the-True-False-Unknown-literals.md`,
which shipped the *atom* half: bare `true` / `false` / `null` now name `True` /
`False` / `Unknown` in the undeclared-atom diagnostic (`clausal/atom_diagnostics.py`).

## Why this half was deferred

The atom half was cheap because a bare undeclared atom already raises. A string
literal does not:

```clausal
-private([flag(X)])
flag("true"),
Test("string true") <- flag("true")
```

`"true"` is a perfectly valid `str`. It reaches neither raise site — not
`_build_strict_atoms_diagnostic` in `clausal/logic/compiler_v2.py`, not
`_intern_atom` in `clausal/import_hook.py` — and produces no error at all. It
silently becomes a truthy string that is not the `True` literal, so the rule
half-works: it unifies with itself and with nothing else.

There is therefore no message to improve. Catching this needs something new.

## What it would take

A lint that knows an argument position is truth-valued, then flags a string
literal there. Open questions, none of them answered yet:

- **Where does the "expects a truth value" signal come from?** Candidates: the
  declared type of the predicate argument, if declared; a builtin's known
  signature; inference from the clause body (a position tested against `True`
  elsewhere). Each has a different reach and a different false-positive profile.
- **Warning or error?** Unlike the atom case, a string in a truth-valued
  position may be deliberate data. An error would be a breaking change; a
  warning risks being ignored.
- **What is the surface?** Compile-time lint, a `-strict` opt-in, or a separate
  checker that runs over a corpus.

## Worth doing?

The evidence from a measured authoring study is weaker here than for the atom half. Bare
lowercase `true` accounts for 38 of the 241 undeclared-atom mentions; `"true"`
appears just 4 times in the gold corpus and every one is inside a comment. The
motivating argument is consistency — "exactly one spelling per truth value
rather than four that half-work" — rather than a measured recovery failure.

Recommend leaving parked until a study shows string truth values actually
burning attempts. If they do, that study will also answer the "where does the
signal come from" question, since it will show which positions are involved.
