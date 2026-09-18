# Migrating to strict-atoms-by-default

## What changed

Clausal used to **auto-mint** any bare atom you referenced: writing `pending`
in a clause silently created a process-wide global atom on first use. That made
a typo (`peding`) a silent wrong answer rather than an error.

As of the strict-atoms release, **an undeclared bare atom is a compile-time
`NameError`**. A bare atom now has to be reachable through one of:

- a `-module([... , atom])` listing,
- a `-private([atom])` listing,
- a `-import_from(other_module, [atom])`,
- a qualified reference (`other_module.atom`), or
- a `global_atom("atom", Atom)` call.

Anything else fails to load with a diagnostic like:

```
strict_atoms: undeclared atom 'pending' in immigration_rules
  bare atom references must be one of:
    - listed in -module(immigration_rules, [atom, ...])
    - listed in -private([atom, ...])
    - imported via -import_from(from_module, [atom])
    - qualified (e.g. other_module.atom)
    - obtained via global_atom("atom", Atom)
```

The new opt-out is the **`-implicit_atoms`** directive, which restores the old
auto-mint behavior for a single file. It is permanent and supported — it is the
escape hatch, not a deprecated shim.

The old `-strict_atoms` directive is now redundant (strict is the default). It
still works but is **deprecated** and emits a one-per-process
`ClausalStrictAtomsDeprecationWarning`; delete it when convenient.

### What did *not* change

- Atom **spellings** in clauses — no source rewriting needed for correct code.
- Predicates with arity ≥ 1 — unchanged (already module-local by default).
- Strings (`"red"`) — a distinct data type, never affected by atom strictness.
- `True` / `False` — parsed as Python constants, not bare atoms, so truth-table
  files need no declarations.
- The **REPL** and **doc/markdown ```clausal example blocks** compile in
  implicit mode automatically — interactive and illustrative snippets keep
  auto-minting with no directive needed.

Note on **dict-literal keys**: a bare atom used as a dict key (`{sky: 1}`) is
treated exactly like any other bare atom — it **raises** under the strict
default and must be declared or reached via `-implicit_atoms`. This holds for
both the compile-time source path and the runtime atom-intern path (they share
the strict-by-default rule), so a dict-key atom and a value-position atom behave
identically.

## Do I need to migrate?

Only files that relied on the auto-mint default and are **loaded/compiled**
break. To find them, load your program (or run your test suite) and look for
`strict_atoms: undeclared atom ...` `NameError`s. Files that already declare
their atoms, use strings for data, or only use arity-≥1 predicates need nothing.

## Two migration paths

You do not have to choose one for the whole repo — the recommended approach is
to bulk-apply the safe path first, then adopt strictness incrementally where it
pays off. This mirrors how upstream Clausal migrated its own corpus.

### Path A — Fastest, zero behavior change: bulk `-implicit_atoms`

Add `-implicit_atoms` to every source file, restoring the old loose behavior
everywhere. Nothing changes semantically; you just become explicit about it.

Upstream ships the exact codemod it used on its own tree:

```bash
# from your own checkout, pointed at your repo's source dirs
python /path/to/clausal/tools/codemods/add_implicit_atoms.py src rules fixtures
```

The codemod:

- inserts `-implicit_atoms` before the first non-comment line of each `.clausal`
  file that does not already carry `-strict_atoms` or `-implicit_atoms`,
- is **idempotent** (safe to re-run), and
- skips byte-exact snapshot directories (its `_SKIP_DIRS`) — adjust that set for
  your repo if you have generated `.clausal` output you compare as text.

After running it, your suite should be green with no behavior change. Commit that
as a mechanical baseline, then move to Path B on the files that matter.

### Path B — Recommended, gain the typo safety: declare atoms

For files where atom-spelling correctness matters (rule sets, decision logic),
remove `-implicit_atoms` and let the diagnostic tell you which atoms to declare.
For each reported atom, pick the right home:

| Situation | Fix |
|---|---|
| Genuine typo | correct the spelling (this is the payoff) |
| Module-local tag, exported | add to `-module(name, [..., tag])` |
| Module-local tag, private | add to `-private([tag])` (bare name, 0-arity) |
| Shared tag owned by another module | `-import_from(owner, [tag])` |
| Need the global atom by name in a strict file | `global_atom("tag", Tag)` |

Iterate file-by-file until the file loads clean. Keep `-implicit_atoms` on
files where loose behavior is genuinely wanted — prototypes, data-heavy
fixtures, or code that deliberately relies on ceremony-free tag atoms.

#### `-private` is fine even when two files must agree

> **Updated 2026-09-04 (P3-1 atom pivot):** this used to be the one migration
> step that could leave you worse off than the error did — declaring the same
> atom `-private` in two files used to mint two DIFFERENT classes, so a query
> comparing one against the other silently had no solution. That failure mode
> is gone. Atoms are now global by spelling: `-module`, `-private`, and an
> `-import_from` of the same spelling all resolve to the same atom — the
> interned Python `str` itself — so there is nothing left to
> disagree about (see [Import System §
> Atoms are global by spelling](import.md#atoms-are-global-by-spelling)).

Two files that each independently declare `-private([red])` (or one declares
it via `-module` and the other via `-private`) refer to the exact same atom —
declaring it twice is redundant, not conflicting. You may still prefer to
**declare an atom where it is owned, and import it everywhere else** for
readability (a status tag a caller compares against, a profile key one file
writes and another reads, a verdict vocabulary two predicates draw from) —
`-module(owner, [..., red])` plus `-import_from(owner, [red])` documents the
ownership relationship for a reader even though it makes no runtime
difference. `-import_from` also remains the only way to reach an atom another
module declared `-private` *without* re-declaring it yourself.

**Need a spelling two files genuinely must NOT agree on?** Global-by-spelling
means `-private` cannot give you that any more — reach for
[`-hide`](directives.md#-hide) instead. `-hide([red])` compiler-renames the
atom into a namespace only its own file can spell, so a different module's
`red` (declared any way at all) is guaranteed to be a genuinely different
value, not a same-spelling collision to avoid.

If you are unsure whether a name crosses a boundary, `global_atom("red", R)`
in both places is a safe way to confirm — it is the same process-wide value
the old auto-mint gave you, and (post-pivot) the same value any declaration
route gives you too.

## Reference

- Directives: [`-implicit_atoms`](directives.md#-implicit_atoms),
  [`-strict_atoms`](directives.md#-strict_atoms) (deprecated),
  `-module` / `-private` / `-import_from` /
  [`-hide`](directives.md#-hide) (module-private atoms, since the
  atom pivot).
- Reflection hatch: [`global_atom/2`](builtins.md#global_atom2).
- Atom model overview: [Atoms](syntax.md#atoms),
  [Import System § Atoms are global by spelling](import.md#atoms-are-global-by-spelling).
- Design rationale: `docs/superpowers/specs/2026-07-24-strict-atoms-default-design.md`,
  `implementation_plans/tagged-tuple-term-representation.md` §1a/§1b (the atom
  pivot that made atoms global by spelling and added `-hide`).
