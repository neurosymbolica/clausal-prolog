# String Implementation Audit — Phase 0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a complete, cross-referenced ledger of issues in the Clausal strings-as-lists implementation, covering core unification + integration surfaces, tagged by class (C1–C17) and severity (`bug`/`design-gap`/`perf`/`smell`/`doc-only`). No source code changes in this plan — only the ledger, probe scripts, and a test-coverage inventory.

**Architecture:** Read-only audit. Each task targets one surface, follows a fixed loop (read → probe to confirm suspected behaviour → append to ledger → commit). Probes are tiny self-contained Python scripts kept in `docs/superpowers/audits/2026-05-25-string-implementation/probes/` so any reviewer can re-run them. The ledger is one markdown file grown by append, grouped by class. After all surfaces are covered, a final task cross-references duplicates, sorts within class, and produces a Phase 1 handoff.

**Tech Stack:** Python 3.13+, pytest (for probes), the existing Clausal build (`pip install -e .` already done in this worktree). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-05-25-string-implementation-audit-design.md` (commits `ef73a58`, `d4fa795`).

---

## Conventions used throughout this plan

### Ledger entry format

Every finding is appended as one entry:

```markdown
### F<NNN> — <one-line title>

- **Class:** C<N> (<class name>)
- **Severity:** bug | design-gap | perf | smell | doc-only
- **Location:** `path/to/file.py:LINE` (or `:LINE_RANGE`)
- **Discovered by:** Task <N> of Phase 0
- **Probe:** `probes/probe_F<NNN>.py` *(when applicable)*
- **Prior-known:** commit `<sha>` or doc reference *(when applicable)*

**Symptom:** <one-paragraph description of the wrong/surprising behaviour>

**Reproducer:**
\`\`\`python
# minimal Python or Clausal snippet that exhibits the symptom
\`\`\`

**Expected:** <one-sentence>
**Actual:** <one-sentence>

**Notes:** <free-form, optional — context, cross-refs to related findings via [[F<NNN>]] links, scope-of-fix sketch>
```

Findings are numbered `F001, F002, …` in discovery order. Re-numbering on commit is forbidden — links would break.

### Probe script format

Probes live at `docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F<NNN>.py`. Each probe is self-contained: imports from `clausal`, exercises the suspected behaviour, and prints both expected and actual in a way a reviewer can read at a glance. Probes are NOT pytest tests — they exist to *confirm a hypothesis before logging it*. Phase 1 will convert promoted findings into real tests.

Probe template:

```python
"""Probe F<NNN>: <one-line description>.

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F<NNN>.py
"""
from clausal import ...  # narrow imports — never `from clausal import *`

def main() -> None:
    # ... exercise the suspected behaviour ...
    expected = ...
    actual = ...
    print(f"Probe F<NNN>: <description>")
    print(f"  Expected: {expected!r}")
    print(f"  Actual:   {actual!r}")
    print(f"  Match:    {expected == actual}")

if __name__ == "__main__":
    main()
```

### Commit message style (matches repo convention)

```
docs(audit): <surface> findings (Fnnn-Fnnn)

<one-paragraph summary of what was added — number of findings,
notable classes, anything unusual>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

### When to pause for user input

Per the spec, pause before:
- recommending a `wontfix` decision on anything the user might want fixed,
- recommending a contract change (e.g. "we should redefine what `[H|T] = "abc"` binds T to"),
- if C4 (head-pattern literal mismatch) confirms with very large blast radius — flag to the user before continuing the audit.

Otherwise: proceed. Phase 0 is read-only; nothing it logs is irreversible.

---

## Task 0: Initialise audit directory and ledger skeleton

**Files:**
- Create: `docs/superpowers/audits/2026-05-25-string-implementation/findings.md`
- Create: `docs/superpowers/audits/2026-05-25-string-implementation/probes/.gitkeep`
- Create: `docs/superpowers/audits/2026-05-25-string-implementation/README.md`

- [ ] **Step 1: Create the audit directory layout**

```bash
mkdir -p docs/superpowers/audits/2026-05-25-string-implementation/probes
touch docs/superpowers/audits/2026-05-25-string-implementation/probes/.gitkeep
```

- [ ] **Step 2: Write the README**

Write `docs/superpowers/audits/2026-05-25-string-implementation/README.md`:

```markdown
# String Implementation Audit — 2026-05-25

This directory holds the artifacts of the strings-as-lists audit.

- **Design spec:** `../../specs/2026-05-25-string-implementation-audit-design.md`
- **Phase 0 plan:** `../../plans/2026-05-25-string-audit-phase-0.md`
- **Ledger:** [findings.md](findings.md) — every issue found, grouped by
  class C1–C17, sorted by severity within class.
- **Probes:** [probes/](probes/) — self-contained Python scripts that
  confirm each finding's symptom. Re-runnable; not pytest tests.
- **Test coverage inventory:** [test_coverage.md](test_coverage.md) —
  which existing tests cover which surface; informs Phase 1.

## How to read the ledger

Each finding has a stable ID (F001…). Phase 1 test files and Phase 2 fix
commits reference these IDs. IDs are never re-numbered. Findings link to
related findings via wiki-style `[[Fnnn]]` syntax.

## How to re-run a probe

```bash
python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F042.py
```
```

- [ ] **Step 3: Write the ledger skeleton**

Write `docs/superpowers/audits/2026-05-25-string-implementation/findings.md`:

```markdown
# String Implementation Audit — Findings Ledger

**Spec:** [../../specs/2026-05-25-string-implementation-audit-design.md](../../specs/2026-05-25-string-implementation-audit-design.md)
**Phase 0 plan:** [../../plans/2026-05-25-string-audit-phase-0.md](../../plans/2026-05-25-string-audit-phase-0.md)
**Status:** Phase 0 in progress

## Summary by class

| Class | Title | Bug | Design-gap | Perf | Smell | Doc-only |
|-------|-------|-----|-----------:|-----:|------:|---------:|
| C1 | Type preservation | 0 | 0 | 0 | 0 | 0 |
| C2 | Non-det collapsed to first | 0 | 0 | 0 | 0 | 0 |
| C3 | SegString blind spots vs SegList | 0 | 0 | 0 | 0 | 0 |
| C4 | Head-pattern literal mismatch | 0 | 0 | 0 | 0 | 0 |
| C5 | Hash/eq asymmetries | 0 | 0 | 0 | 0 | 0 |
| C6 | Hashable vs unhashable bridges | 0 | 0 | 0 | 0 | 0 |
| C7 | Unicode / multi-codepoint | 0 | 0 | 0 | 0 | 0 |
| C8 | Partial-term short-circuits | 0 | 0 | 0 | 0 | 0 |
| C9 | Polymorphic builtin mode matrix | 0 | 0 | 0 | 0 | 0 |
| C10 | DCG / phrase interaction | 0 | 0 | 0 | 0 | 0 |
| C11 | Trail/backtracking around partials | 0 | 0 | 0 | 0 | 0 |
| C12 | Char representation drift | 0 | 0 | 0 | 0 | 0 |
| C13 | Type-check predicates | 0 | 0 | 0 | 0 | 0 |
| C14 | Term inspection drift | 0 | 0 | 0 | 0 | 0 |
| C15 | First-arg indexing on strings | 0 | 0 | 0 | 0 | 0 |
| C16 | Free-threaded build safety | 0 | 0 | 0 | 0 | 0 |
| C17 | Performance, memory, leaks | 0 | 0 | 0 | 0 | 0 |
| —   | Out-of-taxonomy | 0 | 0 | 0 | 0 | 0 |

