# Extension-flip checklist: what is TRUE today and becomes FALSE at the flip

**Filed** 2026-09-10, engine lane, at 820dc66f. Engine side only; each other tree needs its
own. **Not a bug list.** Every item here is correct right now, which is exactly why no sweep
run today will find it. The trigger is the landing, not the code.

## Status 2026-10-01 (engine preparation landed on feat/extension-flip-prep-2026-10-01)

Read this section first; the original inventory follows, each item marked.

### The exact remaining flip diff

1. **`clausal/_suffixes.py`, two lines:**

       CLAUSAL_SUFFIXES: tuple[str, ...] = (".seam",)
       CLAUSAL_PROLOG_SUFFIXES: tuple[str, ...] = (".clausal",)

   Everything else follows these two constants (verified by
   `tests/test_extension_flip_prep.py`, which patches exactly these two).
   Read at each call: `prolog_suffixes()`, `is_prolog_source()`,
   `seam_suffixes_text()`, `end_module.surface_of`, the finders' groups, the
   loader choice (`_prolog_loader_class_for`: Clausal Prolog is ALWAYS
   native), the cache salt (`_suffix_salt`, keyed on the surface), the test
   runner, use_module's export-list reader, clausal-fmt/-rewrite (refuse
   Clausal Prolog), translate.py's direction, and every message.  Frozen at
   import (so correct after a real edit of the file, but NOT exercised by
   the patched-tuple tests): `SOURCE_SUFFIXES`, and through it the test
   runner's `TEST_SUFFIXES`, the lazy stub finder and the diagnostics'
   suffix lists; the finders' informational `_extensions` attributes.
