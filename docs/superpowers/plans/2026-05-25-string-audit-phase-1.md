# String Implementation Audit — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert each Phase 0 `bug` and `design-gap` finding (and selected `perf`/`smell` findings) into an adversarial pytest test marked `xfail(strict=True, reason="ledger F<N>")`, so that Phase 2 fixes will automatically be caught by these tests flipping from xfail→pass.

**Architecture:** One test file per class with findings, under `tests/audit_2026_05_25/`. Inside each file, one test function per finding (named `test_F<NNN>_<short_topic>`). Tests use the same logic as their corresponding `probes/probe_F<NNN>.py` script, but assert the *correct* behaviour rather than print actual vs expected. `xfail(strict=True)` so any test that accidentally passes (because someone fixed the bug or the test is wrong) becomes a loud signal. A shared `_helpers.py` provides the inline-clausal loading helper that ~half the tests need.

**Tech Stack:** pytest 8+, clausal (editable install in this worktree), `tempfile` for inline `.clausal` sources, `pytest.mark.xfail(strict=True)`.

**Inputs (do not duplicate — read directly):**
- Ledger: `docs/superpowers/audits/2026-05-25-string-implementation/findings.md` — every finding's Reproducer + Expected + Actual fields. This is the source of truth for test logic.
- Probes: `docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F<NNN>.py` — runnable reference implementations. Each test lifts the probe's logic into a pytest function.
- Coverage: `docs/superpowers/audits/2026-05-25-string-implementation/test_coverage.md` — identifies the 6 lock-in tests (F033, F042, F067, F080, F092, F093) Phase 2 must handle.
- Spec: `docs/superpowers/specs/2026-05-25-string-implementation-audit-design.md`
- Phase 0 plan: `docs/superpowers/plans/2026-05-25-string-audit-phase-0.md`

**Out-of-scope for Phase 1:**
- C6 (0 findings) and C11 (0 findings) — no test files to write.
- C7 (7 doc-only findings) — no tests needed per spec ("`doc-only` — the implementation is correct; docs are wrong"). Phase 2 will update `docs/strings_as_lists.md` directly.
- C16 F011 — has an xfail test stub but the actual FT race is unreproducible on the GIL-enabled harness; the test asserts the structural fix-target rather than the race itself.
- Modifying or deleting the 6 lock-in tests in `tests/test_seglist_creation.py`, `tests/test_dcg.py`, `tests/test_term_inspection.py`, `tests/test_string_list_builtins.py` — Phase 2 owns those (when the fix flips the contract).

---

## Conventions used throughout this plan

### Test function naming

`def test_F<NNN>_<short_topic>():` — e.g. `test_F015_seglist_unify_first_split_only`. The `F<NNN>` prefix lets `pytest -k` filter by finding ID.

### Xfail marker pattern

Every test in this directory is marked `xfail` because we expect the bug to still be present pre-fix:

```python
@pytest.mark.xfail(strict=True, reason="ledger F<NNN>: <one-line finding title>")
def test_F<NNN>_<topic>():
    # ... assert the CORRECT behaviour the contract demands ...
```

`strict=True` means a passing test becomes a failure — so when Phase 2 lands a fix, the test flips from xfail→pass, and pytest signals an unexpected pass that the Phase 2 commit must clear by removing the xfail marker.

### Test body pattern (mirrors probe scripts)

```python
def test_F<NNN>_<topic>():
    """Adversarial test for F<NNN>: <one-line title>.

    Asserts the strings-as-lists contract is honoured. Currently expected
    to fail (xfail) because <one-sentence symptom from ledger>.
    """
    # === Setup: mirror probe_F<NNN>.py exactly ===
    # (refer to docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F<NNN>.py
    #  for the exact reproducer logic)

    # === Assertion: assert the EXPECTED behaviour from the ledger ===
    assert <expected>, f"expected <X>, got {actual!r}"
```

Tests must NOT print — they assert. Use `assert <cond>, f"<msg>"` form so failures show actual vs expected.

### Inline-clausal helper

Many tests need to register predicates inline (same pattern as probe_F046.py). Use the shared helper:

```python
from tests.audit_2026_05_25._helpers import load_inline_clausal

mod = load_inline_clausal("test_module_name", '''
Foo("abc"),
Bar(['a', 'b', 'c']),
''')
```

Tests that don't need inline predicates (pure-Python module unit tests, e.g. SegList class behaviour) skip the helper and import directly.

### Commit message style