(Counts updated at the end of each task.)

## Findings

<!-- Findings appended below, grouped by class then severity. -->

### Class C1 — Type preservation
*(none yet)*

### Class C2 — Non-det collapsed to first
*(none yet)*

### Class C3 — SegString blind spots vs SegList
*(none yet)*

### Class C4 — Head-pattern literal mismatch
*(none yet)*

### Class C5 — Hash/eq asymmetries
*(none yet)*

### Class C6 — Hashable vs unhashable bridges
*(none yet)*

### Class C7 — Unicode / multi-codepoint
*(none yet)*

### Class C8 — Partial-term short-circuits
*(none yet)*

### Class C9 — Polymorphic builtin mode matrix
*(none yet)*

### Class C10 — DCG / phrase interaction
*(none yet)*

### Class C11 — Trail/backtracking around partials
*(none yet)*

### Class C12 — Char representation drift
*(none yet)*

### Class C13 — Type-check predicates
*(none yet)*

### Class C14 — Term inspection drift
*(none yet)*

### Class C15 — First-arg indexing on strings
*(none yet)*

### Class C16 — Free-threaded build safety
*(none yet)*

### Class C17 — Performance, memory, leaks
*(none yet)*

### Out-of-taxonomy
*(none yet)*
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/audits/2026-05-25-string-implementation/
git commit -m "$(cat <<'EOF'
docs(audit): scaffold string-implementation audit directory

Initial scaffolding: README, empty findings ledger with the C1-C17 class
sections, probes/ directory. No findings yet.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 1: Audit C-level str↔list path in `_variables.c`

**Files:**
- Read: `clausal/logic/variables/_variables.c` (lines 1086–1200 are the relevant unification block; whole file for context on FT_CS_*, var_deref, do_unify, Py_INCREF/DECREF discipline)
- Modify: `docs/superpowers/audits/2026-05-25-string-implementation/findings.md` (append findings to C1, C2, C5, C6, C7, C8, C16, C17 as applicable)
- Create: `docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F*.py` (one per confirmed finding)

- [ ] **Step 1: Read the unification entry path**

Read `clausal/logic/variables/_variables.c` from line 1080 onwards. Read at least through line 1250 (covers the str↔list path, the `__unify__` protocol hook dispatch, and the structural-comparison fallback). Take notes (mental or scratch) on:

