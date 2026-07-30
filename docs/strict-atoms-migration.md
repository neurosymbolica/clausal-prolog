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
# from your clausify checkout, pointed at your repo's source dirs
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

#### Do not reach for `-private` when two files must agree

This is the one migration step that can leave you *worse off than the error
did*. Auto-minting put every undeclared `red` in one global class, so two files
that both said `red` were talking about the same atom. `-private([red])` in each
of them mints **two** classes, and atoms unify by identity — so the load error
goes away and is replaced by a query that silently has no solution. The compiler
cannot warn about this: two modules each declaring their own private atom is
exactly what `-private` is for.

The rule of thumb: **declare an atom where it is owned, and import it
everywhere else.** If the atom crosses a module boundary — a status tag a caller
compares against, a profile key one file writes and another reads, a verdict
vocabulary two predicates draw from — give it a home in the owning module's
`-module(owner, [..., red])` and use `-import_from(owner, [red])` in the rest.
Reserve `-private` for atoms that genuinely never leave their file, and for
atoms that are *deliberately* distinct from a similarly-spelled one elsewhere.

Symptom to watch for while migrating: a file that now loads, in a suite that now
fails an assertion it used to pass. Loading was never the goal; the atoms have
to be the *same* atoms. If you are unsure whether a name crosses a boundary,
`global_atom("red", R)` in both places is a safe intermediate — it is the same
process-wide class the old auto-mint gave you.

## Migrating clausify-domains

clausify-domains is expected to be *mostly* strict-clean already (rule files
tend to declare their atoms), so the migration should be light:

1. **Baseline (Path A).** Run the codemod over the domain source dirs and run
   the domain test suite. Confirm green. This guarantees no regression before
   you touch anything by hand.
   ```bash
   python /path/to/clausal/tools/codemods/add_implicit_atoms.py <domain-source-dirs>
   ```
2. **Strictify the rule files (Path B).** Remove `-implicit_atoms` from the
   authoritative rule files (the ones where a typo would silently change a
   ruling) and fix each `NameError` by declaring the atom — prefer
   `-module`/`-private`/`-import_from` over re-adding the escape hatch. Any
   genuine typo you uncover here is exactly the bug this change exists to catch.
3. **Drop deprecated `-strict_atoms`.** If any domain file still carries
   `-strict_atoms`, delete it — strict is now the default and the directive only
   emits a deprecation warning.
4. **Leave loose where appropriate.** Keep `-implicit_atoms` on scratch/example
   domains or any file intentionally using undeclared tags.

Pin clausify-domains to the strict-atoms Clausal release only after step 1 is
green, so the upgrade and the migration are separable.

## Reference

- Directives: [`-implicit_atoms`](directives.md#-implicit_atoms),
  [`-strict_atoms`](directives.md#-strict_atoms) (deprecated),
  `-module` / `-private` / `-import_from`.
- Reflection hatch: [`global_atom/2`](builtins.md#global_atom2).
- Atom model overview: [Atoms](syntax.md#atoms).
- Design rationale: `docs/superpowers/specs/2026-07-24-strict-atoms-default-design.md`.
