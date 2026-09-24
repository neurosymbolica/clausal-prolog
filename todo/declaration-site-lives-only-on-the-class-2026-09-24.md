# A predicate's declaration SITE lives only on the class — one diagnostic line goes quiet at the flip

**Found:** 2026-09-24, fixing F1 rows 27/29. **Minor; flip design.**

`PredicateMeta` records `_registered_at` (`(file, line)` of the declaration)
at mint time (`predicate.py`, `_source_site`). Readers:

* `describe_imported_predicate_redefinition` — the "f is declared at
  file:line" line of the load channel's clause-clobber refusal. Now passed in
  as `declared_at=getattr(pred_cls, "_registered_at", None)` by
  `compiler_v2._redefinition_error`, so after the flip it is `None` and the
  line is omitted. Everything else in that message is era-agnostic
  (`tests/test_import_origins_both_eras.py` pins it, excluding this line).
* `predicate.py` ~281, ~330, ~1344 — other class-side readers; not audited here.

No row or db field holds the site. Decide whether it moves to the row
(stamped at declaration) or is dropped from the messages.
