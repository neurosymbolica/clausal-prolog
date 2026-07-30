# `true` / `false` / `null` should name the `True` / `False` / `Unknown` literals

Design for `todo/lowercase-true-false-null-should-name-the-True-False-Unknown-literals.md`.

## Problem

A bare undeclared atom raises the same generic five-remedy `NameError` regardless of
its name:

```
strict_atoms: undeclared atom 'true' in eu.banking.crr_output_floor.decision
  bare atom references must be one of:
    - listed in -module(_clausal_test_c, [atom, ...])
    - listed in -private([atom, ...])
    - imported via -import_from(from_module, [atom])
    - qualified (e.g. other_module.atom)
    - obtained via global_atom("atom", Atom)
```

Not one of the five is the right answer. The right answer is `True`.

In a 24-run local-model formalization study (study 11), `undeclared atom(s) in module`
burned 69 attempts across 21 of 24 runs, with 65% never recovering. Of the 241
undeclared-atom mentions, `true` (38), `false` (18) and `null` (7) account for
**63 — 26%**. Just over a quarter of every undeclared-atom incident is a model writing
the Python/JSON spelling of a value the language already has.

There is no competing convention to respect: the gold corpus uses bare `True`/`False`
2003 times and `Unknown` 6 times, and every one of the 47 lowercase `true` occurrences
is inside a comment. One right spelling exists and the message declines to name it.

`Unknown` being titlecase is the least guessable part — every other atom in the
language is lowercase, and titlecase normally reads as a variable — so the hint names
it even when the misspelling is `true` or `false`.

## Design

### New module `clausal/atom_diagnostics.py`

Joins the existing `import_diagnostics` / `predicate_diagnostics` / `syntax_diagnostics`
family. Stdlib-only with no `clausal` imports, so both call sites import it at module
level without cycle risk.

```python
_TRUTH_LITERALS = {
    "true": "True",   "false": "False",
    "null": "Unknown", "none": "Unknown",      "nil": "Unknown",
    "unknown": "Unknown", "undefined": "Unknown", "maybe": "Unknown",
}

def truth_literal_hint_lines(names, indent="  ") -> list[str]
```

Returns `[]` when no name matches, so the passing path and every non-boolean error
message stay byte-identical. Lookup is on `name.lower()`; the working spellings
`True` / `False` / `Unknown` are already bound and never reach a raise site, so
case-insensitivity cannot shadow a name that works.

For a single matching name — the overwhelmingly common case:

```
  `true` is not a literal in Clausal — the boolean literals are `True`
  and `False`, and the third truth value under well-founded semantics
  is `Unknown`.
  -> did you mean `True`?
```

When several names match, the three-value explanation is stated once and each
name gets its own arrow. Collapsing instead on the *literal* would leave a second
synonym unmentioned, so an author with both `null` and `nil` undeclared would fix
`null`, re-run, and meet `nil` on the next pass:

```
  `null`, `nil` are not literals in Clausal — the boolean literals are `True`
  and `False`, and the third truth value under well-founded semantics
  is `Unknown`.
  -> `null`: did you mean `Unknown`?
  -> `nil`: did you mean `Unknown`?
```

The corpus carries no bare `nil` / `none` / `maybe` / `undefined` outside comments, so
the match set collides with nothing. A false positive would only add an off-target
suggestion line to an error that is already fatal.

### Call site 1 — `clausal/logic/compiler_v2.py:731` `_build_strict_atoms_diagnostic`

The hint block slots between the header and `"bare atom references must be one of:"`.
Mixed cases keep both parts: the header still enumerates every undeclared name, and
the five remedies still follow, so the author can fix the non-boolean names too.

```
strict_atoms: undeclared atoms 'foo_bar', 'true' in eu.x.y
  `true` is not a literal in Clausal — the boolean literals are `True` and
  `False`, and the third truth value under well-founded semantics is `Unknown`.
  -> did you mean `True`?
  bare atom references must be one of:
    - listed in -module(eu.x.y, [atom, ...])
    ...(remaining four)
```

### Call site 2 — `clausal/import_hook.py:109` `_intern_atom`

The dict-key path (`{true: 1}`) has its own single-line message and deserves the same
steer. Hint lines append after the existing text.

## Testing

New `tests/test_atom_diagnostics.py`, written red-first:

1. Unit table over the pure helper — every key maps to the right literal; an unrelated
   name yields `[]`
2. Bare `true` in a strict file → message names `True`
3. Bare `null` → message names `Unknown`
4. Mixed `true` + `foo_bar` → hint present **and** all five remedies still present
5. Non-matching atom alone → message unchanged from today (the regression guard)
6. Dict-key path `{true: 1}` → hint present
7. `TRUE` → `True` (case-insensitivity)

## Out of scope

String forms — `"true"` used as a truth value — are excluded. A string literal is a
valid `str` that reaches neither raise site and produces no error at all; catching it
needs a lint pass that knows an argument position is truth-valued, which is a separate
feature with its own design. Recorded as its own todo.
