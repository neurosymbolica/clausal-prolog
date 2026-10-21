# The rewrite driver's re-render spells an identifier-shaped quoted atom bare

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