```
test(audit): C<N> adversarial xfails for F<start>-F<end>

<one-paragraph summary: which findings, what each test asserts, total
test count and expected xfail count>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

### Verification commands

After each task, run:

```bash
pytest tests/audit_2026_05_25/test_class_C<N>_*.py -v
```

Expected output: every test marked `XFAIL`. If any test PASSES, that's a real signal — either the bug isn't present (re-read the finding) or the test is wrong (fix it). If any test fails with an error other than the expected assertion failure, the test setup is broken (fix it).

Use `pytest --runxfail tests/audit_2026_05_25/test_class_C<N>_*.py -v` to see the actual assertion failures and confirm they match the ledger's "Actual" line.

### When to pause for user input

- A test you write actually PASSES at the assertion (xfail flips to pass) — the bug isn't where the ledger claims it is. Re-read the finding, re-check the probe; if both disagree with reality, escalate to the user before logging an xfail-flip-to-pass as a new finding.
- An entire test file's tests all fail to set up (e.g. import errors, fixture problems) — the helper or shared infrastructure is broken; fix before proceeding.

Routine xfails (test fails the assertion exactly as the ledger predicts) need no escalation — that's the expected state.

---

## File structure

Plan output creates these files:

```
tests/audit_2026_05_25/
├── __init__.py                                  # empty package marker
├── conftest.py                                  # shared fixtures, audit-specific config
├── _helpers.py                                  # load_inline_clausal helper
├── test_class_C01_type_preservation.py          # F018, F020, F033, F042, F043
├── test_class_C02_nondet_first_only.py          # F015, F016
├── test_class_C03_segstring_blindspots.py       # F012, F031, F032, F034, F040, F041, F047, F075
├── test_class_C04_head_literal_mismatch.py      # F046
├── test_class_C05_hash_eq_asymmetries.py        # F017, F019, F025
├── test_class_C08_partial_term_shortcircuits.py # F021, F022, F023, F024, F038, F039
├── test_class_C09_polymorphic_mode_matrix.py    # F050-F056, F061-F063, F072, F077
├── test_class_C10_dcg_phrase.py                 # F067, F068, F069, F070
├── test_class_C12_char_representation.py        # F073
├── test_class_C13_type_checks.py                # F080, F081, F082, F083, F084
├── test_class_C14_term_inspection.py            # F088, F089, F090, F091, F092, F093, F094
├── test_class_C15_first_arg_indexing.py         # F095
├── test_class_C16_ft_safety.py                  # F011 (skipif gil_enabled)
└── test_class_C17_perf_memory.py                # F009, F026 (asymptotic checks)
```

Total: 16 files, ~56 test functions, all xfail-strict.

No source code in `clausal/` is modified — Phase 1 is read-only on the project, write-only on `tests/audit_2026_05_25/`.

---

## Task 0: Scaffold the audit test directory

**Files:**
- Create: `tests/audit_2026_05_25/__init__.py`
- Create: `tests/audit_2026_05_25/conftest.py`
- Create: `tests/audit_2026_05_25/_helpers.py`

- [ ] **Step 1: Create `tests/audit_2026_05_25/__init__.py`**

Write the file with this exact content:

```python
"""Adversarial tests generated from the 2026-05-25 string implementation audit.

Every test here is marked `xfail(strict=True)` because the audit found
bugs / design-gaps that have not been fixed yet. When Phase 2 of the audit
lands a fix, the corresponding xfail flips to a pass, and pytest signals
an unexpected pass — the Phase 2 commit must then remove the xfail marker.

See: docs/superpowers/audits/2026-05-25-string-implementation/findings.md
"""
```

- [ ] **Step 2: Create `tests/audit_2026_05_25/_helpers.py`**

Write the file with this exact content:

```python
"""Shared helpers for the 2026-05-25 string audit adversarial tests."""

from __future__ import annotations

import os
import tempfile
from typing import Any

from clausal.import_hook import _load_module


def load_inline_clausal(name: str, source: str) -> Any:
    """Load a .clausal source string as a module, returning the module object.

    Writes *source* to a tempfile, loads it via the clausal import hook,
    and unlinks the tempfile. Returns the loaded module; the caller can
    pass `module=mod.__dict__["$module"]` to `clausal.logic.solve.call`.

    Use this in tests that need to register predicates inline (any test
    that exercises the Database / dispatch / compile pipeline). Pure-Python
    unit tests on `clausal.terms.SegList`/`.SegString` don't need this.
    """
    with tempfile.NamedTemporaryFile(
        suffix=".clausal", mode="w", delete=False
    ) as f:
        f.write(source)
        f.flush()
        path = f.name
    try:
        return _load_module(name, path)
    finally:
        os.unlink(path)
```

- [ ] **Step 3: Create `tests/audit_2026_05_25/conftest.py`**

Write the file with this exact content:

```python
"""Conftest for the 2026-05-25 string audit adversarial tests.

All tests in this directory are intentionally `xfail(strict=True)` pre-fix.
A test that passes here means either:
  (a) Phase 2 landed a fix — the xfail marker should now be removed; or
  (b) the test is wrong — re-check the ledger entry and the probe.

This conftest does not register any auto-use fixtures; it exists so pytest
treats this directory as its own test scope and to document the discipline.
"""

import pytest

# Re-export so tests can `from .conftest import xfail_ledger` for brevity
# if they prefer; otherwise the standard `@pytest.mark.xfail(strict=True, ...)`
# usage is fine.

def xfail_ledger(finding_id: str, title: str) -> pytest.MarkDecorator:
    """Convenience wrapper: `xfail_ledger("F015", "SegList non-det first split only")`."""
    return pytest.mark.xfail(
        strict=True, reason=f"ledger {finding_id}: {title}"
    )
```

- [ ] **Step 4: Verify pytest can collect the directory**

Run:

```bash
cd /workspace/clausal-string_audit && pytest tests/audit_2026_05_25/ --collect-only
```

Expected: `collected 0 items` (no test files yet). If pytest reports import errors on `_helpers.py` or `conftest.py`, fix them before proceeding.

- [ ] **Step 5: Commit**

```bash
git add tests/audit_2026_05_25/
git commit -m "$(cat <<'EOF'
test(audit): scaffold audit_2026_05_25 test directory

Adds __init__.py, conftest.py, _helpers.py. No test files yet.
Subsequent tasks add one test file per audit class with findings.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Per-class test-file tasks

Each task below has the same shape:
1. Read the listed findings from the ledger to get exact reproducer + expected behaviour.
2. Read the corresponding `probe_F<NNN>.py` scripts for runnable reference logic.
3. Write the test file with one `test_F<NNN>_<topic>` function per finding, each marked `@pytest.mark.xfail(strict=True, reason="ledger F<NNN>: <title>")`.
4. Run `pytest tests/audit_2026_05_25/test_class_C<N>_*.py -v` and confirm every test is `XFAIL`.
5. Run `pytest tests/audit_2026_05_25/test_class_C<N>_*.py --runxfail -v` and confirm the assertion-failure messages line up with the ledger's "Actual" lines.
6. Commit.

