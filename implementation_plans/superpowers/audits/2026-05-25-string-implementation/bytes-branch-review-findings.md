# Bytes-as-Lists Branch Review — Findings Ledger

**Reviewed branch:** `feature/bytes-as-lists` (merged to `main` via fast-forward)
**Review date:** 2026-06-19
**Method:** multi-agent branch review, 6 surfaces in parallel (SegBytes term,
C extensions, Python seg-machinery, compiler + first-arg indexing, builtins +
DCG + type-checks, tests + spec alignment).
**Sibling of:** [findings.md](findings.md) (the 2026-05-25 string-implementation
audit). This is its bytes (codes-model) analog; the findings below reference the
string-audit F-codes they mirror.
**Status:** all 6 findings **fixed** in commit `910c1e7`. Every finding has a
named regression test (see each entry).

## Root cause

Five of the six defects share one root cause: `SegBytes` (the codes-model analog
of `SegString`) was given its construction/walk/unify surface but **not** the
groundness machinery its sibling has. The green 242-test suite hid this because
nothing exercised a `SegBytes` *through* the builtins — the path on which the
crashes live.

## Summary

| ID | Severity | Title | Fix location | Regression test |
|------|----------|-------|--------------|-----------------|
| BR-01 | critical | `SegBytes.is_ground()` missing → builtins crash | `clausal/terms.py:1191` | `TestSegBytesIsGround`, `TestSegBytesThroughBuiltins` |
| BR-02 | critical | `SegBytes.__occurs_check__()` missing → unsound | `clausal/terms.py:1195` | `TestSegBytesOccursCheck` |
| BR-03 | high | `_is_ground` blind to `SegBytes` → bad type-checks | `clausal/logic/builtins/_helpers.py:201,246` | `TestNonGroundSegBytesGuard` |
| BR-04 | medium | `same_length/2` bytes-blind | `clausal/logic/builtins/lists.py:862,881` | `TestSameLengthBytes` |
| BR-05 | high (test) | First-arg index never built in tests (criterion 5 unproven) | `tests/test_bytes_indexing.py` | `TestBytesIndexBuckets` |
| BR-06 | medium (test) | Doc-example fixture never executed | `tests/test_bytes_doc_examples.py` | `test_bytes_doc_examples_all_pass` |

## Findings

### BR-01 — `SegBytes.is_ground()` missing; list builtins crash

- **Severity:** critical (bug)
- **Status:** fixed in `910c1e7`
- **Location:** `clausal/terms.py` — `SegBytes` (added at `:1191`). Crash sites:
  `clausal/logic/builtins/lists.py:69` (`_as_items`) and `:100` (`_was_bytes`).
- **Mirrors:** `SegString.is_ground()` (`clausal/terms.py:852`).

**Symptom:** `SegBytes` defined `__walk__`/`__unify__`/`__len__`/`__iter__` but
no `is_ground()`. Both `_as_items` and `_was_bytes` call `.is_ground()` on a
value that may be a `SegBytes`, so **every** list-library predicate (append,
length, member, nth, reverse, sort, msort, select, set-ops, split_with, …) given
a `SegBytes` raised `AttributeError`. Even a fully ground `SegBytes` crashed.
This is the feature's headline workflow: a DCG builds a `SegBytes` remainder,
then a list-library predicate operates on it.

**Reproducer:**
```python
from clausal.logic.solve import call
from clausal.logic.variables import Var
from clausal.terms import SegBytes
# AttributeError: 'SegBytes' object has no attribute 'is_ground'
list(call("reverse", SegBytes([b"abc"]), Var(), module=mod))
```

**Fix:** add `is_ground()` returning `isinstance(self.__walk__(), bytes)`.

**Regression test:** `tests/test_segbytes.py::TestSegBytesIsGround`;
`tests/test_bytes_list_builtins.py::TestSegBytesThroughBuiltins`
(`reverse`/`length` of a `SegBytes`).

---

### BR-02 — `SegBytes.__occurs_check__()` missing; `unify_with_occurs_check` unsound

