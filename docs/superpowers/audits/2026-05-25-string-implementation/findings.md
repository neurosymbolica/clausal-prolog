# String Implementation Audit — Findings Ledger

**Spec:** [../../specs/2026-05-25-string-implementation-audit-design.md](../../specs/2026-05-25-string-implementation-audit-design.md)
**Phase 0 plan:** [../../plans/2026-05-25-string-audit-phase-0.md](../../plans/2026-05-25-string-audit-phase-0.md)
**Status:** Phase 0 in progress

## Summary by class

| Class | Title | Bug | Design-gap | Perf | Smell | Doc-only |
|-------|-------|-----|-----------:|-----:|------:|---------:|
| C1 | Type preservation | 0 | 0 | 0 | 0 | 0 |
| C2 | Non-det collapsed to first | 0 | 0 | 0 | 0 | 0 |
| C3 | SegString blind spots vs SegList | 0 | 1 | 0 | 0 | 0 |
| C4 | Head-pattern literal mismatch | 0 | 0 | 0 | 0 | 0 |
| C5 | Hash/eq asymmetries | 0 | 0 | 0 | 0 | 0 |
| C6 | Hashable vs unhashable bridges | 0 | 0 | 0 | 0 | 0 |
| C7 | Unicode / multi-codepoint | 0 | 0 | 0 | 0 | 4 |
| C8 | Partial-term short-circuits | 0 | 0 | 0 | 0 | 0 |
| C9 | Polymorphic builtin mode matrix | 0 | 0 | 0 | 0 | 0 |
| C10 | DCG / phrase interaction | 0 | 0 | 0 | 0 | 0 |
| C11 | Trail/backtracking around partials | 0 | 0 | 0 | 0 | 0 |
| C12 | Char representation drift | 0 | 0 | 0 | 0 | 0 |
| C13 | Type-check predicates | 0 | 0 | 0 | 0 | 0 |
| C14 | Term inspection drift | 0 | 0 | 0 | 0 | 0 |
| C15 | First-arg indexing on strings | 0 | 0 | 0 | 0 | 0 |
| C16 | Free-threaded build safety | 1 | 0 | 0 | 0 | 0 |
| C17 | Performance, memory, leaks | 0 | 0 | 1 | 0 | 0 |
| —   | Out-of-taxonomy | 0 | 0 | 0 | 0 | 0 |

(Counts updated at the end of each task.)

## Findings

<!-- Findings appended below, grouped by class then severity. -->

### Class C1 — Type preservation

*Task 1 confirmed (no finding):*
- **F010** — The two str↔list branches at `_variables.c:1140` and
  `_variables.c:1167` recurse with swapped argument order
  (`do_unify(ch, elem, ...)` vs `do_unify(elem, ch, ...)`), but `do_unify`
  treats Var-Term and Term-Var symmetrically, so both branches bind the
  Var to a 1-codepoint `str` of the same type and value. Confirmed for
  ASCII and astral codepoints. See `probes/probe_F010.py`.
- **F006** — When a list element is an unbound Var, the C path binds it to
  a 1-codepoint Python `str` (allocated via `PyUnicode_Substring`), never
  to an int code. This sets the de-facto contract for the char element
  type: 1-char `str`. Confirmed for both branches. See
  `probes/probe_F006.py`.
- **F005** — Task 1 confirmed: nested-list elements in a string-vs-list unify are rejected (the per-element check requires `PyUnicode_Check(elem) && PyUnicode_GET_LENGTH(elem) == 1`). Probe: `probes/probe_F005.py`.

### Class C2 — Non-det collapsed to first
*(none yet)*

### Class C3 — SegString blind spots vs SegList

### F012 — Var bound to SegString in list position is not recognised as a char

- **Class:** C3 (SegString blind spots vs SegList)
- **Severity:** design-gap
- **Location:** `clausal/logic/variables/_variables.c:1143-1149` and
  `clausal/logic/variables/_variables.c:1170-1176`
- **Discovered by:** Task 1 of Phase 0
- **Probe:** `probes/probe_F012.py`

**Symptom:** Inside the str↔list loop, the C path type-checks each list
element with `PyUnicode_Check(elem) && PyUnicode_GET_LENGTH(elem) == 1`.
A `SegString` (Python class, *not* a `str` subclass) representing a
single character is rejected even when it semantically equals the
codepoint at that position. A Var bound to such a `SegString` therefore
makes `unify("a", [v])` return `False` even when `v` was previously
bound to `SegString("a")`.

