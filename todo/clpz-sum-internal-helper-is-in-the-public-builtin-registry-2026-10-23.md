# `$clpz_sum/3`, an internal helper, is in the public builtin registry

Filed: 2026-10-23, while moving `$meta_body_check/1` out of the registry.
Severity: low (a listing artefact, no wrong answer).

## What

`_BUILTINS` / `_DB_BUILTINS` (`clausal.logic.builtins._registry`) is the
engine's public builtin registry: tools enumerate it as the list of the
engine's builtins. A `$`-prefixed name cannot be written in source, so a
`$` helper there is internal plumbing that the listing should not show.
`('$clpz_sum', 3)` (`clausal/logic/builtins/clpz_names.py`, behind
library(clpz)'s `sum/3`, `clausal.stdlib.clpz`) is the one such entry.

It stays for now: removing it would move the downstream pins of the
listing. `tests/test_builtin_registry_has_no_internal_names.py` allowlists
exactly it and refuses any new one.

## Fix

Bind it the way `$meta_body_check/1` is bound: a `BuiltinPredicate` held
outside the registry (`clausal.logic.builtins.control.META_BODY_CHECK`),
reached through the compiled code's globals
(`compiler/predicate.py`'s `base_globals`) or the stdlib module that
defines `sum/3` over it. Then drop it from the allowlist, together with
the downstream pin update.