- The two str↔list branches (PyUnicode/PyList and PyList/PyUnicode) — are they symmetric?
- Empty-string / empty-list handling (the `if (n == 0) return 1;` branches).
- Refcount discipline on the `PyUnicode_Substring` allocations (every alloc must be paired with `Py_DECREF` on every return path including error returns).
- The `var_deref` calls — borrowed vs new refs.
- What happens if a list element is itself a Var pointing to a multi-char string?
- What happens if a list element is itself a list or another non-str type?
- Unicode handling: `PyUnicode_GET_LENGTH` is code-point count; `PyUnicode_READ_CHAR` reads one code point. What about combining characters? Surrogate halves?
- The `__unify__` protocol hook check at line 1188 — does it fire for SegString-vs-list? (It's only reached when `t1` is neither list nor tuple, so for `SegString.__unify__(list)` it should fire — confirm.)
- FT_CS_* macros around the str↔list block — present or absent?

- [ ] **Step 2: Write probes for the suspected findings**

For each behaviour you want to confirm before logging, write a probe at `probes/probe_F<next>.py`. Start IDs at F001. Examples of probes you'll likely write here (adjust based on what you actually see):

```python
# probes/probe_F001.py
"""Probe F001: empty string unifies with empty list at C level."""
from clausal.logic.variables import Var, unify, Trail

def main():
    t = Trail()
    actual = unify("", [], t)
    print(f"Probe F001: empty str unifies with empty list")
    print(f"  Expected: True")
    print(f"  Actual:   {actual}")

if __name__ == "__main__":
    main()
```

```python
# probes/probe_F002.py
"""Probe F002: multi-codepoint emoji vs char list."""
from clausal.logic.variables import Var, unify, Trail

def main():
    t = Trail()
    s = "👍🏽"  # thumbs-up + skin-tone modifier (2 code points)
    chars = ["👍", "🏽"]
    actual = unify(s, chars, t)
    print(f"Probe F002: 'thumbs up dark' vs ['thumbs up', 'dark']")
    print(f"  len(s): {len(s)}, len(chars): {len(chars)}")
    print(f"  Expected: True (code-point-level match)")
    print(f"  Actual:   {actual}")

if __name__ == "__main__":
    main()
```

Run each probe to confirm the actual behaviour:

```bash
python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F001.py
```

- [ ] **Step 3: Append findings to the ledger**

For each confirmed finding, append an entry to `findings.md` under the appropriate class section, using the ledger entry format from the conventions section. Examples:

- Any refcount imbalance you spot → C17 / `bug`.
- Any silent acceptance of malformed Unicode → C7 / `bug` or `design-gap`.
- Any missing FT_CS_* around code that might need it → C16 / `bug` or `smell`.
- Empty-string-vs-empty-list — if it works, that's not a finding (no entry); if there's a corner case where it doesn't, log it under C8.

After appending, update the summary table at the top of `findings.md` with the new counts.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/audits/2026-05-25-string-implementation/findings.md \
        docs/superpowers/audits/2026-05-25-string-implementation/probes/
git commit -m "$(cat <<'EOF'
docs(audit): C-level str↔list path findings (F001-Fnnn)

Audit of clausal/logic/variables/_variables.c str↔list unification path,
PyUnicode_Substring refcount discipline, FT critical-section coverage,
and Unicode/grapheme-cluster handling.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Replace `Fnnn` with the actual range of finding IDs created in this task.

---

## Task 2: Audit `SegList` / `SegString` / `VarSeg` in `terms.py`

**Files:**
- Read: `clausal/terms.py` lines 174–630 (covers ConcreteSeg, VarSeg, SegList, _seglist_unify_gen, _multi_star_splits, SegString, _segstring_unify_gen)
- Modify: `docs/superpowers/audits/2026-05-25-string-implementation/findings.md`
- Create: `probes/probe_F*.py` as needed

- [ ] **Step 1: Read `SegList` end-to-end**

Lines 189–387 (`SegList` class through `__repr__`) plus the generator helpers at 390–443. Cover every dunder:

- `__walk__` (lines 213–279): the VarSeg-bound-to-str branch at 227–234 expands to chars — that's a C1 type-preservation candidate. Confirm.
- `__occurs_check__` (296–306): does it recurse into nested SegLists?
- `__unify__(other, trail)` (308–330): the `for _ in _seglist_unify_gen(...): return True` pattern is the C2 first-solution-only candidate. Confirm by writing a probe that calls unify with `[*A, *B] = [1,2,3]` and counts solutions vs. the gen.
- `__len__`, `__iter__`, `__contains__`, `__getitem__` (332–351): all delegate to `to_list()` which raises on non-ground — C8 silent-failure / crash candidate.
- `__add__`, `__radd__` (353–364): asymmetric with strings? `SegList + str` → not handled (falls through to NotImplemented). Confirm.
- `__eq__` (366–374): rejects `str`. Confirm asymmetry with `SegString.__eq__`.
- `__hash__` (376–378): raises TypeError unconditionally. Confirm.
- `_seglist_unify_gen` (390–426): trail mark/undo discipline — does the *generator* leave the trail at its prior length after each iteration?
- `_multi_star_splits` (429–443): correctness with n_stars=0, remainder=0; combinatorial blowup with large n.

- [ ] **Step 2: Read `SegString` end-to-end**

Lines 449–627 plus the generator helper at 594–627. Cover every dunder, mirroring Step 1. Specific items to confirm:

- `__walk__` (475–528): the bound-to-list branch at 493–499 collapses lists into strings via `"".join(v)` — works only when list elements are 1-char strings; what if some are multi-char or non-str?
- `__unify__(other, trail)` with `list` (lines 565–573): only works when SegString is ground — C3 / C8 candidate.
- `__hash__` (589–591): returns `id(self)` when non-ground — C5 inconsistency with SegList. Probe its effect in a `set`/`dict`.
- `__eq__` (581–587): accepts `str`. Asymmetry with SegList.__eq__.
- `_segstring_unify_gen` (594–627): same first-solution-only question as SegList. Confirm.

- [ ] **Step 3: Write probes**

For each suspected finding, write a probe under `probes/`. Likely candidates:

```python
# probes/probe_F<N>.py: SegList only returns first split
from clausal.logic.variables import Var, unify, Trail, deref
from clausal.terms import SegList, VarSeg

def main():
    A, B = Var(), Var()
    sl = SegList([VarSeg(A), VarSeg(B)])
    t = Trail()
    # SegList = [1, 2, 3] should have 4 splits: (0,3), (1,2), (2,1), (3,0)
    # _seglist_unify_gen enumerates them all; __unify__ only takes the first
    ok = unify(sl, [1, 2, 3], t)
    print(f"  unify(SegList[*A,*B], [1,2,3]) → {ok}")
    print(f"  A = {deref(A)!r}, B = {deref(B)!r}")
    # Then probe how many splits the gen actually offers
    from clausal.terms import _seglist_unify_gen
    t2 = Trail()
    sl2 = SegList([VarSeg(Var()), VarSeg(Var())])
    n = sum(1 for _ in _seglist_unify_gen(sl2, [1, 2, 3], t2))
    print(f"  _seglist_unify_gen yields {n} splits (expected: 4)")

if __name__ == "__main__":
    main()
```

```python
# probes/probe_F<N>.py: SegList.__eq__ vs SegString.__eq__ asymmetry
from clausal.terms import SegList, SegString, ConcreteSeg

def main():
    sl = SegList([ConcreteSeg(["a", "b", "c"])])
    ss = SegString(["abc"])
    print(f"  SegList(['a','b','c']) == 'abc'  → {sl == 'abc'}")
    print(f"  SegString('abc')      == 'abc'  → {ss == 'abc'}")
    print(f"  SegList(['a','b','c']) == ['a','b','c'] → {sl == ['a','b','c']}")
    print(f"  SegString('abc')      == ['a','b','c'] → {ss == ['a','b','c']}")

if __name__ == "__main__":
    main()
```

```python
# probes/probe_F<N>.py: SegString.__hash__ non-ground returns id
from clausal.logic.variables import Var
from clausal.terms import SegString, VarSeg

def main():
    X = Var()
    ss1 = SegString(["a", VarSeg(X), "c"])
    ss2 = SegString(["a", VarSeg(X), "c"])
    print(f"  hash(ss1) = {hash(ss1)}")
    print(f"  hash(ss2) = {hash(ss2)}")
    print(f"  ss1 == ss2 → {ss1 == ss2} (probably True via __eq__)")
    print(f"  hash equal → {hash(ss1) == hash(ss2)} (probably False — id-based)")
    print(f"  → {{ss1: 1, ss2: 2}} keeps both? {len({ss1: 1, ss2: 2})}")

if __name__ == "__main__":
    main()
```

Run each probe and confirm output before logging.

- [ ] **Step 4: Append findings, update summary table, commit**

For each confirmed finding, append a ledger entry. Then update the C1/C2/C3/C5/C8/C17 counts in the summary table.

```bash
git add docs/superpowers/audits/2026-05-25-string-implementation/
git commit -m "$(cat <<'EOF'
docs(audit): SegList/SegString/VarSeg findings (Fnnn-Fnnn)

Audit of clausal/terms.py SegList, SegString, VarSeg, ConcreteSeg
classes and their generator helpers. Covers walk-time type preservation,
non-deterministic unification, hash/eq asymmetries, partial-term
short-circuits, and trail discipline in the generators.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Audit `list_unify.py` runtime (head input/output)

**Files:**
- Read: `clausal/logic/runtime/list_unify.py` (full file — 213 lines)
- Read: `clausal/logic/runtime/_list_unify.c` (C-accelerated version — confirm parity with Python fallback)
- Modify: `docs/superpowers/audits/2026-05-25-string-implementation/findings.md`
- Create: `probes/probe_F*.py` as needed

- [ ] **Step 1: Read the Python reference impl end-to-end**

`_head_list_unify_input_py` (lines 87–146) and `_head_list_unify_output_py` (156–200). Focus on:

- Fast path at lines 101–109: `type(d) is list and star_val is not None and not after_vals` — strings deliberately take the slow path. Confirm the slow path handles strings correctly via slicing.
- SegList normalisation at lines 114–117: walks SegList, falls back if not list/str. **No SegString normalisation** — confirm by writing a probe that passes a non-ground SegString to a `[H, *T]`-style head.
- Output mode (lines 156–200): always builds `result` as a list (line 165). When the deferred-output target's *original* type was str, this is C1.
- The `is_var(d)` branch at 141–143 — defers to output mode. Correct?

- [ ] **Step 2: Find the C-accelerated counterpart**

```bash
ls clausal/logic/runtime/_list_unify.c 2>/dev/null || \
  find clausal/logic/runtime -name "_list_unify*"
```

If it exists, read it and confirm whether it has the same SegList walk + same SegString-blind-spot as the Python fallback. If the C version handles SegString and the Python fallback doesn't (or vice versa), that's a C3 finding (`bug`: behaviour differs depending on whether C extension is built).

- [ ] **Step 3: Write probes**

```python
# probes/probe_F<N>.py: head [H, *T] against non-ground SegString silently fails
from clausal.logic.variables import Var, unify, Trail, deref
from clausal.terms import SegString, VarSeg
from clausal.logic.runtime.list_unify import _head_list_unify_input

def main():
    H, T = Var(), Var()
    X = Var()  # unbound — will make SegString non-ground
    seg = SegString(["a", VarSeg(X), "c"])
    t = Trail()
    result = _head_list_unify_input(seg, [H], T, [], t)
    print(f"  head_list_unify_input(non-ground SegString, [H], T) → {result}")
    print(f"  H = {deref(H)!r}")
    print(f"  T = {deref(T)!r}")
    print(f"  Expected: defer or constrain; Actual: probably False (silent failure)")

if __name__ == "__main__":
    main()
```

```python
# probes/probe_F<N>.py: output mode always builds list, never str
from clausal.logic.variables import Var, unify, Trail, deref
from clausal.logic.runtime.list_unify import _head_list_unify_output

def main():
    target = Var()
    H, T = Var(), Var()
    # Bind H and T as if from a body that consumed a string
    unify(H, "h", Trail())
    unify(T, "ello", Trail())  # str-typed tail
    t = Trail()
    result = _head_list_unify_output(target, [H], T, [], t)
    print(f"  output mode result: {deref(target)!r}")
    print(f"  type: {type(deref(target)).__name__}")
    print(f"  Expected: 'hello' (str); Actual: probably ['h', 'e', 'l', 'l', 'o']")

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Append findings, update summary, commit**

```bash
git add docs/superpowers/audits/2026-05-25-string-implementation/
git commit -m "$(cat <<'EOF'
docs(audit): list_unify.py head input/output findings (Fnnn-Fnnn)

Audit of clausal/logic/runtime/list_unify.py and the C-accelerated
overrides in _list_unify.c. Covers SegString blind spots in the head-input
path, type loss in the head-output path, and C-vs-Python fallback parity.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Audit `body_star_unify.py` runtime

**Files:**
- Read: `clausal/logic/runtime/body_star_unify.py` (full file — 305 lines)
- Modify: `docs/superpowers/audits/2026-05-25-string-implementation/findings.md`
- Create: `probes/probe_F*.py` as needed

- [ ] **Step 1: Read each function**

- `_body_star_unify` (lines 26–47): delegates to `_head_list_unify_input` for list / ground-SegList; to `_head_list_unify_output` for Var. Inherits all C3/C1 findings from Task 3.
- `_build_star_list` (50–126): string-preservation only fires when **all** before/after elements are 1-char strs (lines 64–67, 89–91, 96–97). Probe what happens with mixed types or empty before/after.
- `_build_multi_star_list` (129–205): tracks `all_str` flag. Probe edge cases — what if a star is bound to `""` (empty string)? What if `segs` ends up containing only one ConcreteSeg of strs?
- `_in_iter` (208–217): calls `iter(collection)` — on a non-ground SegList/SegString this routes through `to_list()` which raises. C8 candidate.
- `_body_multi_star_unify` (220–304): non-ground SegList branch at 235–248 constructs a SegList and binds — does it also handle non-ground SegString? (Probably not — C3.) Unbound target builds SegList always — C1 candidate (should sometimes build SegString).

- [ ] **Step 2: Write probes**

```python
# probes/probe_F<N>.py: _build_star_list mixed types lose str
from clausal.logic.runtime.body_star_unify import _build_star_list
from clausal.logic.variables import Var, unify, Trail

def main():
    X = Var()
    t = Trail()
    unify(X, "ello", t)
    # before is a single-char str, star is "ello", after is empty
    result = _build_star_list(["h"], X, [])
    print(f"  _build_star_list(['h'], 'ello', []) = {result!r}")
    # Now mixed: before is a 1-char str, after is a 2-char str (not 1)
    result2 = _build_star_list(["h"], X, ["lo"])
    print(f"  _build_star_list(['h'], 'ello', ['lo']) = {result2!r}")

if __name__ == "__main__":
    main()
```

```python
# probes/probe_F<N>.py: _in_iter on non-ground SegList raises
from clausal.logic.runtime.body_star_unify import _in_iter
from clausal.logic.variables import Var
from clausal.terms import SegList, VarSeg, ConcreteSeg

def main():
    seg = SegList([ConcreteSeg([1, 2]), VarSeg(Var()), ConcreteSeg([5])])
    try:
        it = _in_iter(seg, pair_mode=False)
        items = list(it)
        print(f"  _in_iter returned: {items!r}")
    except Exception as e:
        print(f"  _in_iter raised {type(e).__name__}: {e}")
    print(f"  Expected: deferred or enumerated; Actual: TypeError")

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Append findings, update summary, commit**

```bash
git add docs/superpowers/audits/2026-05-25-string-implementation/
git commit -m "$(cat <<'EOF'
docs(audit): body_star_unify.py findings (Fnnn-Fnnn)

Audit of clausal/logic/runtime/body_star_unify.py. Covers _build_star_list
type-preservation thresholds, _build_multi_star_list edge cases, _in_iter
on partial terms, and _body_multi_star_unify SegString parity.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Audit `head_match.py` compiler (head_to_match_pattern + multi-star guard)

**Files:**
- Read: `clausal/logic/compiler/head_match.py` (full file — 1176 lines)
- Modify: `docs/superpowers/audits/2026-05-25-string-implementation/findings.md`
- Create: `probes/probe_F*.py` as needed

- [ ] **Step 1: Read `head_to_match_pattern`**

Lines 187–538. Three things to confirm:

1. **String literal heads (the C4 candidate, lines 253–254)**: a head arg that is a Python `str` compiles to `MatchValue(Constant(value=term))`. Python `match` `MatchValue` uses `==` comparison. So `Foo("abc")` clause head matched against a caller's `Foo(['a','b','c'])` — does Python's `match` pass `['a','b','c']` to `==` against `"abc"`, getting False? Confirm with a probe that compiles a clause with a string head and calls it with a char-list.

2. **Compound heads containing strings**: a head like `Foo(bar("abc"))` — same issue recurses through `MatchClass` patterns into `MatchValue`.

3. **List heads**: lines 258–448 — well-trodden, but check whether anything about `StarUnpack` in a list head against a string caller is mishandled. Most fast-path checks are `type(d) is list` — strings will skip.

- [ ] **Step 2: Read `_compile_multi_star_guard`**

Lines 544–874. The emitted code includes (line 856–872) a `seglist_normalise` branch that walks SegList but **no SegString counterpart**. Confirm with a probe that compiles a clause matching `Foo([H, *Mid, T])` and calls it with a non-ground SegString.

The `isinstance_check` at line 802–805 covers `(list, str)` — good. But the SegList walk happens before the isinstance check (line 857–872); the SegString walk doesn't exist. So a non-ground SegString reaches the isinstance check, fails it, and the clause silently doesn't match — C3 + C8 candidate.

- [ ] **Step 3a: Find the project's clause-registration pattern**

Read `tests/test_string_head_patterns.py` end-to-end (177 lines). Note the exact pattern used to:
1. Define a clausal module/predicate inline from a Python test.
2. Call the predicate with a specific argument and collect solutions.

Likely the file uses either `.clausal` source via the import hook, or a direct `Database` + `compile_clause` API. Whichever pattern it uses, the C4 probe will use the same one.

Also read the first 50 lines of `tests/test_string_list_unification.py` for the unification-call pattern.

- [ ] **Step 3b: Probe C4 (head literal mismatch) — confirm before continuing**

Write `probes/probe_F<N>.py` using the pattern found in Step 3a. The probe must:

1. Register two facts: `Foo("abc")` and `Bar(['a', 'b', 'c'])`.
2. Call `Foo(['a', 'b', 'c'])` and count solutions (expected: 1 if C4 is *not* a bug; 0 if it *is*).
3. Call `Bar("abc")` and count solutions (same expectation).
4. Print both counts and a verdict line: `C4 confirmed (bug)` or `C4 not present`.

Skeleton (adapt the imports/calls to match Step 3a's findings):

```python
"""Probe F<N>: C4 — head string literal vs char-list caller (and vice versa).

This is the largest-blast-radius finding in the audit. If it confirms,
stop and notify the user before logging — the fix scope is potentially
compiler-wide.
"""
# Imports come from Step 3a's pattern. Example shape:
# from clausal import Var
# from clausal.logic.compiler.predicate import compile_fact
# from clausal.logic.database import Database

def main():
    # Register Foo("abc") and Bar(['a','b','c']) into a fresh Database
    # ... using the pattern from Step 3a ...

    # Call Foo(['a','b','c']) — count solutions
    n_foo = ...  # solutions found
    # Call Bar("abc") — count solutions
    n_bar = ...

    print(f"  Foo(\"abc\") called with ['a','b','c']: {n_foo} solutions")
    print(f"  Bar(['a','b','c']) called with \"abc\": {n_bar} solutions")
    print(f"  Expected (strings-as-lists contract): 1 and 1")
    if n_foo == 1 and n_bar == 1:
        print(f"  Verdict: C4 not present")
    else:
        print(f"  Verdict: C4 CONFIRMED — STOP and notify user")

if __name__ == "__main__":
    main()
```

Run the probe:

```bash
python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F<N>.py
```

- [ ] **Step 3c: If C4 confirms, stop**

Per the spec's pause points, do NOT proceed to log C4 findings without user input. Output to the user:

> "C4 (head-pattern literal mismatch) confirmed via probe F<N>. Sample
> outputs: Foo(\"abc\") called with ['a','b','c'] returned 0 solutions
> (expected 1). This is potentially compiler-wide work; recommend a
> separate spec/plan before adding C4 findings to the ledger. Continue
> with Tasks 6+ and revisit C4 after that conversation?"

Then proceed to Step 4 (next probe) and Task 6. Do NOT block the rest of the audit on C4 — defer C4 only.

If C4 does NOT confirm (e.g. the compiler emits a wrapping unify guard instead of a raw MatchValue for str heads): log a one-line ledger note under C4 saying "Task 5 Step 3b: probe F<N> confirms no mismatch; clause Foo(\"abc\") matches caller Foo(['a','b','c']) as expected.", and move on.

- [ ] **Step 4: Probe SegString multi-star blind spot**

Using the same clause-registration pattern from Step 3a, write `probes/probe_F<N>.py`:

```python
"""Probe F<N>: C3 — multi-star pattern against non-ground SegString.

The compiler's _compile_multi_star_guard (head_match.py:857-872) walks
SegList but not SegString. A clause Foo([H, *Mid, T]) called with a
non-ground SegString should either constrain the SegString or defer —
not silently fail.
"""
# Imports per Step 3a
from clausal import Var
from clausal.terms import SegString, VarSeg

def main():
    # 1. Register fact / rule with head Foo([H, *Mid, T])
    # 2. Build a non-ground SegString: SegString(["a", VarSeg(X), "z"])
    #    where X is unbound
    # 3. Call Foo(<that SegString>)
    # 4. Count solutions

    X = Var()
    arg = SegString(["a", VarSeg(X), "z"])
    n = ...  # solutions found
    print(f"  Foo([H, *Mid, T]) called with SegString(['a',*X,'z']): {n} solutions")
    print(f"  Expected: ≥1 (with H='a', T='z', Mid constrained by *X)")
    print(f"  Actual: probably 0 (silent failure — C3 confirmed)")

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Append findings, update summary, commit**

```bash
git add docs/superpowers/audits/2026-05-25-string-implementation/
git commit -m "$(cat <<'EOF'
docs(audit): head_match.py compiler findings (Fnnn-Fnnn)

Audit of clausal/logic/compiler/head_match.py — head_to_match_pattern
and _compile_multi_star_guard. Covers string-literal head matching
against char-list callers (C4), SegString blind spot in the multi-star
guard normalisation (C3).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Audit `goal_shallow.py` deferred-pattern detection

**Files:**
- Read: `clausal/logic/compiler/goal_shallow.py` lines 226–262 (the `_head_has_deferred_pattern` function) + any string-related code elsewhere in the file (grep for `str` and `SegString`)
- Modify: `docs/superpowers/audits/2026-05-25-string-implementation/findings.md`

- [ ] **Step 1: Read `_head_has_deferred_pattern`**

Lines 226–262. The function walks the head looking for `SegList` or `StarUnpack` — does it also need to check for `SegString`? If a clause head includes a `SegString` literal (does this even compile?), the continuation-TCO optimisation could skip the necessary output-mode guard.

- [ ] **Step 2: Grep for any other string-aware code in this file**

```bash
grep -n "str\|String\|SegString" clausal/logic/compiler/goal_shallow.py
```

Audit any hits.

- [ ] **Step 3: Append findings (if any), commit**

If no findings, still commit a one-line note in the ledger under "Class C3" or "Out-of-taxonomy" that says `Task 6: no findings — _head_has_deferred_pattern does not currently encounter SegString in head positions; revisit if Phase 7+ changes that.` so the audit trail is complete.

```bash
git add docs/superpowers/audits/2026-05-25-string-implementation/
git commit -m "docs(audit): goal_shallow.py findings (or: no findings)"
```

---

## Task 7: Audit polymorphic list builtins in `lists.py`

**Files:**
- Read: `clausal/logic/builtins/lists.py` (focus on every function with a `was_str` / `isinstance(_, str)` site — Task 1's grep showed ~25 sites)
- Modify: `docs/superpowers/audits/2026-05-25-string-implementation/findings.md`
- Create: `probes/probe_F*.py` for each suspected mode-matrix finding

- [ ] **Step 1: Generate the mode matrix template**

For each polymorphic predicate in `lists.py`, write down the mode matrix in a scratch note. Predicates to cover (at minimum): `append/3`, `length/2`, `member/2`, `reverse/2`, `nth/3` (and `get_item`), `take/3`, `drop/3`, `split_at/4`, `msort/2`, `last/2`, `select/3`, `permutation/2`, `flatten/2`, `concat/2`.

For each, modes are some combination of: `str`, `list`, `Var`, `SegList`, `SegString`. Don't enumerate all 5^N — focus on the ones where types could plausibly cross-contaminate (e.g. `append(str, str, Var)`, `append(Var, str, str)`, `append(str, list, Var)`, `append(list, str, Var)`).

- [ ] **Step 2: Read each predicate**

For each predicate, read its implementation and confirm:
- What it does when an input is `str`.
- What it does when an input is `list`.
- What it does when inputs mix.
- What it does when an input is a non-ground SegList or SegString.
- What it does in the all-Vars mode (if applicable).
- Whether the output type is consistent with the documented "string-preserving" rule.

Pay attention to the `_seq_result` helper (around line 53–63 of `lists.py`) — it converts back to str when `was_str and all 1-char str`. The "and all 1-char str" condition is the C1 inconsistency candidate; a `reverse(["ab","cd"])` call returns a list even though the input was a str-y `was_str=True`.

Wait — `reverse(["ab","cd"])` input is a list, not str. Re-read carefully. The `was_str` flag tracks the *input* type; the check on the *output* asks whether the result is a coherent string. Edge: what about `reverse("abc")` where result is `['c','b','a']` and all are 1-char strs → returns `"cba"`. Good. But what about something weird like `flatten(["ab", ["c"]], R)` where the input contains a str — does it get treated as a 2-char list? Probe.

- [ ] **Step 3a: Find the project's builtin-call API**

Read `tests/test_string_list_builtins.py` (408 lines) end-to-end. Note the exact pattern used to invoke a built-in predicate (e.g. `append`, `length`, `member`) with given argument types and collect solutions. Likely it uses `from clausal import call` with a predicate name string and arguments; or it uses `.clausal` source via the import hook.

Whichever pattern, the per-predicate probes in Step 3b use it verbatim.

- [ ] **Step 3b: Write probes for each suspected finding**

One probe per predicate × mode combination you want to confirm. Don't write all 50 — write the ones where reading the code makes you suspect a bug. Skip the obvious-works modes.

Probe template (adapt per Step 3a):

```python
"""Probe F<N>: append(Var, str, str) — output type of first arg."""
from clausal import Var, deref, call  # adapt to Step 3a's actual imports

def main():
    A = Var()
    # If the call API is `call(name, *args)`, this is the shape;
    # otherwise adapt per Step 3a.
    n = 0
    for _ in call("append", A, "world", "hello world"):
        n += 1
        actual = deref(A)
        actual_type = type(actual).__name__
        print(f"  Solution {n}: A = {actual!r} ({actual_type})")
    if n == 0:
        print(f"  No solutions (suspicious — append should be deterministic here)")
    print(f"  Expected: A = 'hello ' (str) per string-preservation contract")

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Append findings, update summary, commit**

This task may produce many findings (one per buggy mode). Don't try to be exhaustive — log the suspicious ones, tag the rest as `Task 7: predicate X mode (str, str, Var) — works as expected, no finding.` in a short subsection of the ledger if useful for tracking.

```bash
git add docs/superpowers/audits/2026-05-25-string-implementation/
git commit -m "$(cat <<'EOF'
docs(audit): polymorphic list builtins findings (Fnnn-Fnnn)

Audit of clausal/logic/builtins/lists.py — mode matrix per polymorphic
predicate. Covers append, length, member, reverse, nth, take, drop,
split_at, msort, last, select, permutation, flatten, concat.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Audit higher-order builtins in `higher_order.py`

**Files:**
- Read: `clausal/logic/builtins/higher_order.py` (focus on every `was_str = isinstance(lst_val, str)` site — Task 1's grep showed ~9 sites)
- Modify: `docs/superpowers/audits/2026-05-25-string-implementation/findings.md`
- Create: `probes/probe_F*.py` as needed

- [ ] **Step 1: Read each higher-order predicate**

`maplist/2,3`, `foldl/4,5`, `include/3`, `exclude/3`, `partition/4`. For each, ask:

- When the input is a str, what type are the elements passed to the goal predicate? 1-char strs? Ints (char codes)? (Must be 1-char strs per the contract.)
- For accumulators (foldl): what type does the accumulator start as if the input is str? What if the user's goal produces a non-char output?
- For predicates that build new collections (include/exclude/partition): does the output preserve str type? With what rule (`_seq_result`-like)?
- For maplist/3 where the input is `(str, list)` mixed — what happens?

- [ ] **Step 2a: Find the higher-order goal-passing pattern**

Read `tests/test_string_higher_order.py` (180 lines) end-to-end. Note the pattern for passing a goal (lambda / predicate atom / Python callable) to `maplist` / `foldl` / `include`. Note especially how lambda goals are constructed (the project supports `++expr` Python-escape and lambda goal closures per the README) and how solutions are enumerated.

- [ ] **Step 2b: Write probes**

```python
"""Probe F<N>: maplist on str passes 1-char strs (not int codes) to goal."""
# Imports per Step 2a
from clausal import Var, deref, call

def main():
    types_seen = []
    # Use the project's lambda-goal pattern from Step 2a.
    # Sketch (adapt):
    #   goal = ++lambda x: types_seen.append(type(x).__name__) or True
    #   for _ in call("maplist", goal, "abc"):
    #       pass
    for _ in call("maplist", ..., "abc"):  # <-- replace ... per Step 2a
        pass
    print(f"  types_seen: {types_seen}")
    print(f"  Expected: ['str', 'str', 'str'] (3 × 1-char str)")

if __name__ == "__main__":
    main()
```

```python
"""Probe F<N>: foldl on str — accumulator output type."""
from clausal import Var, deref, call

def main():
    Acc = Var()
    # foldl(append_char, "abc", "", Acc) where append_char does Acc' = Acc + Char
    # Per Step 2a, build the appropriate goal term.
    for _ in call("foldl", ..., "abc", "", Acc):  # <-- replace ...
        result = deref(Acc)
        print(f"  Acc = {result!r} (type {type(result).__name__})")
        break
    print(f"  Expected: 'abc' (str) if accumulator preserves str type")

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Append findings, update summary, commit**

```bash
git add docs/superpowers/audits/2026-05-25-string-implementation/
git commit -m "docs(audit): higher_order.py findings (Fnnn-Fnnn)"
```

---

## Task 9: Audit DCG (`dcg.py`)

**Files:**
- Read: `clausal/logic/builtins/dcg.py` (full file — focus on the `isinstance(_, str)` sites at lines 18, 49, 81, 85, 89–100)
- Read: `docs/dcg.md` to understand the documented contract before judging behaviour
- Modify: `docs/superpowers/audits/2026-05-25-string-implementation/findings.md`
- Create: `probes/probe_F*.py` as needed

- [ ] **Step 1: Read `phrase/2` and `phrase/3`**

Confirm:
- `phrase(g, "abc")` — what type is the threading variable?
- `phrase(g, "abc", Rest)` — what type does Rest get bound to: str or list?
- `phrase(g, S0, S)` with S0 a Var — what gets bound during the parse?
- A terminal `[a, b]` in a DCG rule: when matched against a string body, does the body advance by 2 chars (preserving str) or by 2 list elements?

- [ ] **Step 2: Read the `>>` expansion**

DCG rules are expanded by `clausal/logic/term_expansion.py` or similar. Find the expansion site (grep for `>>` operator handling) and confirm whether the expanded code preserves str-vs-list type for the threading variable.

- [ ] **Step 3a: Find the DCG-definition + phrase-call pattern**

Read `tests/test_dcg.py` end-to-end (use it to find the project's DCG-rule definition syntax and `phrase/2,3` invocation pattern). Note especially how `phrase(g, "input", Rest)` is called and how Rest is inspected.

- [ ] **Step 3b: Write probes**

```python
"""Probe F<N>: phrase/3 Rest preserves str type."""
# Imports per Step 3a
from clausal import Var, deref, call

def main():
    # Define a digits DCG inline per Step 3a's pattern.
    # The example from docs/strings_as_lists.md uses:
    #   digit >> ([D], {char_type(D, digit)})
    #   digits >> (digit)
    #   digits >> (digit, digits)
    REST = Var()
    for _ in call("phrase", ..., "12ab", REST):  # <-- replace ... with `digits`
        rest_val = deref(REST)
        print(f"  REST = {rest_val!r} (type {type(rest_val).__name__})")
        break
    print(f"  Expected: REST = 'ab' (str-preserving) OR ['a','b'] (consistent w/ list mode)")
    print(f"  Either is acceptable; inconsistency between modes is the bug.")

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Append findings, update summary, commit**

```bash
git add docs/superpowers/audits/2026-05-25-string-implementation/
git commit -m "docs(audit): DCG/phrase findings (Fnnn-Fnnn)"
```

---

## Task 10: Audit `chars.py` + `_chars_core.c`

**Files:**
- Read: `clausal/logic/builtins/chars.py`
- Read: `clausal/logic/builtins/_chars_core.c`
- Modify: `docs/superpowers/audits/2026-05-25-string-implementation/findings.md`

- [ ] **Step 1: Enumerate char-aware predicates**

`char_type/2`, `char_code/2`, `upcase_atom/2`, etc. — list every predicate in `chars.py`.

- [ ] **Step 2: Confirm the char representation contract**

For each predicate, does it accept 1-char str (per the strings-as-lists promise) or int code or both? When the contract says 1-char str, audit whether the C code (`_chars_core.c`) reads the input correctly — refcount discipline, PyUnicode_GET_LENGTH checks, etc.

- [ ] **Step 3: Probe edge cases**

Read `tests/test_chars.py` (557 lines) to find the project's `char_type` / `char_code` call pattern, then:

```python
"""Probe F<N>: char_type on multi-codepoint emoji."""
from clausal import Var, deref, call  # adapt per tests/test_chars.py

def main():
    T = Var()
    # char_type("👍🏽", T) — single grapheme but 2 code points.
    # Should fail (not a char) or accept the first code point?
    n = 0
    for _ in call("char_type", "👍🏽", T):
        n += 1
        print(f"  Solution: T = {deref(T)!r}")
    if n == 0:
        print(f"  No solutions — char_type rejects multi-codepoint input (consistent)")
    print(f"  Expected: either consistent rejection OR documented grapheme handling")

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Append findings, update summary, commit**

```bash
git add docs/superpowers/audits/2026-05-25-string-implementation/
git commit -m "docs(audit): chars.py + _chars_core.c findings (Fnnn-Fnnn)"
```

---

## Task 11: Audit type-check builtins in `type_checks.py`

**Files:**
- Read: `clausal/logic/builtins/type_checks.py`
- Modify: `docs/superpowers/audits/2026-05-25-string-implementation/findings.md`

- [ ] **Step 1: Read each type-check predicate**

`is_list/1`, `string/1`, `atom/1`, `var/1`, `nonvar/1`, `ground/1`, `compound/1`, `atomic/1`. For each, confirm the answer for these inputs:

| Input | is_list | string | atom | atomic | compound | ground |
|-------|---------|--------|------|--------|----------|--------|
| `"abc"` | ? | ? | ? | ? | ? | ? |
| `['a','b','c']` | ? | ? | ? | ? | ? | ? |
| `""` | ? | ? | ? | ? | ? | ? |
| `[]` | ? | ? | ? | ? | ? | ? |
| `SegList([VarSeg(X)])` (non-ground) | ? | ? | ? | ? | ? | ? |
| `SegString(["a", VarSeg(X)])` (non-ground) | ? | ? | ? | ? | ? | ? |
| `Var()` | ? | ? | ? | ? | ? | ? |

Build the actual-answers matrix via probes; compare against the strings-as-lists contract.

- [ ] **Step 2: Write probes**

One probe that fills in the full matrix and prints it as a table. Then a per-row entry for each cell that surprises.

- [ ] **Step 3: Append findings, update summary, commit**

```bash
git add docs/superpowers/audits/2026-05-25-string-implementation/
git commit -m "docs(audit): type-check predicates findings (Fnnn-Fnnn)"
```

---

## Task 12: Audit term inspection in `inspection.py`

**Files:**
- Read: `clausal/logic/builtins/inspection.py`
- Modify: `docs/superpowers/audits/2026-05-25-string-implementation/findings.md`

- [ ] **Step 1: Read each inspection predicate**

`functor/3`, `arg/3`, `=..`/`univ/2`, `copy_term/2`, anything else. For each, probe:

- `functor("abc", F, A)` — `F=?`, `A=?`.
- `arg(1, "abc", X)` — does it bind `X="a"`? Or error (because str isn't a compound)?
- `"abc" =.. L` — what is `L`? `["abc"]` (atom-univ) or `['.', 'a', "bc"]` (cons-cell univ)?
- `copy_term("abc", X)` — does `X` share the same str (str is immutable so OK) or get a fresh copy?

- [ ] **Step 2: Write a probe per predicate × input combination of interest**

- [ ] **Step 3: Append findings, update summary, commit**

```bash
git add docs/superpowers/audits/2026-05-25-string-implementation/
git commit -m "docs(audit): term inspection findings (Fnnn-Fnnn)"
```

---

## Task 13: Audit compiler first-arg indexing

**Files:**
- Find the indexing code first — grep for "index" or "bucket" or "dispatch_key" in `clausal/logic/compiler/` and `clausal/logic/runtime/`:
  ```bash
  grep -rn "first.arg.*index\|bucket\|dispatch_key" clausal/logic/compiler/ clausal/logic/runtime/ | head -30
  ```
- Read the relevant file(s) — likely `clausal/logic/compiler/predicate.py` or similar
- Modify: `docs/superpowers/audits/2026-05-25-string-implementation/findings.md`

- [ ] **Step 1: Locate the first-arg indexing implementation**

Use the grep above. Document the file path in your scratch notes.

- [ ] **Step 2: Read the bucket-key computation**

How does the indexer compute a bucket key for a string-headed clause vs a list-headed clause? Same bucket or different? If different, every call that bridges str↔list at the caller side will miss clauses indexed under the other type — C15 finding.

- [ ] **Step 3: Probe**

Reuse the clause-registration pattern found in Task 5 Step 3a.

```python
"""Probe F<N>: C15 — first-arg indexing routes str vs list to different buckets.

If a predicate has clauses Foo("abc") and Foo(['x','y','z']), a call
Foo([?,?,?]) — does it see both clauses or only one?
"""
from clausal import Var, deref, call  # adapt per Task 5 Step 3a

def main():
    # Register two clauses for the same predicate:
    #   Foo("abc"),
    #   Foo(['x', 'y', 'z']),
    # ... using the pattern from Task 5 Step 3a ...

    # Call Foo(L) with L unbound — should enumerate BOTH clauses
    L = Var()
    seen = []
    for _ in call("Foo", L):
        seen.append((type(deref(L)).__name__, deref(L)))
    print(f"  Foo(Var) enumerated: {seen}")
    print(f"  Expected: 2 solutions (one str, one list)")
    print(f"  Actual: if only 1 → C15 indexing routes them to separate buckets")

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Append findings, update summary, commit**

```bash
git add docs/superpowers/audits/2026-05-25-string-implementation/
git commit -m "docs(audit): first-arg indexing findings (Fnnn-Fnnn)"
```

---

## Task 14: Mine git log + in-repo planning docs for prior-known issues

**Files:**
- Read: `git log` filtered by string/seg files
- Read: `todo/`, `implementation_plans/`, `MIGRATION_STATUS.md`, `MIGRATION_TODOS.md`, `MIGRATION_CANDIDATES.md`, `DUPLICATE_TESTS.md`
- Modify: `docs/superpowers/audits/2026-05-25-string-implementation/findings.md`

- [ ] **Step 1: Mine `git log`**

```bash
git log --oneline --all -- 'clausal/terms.py' 'clausal/logic/variables/_variables.c' \
  'clausal/logic/runtime/list_unify.py' 'clausal/logic/runtime/body_star_unify.py' \
  'clausal/logic/runtime/_list_unify.c' 'clausal/logic/compiler/head_match.py' \
  'clausal/logic/builtins/dcg.py' 'clausal/logic/builtins/lists.py' \
  'clausal/logic/builtins/higher_order.py' 'clausal/logic/builtins/chars.py' \
  'clausal/logic/builtins/_chars_core.c' 'clausal/logic/builtins/type_checks.py' \
  'clausal/logic/builtins/inspection.py'
```

For each `fix(...)` commit, run `git show <sha>` and decide:
- Is the fix complete? (i.e. could the same bug recur in a related case?)
- Is the bug class already in C1–C17?
- Add a "Prior-known" cross-reference to any existing F<N> finding it relates to.
- If the fix points at an unaudited fault line, log a new F<N> finding with `Prior-known: commit <sha>`.

- [ ] **Step 2: Read the in-repo planning docs**

```bash
ls todo/ implementation_plans/ 2>/dev/null
cat MIGRATION_STATUS.md MIGRATION_TODOS.md MIGRATION_CANDIDATES.md DUPLICATE_TESTS.md 2>/dev/null | head -200
```

For each unresolved item that touches strings, log a finding (or cross-reference an existing one).

- [ ] **Step 3: Append findings, update summary, commit**

```bash
git add docs/superpowers/audits/2026-05-25-string-implementation/
git commit -m "$(cat <<'EOF'
docs(audit): prior-known issues from git log + planning docs (Fnnn-Fnnn)

Cross-references past fix commits and unresolved planning-doc items
against the audit ledger. Adds new findings for any unaudited fault
lines surfaced by the search.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 15: Inventory existing test coverage

**Files:**
- Read: `tests/test_string_*.py`, `tests/test_seg*.py`, `tests/test_chars.py`, `tests/test_dcg.py`, `tests/test_string_head_patterns.py` (and any other test file whose name suggests string coverage)
- Create: `docs/superpowers/audits/2026-05-25-string-implementation/test_coverage.md`

- [ ] **Step 1: List candidate test files**

```bash
find tests/ -name 'test_*string*' -o -name 'test_seg*' -o -name 'test_chars*' -o -name 'test_dcg*'
```

- [ ] **Step 2: For each file, list the predicates / behaviours it exercises**

Read each test file once, jot down (in a scratch list) which surfaces / classes it covers. Build a table.

- [ ] **Step 3: Write `test_coverage.md`**

Table format:

```markdown
# Existing string test coverage

| Test file | Surfaces covered | Classes likely tested |
|-----------|------------------|------------------------|
| tests/test_string_list_unification.py | C-level str↔list | C1 (partial), C7 (partial) |
| tests/test_seglist_core.py | SegList class | C1, C2 (partial) |
| ... | ... | ... |
```

Then a "gaps" section noting what surfaces are *not* covered. This document drives Phase 1's per-class test file design.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/audits/2026-05-25-string-implementation/test_coverage.md
git commit -m "docs(audit): inventory existing string test coverage"
```

---

## Task 16: Phase 0 wrap-up — cross-reference, sort, summarise

**Files:**
- Modify: `docs/superpowers/audits/2026-05-25-string-implementation/findings.md`
- Modify: `docs/superpowers/audits/2026-05-25-string-implementation/README.md`

- [ ] **Step 1: De-dupe**

Read the ledger end-to-end. For any two findings that look like the same bug (e.g. C1 / `output mode builds list not str` in Task 3 vs C1 / `_build_star_list falls back to list` in Task 4), keep both as separate IDs but link them with `[[Fnnn]]` cross-references in the Notes section. Do NOT collapse — the IDs are stable.

- [ ] **Step 2: Re-sort within each class section**

Within each `### Class C<N>` section, sort findings: `bug` first, then `design-gap`, then `perf`, then `smell`, then `doc-only`. Within each severity bucket, keep discovery order.

- [ ] **Step 3: Update the summary table**

Recount each `(class, severity)` cell and fix the table at the top of `findings.md`.

- [ ] **Step 4: Add a "Phase 0 conclusion" section**

Append to `findings.md`:

```markdown
## Phase 0 conclusion

- **Total findings:** N
- **By severity:** N bug, N design-gap, N perf, N smell, N doc-only
- **By class:** (table above)
- **Highest-blast-radius finding:** F<NNN> (<title>) — see Notes for fix scope
- **Recommended Phase 2 ordering** (fix-blast-radius ascending):
  1. Class C<X> (N findings) — self-contained, ~M file changes
  2. Class C<Y> (N findings) — ...
  3. ...

The Phase 1 plan should produce one test file per class with findings.
The Phase 2 plan should produce one commit per class in the order above.
```

- [ ] **Step 5: Update the README**

Mark the ledger status as "Phase 0 complete; awaiting Phase 1 plan".

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/audits/2026-05-25-string-implementation/
git commit -m "$(cat <<'EOF'
docs(audit): Phase 0 complete — ledger cross-referenced and summarised

N findings total across classes C1-C17 (+ out-of-taxonomy). Findings
are stable; Phase 1 (tests) and Phase 2 (fixes) plans to be written
from this ledger.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 7: Hand off — produce Phase 1 plan stub**

Write `docs/superpowers/plans/2026-05-25-string-audit-phase-1.md` as a short stub:

```markdown
# String Implementation Audit — Phase 1 Implementation Plan

**Status:** STUB — to be expanded from the Phase 0 ledger
(`docs/superpowers/audits/2026-05-25-string-implementation/findings.md`).

**Goal:** Convert each Phase 0 `bug` and `design-gap` finding into an
adversarial pytest test marked `xfail(strict=True, reason="ledger F<N>")`.

**Architecture:** One test file per class with findings. Tests grouped
by finding ID inside each file. xfail strict so a fix that accidentally
passes a test will be caught.

**Tasks:** To be written by invoking superpowers:writing-plans with this
stub + the completed ledger as input.
```

Commit:

```bash
git add docs/superpowers/plans/2026-05-25-string-audit-phase-1.md
git commit -m "docs(audit): stub Phase 1 plan, to be filled from ledger"
```

---

## Phase 0 exit criteria (must all be true before writing Phase 1 plan)

- [ ] Every in-scope file from the spec has been read in a numbered task above.
- [ ] Every class C1–C17 has at least one ledger entry — either a finding or an explicit "no findings, here's why" note.
- [ ] Every ledger entry has a stable F<N> ID and (where applicable) a re-runnable probe in `probes/`.
- [ ] The summary table at the top of `findings.md` is accurate.
- [ ] The Phase 0 conclusion section is present.
- [ ] `test_coverage.md` exists and identifies gaps.
- [ ] The Phase 1 plan stub exists.

If any of these are not satisfied, do not proceed to Phase 1 — go back and finish Phase 0.