- **Severity:** critical (bug — soundness)
- **Status:** fixed in `910c1e7`
- **Location:** `clausal/terms.py` — `SegBytes` (added at `:1195`). C dispatch:
  `clausal/logic/variables/_variables.c` `do_occurs_check` (`:913`), which on a
  missing `__occurs_check__` hook clears the error and returns 0 ("does not
  occur").
- **Mirrors:** `SegString.__occurs_check__()` (`clausal/terms.py:865`).

**Symptom:** With no hook, `occurs_check(v, SegBytes([b"x", VarSeg(v)]))` returned
`False` where it must return `True`. `unify_with_occurs_check` over a `SegBytes`
would therefore bind a variable to a term containing itself (a cyclic term) —
silently defeating the occurs check. The identical `SegString` correctly returned
`True`.

**Reproducer:**
```python
from clausal.logic.variables import Var, occurs_check
from clausal.terms import SegBytes, VarSeg
v = Var()
occurs_check(v, SegBytes([b"GET", VarSeg(v)]))   # was False; must be True
```

**Fix:** add `__occurs_check__(var)` iterating `VarSeg` segments and delegating
to `occurs_check`.

**Regression test:** `tests/test_segbytes.py::TestSegBytesOccursCheck`.

---

### BR-03 — `_is_ground` not taught about `SegBytes`; `is_list/1`, `is_codes/1`, `ground/1` wrong

- **Severity:** high (bug)
- **Status:** fixed in `910c1e7`
- **Location:** `clausal/logic/builtins/_helpers.py` — `_is_ground_py` (added
  branch at `:201`) and the C-wrapper short-circuit (`:246`). Affects
  `clausal/logic/builtins/type_checks.py` `is_list/1`, `is_codes/1`, `ground/1`.
- **Mirrors / re-introduces:** [F083](findings.md) (the same gap previously fixed
  for `SegList`/`SegString`), here re-introduced for bytes.

**Symptom:** `_is_ground_py` had `SegList`/`SegString` branches but none for
`SegBytes`, so a non-ground `SegBytes` fell through to `return True`. The C
wrapper likewise only short-circuited `(SegList, SegString)`. A `SegBytes` still
holding an unbound `VarSeg` was reported **ground**, so `is_list/1` and
`is_codes/1` (which guard with `_is_ground`) **wrongly succeeded**, and
`ground/1` wrongly succeeded.

**Reproducer:**
```python
from clausal.logic.builtins._helpers import _is_ground
from clausal.logic.variables import Var
from clausal.terms import SegBytes, VarSeg
_is_ground(SegBytes([b"GET", VarSeg(Var())]))   # was True; must be False
```

**Fix:** add a `SegBytes` branch to `_is_ground_py` (mirroring the `SegString`
block) and include `SegBytes` in the C-wrapper short-circuit.

**Regression test:** `tests/test_bytes_type_checks.py::TestNonGroundSegBytesGuard`.

---

### BR-04 — `same_length/2` bytes-blind

- **Severity:** medium (design-gap)
- **Status:** fixed in `910c1e7`
- **Location:** `clausal/logic/builtins/lists.py` — `_same_length__2` (`:868`,
  inline `isinstance(., (list, str))` omitted bytes) and `_fresh_same_shape`
  (`:846`).

**Symptom:** Unlike length/member/nth (which route through the bytes-aware
`_as_items`), `same_length/2` checked sequence-ness inline with
`isinstance(., (list, str))`, omitting `bytes`. So `same_length(b"abc", b"xyz")`
**failed** (should succeed; both length 3), and the Var-placeholder direction
produced no bytes-shaped fresh term.

**Reproducer:**
```python
sum(1 for _ in call("same_length", b"abc", b"xyz", module=mod))   # was 0; must be 1
```

**Fix:** add `bytes` to both seq checks; add a `SegBytes` branch to
`_fresh_same_shape` (yielding a `SegBytes` of fresh `VarSeg` holes, bytes-shaped,
mirroring the `SegString` case — input-type-wins).

**Regression test:** `tests/test_bytes_list_builtins.py::TestSameLengthBytes`.

---

### BR-05 — First-arg index never built in tests; spec criterion 5 unproven

- **Severity:** high (test quality / coverage)
- **Status:** fixed in `910c1e7`
- **Location:** `tests/test_bytes_indexing.py`. The fixture had **3** clauses but
  `_INDEX_THRESHOLD == 4` (`clausal/logic/compiler/arg_index.py:38`), so
  `_build_first_arg_index` returned `None` and dispatch fell back to a linear scan.

**Symptom:** The existing `sum(...) == 1` assertion proved only that a solution
exists under linear dispatch — it did **not** exercise the bytes index bucket,
which is exactly what spec success-criterion 5 (bytes-literal heads bucket with
int-list callers) demands. Classic `count == 1` tautology: it could not
distinguish the indexed `==`-bucket path from the linear unify-guard path. (The
canonicaliser itself *was* unit-tested; the integrated indexed path was not.)

**Fix:** add `≥4` bytes-literal clauses so the index builds, and assert at the
index-structure level (`_build_first_arg_index(...)["buckets"]` contains the
bytes-literal keys; an int-list head canonicalises into the same bucket).

**Regression test:** `tests/test_bytes_indexing.py::TestBytesIndexBuckets`.

---

### BR-06 — Doc-example fixture never executed

- **Severity:** medium (test quality / doc-rot)
- **Status:** fixed in `910c1e7`
- **Location:** `tests/fixtures/docs/bytes_as_lists_examples.seam` (24 `Test/1`
  clauses). The only consumer, the doc-snippet coverage checker, merely
  regex-checks the file exists and contains `Test(` — it never loads or runs it.

**Symptom:** The fixture header claims "every Test/1 clause here is executed by
the test suite, so the examples in the documentation are guaranteed to stay
correct." Untrue: nothing executed the clauses (the file was not even verified to
parse). All 24 pass today, but a future implementation regression would let the
documented snippets rot silently.

**Fix:** new test that `_load_module`s the fixture and drives `Test/1`, asserting
all 24 clauses succeed (and that names are unique, catching silent drops).

**Regression test:** `tests/test_bytes_doc_examples.py::test_bytes_doc_examples_all_pass`.

## Surfaces that passed clean

For the record, three of the six reviewed surfaces had **no** defects:

- **C extensions** (`_list_unify.c`, `_variables.c`) — highest-risk surface;
  refcounting, borrowed/owned discipline, 256/overflow/non-int/empty handling,
  error hygiene, and str/bytes type isolation all verified under empirical stress.
- **Python seg-machinery** (`body_star_unify.py`, `list_unify.py`,
  `_seg_helpers.py`) — C-vs-Python fallbacks verified differentially identical;
  no over-promotion; multi-star correct.
- **Compiler + first-arg indexing** (`head_match.py`, `arg_index.py`,
  `predicate.py`) — index-key symmetry confirmed both directions; nested literals
  and the MatchValue→unify-guard migration correct. (One dormant, unreachable
  `bytes` gap noted in `list_dispatch.py`, outside the reviewed surfaces.)