**Step granularity:** for each finding, one step writes the test function (with the full code shown in the step), one step verifies it xfails as expected. A class with 5 findings has ~10 steps + setup + commit.

The plan does NOT inline the full reproducer code per test — that would duplicate the ledger. Instead, each finding's task step says "lift the logic from `probe_F<NNN>.py`, but convert prints to asserts that the contract is honoured." The implementer reads the ledger entry's Reproducer + Expected + Actual sections and the probe file to produce the correct test body.

If the implementer needs an example of the full conversion pattern, here is the canonical one (used in Task 1's first step):

### Reference conversion: probe → xfail test

**probe_F015.py (excerpt — actual file may differ slightly):**

```python
from clausal.logic.variables import Var, unify, Trail, deref
from clausal.terms import SegList, VarSeg, _seglist_unify_gen

def main():
    A, B = Var(), Var()
    sl = SegList([VarSeg(A), VarSeg(B)])
    t = Trail()
    ok = unify(sl, [1, 2, 3], t)
    print(f"  unify(SegList[*A,*B], [1,2,3]) → {ok}")
    print(f"  A = {deref(A)!r}, B = {deref(B)!r}")
    # The gen yields 4 splits, but __unify__ takes only the first.
```

**Equivalent xfail test (test_class_C02_nondet_first_only.py::test_F015):**

```python
import pytest
from clausal.logic.variables import Var, unify, Trail, deref
from clausal.terms import SegList, VarSeg


@pytest.mark.xfail(
    strict=True,
    reason="ledger F015: SegList.__unify__ returns only the first valid split",
)
def test_F015_seglist_unify_enumerates_all_splits():
    """When `[*A, *B] = [1, 2, 3]` is solved, backtracking should yield all
    four splits: A=[]/B=[1,2,3], A=[1]/B=[2,3], A=[1,2]/B=[3], A=[1,2,3]/B=[].
    SegList.__unify__ currently consumes only the first split from the
    generator.

    Adversarial test asserts that re-running unify after backtracking yields
    distinct (A, B) pairs. The implementation today binds the first split
    and returns; subsequent attempts find no more solutions because there's
    no caller hook to drive the generator.
    """
    # Setup mirrors probe_F015.py.
    A, B = Var(), Var()
    sl = SegList([VarSeg(A), VarSeg(B)])
    t = Trail()

    # Drive whatever solution-enumeration the SegList unification exposes
    # to the trampoline. The bug: only the first solution is reachable
    # through the unify entry point.
    splits_seen = []
    mark = t.mark()
    if unify(sl, [1, 2, 3], t):
        splits_seen.append((deref(A), deref(B)))
    t.undo(mark)

    # ... (the ledger entry will guide whether to assert via a solve()
    # loop or by direct generator inspection; F015's specific shape is
    # documented in findings.md and probe_F015.py.)

    # Adversarial assertion: the contract demands enumeration of all
    # valid splits via the trampoline, not just the first.
    assert len(splits_seen) >= 4, (
        f"expected ≥4 splits via __unify__, got {len(splits_seen)}: {splits_seen!r}"
    )
```

The implementer uses this exact pattern: docstring summarises the finding, setup mirrors the probe, assertion encodes the **expected** behaviour from the ledger. The xfail marker carries the ledger ID and the one-line title.

If a finding's expected behaviour is "raise a specific exception" (e.g. F021 SegList sequence-protocol crash), use `pytest.raises(...)` inside an assertion that the wrong-kind-of-exception is what's raised:

```python
@pytest.mark.xfail(
    strict=True,
    reason="ledger F021: SegList __len__/__iter__/__getitem__ crash on non-ground",
)
def test_F021_seglist_len_on_partial_returns_or_constrains_not_crashes():
    """A non-ground SegList should support a sequence-protocol query in
    *some* defined way — either constrain (return), raise a Clausal-typed
    exception, or return a specifically-documented sentinel. Raising raw
    Python TypeError on `len(sl)` is the C8 crash pattern.
    """
    from clausal.terms import SegList, VarSeg, ConcreteSeg
    from clausal.logic.variables import Var
    sl = SegList([ConcreteSeg([1, 2]), VarSeg(Var()), ConcreteSeg([5])])
    # Contract should be: either defined sentinel/length, or a typed
    # clausal exception — not bare TypeError.
    try:
        result = len(sl)
    except TypeError as e:
        pytest.fail(f"len(non-ground SegList) raised bare TypeError: {e}")
    # If it returns, the value should be ≥3 (concrete parts plus ≥0 var parts).
    assert result >= 3, f"len returned {result}, expected ≥3 (lower bound)"
```

For "wrong answer" findings (e.g. F068 DCG silently splits string state arg), the assertion compares the wrong actual to the expected correct answer:

```python
@pytest.mark.xfail(
    strict=True,
    reason="ledger F068: phrase/3 silently splits str state-threading arg into chars",
)
def test_F068_phrase3_state_threading_str_not_split():
    """When a DCG rule's input slot expects an atom but receives a str
    that should match as a 1-element list, phrase/3 should either fail
    cleanly or treat the str as a single token — not silently split the
    str into its characters and match against the first char.
    """
    from clausal.logic.variables import Var, deref
    from clausal.logic.solve import call
    from tests.audit_2026_05_25._helpers import load_inline_clausal

    # Setup mirrors probe_F068.py.
    mod = load_inline_clausal("test_F068", """
        # ... DCG fixture per the probe ...
    """).__dict__["$module"]

    REST = Var()
    solutions = list(call("phrase", "...", "bob", REST, module=mod))
    # ... assert the corrected behaviour per the ledger entry's Expected line ...
```

The implementer reads each finding's Reproducer + Expected + Actual + Notes (in `findings.md`) and the corresponding probe to construct the test body. Plan does not duplicate that content.

---

## Task 1: C1 — Type preservation (5 findings)

**File:** `tests/audit_2026_05_25/test_class_C01_type_preservation.py`

**Findings:** F018, F020, F033, F042, F043 (all design-gap)

**Lock-in alert:** F033 and F042 have existing tests in `tests/test_seglist_creation.py` that codify the buggy behaviour as the intended contract. Phase 2 will need to delete/update those tests when the fix lands. Phase 1 just writes the new adversarial tests; existing tests stay as-is.

- [ ] **Step 1: Create the file with imports + module docstring**

Write `tests/audit_2026_05_25/test_class_C01_type_preservation.py`:

```python
"""C1 — Type preservation across the str↔list boundary.

5 design-gap findings. Each test asserts the strings-as-lists contract:
an operation that consumes a `str` should return a `str` (or vice versa)
when the contract demands it — not a `list`.

Findings tested here:
- F018 SegList.__walk__ expands VarSeg-bound str into char list
- F020 SegList.__add__ / __radd__ rejects str
- F033 _head_list_unify_output always builds a list, never a str  (lock-in test exists)
- F042 _body_multi_star_unify unbound-target branch always builds SegList  (lock-in test exists)
- F043 _build_star_list / _build_multi_star_list lose str type for list-of-chars and
  non-ground SegString stars
"""

import pytest
```

- [ ] **Step 2: Write `test_F018_seglist_walk_preserves_str_binding`**

Read finding F018 in `findings.md` (search for `### F018`) and `probes/probe_F018.py`. Lift the setup; write the assertion that a VarSeg bound to a `str` walks to a SegList whose segment is a `str` (not a list of chars). Add the `xfail(strict=True)` marker. Append to the file.

- [ ] **Step 3: Write `test_F020_seglist_add_accepts_str`**

Same pattern, for F020.

- [ ] **Step 4: Write `test_F033_head_output_preserves_str_type`**

Same pattern, for F033. Note the lock-in test in `tests/test_seglist_creation.py` exists; do NOT touch it.

- [ ] **Step 5: Write `test_F042_body_multi_star_unbound_target_preserves_str`**

Same pattern, for F042. Same lock-in note.

- [ ] **Step 6: Write `test_F043_build_star_list_preserves_str_with_seg_star`**

Same pattern, for F043.

- [ ] **Step 7: Run pytest and confirm all 5 tests xfail**

```bash
pytest tests/audit_2026_05_25/test_class_C01_type_preservation.py -v
```

Expected: 5 XFAIL, 0 PASSED, 0 FAILED. If any test PASSES (strict-xfail flip), the bug isn't where the ledger claims; re-check. If any test ERRORS (setup broken), fix it.

- [ ] **Step 8: Confirm assertion messages match the ledger**

```bash
pytest tests/audit_2026_05_25/test_class_C01_type_preservation.py --runxfail -v 2>&1 | tail -50
```

For each test, the assertion failure message should describe the actual wrong type/value matching the ledger's "Actual" line. If a message is opaque, improve the assertion's f-string.

- [ ] **Step 9: Commit**

```bash
git add tests/audit_2026_05_25/test_class_C01_type_preservation.py
git commit -m "$(cat <<'EOF'
test(audit): C1 type-preservation adversarial xfails (F018, F020, F033, F042, F043)

Five xfail-strict tests, one per C1 design-gap finding. Each asserts the
strings-as-lists contract: str-typed inputs round-trip to str-typed
outputs through walks, builders, and head/body unification.

F033 and F042 have existing tests in tests/test_seglist_creation.py that
codify the buggy behaviour; Phase 2 must update/delete those when the
fix lands. Phase 1 leaves them as-is.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: C2 — Non-determinism collapsed to first (2 findings)

**File:** `tests/audit_2026_05_25/test_class_C02_nondet_first_only.py`

**Findings:** F015, F016 (both bug)

- [ ] **Step 1: Create the file with imports + module docstring**

Write the file. Use the structure from Task 1 Step 1 but with:

```python
"""C2 — Non-deterministic SegList/SegString unification collapsed to first split.

2 bug findings. Each test asserts the unification entry point exposes
ALL valid splits (not just the first), so backtracking can find them.

Findings tested here:
- F015 SegList.__unify__ returns only the first valid split
- F016 SegString.__unify__ returns only the first valid split
"""

import pytest
```

- [ ] **Step 2: Write `test_F015_seglist_unify_enumerates_all_splits`**

Reference test body in the "Reference conversion: probe → xfail test" section above (uses F015 as the canonical example).

- [ ] **Step 3: Write `test_F016_segstring_unify_enumerates_all_splits`**

Same pattern, for F016. Reproducer lives in `probe_F016.py`.

- [ ] **Step 4: Run pytest and confirm both tests xfail**

```bash
pytest tests/audit_2026_05_25/test_class_C02_nondet_first_only.py -v
```

Expected: 2 XFAIL.

- [ ] **Step 5: Commit**

```bash
git add tests/audit_2026_05_25/test_class_C02_nondet_first_only.py
git commit -m "test(audit): C2 non-det adversarial xfails (F015, F016)"
```

(Add body + Co-Authored-By trailer matching prior commits.)

---

## Task 3: C3 — SegString blind spots (8 findings)

**File:** `tests/audit_2026_05_25/test_class_C03_segstring_blindspots.py`

**Findings:** F012 (design-gap), F031 (bug), F032 (bug), F034 (design-gap), F040 (bug), F041 (bug), F047 (bug), F075 (design-gap)

This is the largest cluster in the audit. Per Phase 0's Phase 2 ordering recommendation, fixing C3 will likely close many of these in a single change. Phase 1 still writes one test per finding so each individual site has coverage.

- [ ] **Step 1: Create the file**

Module docstring lists the 8 findings briefly. Add `import pytest`.

- [ ] **Steps 2-9: Write one test per finding (F012, F031, F032, F034, F040, F041, F047, F075)**

Each step: read the ledger entry, read the probe, lift logic into an xfail test. Use `load_inline_clausal` helper for tests that need a registered predicate (F047, F075 likely); pure-Python tests (F012, F031, F032, F034, F040, F041) can import directly.

- [ ] **Step 10: Run pytest and confirm 8 xfails**

```bash
pytest tests/audit_2026_05_25/test_class_C03_segstring_blindspots.py -v
```

- [ ] **Step 11: Commit**

```bash
git add tests/audit_2026_05_25/test_class_C03_segstring_blindspots.py
git commit -m "test(audit): C3 SegString blind-spot adversarial xfails (F012, F031, F032, F034, F040, F041, F047, F075)"
```

---

## Task 4: C4 — Head-pattern literal mismatch (1 finding)

**File:** `tests/audit_2026_05_25/test_class_C04_head_literal_mismatch.py`

**Findings:** F046 (bug — the largest-blast-radius finding)

- [ ] **Step 1: Create the file**

Module docstring notes that F046 is the audit's largest-blast-radius finding and that this single test will guard the Phase 2 fix.

- [ ] **Step 2: Write `test_F046_rule_str_head_matches_charlist_caller`**

Reproducer lives in `probe_F046.py`. The test should:
- Register two rule clauses with literal heads (`Quux("abc") <- (Helper(1))` and `Zorp(['a','b','c']) <- (Helper(1))`) plus the `Helper(1)` fact, via `load_inline_clausal`.
- Call `Quux(['a','b','c'])` — assert 1 solution (currently 0 — xfail).
- Call `Zorp("abc")` — assert 1 solution (currently 1 — should ALSO be in the assertion to guard against regression in the working direction).
- Also assert the same-type controls work (each call with matching type returns 1).

- [ ] **Step 3: Run pytest and confirm xfail**

```bash
pytest tests/audit_2026_05_25/test_class_C04_head_literal_mismatch.py -v
```

Expected: 1 XFAIL.

- [ ] **Step 4: Commit**

```bash
git add tests/audit_2026_05_25/test_class_C04_head_literal_mismatch.py
git commit -m "test(audit): C4 head-literal mismatch adversarial xfail (F046)"
```

---

## Task 5: C5 — Hash/eq asymmetries (3 findings)

**File:** `tests/audit_2026_05_25/test_class_C05_hash_eq_asymmetries.py`

**Findings:** F017 (bug — Python eq/hash invariant violation), F019 (design-gap), F025 (design-gap)

- [ ] **Step 1: Create the file**

- [ ] **Steps 2-4: Write tests F017, F019, F025**

F017 needs to assert that `hash(ss1) == hash(ss2)` for `ss1 == ss2`. F019 needs to assert symmetric behaviour: either both SegList and SegString accept str/list, or neither does. F025 needs to assert hashability discipline is consistent.

- [ ] **Step 5: Run pytest and confirm 3 xfails**

- [ ] **Step 6: Commit**

```bash
git commit -m "test(audit): C5 hash/eq asymmetry adversarial xfails (F017, F019, F025)"
```

---

## Task 6: C8 — Partial-term short-circuits (6 findings)

**File:** `tests/audit_2026_05_25/test_class_C08_partial_term_shortcircuits.py`

**Findings:** F021 (bug), F022 (design-gap), F023 (bug), F024 (smell), F038 (bug), F039 (bug)

- [ ] **Step 1: Create the file**

- [ ] **Steps 2-7: Write tests F021, F022, F023, F024, F038, F039**

F021/F038/F039 assert "no bare TypeError" (use the `pytest.fail(f"... raised bare TypeError")` pattern from the reference conversion). F022/F023 assert correct values. F024 is a smell — a cheap test asserting the malformed-segment case doesn't crash silently is sufficient.

- [ ] **Step 8: Run pytest, confirm 6 xfails**

- [ ] **Step 9: Commit**

```bash
git commit -m "test(audit): C8 partial-term short-circuit adversarial xfails (F021-F024, F038, F039)"
```

---

## Task 7: C9 — Polymorphic builtin mode matrix (12 findings)

**File:** `tests/audit_2026_05_25/test_class_C09_polymorphic_mode_matrix.py`

**Findings:** F050 (bug), F051 (bug), F052 (bug), F053 (design-gap), F054 (design-gap), F055 (design-gap), F056 (design-gap), F061 (bug), F062 (design-gap), F063 (design-gap), F072 (bug), F077 (smell)

Largest class file. 12 tests; if this becomes unwieldy, consider splitting into `_lists.py` and `_higher_order.py` sub-files — but the simpler default is one file.

- [ ] **Step 1: Create the file**

- [ ] **Steps 2-13: Write one test per finding**

Most tests use `load_inline_clausal` to register a fixture predicate that calls the builtin under audit (e.g. `Test(A) <- append(A, "world", "hello world")`).

F054's adversarial assertion is the "input-type wins" rule applied to the 8 rows in the ledger's matrix — implementer can either write 8 sub-assertions in one test or split into 8 parametrised cases via `pytest.mark.parametrize`. Use parametrize if it stays readable.

- [ ] **Step 14: Run pytest and confirm 12+ xfails** (more if parametrize splits F054)

- [ ] **Step 15: Commit**

```bash
git commit -m "test(audit): C9 polymorphic mode-matrix adversarial xfails (F050-F056, F061-F063, F072, F077)"
```

---

## Task 8: C10 — DCG / phrase interaction (4 findings)

**File:** `tests/audit_2026_05_25/test_class_C10_dcg_phrase.py`

**Findings:** F067 (design-gap — lock-in test in tests/test_dcg.py), F068 (bug — silent wrong answer), F069 (bug — SegString rejection), F070 (design-gap)

- [ ] **Step 1: Create the file**

- [ ] **Steps 2-5: Write tests F067, F068, F069, F070**

All four need `load_inline_clausal` to register DCG rules. F068's reference body is in the test/reference conversion section above. F067 has a lock-in test at `tests/test_dcg.py` — the new test asserts the corrected `Rest` type contract; Phase 2 handles the lock-in.

- [ ] **Step 6: Run pytest, confirm 4 xfails**

- [ ] **Step 7: Commit**

```bash
git commit -m "test(audit): C10 DCG/phrase adversarial xfails (F067-F070)"
```

---

## Task 9: C12 — Char representation drift (1 finding)

**File:** `tests/audit_2026_05_25/test_class_C12_char_representation.py`

**Findings:** F073 (bug — chr() ValueError leak)

- [ ] **Step 1: Create the file**

- [ ] **Step 2: Write `test_F073_char_code_out_of_range_fails_logically`**

Reproducer lives in `probe_F073.py`. Test should call `char_code(V, 0x110000)` (out-of-range code point) and assert the call fails *logically* (0 solutions) rather than raising raw Python ValueError. Pattern:

```python
try:
    n = sum(1 for _ in call("char_code", V, 0x110000, module=mod))
except ValueError as e:
    pytest.fail(f"char_code out-of-range leaked raw ValueError: {e}")
assert n == 0, f"expected logical failure (0 solutions), got {n}"
```

Same pattern for `atom_codes(V, [0x110000])` and `number_chars` if applicable.

- [ ] **Step 3: Run pytest, confirm 1 xfail**

- [ ] **Step 4: Commit**

```bash
git commit -m "test(audit): C12 char representation adversarial xfail (F073)"
```

---

## Task 10: C13 — Type-check predicates (5 findings)

**File:** `tests/audit_2026_05_25/test_class_C13_type_checks.py`

**Findings:** F080 (design-gap — lock-in test in tests/test_string_list_builtins.py), F081 (design-gap), F082 (design-gap), F083 (bug — ground/1 silent wrong answer), F084 (smell)

- [ ] **Step 1: Create the file**

- [ ] **Steps 2-6: Write tests F080, F081, F082, F083, F084**

F083 is the most important: assert `ground(SegList([VarSeg(Var())]))` is `False`. Currently returns `True`.

F081/F082 assert that `string/1` and `atomic/1` are registered as builtins (a `clausal.logic.solve.call("string", "abc", module=mod)` should produce 1 solution).

- [ ] **Step 7: Run pytest, confirm 5 xfails**

- [ ] **Step 8: Commit**

```bash
git commit -m "test(audit): C13 type-check adversarial xfails (F080-F084)"
```

---

## Task 11: C14 — Term inspection drift (7 findings)

**File:** `tests/audit_2026_05_25/test_class_C14_term_inspection.py`

**Findings:** F088 (bug), F089 (design-gap), F090 (bug), F091 (bug), F092 (bug — lock-in test), F093 (design-gap — lock-in test), F094 (design-gap)

- [ ] **Step 1: Create the file**

- [ ] **Steps 2-8: Write tests F088-F094**

F092 (copy_term aliasing Seg* containers) is the highest-impact: test should construct a clause-like structure containing a SegList with a VarSeg, call `copy_term`, then mutate the original's VarSeg and assert the copy is unaffected.

F091's assertion contradicts F088's (per the ledger — both predicates currently disagree about list arg counts). Phase 1 asserts each predicate independently against the strings-as-lists contract; Phase 2 will reconcile.

- [ ] **Step 9: Run pytest, confirm 7 xfails**

- [ ] **Step 10: Commit**

```bash
git commit -m "test(audit): C14 term inspection adversarial xfails (F088-F094)"
```

---

## Task 12: C15 — First-arg indexing (1 finding)

**File:** `tests/audit_2026_05_25/test_class_C15_first_arg_indexing.py`

**Findings:** F095 (bug — depends on F046 fix)

- [ ] **Step 1: Create the file**

- [ ] **Step 2: Write `test_F095_first_arg_index_coalesces_str_and_charlist`**

Reproducer lives in `probe_F095.py`. Test should:
- Register two clauses for the same predicate, one with str head, one with char-list head, via `load_inline_clausal`.
- Call the predicate with an unbound Var and assert 2 solutions.
- Call the predicate with each container type and assert each finds both clauses (since `"abc"` and `['a','b','c']` are unifiable, the indexer must route both to the same bucket).

Note the docstring should mention F095 fix depends on F046's compile-time fix (per the ledger Notes).

- [ ] **Step 3: Run pytest, confirm 1 xfail**

- [ ] **Step 4: Commit**

```bash
git commit -m "test(audit): C15 first-arg indexing adversarial xfail (F095)"
```

---

## Task 13: C16 — Free-threaded safety (1 finding)

**File:** `tests/audit_2026_05_25/test_class_C16_ft_safety.py`

**Findings:** F011 (bug — refcount/UAF hazard, unverified on GIL builds)

Per the ledger Notes, F011 cannot be reproduced on a GIL-enabled harness. The test asserts the *structural fix-target* — that the relevant C extension symbol is structured to acquire the appropriate critical section — rather than triggering the race.

- [ ] **Step 1: Create the file**

- [ ] **Step 2: Write `test_F011_str_list_unify_uses_ft_safe_listitem`**

Two-pronged test:
1. `pytest.skipif(not sys._is_gil_enabled(), reason="FT race only matters on Py_GIL_DISABLED")` — but the test should still be meaningful on GIL builds by asserting the *structural* fix. So actually invert: only the *race-trigger* skips on GIL.
2. Structural assertion: `inspect` `clausal/logic/variables/_variables.c` source via a string-scan (or a marker symbol) that confirms either `PyList_GetItemRef` is used, or an explicit `FT_CS_*` macro wraps the str↔list loop.

Pragmatic approach: do a small Python-level test that calls `unify(str, list)` in a tight loop under threads and asserts no crash/segfault. On GIL builds this is uninformative but harmless; on FT builds it has some signal. Mark `xfail(strict=True)` with the F011 reason.

```python
import sys
import threading

import pytest

from clausal.logic.variables import Var, unify, Trail


@pytest.mark.xfail(
    strict=True,
    reason="ledger F011: FT critical section missing in str↔list unify",
)
def test_F011_str_list_unify_ft_smoke():
    """Smoke-test concurrent str↔list unify under Python threads.

    On a GIL-enabled build this is essentially uninformative (the GIL
    serialises everything). On a free-threaded build, a missing critical
    section around PyList_GET_ITEM in the str↔list path can produce a
    segfault or wrong result. We assert that 10k iterations across 4
    threads complete without crash and produce only True outcomes.

    Currently xfail because the C path lacks the critical section.
    """
    errors = []
    n_iters = 10_000

    def worker():
        for _ in range(n_iters):
            chars = ["h", "e", "l", "l", "o"]
            try:
                t = Trail()
                if not unify("hello", chars, t):
                    errors.append(("unify returned False unexpectedly",))
            except Exception as e:
                errors.append((type(e).__name__, str(e)))

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"errors during concurrent str↔list unify: {errors[:5]}"
```

- [ ] **Step 3: Run pytest, confirm xfail (or expected pass on GIL builds)**

On a GIL-enabled harness the test will likely PASS (no race possible), which triggers the strict-xfail "unexpected pass" failure. That's actually fine here — the test is xfail because the fix isn't in, but the GIL harness can't reproduce. **In this specific case**, change the marker to `xfail(strict=False, reason="ledger F011: only reproducible on Py_GIL_DISABLED")` so a GIL-passing run doesn't break the suite. Document the strict-False exception in the test docstring.

- [ ] **Step 4: Commit**

```bash
git commit -m "test(audit): C16 FT safety adversarial xfail (F011)"
```

---

## Task 14: C17 — Performance / memory / leaks (2 findings)

**File:** `tests/audit_2026_05_25/test_class_C17_perf_memory.py`

**Findings:** F009 (perf — per-element substring allocation), F026 (perf — `_multi_star_splits` combinatorial cost). F078 (smell — dead non-ASCII branch in the C accelerator) is intentionally **not** tested in Phase 1: per the spec, smell findings get tests only when cheap, and F078 requires C-level branch-coverage instrumentation that isn't worth the effort here. It stays as a ledger-only item for Phase 2 to address with a code-reading fix.

`perf` findings are tested only when cheap; both F009 and F026 are amenable to a brief asymptotic-shape test.

- [ ] **Step 1: Create the file**

- [ ] **Step 2: Write `test_F009_str_list_unify_no_per_element_alloc_growth`**

Use `tracemalloc` or `sys.getsizeof` deltas to assert the C-level unify of a 1000-char str against a 1000-element char list doesn't allocate proportional-to-N temporary objects.

Pragmatic: time `unify("a"*N, ["a"]*N, Trail())` for N=100 vs N=10000 and assert linear scaling (the 100x growth should produce ≤200x time, not 10000x).

- [ ] **Step 3: Write `test_F026_multi_star_splits_avoids_exponential_growth`**

Assert that `_multi_star_splits(n_stars=10, remainder=20)` returns in <1s. Currently O(C(remainder+n_stars-1, n_stars-1)) which is manageable for these sizes but quickly explodes.

- [ ] **Step 4: Run pytest, confirm 2 xfails**

- [ ] **Step 5: Commit**

```bash
git commit -m "test(audit): C17 perf/memory adversarial xfails (F009, F026)"
```

---

## Task 15: Cross-class verification + summary

**Files:** none new; checks existing.

- [ ] **Step 1: Run the entire audit test directory**

```bash
pytest tests/audit_2026_05_25/ -v 2>&1 | tail -100
```

Expected output structure:
- Total xfailed: ~56 (sum of findings across all classes minus 0-1 unexpected passes)
- 0 failed
- 0 errored
- The summary line should show `XFAIL: 56` (approximately).

Reconcile: count the test functions across all `test_class_C*.py` files vs the count of `bug`/`design-gap` findings in the ledger (53) + smell tests written (1) + perf tests written (2). Expect 56.

If any test PASSED (unexpected): re-check the ledger entry and the probe. Likely the test is wrong or the bug isn't where the ledger claims. Fix the test; if the bug really is gone, re-grade the ledger entry to "fixed" and remove the xfail marker.

If any test ERRORED (setup broken): fix the test; do not leave broken tests in the suite.

- [ ] **Step 2: Run the pre-existing pytest suite to confirm zero regressions**

```bash
pytest tests/ --ignore=tests/audit_2026_05_25 -v 2>&1 | tail -30
```

Expected: same number of pass/fail/xfail as before Phase 1 started. Phase 1 added only new tests; existing tests must be untouched.

- [ ] **Step 3: Update the audit README**

Edit `docs/superpowers/audits/2026-05-25-string-implementation/README.md`. Add a section:

```markdown
## Phase 1 status

- **Test files:** 14 (`tests/audit_2026_05_25/test_class_C*.py`)
- **Tests:** ~56, all xfail-strict (or xfail-non-strict for F011 due to GIL-build limitation)
- **Pre-existing suite:** verified unchanged

Phase 2 fixes will flip xfails to passes; each fix commit must remove
the corresponding xfail marker(s).
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/audits/2026-05-25-string-implementation/README.md
git commit -m "$(cat <<'EOF'
docs(audit): Phase 1 status — 14 test files, ~56 xfail-strict tests

All Phase 1 adversarial tests are in place. Pre-existing pytest suite
verified unchanged. Phase 2 will flip xfails to passes class-by-class.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 16: Write Phase 2 plan stub

**Files:**
- Create: `docs/superpowers/plans/2026-05-25-string-audit-phase-2.md`

- [ ] **Step 1: Write the stub**

```markdown
# String Implementation Audit — Phase 2 Implementation Plan

**Status:** STUB — to be expanded from the Phase 0 ledger + Phase 1 test suite.

**Goal:** Land one fix commit per audit class, flipping the corresponding
`tests/audit_2026_05_25/test_class_C<N>_*.py` xfails to passes. Each commit
also removes/updates the lock-in tests in `tests/test_*.py` that codified
the old buggy contract.

**Architecture:** Class-by-class fixes in the Phase 0-recommended order
(`docs/superpowers/audits/2026-05-25-string-implementation/findings.md`
Phase 0 conclusion section). Each fix commit:
1. Implements the fix in the relevant `clausal/` source file(s).
2. Removes the xfail markers from `tests/audit_2026_05_25/test_class_C<N>_*.py`
   for the findings closed by the fix.
3. Updates or deletes the lock-in tests in the pre-existing suite as needed.
4. Runs the full pytest suite — zero regressions allowed.
5. Updates the ledger entry status: `open` → `fixed in <sha>`.

**Recommended ordering** (from Phase 0 conclusion):
1. C17 (perf/smell)
2. C7 (doc-only)
3. C12 (chr() range guard)
4. C16 (FT critical section)
5. C5 (Seg* hash/eq)
6. C2 (non-det protocol)
7. C8 (Seg* sequence protocol)
8. C15 (runtime_arg_key canonicalisation — must precede C4)
9. C13 (register Seg* + add string/atomic/1)
10. C14 (copy_term/term_variables Seg* registration)
11. C3 (SegString blind-spot sweep — closes ~16 findings)
12. C9 (_as_items extension + output-shape fixes)
13. C1 (type-source plumbing)
14. C10 (DCG depends on C3+C1)
15. C4 (F046 + F095 sub-plan — highest blast radius)

**Lock-in test handling:** When fixing C1/C10/C13/C14, the Phase 2 commit
must also update or delete the corresponding tests in:
- `tests/test_seglist_creation.py` (F033, F042)
- `tests/test_dcg.py` (F067)
- `tests/test_string_list_builtins.py` (F080)
- `tests/test_term_inspection.py` (F092, F093)

Phase 1 leaves these tests untouched; Phase 2 owns the contract change.

**Tasks:** To be written by invoking superpowers:writing-plans with this
stub + the completed ledger + the Phase 1 test suite as input. Expected
output: ~15 tasks, one per class fix, plus a final sweep task.

**Inputs for plan-writing:**
- Spec: `docs/superpowers/specs/2026-05-25-string-implementation-audit-design.md`
- Ledger: `docs/superpowers/audits/2026-05-25-string-implementation/findings.md`
- Coverage: `docs/superpowers/audits/2026-05-25-string-implementation/test_coverage.md`
- Phase 1 plan + tests: `docs/superpowers/plans/2026-05-25-string-audit-phase-1.md` + `tests/audit_2026_05_25/`
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/plans/2026-05-25-string-audit-phase-2.md
git commit -m "docs(audit): stub Phase 2 plan, to be filled from ledger + Phase 1 tests"
```

---

## Phase 1 exit criteria (must all be true)

- [ ] `tests/audit_2026_05_25/__init__.py`, `conftest.py`, `_helpers.py` exist.
- [ ] One `test_class_C<N>_*.py` file exists for every class with findings (C1, C2, C3, C4, C5, C8, C9, C10, C12, C13, C14, C15, C16, C17 — 14 files).
- [ ] Every `bug` or `design-gap` finding in the ledger has at least one xfail-strict test referencing its F-ID.
- [ ] F011 test is xfail-non-strict (documented exception for GIL-build limitation).
- [ ] `pytest tests/audit_2026_05_25/ -v` shows ~56 XFAIL, 0 FAILED, 0 ERRORED.
- [ ] `pytest tests/ --ignore=tests/audit_2026_05_25 -v` shows no regressions vs pre-Phase-1 baseline.
- [ ] Phase 2 stub plan exists at `docs/superpowers/plans/2026-05-25-string-audit-phase-2.md`.
- [ ] README updated to show Phase 1 status.

If any of these are not satisfied, do not proceed to Phase 2 — go back and finish Phase 1.
