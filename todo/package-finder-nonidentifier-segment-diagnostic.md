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
