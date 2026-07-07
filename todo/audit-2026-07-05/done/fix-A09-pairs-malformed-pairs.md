# fix(A09-F018): pairs_* silently drop malformed pairs (+ IndexError on short ones)

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/findings.md A09-F018 (+ the pairs half of A09-F012)
**Tests:** tests/audit_2026_07_05/test_09_builtins.py::test_F018_pairs_keys_values_skips_junk, ::test_F012_pairs_values_short_pair (xfail — flip to pass)

## Bug

pairs.py:16-17/39/52 build `[deref(p)[i] for p in pairs_val if
isinstance(deref(p), list)]` — a non-list entry is silently SKIPPED
(`pairs_keys_values([[1,"a"],"junk"],K,V)` succeeds with K=[1]), and a
too-short list entry hits `[1]` → raw IndexError. Also len>2 entries are
silently accepted with extras ignored.

## Fix direction

Validate each pair once: deref, require list of len == 2; on violation fail
(or type_error("pair", p) per A09-D002). One shared helper for the three
predicates; group_pairs_by_key already validates length — align shapes.

## Acceptance

- Both xfails pass; well-formed pair lists unchanged (regression:
  test_regression_* in the file stay green).
