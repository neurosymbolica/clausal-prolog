# The rewrite driver's re-render spells an identifier-shaped quoted atom bare

**Status: FIXED 2026-10-21 (branch fix/rewrite-keeps-quoted-atoms-2026-10-21).**
Candidate 2, as a side table rather than a flag: `clausal.reflection.AtomSpellings`
records each atom's quote character beside the terms (`reify_source(...,
spellings=)`, keyed by the Atom cell, then by name within the item -- atoms and
functors), and `render_source(term, spellings)` writes it back. The driver
resolves a rule's answer with a walk that keeps an unchanged tuple
(`driver._resolved_keeping_cells`; `_deref_walk` rebuilds every tuple and
would lose the cell), so a passed-through atom is spelled by its cell even in an item that
writes `'a'` and `a` both. An atom a rule built is bare only where the item
itself spells that name bare (`Atom(CALLEE)` for a callee the lambda body
spelled bare), quoted where the item spells it two ways or never (a bare
`score` may be a predicate, a declared atom, an imported module or a load
error, and `ǅx` normalises to the variable `Džx`), bare for an unseen dotted
name that reads back bare, and refused inside a lambda with a parameter of that
name. Bare = the reference the item uses, which for an imported or dotted name
is not the plain atom: a rule-built `Atom(N)` where the item only calls an
imported `N` renders as that reference (the hidden atom or the module
predicate), which is what the shipped rules intend. The driver then reads every rewritten statement back out of the formatted
output and compares it with the rule's term (`driver._assert_reads_back`), each
passed-through atom's quote by cell, refusing the file on any difference. Not a flag on `Atom` because the engine tests "is
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
came back as the qualified reference `a.b`; it now stays `'a.b'`. The dict-key
case left open here (a quoted atom KEY of an all-constant dict literal,
`{'a': 1}` or `{'a': R}`, rendered as the string `{"a": 1}` and was refused by
the read-back check) is **FIXED 2026-10-22 (branch
fix/fmt-anchor-and-dict-key-2026-10-22)**: the raw dict keeps its
representation, and `AtomSpellings.record_key`/`key_quote` spell its keys by
the dict object, which the driver now keeps when the rule passes it through.
A raw dict's atom key a rule built is single-quoted (never bare: `{a: 1}` is
the `DictLiteral` surface), a string key stays a string, a bare `DictLiteral`
key stays bare, and a rule-built `DictTerm` renders as its dict. Pinned in
`tests/rewrite/test_driver.py::test_a_passed_through_dict_keeps_its_key_spellings`,
`::test_an_atom_mode_dict_keeps_its_key_spellings`,
`::test_an_atom_mode_item_spelling_one_key_two_ways_keeps_each`,
`::test_a_rule_built_dict_keeps_its_key_kinds` and
`tests/test_reflection_render.py::TestAtomSpellings::test_a_dict_key_renders_with_the_quote_it_was_read_with`,
`::test_a_raw_dict_atom_key_is_quoted_and_a_string_key_double_quoted`.

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
