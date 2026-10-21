# The rewrite driver's re-render spells an identifier-shaped quoted atom bare

**Status: FIXED 2026-10-21 (branch fix/rewrite-keeps-quoted-atoms-2026-10-21).**
Candidate 2, as a side table rather than a flag: `clausal.reflection.AtomSpellings`
records each atom's quote character beside the terms (`reify_source(...,
spellings=)`, keyed by the Atom cell, then by name within the item), and
`render_source(term, spellings)` writes it back; an atom a rule built is bare
only when the bare name reads back as that atom (`_reads_back_bare`). The
driver reifies each clause with its table, renders through it, and then reads
every rewritten statement back out of the formatted output and compares it,
spellings included, with the rule's term (`driver._assert_reads_back`), refusing
the file on any difference. Not a flag on `Atom` because the engine tests "is
this an atom" by exact `str` type (a `str` subclass name a rule handed to
`atom_length/2` would stop being an atom) and a third field would break every
`Atom("a") == reified` comparison. Pinned in
`tests/rewrite/test_driver.py::test_a_passed_through_literal_keeps_its_spelling`,
`::test_a_folded_literal_keeps_its_spelling`,
`::test_a_rule_built_atom_is_spelled_to_read_back_as_itself`,
`::test_the_output_must_read_back_as_the_rule_meant`, `::TestReadsBackAs`,
`tests/test_reflection_render.py::TestAtomSpellings`, and the literal census in
`tests/rewrite/test_corpus.py` (662 files, 36 with a firing: 24 files / 141
quoted atoms respelled before, 0 after). The dotted case is confirmed: `'a.b'`
came back as the qualified reference `a.b`; it now stays `'a.b'`. Still open,
and now REFUSED by the read-back check rather than written: a quoted atom KEY
of an all-constant dict literal (`p({'a': 1})`) reifies as the raw key string
and renders as the string `{"a": 1}` -- the dict representation, not the
renderer, decides that one.

Filed 2026-10-21, found while reviewing the clausal-fmt quote-spelling fix
(`fix/fmt-keeps-quote-style-2026-10-20`). Pre-existing: it reproduces the same
way on `main` before that branch. Severity: high when it fires. A rewrite can
silently turn an atom into a variable or a Python constant.

## What

When a rule fires, `clausal/rewrite/driver.py` re-renders the modified goal
through `reflection.render_ast`. The emitter then copies the rendered
literals back verbatim (`table.literals.update(literal_spellings(node, text))`),
so the formatter is faithful to the rendered text. The rendered text is
already wrong.

Reification maps a quoted atom `'a'` and a bare `a` to the same vocabulary term,
`Atom('a')` (`_Reifier.term`, "THE FLIP", `clausal/reflection.py` ~line 486).
The renderer then writes any `Atom` whose spelling is a dotted identifier as a
bare name (`_ClauseRenderer`, `if _is_dotted_identifier(display)`, ~line 934).
It uses single quotes only for a non-identifier spelling. The source's quote is
lost, and "identifier-shaped" is not the same as "reads back as this atom".

The rule does not need to touch the literal. Any literal in the same goal
as the rewritten argument gets re-rendered. Strings are fine because they
always come back `"…"`.

## Repro

Use the shipped `unnecessary_lambda` rule on a scratch file:

```
q(_X) <- True

pass_through(_G, A, R) <- (R is A)

p(R) <- (
    pass_through(((X) <- q(X)), 'Foo', R)
)
```

```
python -m clausal.rewrite.cli --rules unnecessary_lambda --diff m.seam
-    pass_through(((X) <- q(X)), 'Foo', R)
+    pass_through(q, Foo, R)
```

`fold(((X, V) <- score(X, V)), 'a', "a", R)` becomes
`fold(score, a, "a", R)` in the same way. In the generated module, the literal
`'a'` becomes `$LoadName(name='a')`.

## Does it change meaning?

I loaded the program before and after the rewrite and ran `p(R)`. The table
shows what R was bound to, keyed by the atom written in place of `'Foo'`:

| quoted atom | rewritten to | before | after |
|---|---|---|---|
| `'a'`, undeclared | `a` | `'a'` | load fails: `NameError strict_atoms: undeclared atom 'a'` |
| `'a'`, declared (`-private([a])`, `-module(m, [..., a])`, `-import_from(m, [a])`) | `a` | `'a'` | `'a'`: the same str object, so no change |
| `'Foo'` | `Foo` | `'Foo'` | an unbound variable (silent) |
| `'_x'` | `_x` | `'_x'` | an unbound variable (silent) |
| `'None'` | `None` | `'None'` | Python `None` (silent) |
| `'True'` | `True` | `'True'` | Python `True` (silent) |
| `'if'` | `if` | `'if'` | refused: `RewriteError ... rendered to unparsable source` |

So a lowercase atom is safe when declared and fails to load loudly when not.
A capitalised or underscore-led atom, or one spelled like a Python constant,
changes meaning silently. A dotted quoted atom (`'a.b'`) presumably comes back
as the qualified reference `a.b`. I have not checked that one.

## Candidates

1. Render an `Atom` bare only if it reads back as the same atom: a lowercase
   identifier that is not a keyword or `None`/`True`/`False`, and not dotted
   unless it was a qualified reference. Otherwise single-quote it. This still
   turns an undeclared `'a'` into a load error.
2. Keep the source quote through reification (a flag on `Atom`, or a
   side-table keyed by position), so the re-render writes back what was read.
   This is the same idea as `CommentTable.literals` for the formatter.
3. In the driver, take each unchanged argument's spelling from the original
   source span and re-render only the arguments the rule changed.
