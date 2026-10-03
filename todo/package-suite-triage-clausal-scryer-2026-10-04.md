# clausal-scryer: package-suite failures triaged (2026-10-04)

Box run on 1c5ee5a0: **1 failed**. After feat/package-followups-2026-10-04:
**0 failed**.

| Group | Class | Count | Representative node id | Status |
|---|---|---|---|---|
| `foo(X) :- X > 0, !.` expected to round-trip with its cut; the .pl translator refuses cut (`PrologTranslationError: Cut (!/0) cannot be translated`) | BY-DESIGN (Clausal is cut-free, ruled) | 1 | `packages/clausal-scryer/tests/test_scryer_backend.py::TestScryerDialectFeatures::test_scryer_cut` | rewritten as `test_scryer_cut_is_refused`, asserting the refusal |

Remaining failures: none.
