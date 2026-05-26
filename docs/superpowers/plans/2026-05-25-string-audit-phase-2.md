# String Implementation Audit — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land one fix commit per audit class, flipping the corresponding `tests/audit_2026_05_25/test_class_C<N>_*.py` xfails to passes. Cumulatively, this closes 75+ findings across 14 classes and restores the strings-as-lists contract.

**Architecture:** Class-by-class fixes in the Phase 0-recommended order (fix-blast-radius ascending). Each task = one fix commit. Each commit:
1. Implements the source-code fix in `clausal/`.
2. Removes `@pytest.mark.xfail(strict=True, ...)` markers from the corresponding Phase 1 test file for findings closed by the fix.
3. Updates or deletes lock-in tests in the pre-existing suite (`tests/test_*.py`) where applicable.
4. Runs the full pytest suite (`pytest tests/`) — **zero regressions allowed**.
5. Rebuilds C extensions when C source changes (`pip install -e . --no-build-isolation`).
6. Updates the ledger entry status: `open` → `fixed in <sha>` with a one-line summary in Notes.

**Tech Stack:** Python 3.13+, pytest 8+, clausal (editable install), C extension build via `setuptools` / `pip install -e .`. No new dependencies.

**Inputs:**
- Ledger: `docs/superpowers/audits/2026-05-25-string-implementation/findings.md` — every finding's Symptom + Expected + Notes (where the fix lives).
- Probes: `docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F<NNN>.py` — runnable reproducers.
- Phase 1 tests: `tests/audit_2026_05_25/test_class_C<N>_*.py` — adversarial xfails to flip.
- Test coverage inventory: `docs/superpowers/audits/2026-05-25-string-implementation/test_coverage.md` — identifies lock-in tests Phase 2 must update.
- Spec: `docs/superpowers/specs/2026-05-25-string-implementation-audit-design.md`.
- Phase 0 plan: `docs/superpowers/plans/2026-05-25-string-audit-phase-0.md`.
- Phase 1 plan: `docs/superpowers/plans/2026-05-25-string-audit-phase-1.md`.

**Out-of-scope for Phase 2:**
- `wontfix` items per spec (Phase 6 SegList-vs-SegList — `F030`; other deferred items).
- C7 doc-only findings beyond the targeted `docs/strings_as_lists.md` updates (no API redesign).
- `perf` items beyond F026 (F009 already a passing regression test; F078 deferred per Phase 1).
- New features beyond what closing the findings requires.

---

## Conventions used throughout this plan

### Removing xfail markers

When a fix closes a finding, find the corresponding test in `tests/audit_2026_05_25/test_class_C<N>_*.py` and remove **only** the `@pytest.mark.xfail(strict=True, reason="ledger F<NNN>: ...")` decorator above the test function. Keep the test body untouched — it stays as a regression guard.

If a test was parametrized (e.g. F054 was split into 8 cases, F073 into 6), remove the xfail marker once; all parametrized variants flip together.

### Updating ledger entries

