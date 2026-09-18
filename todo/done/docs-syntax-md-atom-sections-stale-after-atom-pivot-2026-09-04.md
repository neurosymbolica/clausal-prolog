# docs/syntax.md Atoms sections are stale after the P3-1 atom pivot

Found during P3-1 Task 8 (close-out) while updating `docs/directives.md`
and `docs/import.md`'s atom-identity docs (both link to `syntax.md#atoms`
as "the atom model overview"). Out of scope for Task 8's itemized doc
list (`directives.md`, `import.md`, the strict-atoms migration doc,
`directives_sigs.txt`) so parked here rather than rewritten ad hoc, same
discipline as the sibling todo
`todo/docs-strings-as-lists-md-stale-after-cons-rule-retirement-2026-09-04.md`
(also parked for a doc pass, also found by this same plan).

## What's stale

Two sections in `docs/syntax.md` describe the PRE-pivot per-module
atom-class-identity model, which P3-1 deleted:

1. **`## Atoms`** (~line 317-362): "Every atom is reified at compile time
   as a zero-arity `PredicateMeta` class... Unification on atoms is class
   identity." False post-pivot — an atom is an interned `str`; unification
   is str equality. The `-module`/`-private` description ("A module opts
   an atom into **module-local** identity (a class distinct from the
   global one)...") describes the EXACT mechanism P3-1 deleted (see
   `docs/import.md#atoms-are-global-by-spelling`, corrected in this same
   Task 8, for the accurate story: `-module`/`-private` no longer create
   distinct identities at all -- only [`-hide`](directives.md#-hide) does,
   and it renames rather than classing). The referenced snippet
   `tests/fixtures/docs/syntax_sigs.txt:atoms_module_local` also asserts
   the false claim in its own comments ("Public, module-local: importers
   see traffic.red as a distinct class from the global red").
2. **`## Atoms vs strings: there are no "string atoms"`** (~line
   629-666): the section's entire THESIS is now false. R2 (§1b/§5 of
   `implementation_plans/tagged-tuple-term-representation.md`) collapsed
   atom and string into the same runtime value and the same predicate:
   `atom(X)` is now true for every `str` (verified live:
   `atom("hello world")` succeeds), directly contradicting the section's
   comparison table (`atom/1` row: "does **not** match (use `is_str/1`)"
   -- wrong) and its `identity` row ("global class identity; `is` works"
   -- wrong, it's just str equality/interning now). The prose argument
   for why "Adding string atoms would also actively *harm* the model" is
   now moot -- the pivot added exactly that, deliberately (§5's "Atom/
   string collapse" ruling), and the sky did not fall; Phase 3's actual
   reasoning for the collapse (documented in the design doc, not
   reproduced here) should replace this section's now-backwards
   rationale, not just patch the table.

## NOT in scope for whoever picks this up

Leave `## Strings` (~line 606-627, "a str behaves as a list of character
atoms under unification") and everything the OTHER todo
(`docs-strings-as-lists-md-stale-after-cons-rule-retirement-2026-09-04.md`)
covers alone -- that is a DIFFERENT staleness class (Task 5's cons-rule
retirement changing str~char-list unification), not this one (Task
1-3/R2's atom/string value collapse). The two todos are complementary,
not overlapping; a single doc pass over `syntax.md`'s string/atom
sections should probably resolve both together since they're adjacent
and interact (e.g. the "Atoms vs strings" table's `identity` row touches
both), but they are DISTINCT underlying claims to verify independently
before rewriting.

## Suggested fix direction

Rewrite `## Atoms vs strings` from "two disjoint kinds" to something like
"one runtime kind, two spellings" -- a bare identifier and a quoted
literal now produce the identical `str` value (in the CURRENT
Python-syntax surface; R3 notes the double-quote/char-list distinction
returns in the new surface when it lands). The remaining, still-genuinely-
true distinction is COMPILE-TIME, not runtime: a bare identifier
reference is checked against the declared vocabulary under
[`-strict_atoms`](directives.md#-strict_atoms) (undeclared -> compile
error), while a quoted string literal is a plain `Constant` and is never
subject to that check. Keep the genuinely-useful design guidance (Unicode
identifiers, the translation-lexicon pattern for punctuated display text)
-- that advice survives the collapse even though the "there are no string
atoms" framing it was hung on does not.

## CLOSED 2026-09-18

Done in the docs pass after the atoms-as-str flip (stages 1+2 landed on main at 3fcfd29e): docs branch `docs/atoms-as-str-doc-pass-2026-09-18`, fast-forwarded onto main. Every claim was measured against the landed engine; the doc-snippet suite (tests/fixtures/docs) is green. The current model: an atom IS the interned Python str, a string is the list of its char atoms (the `$chars` carrier internally), an atom key and a same-spelled STRING key are different keys, an atom key and its quoted spelling are one.
