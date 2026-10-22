# One local import name bound in two -import_from directives silently keeps the later

Filed 2026-10-22, found reviewing the unit-alias export fix. Severity: medium
(which import a name means depends on directive order, with no diagnostic).

## What / Repro

Within ONE directive the engine refuses a local name bound twice
(`[alias(f, h), alias(g, h)]` is a `SyntaxError` at load, CHANGELOG "A repeated
`-import_from` entry is one import"). Across two directives it does not:

```seam
-module(dup2, [p(X)])
-import_from(united_states, [alias(usd, money_unit)])
-import_from(australia, [alias(aud, money_unit)])
p(X) <- (X == 5(money_unit))
```

loads, and `p(X)` answers `5 (aud)`: the later binding wins (measured
2026-10-22). The same holds for predicates (`alias(f, h)` from `a`, then
`alias(g, h)` from `b`).

The `.pl` exporter refuses this when a unit alias is involved
(`_unit_import_aliases`), so the export does not pick one.

## Fix

In `compiler_v2._process_imports`: key the per-directive "bound twice" check
on the local name per MODULE (across all `-import_from` directives), and
refuse with the same message. Not done in the exporter fix on purpose.