After the fix lands, find the corresponding `### F<NNN>` entry in `findings.md` and:
1. Add a `**Status:** fixed in <sha>` line right after the `**Severity:**` line (or update an existing Status line — F046's status was `open`, change to `fixed in <sha>`).
2. Append to the Notes section: `Fixed in commit <sha> (Phase 2 Task <N>) — <one-line summary of the fix>.`

Do NOT remove the finding entry. The ledger is append-only history.

Update the summary table at the top of `findings.md` only if the change affects severity counts. (Closing a finding doesn't change its severity count; the table tracks discovered findings, not open findings. So usually no table update needed.)

### Lock-in test handling

The 6 lock-in tests in the pre-existing suite codify the buggy contract as intended behavior:

| Finding | Lock-in test location | Action when fix lands |
|---------|----------------------|----------------------|
| F033 | `tests/test_seglist_creation.py` | Update assertion to match new contract |
| F042 | `tests/test_seglist_creation.py` | Update assertion to match new contract |
| F067 | `tests/test_dcg.py` | Update assertion to match new contract |
| F080 | `tests/test_string_list_builtins.py` | Delete or invert assertion |
| F092 | `tests/test_term_inspection.py` | Update to assert independent copy |
| F093 | `tests/test_term_inspection.py` | Update assertion to count VarSegs |

Each fix task that touches one of these findings must include a step to update the lock-in test in the same commit.

### Rebuilding C extensions

When a fix changes `.c` files (notably C12, C16), rebuild before running tests:

```bash
cd /workspace/clausal-string_audit && pip install -e . --no-build-isolation --quiet
```

If `pip install` reports a build error, the C change has a syntax/type problem — fix before re-running.

### Commit message style

```
fix(<scope>): close <class> findings (F<n>-F<n>) — <one-line summary>

<one-paragraph: what changed in the source, which xfails flipped,
which lock-in tests updated, regression-suite verdict>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

`<scope>` reflects the primary surface touched: `terms`, `chars`, `lists`, `higher_order`, `dcg`, `type_checks`, `inspection`, `compiler`, `variables` (for `_variables.c`), `runtime` (for runtime/* files).

### Verification per task

After each fix commit:

```bash
# 1. Confirm the class's Phase 1 tests now pass:
pytest tests/audit_2026_05_25/test_class_C<N>_*.py -v
# Expected: previously XFAIL findings are now PASSED, no unexpected XPASS.

# 2. Confirm the full audit suite still works:
pytest tests/audit_2026_05_25/ -v 2>&1 | tail -10
# Expected: count of XFAIL drops by N (closed findings), PASS count rises by N.

# 3. Confirm pre-existing suite has zero regressions:
pytest tests/ --ignore=tests/audit_2026_05_25 -q 2>&1 | tail -5
# Expected: same pass/fail/xfail counts as the pre-Phase-2 baseline.
```

If step 1 shows `XFAIL` (the xfail marker is still present even though the test passes), remove the marker.
If step 1 shows `FAILED` (the test was updated but still fails), the fix is incomplete — investigate.
If step 3 shows new failures, the fix broke something — investigate before proceeding.

### When to pause for user input

The spec requires pausing before any change that alters a user-visible Clausal contract. Tasks **9 (C13 — F080)**, **12 (C9 — F054 row choices)**, **13 (C1 — type-source plumbing rule)**, **10 (C14 — args-of-list convention)**, and **15 (C4 — narrow vs broad fix)** require user adjudication. Don't make those design calls unilaterally; embed an `AskUserQuestion`-style pause in the task.

Otherwise: proceed without per-step gates.

---

## File-change index (read-only summary — task descriptions below have the detail)

| Task | Class | Source files modified | Test files updated |
|-----:|-------|----------------------|---------------------|
| 1 | C17 | `clausal/terms.py` (_multi_star_splits) | `tests/audit_2026_05_25/test_class_C17_perf_memory.py` |
| 2 | C7 | `docs/strings_as_lists.md` | (no test changes — doc-only) |
| 3 | C12 | `clausal/logic/builtins/chars.py` | `tests/audit_2026_05_25/test_class_C12_char_representation.py` |
| 4 | C16 | `clausal/logic/variables/_variables.c` | `tests/audit_2026_05_25/test_class_C16_ft_safety.py` |
| 5 | C5 | `clausal/terms.py` (SegList/SegString dunders) | `tests/audit_2026_05_25/test_class_C05_hash_eq_asymmetries.py` |
| 6 | C2 | `clausal/terms.py` (__unify__ entry point) | `tests/audit_2026_05_25/test_class_C02_nondet_first_only.py` |
| 7 | C8 | `clausal/terms.py` (sequence protocol) | `tests/audit_2026_05_25/test_class_C08_partial_term_shortcircuits.py` |
| 8 | C15 | `clausal/logic/compiler/arg_index.py` | `tests/audit_2026_05_25/test_class_C15_first_arg_indexing.py` |
| 9 | C13 | `clausal/logic/builtins/type_checks.py` + `_register_term_types` | `tests/audit_2026_05_25/test_class_C13_type_checks.py` + `tests/test_string_list_builtins.py` (F080 lock-in) |
| 10 | C14 | `clausal/logic/builtins/inspection.py` + `_register_term_types` (or equivalent) | `tests/audit_2026_05_25/test_class_C14_term_inspection.py` + `tests/test_term_inspection.py` (F092/F093 lock-in) |
| 11 | C3 | `clausal/logic/runtime/list_unify.py` + `body_star_unify.py` + `_list_unify.c` (likely) | `tests/audit_2026_05_25/test_class_C03_segstring_blindspots.py` |
| 12 | C9 | `clausal/logic/builtins/lists.py` + `higher_order.py` | `tests/audit_2026_05_25/test_class_C09_polymorphic_mode_matrix.py` |
| 13 | C1 | Many — type-source plumbing | `tests/audit_2026_05_25/test_class_C01_type_preservation.py` + `tests/test_seglist_creation.py` (F033/F042 lock-in) |
| 14 | C10 | `clausal/logic/builtins/dcg.py` + `clausal/templating/term_rewriting.py` | `tests/audit_2026_05_25/test_class_C10_dcg_phrase.py` + `tests/test_dcg.py` (F067 lock-in) |
| 15 | C4 | `clausal/logic/compiler/head_match.py` + `clausal/logic/database.py` | `tests/audit_2026_05_25/test_class_C04_head_literal_mismatch.py` |
| 16 | — | (Phase 3 sweep — no source changes) | (re-run audit + Phase 3 ledger appendix) |

---

## Task 1: C17 — `_multi_star_splits` combinatorial cost (F026)

**Findings closed:** F026.

**Source change:** `clausal/terms.py` `_multi_star_splits` (and its sibling helper in `clausal/logic/compiler/head_match.py` if the latter has a duplicate).

**Approach:** the current implementation generates every combination eagerly. F026's test asserts <1s for `_multi_star_splits(10, 20)`. The fix options:
- **Memoize** the recursion (the function is pure; same `(n_stars, remainder)` inputs always produce the same outputs).
- **Lazy iteration with an early cap** — accept an optional `max_splits` argument so callers can bail out early.
- **Restructure** to avoid building intermediate tuples.

Read F026's Notes for the implementer's preferred sketch; pick whichever fits without changing the caller contract.

- [ ] **Step 1: Read F026 entry + probe + Phase 1 test**

Read `### F026` in `findings.md`, `probes/probe_F026.py`, and `tests/audit_2026_05_25/test_class_C17_perf_memory.py::test_F026_multi_star_splits_bounded_for_moderate_input`. Identify exact expected behaviour: function must return <1s for `(10, 20)` while still enumerating every split (10M+) when fully consumed.

- [ ] **Step 2: Locate _multi_star_splits**

```bash
grep -rn "_multi_star_splits" clausal/ | head -20
```

It lives in `clausal/terms.py` (the canonical version) and possibly mirrored in `clausal/logic/compiler/head_match.py`. If both exist, fix both — keep them in sync.

- [ ] **Step 3: Implement the fix**

Replace the eager generator with one of:
- An iterative version using `itertools.combinations_with_replacement`.
- A memoized recursive helper that only generates the prefix and yields lazily.

Whichever you pick, preserve the contract: `_multi_star_splits(n_stars, remainder)` yields every tuple of `n_stars` non-negative ints summing to `remainder`. The order doesn't matter for callers — they're enumerating splits, not assuming an order.

- [ ] **Step 4: Confirm xfail flips to pass**

```bash
pytest tests/audit_2026_05_25/test_class_C17_perf_memory.py::test_F026_multi_star_splits_bounded_for_moderate_input -v
```

Expected: PASS (was XFAIL).

- [ ] **Step 5: Remove the xfail marker**

Edit `tests/audit_2026_05_25/test_class_C17_perf_memory.py` and remove the `@pytest.mark.xfail(strict=True, reason="ledger F026: ...")` decorator above `test_F026_multi_star_splits_bounded_for_moderate_input`. Keep the test function body unchanged.

- [ ] **Step 6: Run pre-existing suite for regressions**

```bash
pytest tests/ --ignore=tests/audit_2026_05_25 -q 2>&1 | tail -5
```

Expected: same baseline pass/fail/xfail counts (7749 passed pre-Phase 2).

- [ ] **Step 7: Update F026 ledger entry**

In `findings.md`, find `### F026`. Add `- **Status:** fixed in <sha>` after the Severity line. Append to Notes: `Fixed in commit <sha> (Phase 2 Task 1) — <one-line summary>.`

- [ ] **Step 8: Commit**

```bash
git add clausal/terms.py tests/audit_2026_05_25/test_class_C17_perf_memory.py \
        docs/superpowers/audits/2026-05-25-string-implementation/findings.md
git commit -m "$(cat <<'EOF'
fix(terms): close F026 _multi_star_splits combinatorial cost

Rewrites the eager-generator implementation to <approach summary>.
Phase 1 test_F026_multi_star_splits_bounded_for_moderate_input now
passes in <X>s (was 5.59s, threshold 1.0s); xfail marker removed.

Pre-existing pytest suite: unchanged (7749 passing). C17 row in
findings.md updated.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: C7 — Unicode/multi-codepoint documentation (F002, F003, F004, F007, F071, F074, F076)

**Findings closed:** 7 doc-only findings under C7.

**Source change:** `docs/strings_as_lists.md` — add a dedicated "Code-point vs grapheme" section that documents:
- Code-point (not grapheme) semantics for string indexing, splitting, unification.
- Multi-codepoint emoji and grapheme clusters (base+combining) behave as N independent characters.
- Surrogate halves (technically possible in Python `str`) are processed as code points.
- Multi-char list elements (e.g. `["ab", "c"]`) are rejected; only 1-char strs unify with str positions.
- `char_type` / `char_code` / `atom_chars` follow the same code-point rule.

**No test changes** — these are doc-only findings. The Phase 1 plan didn't write tests for C7.

- [ ] **Step 1: Read each C7 finding**

Read F002, F003, F004, F007, F071, F074, F076 in `findings.md`. Each describes a specific Unicode case (grapheme, NFC/NFD, multi-char list element, surrogate halves, etc.). Note the doc-only label.

- [ ] **Step 2: Read current docs/strings_as_lists.md**

Identify where the new section fits. Likely after the "Unification" section or as a sub-section under "Pattern Matching".

- [ ] **Step 3: Write the "Code-point vs grapheme" section**

Add a new H2 section:

```markdown
## Code-point vs grapheme semantics

Clausal's strings-as-lists contract operates at **code-point granularity**,
not grapheme granularity. This means:

- A multi-codepoint emoji like `"👍🏽"` (thumbs-up + skin-tone modifier)
  has `len("👍🏽") == 2` and unifies with `["👍", "🏽"]`, not `["👍🏽"]`.
- A base character followed by a combining mark — `"é"` written as
  `"é"` — has length 2 and unifies with `["e", "́"]`.
  The same character in precomposed form (`"é"`) has length 1
  and unifies with `["é"]`.
- Lone surrogate halves are processed as individual code points
  (their str is technically malformed Unicode but Python allows it).
- List elements that are multi-character strings (e.g. `["ab", "c"]`)
  are **rejected** by the per-element check; only 1-char list elements
  participate in str↔list unification.

This rule applies uniformly across:
- C-level `unify` (str ↔ list).
- `SegList` and `SegString` walks and unification.
- Head and body multi-star patterns over string targets.
- `phrase/2,3` and DCG terminals.
- `char_type`, `char_code`, `atom_chars`, `atom_codes`.
- All polymorphic list builtins (`append`, `length`, `member`, etc.).

If your application needs grapheme-aware processing (e.g. cursor
movement in a text editor), use the standard Python library
`unicodedata` or the third-party `regex` / `grapheme` packages
**before** handing the string to Clausal — Clausal sees code points.
```

- [ ] **Step 4: Cross-link relevant existing sections**

If the existing docs say something like "strings unify char-by-char", append "(code-point-by-code-point — see [Code-point vs grapheme](#code-point-vs-grapheme-semantics))".

- [ ] **Step 5: Update ledger**

For each of F002, F003, F004, F007, F071, F074, F076 in `findings.md`, add `- **Status:** fixed in <sha>` and a Notes line: `Doc-only fix landed in commit <sha> — documented in the "Code-point vs grapheme semantics" section of docs/strings_as_lists.md.`

- [ ] **Step 6: Commit**

```bash
git add docs/strings_as_lists.md docs/superpowers/audits/2026-05-25-string-implementation/findings.md
git commit -m "$(cat <<'EOF'
docs(strings_as_lists): close C7 findings (F002-F004, F007, F071, F074, F076)

Adds the "Code-point vs grapheme semantics" section documenting that
the strings-as-lists contract operates at code-point granularity, not
grapheme granularity. Covers multi-codepoint emoji, NFC/NFD
normalization, surrogate halves, and multi-char list element
rejection — uniformly across unification, SegList/SegString,
head/body patterns, DCG, and char/atom builtins.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: C12 — `chr()` range guard (F073)

**Findings closed:** F073 (×6 parametrized test cases).

**Source change:** `clausal/logic/builtins/chars.py` — wrap the three `chr()` call sites in `char_code/2`, `atom_codes/2`, `number_codes/2` with a range guard. When out-of-range (`< 0` or `>= 0x110000`), fail logically (return False / no solutions) instead of leaking the raw Python `ValueError`.

- [ ] **Step 1: Read F073 entry + probe + Phase 1 tests**

Read `### F073` in `findings.md` and `probes/probe_F073.py`. Open `tests/audit_2026_05_25/test_class_C12_char_representation.py` — note the 6 parametrized cases.

- [ ] **Step 2: Locate the chr() sites**

```bash
grep -n "chr(" clausal/logic/builtins/chars.py
```

Likely 3 sites: `char_code`, `atom_codes`, `number_codes`.

- [ ] **Step 3: Add a `_safe_chr` helper or inline guard**

Either approach (helper or inline) is fine. Inline is simpler:

```python
def char_code__2(...):
    ...
    if not (0 <= code < 0x110000):
        return  # logical failure — yields no solutions
    ch = chr(code)
    ...
```

Apply the same guard at `atom_codes` and `number_codes` sites where they call `chr()` on a list element.

- [ ] **Step 4: Confirm all 6 parametrized tests flip to pass**

```bash
pytest tests/audit_2026_05_25/test_class_C12_char_representation.py -v
```

Expected: 6 PASSED.

- [ ] **Step 5: Remove the xfail marker**

There's one xfail decorator (the parametrize marks the test function once). Remove it.

- [ ] **Step 6: Pre-existing suite check + ledger update + commit**

```bash
pytest tests/ --ignore=tests/audit_2026_05_25 -q 2>&1 | tail -5
# Update findings.md F073 status.
git add clausal/logic/builtins/chars.py tests/audit_2026_05_25/test_class_C12_char_representation.py \
        docs/superpowers/audits/2026-05-25-string-implementation/findings.md
git commit -m "$(cat <<'EOF'
fix(chars): close F073 chr() ValueError leak on out-of-range codes

Adds range guards (0 <= code < 0x110000) around the chr() call sites
in char_code/2, atom_codes/2, number_codes/2. Out-of-range codes now
fail logically (zero solutions) — catch/3 can intercept the failure
where previously the raw Python ValueError leaked through.

All 6 parametrized F073 tests pass; pre-existing suite unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: C16 — FT critical section in str↔list path (F011)

**Findings closed:** F011.

**Source change:** `clausal/logic/variables/_variables.c` — replace `PyList_GET_ITEM` with `PyList_GetItemRef` (Py 3.13+) or wrap the read in an `FT_CS_*` critical section. Per F011's Notes, the broader pattern (line 1103-1116 plain-list block) has the same hazard; fix both blocks.

- [ ] **Step 1: Read F011 entry + probe + Phase 1 test**

Read `### F011` in `findings.md`, `probes/probe_F011.py`, and `tests/audit_2026_05_25/test_class_C16_ft_safety.py`. Note that the Phase 1 test is `xfail(strict=False)` because GIL builds mask the race — after the fix, it will pass on both GIL and FT builds.

- [ ] **Step 2: Locate the unsafe reads**

In `clausal/logic/variables/_variables.c`:
- Lines 1135 (str↔list, `PyList_GET_ITEM(t2, i)`)
- Lines 1163 (list↔str, `PyList_GET_ITEM(t1, i)`)
- Lines 1107, 1113 (plain list↔list block — sibling hazard noted in F011)

- [ ] **Step 3: Apply the fix**

Use `PyList_GetItemRef` (returns a new strong reference; CPython 3.13+ FT-safe accessor):

```c
PyObject *elem = NULL;
if (PyList_GetItemRef(t2, i, &elem) < 0) return -1;
PyObject *deref_elem = var_deref(elem);
// ... existing logic using deref_elem ...
Py_DECREF(elem);  // release the GetItemRef strong ref
```

Adapt the existing logic so the new reference is properly decremented on every return path (success, failure, error).

If `PyList_GetItemRef` is unavailable in the build's Python headers, use `FT_CS_*` macros to wrap the index read — but `PyList_GetItemRef` is preferred per CPython docs for this exact pattern.

- [ ] **Step 4: Rebuild C extensions**

```bash
cd /workspace/clausal-string_audit && pip install -e . --no-build-isolation --quiet
```

If build fails, fix the C error and re-run.

- [ ] **Step 5: Confirm xfail flips**

```bash
pytest tests/audit_2026_05_25/test_class_C16_ft_safety.py -v
```

On GIL build, the test was already XPASSED with strict=False. After the fix, change the marker to strict=True (or remove entirely) since the fix should also be correct on FT.

- [ ] **Step 6: Pre-existing suite + ledger + commit**

```bash
pytest tests/ --ignore=tests/audit_2026_05_25 -q 2>&1 | tail -5
# Update findings.md F011 status.
git add clausal/logic/variables/_variables.c \
        tests/audit_2026_05_25/test_class_C16_ft_safety.py \
        docs/superpowers/audits/2026-05-25-string-implementation/findings.md
git commit -m "$(cat <<'EOF'
fix(variables): close F011 FT critical section in str↔list unify

Replaces PyList_GET_ITEM with PyList_GetItemRef in the str↔list and
list↔str branches of do_unify (lines 1135, 1163), plus the
neighbouring plain list↔list block (lines 1107, 1113) that shares
the same hazard pattern. Refcount discipline preserved on all return
paths including error.

F011 Phase 1 test now passes on GIL builds (was XPASSED with
strict=False); strict=True restored. Pre-existing suite unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: C5 — SegList/SegString hash/eq asymmetries (F017, F019, F025)

**Findings closed:** F017 (bug — Python eq/hash invariant violation), F019 (design-gap — __eq__ asymmetry), F025 (design-gap — __hash__ asymmetry).

**Source change:** `clausal/terms.py` — `SegList.__eq__`, `SegList.__hash__`, `SegString.__eq__`, `SegString.__hash__`.

**Approach:**
- For F017: make `SegString.__hash__` raise `TypeError` when non-ground (mirror SegList). The eq/hash invariant requires hashable + equal → equal hash; the current `id(self)` fallback violates this. Refusing to hash non-ground values is consistent with `SegList`.
- For F019: make both `__eq__` methods accept both `str` and `list` (and the other Seg* type). Symmetry restored.
- For F025: same hashability discipline — both Seg* types raise on non-ground hash, both return `hash(walked)` on ground.

- [ ] **Step 1: Read F017, F019, F025 + Phase 1 tests**

- [ ] **Step 2: Edit SegList.__eq__** to accept both str and list (and SegString). Currently it rejects str.

- [ ] **Step 3: Edit SegList.__hash__** to return `hash(walked)` when ground (currently always raises TypeError). Keep raising on non-ground.

- [ ] **Step 4: Edit SegString.__eq__** to accept both str and list (and SegList). Currently it only accepts str.

- [ ] **Step 5: Edit SegString.__hash__** to raise TypeError when non-ground (currently returns `id(self)`).

- [ ] **Step 6: Confirm 3 xfails flip**

```bash
pytest tests/audit_2026_05_25/test_class_C05_hash_eq_asymmetries.py -v
```

Expected: 3 PASSED.

- [ ] **Step 7: Remove 3 xfail markers + pre-existing suite + ledger + commit**

```bash
git commit -m "$(cat <<'EOF'
fix(terms): close C5 SegList/SegString hash/eq asymmetries (F017, F019, F025)

Symmetrises __eq__ (both Seg* types now accept str/list/sibling-Seg)
and __hash__ (both refuse on non-ground, both return hash(walked)
when ground). Restores Python's eq/hash invariant on SegString
(was violated by the id(self) fallback for non-ground).

Pre-existing suite unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: C2 — Non-det protocol exposure (F015, F016)

**Findings closed:** F015, F016.

**Source change:** `clausal/terms.py` — `SegList.__unify__` and `SegString.__unify__`. Currently both consume only the first split from their respective generators. The fix needs to expose all splits to the trampoline so backtracking finds them.

**Approach:** The `__unify__` protocol returns `bool | NotImplemented`. The trampoline expects deterministic unification; non-deterministic splits must be exposed via a different mechanism — likely:
- A new protocol hook `__unify_gen__(other, trail)` that returns an iterator over solutions, OR
- Driving the splits through a synthetic Var binding that backtracks naturally.

Read F015's Notes for the implementer's preferred approach. This may require a small change to the C-level `do_unify` dispatch as well, to recognize the new hook.

- [ ] **Step 1: Read F015, F016 + Phase 1 tests + probes**

- [ ] **Step 2: Design the fix**

Read the trampoline / solve.py code to understand how non-deterministic builtins (like `member/2`) expose multiple solutions. Mirror that pattern for SegList/SegString unification.

- [ ] **Step 3: Implement the fix in terms.py and (if needed) variables.c / variables/_capi.h**

- [ ] **Step 4: Rebuild C extensions if needed**

- [ ] **Step 5: Confirm 2 xfails flip**

```bash
pytest tests/audit_2026_05_25/test_class_C02_nondet_first_only.py -v
```

- [ ] **Step 6: Remove xfail markers + pre-existing suite + ledger + commit**

```bash
git commit -m "$(cat <<'EOF'
fix(terms): close C2 non-det SegList/SegString unify (F015, F016)

Exposes all valid splits via the trampoline instead of consuming only
the first from _seglist_unify_gen / _segstring_unify_gen. Backtracking
through [*A, *B] = [1,2,3] now yields all four splits.

Pre-existing suite unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: C8 — Seg* sequence protocol (F021, F022, F023, F024, F038, F039)

**Findings closed:** 6 findings.

**Source change:** `clausal/terms.py` — `SegList.__len__`, `__iter__`, `__contains__`, `__getitem__`; `SegString` equivalents; `_in_iter` in `clausal/logic/runtime/body_star_unify.py`. F023 also touches `SegString.__unify__(list)` to handle non-ground.

**Approach:** Replace bare `TypeError` with either:
- A typed Clausal exception (e.g. `ClausalNonGroundError`) — if the project has such a type.
- A defined sentinel value with a comment explaining the contract.
- A constrained result (for `__contains__`, return True if any concrete segment contains the element).

For F024 (malformed segments), assert preconditions early with a typed exception.

- [ ] **Step 1: Read all 6 findings + Phase 1 tests**

- [ ] **Step 2: Decide on the typed-exception strategy**

Look for an existing typed exception class in the codebase (e.g. `clausal.exceptions.ClausalTypeError`). Use it consistently across all six methods. If none exists, introduce a small one with a clear name like `PartialTermError`.

- [ ] **Step 3: Update SegList sequence-protocol methods**

`__len__`, `__iter__`, `__getitem__` on non-ground SegList → raise the typed exception with a descriptive message instead of `to_list()`'s bare TypeError.

`__contains__` on non-ground SegList → if `item` appears in any ConcreteSeg, return True; else return False with a NOTE that this is partial (or, alternatively, raise the typed exception — pick consistently with __len__).

- [ ] **Step 4: Update SegString sequence-protocol methods**

Mirror SegList.

- [ ] **Step 5: Update SegString.__unify__(list) for non-ground (F023)**

Currently returns NotImplemented for non-ground. Change to: walk the SegString first; if walks to str, delegate to the C-level str↔list unify path; if still non-ground SegString, build the equivalent SegList and delegate.

- [ ] **Step 6: Update _in_iter to handle SegString**

Currently routes through `iter(collection)` which calls `SegString.__iter__` (not implemented) → falls to `to_str()` → raises on non-ground. Add a SegString branch that either iterates ground SegStrings or raises typed-exception on non-ground.

- [ ] **Step 7: Confirm 6 xfails flip + remove markers + pre-existing suite + commit**

```bash
git commit -m "$(cat <<'EOF'
fix(terms): close C8 partial-term short-circuits (F021-F024, F038, F039)

SegList/SegString sequence-protocol methods (__len__, __iter__,
__contains__, __getitem__) and _in_iter now raise a typed
PartialTermError (or constrain) on non-ground inputs instead of
leaking bare TypeError. SegString.__unify__(list) handles non-ground
by walking + delegating. Malformed-segment construction asserts
preconditions early.

Pre-existing suite unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: C15 — First-arg indexing canonicalisation (F095)

**Findings closed:** F095. **Must precede Task 15 (C4).**

**Source change:** `clausal/logic/compiler/arg_index.py` — `_classify_*` / dispatch-key extraction functions. Coalesce str and char-list keys so a caller with one container type routes to a bucket containing clauses indexed by the other.

**Approach:** The current indexer treats `Foo("abc")` and `Foo(['a','b','c'])` as distinct keys. Fix: at the index-key computation site, canonicalize str keys to their char-list equivalent (or vice versa). Choose direction based on what's faster (str→list is O(N) char-list allocation; list→str is O(N) join when all elements are 1-char).

Pragmatic choice: canonicalize char-list-of-1-char-strs → str. This is the rarer compile-time direction.

- [ ] **Step 1: Read F095 + Phase 1 test + probe**

- [ ] **Step 2: Locate the index-key extraction site**

Per the implementer's notes from Task 13 of Phase 0, the relevant file is `arg_index.py` (see `_classify_list_key` at line 125-138 noted in F097). Read it.

- [ ] **Step 3: Apply the canonicalization**

In the bucket-key computation: when the head arg is a `list` of all-1-char-strs, treat it as `"".join(head_arg)` for index-key purposes; when the head arg is a `str`, leave it as-is. Both end up in the same bucket.

- [ ] **Step 4: Confirm xfail flips**

```bash
pytest tests/audit_2026_05_25/test_class_C15_first_arg_indexing.py -v
```

- [ ] **Step 5: Remove xfail marker + pre-existing suite + ledger + commit**

```bash
git commit -m "$(cat <<'EOF'
fix(compiler): close F095 first-arg indexing str/charlist canonicalisation

The first-arg index now canonicalises char-list-of-1-char-strs head
args to their str equivalent for index-key computation, so a caller
of either container type routes to a bucket containing both
clauses. Required for C4 (F046) to fully restore the strings-as-lists
contract at the dispatch layer.

Pre-existing suite unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: C13 — Type-check predicates (F080, F081, F082, F083, F084)

**Findings closed:** 5 findings, including F080 lock-in test.

### **PAUSE POINT — design choice required on F080**

F080's underlying question: should `is_list("abc")` succeed under the strings-as-lists contract? The lock-in test in `tests/test_string_list_builtins.py` asserts it fails. The design decision affects every program using `is_list/1`.

Three options:
- **A. Make `is_list("abc")` succeed** (per strict strings-as-lists). Aligns with how list builtins treat strings. Breaks the lock-in test (Phase 2 must update it).
- **B. Add a new `is_chars/1` predicate** that succeeds on both `is_chars("abc")` and `is_chars(['a','b','c'])`; keep `is_list/1` strict. Documents the distinction without breaking the lock-in.
- **C. Keep `is_list("abc")` failing**; downgrade F080 from design-gap to doc-only. Just document the gap.

**Before executing this task, ask the user which option to take.**

After the choice, proceed:

**Source change for all options:** `clausal/logic/builtins/type_checks.py` — register `string/1` and `atomic/1` (F081/F082), fix `ground/1` (F083), tighten `callable_/1` (F084).

**Source change specific to option A:** also change `is_list/1` to accept str + update the lock-in test.

**Source change specific to option B:** add `is_chars/1` registration.

Lock-in test handling per option:
- A: Edit `tests/test_string_list_builtins.py` (and any sibling cases) to assert `is_list("abc")` succeeds.
- B: Lock-in test unchanged.
- C: Lock-in test unchanged; F080 reclassified.

- [ ] **Step 1: Ask user for F080 option (A/B/C)**

- [ ] **Step 2: Read all 5 C13 findings + Phase 1 tests**

- [ ] **Step 3: Register `string/1` and `atomic/1`** (F081, F082). Add to the builtin registry.

- [ ] **Step 4: Fix `ground/1` to recognise Seg* containers** (F083). The `_is_ground_py` and C `c_is_ground` need a Seg* branch (or use `_register_term_types` to register a `__is_ground__` hook on SegList/SegString).

- [ ] **Step 5: Tighten `callable_/1`** (F084). Reject empty str; reject unregistered atoms (the smell).

- [ ] **Step 6: Apply F080 fix per user's option**

- [ ] **Step 7: Update lock-in test (if option A)**

- [ ] **Step 8: Confirm xfails flip + pre-existing suite + ledger + commit**

```bash
git commit -m "$(cat <<'EOF'
fix(type_checks): close C13 type-check findings (F080-F084)

- F080: <per user's option A/B/C decision>
- F081: register string/1 builtin
- F082: register atomic/1 builtin
- F083: ground/1 recognises Seg* containers via _register_term_types
- F084: callable_/1 rejects empty strs and unregistered atoms

Lock-in test in tests/test_string_list_builtins.py: <kept|updated per option>.
Pre-existing suite unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: C14 — Term inspection drift (F088, F089, F090, F091, F092, F093, F094)

**Findings closed:** 7 findings, including F092/F093 lock-in tests.

### **PAUSE POINT — design choice required on F088-F091**

F088-F091 disagree about what "the args of a list" means. Pick:
- **A. Cons-cell convention** (matches Prolog tradition / SWI / SICStus): `functor([a,b,c], '.', 2)`, `arg(1, [a,b,c], a)`, `arg(2, [a,b,c], [b,c])`, `[a,b,c] =.. ['.', a, [b,c]]`.
- **B. Python-indexing convention** (current buggy behaviour): `arg(1, [a,b,c], a)`, `arg(2, [a,b,c], b)`, etc.
- **C. Hybrid** — functor reports list arity (3 for [a,b,c]) per Python, arg uses Python indexing, =.. unwraps to ['.', a, b, c] — no Prolog precedent.

Recommend A for Prolog compatibility; ask user to confirm.

**Source change:** `clausal/logic/builtins/inspection.py` — all four predicates per chosen option. Also `_register_term_types` for F092/F093/F094 (Seg* visibility).

- [ ] **Step 1: Ask user for cons-cell vs Python-indexing option**

- [ ] **Step 2: Read all 7 C14 findings + Phase 1 tests**

- [ ] **Step 3: Implement Seg*-aware copy_term + term_variables + numbervars** (F092, F093, F094). Register `__copy_term__`, `__term_variables__`, `__numbervars__` hooks on SegList and SegString via `_register_term_types`. Each hook recurses into segments and produces the appropriate new value / counts.

- [ ] **Step 4: Implement functor/arg/=../2 per chosen convention** (F088, F089, F090, F091).

- [ ] **Step 5: Update F092 / F093 lock-in tests in tests/test_term_inspection.py**

Per the Phase 0 ledger Prior-known notes, commit `4507be8` landed lock-in tests that document the Seg*-blind behaviour. Edit those tests to assert the new contract (independent copy, VarSegs counted).

- [ ] **Step 6: Confirm 7 xfails flip + pre-existing suite + ledger + commit**

```bash
git commit -m "$(cat <<'EOF'
fix(inspection): close C14 term-inspection findings (F088-F094)

- F092: copy_term produces independent Seg* copies (registered hook)
- F093: term_variables visits VarSegs (registered hook)
- F094: numbervars labels VarSegs (registered hook)
- F088-F091: functor/3, arg/3, =../2 adopt <cons-cell|Python> convention
  for lists per user decision.

Lock-in tests in tests/test_term_inspection.py updated to assert new
contracts. Pre-existing suite verified — N tests updated, no
regressions.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: C3 — SegString blind-spot sweep (F012, F031, F032, F034, F040, F041, F047, F075)

**Findings closed:** 8 findings. **This is the highest-leverage task** — likely closes many sibling C-class findings (the implementer's Task-by-task reports flagged this).

**Source change:**
- `clausal/logic/runtime/list_unify.py` (Python fallback) and `_list_unify.c` (C accelerator) — add a SegString-normalise branch alongside the existing SegList-normalise (mirror lines 114-117 of list_unify.py).
- `clausal/logic/runtime/body_star_unify.py` — extend `_body_multi_star_unify` to handle SegString targets, both ground and non-ground.
- `clausal/logic/compiler/head_match.py` — `_compile_multi_star_guard` emits a SegString-normalise branch (mirror lines 857-872).
- `clausal/logic/builtins/chars.py` — `_atom_to_str` (or equivalent) extends to walk SegString.

**Approach:** the unified pattern across all 8 findings is: every dispatch site that branches on the target's container type has a SegList arm but no SegString arm. The fix is to add the SegString arm at each site, ideally factoring out a shared helper (e.g. `_normalize_string_input(x) -> Union[str, list]`) that walks SegString → str and SegList → list.

- [ ] **Step 1: Read all 8 C3 findings + Phase 1 tests + probes**

- [ ] **Step 2: Design the shared helper**

In `clausal/logic/runtime/_seg_helpers.py` (new file), define:

```python
def normalize_seg_input(x):
    """Walk a SegList/SegString to its ground form (list/str) or return
    the original if already a list/str/non-Seg type. Used at dispatch
    sites that branch on container type to ensure SegString and SegList
    inputs are handled symmetrically."""
    from clausal.terms import SegList, SegString
    if isinstance(x, SegList):
        walked = x.__walk__()
        return walked  # may be a list (ground) or SegList (non-ground)
    if isinstance(x, SegString):
        walked = x.__walk__()
        return walked  # may be a str (ground) or SegString (non-ground)
    return x
```

- [ ] **Step 3: Apply at each dispatch site**

- `list_unify.py:114-117` → add SegString case after SegList
- list_unify.py output mode → mirror
- `_list_unify.c` → mirror in C (read PyObject's type, branch accordingly)
- `body_star_unify.py::_body_multi_star_unify` → add SegString branch
- `head_match.py::_compile_multi_star_guard` → emit SegString-normalise AST node
- `chars.py::_atom_to_str` (or similar) → walk SegString

- [ ] **Step 4: Rebuild C extensions** (because `_list_unify.c` changed)

- [ ] **Step 5: Confirm 8 xfails flip**

```bash
pytest tests/audit_2026_05_25/test_class_C03_segstring_blindspots.py -v
```

Expected: 8 PASSED.

**Cascade check:** the implementer's Task 5 Phase 0 report noted that C3 fixes may close findings in C9 (F051 _as_items), C10 (F069), etc. Re-run the full audit suite to see how many *other* xfails flip as a side effect:

```bash
pytest tests/audit_2026_05_25/ -v 2>&1 | tail -15
```

Any unexpected XPASSED need to be addressed (remove their xfail markers and update ledger).

- [ ] **Step 6: Remove xfail markers across all classes affected**

For every test that XPASSED unexpectedly, remove its xfail marker. Update the corresponding ledger entries.

- [ ] **Step 7: Pre-existing suite + ledger + commit**

```bash
git commit -m "$(cat <<'EOF'
fix(runtime,compiler,chars): close C3 SegString blind-spot cluster (8 findings + cascade)

Introduces normalize_seg_input() helper and applies it at every
dispatch site that branches on container type — list_unify (Py + C),
body_star_unify, _compile_multi_star_guard (compiler), and the
char/atom builtins. Each site now has a SegString arm symmetric with
the existing SegList arm.

Direct closures: F012, F031, F032, F034, F040, F041, F047, F075.
Cascade closures: <list of F-IDs that flipped unexpectedly — likely
F069 (DCG), F051 (lists.py), F061 (higher_order)>.

Pre-existing suite unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: C9 — Polymorphic mode matrix (F050, F051, F052, F053, F054, F055, F056, F061, F062, F063, F072, F077)

**Findings closed:** 12. Several may already be closed by Task 11's cascade — focus on the residuals.

**Source change:** `clausal/logic/builtins/lists.py` and `clausal/logic/builtins/higher_order.py`. Specifically:
- `_as_items` extension (likely already done in Task 11 if `_as_items` lives in a place that the C3 helper reaches).
- `_seq_result` consistency — per F054's matrix, decide the rule (input-type-wins is the recommended default).
- F050 split_with join fix (1-line).
- F052 sum/max/min error-swallowing fix.
- F072 char_type mode-mismatch fix.

### **PAUSE POINT — design choice required on F054**

F054 documents 8 rows where the same logical input shape produces different output types. Pick the canonical rule:
- **A. Input-type-wins** (recommended) — if input is str, output is str (when results are 1-char-strs); if input is list, output is list.
- **B. Output-as-input-narrowed** — current behaviour, with `_seq_result` requiring all-1-char-strs to upgrade to str.
- **C. New rule** — user proposes.

Ask the user before implementing F054 fix.

- [ ] **Step 1: Re-run Phase 1 C9 tests after Task 11**

```bash
pytest tests/audit_2026_05_25/test_class_C09_polymorphic_mode_matrix.py -v
```

Note which xfails already flipped from Task 11's cascade. Remove their xfail markers in this commit.

- [ ] **Step 2: Read residual findings + identify per-finding fix sites**

For the remaining xfails, locate the source-code fix per finding's Notes section.

- [ ] **Step 3: Ask user for F054 option**

- [ ] **Step 4: Implement residual fixes**

- [ ] **Step 5: Confirm all 12 (or remaining) xfails flip + pre-existing suite + ledger + commit**

```bash
git commit -m "$(cat <<'EOF'
fix(lists, higher_order): close C9 polymorphic mode matrix residuals (F050-F056, F061-F063, F072, F077)

After C3 cascade closed F051/F061 (and possibly others), the remaining
C9 findings address split_with join (F050), reduction error-swallowing
(F052), output-type asymmetry (F053-F056, F062, F063 per user's F054
option <A/B/C>), char_type mode mismatch (F072), and atom_concat error
class (F077).

Pre-existing suite unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: C1 — Type-source plumbing (F018, F020, F033, F042, F043)

**Findings closed:** 5 findings, including F033/F042 lock-in tests.

### **PAUSE POINT — design choice required**

C1 is fundamentally a contract question: **how does an operation know to return str vs list when the input could be either?** Options:
- **A. Input-type tracking** — every operation that consumes a sequence records whether the input was a str, and uses that to choose output type. Requires plumbing the type-source through SegList/SegString construction.
- **B. Output canonical form** — always return list; user converts to str via explicit `chars_to_str` if desired.
- **C. Heuristic** — return str iff all elements are 1-char strs (current `_seq_result` behaviour, extended to cover the broken sites).

Each option has substantial blast radius. Ask the user before implementing.

After choice:

**Source change** (varies):
- A: many files — SegList/SegString construction sites take a `src_type` parameter.
- B: easier — remove the str-preservation attempts, document the contract.
- C: extend `_seq_result` use to the broken sites (F033, F042, F043) and document the rule.

Lock-in tests in `tests/test_seglist_creation.py` for F033/F042 need updating per the chosen option.

- [ ] **Step 1: Ask user for option A/B/C**

- [ ] **Step 2: Read all 5 C1 findings**

- [ ] **Step 3: Implement per option**

- [ ] **Step 4: Update F033/F042 lock-in tests**

- [ ] **Step 5: Confirm 5 xfails flip + pre-existing suite + ledger + commit**

```bash
git commit -m "fix(terms,runtime): close C1 type-preservation findings (F018, F020, F033, F042, F043)"
```

---

## Task 14: C10 — DCG/phrase (F067, F068, F069, F070)

**Findings closed:** 4 findings, including F067 lock-in test.

**Source change:** `clausal/logic/builtins/dcg.py` and `clausal/templating/term_rewriting.py` (DCG expansion). Likely depends on C3 (Task 11) and C1 (Task 13) having landed first.

- F069 (SegString rejection) — should be closed by Task 11's cascade. Check first.
- F068 (state-threading splits str) — needs DCG-specific fix: detect when the threading var is consumed by a non-list-mode goal and don't auto-split the str.
- F067 (Rest type) — depends on Task 13's choice (per option A, Rest preserves str).
- F070 (sequence//1 type loss) — same as C9 type-loss pattern.

Lock-in test in `tests/test_dcg.py` for F067 needs updating per Task 13's choice.

- [ ] **Step 1: Re-run Phase 1 C10 tests after Tasks 11+13**

- [ ] **Step 2: Implement residual fixes (F068, F070)**

- [ ] **Step 3: Update F067 lock-in test**

- [ ] **Step 4: Confirm xfails flip + pre-existing suite + ledger + commit**

```bash
git commit -m "fix(dcg): close C10 DCG/phrase findings (F067-F070)"
```

---

## Task 15: C4 — Head-pattern literal mismatch (F046) — sub-plan

**Findings closed:** F046. **Largest blast radius in the audit; treat as its own sub-effort.**

**Source change:** `clausal/logic/compiler/head_match.py` and `clausal/logic/database.py`.

### **PAUSE POINT — design choice required**

Two options from Phase 0's fix-scope assessment:
- **Narrow:** split the `(int, float, str, bytes, complex)` tuple in `head_match.py:253-254` — emit `MatchValue` only for non-sequence scalars (int, float, complex); emit a wildcard capture + `unify(_lcap, literal, trail)` guard for `str` and `bytes`, mirroring the list-literal path at `:258`. ~10-line change.
- **Broad:** lift the `_normalize_dataclass_fact` elaborator gate at `database.py:274` (`body_goals == [True]`) to run for all clauses, not just fact-like ones. Removes the C4 surface at its source. ~5-line change but bigger semantic implication.

Either approach has perf implications (literal-string-head clauses become wildcard-match + runtime-unify instead of Python `==`). The narrow option is safer for blast radius; the broad option is cleaner architecturally.

**Pause before implementing — confirm with user which option.**

C4 work also includes verifying C15 (Task 8) is still working — they're conjoined fixes.

- [ ] **Step 1: Ask user for narrow vs broad option**

- [ ] **Step 2: Read F046 entry + Phase 1 test + probe (extended to cover rules)**

- [ ] **Step 3: Implement per option**

- [ ] **Step 4: Verify F046 xfail flips**

```bash
pytest tests/audit_2026_05_25/test_class_C04_head_literal_mismatch.py -v
```

Should now show 1 PASSED.

- [ ] **Step 5: Verify F095 (C15) xfail also still passes** (the two were conjoined)

- [ ] **Step 6: Full pre-existing suite — extra scrutiny**

```bash
pytest tests/ --ignore=tests/audit_2026_05_25 -v 2>&1 | tail -50
```

The C4 fix may shift the behaviour of any clause with a string-literal head. Expect some test cases that were testing the old buggy behaviour to fail; update them in this commit.

- [ ] **Step 7: Update ledger + commit**

```bash
git commit -m "$(cat <<'EOF'
fix(compiler): close C4 head-literal mismatch (F046) — <narrow|broad> option

<Implementation summary per option>. The strings-as-lists contract
now holds for rule heads with string literals: Quux("abc") <- Body
matches caller Quux(['a','b','c']) and vice versa.

Conjoined fix with C15 (F095): both must land together. Pre-existing
suite: N tests updated to match the new contract, M regressions
investigated and fixed.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 16: Phase 3 sweep — verify and close

**Files:** `docs/superpowers/audits/2026-05-25-string-implementation/findings.md` (append Phase 3 conclusion).

**Approach:** Per the spec's Phase 3, re-run the audit on the now-fixed code. New findings get appended as Phase 3 items.

- [ ] **Step 1: Run the full audit test suite**

```bash
pytest tests/audit_2026_05_25/ -v 2>&1 | tail -30
```

Expected: ~all PASSED (target: 0 XFAIL, 0 FAILED, 0 ERRORED). Any remaining XFAIL is a finding that wasn't fixed (intentional `wontfix` or oversight).

- [ ] **Step 2: Run the full pre-existing suite**

```bash
pytest tests/ --ignore=tests/audit_2026_05_25 -q 2>&1 | tail -5
```

Expected: zero regressions.

- [ ] **Step 3: Cross-class consistency check**

Per the spec's Phase 3, ask: did any class-N fix break a class-M assumption? Re-read each fix commit's diff, looking for shared utilities (`_as_items`, `normalize_seg_input`, `_seq_result`) that were extended in one task and may need to be re-examined after later tasks.

- [ ] **Step 4: Append Phase 3 conclusion to findings.md**

```markdown
## Phase 3 conclusion

- **Phase 2 fixes landed:** N commits across 15 tasks.
- **Findings closed:** M (N bug, N design-gap, N perf, N smell, N doc-only).
- **Findings deferred (wontfix):** N — list with rationale.
- **Phase 3 sweep findings:** N new (appended as F<N>+ — log under appropriate class).
- **Cross-class consistency:** verified — no class-N fix broke class-M assumption.
- **Pre-existing suite:** N tests added/updated for the new contracts; zero regressions vs pre-Phase-2 baseline.
- **`docs/strings_as_lists.md`:** updated to reflect post-fix contract.

The strings-as-lists implementation is now contract-consistent across
core unification, partial-term machinery, polymorphic builtins,
higher-order, DCG, type-checks, term inspection, and dispatch
indexing.
```

- [ ] **Step 5: Commit + final tag**

```bash
git add docs/superpowers/audits/2026-05-25-string-implementation/findings.md
git commit -m "$(cat <<'EOF'
docs(audit): Phase 3 sweep complete — audit closed

All 75 Phase 1 tests pass. Pre-existing pytest suite has zero
regressions. Cross-class consistency verified. Phase 3 sweep findings:
<N> new (appended). The strings-as-lists audit is closed.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git tag -a string-audit-complete -m "String implementation audit complete — Phase 0-3"
```

---

## Phase 2 exit criteria (must all be true)

- [ ] Every `bug` and `design-gap` finding has either: a passing test + a fix commit, or a `wontfix` ledger entry with rationale.
- [ ] All Phase 1 xfail markers removed for closed findings.
- [ ] Lock-in tests in the pre-existing suite (F033, F042, F067, F080, F092, F093) updated or deleted per the new contracts.
- [ ] Full pre-existing pytest suite has zero regressions vs pre-Phase-2 baseline.
- [ ] `docs/strings_as_lists.md` updated where the contract changed.
- [ ] Phase 3 sweep conclusion appended to findings.md.

If any criterion fails, do not declare the audit complete.
