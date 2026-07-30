# `true` / `false` / `null` should name the `True` / `False` / `Unknown` literals

## There is no guardrail today

Verified at pin `31a1ab79`:

```clausal
-private([flag(X), tri(X)])
flag(True),
flag(False),
tri(Unknown),
Test("True/False/Unknown are literals, undeclared") <- (flag(True), flag(False), tri(Unknown))
```
→ `1 tests: 1 passed, 0 failed [PASSED]` — the three literals work bare and undeclared.

```clausal
-private([flag(X)])
flag(true),
Test("bare lowercase true") <- flag(true)
```
→
```
      bare atom references must be one of:
        - listed in -module(_clausal_test_c, [atom, ...])
        - listed in -private([atom, ...])
        - imported via -import_from(from_module, [atom])
        - qualified (e.g. other_module.atom)
        - obtained via global_atom("atom", Atom)
```

Five remedies, and **not one of them is the right answer.** The right answer is `True`.
`_make_intern_atom` in `clausal/import_hook.py:109` raises the same generic `NameError`
for every undeclared name, with no special case for the boolean spellings.

## Why it matters

In a 24-run local-model formalization study (study 11), `undeclared atom(s) in module`
burned **69 attempts across 21 of 24 runs, 65% never recovering**. Breaking the 241
undeclared-atom mentions down by name:

| name | mentions |
|---|---|
| `true` | 38 |
| `false` | 18 |
| `null` | 7 |
| **subtotal** | **63 (26%)** |

Just over a quarter of every undeclared-atom incident in the study is a model writing
the Python/JSON spelling of a value the language already has. For comparison, the gold
corpus uses bare `True`/`False` **2003 times** and `Unknown` 6 times; bare lowercase
`true` appears 43 times and `"true"` 4 times, and *every one of those 47 is inside a
comment*. There is no competing convention — there is one right spelling and the error
message declines to name it.

## Requested behaviour

When the undeclared atom's name matches a boolean/unknown spelling, lead with the
literal instead of the generic remedy list:

```
strict_atoms: undeclared atom 'true' in eu.banking.crr_output_floor.decision
  `true` is not a literal in Clausal — the boolean literals are `True` and `False`,
  and the third truth value under well-founded semantics is `Unknown`.
  -> did you mean `True`?
```

Suggested match set, case-insensitive: `true` → `True`; `false` → `False`;
`null`, `none`, `nil`, `unknown`, `undefined`, `maybe` → `Unknown`. Falling back to
today's five-remedy list for everything else.

The string forms deserve the same treatment where they are cheap to catch — `"true"`,
`"True"`, `"false"` used as a truth value should also point at `True`/`False`, so that
there is exactly one spelling per truth value rather than four that half-work.

`Unknown` being titlecase is the part a reader is least likely to guess, since every
other atom in the language is lowercase and titlecase normally reads as a variable.
That alone justifies naming it in the message.

## Notes

- The check is a dict lookup on the name at the existing raise site
  (`clausal/import_hook.py:109` and the corresponding bare-atom-reference site), so it
  costs nothing on the passing path.
- Related: [[nameerror-does-not-name-the-sibling-that-exports-it]] — same shape of fix,
  turning a message that states a fact into one that names the action.