2. **The rename sweep:** `git mv` every seam `.clausal` to `.seam` (MOVE,
   never copy: a stale twin would be a different module after the flip).
   Includes `clausal/stdlib`, `clausal/examples`, `clausal/rewrite/rules`
   (clausal-rewrite cannot load its rules until they move), `tests/`,
   `packages/`, plus any path that names a `.clausal` file
   (`--8<--` snippet refs in docs, test fixtures that name paths, the
   funnel-lint allowlist's path entries).
3. **Tests that pin the PRE-flip state and must be repointed in the same
   landing** (they are correct today, by design):
   - `tests/test_import.py::test_finder_lists_both_clausal_extensions`
     (`(".clausal", ".seam")`);
   - `tests/rewrite/test_cli.py::test_the_twin_resolves_in_finder_priority_order`
     (asserts `CLAUSAL_SUFFIXES[0] == ".clausal"`; becomes vacuous -- item 3
     below -- delete it or repoint it, do not let it pass vacuously);
   - `tests/test_extension_flip_prep.py`: the `before_the_flip` tests and
     `test_existing_cache_keys_are_unchanged_before_the_flip` (their
     `flip`-fixture twins become the unpatched truth; drop the fixture);
   - `tests/iso_l3/test_l3_end_module.py::test_surface_of_follows_the_suffix_tuples`
     (`surface_of("m.clausal") == "seam"`).
4. **Doc fences:** drop `"clausal"` from
   `clausal/tools/doc_snippet_check.SEAM_FENCE_LANGS` -- only AFTER
   `packages/*/docs` (861 blocks, still ```clausal) are fenced ```seam;
   else those blocks silently stop being tested.  `docs/` is done.

Not engine-prep, but the plan puts them in the SAME landing (see the cut
sizing plan, sec. 7.3 step 4): the `.clausal`-may-not-import-`.pl`
refusal (route 1); and nothing may be renamed before every downstream glob
reads a shared suffix list (positive control required).

- **Route 1 READY (2026-10-02, feat/clausal-may-not-import-pl-2026-10-02).**
  A Clausal Prolog module whose `use_module/1,2` resolves to a `.pl` file
  is refused at load: `permission_error(access, prolog_module, M)`, "Clausal
  Prolog may not import ISO Prolog (.pl), which may use cut; convert ... to
  .clausal".  Keyed on the SURFACE of the importer and of the file the
  finders picked (so a `.seam`/`.clausal` twin of a `.pl` is never
  refused); inert until the tuple flips, active with no further edit.
  Both front ends (native `_use_module`, the translator's
  `_clausal_prolog_facade`).  Pinned (simulated flip) in
  `tests/test_clausal_prolog_may_not_import_pl.py`.  Census on the flip
  preview: 0 static in-repo sites (the 4 `.clausal` left there are seam
  repros under `todo/done/` with no `use_module`); 1 test-generated site,
  `test_extension_flip_prep.py::test_a_clausal_prolog_importer_is_told_use_module`,
  repointed at a `.clausal` library on this branch.  Not covered (routes
  2-7, later, with the dialect gate; route 2 RULED strict: a `.pl` closure
  passed into a `.clausal` meta-predicate is refused too): a run-time
  `M:G` / `call/N` into a `.pl` module some other code loaded still runs
  (pinned as today's behaviour, labelled "closed by route 2").
  Open Low (review): the defensive `.pl` check on mapped libraries in
  `iso_l3_directives._use_library` is unreachable today (every mapped
  module is `.py`/`.seam`), costs a `find_spec` per mapped-library import
  under the Clausal Prolog surface, and has no twin in the translator's
  mapped-library branch; a static test over `_LIBRARY_MODULES` /
  `_LIBRARY_OVERRIDES` would replace it.
  `ensure_loaded/1` is no native directive; `library(L)` never reaches a
  `.pl` (built-in, mapped engine module, or `.seam` facade only).

### Still remaining, outside the two-line diff

- The end-of-life translator (`clausal/tools/prolog_to_clausal.py`) spells
  `(".clausal", ".seam")` as "the seam twin" in `_find_module_file` and
  `_MODULE_EXTS`.  After the flip a `.clausal` twin of a `.pl` is Clausal
  Prolog, and the finder takes the `.clausal` (ruled order below), so the
  translator's "a twin exists, read no export list" shortcut still matches
  what the hook loads; only its comment ("seam twin") goes stale.  Fix it
  or retire the translator first.
- Prose in `docs/**/*.md` naming `.clausal` as seam source (item 5) is not
  swept; only the fences are.
- RULED 2026-10-01 (operator), DONE on this branch: the Prolog group is
  `(*CLAUSAL_PROLOG_SUFFIXES, PROLOG_SUFFIX)` (`_suffixes.prolog_suffixes()`),
  so after the flip `name.clausal` beats `name.pl` in one directory for ANY
  importer (a `.pl` importer may use a `.clausal` module).  Full finder order
  per path entry, before the flip: `[.clausal, .seam]` then `[.pl]`; after:
  `[.seam]` then `[.clausal, .pl]`.  Pinned in
  `tests/test_extension_flip_prep.py` (simulated flip).

## Why this file exists

A downstream user named the gap: this class has a third tense. Not stale, not broken, but
SCHEDULED to become false. A sweep for wrong statements returns nothing, because they are
not wrong yet. So the inventory has to be taken in advance and re-read at the flip, and it
has to live somewhere the flip will actually consult.

The ruling being prepared for: seam files become `.seam`; `.clausal` becomes the ISO-like
surface; `.pl` stays pure ISO. So at the flip `.clausal` STOPS meaning "seam source" and
starts meaning something a seam loader must not touch.

## The good news, measured

The mechanical half is genuinely centralised. Every consumer of the suffixes reads
`clausal/_suffixes.py` — **12 files** import it, with no exceptions left as of 820dc66f (the
three sites that did not are what 820dc66f fixed). Count it rather than trusting this line:
`git ls-files -z 'clausal/*.py' | xargs -0 /usr/bin/grep -l '_suffixes import' | wc -l`. So the finder, the formatter, the rewriter, the test runner, the
diagnostics and the doc-snippet checker all follow the tuple automatically:

    clausal/import_hook.py:855      PredicateFinder._extensions = CLAUSAL_SUFFIXES
    clausal/import_hook.py:865      PrologFinder._extensions   = (PROLOG_SUFFIX,)

Changing `CLAUSAL_SUFFIXES` to `(".seam",)` moves the loader dispatch for every one of them
in one edit. **Do not read that as "the flip is one line".** It is one line for the CODE and
not for anything a human reads.

## The items — prose that flips from true to false

**1. Twenty message strings, and BOTH groups need editing, at different times.** -- **DONE 2026-10-01** (e209ee21): every one reads the tuples (`SEAM_SUFFIX`, `suffix_list`, `seam_suffixes_text`), correct in both states; the sweep reports only the CSS false positive.
See `todo/done/messages-name-only-the-old-suffix-2026-09-10.md` for the inventory and the sweep.

- The 12 naming ONLY `.clausal` are INCOMPLETE today (they omit the alias) and become
  WRONG at the flip (they name the ISO surface as though it were seam source).
- The 8 naming BOTH are CORRECT today and become WRONG at the flip, in the opposite
  direction: "format .clausal (or .seam) source" would offer the seam formatter for ISO
  files. These are the third-tense ones. Fixing the first group before the flip does not
  touch them, and a sweep for "names only the old suffix" will never flag them.

The single worst line is in `clausal/logic/seam.py` — "host this code in a `.clausal`
file" — which instructs the reader to put seam code in what will be the ISO surface. The
message is implicitly concatenated: the sweep reports it at the node's first line, 312, and
the suffix itself is on 314. Edit by content, not by line number.

**2. The suffix module's own docstring.** -- **DONE 2026-10-01**: it now describes two surfaces and the flip as the two-tuple edit; `strip_clausal_suffix` says it strips a SEAM suffix. `clausal/_suffixes.py` opens with "``.clausal``
and ``.seam`` are aliases for one another: both carry the same Python-seam syntax". That is
the sentence the whole aliasing design rests on, and it is precisely what stops being true.
Its `strip_clausal_suffix` docstring example follows it.

**3. REMAINING (in the flip landing; see 'Tests that pin the PRE-flip state').** The comment is reworded (DONE); the tie-break test is not touched yet. `CLAUSAL_SUFFIXES` is documented as "in finder priority order. Order matters where two
files share a stem in one directory."** At the flip there is no tie to break, because the
two suffixes stop being alternatives for the same thing. The comment and the tie-break
tests in `tests/rewrite/test_cli.py` both encode a rule that becomes vacuous rather than
wrong — decide whether to delete or repoint them, and do not let a vacuously-passing test
stand in as evidence of anything.

**4. Anything that says a `.clausal` file is loaded by `PredicateLoader`.** -- **DONE 2026-10-01** for the engine: `PredicateFinder`/`PrologFinder` docstrings name the seam and Prolog groups by tuple; the dispatch itself is by surface (8180d533). After the flip
that dispatch is the bug, not the behaviour. `import_hook.py:854`'s docstring says it
outright.

**5. Docs.** -- **PARTLY DONE 2026-10-01** (3fddf3eb): the 1159 seam blocks in `docs/` are fenced ```seam (counts unchanged, see the commit); `packages/*/docs` fences and the prose sweep REMAIN. Not inventoried here — this file is code-side. Someone should sweep
`docs/**/*.md` for the same three tenses before the flip. Note the fenced blocks are already
lint-clean (1045 scanned, 1 hit, an archived design spec), so the risk is prose, not code.

**6. `end_module/1` becomes REQUIRED for `.clausal` files -- by design, with no code change.** -- **DONE (nothing to do)**; the finder now hands Clausal Prolog files to `NativePrologLoader`, which passes the path to `iso_l3.lower_source`, so the requirement fires (exercised by `tests/test_extension_flip_prep.py`).
`clausal/end_module.py` keys the "require end_module" default by SURFACE
(`REQUIRE_END_MODULE_DEFAULTS`: `pl` no, `clausal_prolog` yes), and `surface_of` reads
`_suffixes.CLAUSAL_PROLOG_SUFFIXES` (empty today). Moving `.clausal` into that tuple at the
flip makes every `.clausal` MODULE file (one with `:- module/2`) fail to load unless it ends
with `:- end_module(Name).` (or `CLAUSAL_REQUIRE_END_MODULE=0` / the file's own
`set_prolog_flag(require_end_module, false)`). The Prolog loader that takes `.clausal` must
pass the file's path (or `surface=`) to `iso_l3.lower_source`; the NativePrologLoader
already does. Plan the Clausal-Prolog `.clausal` files to carry end_module from the start.
Seam files keep their exemption: `surface_of` names `.seam` `seam`, which has no entry.

## Ordering constraint

The rename of every seam file must COMPLETE before `CLAUSAL_SUFFIXES` drops `.clausal`,
or every unrenamed file stops loading at once. The reverse order is safe: dropping the
suffix last means a renamed file works throughout, because both spellings load until the
moment they do not.

Engine note carried forward from the earlier handoff, still true and still a trap: in one
directory `name.clausal` beats `name.seam`, so a stale twin wins silently. The rename must
MOVE, never copy.

## How to use this file

At the flip, re-read it and treat every item as a defect to be fixed in the same landing,
not afterwards. Then delete the file — its whole value is that it is read once, at a moment
no sweep can identify from the code alone.
