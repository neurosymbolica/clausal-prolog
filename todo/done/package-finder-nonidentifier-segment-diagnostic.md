# Clearer finder diagnostic when a dotted import fails on a non-identifier path segment

**Priority:** DX / diagnostics (not a correctness bug — resolution behaviour is correct; only the error message is unhelpful).

## Motivation
Surfaced repeatedly during the clausify-domains hierarchical-namespace migration (54 domains
-> `eu.banking.crr_lcr` etc., using the landed `__init__.clausal` package resolution). Two
recurring failure shapes each produced a bare, misleading error that cost real debugging time:

1. **Hyphenated intermediate dir.** `-import_from(eu.state_aid.gber_…, [...])` when the dir on
   disk is `eu/state-aid/` (hyphen) fails with `ModuleNotFoundError: No module named 'eu.state_aid'`
   — even though `eu/state-aid/` plainly exists. The operator sees "no module" while staring at
   the directory. (Python package segments must be valid identifiers, so `state-aid` cannot be the
   `state_aid` segment — correct, but the message doesn't say so.)
2. **Digit-leading segment.** A dir like `42usc423-ssdi-…` -> segment `42usc423_…` is an invalid
   Python identifier; the import fails opaquely rather than saying why.

## Goal
When the `.clausal` package/module finder (`clausal/import_hook.py` `_ExtensionFinder.find_spec`,
the package branch that matches `<dir>/__init__.clausal`) fails to resolve a dotted name, and a
SIBLING directory exists that differs from the wanted segment only by (a) `-`↔`_`, or (b) is a
non-identifier for another reason (leading digit), emit a targeted diagnostic instead of letting
the bare `ModuleNotFoundError` propagate. E.g.:

    dotted import 'eu.state_aid' not found, but sibling dir 'eu/state-aid/' exists —
    package directories must be valid identifiers; rename 'state-aid' -> 'state_aid'.

    package segment '42usc423_…' begins with a digit — a package dir cannot start with a digit;
    rename the directory to be letter-led.

## Where
- `clausal/import_hook.py` :: `_ExtensionFinder.find_spec` — in the package branch, when no
  `<dir>/tail/__init__.clausal` matches, before returning `None`: scan `search_dirs` for a sibling
  entry whose name normalises (hyphen->underscore) to `tail`, or whose name would be `tail` but is
  a non-identifier, and raise/warn with the actionable message. Must NOT change resolution
  behaviour for valid names, and must stay cheap (only runs on the miss path). A `ClausalLintWarning`
  (as the stdlib-shadow guard already uses) or a raised `ModuleNotFoundError` subclass with the
  enriched message are both acceptable — pick per the finder's existing error conventions.

## Acceptance
- Importing `a.b_c` when only `a/b-c/__init__.clausal` exists -> error names the hyphen mismatch
  and the fix, not a bare "No module named 'a.b_c'".
- Importing a digit-leading segment -> error explains the identifier rule.
- Valid dotted imports unaffected; the diagnostic only fires on the resolution-miss path; no
  measurable overhead on the hot success path.

## Notes
- Corpus-side mitigations already shipped (not blocking this): the migration tool
  (`clausify-domains/_tools/migrate_namespace.py`) now underscores all path segments and
  pre-flight-rejects digit-leading segments. This todo is purely to make the LANGUAGE's own error
  helpful for anyone hand-authoring dotted imports.

---

## FIXED — 2026-07-29

Real, and worse than reported: two defects, not one. But both the location and
one of the two acceptance criteria in this todo were wrong.

### Triage

**The premise was half-stale.** The "bare, misleading error" this todo describes
had already been partly addressed by the case-2 diagnostic in
`clausal/import_diagnostics.py` (`_describe_missing_module`), which landed after
this todo was filed. For the *flat* shape (`-import_from(eu.state_aid, [...])`)
today's message was not bare at all:

    ModuleNotFoundError: No module named 'eu.state_aid'
      -import_from(eu.state_aid, [AidOk])
        in top.clausal
      names a module that does not exist: no .clausal file, .pl file or Python
      module called 'eu.state_aid' is on the import path. There is therefore no
      export list to show — this is a MISSING module, not a module that exports
      nothing.
      -> fix the module path (check spelling and package prefix), or create that
         module.

That is not terse, it is **false**: `eu/state-aid/` *is* on the import path. A
reader is told the file is absent, so they check spelling (finding nothing
wrong), then follow the second half of the remedy and *create* a package they
already have. The stated remedy is actively harmful here.

**The shape this todo actually reports was not enriched at all.** The motivating
example is a hyphenated *intermediate* directory —
`-import_from(eu.state_aid.gber, [...])` — and CPython raises that with
`name='eu.state_aid'`, a strict *prefix* of the declared path.
`enrich_import_error` keyed on `exc.name in targets` (exact match), so it did not
recognise the failure as this file's own directive and returned `None`. The
author got CPython's raw one-liner with no directive, no file and no directory:

    ModuleNotFoundError: No module named 'eu.state_aid'

That second defect is independent of the naming diagnosis and would have kept
biting every intermediate-segment miss (missing module, typo, anything) even
after a sibling scan was added. It is fixed here too (`_prefix_target`).

**The `Where` section pointed at the wrong seam.** Not
`_ExtensionFinder.find_spec`. Returning `None` from `find_spec` is the *normal*
path for every import in the process — `PredicateFinder` is first on
`sys.meta_path`, so it declines thousands of times per run and `PathFinder`
picks up. A raise there would break unrelated imports, and a warning there has
no idea whether the import came from a `.clausal` file at all. The error path
that already owns this sentence, already knows the directive text and importer
file, and already runs only on failure, is `_describe_missing_module`. That is
where it went.

**Acceptance criterion 2 (digit-leading segment) is unreachable and was
dropped.** A digit-leading segment cannot be *written*, so it never reaches any
finder or loader:

    -import_from(42usc423_ssdi, [D])

    File "dig.clausal", line 1
        -import_from(42usc423_ssdi, [D])
                      ^
    SyntaxError: invalid decimal literal
        1 | -import_from(42usc423_ssdi, [D])
          |               ^

The caret is already on the exact character, from the syntax-error-source-line
work. "invalid decimal literal" is CPython's wording and is terse, but the
diagnostic is pointing at the right place and this is a *syntax*-diagnostics
concern, not a finder one. Left alone deliberately; a directory that can never
be named needs no import-time message because no import naming it can compile.

### Fix

`clausal/import_diagnostics.py`:

* `_prefix_target` — accept an `exc.name` that is a strict dotted prefix of a
  *declared* path, so an intermediate-segment miss is enriched. Only prefixes of
  the declared text count: an alias rewrite (`date_time` →
  `clausal.modules.py.date_time`, which fails at `clausal.modules.py` on a broken
  install) names a segment the author never wrote and cannot be quoted back at
  them, so those keep Python's own message.
* `_misnamed_path_entry` — on the miss path only, scan the search path the
  machinery actually used (`parent.__path__`, or `sys.path` for a top-level
  name) for a directory or `.clausal`/`.pl`/`.py` file whose name is *not* a
  Python identifier but normalises (`\W` → `_`) to exactly the wanted segment.
* `_describe_missing_module` — name the stopping segment when it differs from
  the declared path, and replace the "does not exist" sentence with the entry,
  the rule and the rename when a misnamed entry explains the miss.
* `_sentence` moved here from `predicate_diagnostics.py` (which now imports it),
  joining `_INDENT`/`_WIDTH`/`_arrow` in the one shared home.

The scan cannot fire where the old sentence was right, because its predicate is
a tautology rather than a guess: if an entry's name normalises to the segment
and is not an identifier, then it *cannot* be that segment. Two guards keep it
honest — a correctly-spelled entry anywhere on the search path aborts the scan
(the import then failed for some other reason: a directory with no `__init__`,
an unreadable file, a stale cache, and the neighbouring hyphen is not the
story), and an entry that is neither a directory nor a recognised source file is
skipped, so `state-aid.txt` is never offered as a package. Every other route
into `_describe_missing_module` — a genuine typo, a module never written, a
wrong package prefix, a missing third-party library, a misconfigured `sys.path`
— finds no candidate and keeps today's wording verbatim, pinned by
`TestGenuinelyAbsentModule`.

### Findings left open

* `_KNOWN_UNCOMPILABLE` in `tests/test_doc_snippet_coverage.py` is keyed by
  fence line number, and three of its four `import.md` entries were **already
  stale by 3 lines** before this change — which is why three `import.md` blocks
  sit in the expected-failure list of `test_no_raw_untested_blocks`. This change
  shifted all four by +36 to preserve that baseline exactly; it did not repair
  the staleness, because repairing it would change the documented baseline.
  Worth its own todo: a line-keyed allowlist silently un-allowlists a block
  whenever anyone adds prose above it, and silently allowlists whatever lands on
  the number.

### Design question — how wide should the scan's net be?

The scan currently claims a naming fault only for a non-identifier name. Two
neighbouring confusions reach the same code path and get today's "does not
exist" wording:

1. **Case mismatch** — `eu/State_Aid/` present, `eu.state_aid` wanted. Both are
   valid identifiers, so this is a genuine wrong-name, not an unnameable one.
2. **Correctly named directory with no `__init__.clausal`** and no matching
   submodule — the dir is right there and the import still fails.

Options: (a) leave both to the "does not exist" sentence; (b) extend
`_misnamed_path_entry` to a general near-miss report ("`eu/State_Aid/` is there;
did you mean …?"); (c) handle (2) only, since "the directory exists but is not a
package" is a different *fact* rather than a spelling guess.

Recommendation: **(c), later, as its own todo.** (b) turns a tautology into a
suggestion engine and reintroduces the misfire risk this fix was careful to
avoid — `_suggestions` already exists for name-level guessing and would be the
right tool if it is ever wanted. (2) is a fact the loader can state without
guessing, and is a common enough shape to deserve its own sentence; but it is a
different diagnosis with a different remedy (add an `__init__.clausal`) and does
not belong in this change.
