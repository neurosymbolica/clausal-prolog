# `snake_to_pascal` has no caller; it survives only as a re-export

**Filed** 2026-09-10, engine lane, at the landing of
`feat/titlecase-is-an-error-2026-09-10` (e0460d12).
**Owner** the export lane, by agreement — see "Sequencing" below.

## What

`clausal/tools/prolog_dialect.py:111` defines `snake_to_pascal`, documented as
"Convert Prolog snake_case to clausal PascalCase". Nothing calls it.

Measured on e0460d12, not recalled:

    grep -rn "snake_to_pascal" clausal/        # 2 hits, both in clausal_to_prolog.py
      clausal/tools/clausal_to_prolog.py:39    #   the import
      clausal/tools/clausal_to_prolog.py:49    #   the __all__ entry

Neither is a call site. The `.pl` importer stopped PascalCasing predicate
names in this branch — names now cross unchanged, because a TitleCase
identifier in a Clausal position is a load-time error, so a name the function
produced could not load. Its sibling `pascal_to_snake` IS still live: the
export direction still calls it, and the export lane confirmed their repo
imports `pascal_to_snake` only.

## Why it is not already done

Removing a name from `clausal_to_prolog.__all__` is an export-surface change.
The export lane asked for it not to ride in the same window as their `.seam`
rename sweep, where a new failure would have two candidate causes. That is the
whole reason this is a todo and not a commit.

## Exit criterion

The export lane's `.seam` rename sweep has landed and been verified. Then:
delete `snake_to_pascal` from `prolog_dialect.py`, its import in
`clausal_to_prolog.py:39`, and its `__all__` entry at :49.

Before deleting, re-run the grep above rather than trusting this file — it is
a fact with a shelf life, and an out-of-tree consumer may have appeared.
`_get_dispatch`-style out-of-tree implementors are a real pattern in
`packages/`, so check there too, and in any sibling tree that consumes this
one:

    grep -rn "snake_to_pascal" packages/

If an out-of-tree caller exists, this becomes a deprecation rather than a
deletion.

## Not in scope

`pascal_to_snake` stays. The export direction is a different question from the
import direction, and Clausal source that a program builds programmatically
(rather than loads) can still carry names the lint would refuse.
