# Extension-flip checklist: what is TRUE today and becomes FALSE at the flip

**Filed** 2026-09-10, engine lane, at 820dc66f. Engine side only; each other tree needs its
own. **Not a bug list.** Every item here is correct right now, which is exactly why no sweep
run today will find it. The trigger is the landing, not the code.

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

**1. Twenty message strings, and BOTH groups need editing, at different times.**
See `todo/messages-name-only-the-old-suffix-2026-09-10.md` for the inventory and the sweep.

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

**2. The suffix module's own docstring.** `clausal/_suffixes.py` opens with "``.clausal``
and ``.seam`` are aliases for one another: both carry the same Python-seam syntax". That is
the sentence the whole aliasing design rests on, and it is precisely what stops being true.
Its `strip_clausal_suffix` docstring example follows it.

**3. `CLAUSAL_SUFFIXES` is documented as "in finder priority order. Order matters where two
files share a stem in one directory."** At the flip there is no tie to break, because the
two suffixes stop being alternatives for the same thing. The comment and the tie-break
tests in `tests/rewrite/test_cli.py` both encode a rule that becomes vacuous rather than
wrong — decide whether to delete or repoint them, and do not let a vacuously-passing test
stand in as evidence of anything.

**4. Anything that says a `.clausal` file is loaded by `PredicateLoader`.** After the flip
that dispatch is the bug, not the behaviour. `import_hook.py:854`'s docstring says it
outright.

**5. Docs.** Not inventoried here — this file is code-side. Someone should sweep
`docs/**/*.md` for the same three tenses before the flip. Note the fenced blocks are already
lint-clean (1045 scanned, 1 hit, an archived design spec), so the risk is prose, not code.

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
