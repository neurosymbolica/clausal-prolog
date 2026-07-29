# `-keys` — declared profile keys with string representation (the TypedDict path)

**Date:** 2026-07-29
**Status:** design sketch, not approved. Raised while brainstorming
`2026-07-29-dot-attribute-access-design.md`; separated because it is a language-*and*-corpus change
with its own migration, and should not ride along with the `.` sugar.

## The problem in one table

Profile keys must satisfy three things. Today's two options each fail one:

| | declared / typo-checkable | collision-free with predicates | survives the Python→`solve()` boundary |
|---|---|---|---|
| **atom keys** (today's corpus) | ✅ | ❌ | ❌ |
| **string keys** (pre-migration) | ❌ | ✅ | ✅ |
| **`-keys` (this design)** | ✅ | ✅ | ✅ |

The corpus migrated string→atom to buy column 1. R8's own lint docstring states the goal plainly:
*"A profile field is domain vocabulary and must be a bare declared atom."* Declaredness was the
objective; atoms were merely the mechanism. Columns 2 and 3 are what that mechanism costs.

### What columns 2 and 3 cost, concretely

Both failures are documented and reproduced:

- **Column 2** — Phenomenon A (`implementation_plans/dict-atom-keys-vs-predicates.md`): importing a
  key atom whose name matches a predicate the module *exports* shadows the predicate; calls
  mis-resolve to 0-arity atom construction and die with `TypeError: __init__() got an unexpected
  keyword argument`. Worked around by un-exporting predicates. `au/firb/profile_keys.yaml` carries
  the workaround in a header comment.
- **Column 3** — `todo/query-template-rebinds-atom-dict-keys.md`: an atom-keyed `DictTerm` crossing
  into a module where the key name is bound to something else has its key **silently rebound** to
  that object. Verified: a profile with `query_date: 5` returns **0** solutions from a rule that
  should succeed, no error, even with a fully qualified key read.

Under the snake_case predicate convention (`todo/module-predicates-snake-case-rename.md`) keys and
predicates are spelled identically — both name the same domain noun — so these are the common case,
not corner cases.

Verified, same collision, same boundary, **string** key:

```
profile: DictTerm({'query_date': 5})
  eligible/1 -> 1 solutions   (the atom version returns 0)
```

String keys compile as `Constant` nodes, are never re-resolved by name, and are structurally immune
to the whole class.

## The design

Separate **declaration** from **representation**, exactly as Python's `TypedDict` does — a declared
key set, checked at compile time, that at runtime is a plain dict with string keys.

```clausal
# profile.clausal — the type module
-keys([ query_date, filing_status, foreign_person, acquisition_value_cents ])
```

- **Representation: strings.** `P.query_date` lowers to `P["query_date"]`. Immune to Phenomena A and
  B and to the key-rebinding bug. JSON-native, which `todo/dict-native-profile-api.md` lists as a
  motivating goal since profiles map 1:1 onto JSON objects.
- **The quotes are invisible**, because authors write `P.query_date`. This is what makes strings
  palatable again; it was the visible `"..."` noise that made bare atoms attractive.
- **Nothing enters the module namespace.** No import at the use site, so a local `query_date/2`
  predicate cannot collide. This is the "key namespace" — separate precisely because it is not the
  module globals.
- **Checked at load.** `P.filing_sttus` errors against the declared key set.

### Checking power is deliberately unchanged

This is the load-bearing honesty of the design. Strict atoms does **not** verify that *this dict* has
*that key* — Clausal is untyped and the compiler cannot know a variable holds a profile. It verifies
that the name is declared vocabulary in scope. A `-keys` check is exactly as strong: a **vocabulary**
check, not a schema check.

So `-keys` buys no new guarantee. It buys the *same* guarantee without the collisions, the import
ceremony, or the boundary corruption. That is the entire pitch, and overclaiming it as "typed
profiles" would be wrong.

## Open design questions

1. **Scoping.** How does a `-keys` declaration reach other modules — a `-keys_from(profile)` import
   of the *schema* (not the names), lexical scope, or process-wide? Schema import is the most
   consistent with the type-module convention.
2. **Coverage.** Does the check apply only to `.key`, or also to bare/literal keys in `P[...]`,
   `get/3`, `in`, `delete/3`, and `{k: v}` literals? Consistency argues for all key positions where
   the key is a compile-time literal.
3. **Permissiveness.** Dicts with genuinely dynamic or unschema'd keys must keep working. Probably:
   the check fires only where a `-keys` declaration is in scope; otherwise anything goes. Needs to be
   stated so it cannot silently start rejecting general-purpose dict code.
4. **Atom keys are not removed.** They stay valid for non-profile dicts. Only the *profile*
   convention changes. R8 inverts.
5. **Error or warning**, and is there an escape hatch analogous to `-implicit_atoms`?

## Cost

- Reverses a completed 54-domain migration and inverts R8 plus `R8_STRINGKEY_ALLOWLIST`. The edit is
  mechanical, but every domain needs re-proving (`G3 PROVED ≥ baseline`) and its gold suite re-run.
- New directive, new checker, plus the scoping decision above.
- The SMT prover's profile projection must recognize the new read/key form.
- `profile_keys.yaml` (40 of 54 domains) becomes redundant or generated — it is the same information,
  currently sidecar. Folding it in is a benefit, but it is also 40 files of migration.

## Sequencing

Independent of, but interacting with, the `.` sugar:

- If `-keys` lands **first**, the corpus migrates once (atoms → declared strings) and the `.` sugar
  arrives into a world where attribute position is already unambiguous.
- If the `.` sugar lands **first**, it ships against today's atom-key world and the corpus migrates
  later, touching some of the same lines twice.

The sugar is small and self-contained either way. The `query-template-rebinds-atom-dict-keys` fix
should land before either, since it is a live silent-wrong-answer bug and is independent of both.

## A decision this would subsume

The sugar spec asks whether attribute position should resolve names like `[]` does (strict
equivalence) or be a *quoted* context. That question exists only because a bare name in key position
goes through Python name resolution and can hit a predicate. With `-keys`, attribute position is both
quoted and checked, and the tradeoff disappears — so if `-keys` is adopted, do not settle that
question separately.

## Pointers
- `docs/superpowers/specs/2026-07-29-dot-attribute-access-design.md` — the `.` sugar and the
  dict-type-module convention this schema would formalize
- `todo/query-template-rebinds-atom-dict-keys.md` — column 3, with reproduction
- `implementation_plans/dict-atom-keys-vs-predicates.md` — column 2, with design options
- `todo/dict-native-profile-api.md` — the dict-native surface and its JSON-mapping goal
- `clausify-domains/_tools/check_corpus_conventions.py` — R8 and `R8_STRINGKEY_ALLOWLIST`
- `clausify-domains/*/profile_keys.yaml` — the existing sidecar schema, 40 domains