**Reproducer:**
```python
from clausal.logic.variables import Trail, Var, unify
from clausal.terms import SegString

v = Var()
t = Trail()
unify(v, SegString("a"), t)
assert unify("a", [v], t) is True  # FAILS — returns False
```

**Expected:** True (the bound value is semantically the char `'a'`).
**Actual:** False (the C path's `PyUnicode_Check` excludes `SegString`).

**Notes:** Symmetric to the SegList walking gap noted in spec C3 but at
the C boundary rather than the Python list-unify path. The hot loop must
keep its fast path; one option is to defer to the `__unify__` protocol
when `elem` is not a Var and not a 1-codepoint `PyUnicode`. Related to
[[F008]] (ground-SegString-vs-list does reach the `__unify__` hook when
the SegString is the top-level arg, but Vars *inside* a list never
reach that fallback).

*Task 1 confirmed (no finding):*
- **F008** — Top-level `unify(SegString("abc"), ["a","b","c"], t)` and the
  reverse direction both succeed. The C path's str↔list block keys off
  `PyUnicode_Check`, which is `False` for `SegString`, so control falls
  through to the `__unify__` protocol at `_variables.c:1188` /
  `_variables.c:1207`. `SegString.__mro__` is `(SegString, object)` —
  it is not a `str` subclass. See `probes/probe_F008.py`.

### Class C4 — Head-pattern literal mismatch
*(none yet)*

### Class C5 — Hash/eq asymmetries
*(none yet)*

### Class C6 — Hashable vs unhashable bridges
*(none yet)*

### Class C7 — Unicode / multi-codepoint

### F002 — Multi-codepoint emoji split at codepoint, not grapheme, boundary

- **Class:** C7 (Unicode / multi-codepoint)
- **Severity:** doc-only
- **Location:** `clausal/logic/variables/_variables.c:1127-1179`
- **Discovered by:** Task 1 of Phase 0
- **Probe:** `probes/probe_F002.py`

**Symptom:** The str↔list path uses `PyUnicode_GET_LENGTH` (code-point
count) and `PyUnicode_READ_CHAR` (single code point) for both the length
check and per-element comparison. A user-perceived grapheme that spans
multiple codepoints (e.g. `"👍🏽"` = U+1F44D + U+1F3FD, 2 codepoints) is
treated as 2 list elements, and a list containing the whole grapheme as
one entry fails to unify with the string.

**Reproducer:**
```python
from clausal.logic.variables import Trail, unify
s = "\U0001f44d\U0001f3fd"  # thumbs-up + skin-tone modifier
assert unify(s, ["\U0001f44d", "\U0001f3fd"], Trail()) is True
assert unify(s, [s], Trail()) is False  # 1 list elem, 2 codepoint str
```

**Expected:** Defensible at the code-point level (Python's own indexing).
**Actual:** Same as expected.

**Notes:** This is the documented contract per spec C7; the finding is to
make it explicit in user-visible documentation. No semantic fix planned.

### F003 — NFC and NFD forms of the same grapheme do not unify

- **Class:** C7 (Unicode / multi-codepoint)
- **Severity:** doc-only
- **Location:** `clausal/logic/variables/_variables.c:1127-1179` and the
  fall-through to `PyObject_RichCompareBool` at `_variables.c:1229`
- **Discovered by:** Task 1 of Phase 0
- **Probe:** `probes/probe_F003.py`

**Symptom:** `"é"` (precomposed, U+00E9, length 1) and `"é"` (decomposed
e + combining acute, U+0065 U+0301, length 2) are visually identical but
have different codepoint sequences. The C str↔list path treats them as
distinct: `unify(nfc, [nfc])` is True, `unify(nfd, [nfc])` is False,
`unify(nfd, list(nfd))` is True. Python `==` agrees, so this is
internally consistent — but surprising to users who expect
"string equals string" to be NFC-normalised.

**Reproducer:**
```python
from clausal.logic.variables import Trail, unify
nfc = "é"          # one codepoint
nfd = "é"         # two codepoints
assert unify(nfc, nfd, Trail()) is False
assert unify(nfd, [nfc], Trail()) is False
assert unify(nfd, ["e", "́"], Trail()) is True
```

**Expected:** Code-point-level identity (the implementation rule).
**Actual:** Same as expected.

**Notes:** Document the no-normalisation contract. Consider whether DCG /
`phrase` should accept an opt-in normalisation hook (out of scope).

### F004 — List element must be exactly one codepoint (multi-char rejected)

- **Class:** C7 (Unicode / multi-codepoint)
- **Severity:** doc-only
- **Location:** `clausal/logic/variables/_variables.c:1129, 1144, 1171`
- **Discovered by:** Task 1 of Phase 0
- **Probe:** `probes/probe_F004.py`

**Symptom:** `PyUnicode_GET_LENGTH(elem) == 1` rejects any list element
that is a multi-char string, even when the concatenation of all
elements equals the str. `unify("abc", ["ab", "c"])` is False;
`unify("abc", ["abc"])` is False. This is consistent with treating a
list as a strict sequence of single codepoints.

**Reproducer:**
```python
from clausal.logic.variables import Trail, unify
assert unify("abc", ["ab", "c"], Trail()) is False
assert unify("abc", ["a", "bc"], Trail()) is False
assert unify("abc", ["abc"],     Trail()) is False
```

**Expected:** False (single-codepoint-per-element rule).
**Actual:** False.

**Notes:** Spec C7 calls this out explicitly ("currently rejected;
document the rule"). The finding is to add a note to the str↔list
section of `_variables.c` and any user-facing docs that describe the
contract.

Reproducer cases all return False at the size-mismatch check (`:1129`) before reaching the per-element `PyUnicode_GET_LENGTH(elem) == 1` gate (`:1144`/`:1171`). The per-element gate is effectively unreachable in isolation because any list whose elements sum to `n` codepoints with at least one multi-char element must have fewer than `n` slots. The doc-only finding stands: the contract documented by the per-element gate (no multi-char elements) is implicitly enforced by the size check in every reachable case.

### F007 — Lone surrogate halves are treated as ordinary codepoints

- **Class:** C7 (Unicode / multi-codepoint)
- **Severity:** doc-only
- **Location:** `clausal/logic/variables/_variables.c:1127-1179`
- **Discovered by:** Task 1 of Phase 0
- **Probe:** `probes/probe_F007.py`

**Symptom:** Python permits constructing `str` containing lone surrogate
halves (U+D800–U+DFFF). The C path treats each lone surrogate as one
codepoint and unifies it with a list element that is the same
1-codepoint `str`. It does *not* combine `'\ud83d'` + `'\ude00'` into the
astral codepoint U+1F600 (`'😀'`); a list of two surrogate halves is
unequal to a single-codepoint astral str.

**Reproducer:**
```python
from clausal.logic.variables import Trail, unify
assert unify("\ud83d", ["\ud83d"], Trail()) is True
smile = "\U0001f600"        # 1 codepoint
assert unify(smile, [smile], Trail()) is True
assert unify(smile, ["\ud83d", "\ude00"], Trail()) is False
```

**Expected:** Codepoint-level identity, no UTF-16 reassembly.
**Actual:** Same as expected.

**Notes:** Document the no-UTF-16 contract. Matches Python's `len()` and
indexing semantics on str.

*Task 1 confirmed (no finding):*
- **F001** — The `n == 0` fast path at `_variables.c:1130` /
  `_variables.c:1158` correctly succeeds for `unify("", [], t)` and
  `unify([], "", t)`. See `probes/probe_F001.py`.

### Class C8 — Partial-term short-circuits
*(none yet)*

### Class C9 — Polymorphic builtin mode matrix
*(none yet)*

### Class C10 — DCG / phrase interaction
*(none yet)*

### Class C11 — Trail/backtracking around partials
*(none yet)*

### Class C12 — Char representation drift

*Task 1 confirmed (no finding):*
- **F013** — A Var bound to a non-Var, non-single-char-PyUnicode dereffed element (e.g. int, list, tuple) does not unify when placed inside a list against the equivalent `str`. The C path requires the dereffed element to be either an unbound Var (allocate substring & bind) or a PyUnicode of exactly 1 code point. This is consistent with [[F006]]: the C path binds chars as 1-char `str`, never as int codes. See `probes/probe_F013.py`. Spec C12 notes this is the intended contract; the broader char-aware-builtin audit is left to later tasks.

### Class C13 — Type-check predicates
*(none yet)*

### Class C14 — Term inspection drift
*(none yet)*

### Class C15 — First-arg indexing on strings
*(none yet)*

### Class C16 — Free-threaded build safety

### F011 — str↔list block holds no critical section on the list arg

- **Class:** C16 (Free-threaded build safety)
- **Severity:** bug
- **Location:** `clausal/logic/variables/_variables.c:1127-1179`
- **Discovered by:** Task 1 of Phase 0
- **Probe:** `probes/probe_F011.py`

**Symptom:** The two str↔list branches iterate the list with
`PyList_GET_ITEM` and `PyList_GET_SIZE` (macros that touch the underlying
array without locking) and call `var_deref` on each element. There is no
`FT_CS_BEGIN` on the list argument. Other places in `do_unify` that touch
mutable per-object state (Var bindings) acquire `FT_CS_BEGIN(&cs, t)` —
the str↔list path was added later (lines 1118–1179, between the
list-vs-list block and the `__unify__` hook) without that discipline.

Under `Py_GIL_DISABLED` (3.13t+) another thread mutating the list
concurrently (e.g. `lst[i] = x` or `lst.append(...)`) while the C loop
is running is racy at the C level: `PyList_GET_ITEM` reads the slot
without a load barrier, and the underlying `ob_item` array can be
reallocated by a concurrent `list.resize`. The probe documents the
concern; on a GIL build the race is masked because the mutating
operation cannot run concurrently with the C call.

**Reproducer:** see `probes/probe_F011.py` — multi-threaded read/mutate
stress; no failure observed on GIL build, but this does not prove
soundness on `Py_GIL_DISABLED`.

**Expected:** No undefined behaviour under FT.
**Actual:** Unverified on FT build; static review shows no critical
section is taken on the list.

**Notes:** Standard immutable-PyUnicode reads are safe. The hole is on
the `list` side. CPython's recommended FT-safe accessor is
`PyList_GetItemRef` (returns a strong ref, increments under the list's
lock) — applying it in the loop would resolve the static concern at the
cost of one INCREF/DECREF per element. Alternative: wrap the loop body
in `FT_CS_BEGIN(&cs, t2_or_t1)`. The neighbouring plain list-vs-list
block (`_variables.c:1103-1116`) has the same gap and should be
re-examined as part of any fix. Cross-ref [[F012]] (the same loop also
needs to widen its element type check).

Re-graded from smell to bug after Task 1 spec review: the spec's severity vocabulary defines bug to include "refcount/use-after-free hazard", which is exactly what an unprotected PyList_GET_ITEM on FT builds is. Caveats kept: (a) unverified — the test harness runs with the GIL enabled, so the race cannot be reproduced here; (b) the same hazard pattern pre-dates the str↔list addition and exists in the neighbouring plain list-vs-list block at `_variables.c:1103-1116` — fixing F011 should address both.

### Class C17 — Performance, memory, leaks

### F009 — Per-element PyUnicode_Substring allocation in unbound-Var branch

- **Class:** C17 (Performance, memory, leaks)
- **Severity:** perf
- **Location:** `clausal/logic/variables/_variables.c:1138` and
  `clausal/logic/variables/_variables.c:1165`
- **Discovered by:** Task 1 of Phase 0
- **Probe:** `probes/probe_F009.py`

**Symptom:** When a list element is an unbound Var, the C path calls
`PyUnicode_Substring(t, i, i + 1)` to materialise a 1-codepoint `str`
for binding. For an N-element list of fresh Vars unified against a
length-N str, this is O(N) allocations. CPython caches 1-codepoint
Latin-1 strings (U+0000–U+00FF) so the cost is amortised for ASCII /
Latin-1 work — the probe measures ~0.03 µs/elem at N=10 000 for
`"a" * N`. For non-Latin-1 (BMP-and-above) codepoints, each allocation
is a real `PyUnicode` heap object. The spec calls this out under C17 as
worth flagging.

**Reproducer:** `probes/probe_F009.py` — `unify("a" * 10_000, [Var()] *
10_000, Trail())` completes in well under a millisecond on Latin-1, but
the same workload with astral codepoints would allocate ~10 000 fresh
PyUnicode objects.

**Expected:** Fast path that avoids allocation for the common Latin-1
case (already true via CPython's cache).
**Actual:** Always uses `PyUnicode_Substring`; relies on CPython's
1-codepoint Latin-1 cache for the fast case. Non-Latin-1 codepoints
allocate every time.

**Notes:** No correctness issue; refcount discipline is balanced
(`Py_DECREF(ch)` follows every return path in the loop, including the
error return at `_variables.c:1142` and `_variables.c:1169`). Possible
optimisation: skip the `Substring` when the deref'd elem already
contains the matching codepoint (already the fast path for the ground
case). For the unbound-Var case the allocation is fundamental — the var
must be bound to *some* `PyObject`. Logged for visibility; not worth
fixing in isolation.

*Task 1 confirmed (no finding):*
- **F014** — Task 1 confirmed: refcount discipline on `PyUnicode_Substring` allocations is balanced. Every alloc at `_variables.c:1138`/`:1165` is paired with `Py_DECREF` at `:1141`/`:1168` on the success path; error returns (`r == -1`) propagate the unbinding via standard CPython exception flow. No probe (static review only).

### Out-of-taxonomy
*(none yet)*
