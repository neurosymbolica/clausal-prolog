# fix-A07: clpb doc drift (test count, C comment, dead HASH_KEY)

**Finding:** A07-F011 (doc-drift, minor).

- `docs/clpb.md` "Test coverage" box says `tests/test_clpb.py` has 87 tests;
  the file has 113.
- `_clpb_core.c:31-33` comment claims `is_bdd_true/false` "also accepts value
  comparison as fallback" — they are pointer-comparison only (correct given
  the small-int cache, but the comment lies).
- `clausal/logic/clpb.py:44` `HASH_KEY = "clpb_hash"` is defined and exported
  in `__all__` but referenced nowhere in the codebase — remove or document.
