# String Implementation Audit — Findings Ledger

**Spec:** [../../specs/2026-05-25-string-implementation-audit-design.md](../../specs/2026-05-25-string-implementation-audit-design.md)
**Phase 0 plan:** [../../plans/2026-05-25-string-audit-phase-0.md](../../plans/2026-05-25-string-audit-phase-0.md)
**Status:** Phase 0 complete; awaiting Phase 1 plan execution

## Summary by class

| Class | Title | Bug | Design-gap | Perf | Smell | Doc-only |
|-------|-------|-----|-----------:|-----:|------:|---------:|
| C1 | Type preservation | 0 | 5 | 0 | 0 | 0 |
| C2 | Non-det collapsed to first | 2 | 0 | 0 | 0 | 0 |
| C3 | SegString blind spots vs SegList | 5 | 3 | 0 | 0 | 0 |
| C4 | Head-pattern literal mismatch | 1 | 0 | 0 | 0 | 0 |
| C5 | Hash/eq asymmetries | 1 | 2 | 0 | 0 | 0 |
| C6 | Hashable vs unhashable bridges | 0 | 0 | 0 | 0 | 0 |
| C7 | Unicode / multi-codepoint | 0 | 0 | 0 | 0 | 7 |
| C8 | Partial-term short-circuits | 4 | 1 | 0 | 1 | 0 |
| C9 | Polymorphic builtin mode matrix | 5 | 6 | 0 | 1 | 0 |
| C10 | DCG / phrase interaction | 2 | 2 | 0 | 0 | 0 |
| C11 | Trail/backtracking around partials | 0 | 0 | 0 | 0 | 0 |
| C12 | Char representation drift | 1 | 0 | 0 | 0 | 0 |
| C13 | Type-check predicates | 1 | 3 | 0 | 1 | 0 |
| C14 | Term inspection drift | 4 | 3 | 0 | 0 | 0 |
| C15 | First-arg indexing on strings | 1 | 0 | 0 | 0 | 0 |
| C16 | Free-threaded build safety | 1 | 0 | 0 | 0 | 0 |
| C17 | Performance, memory, leaks | 0 | 0 | 2 | 1 | 0 |
| —   | Out-of-taxonomy | 0 | 0 | 0 | 0 | 0 |

(Counts verified at Phase 0 completion: 66 findings total — 28 bug, 25 design-gap, 2 perf, 4 smell, 7 doc-only.)

## Findings

<!-- Findings appended below, grouped by class then severity. -->

### Class C1 — Type preservation

### F018 — SegList.__walk__ expands VarSeg-bound str into char list

- **Class:** C1 (Type preservation)
- **Severity:** design-gap
- **Status:** fixed in Phase 2 Task 13 (952aa88)
- **Location:** `clausal/terms.py:227-234`
- **Discovered by:** Task 2 of Phase 0
- **Probe:** `probes/probe_F018.py`

**Symptom:** When a `VarSeg`'s var is bound to a `str`, `__walk__`
expands it to characters via `list(v)` and concatenates them into the
adjacent `ConcreteSeg`. The walked SegList ends up holding individual
char elements; the `str` identity of the binding is lost. Combined with
the SegList-treats-itself-as-a-list contract this is internally
consistent — but a caller that asked for `walk(x)` and saw `"abc"`
will see `['a','b','c']` (or worse, inlined into surrounding numbers
like `[1,'a','b','c',2]`) after the value is re-walked through a
SegList.

**Reproducer:**
```python
from clausal.logic.variables import Var, unify, Trail
from clausal.terms import SegList, VarSeg, ConcreteSeg

X = Var(); t = Trail()
unify(X, "abc", t)
sl = SegList([ConcreteSeg([1]), VarSeg(X), ConcreteSeg([2])])
assert sl.__walk__() == [1, "a", "b", "c", 2]
```

**Expected:** Under "input-type wins" the result preserves the str.
Under "SegList is a list-shaped container" the inline expansion is
correct.
**Actual:** Char expansion (list-shape wins).

**Notes:** The companion `SegString.__walk__` at terms.py:493-499 does
the inverse: it joins a list-bound VarSeg into a str. So the rule
inside the Seg* layer is "container-shape wins" — but that contradicts
the broader strings-as-lists contract where the user shouldn't have to
think about which container they passed. Picking a coherent rule across
both classes is the C1 work. Related to [[F019]] (the same shape
mismatch surfaces in __eq__).

**Prior-known:** commit f635551 — "Phase 7: SegString and string-preserving pattern matching" rewrote `SegList.__walk__` to handle VarSegs bound to strings (eliminating the SegList/compiler path asymmetry per the plan in `implementation_plans/data_structures/STRING_LIST_UNIFICATION.md` Phase 7 acceptance criterion); the rewrite normalized inward (str → char-list) for the SegList container and outward (list → str) for SegString, which is exactly the "container-shape wins" rule this finding flags.

Fix (Phase 2 Task 13): under the user-confirmed Liskov "strings-as-lists" model, `SegList.__walk__` now applies the new `maybe_promote_to_str` helper (in `clausal/logic/runtime/_seg_helpers.py`) to its final fully-ground walked list. VarSeg's splat semantics still expand a bound `str` into chars (str ⊂ list-of-chars), but the post-walk promotion re-emits a `str` whenever every element is a 1-char str. Default output remains `list`; the upgrade to `str` fires only when provable from the result elements.

### F020 — SegList.__add__ / __radd__ rejects str

- **Class:** C1 (Type preservation)
- **Severity:** design-gap
- **Status:** fixed in Phase 2 Task 13 (952aa88)
- **Location:** `clausal/terms.py:353-364`
- **Discovered by:** Task 2 of Phase 0
- **Probe:** `probes/probe_F020.py`

**Symptom:** `SegList.__add__` handles `list` and `SegList` and returns
`NotImplemented` for `str`. `SegList.__radd__` only handles `list`. So
`SegList(['a','b']) + "cd"` raises TypeError and `"cd" +
SegList(['a','b'])` raises TypeError (because `str.__add__` also
NotImplements). Under the strings-as-lists contract a `str` should
work as a list-of-1-char-strs in a SegList tail just as a `list`
does.

**Reproducer:**
```python
from clausal.terms import SegList, ConcreteSeg

sl = SegList([ConcreteSeg(["a", "b"])])
assert sl + ["c", "d"] == ["a", "b", "c", "d"]      # works
try:
    sl + "cd"                                       # TypeError
except TypeError:
    pass
try:
    "cd" + sl                                       # TypeError
except TypeError:
    pass
```

**Expected:** Either both `list` and `str` accepted (preferred for the
strings-as-lists contract), or both rejected.
**Actual:** Only `list` accepted.

**Notes:** Native Python `list + str` also raises TypeError, so the
current behaviour is at least consistent with the host language. The
audit logs this as a contract gap rather than a bug. Related to
[[F019]] (parallel asymmetry in `__eq__`).

Fix (Phase 2 Task 13): `SegList.__add__` now accepts a `str` operand and treats it as a list-of-1-char-strs tail (`list(other)`); `SegList.__radd__` does the same on the left. The Liskov "strings-as-lists" rule means a `str` and a `list-of-chars` are interchangeable as a SegList neighbour.

### F033 — `_head_list_unify_output` always builds a list, never a str

- **Class:** C1 (Type preservation)
- **Severity:** design-gap
- **Status:** fixed in Phase 2 Task 13 (952aa88)
- **Location:** `clausal/logic/runtime/list_unify.py:165` and
  `clausal/logic/runtime/_list_unify.c:251`
- **Discovered by:** Task 3 of Phase 0
- **Probe:** `probes/probe_F033.py`

**Symptom:** The output-mode helper unconditionally allocates
``result = [...]`` (a Python list) for the deferred head reconstruction.
There is no record of the input target's original *logical* type — the
target was an unbound `Var` when the input phase deferred — so even if
``H`` and ``T`` were bound from a str-typed context (e.g. ``T = "ello"``
), the constructed target is bound to the list ``['h', 'ello']``.

Concrete effect: a clause ``foo([H, *T])`` whose body proves
``T = "ello"`` and ``H = "h"`` produces a target ``['h', 'ello']``
rather than ``"hello"``. The C and Python paths agree (both write
list).

**Reproducer:**
```python
from clausal.logic.variables import Var, unify, Trail, deref
from clausal.logic.runtime.list_unify import _head_list_unify_output

target = Var()
H, T = Var(), Var()
unify(H, "h", Trail())
unify(T, "ello", Trail())
_head_list_unify_output(target, [H], T, [], Trail())
assert deref(target) == ['h', 'ello']         # list, not 'hello'
assert type(deref(target)) is list
```

**Expected:** Under the strings-as-lists "input type wins" contract,
the str-typed inputs should reconstruct as ``"hello"`` (a str).
**Actual:** Always a list.

**Notes:** The fix is structural: the deferred-output guard would
have to capture the original target type at the compile-time site
(or pass it through the input-mode return value). Logged as
design-gap because the information genuinely isn't present at the
call site; F003-class type-preservation gap on the head-pattern
boundary. Related to [[F018]] (parallel type loss in
`SegList.__walk__`) and [[F034]] (SegString blind spot in output
star_val, the C3 sibling of this C1 finding).

**Prior-known:** commit aa2155d — "Compiler: head patterns accept strings in clause matching" widened `_head_list_unify_input` to accept `(list, str)` and noted that "string slicing naturally preserves type: [H, *T] on 'hello' gives H='h', T='ello'". That commit only covered the input-mode path; the symmetric output-mode reconstruction at `_head_list_unify_output` was not touched and still always allocates a list.

Fix (Phase 2 Task 13): `_head_list_unify_output` (both Python and C accelerator) now applies the `maybe_promote_to_str` helper before the final `unify(target, result, trail)` call. A str-bound star is treated as a list of 1-char strs (splat its chars); the post-construction promotion re-emits a `str` when every element of the result is a 1-char str. Default remains `list`; the upgrade is purely a property of the result elements — no type-source plumbing required.

### F042 — `_body_multi_star_unify` unbound-target branch always builds SegList

- **Class:** C1 (Type preservation)
- **Severity:** design-gap
- **Status:** fixed in Phase 2 Task 13 (952aa88)
- **Location:** `clausal/logic/runtime/body_star_unify.py:249-260`
- **Discovered by:** Task 4 of Phase 0
- **Probe:** `probes/probe_F042.py`

**Symptom:** When the dereffed target is an unbound `Var`, the helper
unconditionally constructs a `SegList` of `[VarSeg | ConcreteSeg]`
segments from the pattern and binds the target to it. There is no
record of whether the surrounding logical context expects a
str/SegString result — even when every fixed segment is a 1-char str
var and every star is bound (or would later bind) to a str. A goal
``X is [H, *S, T]`` where every var is fresh therefore binds X to a
SegList regardless of how X is consumed downstream.

This is the multi-star body-position parallel of [[F033]] (head-output
mode always builds a list). The information genuinely isn't present at
this site, so the fix requires upstream plumbing (compile-time
type-source recording, or threading the type through the input phase).

**Reproducer:**
```python
from clausal.logic.variables import Var, Trail, deref
from clausal.logic.runtime.body_star_unify import _body_multi_star_unify
from clausal.terms import SegList, SegString

target = Var()
H, S, R = Var(), Var(), Var()
segments = [("fixed", [H]), ("star", S), ("fixed", [R])]
# inspect during yield — trail.undo at :259 unbinds after each yield
for _ in _body_multi_star_unify(target, segments, Trail()):
    assert isinstance(deref(target), SegList)
    assert not isinstance(deref(target), SegString)
    break
```

**Expected:** Under "input type wins" a SegString when the surrounding
logical context is string-typed; SegList otherwise.
**Actual:** Always SegList.

**Notes:** Same root-cause class as [[F033]]; if Phase 2 fixes F033 by
threading the original target type into the output-mode call site, the
same plumbing should reach this helper. The single-star body path `[*S]` does not reach this branch — it delegates to `_body_star_unify` → `_head_list_unify_output`, which inherits [[F033]]. F042 is specific to multi-star body patterns (≥2 stars) whose targets are unbound Vars. Companion to [[F043]] (the build helpers also
lose type when star is bound to a list-of-1-char-strs).

**Prior-known:** commit 82ecc96 — "Fix SegString bugs, update strings_as_lists docs for Phase 7" reworked `_build_star_list` to "handle non-ground SegString with mixed before/after by converting to SegList instead of falling through to VarSeg(SegString)". That commit closed a specific crash but did not introduce a target-type record, so the unbound-Var branch in `_body_multi_star_unify` (a sibling helper) still builds SegList unconditionally.

Fix (Phase 2 Task 13): the unbound-Var branch now delegates to `_build_multi_star_list`, which under the new Liskov rule first scans the segments — if every fixed element is a 1-char str and every star derefs to a str / ground-SegString / non-ground-SegString / list-of-1-char-strs, the build returns a plain `str` (ground) or a `SegString` (non-ground holes). Mixed or non-string-compatible content takes the original SegList path. No type-source plumbing required; the choice is purely a property of the derefferenced star values.

### F043 — `_build_star_list` / `_build_multi_star_list` lose str type for list-of-chars and non-ground SegString stars

- **Class:** C1 (Type preservation)
- **Severity:** design-gap
- **Status:** fixed in Phase 2 Task 13 (952aa88)
- **Location:** `clausal/logic/runtime/body_star_unify.py:70-71, 119-126`
  (`_build_star_list`) and `clausal/logic/runtime/body_star_unify.py:150-156,
  167-184` (`_build_multi_star_list`)
- **Discovered by:** Task 4 of Phase 0
- **Probe:** `probes/probe_F043.py`

**Symptom:** Both helpers preserve `str` only when the dereffed star is
itself a `str` (or a ground SegString that walks to a str). When the
star is bound to a `list` of 1-char strs — semantically equivalent to a
str under the strings-as-lists contract — the helpers fall into the
`list` branch (line 71 for `_build_star_list`, line 150-156 for
`_build_multi_star_list`) and never re-promote the result to str.

For `_build_multi_star_list`, the non-ground SegString fork at
`:167-184` explicitly sets `all_str = False` and emits
`ConcreteSeg`/`VarSeg` (SegList shape) rather than rebuilding a
SegString, losing both the SegString container identity *and* the
str-typing for the concrete-string segments that *are* known.

**Reproducer:**
```python
from clausal.logic.variables import Var, unify, Trail
from clausal.logic.runtime.body_star_unify import (
    _build_star_list, _build_multi_star_list,
)
from clausal.terms import SegString, VarSeg

# list-of-chars star — str is recoverable but is lost
X = Var(); unify(X, ["e","l","l","o"], Trail())
assert _build_star_list(["h"], X, []) == ["h","e","l","l","o"]   # not 'hello'
Z = Var(); unify(Z, ["e","l","l","o"], Trail())
assert _build_multi_star_list([("fixed", ["h"]), ("star", Z)]) == [
    "h","e","l","l","o"
]                                                                # not 'hello'

# non-ground SegString star — rebuilt as SegList, not SegString
W = Var(); Inner = Var()
unify(W, SegString(["el", VarSeg(Inner), "o"]), Trail())
r = _build_multi_star_list([("fixed", ["h"]), ("star", W)])
# r is a SegList(['h','e','l', *Inner, 'o']) — should be a SegString instead.
```

**Expected:** Under "input type wins", either branch should re-detect
list-of-1-char-strs and promote to str when the surrounding context is
str-typed; the non-ground-SegString fork should preserve the
SegString container.
**Actual:** Always list / SegList.

**Notes:** Sibling of [[F018]] (SegList.__walk__ drops str typing via
char expansion), [[F033]] (head-output mode always builds a list), and
[[F034]] (head-output mode never walks SegString). Sibling-task companion: [[F042]] (unbound-Var-target builds SegList even when SegString would be type-correct) — same C1 class, same body-side audit task. The strings-as-lists
contract is genuinely underdetermined for "list of 1-char strs" —
ambiguous whether the value originated as a str or a list — but the
non-ground-SegString-to-SegList demotion has no such ambiguity and
should be fixable in isolation. Logged as design-gap (matching F018,
F033, F034 grading).

**Prior-known:** commit 82ecc96 — "Fix SegString bugs" specifically fixed the non-ground SegString path in `_build_star_list` (converting to SegList rather than wrapping in `VarSeg(SegString)`) but the *type-preservation* gap this finding flags — that list-of-1-char-strs and non-ground SegString stars both demote to list/SegList rather than promoting back to str/SegString — was left in place; commit f635551 (Phase 7) introduced the `all_str` gate that captures most ground cases, but the gate explicitly disables string promotion when a non-ground SegString segment is seen (the `all_str = False` flip in `_build_multi_star_list` line 167-184).

Fix (Phase 2 Task 13): both helpers now apply the new `maybe_promote_to_str` helper at every list-shaped exit. `_build_multi_star_list` was rewritten with a first-pass type check that determines whether every star + fixed element is str-compatible (1-char strs, strs, ground SegStrings, non-ground SegStrings, lists of 1-char strs); if so, the second pass builds str segments and emits a plain `str` (ground) or `SegString` (non-ground holes). Otherwise it falls back to the SegList build with a final `maybe_promote_to_str` so a list of all 1-char strs still re-promotes. The non-ground-SegString fork no longer demotes to SegList — the SegString container identity is preserved.

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

### F015 — SegList.__unify__ returns only the first valid split

- **Class:** C2 (Non-det collapsed to first)
- **Severity:** bug
- **Status:** fixed in Phase 2 Task 6
- **Location:** `clausal/terms.py:325-326` (with the gen at
  `clausal/terms.py:390-426`)
- **Discovered by:** Task 2 of Phase 0
- **Probe:** `probes/probe_F015.py`

**Symptom:** `SegList.__unify__` against a `list` / `str` target uses
`for _ in _seglist_unify_gen(...): return True`, returning on the
first yielded split. The generator enumerates *all* valid splits
(`_multi_star_splits` is full stars-and-bars), but only the first is
ever surfaced. For `SegList([*A, *B]) = [1, 2, 3]` there are four
valid splits — `A=[], B=[1,2,3]` / `A=[1], B=[2,3]` / `A=[1,2],
B=[3]` / `A=[1,2,3], B=[]` — but the unify hook commits to the first
without offering the others.

This is the textbook C2 violation: a logic-level non-deterministic
operation is collapsed to its first solution at the protocol boundary.
A Prolog-style `findall` / `bagof` over `[*A, *B] = [1,2,3]` would
return one solution instead of four; downstream conjunctions that
depended on the "right" split silently fail.

**Reproducer:**
```python
from clausal.logic.variables import Var, unify, Trail, deref
from clausal.terms import SegList, VarSeg, _seglist_unify_gen

A, B = Var(), Var()
sl = SegList([VarSeg(A), VarSeg(B)])
t = Trail()
assert unify(sl, [1, 2, 3], t) is True
assert deref(A) == [] and deref(B) == [1, 2, 3]
A2, B2 = Var(), Var()
sl2 = SegList([VarSeg(A2), VarSeg(B2)])
assert sum(1 for _ in _seglist_unify_gen(sl2, [1, 2, 3], Trail())) == 4
```

**Expected:** Enumerate all splits via the choice-point machinery, so
`bagof([A,B], unify(SegList[*A,*B], [1,2,3]), L)` yields 4 bindings.
**Actual:** Only the first split is surfaced; subsequent splits are
unreachable through the protocol.

**Notes:** The generator helper already does the right work — the bug
is in the consumer. Compare with the head/body multi-star unification
paths in `body_star_unify.py`, which *do* backtrack via compiled
for-loops. Fix likely requires exposing the gen through a non-det
protocol or moving the call sites onto the gen directly. Related to
[[F016]] (same pattern in SegString) and [[F026]] (the combinatorial
cost of enumerating all splits becomes visible once C2 is fixed).

Fix (Phase 2 Task 6): `SegList.__unify__` now caches the
`_seglist_unify_gen` instance on a new `_unify_gens` slot keyed by
`(content-of-target, id(trail))` (see the `_seg_unify_cache_key`
helper in `clausal/terms.py`). Each call into `__unify__` advances
the cached generator one step via `next()`, returning `True` for
each yielded split and `False` (plus dropping the cache entry) once
the generator is exhausted. Re-driving `unify(sl, [1,2,3], t)` four
times between `trail.mark()`/`trail.undo(mark)` pairs now surfaces
all four `[*A,*B] = [1,2,3]` splits via the deterministic bool
protocol — no new C-level hook required. The cache key is
content-derived (list targets are tupled) so a freshly constructed
but value-equal target on each loop iteration still hits the same
cached generator. The combinatorial perf concern flagged in
[[F026]] now affects real callers; left to its existing visibility-
only ledger entry.

### F016 — SegString.__unify__ returns only the first valid split

- **Class:** C2 (Non-det collapsed to first)
- **Severity:** bug
- **Status:** fixed in Phase 2 Task 6
- **Location:** `clausal/terms.py:562-563` (with the gen at
  `clausal/terms.py:594-627`)
- **Discovered by:** Task 2 of Phase 0
- **Probe:** `probes/probe_F016.py`

**Symptom:** Mirror of [[F015]] for `SegString`. `SegString.__unify__`
against a `str` target uses the same `for _ in
_segstring_unify_gen(...): return True` pattern. For
`SegString([*A, *B]) = "abc"` there are four valid splits but the
unify hook commits to `A="", B="abc"` and never offers the others.

**Reproducer:**
```python
from clausal.logic.variables import Var, unify, Trail, deref
from clausal.terms import SegString, VarSeg, _segstring_unify_gen

A, B = Var(), Var()
ss = SegString([VarSeg(A), VarSeg(B)])
t = Trail()
assert unify(ss, "abc", t) is True
assert deref(A) == "" and deref(B) == "abc"
A2, B2 = Var(), Var()
ss2 = SegString([VarSeg(A2), VarSeg(B2)])
assert sum(1 for _ in _segstring_unify_gen(ss2, "abc", Trail())) == 4
```

**Expected:** Four bindings enumerated; sym with [[F015]].
**Actual:** One.

**Notes:** Same fix shape as F015. Trail discipline inside the
generator is correct (see "Task 2 confirmed" bullet below) — the
mark/undo pair leaves the trail at its prior length after each yield,
so the iteration is safe to drive from outside.

Fix (Phase 2 Task 6): mirror of the F015 fix — `SegString.__unify__`
now caches `_segstring_unify_gen` on a `_unify_gens` slot keyed via
the shared `_seg_unify_cache_key` helper, and advances the cached
generator one step per call. Re-driving `unify(ss, "abc", t)` four
times via the `mark()` / `unify()` / `undo(mark)` pattern surfaces
all four splits of `[*A,*B] = "abc"`. No change to the C-level
`do_unify` protocol; the existing bool / `NotImplemented` contract
carries the non-determinism via per-(target, trail) generator state
on the SegString itself.

**Prior-known:** commit f635551 — "Phase 7: SegString and string-preserving pattern matching" introduced `SegString` and `_segstring_unify_gen` with the same `for _ in gen: return True` first-solution-only protocol that [[F015]] already documents for the older `SegList` path; the symmetry was preserved (intentionally — same code pattern) but neither side was upgraded to a true non-deterministic protocol.

*Task 2 confirmed (no finding):*
- **F027** — Trail discipline in `_seglist_unify_gen`
  (`terms.py:390-426`) and `_segstring_unify_gen`
  (`terms.py:594-627`) is correct. Each iteration calls
  `trail.mark()` before the per-split unifies and `trail.undo(mark)`
  after the yield, so the generator leaves the trail at its prior
  length after each iteration. The intentional non-symmetry is that
  the *last* iteration's bindings are left on the trail at the
  moment of `yield` — by design, so `__unify__`'s
  `for _ in gen: return True` picks up the bindings of the chosen
  split. Confirmed by counting `trail.mark()` before and after a
  full generator exhaustion: returns to the initial mark. Probe:
  shared logic verified inside `probes/probe_F015.py` /
  `probes/probe_F016.py`.
- **F028** — `_multi_star_splits` edge cases (`terms.py:429-443`)
  behave correctly: `n_stars=0, remainder=0` yields the empty tuple
  `()` (one valid split — the all-ground case); `n_stars=0,
  remainder>0` yields nothing (no way to absorb extra items);
  `n_stars=1, remainder=k` yields `(k,)`. Confirmed inside
  `probes/probe_F026.py`.

### Class C3 — SegString blind spots vs SegList

### F031 — `_head_list_unify_input` never walks SegString (non-ground silently fails)

- **Class:** C3 (SegString blind spots vs SegList)
- **Severity:** bug
- **Status:** fixed in Phase 2 Task 11 — `_head_list_unify_input_py`
  (and the matching `_list_unify.c` accelerator) now grow a SegString
  walk branch parallel to the SegList one: ground SegString routes
  through the existing `(list, str)` arm; non-ground SegString defers
  to output mode (returns `None`) so the body can constrain the
  unbound holes.
- **Location:** `clausal/logic/runtime/list_unify.py:114-117, 145-146`
  and `clausal/logic/runtime/_list_unify.c:139-149, 213-214`
- **Discovered by:** Task 3 of Phase 0
- **Probe:** `probes/probe_F031.py`

**Symptom:** The input-mode helper has an explicit ``isinstance(d,
SegList)`` walk branch but no SegString equivalent. A non-ground
``SegString(["a", VarSeg(X), "c"])`` flows past the list/str
isinstance check, past the `SegList` check, past the `is_var` defer
branch, and hits the final ``return False``. The clause head
``foo([H, *T])`` matched against the SegString silently fails even
though the unification is logically satisfiable
(e.g. H="a", T = SegString([VarSeg(X), "c"]) or analogous).

The C version mirrors the same blind spot: only `SegListType` is
TypeChecked at `_list_unify.c:140`; no `SegStringType` branch
exists, so behaviour is identical regardless of whether the C
extension was built (see C-vs-Python parity note below).

This is a textbook "silently drops solutions" pattern listed under
bug in the spec's severity vocabulary; sibling [[F023]] (same shape
on `SegString.__unify__(list)`) was re-graded to bug under the
same rule.

**Reproducer:**
```python
from clausal.logic.variables import Var, Trail, deref
from clausal.terms import SegString, VarSeg
from clausal.logic.runtime.list_unify import _head_list_unify_input

X = Var()
seg = SegString(["a", VarSeg(X), "c"])
H, T = Var(), Var()
t = Trail()
assert _head_list_unify_input(seg, [H], T, [], t) is False  # silent
```

**Expected:** Either deferred output mode (None) so the body can
constrain the SegString, or success with a SegString-aware
destructure. Silent False is the C8/C3 worst case.
**Actual:** Silent False.

**Notes:** Companion to [[F032]] (same path also fails on *ground*
SegString) and [[F034]] (the output-mode side has the same blind
spot). The Python and C paths agree, so this is *not* a C3 bug
that depends on the build configuration — both are equally broken.

**Prior-known:** commit aa2155d — "Compiler: head patterns accept strings in clause matching" widened `_head_list_unify_input` to accept `(list, str)` and `_build_list_dispatch_guard` / `_compile_multi_star_guard` to emit `isinstance(_, (list, str))`. The SegString type didn't yet exist at that commit (introduced 6 commits later in f635551), and Phase 7's `STRING_LIST_UNIFICATION.md` plan did not include a follow-up to widen these head-pattern paths for SegString. The blind spot was introduced by omission rather than regression.

### F032 — `_head_list_unify_input` rejects *ground* SegString too

- **Class:** C3 (SegString blind spots vs SegList)
- **Severity:** bug
- **Status:** fixed in Phase 2 Task 11 — same patch as [[F031]];
  ground SegString is walked to its str form and routed through the
  existing `(list, str)` arm in both the Python and C paths.
- **Location:** `clausal/logic/runtime/list_unify.py:114-117, 145-146`
  and `clausal/logic/runtime/_list_unify.c:139-149, 213-214`
- **Discovered by:** Task 3 of Phase 0
- **Probe:** `probes/probe_F032.py`

**Symptom:** A trivially-ground ``SegString(["abc"])`` whose
``__walk__()`` returns the plain str ``"abc"`` is *still* rejected
by `_head_list_unify_input`. The function never walks SegString in
either the C or Python path, so a Var bound to a ground SegString
matched against ``[H, *T]`` returns False even though
``unify(SegString(["abc"]), [H, *T])`` is unambiguously solvable
(H="a", T="bc").

This is the stronger half of [[F031]]: even when no logical
ambiguity exists, the input path silently fails.

**Reproducer:**
```python
from clausal.logic.variables import Var, unify, Trail, deref
from clausal.terms import SegString
from clausal.logic.runtime.list_unify import _head_list_unify_input

ss = SegString(["abc"])
assert ss.is_ground() and ss.__walk__() == "abc"
H, T = Var(), Var()
t = Trail()
assert _head_list_unify_input(ss, [H], T, [], t) is False  # WRONG
# Symmetric: Var bound to ground SegString
X = Var()
unify(X, SegString(["abc"]), Trail())
H2, T2 = Var(), Var()
assert _head_list_unify_input(X, [H2], T2, [], Trail()) is False
```

**Expected:** True with H='a' and T='bc' (or list equivalents under
the strings-as-lists contract).
**Actual:** Silent False.

**Notes:** The minimal fix is symmetric to the SegList branch at
list_unify.py:114-117 / _list_unify.c:140-149: add an
``isinstance(d, SegString)`` branch that calls ``d.__walk__()`` and
then routes through the existing ``(list, str)`` arm. The C path
needs the matching `SegStringType` cache + `TypeCheck` branch.
Related to [[F031]], [[F034]] (output-mode twin), [[F012]] (C-level
SegString-as-list-element blind spot).

**Prior-known:** same as [[F031]] — commit aa2155d widened the head-pattern path for `str` but not for `SegString`. Cross-ref the same Phase 7 plan gap.

### F040 — `_body_multi_star_unify` rejects ground SegString target

- **Class:** C3 (SegString blind spots vs SegList)
- **Severity:** bug
- **Status:** fixed in Phase 2 Task 11 — the dispatch's
  `isinstance(d, SegList)` arm now also fires on SegString. Ground
  SegString walks to a plain str and falls through to the enumeration
  loop unchanged.
- **Location:** `clausal/logic/runtime/body_star_unify.py:231-262`
- **Discovered by:** Task 4 of Phase 0
- **Probe:** `probes/probe_F040.py`

**Symptom:** The dispatch checks `isinstance(d, (list, str))` at line
234 (true → enumerate splits), then `isinstance(d, SegList)` at line
235 (true → walk and either enumerate or rebuild), then `is_var(d)` at
line 249 (true → construct + bind). A trivially ground
``SegString(["abc"])`` whose ``__walk__()`` returns the plain str
``"abc"`` falls through all four branches and hits the catch-all
``else: return`` at line 262, silently producing zero solutions.

This is the body-position multi-star parallel of [[F032]] (head-position
input rejects ground SegString). The fix is symmetric: a SegString
branch that walks the value and routes through the existing
``(list, str)`` arm.

**Reproducer:**
```python
from clausal.logic.variables import Var, unify, Trail
from clausal.logic.runtime.body_star_unify import _body_multi_star_unify
from clausal.terms import SegString

ss = SegString(["abc"])
assert ss.is_ground() and ss.__walk__() == "abc"
H, S, R = Var(), Var(), Var()
assert list(_body_multi_star_unify(
    ss, [("fixed", [H]), ("star", S), ("fixed", [R])], Trail()
)) == []                                            # WRONG — should yield True
# Symmetric: Var bound to ground SegString
X = Var(); unify(X, SegString(["abc"]), Trail())
H2, S2, R2 = Var(), Var(), Var()
assert list(_body_multi_star_unify(
    X, [("fixed", [H2]), ("star", S2), ("fixed", [R2])], Trail()
)) == []
```

**Expected:** `[True]` with `H='a'`, `S='b'`, `R='c'` (analogous to the
SegList branch which walks then enumerates).
**Actual:** Silent `[]`.

**Notes:** Companion to [[F041]] (same path drops non-ground SegString
too) and to [[F032]] (head-position twin). The body-position
single-star path inherits [[F031]]/[[F032]] via the delegation chain
(`_body_star_unify` → `_head_list_unify_input`), but the multi-star
path is independent and has its own dispatch — hence this separate
finding.

### F041 — `_body_multi_star_unify` has no non-ground SegString branch

- **Class:** C3 (SegString blind spots vs SegList)
- **Severity:** bug
- **Status:** fixed in Phase 2 Task 11 — non-ground SegString is
  routed through a new `_segstring_align` helper that binds every
  VarSeg to the empty string ``""`` (a witness extension of the
  goal), re-walks the SegString to its concrete prefix, and then
  enumerates the standard split loop. Yields one True per valid
  alignment; falls through silently otherwise (parity with the
  SegList branch still blocked by F030 / Phase 6).
- **Location:** `clausal/logic/runtime/body_star_unify.py:234-262`
- **Discovered by:** Task 4 of Phase 0
- **Probe:** `probes/probe_F041.py`

**Symptom:** The non-list/str dispatch has an ``isinstance(d, SegList)``
branch (lines 235-248) that walks the SegList; when the walked value is
still a SegList (i.e. genuinely non-ground), it constructs a SegList
from the pattern segments and unifies. There is *no* parallel
``isinstance(d, SegString)`` branch — a non-ground SegString-bound
target hits the catch-all ``else: return`` at :262 and silently drops
the goal.

(The existing SegList branch is *itself* currently blocked by the
deferred SegList-vs-SegList unification [[F030]] — but that's a
separate issue. F041 is the structural absence of a SegString branch
at all.)

This is the multi-star body-position parallel of [[F031]] (head-position
input never walks SegString).

**Reproducer:**
```python
from clausal.logic.variables import Var, Trail
from clausal.logic.runtime.body_star_unify import _body_multi_star_unify
from clausal.terms import SegString, VarSeg

X = Var()
ss = SegString(["a", VarSeg(X), "c"])
H, S, R = Var(), Var(), Var()
assert list(_body_multi_star_unify(
    ss, [("fixed", [H]), ("star", S), ("fixed", [R])], Trail()
)) == []                                            # silent
```

**Expected:** A structural SegString branch symmetric to lines 235-248
that constructs a SegString from the pattern (translating ``("fixed",
[v])`` → string slot, ``("star", v)`` → VarSeg) and unifies with the
target. Or, at minimum, a typed deferred-constraint signal.
**Actual:** Silent `[]`.

**Notes:** Cluster of body-position SegString C3 findings: this one
([[F041]] — non-ground multi-star), [[F040]] (ground multi-star),
plus the inherited [[F031]]/[[F032]]/[[F033]]/[[F034]] via
``_body_star_unify``'s delegation chain. The minimal fix is symmetric
to the head-position SegString patches.

### F047 — Multi-star head guard ignores SegString (both ground and non-ground)

- **Class:** C3 (SegString blind spots vs SegList)
- **Severity:** bug
- **Status:** fixed in Phase 2 Task 11 —
  `_compile_multi_star_guard` now emits a sibling `segstring_normalise`
  AST branch parallel to `seglist_normalise` (ground SegString → walk
  to str → existing `(list, str)` arm fires) plus a new
  `segstring_branch` that, for still-non-ground SegStrings, delegates
  to `$body_multi_star_unify` via the runtime `_segstring_align`
  helper so each alignment runs the body_stmts. `SegString` is added
  to `base_globals` so the emitted `isinstance(_d, SegString)`
  references resolve at runtime.
- **Location:** `clausal/logic/compiler/head_match.py:857-872`
  (`_compile_multi_star_guard` — the ``seglist_normalise`` block plus the
  trailing ``isinstance(_d, (list, str))`` test in ``list_branch``)
- **Discovered by:** Task 5 of Phase 0
- **Probe:** `probes/probe_F047.py`

**Symptom:** The multi-star head guard emits this normalisation pipeline
before its ``(list, str)`` isinstance arm:

```
_d = deref(_lcap)
if isinstance(_d, SegList):
    _d = _d.__walk__()            # walk SegList → list (or stays SegList)
if isinstance(_d, Var): defer …   # output mode
if isinstance(_d, (list, str)):
    …guarded body…                # input mode
```

There is no ``isinstance(_d, SegString)`` branch. A SegString target —
whether ground (``SegString(["abc"])`` whose ``__walk__()`` returns the
plain str ``"abc"``) or non-ground (``SegString(["a", VarSeg(X), "c"])``)
— walks past the SegList normalise, past the Var defer, fails the
``(list, str)`` isinstance test, and the multi-star arm is skipped.
The enclosing ``match`` falls through and the caller silently gets zero
solutions.

The probe drives the existing ``Bracket([*A, X, Y, *B], X, Y, A, B)``
fixture in ``tests/clausal_modules/list_edge_cases.seam`` with four
targets — ``"abc"`` (control), ``['a','b','c']`` (control),
``SegString(["abc"])`` (ground probe), and ``SegString(["a",VarSeg(X),"c"])``
(non-ground probe). Both controls yield 2 solutions; both SegString
calls yield 0.

This is the head-position multi-star parallel of [[F041]] (body-position
multi-star has no SegString branch) and [[F031]]/[[F032]] (head-position
single-star input-mode helper also has no SegString branch). Per the
spec vocabulary, "False/no-solutions on satisfiable goal = bug".

**Reproducer:** see `probes/probe_F047.py`. Output:
```
  Control Bracket("abc")             solutions: 2
  Control Bracket(['a','b','c'])       solutions: 2
  Probe   Bracket(SegString(['abc']))  solutions: 0
  Probe   Bracket(SegString(['a',*X,'c'])) solutions: 0
```

**Expected:** Either symmetric SegString normalisation at the guard
(``isinstance(_d, SegString)`` → ``_d = _d.__walk__()``, parallel to
the SegList branch at :857-872) followed by the existing
``(list, str)`` arm; or, for non-ground SegString, a structural
SegString-vs-segments unification analogous to the head-position
single-star fix proposed for F031/F041.
**Actual:** Silent zero solutions.

**Notes:** The minimal fix is symmetric to the SegList normalise — one
``isinstance``/``__walk__`` pair before the Var defer. Ground SegString
falls out for free (walk returns str → existing arm fires); the
non-ground case still drops because the walked value is itself a
SegString. A full fix would need a SegString-aware arm parallel to the
SegList walk-or-rebuild branch (or route through ``_body_multi_star_unify``,
once [[F040]]/[[F041]] are fixed there too). Companion cluster:
[[F031]]/[[F032]] (head-position single-star input), [[F034]]
(head-position single-star output), [[F040]]/[[F041]] (body-position
multi-star), [[F038]]/[[F039]] (`_in_iter`). The whole cluster shares
the same root cause: every dispatch site that branches on the target's
container type has a SegList arm but no SegString arm.

### F012 — Var bound to SegString in list position is not recognised as a char

- **Class:** C3 (SegString blind spots vs SegList)
- **Severity:** design-gap
- **Status:** fixed in Phase 2 Task 11 — the C str↔list loop now
  preserves its fast path (Var → allocate; ground 1-char str →
  compare) but, when the element is neither a Var nor a plain str,
  allocates the single codepoint and delegates to `do_unify` so the
  `__unify__` protocol fires on `SegString` (and any other custom
  term that knows how to unify with a 1-char string). Symmetric on
  both list-on-left and list-on-right arms.
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

**Prior-known:** commit b8d3038 — "Phase 1: string ↔ list unification at the C level" set the `PyUnicode_Check(elem) && PyUnicode_GET_LENGTH(elem) == 1` element type-check; SegString didn't exist yet (introduced in f635551 Phase 7), so the check was correct at the time. Phase 7 added the SegString type but never came back to widen this C-level element check.

### F034 — `_head_list_unify_output` never walks SegString star_val

- **Class:** C3 (SegString blind spots vs SegList)
- **Severity:** design-gap
- **Status:** fixed in Phase 2 Task 11 — both the Python output-mode
  helper and its C accelerator grow a SegString arm parallel to the
  SegList one: a ground SegString-bound star_val is iterated as
  chars and extended into the result list; a still-non-ground
  SegString is converted to a SegList equivalent (str segments →
  ConcreteSeg of chars, VarSegs preserved) and used to rebuild the
  output as a SegList for unification.
- **Location:** `clausal/logic/runtime/list_unify.py:166-200` and
  `clausal/logic/runtime/_list_unify.c:264-434`
- **Discovered by:** Task 3 of Phase 0
- **Probe:** `probes/probe_F034.py`

**Symptom:** The output-mode helper branches the dereffed
``star_val`` on ``list`` (extend), ``SegList`` (walk-and-extend or
rebuild as SegList), and ``Var`` (rebuild as SegList with a fresh
VarSeg). It has *no* SegString branch — a SegString-bound star_val
falls into the catch-all ``else`` at list_unify.py:197-198 (Python)
/ _list_unify.c:425-432 (C) and is appended as a single opaque
element.

Effect: a head ``foo([H, *T])`` whose T is bound to
``SegString(['hello'])`` produces ``[deref(H), SegString(['hello'])]``
— the SegString is neither walked into chars (as a ground SegList
would be) nor used to rebuild a SegList/SegString result. The C
and Python paths agree (both blind).

**Reproducer:**
```python
from clausal.logic.variables import Var, unify, Trail, deref
from clausal.terms import SegString
from clausal.logic.runtime.list_unify import _head_list_unify_output

target = Var()
H = Var(); T = Var()
unify(H, "h", Trail())
unify(T, SegString(["ello"]), Trail())
_head_list_unify_output(target, [H], T, [], Trail())
assert deref(target) == ["h", SegString(["ello"])]  # un-walked
# Compare with the SegList branch:
from clausal.terms import SegList, ConcreteSeg
target2 = Var()
H2 = Var(); T2 = Var()
unify(H2, "h", Trail())
unify(T2, SegList([ConcreteSeg(["e","l","l","o"])]), Trail())
_head_list_unify_output(target2, [H2], T2, [], Trail())
assert deref(target2) == ["h", "e", "l", "l", "o"]    # walked
```

**Expected:** Symmetric handling — walk ground SegString into the
result (extending chars or, under "input type wins", building a
str/SegString-shaped result); rebuild from segments when
non-ground, analogous to the SegList branch at list_unify.py:170-186.
**Actual:** SegString appended as a single opaque element.

**Notes:** Logged as design-gap rather than bug because the result
unify still succeeds and the target value is a defined Python
object; it just doesn't match the SegList branch's semantics. If
downstream code does `list(target)` or indexes into it, the
SegString-as-element will surface as a surprise. Companion to
[[F031]]/[[F032]] (input-mode SegString blind spots), [[F018]]
(SegList walk type-loss), [[F033]] (output-mode always builds a
list).

### F075 — Every char/atom builtin in `chars.py` is SegString-blind

- **Class:** C3 (SegString blind spots vs SegList)
- **Severity:** design-gap
- **Status:** fixed in Phase 2 Task 11 — `_atom_to_str` now walks a
  ground SegString to its str form (non-ground SegStrings still
  return `None` so the caller raises the usual `type_error`), which
  closes every atom-accepting predicate (`upcase_atom/2`,
  `downcase_atom/2`, `atom_length/2`, `atom_chars/2`, `atom_codes/2`,
  `atom_concat/3`, `sub_atom/5`, `number_chars/2`,
  `number_codes/2`). `char_type/2` and `char_code/2` get a parallel
  walk before their `isinstance(vc, str)` gate so they no longer
  silently fail on a single-char SegString.
- **Location:** `clausal/logic/builtins/chars.py:47-57` (`_atom_to_str`),
  plus the `isinstance(vc, str)` gate in `char_type/2`
  (`chars.py:105`) and `char_code/2` (`chars.py:179`)
- **Discovered by:** Task 10 of Phase 0
- **Probe:** `probes/probe_F075.py`

**Symptom:** ``_atom_to_str`` accepts only a plain Python ``str`` or a
zero-arity ``PredicateMeta``; ``SegString`` is neither, so every
atom-accepting predicate raises ``type_error("atom", SegString(...))``
when handed one — *even when the SegString is fully ground and would
walk to a plain str.* Affected: ``upcase_atom/2``, ``downcase_atom/2``,
``atom_length/2``, ``atom_chars/2``, ``atom_codes/2``, ``atom_concat/3``,
``sub_atom/5``, ``number_chars/2``, ``number_codes/2``. ``char_type/2``
and ``char_code/2`` use ``isinstance(vc, str)`` directly and *silently
fail* (zero solutions, no error) — see [[F071]] for the char_type
silent-fail surface.

**Reproducer:** see `probes/probe_F075.py`. Output excerpt:
```
upcase_atom(SegString(["h","i"]), V)   → type_error(atom, SegString(...))
atom_length(SegString(["h","i"]), N)   → type_error(atom, SegString(...))
char_type(SegString(["h","i"]), alpha) → silent 0 solutions
```

**Expected:** Same answer as for the walked str — ``SegString(["hi"])``
should behave like ``"hi"`` for every predicate above. Under the
strings-as-lists "input-type wins" contract, the SegString is a
str-shaped container.
**Actual:** Either ``type_error`` (atom-accepting predicates) or silent
fail (char-accepting predicates).

**Notes:** Same blind-spot pattern as [[F069]] (``phrase/2,3`` on
SegString), [[F068]] (``phrase/3`` state-thread), [[F031]]–[[F034]],
[[F040]]/[[F041]], [[F047]], [[F051]]. The cluster will collapse to a
single Phase 2 fix: either ``_atom_to_str`` grows a ``SegString``
branch (``return seg.__walk__() if isinstance(seg.__walk__(), str)
else None``), or the wrapper layer calls ``__walk__`` on Seg* inputs
before dispatch. The latter is more uniform across the codebase but
needs care for non-ground SegStrings (which walk to themselves —
they'd still hit the type_error). Cross-ref [[F012]] (Var bound to
SegString in list-element position) — that's the same gap surfacing
in the C-level unify path.

**Prior-known:** commit 98379ed — "perf: add C-accelerated inner loops for char/string predicates" added the C accelerators (`_chars_core.c`) for `char_type/2`, `atom_concat/3`, `sub_atom/5` and noted in its description "Python fallbacks are preserved for all predicates"; neither the C path nor the Python fallback gained a SegString-walk branch. The companion `todo/C_chars_issues.md` (created in the same commit, 82 lines) lists eight optimization concerns but does not mention the SegString-blind contract gap.

*Task 1 confirmed (no finding):*
- **F008** — Top-level `unify(SegString("abc"), ["a","b","c"], t)` and the
  reverse direction both succeed. The C path's str↔list block keys off
  `PyUnicode_Check`, which is `False` for `SegString`, so control falls
  through to the `__unify__` protocol at `_variables.c:1188` /
  `_variables.c:1207`. `SegString.__mro__` is `(SegString, object)` —
  it is not a `str` subclass. See `probes/probe_F008.py`.

*Task 2 confirmed (no finding):*
- **F030** — `SegList.__unify__(SegList)` (`terms.py:328-329`) and
  `SegString.__unify__(SegString)` (`terms.py:574-575`) both return
  `NotImplemented`, and the top-level `unify` consequently returns
  `False` for SegList-vs-SegList and SegString-vs-SegString. This is
  the deferred "Phase 6" SegList-vs-SegList unification feature
  explicitly out-of-scope per the audit spec; `wontfix: deferred`
  applies. Confirmed by direct calls.

*Task 3 confirmed (no finding):*
- **F035** — C-vs-Python parity for `_head_list_unify_input` /
  `_head_list_unify_output` is exact for the SegString blind spot.
  Both `list_unify.py:114-117` and `_list_unify.c:139-149` only
  `isinstance`/`TypeCheck` against `SegList`; neither has a
  `SegString` branch, neither walks SegString in the input path,
  and neither has a SegString branch in the output-mode
  star-handling. The behaviour described in F031/F032/F034 is
  therefore identical on `Py_GIL_DISABLED` builds without the C
  extension and on standard builds with the C extension loaded.
  No C-vs-Python divergence bug exists in this module. Verified by
  direct calls to both the unsuffixed (C-backed) and `_py`
  fallbacks; see `probes/probe_F031.py`, `probes/probe_F032.py`,
  `probes/probe_F034.py`.
- **F036** — The `is_var(d)` defer-to-output branch
  (`list_unify.py:141-143`, `_list_unify.c:205-211`) correctly
  returns `None` and leaves all input vars unbound. The output-mode
  helper then handles the actual construction at a later yield
  point. Confirmed via direct call:
  `_head_list_unify_input(Var(), [Var()], Var(), [], Trail())`
  returns `None`. The protocol contract (None = defer) holds.
- **F037** — Task 3 confirmed: the fast path at `list_unify.py:101-109` (gated `type(d) is list and star_val is not None and not after_vals`) deliberately skips strings; strings flow through the slow path at `:119-139` where `isinstance(d, (list, str))` correctly handles both via uniform slicing. F031/F032 implicitly demonstrated the slow path's string-handling correctness for the SegList walk → list result case. No fast-path-specific finding.

*Task 4 confirmed (no finding):*
- **F044** — Task 4 confirmed: `_build_multi_star_list` edge cases all behave correctly. The str-preservation gate at `body_star_unify.py:197-204` (`all_str` tracked across loop iterations, plus the `all(isinstance(e, str) and len(e) == 1 for e in result)` final check) correctly handles: (a) an empty string `""` bound to a star (no-op merge per the `if d:` guard at `:148`), (b) a single ConcreteSeg of 1-char strs (preserves str via the gate), (c) entirely-empty input segments list (returns `[]`), (d) a mix of star types where any non-str element flips `all_str` to False. No probe (verified by code-path reading + bench-runs in adjacent probes).
- **F045** — `_body_star_unify` (single-star body-position dispatch at
  `body_star_unify.py:26-47`) is a thin delegate to
  `_head_list_unify_input` (for `SegList` and `list` targets) and
  `_head_list_unify_output` (for unbound `Var` targets). All the C3
  SegString blind spots and the C1 type-loss findings already logged
  for the head-position helpers — [[F031]], [[F032]], [[F033]],
  [[F034]] — therefore apply to body-position single-star
  unification too. No new finding is logged for `_body_star_unify`
  itself; the same fix scope applies. Confirmed by direct calls
  reproducing F031/F032/F033 via `_body_star_unify`; no separate
  probe (covered by the existing F031/F032/F033/F034 probes which
  exercise the delegated helpers).

*Task 6 confirmed (no finding):*
- **F049** — Task 6 confirmed: `_head_has_deferred_pattern` (goal_shallow.py:226–262) correctly checks for `SegList` and `StarUnpack` in clause heads to gate continuation-TCO; no `SegString` check is needed. Rationale: `SegString` is a runtime construct created only in `__walk__` (when ground) and in `_build_multi_star_list` (body-position multi-star), never as a head literal. Head terms are validated by `term_to_ast_expr` (terms_to_ast.py) which lacks a case for `SegString` and raises `NotImplementedError` if someone attempts to use one as a head argument; `is_term_instance(SegString(...))` returns False. Since `SegString` cannot appear in heads, the absence of a SegString check in the deferred-pattern gate is correct and requires no fix. Verified by: (1) inspection of `SegString.__init__` and `__walk__` (no head-constructor entry points); (2) `term_to_ast_expr` type coverage (SegString not handled); (3) runtime check that `is_term_instance(SegString(...)) == False`. No probe needed (static verification only).

### Class C4 — Head-pattern literal mismatch

### F046 — C4 confirmed: rule heads with string literals fail to match char-list callers

- **Class:** C4 (Head-pattern literal mismatch)
- **Severity:** bug
- **Status:** fixed in 6c7acf6 (2026-06-16 follow-up spec `docs/superpowers/specs/2026-06-13-f046-head-literal-mismatch-design.md`; narrow fix — split `str` out of the `MatchValue` scalar tuple, emit a wildcard capture + same-type-short-circuit `unify` guard. Was: deferred to follow-up spec per user decision 2026-05-26.)
- **Location:** `clausal/logic/compiler/head_match.py` (the `MatchValue` branch for str/bytes literals — `str` now split out into a wildcard-capture + `unify`-guard branch; `bytes` stays on `MatchValue`)
- **Discovered by:** Task 5 of Phase 0
- **Probe:** `probes/probe_F046.py`

**Symptom:** A rule `Quux("abc") <- (real_body)` compiles to a Python `match` arm with `MatchValue(Constant("abc"))` at `head_match.py:253-254`. Python's `match` compares `MatchValue` with `==`, so a caller `Quux(['a','b','c'])` — which unifies with `"abc"` under the strings-as-lists contract at the runtime layer — silently fails to match this clause. The symmetric list-literal case (`Zorp(['a','b','c']) <- body` called with `"abc"`) works correctly because list-literal heads go through the wildcard-capture + runtime-unify path at `head_match.py:258`. Facts are dodged by the `_normalize_dataclass_fact` elaborator at `database.py:332-361` (gated by `body_goals == [True]` at `database.py:274`, which also catches `<- (True)` bodies), but rules with non-True bodies survive with the literal in the head.

**Reproducer:**
```python
# Define a rule Quux("abc") <- Helper(1), and a fact Helper(1).
# Then call Quux(['a','b','c']) — strings-as-lists says this should match.
# Actual: 0 solutions.
# See probe_F046.py for full setup via inline .clausal source.
```

**Expected:** `call("Quux", ["a", "b", "c"])` returns 1 solution (the same as `call("Quux", "abc")`).
**Actual:** Returns 0 solutions.

**Notes:** Confirmed by extended probe `probe_F046.py`. Fix-scope assessment from Task 5:

1. The narrow fix at `head_match.py:253-254` is to split the `(int, float, str, bytes, complex)` tuple — emit `MatchValue` only for non-sequence scalars (int, float, complex); emit a wildcard capture + `unify(_lcap, literal, trail)` guard for `str` and `bytes`, mirroring the list-literal path that already works correctly.
2. Alternative: lift the fact-side elaborator gate (`_normalize_dataclass_fact` at `database.py:274`) to run for all clauses, not just `body == [True]` clauses. This removes the C4 surface at the source.
3. Either approach has perf implications: literal-string-head clauses become wildcard-match + runtime-unify instead of Python-level `==`. May warrant a same-type fast-path. Verify first-arg indexing (`clausal/logic/compiler/arg_index.py:162` mentions the Var+Unify pattern) still discriminates correctly when literal heads are converted.
4. Compound-head and list-head cases ([[F048]]) inherit whichever fix lands.
5. Symmetric concern for `bytes` (also a sequence type) — not explicitly probed but the same branch handles it.

Sibling C-class cluster: this is C4, structurally orthogonal to the C3 "SegList arm but no SegString arm" cluster ([[F031]] [[F032]] [[F034]] [[F040]] [[F041]] [[F047]]). Both are compiler-side findings; they'd likely be tackled in separate Phase 2 efforts.

**Prior-known:** commit aa2155d — "Compiler: head patterns accept strings in clause matching" widened the *runtime* destructuring path (`_head_list_unify_input` and the two `isinstance` dispatch guards) so a clause with a list-literal head matches a string caller. The commit message claims "user-defined predicates with list patterns work on strings" and lists three sites changed. The fourth site — `MatchValue(Constant(<str>))` for clause heads that contain a *string literal* — was not addressed; that's the F046 surface. Phase 5b's plan in `STRING_LIST_UNIFICATION.md` (L1198-1281) likewise only enumerates the three sites that were fixed.

Phase 2 deferred F046 per user decision 2026-05-26; **closed 2026-06-16** via the follow-up spec `docs/superpowers/specs/2026-06-13-f046-head-literal-mismatch-design.md` (commit 6c7acf6). The **narrow** approach was chosen (split `str` out of the `MatchValue` scalar tuple at the single `head_match.py` site; emit a wildcard capture + a same-type-short-circuit `unify` guard `_scap == "abc" or unify(_scap, "abc", trail)`, mirroring the existing list/dict/set guard machinery). The broad (`database.py:274` elaborator-gate removal) and combined approaches were rejected — see the spec's "Rejected alternative" section (and the rejected `Seg*`-head representation). The conjoined finding F095 (C15 first-arg indexing) was closed in Phase 2 Task 8 (commit 9494e22), restoring the dispatch-layer half; this fix restores the compile-layer half and composes with it (`arg_index.py` buckets a str-literal head and its char-list caller together; the in-bucket match now succeeds). `bytes` was deliberately left on the `MatchValue` fast path (no strings-as-lists contract; documented exclusion + extension point in the spec and `todo/bytes-as-lists.md`). The Phase 1 test `test_F046_rule_str_head_matches_charlist_caller` was flipped from xfail-strict to passing and joined by added coverage (multi-clause dispatch via char-list, `SegString` caller, compiler-level guard lock-in, F048 compound-head list-unify path, `bytes` regression, same-type fast path); a dispatch micro-benchmark lives at `benchmarks/bench_f046_head_dispatch.py` (same-type str path 1.86µs vs 1.83µs int `MatchValue` baseline — no regression).

*Task 5 confirmed (no finding):*
- **F048** — Task 5 confirmed: compound heads containing list literals (e.g. ``Zorp(['a','b','c']) <- body``) and list-literal-only paths are subsumed by the successful elaboration + wildcard-capture + runtime-unify mechanism. Direct inspection of the compiled clause shows the parser/elaborator lifts the entire argument into a body Unify:
  ``Clause(head=Zorp(arg_0=AttVar(_0)), body=[Unify(left=AttVar(_0), right=['a','b','c'])])`` —
  the head pattern is a wildcard capture; runtime unify handles the list value, and calls with str-typed args match via the strings-as-lists contract. List-literal heads therefore work. Str-literal heads in rules with non-trivial bodies (e.g. ``Quux("abc") <- Helper(1)``) exposed the C4 gap directly — that is the F046 surface, **fixed 2026-06-16** (commit 6c7acf6). **Update (2026-06-16, corrected by compiler inspection during the F046 fix):** compound heads like ``Quux(foo("abc")) <- body`` are NOT lifted into a body Unify and do NOT inherit the F046 bug. The head compiles to a `MatchClass(Call(func=LoadName(...), args=_lcap, ...))` whose inner ``"abc"`` is an *element of the Call's args list*, handled by `_head_list_unify_input` (the runtime list-unify path) — already strings-as-lists-correct, never a `MatchValue`. (The functor-name str now routes through the new str branch, but that only changes how the name is matched, not correctness.) Locked in by `test_F048_compound_str_head_inner_arg_via_list_unify`. No separate probe for F048 (verified by direct module inspection); F046's probe covers the core issue.

### Class C5 — Hash/eq asymmetries

### F017 — SegString.__hash__ violates the Python eq/hash invariant

- **Class:** C5 (Hash/eq asymmetries)
- **Severity:** bug
- **Status:** fixed in Phase 2 Task 5
- **Location:** `clausal/terms.py:589-591` (with `__eq__` at
  `clausal/terms.py:581-587`)
- **Discovered by:** Task 2 of Phase 0
- **Probe:** `probes/probe_F017.py`

**Symptom:** `SegString.__hash__` returns `hash(walked)` when the
SegString is ground but `id(self)` otherwise. `SegString.__eq__`
returns `True` for two SegStrings whose `_segments` lists compare
equal (even when non-ground). So two non-ground SegStrings
constructed from the same `_segments` list (same Var, same string
literals) compare equal but hash to distinct values, violating
Python's data-model invariant
`a == b ⇒ hash(a) == hash(b)`.

Concrete effect: identical non-ground SegStrings are distinct keys
in a `dict` or `set`. Any memoisation / tabling / `setof` that uses
SegString as a key silently keeps both copies and may double-count.

**Reproducer:**
```python
from clausal.logic.variables import Var
from clausal.terms import SegString, VarSeg

X = Var()
ss1 = SegString(["a", VarSeg(X), "c"])
ss2 = SegString(["a", VarSeg(X), "c"])
assert ss1 == ss2                          # True
assert hash(ss1) != hash(ss2)              # invariant violated
assert len({ss1: 1, ss2: 2}) == 2          # both kept as distinct keys
```

**Expected:** Either both hashable (and equal-hash for equal values),
or both unhashable (like SegList).
**Actual:** Non-ground SegString is hashable but breaks the invariant.

**Notes:** Two fixes possible: (a) raise TypeError for non-ground
(matching SegList — but then ground SegString stays hashable, which is
a different asymmetry); (b) hash on the `_segments` tuple structure
(but `Var` objects are usually identity-hashed already, so this works
trivially). Related to [[F025]] (SegList vs SegString hashability
asymmetry) and the C6 tabling concerns the spec calls out.
Fix (Phase 2 Task 5): adopted approach (b) — both Seg* `__hash__`
methods now return `hash(walked)` when ground and a structural hash
over `_segments` (via the shared `_seg_hash_key` helper) when
non-ground, so two SegStrings built from identical segments produce
identical hashes and the eq/hash invariant holds.

**Notes (Phase 2 Task 13 contract revision):** the Task 5 hashable-when-
ground / structural-when-non-ground rule was reverted in Task 13.
Under the user-confirmed Liskov "strings-as-lists" model, hashing
behaviour of a Clausal-side seg container is undefined; both
`SegList.__hash__` and `SegString.__hash__` now *unconditionally*
raise `TypeError("unhashable type: ...")` — matching Python's `list`
parallel. The Python eq/hash invariant is trivially satisfied (no
SegString or SegList instance is ever hashable). The shared
`_seg_hash_key` helper added in Task 5 is removed (no longer used).
Callers needing hashability convert via `to_str()` / `to_list()` /
`str(...)` / `list(...)` first.

### F019 — SegList vs SegString __eq__ asymmetry against str / list

- **Class:** C5 (Hash/eq asymmetries)
- **Severity:** design-gap
- **Status:** fixed in Phase 2 Task 5
- **Location:** `clausal/terms.py:366-374` and
  `clausal/terms.py:581-587`
- **Discovered by:** Task 2 of Phase 0
- **Probe:** `probes/probe_F019.py`

**Symptom:** The two Seg* classes disagree about which container they
accept in `__eq__`:

| left → / right ↓     | `str`  | `list` |
|----------------------|--------|--------|
| `SegList([...])`     | False  | walks  |
| `SegString([...])`   | walks  | NI→F   |

`SegList(['a','b','c']) == 'abc'` is `False` (str rejected, returns
NotImplemented; Python falls back to identity which is also False).
`SegString(['abc']) == 'abc'` is `True`. Same for the inverse cross
type. The strings-as-lists contract makes these two Seg* values
semantically interchangeable, so the equality answers should agree.

**Reproducer:**
```python
from clausal.terms import SegList, SegString, ConcreteSeg

sl = SegList([ConcreteSeg(["a", "b", "c"])])
ss = SegString(["abc"])
assert (sl == "abc")        is False        # SegList rejects str
assert (ss == "abc")        is True         # SegString accepts str
assert (sl == ["a","b","c"]) is True        # SegList accepts list
assert (ss == ["a","b","c"]) is False       # SegString rejects list
```

**Expected:** Both classes agree on both container types — either
both reject the foreign container, or both walk-then-compare.
**Actual:** Each class only accepts its own container.

**Notes:** Companion to [[F020]] (same asymmetry in `__add__`) and
[[F023]] (same asymmetry in `__unify__(list)`). Fixing C5 requires
deciding the rule once and applying it across __eq__, __add__,
__unify__, and likely the C-level identity test.
Fix (Phase 2 Task 5): `SegList.__eq__` now accepts `str` (returns
`True` when the walked list is a list of 1-char strings that joins to
the str), and `SegString.__eq__` now accepts `list` (mirror). Both
also accept the sibling Seg* type, delegating to the other side for
symmetric handling. `__add__` and `__unify__` are tracked separately
under F020/F023.

### F025 — SegList.__hash__ unconditional vs SegString.__hash__ conditional

- **Class:** C5 (Hash/eq asymmetries)
- **Severity:** design-gap
- **Status:** fixed in Phase 2 Task 5
- **Location:** `clausal/terms.py:376-378` and
  `clausal/terms.py:589-591`
- **Discovered by:** Task 2 of Phase 0
- **Probe:** `probes/probe_F025.py`

**Symptom:** `SegList.__hash__` raises `TypeError("unhashable type:
'SegList'")` unconditionally, even when the SegList is ground (i.e.
walks to a plain Python list). By contrast `SegString.__hash__`
returns a real hash when ground and `id(self)` when not (see
[[F017]] for the invariant violation in the non-ground case). A
ground SegList ``SegList([ConcreteSeg(['a','b','c'])])`` has a
well-defined value but cannot be used as a dict key.

**Reproducer:**
```python
from clausal.terms import SegList, SegString, ConcreteSeg

sl = SegList([ConcreteSeg(["a", "b", "c"])])
assert sl.is_ground()
try:
    hash(sl)            # TypeError
except TypeError:
    pass
ss = SegString(["abc"])
assert hash(ss)         # works
```

**Expected:** Both classes share a rule: either both hashable when
ground / unhashable when not, or both unhashable.
**Actual:** SegList unconditionally unhashable, SegString
conditionally hashable.

**Notes:** This mirrors `list` (unhashable) vs `str` (hashable) at
the host-language level, so it's defensible — but it makes
strings-as-lists round-tripping leak through to dict-key behaviour.
Related to [[F017]] (the SegString hash invariant bug) and the C6
tabling concerns.
Fix (Phase 2 Task 5): both Seg* `__hash__` methods now share the
same discipline — `hash(walked)` when ground (via `tuple` for
SegList), and a structural hash over `_segments` when non-ground
(via the shared `_seg_hash_key` helper). Ground SegList is therefore
hashable as a dict key, matching ground SegString, and non-ground
hashes line up with `_segments`-based `__eq__`.

**Notes (Phase 2 Task 13 contract revision):** the Task 5 fix was
reverted in Task 13 under the user-confirmed Liskov rule. Both
SegList and SegString now *unconditionally* raise `TypeError` on
hash — the symmetric rule is now "both unhashable always", matching
Python's `list` parallel. Hashing of seg containers is undefined on
the Clausal side; callers convert via `to_list()` / `to_str()` first.
The `_seg_hash_key` helper introduced in Task 5 has been removed
(no longer used).

### Class C6 — Hashable vs unhashable bridges
*(none yet)*

### Class C7 — Unicode / multi-codepoint

### F002 — Multi-codepoint emoji split at codepoint, not grapheme, boundary

- **Class:** C7 (Unicode / multi-codepoint)
- **Severity:** doc-only
- **Status:** fixed in 07129a8
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

**Notes:** Doc-only fix landed in commit 2c8b1f7 (Phase 2 Task 2) — documented in the "Code-point vs grapheme semantics" section of docs/strings_as_lists.md.

### F003 — NFC and NFD forms of the same grapheme do not unify

- **Class:** C7 (Unicode / multi-codepoint)
- **Severity:** doc-only
- **Status:** fixed in 07129a8
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

**Notes:** Doc-only fix landed in commit 2c8b1f7 (Phase 2 Task 2) — documented in the "Code-point vs grapheme semantics" section of docs/strings_as_lists.md.

### F004 — List element must be exactly one codepoint (multi-char rejected)

- **Class:** C7 (Unicode / multi-codepoint)
- **Severity:** doc-only
- **Status:** fixed in 07129a8
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

**Notes:** Doc-only fix landed in commit 2c8b1f7 (Phase 2 Task 2) — documented in the "Code-point vs grapheme semantics" section of docs/strings_as_lists.md.

Reproducer cases all return False at the size-mismatch check (`:1129`) before reaching the per-element `PyUnicode_GET_LENGTH(elem) == 1` gate (`:1144`/`:1171`). The per-element gate is effectively unreachable in isolation because any list whose elements sum to `n` codepoints with at least one multi-char element must have fewer than `n` slots. The doc-only finding stands: the contract documented by the per-element gate (no multi-char elements) is implicitly enforced by the size check in every reachable case.

### F007 — Lone surrogate halves are treated as ordinary codepoints

- **Class:** C7 (Unicode / multi-codepoint)
- **Severity:** doc-only
- **Status:** fixed in 07129a8
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

**Notes:** Doc-only fix landed in commit 2c8b1f7 (Phase 2 Task 2) — documented in the "Code-point vs grapheme semantics" section of docs/strings_as_lists.md.

### F071 — `char_type/2` silently fails on multi-codepoint graphemes

- **Class:** C7 (Unicode / multi-codepoint)
- **Severity:** doc-only
- **Status:** fixed in 07129a8
- **Location:** `clausal/logic/builtins/chars.py:104-106` (the
  ``len(vc) != 1`` gate)
- **Discovered by:** Task 10 of Phase 0
- **Probe:** `probes/probe_F071.py`

**Symptom:** ``char_type(Char, Type)`` accepts only Char arguments
where ``isinstance(vc, str) and len(vc) == 1``. A user-perceived
grapheme spanning multiple codepoints — thumbs-up + skin-tone modifier
``"👍🏽"`` (2 codepoints), NFD ``"é"`` = ``e`` + combining acute
(2 codepoints), family emoji ZWJ sequences (5+ codepoints) — silently
returns zero solutions at the length check. No type_error, no warning.
Single-codepoint astral emoji (e.g. ``"😀"`` = U+1F600) work correctly
because their str length is 1.

**Reproducer:**
```python
from clausal.logic.builtins import get_builtin_dispatch
from clausal.logic.variables import Trail
from clausal.logic.trampoline import StepGenerator, solutions
disp = get_builtin_dispatch("char_type", 2, None)
assert len(solutions(StepGenerator(disp, None, None, None,
    "\U0001f600", "print", Trail()))) == 1   # single-cp OK
assert len(solutions(StepGenerator(disp, None, None, None,
    "\U0001f44d\U0001f3fd", "print", Trail()))) == 0  # 2-cp silent fail
```

**Expected:** Codepoint-level identity (the documented contract for
[[F002]] / [[F004]]).
**Actual:** Same as expected — the failure mode is silent, no error.

**Notes:** Doc-only fix landed in commit 2c8b1f7 (Phase 2 Task 2) — documented in the "Code-point vs grapheme semantics" section of docs/strings_as_lists.md.

### F074 — `upcase_atom`/`downcase_atom` can change string length

- **Class:** C7 (Unicode / multi-codepoint)
- **Severity:** doc-only
- **Status:** fixed in 07129a8
- **Location:** `clausal/logic/builtins/chars.py:207, 222` (the
  ``.upper()`` / ``.lower()`` calls)
- **Discovered by:** Task 10 of Phase 0
- **Probe:** `probes/probe_F074.py`

**Symptom:** Python's case-folding is locale-aware and not bijective
on codepoint length:
  * ``"ß"`` (1 cp) → ``.upper() = "SS"`` (2 cps)
  * ``"ﬃ"`` (1 cp ligature) → ``.upper() = "FFI"`` (3 cps)
  * ``"ς"`` (final sigma) and ``"σ"`` (medial sigma) both → ``"Σ"``
    → ``.lower() = "σ"`` (round-trip loses the final form)

Consequences for the strings-as-lists contract:
  * ``atom_length`` is *not* preserved by ``upcase_atom`` /
    ``downcase_atom``. ``length("ß", 1)`` succeeds but
    ``upcase_atom("ß", X), length(X, L)`` binds ``L = 2``.
  * ``downcase_atom(upcase_atom(A))`` is not the identity on case-folded
    text, even when the original is lowercase.

**Reproducer:** `probes/probe_F074.py`. ``upcase_atom('straße', U)``
binds ``U = 'STRASSE'`` (length 7, was 6).

**Expected:** Python's default case-folding semantics — the
implementation rule.
**Actual:** Same as expected.

**Notes:** Doc-only fix landed in commit 2c8b1f7 (Phase 2 Task 2) — documented in the "Code-point vs grapheme semantics" section of docs/strings_as_lists.md.

### F076 — `sub_atom/5` and `atom_concat/3` split at codepoint boundaries

- **Class:** C7 (Unicode / multi-codepoint)
- **Severity:** doc-only
- **Status:** fixed in 07129a8
- **Location:** `clausal/logic/builtins/chars.py:386-388, 483` and
  `clausal/logic/builtins/_chars_core.c:272-298, 450`
- **Discovered by:** Task 10 of Phase 0
- **Probe:** `probes/probe_F076.py`

**Symptom:** Both positional predicates index into the str at codepoint
offsets. ``atom_concat(A, B, S)`` enumerates ``i ∈ [0, len(S)]`` and
binds ``A = S[:i], B = S[i:]`` — for an input with a multi-codepoint
grapheme, the middle split breaks the grapheme. ``sub_atom`` likewise
slices at arbitrary codepoint indices. Resulting substrings can contain
isolated combining marks or skin-tone modifiers with no base character.

**Reproducer:** see `probes/probe_F076.py`. For
``g = "\U0001f44d\U0001f3fd"`` (thumbs-up + skin-tone), the middle
split of ``atom_concat(A, B, g)`` yields
``A = "\U0001f44d", B = "\U0001f3fd"`` (a dangling modifier).

**Expected:** Codepoint-level slicing — the documented contract.
**Actual:** Same as expected.

**Notes:** Doc-only fix landed in commit 2c8b1f7 (Phase 2 Task 2) — documented in the "Code-point vs grapheme semantics" section of docs/strings_as_lists.md.

**Prior-known:** commit 98379ed introduced the C accelerator with the same codepoint-offset slicing semantics as the Python original; no commit in the history has changed sub_atom/atom_concat to grapheme-aware semantics.

*Task 1 confirmed (no finding):*
- **F001** — The `n == 0` fast path at `_variables.c:1130` /
  `_variables.c:1158` correctly succeeds for `unify("", [], t)` and
  `unify([], "", t)`. See `probes/probe_F001.py`.

### Class C8 — Partial-term short-circuits

### F021 — SegList sequence protocol crashes on non-ground

- **Class:** C8 (Partial-term short-circuits)
- **Severity:** bug
- **Status:** fixed in Phase 2 Task 7 — ``__len__`` / ``__iter__`` /
  ``__getitem__`` return a partial answer drawn from the concrete
  prefix (sum of ConcreteSeg sizes / iter over ConcreteSeg elements /
  index into the known prefix); ``__getitem__`` past the prefix raises
  a typed ``PartialTermError`` (defined in ``clausal/terms.py``) rather
  than a bare ``TypeError``.
- **Location:** `clausal/terms.py:334-351` (via `to_list()` at
  `clausal/terms.py:285-292`)
- **Discovered by:** Task 2 of Phase 0
- **Probe:** `probes/probe_F021.py`

**Symptom:** `SegList.__len__`, `SegList.__iter__`, and
`SegList.__getitem__` all delegate to `self.to_list()`, which raises
`TypeError("SegList is not ground: ...")` when the SegList has any
unbound `VarSeg`. A caller using duck-typed sequence operations on a
non-ground SegList gets a crash rather than a logically-meaningful
answer (a partial iterator over the ConcreteSeg elements would be
defensible) or a deferred constraint.

**Reproducer:**
```python
from clausal.logic.variables import Var
from clausal.terms import SegList, VarSeg, ConcreteSeg

X = Var()
sl = SegList([ConcreteSeg([1, 2]), VarSeg(X)])
try:
    len(sl)        # TypeError
except TypeError:
    pass
try:
    list(sl)       # TypeError
except TypeError:
    pass
try:
    sl[0]          # TypeError
except TypeError:
    pass
```

**Expected:** Either a defined answer for the ConcreteSeg prefix /
known indices, or a typed exception clearly tagged as
"non-ground-required". The current TypeError is the latter, but the
message text just says "not ground" which doesn't surface to logic
code.
**Actual:** TypeError surfaces wherever a builtin tries `len`,
`iter`, or `getitem`.

**Notes:** Pairs with [[F022]] (`__contains__` instead returns silent
False on the same partial-term). The two are arguably inconsistent:
`__len__` raises, `__contains__` quietly answers False. Pick one
discipline. Related to spec's `_in_iter` example (list_unify.py).

Re-graded from design-gap to bug after Task 2 spec review: the spec's severity vocabulary lists "crashes" under bug, and TypeError on a sequence-protocol call is a crash regardless of whether it is typed-and-informative. Same logic as the Task 1 F011 re-grade. The implementer's defense (TypeError is a deliberate contract signal) is preserved as context but no longer determines the severity.

### F023 — SegString.__unify__(list) silently fails when non-ground

- **Class:** C8 (Partial-term short-circuits)
- **Severity:** bug
- **Status:** fixed in Phase 2 Task 7 — non-ground
  ``SegString.__unify__(list)`` now walks the SegString, converts every
  ``str`` segment to a ``ConcreteSeg`` of chars (preserving VarSegs),
  and delegates to ``SegList.__unify__(list)`` so the symmetric
  generator-driven split path picks up the call. Returns
  ``NotImplemented`` only for unsupported target types. Cascade-closed
  the SegString-Rest half of F069 (``test_F069_phrase3_rejects_segstring_rest``).
- **Location:** `clausal/terms.py:565-573`
- **Discovered by:** Task 2 of Phase 0
- **Probe:** `probes/probe_F023.py`

**Symptom:** `SegString.__unify__` handles `list` only when the
SegString is fully ground (walks to a `str`, then re-unifies the
`str` against the list). When the SegString has any unbound VarSeg,
the method returns `NotImplemented`, which the C top-level unify
treats as "no protocol match → False". The user sees a silent
failure even though the unification is logically solvable
(`SegString(["a", *X, "c"]) = ['a','b','c']` ⇒ `X = ['b']` or
`X = "b"`).

The companion `SegList.__unify__(str)` *does* handle the non-ground
case — it routes the SegList through `_seglist_unify_gen` against
the string. The SegString side has no such twin path against a list.

**Reproducer:**
```python
from clausal.logic.variables import Var, unify, Trail, deref
from clausal.terms import SegString, SegList, VarSeg, ConcreteSeg

X = Var()
ss = SegString(["a", VarSeg(X), "c"])
t = Trail()
assert ss.__unify__(["a", "b", "c"], t) is NotImplemented
assert unify(ss, ["a", "b", "c"], t) is False        # silent
# Symmetric SegList<->str path works:
Y = Var()
sl = SegList([ConcreteSeg(["a"]), VarSeg(Y), ConcreteSeg(["c"])])
assert unify(sl, "abc", Trail()) is True
```

**Expected:** Either succeed by routing the SegString through the
generator (split the list, bind X to the inner slice), or surface a
typed failure. Silent `False` on a satisfiable goal is the C8 worst
case.
**Actual:** Silent `False`.

**Notes:** This is a C3 SegString-blind-spot finding too — the spec
explicitly calls out `SegString.__unify__(list)` only working when
ground. Logged under C8 because the silent failure flavour matches
the C8 description; C3 covers the structural absence of the twin
path. Related to [[F012]] (C-side blind spot for SegString-as-list-
element) and the spec's C3 enumeration.

Re-graded from design-gap to bug after Task 2 spec review: silent dropped solutions on a logically-satisfiable unify call is the textbook "silently drops solutions" pattern listed under bug in the spec's severity vocabulary. F015 and F016 have the same character and were graded bug; F023 should match. The C3 structural-gap framing remains valid but does not lower the C8 severity.

**Prior-known:** commit 82ecc96 — "Fix SegString bugs, update strings_as_lists docs for Phase 7" fixed one half of this gap: `SegString.__unify__ vs list` "delegate to C-level str↔list unification instead of broken `walked == list(other)` comparison". That fix only routes through C str↔list when the SegString walks to a plain str (i.e. is ground); the non-ground case this finding documents still returns `NotImplemented` and surfaces as silent `False`. The commit description acknowledges only the ground case ("walked == list(other) was broken"); the non-ground hole was not addressed.

### F038 — `_in_iter` raises on ground SegString (no `__iter__`)

- **Class:** C8 (Partial-term short-circuits)
- **Severity:** bug
- **Status:** fixed in Phase 2 Task 7 — added
  ``SegString.__iter__`` (and the rest of the sequence protocol)
  that walks to the ground ``str`` and yields chars. The body-position
  ``elem in coll`` goal now succeeds without any change to
  ``_in_iter`` itself.
- **Location:** `clausal/logic/runtime/body_star_unify.py:208-217`
- **Discovered by:** Task 4 of Phase 0
- **Probe:** `probes/probe_F038.py`

**Symptom:** `_in_iter(collection, pair_mode)` returns
``iter(collection)`` for the non-DictTerm branch. `SegString` does not
define `__iter__` (terms.py:449-630 — only `__walk__`,
`__occurs_check__`, `__unify__`, sequence-shaped helpers are absent),
and it is not a `str` subclass (MRO is `(SegString, object)` — see
[[F008]]). So even a trivially ground ``SegString(["abc"])`` raises
``TypeError: 'SegString' object is not iterable`` when used in a
body-position ``elem in coll`` goal — the exception propagates out of
the compiled body code.

By contrast, ground SegList enumerates correctly: ``SegList`` does
define ``__iter__`` (terms.py:337) which delegates to ``to_list()``.
The asymmetry is the C3 SegString blind spot — surfacing here as a
C8 silent-crash.

Per spec vocabulary, "TypeError on a logically-valid call = bug".

**Reproducer:**
```python
from clausal.logic.runtime.body_star_unify import _in_iter
from clausal.terms import SegString

ss = SegString(["abc"])
assert ss.is_ground() and ss.__walk__() == "abc"
try:
    list(_in_iter(ss, pair_mode=False))                # TypeError
except TypeError:
    pass
```

**Expected:** `['a', 'b', 'c']` (parallel to ground SegList) — or, if
the strings-as-lists contract says iteration over a string yields
chars, the walked str routes through `iter("abc")`.
**Actual:** TypeError.

**Notes:** The minimal fix is to walk the collection before iterating
(or add a `SegString.__iter__` that delegates to `__walk__` then
`iter`). Companion to [[F039]] (the partial-term variant), [[F034]]
(output-mode SegString blind spot in the head-position path).

### F039 — `_in_iter` raises on non-ground SegList / SegString

- **Class:** C8 (Partial-term short-circuits)
- **Severity:** bug
- **Status:** fixed in Phase 2 Task 7 — partial-aware
  ``__iter__`` on both SegList (via the F021 fix) and SegString
  (new) yields the concrete prefix from ConcreteSeg / str segments
  in order, skipping VarSeg gaps. ``_in_iter`` was not touched —
  the standard ``iter(collection)`` dispatch now succeeds because
  the Seg* iterators no longer raise.
- **Location:** `clausal/logic/runtime/body_star_unify.py:208-217`
  (via `SegList.__iter__` → `to_list()` at `clausal/terms.py:337` and
  the missing SegString `__iter__` — see [[F038]])
- **Discovered by:** Task 4 of Phase 0
- **Probe:** `probes/probe_F039.py`

**Symptom:** `_in_iter` calls ``iter(collection)`` unconditionally.
For a non-ground SegList this routes through `SegList.__iter__` →
`SegList.to_list()` which raises ``TypeError("SegList is not ground:
...")`` (see [[F021]]). For a SegString it raises regardless of ground
state (see [[F038]]). The body-position ``elem in coll`` goal has no
way to defer or partially enumerate — the TypeError propagates out of
the compiled body code.

A defensible alternative: enumerate the known ConcreteSeg / string
prefix and surface the VarSeg holes as deferred constraints so the
caller can re-attempt after binding. The current behaviour drops a
logically satisfiable goal as an exception.

Per spec vocabulary, "TypeError on a logically-valid call = bug". The
concrete prefix elements are knowable and the goal could succeed on
any of them without committing on the VarSeg holes.

**Reproducer:**
```python
from clausal.logic.variables import Var
from clausal.logic.runtime.body_star_unify import _in_iter
from clausal.terms import SegList, SegString, VarSeg, ConcreteSeg

sl = SegList([ConcreteSeg([1, 2]), VarSeg(Var()), ConcreteSeg([5])])
try:
    list(_in_iter(sl, pair_mode=False))                # TypeError
except TypeError:
    pass

ss = SegString(["a", VarSeg(Var()), "c"])
try:
    list(_in_iter(ss, pair_mode=False))                # TypeError
except TypeError:
    pass
```

**Expected:** Either enumerate the concrete prefix (1, 2, 5 / 'a', 'c')
with deferred-membership semantics on the VarSeg holes, or a typed
soft-failure that the caller can recover from.
**Actual:** TypeError propagates out of the body goal.

**Notes:** Body-position twin of [[F021]] (SegList sequence-protocol
crash on partial terms). [[F038]] covers the ground-SegString case in
this same helper. Pairs with [[F022]] (`__contains__` is silently
incomplete on VarSegs) — note the inconsistent disciplines: `_in_iter`
raises, `__contains__` answers `False`. A coherent fix should pick
one rule and apply it across both.

### F022 — SegList.__contains__ silently incomplete on VarSegs

- **Class:** C8 (Partial-term short-circuits)
- **Severity:** design-gap
- **Status:** fixed in Phase 2 Task 7 — chose the conservative rule:
  return ``True`` when the item is in any ConcreteSeg *or* when no
  ConcreteSeg matches but an unbound VarSeg remains (the VarSeg could
  bind to a list containing the item, so the membership goal is
  satisfiable). Definite ``False`` only when every segment is concrete
  and the item is absent — eliminating the silent-wrong-answer case
  flagged here. The matching SegString rule was added at the same time.
- **Location:** `clausal/terms.py:340-348`
- **Discovered by:** Task 2 of Phase 0
- **Probe:** `probes/probe_F022.py`

**Symptom:** When the SegList is non-ground, `__contains__` walks the
remaining segments and only checks `ConcreteSeg.elements`; it never
checks whether a `VarSeg`'s bound value contains the item. Effect:
`3 in SegList([ConcreteSeg([1,2]), VarSeg(X), ConcreteSeg([4])])`
returns `False` even when `X` could be bound to a list containing 3.

This is silent logical incompleteness: no error, just a wrong answer
in the case where the item *could* be inside a VarSeg.

**Reproducer:**
```python
from clausal.logic.variables import Var
from clausal.terms import SegList, VarSeg, ConcreteSeg

X = Var()
sl = SegList([ConcreteSeg([1, 2]), VarSeg(X), ConcreteSeg([4])])
assert 1 in sl                              # True via ConcreteSeg
assert 4 in sl                              # True via ConcreteSeg
assert (3 in sl) is False                   # silently False; could be in X
```

**Expected:** Either `True` (membership is satisfiable), `None`
(unknown), or a TypeError. Returning a definite `False` is wrong for
the case where X is unbound and 3 could legitimately be assigned.
**Actual:** Definite `False`.

**Notes:** Inconsistent with [[F021]] (the sibling sequence methods
raise instead of silently answering). The combined picture: SegList's
sequence protocol is half "raise on partial" and half "answer wrong
on partial". Either is defensible alone; the mix is the smell.

The spec vocabulary's "wrong answer" definition technically could cover a definite-False return on a partial container where the logical answer is "unknown". Task 2 spec review judged this borderline and kept the design-gap grading because Python's `__contains__` contract on partial terms is genuinely unspecified by the strings-as-lists contract. If a fix in Phase 2 reveals a clear corrective rule, revisit this grading then.

### F024 — SegString.__walk__ raises TypeError on non-str list binding

- **Class:** C8 (Partial-term short-circuits)
- **Severity:** smell
- **Status:** fixed in Phase 2 Task 7 — two-layer fix:
  (1) ``SegString.__init__`` validates that every segment is ``str``
  or ``VarSeg`` at construction time, rejecting malformed bare-int /
  nested-list segments with a typed ``PartialTermError``;
  (2) the ``isinstance(v, list)`` branch in ``__walk__`` validates
  every element is a ``str`` before delegating to ``str.join``, so a
  VarSeg bound to ``[1, 2, 3]`` raises ``PartialTermError("SegString
  VarSeg bound to non-char-list: ...")`` instead of leaking the bare
  CPython ``TypeError`` from ``str.join``.
- **Location:** `clausal/terms.py:493-499`
- **Discovered by:** Task 2 of Phase 0
- **Probe:** `probes/probe_F024.py`

**Symptom:** The `isinstance(v, list)` branch in `SegString.__walk__`
joins the list via `"".join(v)`. This works when every element is a
`str` (including multi-char strings — see notes). If a VarSeg's var
was unified with a list of non-strs (e.g. ints — possible via a
direct `unify(X, [1,2,3], t)` followed by embedding X in a SegString),
the walk raises TypeError from inside `str.join`, propagating out of
`__walk__`. Anything that touches `__walk__` — `is_ground`,
`__eq__`, `__hash__`, `__repr__`, `__unify__` — then blows up.

**Reproducer:**
```python
from clausal.logic.variables import Var, unify, Trail
from clausal.terms import SegString, VarSeg

X = Var(); t = Trail()
unify(X, [1, 2, 3], t)
ss = SegString(["a", VarSeg(X), "b"])
try:
    ss.__walk__()      # TypeError: sequence item 0: expected str instance, int found
except TypeError:
    pass
```

**Expected:** A typed contract violation ("SegString VarSeg bound to
non-char-list"), not a low-level `str.join` exception from deep in
the walk. Better: catch in the walk and fall through to a no-walk
result (keep the VarSeg as opaque).
**Actual:** Raw TypeError from `str.join`.

**Notes:** Multi-char string elements work silently (`["ab","cd"]`
joins to `"abcd"`), which is a *separate* smell — the char-list
contract says every element is 1-char, but the code doesn't enforce
it. Both are smells, not bugs (a malformed SegString construction is
out of contract). Logged for the cleanup pass.

*Task 2 confirmed (no finding):*
- **F029** — `SegList.__occurs_check__` (`terms.py:296-306`) and
  `SegString.__occurs_check__` (`terms.py:543-549`) handle nested
  Seg* recursion correctly. The Python hooks only call
  `occurs_check(var, seg.var)` directly — recursion through the
  bound value is handled by the C-level `do_occurs_check`
  (`_variables.c:913-955`), which derefs the var and then dispatches
  on the bound value's type (list, tuple, or `__occurs_check__`
  protocol). Confirmed for `SegList(VarSeg(Y))` where Y is bound to
  `SegList(VarSeg(X))`, and the SegString analogue: both return True
  when X occurs deep inside. No probe (verified by code path
  inspection plus direct repl check; see Task 2 notes).

### Class C9 — Polymorphic builtin mode matrix

### F050 — `split_with/3` join mode silently drops str parts

- **Class:** C9 (Polymorphic builtin mode matrix)
- **Severity:** bug
- **Status:** fixed in Phase 2 Task 12 — the join branch now feeds
  each part through ``_as_items`` instead of the bug-shape
  ``isinstance(p, list)`` test, so str / list / ground Seg* parts all
  contribute their elements (and a non-sequence part is appended as a
  single element).
- **Location:** `clausal/logic/builtins/lists.py:630-642`
- **Discovered by:** Task 7 of Phase 0
- **Probe:** `probes/probe_F050.py`

**Symptom:** The join (inverse-split) branch interleaves *parts* with
the separator using ``if isinstance(p, list): joined.extend(p)``.  A
part that is a ``str`` — the natural inverse of the split direction,
which *produces* str parts when the input was a str — is silently
skipped: only the separators end up in the joined result.

Round-trip: ``split_with(',', 'a,b,c', P)`` yields ``P = ['a','b','c']``
(three 1-char strs).  Feeding that back in as
``split_with(',', J, ['a','b','c'])`` yields ``J = [',', ',']`` — the
'a', 'b', 'c' parts are dropped because each fails the ``isinstance(p,
list)`` guard.  ``split_with(',', J, ['abc','def'])`` yields ``J =
[',']``.

**Reproducer:**
```python
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
# ... mod loaded ...

J = Var()
for _ in call("split_with", ",", J, ["a", "b", "c"], module=mod):
    assert deref(J) == [",", ","]      # bug: should round-trip to 'a,b,c'
```

**Expected:** Join should re-include str parts (treat them as
list-of-chars under the strings-as-lists contract), or at minimum the
forward and inverse directions should round-trip.
**Actual:** Only ``isinstance(p, list)`` parts are extended; str parts
are silently dropped.

**Notes:** This is a true bug — wrong answer on a satisfiable goal.
The fix is straightforward: replace ``isinstance(p, list)`` with
``isinstance(p, (list, str))`` (or the existing ``_as_items`` helper).
The same module's split-direction branch (lists.py:614-629) correctly
handles str input via ``_as_items``, so the asymmetry is just the
inverse direction's blind spot.  Related to [[F054]] (broader C9
list-vs-str output asymmetry across the file).

### F051 — Every polymorphic list builtin silently fails on ground SegList / SegString

- **Class:** C9 (Polymorphic builtin mode matrix)
- **Severity:** bug
- **Status:** fixed in Phase 2 Task 12 — ``_as_items`` now walks a
  ground SegList/SegString to its concrete list/str and re-enters; a
  non-ground Seg* still returns None. Cascade-closed every gated
  builtin in lists.py and (via shared import) in higher_order.py
  (closes [[F061]]). ``length`` / ``last`` / ``reverse`` previously
  used a bare ``isinstance(_, (list, str))`` test instead of
  ``_as_items`` — switched to ``_as_items`` in the same task.
- **Location:** `clausal/logic/builtins/lists.py:48-57` (the
  ``_as_items`` helper itself), affecting every predicate that gates on
  ``items is not None`` (append, length, member/``in_``, in_check,
  reverse, get_item, take, drop, split_at, msort, sort, last, select,
  permutation, flatten, subtract, intersection, union, list_to_set,
  sum_list, max_list, min_list, zip_, split_with, same_length).
- **Discovered by:** Task 7 of Phase 0
- **Probe:** `probes/probe_F051.py`

**Symptom:** ``_as_items`` accepts only ``list`` or ``str`` and returns
``None`` otherwise.  Ground ``SegList(ConcreteSeg([...]))`` and
``SegString([...])`` walk to a concrete list / str via ``__walk__`` and
are logically equivalent under the SegList / strings-as-lists
contracts, but ``_as_items`` doesn't call ``__walk__`` — it just
returns ``None``.  Every predicate then falls through to ``(_fail,
DONE)`` and yields zero solutions silently on a Seg* input.

Combined with the surrounding non-list / non-str rejection, this means
roughly **20 polymorphic builtins** silently drop satisfiable goals
when handed a Seg* term.  In practice this surfaces whenever a Seg*
value flows from the head/body unification layer (e.g. via
``_build_multi_star_list`` or ``_seg*_unify_gen``) into a downstream
builtin call.

**Reproducer:**
```python
from clausal.logic.solve import call
from clausal.logic.variables import Var
from clausal.terms import SegList, SegString, ConcreteSeg

sl = SegList([ConcreteSeg(["a", "b", "c"])])
ss = SegString(["abc"])
assert sl.is_ground() and sl.__walk__() == ["a", "b", "c"]
assert ss.is_ground() and ss.__walk__() == "abc"

# Both yield zero solutions despite the goals being satisfiable:
assert sum(1 for _ in call("append", sl, "d", Var(), module=mod)) == 0
assert sum(1 for _ in call("in_",    Var(), ss,   module=mod)) == 0
assert sum(1 for _ in call("length", sl,    Var(), module=mod)) == 0
# ... and ~17 others
```

**Expected:** Either walk the Seg* via ``__walk__`` inside
``_as_items`` (preferred — single fix for ~20 call sites), or refuse
Seg* inputs with a type error.  Silent failure on a logically valid
goal is the worst option.
**Actual:** Silent ``(_fail, DONE)``.

**Notes:** The fix is one line: extend ``_as_items`` to walk ground
Seg* terms (e.g. ``if isinstance(val, (SegList, SegString)) and
val.is_ground(): return _as_items(val.__walk__())``).  Non-ground Seg*
is a separate concern — those should arguably defer or refuse rather
than silently fail.

This is the C9 cross-cut companion of the C3 family of SegString
blind-spot findings ([[F031]], [[F032]], [[F034]], [[F040]], [[F041]],
[[F047]]) — the SegList/SegString blind-spot pattern repeats wherever
the runtime tests ``isinstance(val, (list, str))`` without first
considering walked Seg* values.  Logging as one bug across multiple
loci per the spec's "merge same-root-cause findings" guidance.

**Prior-known:** commit 423be48 — "Phase 4: polymorphic list builtins accept strings" introduced the `_as_items` / `_seq_result` helpers and routed all 27 list builtins through them. The plan in `STRING_LIST_UNIFICATION.md` Phase 4 (L709-942) only mentioned `(list, str)` as the accepted types; SegList / SegString unification with builtin consumers was deferred to "Phase 7 (optional)" — Phase 7 added the SegString type but never came back to extend `_as_items`.

### F052 — `sum_list/max_list/min_list` swallow TypeError into silent failure

- **Class:** C9 (Polymorphic builtin mode matrix)
- **Severity:** bug
- **Status:** fixed in Phase 2 Task 12 — each predicate now raises a
  typed clausal ``type_error`` (``number`` for sum_list, ``orderable``
  for max_list / min_list) instead of converting the underlying
  TypeError into a silent ``(_fail, DONE)``. The previous behaviour
  made undefined-on-input indistinguishable from a clean empty
  result.
- **Location:** `clausal/logic/builtins/lists.py:475-479` (sum_list),
  `:493-497` (max_list), `:511-515` (min_list)
- **Discovered by:** Task 7 of Phase 0
- **Probe:** `probes/probe_F052.py`

**Symptom:** Each numeric-reduction predicate wraps the
``sum/max/min`` call in ``try: ... except TypeError: yield (_fail,
DONE); return``.  When the items are not summable / orderable (e.g.
``sum_list("abc", S)`` because ``sum(str, 0)`` raises TypeError, or
``max_list([1, 'a'], M)`` because mixed types are incomparable), the
TypeError is silently converted to logical failure.

This makes a type error indistinguishable from a clean "no solutions"
result.  ``sum_list("abc", S)`` is not a satisfiable goal under any
reasonable interpretation, but the silent failure leaves the user
guessing whether the program failed because the input was wrong or
because the predicate decided there is no answer.

**Reproducer:**
```python
from clausal.logic.solve import call
from clausal.logic.variables import Var

S = Var()
assert sum(1 for _ in call("sum_list", "abc", S, module=mod)) == 0
S = Var()
assert sum(1 for _ in call("sum_list", ["a", "b", "c"], S, module=mod)) == 0
M = Var()
assert sum(1 for _ in call("max_list", [1, "a"], M, module=mod)) == 0
```

**Expected:** Either define sum/max/min on str input meaningfully
(e.g. sum_list-of-str = concatenation), or raise a type error rather
than silently failing.
**Actual:** Silent ``(_fail, DONE)``.

**Notes:** Logged as bug (silent drop of a satisfiable-or-erroneous
goal) rather than design-gap because the user has no signal that the
predicate is undefined on the input — the same shape as a clean
no-solutions result.  ``max_list`` and ``min_list`` happen to succeed
on str input (str chars are orderable), so the asymmetry is also a
documentation gap.

### F061 — `higher_order.py` predicates silently fail on Seg* inputs

- **Class:** C9 (Polymorphic builtin mode matrix)
- **Severity:** bug
- **Status:** fixed in Phase 2 Task 12 — cascade-closed by the
  ``_as_items`` walk-into-Seg* extension that closes [[F051]]. Every
  higher_order predicate imports the shared helper from lists.py, so
  the single Seg*-walk patch fixes all ~16 predicates in one shot.
- **Location:** `clausal/logic/builtins/higher_order.py:62` (maplist/2),
  `:86` (maplist/3), `:113` (include/3), `:140` (exclude/3),
  `:167` (foldl/4), `:202` (take_while/3), `:230` (drop_while/3),
  `:258` (span/4), `:288` (group_by/3), `:324` (sort_by/3),
  `:360` (max_by/3), `:397` (min_by/3), `:434` (filter_map/3),
  `:465` (partition/4), `:504` (tfilter/3), `:542` (tpartition/4) — all
  consume ``items = _as_items(lst_val)`` and fall through to
  ``(_fail, DONE)`` when ``items is None``.
- **Discovered by:** Task 8 of Phase 0
- **Probe:** `probes/probe_F061.py`

**Symptom:** Every higher_order list predicate cracks the input via the
shared ``_as_items`` helper from ``lists.py`` (imported at
higher_order.py:10).  ``_as_items`` rejects ``SegList`` / ``SegString``
and returns ``None`` (see [[F051]] for the root cause and the lists.py
side of this problem).  Each higher_order predicate then gates on
``items is None`` and yields zero solutions silently when handed a
Seg* input.

In practice this surfaces whenever a Seg* value flows out of the
head/body unification layer (e.g. via ``_build_multi_star_list`` or a
``_seg*_unify_gen`` solution) into a higher_order call.

**Reproducer:**
```python
from clausal.logic.solve import call
from clausal.logic.variables import Var
from clausal.terms import SegList, SegString, ConcreteSeg

sl = SegList([ConcreteSeg(["a", "e", "i"])])
ss = SegString(["abc"])
assert sl.is_ground() and ss.is_ground()

# Every higher_order predicate silently drops the satisfiable goal:
assert sum(1 for _ in call("maplist",   is_vowel, sl, module=mod)) == 0
assert sum(1 for _ in call("include",   is_vowel, sl, Var(), module=mod)) == 0
assert sum(1 for _ in call("foldl",     concat,   ss, "", Var(), module=mod)) == 0
assert sum(1 for _ in call("partition", is_vowel, ss, Var(), Var(), module=mod)) == 0
# ... and the other ~12 predicates
```

**Expected:** Either walk the Seg* via ``__walk__`` inside the shared
``_as_items`` (preferred — single fix simultaneously closes this and
[[F051]]), or refuse Seg* inputs with a type error.  Silent failure on
a logically valid goal is the worst option.
**Actual:** Silent ``(_fail, DONE)``.

**Notes:** Same single-line fix as [[F051]] — extend ``_as_items`` to
walk ground Seg* terms.  Logged separately from F051 because the loci
(file-wide impact across ~16 higher_order predicates) and the symptom
surface (higher-order goal silently never invoked) are user-distinct
from the lists.py family even though the root cause is shared.
Cross-links: [[F051]] (the helper itself in lists.py), [[F031]],
[[F032]], [[F034]], [[F040]], [[F041]], [[F047]] (C3 SegString
blind-spot family).

**Prior-known:** commit 39415d6 — "Phase 5: higher-order predicates accept strings" rewrote all 16 higher_order predicates to consume `_as_items` from lists.py; the Seg* gap was inherited from [[F051]]'s root cause and propagated by the import.

### F072 — `char_type/2` Char-bound vs Type-bound mode disagree on non-ASCII

- **Class:** C9 (Polymorphic builtin mode matrix)
- **Severity:** bug
- **Status:** fixed in Phase 2 Task 12 — the Type-bound mode now
  takes a Python path that walks the Basic Multilingual Plane on
  first call (with a per-type cache) for the Unicode-eligible types
  (``alpha`` / ``alnum`` / ``upper`` / ``lower`` / ``print``); the C
  accelerator is kept for the intentionally ASCII-only types
  (``ascii`` / ``control`` / ``digit`` / ``space`` / ``punct``). The
  enumeration and Char-bound test relations now agree on every
  Unicode codepoint up to U+FFFF.
- **Location:** `clausal/logic/builtins/chars.py:76-86` (pre-computed
  ASCII-only enumeration tables); `clausal/logic/builtins/_chars_core.c:128-132`
  (`type_to_chars` populated from 0..127 only); `chars.py:148-158` and
  `_chars_core.c:226-247` (the enumeration paths themselves)
- **Discovered by:** Task 10 of Phase 0
- **Probe:** `probes/probe_F072.py`

**Symptom:** ``char_type/2`` has three modes; they disagree on which
characters are *in* the relation:

1. *Char bound:* the per-codepoint classifier supports the full Unicode
   range (``Py_UNICODE_ISALPHA`` etc. in the C path at
   ``_chars_core.c:165-179``, ``str.isalpha`` etc. in the Python
   fallback at ``chars.py:113``). So ``char_type('α', alpha)`` succeeds.
2. *Char bound, Type unbound:* same classifier, enumerates matching
   types for the given char. So ``char_type('α', T)`` enumerates
   ``[alpha, alnum, lower, print]``.
3. *Type bound, Char unbound:* iterates the pre-computed
   ``_TYPE_TO_CHARS`` / ``type_to_chars`` table, which only contains
   ASCII codepoints. So ``findall(C, char_type(C, alpha), L)`` returns
   only the 52 ASCII letters — ``α`` is silently omitted from the
   enumeration even though it satisfies the relation under mode (1).

Consequence: a Prolog program that uses ``char_type(C, alpha)`` as a
generator and then tests something else on each ``C`` will silently
skip every non-ASCII letter. ``findall`` is incomplete relative to
test-mode membership — the relation is not well-defined.

**Reproducer:** see `probes/probe_F072.py`.

**Expected:** Either (a) restrict the Char-bound modes to ASCII only
(matching the enumeration), or (b) document that Type-bound enumeration
is limited to a fixed alphabet (the ISO-standard practice — but Prolog
systems vary on what that alphabet is).
**Actual:** Char-bound mode supports Unicode; Type-bound mode is ASCII-
only; no documentation of the asymmetry.

**Notes:** Severity is bug per the spec vocabulary — "non-determinism
collapsed silently" applies here: the relation enumerated is a proper
subset of the relation tested. Two fix-shapes:

  * *Cheap:* document the ASCII-only enumeration contract and gate the
    Char-bound modes with the same ASCII restriction (1-line change in
    ``chars.py`` and ``_chars_core.c::py_char_type_find_types``).
  * *Right:* expand ``type_to_chars`` to cover all Unicode general
    categories, lazily (155k codepoints — feasible but memory-heavy).
    Note: ``_chars_core.c:228-234`` already has a dead non-ASCII branch
    that would need fixing (see [[F078]]).

Cross-ref [[F078]] (dead non-ASCII allocation branch in the C path is
*almost* set up for the right fix but uses the wrong PyUnicode kind for
codepoints ≥ 0x100).

### F053 — `length(Var, N)`, `replicate/3`, `same_length` always build list output

- **Class:** C9 (Polymorphic builtin mode matrix)
- **Severity:** design-gap
- **Status:** fixed in Phase 2 Task 12 (per user decision option A —
  input-type wins) — ``replicate(N, '<c>', R)`` now returns a ``str``
  when the element is a 1-char str (the lossless str-shape); the
  output of ``same_length(<str>, X)`` is a fresh ``SegString`` of N
  ``VarSeg`` holes (the natural variable-bearing str shape).
  ``length(L, N)`` output mode has no type hint at the call site —
  documented as list-only and unchanged.
- **Location:** `clausal/logic/builtins/lists.py:210-215` (length
  output mode), `:589-598` (replicate), `:683-697` (same_length)
- **Discovered by:** Task 7 of Phase 0
- **Probe:** `probes/probe_F053.py`

**Symptom:** The output-mode builders for these predicates have no
input-type hint to switch on — they allocate a Python ``list``
unconditionally.  A caller cannot ask for a "str-shaped" fresh
variable, even when the surrounding logic would consume the result as
a str.

Examples (each yields a ``list`` even though a str would be
semantically valid):
- ``length(L, 5)`` → ``L = [Var, Var, Var, Var, Var]`` (list)
- ``replicate(5, 'a', R)`` → ``R = ['a', 'a', 'a', 'a', 'a']`` (list,
  even though all elements are 1-char strs)
- ``same_length("abc", X)`` → ``X = [Var, Var, Var]`` (list)
- ``same_length(X, "abc")`` → ``X = [Var, Var, Var]`` (list)

**Reproducer:**
```python
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref

L = Var()
for _ in call("length", L, 5, module=mod):
    assert type(deref(L)) is list   # not str, even with hint

R = Var()
for _ in call("replicate", 5, "a", R, module=mod):
    assert deref(R) == ["a"]*5      # list, even though all 1-char strs
```

**Expected:** Under "input type wins" the predicate should preserve
the str shape when an adjacent argument carries str typing (e.g.
``same_length("abc", X)`` should arguably bind X to a fresh str-typed
hole).  Under "list is canonical" the docstring should call out that
output-mode is always list.
**Actual:** Always list, undocumented.

**Notes:** This is the C9 mode-matrix mirror of [[F033]] (head-output
mode always builds a list) and [[F042]] (body multi-star unbound-target
always builds SegList).  The information genuinely isn't present at
the call site for ``length(L, N)`` with both vars except N — so a fix
requires either a typed output-mode protocol or a documented
contract.  ``replicate`` and ``same_length`` *do* have type
information available (the element / sibling argument), so could in
principle promote.

**Prior-known:** commit 423be48 — "Phase 4: polymorphic list builtins accept strings" reworked the input side of these predicates via `_as_items` but documented `replicate` and `same_length` as list-output. The `same_length` case in particular has the sibling-type signal available but the commit's design (per `STRING_LIST_UNIFICATION.md` Phase 4 table at L770-787) hard-coded list output for predicates "generates integer lists / numlist"-class — the matrix didn't include `same_length` in that group, so the omission appears unintentional.

### F054 — `_seq_result` asymmetry: list-of-1-char-str input ≠ str-promoted output

- **Class:** C9 (Polymorphic builtin mode matrix)
- **Severity:** design-gap
- **Status:** fixed in Phase 2 Task 12 — resolved per user decision
  option A (**input-type wins**): when input is ``str``, output is
  ``str``; when input is ``list``, output is ``list`` (even if every
  element is a 1-char str — *no* silent promotion). The existing
  ``was_string = isinstance(_, str)`` test already implements this;
  the audit fix is the *contract clarification* plus an aligned
  ``_was_string`` helper for the (also-str-shaped) ground SegString
  case. C9 test ``test_F054_seq_result_input_type_wins`` now codifies
  the option-A symmetry across the 8 predicates in the matrix.
  Lock-in updates: ``tests/test_list_util.py::TestReplicate`` and
  ``tests/fixtures/list_util.seam`` (replicate basic / zero) — both
  previously asserted ``[["x","x","x"]]`` / ``[[]]``, updated to
  ``["xxx"]`` / ``[""]`` per F053 + option A.
- **Location:** `clausal/logic/builtins/lists.py:60-65` (helper) plus
  every call site that derives ``was_string`` from
  ``isinstance(lst_val, str)``: reverse (`:236`), msort (`:314`), sort
  (`:336`), permutation (`:351`), select (`:375`), take (`:532`), drop
  (`:547`), split_at (`:562`), list_to_set (`:461`), subtract (`:404`),
  intersection (`:421`), union (`:438`), append (`:157-159`).
- **Discovered by:** Task 7 of Phase 0
- **Probe:** `probes/probe_F054.py`

**Symptom:** ``_seq_result`` promotes the result back to a str only
when ``was_string`` is True — and ``was_string`` is set strictly from
``isinstance(lst_val, str)``.  A caller that passes ``['a','b','c']``
(a list of 1-char strs, semantically equivalent to ``"abc"`` under the
strings-as-lists contract) gets a list result even when the result is
a valid char sequence:

| call                                  | list input         | str input |
|---------------------------------------|--------------------|-----------|
| ``reverse(.., R)``                    | ``['c','b','a']``  | ``'cba'`` |
| ``msort(.., M)``                      | ``['a','b','c']``  | ``'abc'`` |
| ``sort(.., S)``                       | ``['a','b','c']``  | ``'abc'`` |
| ``take(2, .., T)``                    | ``['a','b']``      | ``'ab'``  |
| ``drop(1, .., D)``                    | ``['b','c']``      | ``'bc'``  |
| ``list_to_set(.., S)``                | ``['a','b','c']``  | ``'abc'`` |
| ``subtract(.., ['b'], R)``            | ``['a','c']``      | ``'ac'``  |
| ``union(.., ['d'], R)``               | ``['a','b','c','d']`` | ``'abcd'`` |

**Reproducer:** See `probes/probe_F054.py` — runs the whole table.

**Expected:** Under "string-preserving + input-type wins", the output
shape should track the input shape consistently.  Either (a) detect a
list of 1-char strs and treat it as str-shaped at the entry, (b)
document that mixed inputs always degrade to list, or (c) provide a
canonical conversion contract.
**Actual:** Asymmetric — only ``isinstance(_, str)`` triggers
promotion; equivalent list inputs stay list.

**Notes:** This is the C9-side of the type-loss family.  Cross-links:
[[F018]] (SegList walk drops str via char expansion), [[F033]]
(head-output mode always list), [[F043]] (body-star helpers lose str
type for list-of-chars stars).  The audit grades all of these as
design-gap because the strings-as-lists contract is genuinely
under-specified for "list of 1-char strs" — ambiguous whether the value
originated as str or list.  Picking a coherent rule is the C1+C9 work.

### F055 — `transpose/2` silently fails on str outer matrix

- **Class:** C9 (Polymorphic builtin mode matrix)
- **Severity:** design-gap
- **Status:** fixed in Phase 2 Task 12 — the outer matrix guard now
  uses ``_as_items`` (accepts list / str / ground Seg*) so
  ``transpose("ab", T)`` succeeds with ``T = [['a'], ['b']]`` (the
  str-as-list-of-1-char-strs interpretation). Inner-row handling is
  unchanged; rows that don't themselves walk to a sequence are
  treated as single-cell rows so the inner / outer treatments are
  symmetric.
- **Location:** `clausal/logic/builtins/lists.py:700-722` (the
  ``isinstance(mat, list)`` gate at :704)
- **Discovered by:** Task 7 of Phase 0
- **Probe:** `probes/probe_F055.py`

**Symptom:** ``transpose`` requires the outer matrix to be a Python
``list`` (``if is_var(mat) or not isinstance(mat, list): return``),
but rows go through ``_as_items`` (lists.py:714) — so a list-of-str
matrix transposes fine, while a str outer matrix silently yields zero
solutions.

| call                              | result             |
|-----------------------------------|--------------------|
| ``transpose([[1,2],[3,4]], T)``   | ``[[1,3],[2,4]]``  |
| ``transpose(['ab','cd'], T)``     | ``[['a','c'],['b','d']]`` |
| ``transpose('ab', T)``            | **0 solutions** (silent fail) |

**Reproducer:**
```python
T = Var()
assert sum(1 for _ in call("transpose", "ab", T, module=mod)) == 0
```

**Expected:** Either (a) accept str outer matrix as a list of 1-char
strs (transposing ``"ab"`` would give ``[['a'], ['b']]`` if a 1-char
str is read as a 1-row matrix, or refused as ambiguous), or
(b) document that the matrix must be a list-shaped container.
Silent failure on a logically-shaped input is the design-gap.
**Actual:** Silent ``return``.

**Notes:** The implementation's docstring says "list of lists" — the
strict outer-list requirement is consistent with that, but the
inconsistency with row-level ``_as_items`` plumbing makes the contract
hard to predict.  Logged as design-gap (matches the spec's "code right,
doc right but contract inconsistent with siblings" pattern).

### F056 — `flatten/2` str-as-atom contract breaks list-of-chars equivalence

- **Class:** C9 (Polymorphic builtin mode matrix)
- **Severity:** design-gap
- **Status:** fixed in Phase 2 Task 12 — flatten now recurses through
  a *nested* ``str`` (and ground ``SegString``) as if it were a list
  of 1-char strs, restoring the strings-as-lists equivalence:
  ``flatten(['ab'])`` and ``flatten([['a','b']])`` now both return
  ``['a','b']``. The top-level container retains the classic Prolog
  contract (a non-list input flattens to its single-element
  wrapper).
- **Location:** `clausal/logic/builtins/lists.py:277-301`
- **Discovered by:** Task 7 of Phase 0
- **Probe:** `probes/probe_F056.py`

**Symptom:** ``flatten`` deliberately treats str as an atom (it only
recurses through ``isinstance(x, list)``).  The docstring at lists.py:282
calls this out explicitly: "Strings are treated as atoms (not flattened
into characters)."  But this means two "equivalent" inputs produce
different outputs:

| input                       | flatten result |
|-----------------------------|-----------------|
| ``[['a','b']]``             | ``['a','b']``  (2 elements) |
| ``['ab']``                  | ``['ab']``     (1 element)  |
| ``[['a','b'], ['c']]``      | ``['a','b','c']`` |
| ``[['ab', 'cd']]``          | ``['ab', 'cd']``  |

Under the strings-as-lists contract ``[['a','b']]`` and ``['ab']``
should be equivalent values — but flatten distinguishes them, breaking
the equivalence in the most user-visible spot in the file.

**Reproducer:** See `probes/probe_F056.py`.

**Expected:** Either (a) recurse through str like list (flatten
``['ab']`` → ``['a','b']``), or (b) the documented contract is the
chosen semantics and the strings-as-lists equivalence is explicitly
suspended here.
**Actual:** (b), but the divergence from sibling builtins (which *do*
treat str as list-of-chars via ``_as_items``) makes it a coherence gap
even with the honest docstring.

**Notes:** Logged as design-gap.  The Prolog ``flatten/2`` would have
the same issue (atoms vs lists), so the contract is defensible — but
the audit's job is to log the C9-class user-visible asymmetry, which
this is.  No fix recommended; the docstring already covers it.  Logged
for the ledger's completeness.

### F062 — `higher_order` string-preserving predicates: list-of-1-char-str input ≠ str-promoted output

- **Class:** C9 (Polymorphic builtin mode matrix)
- **Severity:** design-gap
- **Status:** fixed in Phase 2 Task 12 — resolved per user decision
  option A (**input-type wins**), shared with [[F054]]: list input
  keeps list output, str input keeps str output, no silent promotion
  of list-of-1-char-strs. The current ``was_str = isinstance(_,
  str)`` test in each higher_order predicate already implements this;
  the audit fix is the contract clarification plus the F063
  ``_seq_result`` thread added to the four output-builders.
- **Location:** every higher_order predicate that derives ``was_str``
  from ``isinstance(lst_val, str)`` and wraps the result via
  ``_seq_result``: ``include/3`` (`:117`, `:129`), ``exclude/3`` (`:144`,
  `:156`), ``take_while/3`` (`:206`, `:219`), ``drop_while/3`` (`:234`,
  `:247`), ``span/4`` (`:262`, `:277`), ``partition/4`` (`:469`, `:484`),
  ``tfilter/3`` (`:508`, `:524`), ``tpartition/4`` (`:546`, `:563`).
- **Discovered by:** Task 8 of Phase 0
- **Probe:** `probes/probe_F062.py`

**Symptom:** The ``was_str = isinstance(lst_val, str)`` test only fires
when the input is literally a ``str``.  A semantically equivalent input
(a list of 1-char strs, e.g. ``['h','e','l','l','o']``) is reported as
``was_str=False`` and the result stays as a list — even when every
element of the result is a 1-char str and ``"".join(result)`` would
succeed.

| call                                      | list input              | str input |
|-------------------------------------------|-------------------------|-----------|
| ``include(is_vowel, .., R)``              | ``['e','o']``           | ``'eo'``  |
| ``exclude(is_vowel, .., R)``              | ``['h','l','l']``       | ``'hll'`` |
| ``take_while(is_vowel, .., R)``           | ``[]``                  | ``''``    |
| ``drop_while(is_vowel, .., R)``           | ``['h','e','l','l','o']`` | ``'hello'`` |
| ``partition(is_vowel, .., Y, N)``         | ``(['e','o'], ['h','l','l'])`` | ``('eo','hll')`` |
| ``span(is_vowel, .., Y, N)``              | ``([], ['h','e','l','l','o'])`` | ``('','hello')`` |

**Reproducer:** See `probes/probe_F062.py` — runs every affected
predicate on logically-equivalent inputs and tabulates the asymmetric
output container.

**Expected:** Under "string-preserving + input-type wins", the output
shape should track the input shape consistently.  Either (a) detect a
list-of-1-char-strs at the entry and treat it as str-shaped, (b)
document that mixed inputs always degrade to list, or (c) provide a
canonical conversion contract.
**Actual:** Asymmetric — only ``isinstance(_, str)`` triggers promotion;
equivalent list inputs stay list.

**Notes:** Direct sibling of [[F054]] for the higher_order family.
Cross-links: [[F018]], [[F033]], [[F043]], [[F053]], [[F054]] (the
recurring C1/C9 type-loss family across head, body-star, lists.py and
higher_order.py).  Logged as design-gap because the strings-as-lists
contract is genuinely under-specified for "list of 1-char strs" —
ambiguous whether the value originated as str or list.

### F063 — `maplist/3`, `filter_map/3`, `group_by/3`, `sort_by/3` build list output unconditionally (no `_seq_result`)

- **Class:** C9 (Polymorphic builtin mode matrix)
- **Severity:** design-gap
- **Status:** fixed in Phase 2 Task 12 — each of the four
  output-builders now threads ``was_str = isinstance(lst_val, str)``
  and wraps the result via ``_seq_result``, matching the rest of the
  higher_order family. For ``group_by`` the inner groups (slices of
  the input) are also wrapped so an all-1-char-str group collapses
  to a str; the outer container stays a list (a str cannot contain
  str cells under the strings-as-lists contract). Behaviour
  follows option A (input-type wins): str input with all-1-char-str
  elements collapses to str; list input keeps list output. The
  pre-existing int-codes test (``maplist(char_to_code, "abc", R)``
  → ``[97,98,99]``) is unchanged because ints don't trigger the
  ``_seq_result`` str-promotion guard.
- **Location:** `clausal/logic/builtins/higher_order.py:92-102`
  (maplist/3 — ``results = []``, ``unify(ys, results, trail)``),
  `:440-450` (filter_map/3 — ``kept = []``, ``unify(result, kept, trail)``),
  `:294-313` (group_by/3 — outer ``result: list[list] = []`` and inner
  ``[deref(elem)]`` lists), `:330-349` (sort_by/3 — ``result = [e for _,
  e in keyed]``).
- **Discovered by:** Task 8 of Phase 0
- **Probe:** `probes/probe_F063.py`

**Symptom:** Unlike the string-preserving siblings (include, exclude,
partition, take_while, drop_while, span, tfilter, tpartition) that
honour the str-input shape via ``_seq_result(kept, was_str)``, these
four output-building predicates have no ``was_str`` / ``_seq_result``
path at all.  Their result is hard-coded to a Python ``list`` even when
the input is a str and every result element is a 1-char str (the case
where str promotion would be unambiguous and lossless).

Examples (str input, str-typed result elements, but list output):
- ``maplist(upcase, "abc", R)`` → ``R = ['A', 'B', 'C']``
- ``filter_map(upcase, "abc", R)`` → ``R = ['A', 'B', 'C']``
- ``group_by(vowel_key, "hello", R)`` →
  ``R = [['h'], ['e'], ['l','l'], ['o']]`` (outer AND inner are lists —
  even the inner groups, which are always slices of the input, lose
  str typing)
- ``sort_by(code_key, "cba", R)`` → ``R = ['a','b','c']``

**Reproducer:**
```python
R = Var()
for _ in call("maplist", upcase, "abc", R, module=mod):
    assert type(deref(R)) is list   # not str, even though all-1-char
    break

R = Var()
for _ in call("sort_by", code_key, "cba", R, module=mod):
    assert type(deref(R)) is list   # not str, even though all-1-char
    break
```

**Expected:** Under "string-preserving + input-type wins", str input
with all-1-char-str result elements should produce a str.  For
``group_by``, the inner groups (which are slices of the input) should
preserve the input's str typing.
**Actual:** Hard-coded list output across all four predicates.

**Notes:** This is structurally distinct from [[F062]] — F062 is about
input-side list-vs-str asymmetry on str-preserving predicates;
F063 is that for these four predicates, **even str input degrades to
list output** because they never reach a ``_seq_result`` decision.
Closest sibling is [[F053]] (output-mode builders in lists.py always
list).  Logged as design-gap because the fix needs the same
``was_str``/``_seq_result`` thread that the other predicates already
have — straightforward to apply but currently undocumented as a
gap.  Existing test `test_string_higher_order.py::test_maplist3_char_to_code`
codifies the list output for the int-codes case, which is *correct*
(ints aren't joinable to str); the gap is the 1-char-str-output case
that isn't covered.

**Prior-known:** commit 39415d6 — "Phase 5: higher-order predicates accept strings" applied `_seq_result` to the filter-style predicates (include/exclude/take_while/drop_while/span/partition/tfilter/tpartition) but not to the four output-building ones documented here. The omission is visible in the diff: the maplist/3, filter_map/3, group_by/3, sort_by/3 sections of the commit have plain `results = []` / `unify(ys, results, trail)` without a `was_str` thread.

### F077 — `atom_concat/3` raises instantiation_error for mis-typed bound args

- **Class:** C9 (Polymorphic builtin mode matrix)
- **Severity:** smell
- **Status:** fixed in Phase 2 Task 12 — before the final
  ``instantiation_error`` branch, ``atom_concat/3`` now scans the
  three args for any bound-but-not-atom-shaped value and raises
  ``type_error("atom", NonAtom, "atom_concat/3")``. A user
  ``catch(_, instantiation_error, _)`` handler no longer swallows
  real type errors as instantiation errors.
- **Location:** `clausal/logic/builtins/chars.py:346-393` (the boundness
  inference via ``_atom_to_str`` and the final ``else``)
- **Discovered by:** Task 10 of Phase 0
- **Probe:** `probes/probe_F077.py`

**Symptom:** ``atom_concat/3`` infers boundness by setting
``a_bound = sa is not None`` (and the same for ``b_bound``, ``c_bound``)
where ``sa = _atom_to_str(va) if not is_var(va) else None``. When an
arg is bound but not atom-shaped (``[h,e,l]``, ``1``, ``3.14``,
``foo(x)``), the corresponding ``_bound`` flag is False, so the
fully-instantiated mis-typed call falls through to the final ``else``
at ``chars.py:391-393`` which raises
``instantiation_error("atom_concat/3")``. The correct ISO error is
``type_error(atom, NonAtom)``.

**Reproducer:** see `probes/probe_F077.py`. Every of
``atom_concat([h,e,l], "lo", V)``, ``atom_concat(1, 2, V)``,
``atom_concat(3.14, "x", V)`` raises instantiation_error.

**Expected:** ``type_error(atom, NonAtom)`` for any bound non-atom arg.
**Actual:** ``instantiation_error("atom_concat/3")``.

**Notes:** A user ``catch(_, instantiation_error, …)`` handler will
swallow these — masking real type-error bugs. Fix is local: at
``chars.py:391-393``, before the instantiation_error, check whether
any of ``va``, ``vb``, ``vc`` is bound-but-non-atom and raise
``type_error("atom", first_non_atom, "atom_concat/3")``. The same
pattern likely appears in other atom-accepting predicates that gate on
``_atom_to_str is None`` to mean "unbound" — worth a sweep when
fixing.

*Task 7 confirmed (no finding):*
- **F057** — Task 7 confirmed: the ``_seq_result`` "all 1-char str"
  guard at lists.py:63 is correct for all known callers.  For every
  ``was_string=True`` call site, the items list originates from
  ``list(str_val)`` (str iteration gives 1-char strs) or from
  ``slice/sort/permutations`` of those, so the per-element 1-char check
  is always true and ``"".join(items)`` always succeeds.  The guard is
  defensive against future callers that pass mixed-type items with
  ``was_string=True`` — no current bug.  No probe (static review).
- **F058** — Task 7 confirmed: ``append(Var, Var, Var)`` mode (all
  three unbound) correctly yields zero solutions.  Insufficient input
  to enumerate is the standard Prolog mode-error behaviour; the
  implementation falls through to ``(_fail, DONE)`` cleanly via the
  ``l3_items is not None`` gate at lists.py:177.  No probe.
- **F059** — Task 7 confirmed: the C accelerators
  (``_c_member_find``, ``_c_append_split_find``, ``_c_select_find``,
  ``_c_permutation_find``, ``_c_nth0_find``, ``_c_memberchk_find``)
  use ``PyList_GET_SIZE`` / ``PyList_GET_ITEM`` macros on the
  ``items`` argument with no type check, but every call site passes
  ``items`` from ``_as_items(...)`` which always returns a Python list
  (str input is converted via ``list(val)``).  No type confusion in
  the C path.  No probe (static review of _lists_core.c:128, 168).
- **F060** — Task 7 confirmed: ``get_item`` / ``last`` / ``in_`` /
  ``in_check`` / ``select`` / ``permutation`` element-type output is
  consistently a 1-char str when iterating a str input — confirmed by
  the existing `tests/test_string_list_builtins.py` coverage (see
  ``TestInString.test_enumerate_chars``, ``TestGetItemString``,
  ``TestSelectString``, ``TestPermutationString``).  No new probe
  required; the test suite is the witness.

*Task 8 confirmed (no finding):*
- **F064** — Task 8 confirmed: ``maplist/2``, ``maplist/3`` and
  ``foldl/4`` pass 1-char ``str`` elements to the user's goal when the
  input collection is a ``str``, per the strings-as-lists contract.
  Verified by instrumenting a Python-callable goal via the ``++expr``
  escape (see `probes/probe_F064.py`).  ``foldl/4`` also threads the
  accumulator transparently — a str-typed acc stays str when the goal
  builds str, an int-typed acc stays int when the goal does int
  arithmetic.  No element-coercion bug; the goal-side typing contract
  is honoured.  The C9 issues logged under F061/F062/F063 are all
  *output-shape* and *Seg* input-acceptance* concerns, not element-
  typing concerns.
- **F065** — Task 8 confirmed: ``max_by/3`` and ``min_by/3`` correctly
  bind the result to a 1-char ``str`` when the input is a ``str`` (the
  result is just one of the input elements, dereffed and unified into
  the output var).  No string-preservation issue: ``max_by`` returns a
  single element, not a collection, so ``_seq_result`` has nothing to
  do.  Verified by probe_F063.py control invocation pattern.  No probe.
- **F066** — Task 8 confirmed: the goal-callable check used by every
  higher_order predicate (``callable(goal_val) or hasattr(goal_val,
  '_get_dispatch')``) correctly rejects ``str`` as a goal — ``str``
  instances are not callable in Python 3 and have no ``_get_dispatch``
  attribute.  No risk of mistakenly treating an input str as a goal in
  any of the higher_order entry points.  No probe (static check + REPL
  verification).

### Class C10 — DCG / phrase interaction

### F068 — `phrase/3` silently splits str state-threading arg into chars

- **Class:** C10 (DCG / phrase interaction)
- **Severity:** bug
- **Status:** deferred in Phase 2 Task 14 — see Notes below for the
  unresolved design question.
- **Location:** `clausal/logic/builtins/dcg.py:49-50` (and `:18-19` for
  `phrase/2`)
- **Discovered by:** Task 9 of Phase 0
- **Probe:** `probes/probe_F068.py`

**Symptom:** `phrase/3` is documented in `docs/dcg.md` as both a
character-level DCG entry point (string input is split into chars) *and*
a generic state-threading mechanism where the input list carries an
arbitrary single state value (`phrase(rule, [State0], [State])`). Those
two uses share the same input slot, and `dcg.py:49-50` unconditionally
applies `list(list_val)` when the slot is a `str`. If a user accidentally
drops the brackets in the state-threading form (`phrase(set_name("alice"),
"bob", Rest)` instead of `phrase(set_name("alice"), ["bob"], Rest)`),
the str `"bob"` is silently split to `["b", "o", "b"]` and the rule
head unifies just the first character with what was meant to be the
whole state. The query *succeeds* with a wrong answer (`Rest =
['alice', 'o', 'b']` instead of the intended `Rest = ['alice']`) — no
runtime error, no warning.

**Reproducer:**
```seam
-module(s2, [state2(_s0, _s, S0_2, S_2), set_name(_n, _s0, _s)])
(state2(_s0, _s), [_s]) >> ([_s0])
set_name(_n) >> (state2(_, _n))
```
```python
# Correct call: Rest = ['alice']
for _ in call("phrase", set_name("alice"), ["bob"], rest, module=mod): ...
# User error — Rest comes back as ['alice', 'o', 'b']
for _ in call("phrase", set_name("alice"), "bob", rest, module=mod): ...
```

**Expected:** Either reject str inputs in state-threading shape, or
require the user to opt in to char-splitting (e.g. a separate
`phrase_chars/3` or a wrapping helper). At minimum a wrong-answer
outcome should not be silent.
**Actual:** Silent wrong answer: `Rest = ['alice', 'o', 'b']`.

**Notes:** Root cause is the polymorphism in `phrase/3` itself — the
str-to-chars conversion is the right default for token parsing but
the wrong default for state threading, and the implementation can't
distinguish the two intents from the call shape. Cross-link to
[[F067]] (output-type leak from the same conversion) and to the C9
"input-type wins" cluster ([[F053]], [[F063]]) which the dcg.py
conversion fundamentally contradicts. Graded `bug` because the spec
vocabulary defines `bug` as "wrong answer / silently drops solutions";
this is the dual — silently *produces* a wrong answer.

**Prior-known:** commit c3f8844 — "Phase 3: DCGs accept strings as input" added the unconditional `list(list_val)` conversion at `phrase/2,3` entry. The plan in `STRING_LIST_UNIFICATION.md` Phase 3 (L506-705) considered two designs — a complex `sequence//1`-aware rewrite and a "simpler: convert at phrase boundary" approach — and explicitly chose the latter, observing "the remainder will be a list of chars, not a string — this is acceptable and consistent" (D5 design decision). The state-threading-overload hazard this finding documents was not considered in the plan.

**Deferral (Phase 2 Task 14):** Phase 2 Task 14 closed [[F067]] / [[F069]] /
[[F070]] by removing the eager `list(list_val)` conversion at the
`phrase/2,3` entry and extending `_body_star_unify` to destructure str /
SegString natively (`clausal/logic/runtime/body_star_unify.py`). After
that change `phrase(set_name("alice"), "bob", Rest)` still produces
`Rest = ['alice', 'o', 'b']`: the rule head `[_s0, *_mid]` against the
str `"bob"` now binds `_s0 = "b"`, `_mid = "ob"` (a str slice rather
than a list slice), and the pushback `[_s, *_mid]` builds the same
mixed list once `_s = "alice"` is interleaved with the chars of
`"ob"`. The wrong-answer shape is preserved because the implementation
still cannot distinguish state-threading from char-parsing intent from
the call shape alone — the two readings disagree at the very first
goal step and there is no later vantage point that can pick the right
one. Closing F068 properly requires one of:
 * adding a separate `phrase_state/3` (or syntactic marker) that opts
   out of char-level destructuring at the phrase boundary;
 * adding a per-DCG-rule declaration that records whether the rule
   operates on chars or state items, then dispatching to a strict
   shape-check at the rule head;
 * documenting the hazard and accepting the silent wrong answer as a
   user-error pitfall (parallel to how Prolog's `phrase/3` shares the
   same polymorphism).
None of these fits inside Task 14's "DCG-layer fix" scope; the test
remains `xfail` so the wrong-answer shape is locked in until a future
phase makes the design call.

### F069 — `phrase/2` and `phrase/3` silently fail on SegString input

- **Class:** C10 (DCG / phrase interaction)
- **Severity:** bug
- **Status:** fixed in Phase 2 Task 14 — `phrase/2,3` now apply
  `normalize_seg_input` to walk SegList/SegString to their ground form;
  `_body_star_unify` gained str/SegString arms so the rule-body
  destructuring fires uniformly. The Rest-as-SegString sub-case was
  already cascade-closed by Task 7 (F023).
- **Location:** `clausal/logic/builtins/dcg.py:15-19` (`phrase/2` list
  arg) and `:46-51` (`phrase/3` list arg and rest arg)
- **Discovered by:** Task 9 of Phase 0
- **Probe:** `probes/probe_F069.py`

**Symptom:** `phrase/2` and `phrase/3` test `isinstance(list_val, str)`
to decide whether to split into chars. `SegString` instances — which
walk to a `str` and represent the same logical value — are not
recognised; they fall through into the dispatch path, and the rule
body's `s_in is [t1, ..., tn, *s_out]` cannot unify against a raw
SegString (no list-shape match path for `SegString` at the head-unify
layer either — see [[F031]], [[F032]], [[F034]], [[F040]], [[F041]],
[[F047]]). Net effect: `phrase(rule, ground_SegString)` returns zero
solutions where `phrase(rule, ground_SegString.__walk__())` returns
one. The same hole applies to the `rest_arg` of `phrase/3`: a
SegString-shaped remainder is never accepted, even when ground.

**Reproducer:**
```python
seg = SegString(["h", VarSeg(X)])  # X bound to "i" → walks to "hi"
for _ in call("phrase", hi_rule, seg, module=mod): ...      # 0 solutions
for _ in call("phrase", hi_rule, "hi", module=mod): ...     # 1 solution
```

**Expected:** SegString should be handled by walking-to-str at
`dcg.py:18,49` (parallel to the existing str path) when ground, and
treated as a SegList-style sequence when non-ground (parallel to the
C3 fixes wanted in `_head_list_unify_input`).
**Actual:** Silent failure.

**Notes:** This is the DCG-layer expression of the same C3 SegString
blind spot that runs through the unify/head paths. Logged here under
C10 because the visible call site is `phrase/2,3`, but the root cause
overlaps with the C3 cluster — a fix in `dcg.py` could pre-walk
SegString to str on the way in, *or* defer to fixes in
`_head_list_unify_input` (which would address both). Cross-link to
[[F031]], [[F032]], [[F034]], [[F040]], [[F041]], [[F047]].

**Prior-known:** commit c3f8844 — "Phase 3: DCGs accept strings as input" added the `isinstance(list_val, str)` check that gates the str→char-list conversion; SegString wasn't yet introduced. Phase 7 added SegString (f635551) without revisiting dcg.py.

Fix (Phase 2 Task 14): `phrase/2,3` apply `normalize_seg_input` to
walk Seg* inputs to their ground form (str / list) at entry, so the
existing dispatch path sees a uniform container shape.
`_body_star_unify` (`clausal/logic/runtime/body_star_unify.py`) grew
`str` and `SegString` arms that delegate to `_head_list_unify_input`,
which already destructures both shapes via the Liskov "strings-as-
lists" rule. Rest-as-SegString was already cascade-closed by Task 7
(F023's `SegString.__unify__(list)` walk-and-delegate path);
`test_F069_phrase3_rejects_segstring_rest` passed before this task.

### F067 — `phrase/3` Rest type does not preserve str input shape

- **Class:** C10 (DCG / phrase interaction)
- **Severity:** design-gap
- **Status:** fixed in Phase 2 Task 14 — phrase/2,3 no longer eagerly
  convert str → list at entry; native str destructuring in
  `_head_list_unify_input` / `_body_star_unify` binds Rest to a str
  slice when the input was str.
- **Location:** `clausal/logic/builtins/dcg.py:49-50` (input
  conversion) and the lack of any output-shape record threaded back
  through to `rest_arg`
- **Discovered by:** Task 9 of Phase 0
- **Probe:** `probes/probe_F067.py`

**Symptom:** When the user passes a str to `phrase/3`
(`phrase(g, "abcd", Rest)`), the input is converted to a Python list
of 1-char strs at `dcg.py:49-50`, the rule body threads list-shaped
state, and `Rest` ends up bound to the list slice of the residue
(e.g. `['b','c','d']`) — never a str like `"bcd"`. The contract is
*documented* in `docs/dcg.md:148` (the example asserts
`Rest == ['a', 'b']`), so this is the intended behaviour today. The
design gap is that:

  1. It is inconsistent with the broader "input-type wins" pattern
     emerging from the C1/C9 audit (see [[F018]], [[F033]], [[F042]],
     [[F043]], [[F053]], [[F062]], [[F063]] — every other
     str-preserving builtin tries to preserve str shape on output when
     the input was str).
  2. There is no opt-in to recover str-shaped Rest. A caller wanting
     to chain `phrase/3` calls and keep the residue str-typed for
     downstream str-only predicates has to `"".join(Rest)` manually.

**Reproducer:** `probes/probe_F067.py` — `phrase(tok(V), "abcd", Rest)`
binds `Rest = ['b','c','d']` (list), not `"bcd"`.

**Expected:** Either (a) document the asymmetry in the spec as
intentional and add a sibling `phrase_str/3` that preserves str shape,
or (b) thread a `was_string` flag through the rule body so the final
unification of `rest_arg` can promote a list-of-1-char-strs back to
str (analogous to the `_seq_result` pattern in `lists.py`).
**Actual:** Always list Rest.

**Notes:** Sibling-shaped to [[F053]] (`length/2`, `replicate/3`,
`same_length/2` always build list output) and [[F063]] (higher_order
predicates without `_seq_result`). Logged as design-gap rather than
bug because the current behaviour is *documented* — the gap is the
inconsistency with the rest of the audit's emerging "input-type wins"
contract.

**Prior-known:** commit c3f8844 — Phase 3's plan in `STRING_LIST_UNIFICATION.md` Phase 3 D5 explicitly chose the list-Rest behaviour ("the remainder will be a list of chars, not a string — this is acceptable and consistent"). The contract was documented; the design-gap is the inconsistency with `_seq_result` / `_as_items` plumbing landed later in Phase 4 (commit 423be48).

Fix (Phase 2 Task 14): the eager `list(list_val)` conversion at
`phrase/2,3` entry is removed. Strings flow into the dispatch
unchanged, and the existing `_head_list_unify_input` /
`_body_star_unify` arms destructure str natively (str slicing returns
str), so `Rest` is bound to the natural str slice. The
`docs/dcg.md:148` example and the `test_phrase3_string_remainder`
lock-in in `tests/test_dcg.py` were updated to assert
`Rest == "XY"` rather than `["X", "Y"]`. The fix slots into the
broader "input-type wins" pattern (parallel to [[F053]] / [[F063]] /
[[F018]] / [[F033]] / [[F042]] / [[F043]] / [[F070]]) without any new
type-source plumbing — the str shape survives because the runtime
helpers already pass str through without conversion.

### F070 — `sequence//1` drops str type across every binding mode

- **Class:** C10 (DCG / phrase interaction)
- **Severity:** design-gap
- **Status:** fixed in Phase 2 Task 14 — every binding mode now
  preserves str type per the input-type-wins rule (Mode A returns str
  slice, Mode B str concat when both inputs are str, Mode C builds
  `SegString`, Mode D walks SegList/SegString to its ground form).
- **Location:** `clausal/logic/builtins/dcg.py:73-116`
- **Discovered by:** Task 9 of Phase 0
- **Probe:** `probes/probe_F070.py`

**Symptom:** `sequence//1` (`sequence/3` builtin) asserts
`S0 = List ++ S` across four binding modes; every mode produces a
list-typed output even when the inputs are str:

- **Mode A** (S0 bound to str, S unbound): `dcg.py:90-98` converts
  `s0_val = list(s0_val)` and binds `s = s0_val[n:]` — a list slice.
  `phrase`-style str input → list output S.
- **Mode B** (S bound to str, S0 unbound): `dcg.py:99-107` builds
  `expected = lst_val + s_val` where `lst_val` was eagerly converted
  to list at `:86`. Result S0 is always a list (or raises if
  `lst_val` is list and `s_val` is str of unequal types — masked by
  the eager conversion).
- **Mode C** (both unbound): `dcg.py:108-115` builds a `SegList` with
  `ConcreteSeg(lst_val)` and `VarSeg(s_val)`. Even when `lst` was a
  `str`, the output is `SegList`, not `SegString`.
- **Mode D** (`lst` is `SegList`/`SegString`): unsupported. `dcg.py:81`
  guards `not isinstance(lst_val, (list, str))` and silently fails.

**Reproducer:** `probes/probe_F070.py` — exercises all four modes.
Examples:
```python
# Mode A: lst="ab", S0="abXY", S=Var → S = ['X','Y'] (not "XY")
# Mode B: lst="ab", S0=Var,    S="XY"  → S0 = ['a','b','X','Y']
# Mode C: lst="ab", S0=Var,    S=Var   → S0 = SegList([ConcreteSeg(['a','b']),
#                                                       VarSeg(...)])
# Mode D: lst=SegString("ab")           → fail
```

**Expected:** Modes A/B should produce str output when both inputs
are str (input-type wins). Mode C should build a `SegString` when
`lst` is a `str`. Mode D should accept ground SegString/SegList by
walking to a comparable list/str (parallel to the [[F069]] fix).
**Actual:** Every output mode hard-codes list/SegList/fail.

**Notes:** Direct C10 analogue of [[F053]] (`length/2`, `replicate/3`)
and [[F063]] (`maplist/3`, `filter_map/3` etc.) — output builders
that never reach a `_seq_result`-style decision. Mode-D failure
shares root cause with [[F069]] / the C3 SegString cluster. Logged
as design-gap (matches the F053/F063 grading).

**Prior-known:** commit c3f8844 — "Phase 3: DCGs accept strings as input" added the original `sequence//1` str-handling, and commit 5fcade4 — "fix: wire up SegList in Sequence//1 for both-unbound S0/S case" landed the *Mode C* branch this finding documents. The 5fcade4 commit description acknowledges: "SegList Phases 1-4 were complete but Phase 5 (builtin integration) was interrupted by OOM. This adds the missing else branch in _sequence__3: when both S0 and S are unbound, build SegList…" — the OOM-interrupted Phase 5 mention and the file `todo/SEQUENCE_BOTH_UNBOUND.md` that was deleted in 5fcade4 both indicate the str-vs-SegList branching was a known gap; the fix landed the SegList branch but did not introduce a parallel SegString branch (Phase 7's SegString was introduced in f635551, which came after 5fcade4 in calendar time but did not revisit dcg.py).

Fix (Phase 2 Task 14): `_sequence__3` rewritten to preserve input
type across all four modes.
 * `normalize_seg_input` walks ground SegList / SegString inputs at
   entry so Mode D succeeds via the existing list / str arms.
 * Mode A (S0 bound to str, S unbound): the prefix check normalises
   both sides to list for the equality test but the slice `s0_val[n:]`
   is bound as-is — a str slice when S0 is str.
 * Mode B (S0 unbound, S str/list): when both `lst` and `S` are str
   the concatenation is built as str; otherwise both are normalised
   to list (input-type-wins is decided per-mode by the inputs that
   pin the type).
 * Mode C (both unbound, str `lst`): builds a `SegString` with the
   ground `lst` prefix and a `VarSeg` for the unbound tail, instead
   of the previous list-shaped `SegList`. The non-str case keeps the
   prior SegList behaviour.

### Class C11 — Trail/backtracking around partials
*(none yet)*

### Class C12 — Char representation drift

### F073 — `char_code/2`, `atom_codes/2`, `number_codes/2` leak raw `ValueError` for out-of-range codes

- **Class:** C12 (Char representation drift)
- **Severity:** bug
- **Status:** fixed in Phase 2 Task 3
- **Location:** `clausal/logic/builtins/chars.py:190`
  (``char_code`` ``chr(vn)``), `:323` (``atom_codes`` ``chr(e)`` in
  the codes-to-atom branch), `:571` (``number_codes`` ``chr(e)``)
- **Discovered by:** Task 10 of Phase 0
- **Probe:** `probes/probe_F073.py`

**Symptom:** ``chr(n)`` raises Python ``ValueError`` for ``n < 0`` or
``n >= 0x110000``. None of the three call sites guards the call:

  * ``char_code(V, -1)`` *is* guarded (``chars.py:187`` raises
    ``type_error(integer, vn)``), but ``char_code(V, 0x110000)`` is not.
  * ``atom_codes(V, [-1])`` and ``atom_codes(V, [0x110000])`` reach
    ``chr(e)`` directly — only the ``isinstance(e, int)`` gate fires
    (``chars.py:321``).
  * ``number_codes`` has the same shape at ``chars.py:571``.

The raw ``ValueError`` propagates through the trampoline as an
uncaught Python exception — it is *not* an ISO ``error/2`` term, so
``catch/3`` in Prolog cannot intercept it.

**Reproducer:** see `probes/probe_F073.py`.

**Expected:** ``representation_error(character_code)`` (or
``type_error(character_code, N)``) — a proper Prolog error term.
**Actual:** ``ValueError: chr() arg not in range(0x110000)``.

**Notes:** This is the C12-drift surface for the int↔chr boundary: the
int-code domain is wider than the str char domain (negative ints and
``>= 0x110000``) and the boundary is unguarded. Fix is local — wrap
each ``chr(...)`` site with a range check that raises the proper
LogicException, or guard the input list / int up-front. Should also
sweep ``number_chars`` for the symmetric concern (it parses via
``int()``/``float()`` which already raise on invalid input — already
caught at ``chars.py:528-531``; the issue is specific to the codes
form).

Fixed in Phase 2 Task 3 — added ``0 <= code < 0x110000`` range guards
around ``chr()`` in ``char_code/2``, ``atom_codes/2``, ``number_codes/2``.
Out-of-range codes now fail logically (zero solutions) instead of leaking
Python ``ValueError``. All 6 parametrized F073 tests pass; pre-existing
suite unchanged (7749 passing).

*Task 1 confirmed (no finding):*
- **F013** — A Var bound to a non-Var, non-single-char-PyUnicode dereffed element (e.g. int, list, tuple) does not unify when placed inside a list against the equivalent `str`. The C path requires the dereffed element to be either an unbound Var (allocate substring & bind) or a PyUnicode of exactly 1 code point. This is consistent with [[F006]]: the C path binds chars as 1-char `str`, never as int codes. See `probes/probe_F013.py`. Spec C12 notes this is the intended contract; the broader char-aware-builtin audit is left to later tasks.

### Class C13 — Type-check predicates

**Answer matrix from `probes/probe_F080.py`** — each cell is whether the
type-check builtin succeeds (T) / fails (F) / is not registered (UNDEF)
for the input on the left:

| input                              | is_list | is_chars | is_str | string | atom | atomic | var | nonvar | ground | compound | callable_ |
|------------------------------------|:-------:|:--------:|:------:|:------:|:----:|:------:|:---:|:------:|:------:|:--------:|:---------:|
| `"abc"`                            | F       | T        | T      | UNDEF  | F    | UNDEF  | F   | T      | T      | F        | T         |
| `["a","b","c"]`                    | T       | T        | F      | UNDEF  | F    | UNDEF  | F   | T      | T      | F        | F         |
| `""`                               | F       | T        | T      | UNDEF  | F    | UNDEF  | F   | T      | T      | F        | T         |
| `[]`                               | T       | T        | F      | UNDEF  | F    | UNDEF  | F   | T      | T      | F        | F         |
| `SegList([VarSeg(X)])` (unbound)   | F       | F        | F      | UNDEF  | F    | UNDEF  | F   | T      | **T**  | F        | F         |
| `SegString(["a",VarSeg(Y)])` (unbound) | F   | F        | F      | UNDEF  | F    | UNDEF  | F   | T      | **T**  | F        | F         |
| `Var()` (unbound)                  | F       | F        | F      | UNDEF  | F    | UNDEF  | T   | F      | F      | F        | F         |

Bolded cells are the surprising answers driving findings below.

### F083 — `ground/1` returns True for SegList / SegString with unbound VarSeg

- **Class:** C13 (Type-check predicates)
- **Severity:** **bug**
- **Status:** fixed in Phase 2 Task 9 — ``_is_ground_py`` now has
  explicit ``SegList`` / ``SegString`` branches and recurses into
  ``VarSeg.var``; the C-accelerated ``_is_ground`` is wrapped in
  ``clausal/logic/builtins/_helpers.py`` so any ``SegList`` /
  ``SegString`` is short-circuited to the Python implementation
  before reaching ``c_is_ground``. The C function itself remains
  Seg*-blind but is no longer ever invoked on those shapes from
  the helper path.
- **Location:** `clausal/logic/builtins/_helpers.py:93-110` (Python
  fallback) and `clausal/logic/variables/_variables.c:1933-2038`
  (``c_is_ground``)
- **Discovered by:** Task 11 of Phase 0
- **Probe:** `probes/probe_F080.py`

**Symptom:** Both the Python fallback ``_is_ground_py`` and the C
implementation ``c_is_ground`` enumerate the known container shapes
(list, Compound, KWTerm, PredicateMeta, term-instance) and fall
through to ``return 1`` (True) for any other object — including
``SegList`` and ``SegString``. The Var living inside a ``VarSeg`` is
never visited.

Concrete consequence: with ``X = Var()``,
``ground(SegList([VarSeg(X)])) == True``, even though the SegList is
explicitly a term-with-a-hole. The same is true for ``SegString``.
This contradicts ``ground/1``'s entire purpose — it is the canonical
test for "no unbound Vars anywhere in the term" — and contradicts the
companion behaviour of every Seg*-aware builtin in the C3 cluster.

The audit matrix also shows the related ``nonvar(SegList([VarSeg(X)]))``
is True, which is *consistent within the type-check layer* (Seg* is
not itself a Var) but inconsistent with ground/1's documented
recursive definition.

**Reproducer:** see `probes/probe_F080.py`. The asserts cover both
``SegList`` and ``SegString`` shapes. Minimal:

```python
from clausal.logic.variables import Var
from clausal.terms import SegList, VarSeg
from clausal.logic.builtins._helpers import _is_ground

X = Var()
assert _is_ground(SegList([VarSeg(X)])) is False     # FAILS — returns True
```

**Expected:** ``_is_ground`` walks Seg* segments and recurses into
``VarSeg.var``.
**Actual:** Seg* falls through the "unknown container" branch and
silently reports ground.

**Notes:** This is a real correctness bug (severity: bug) because
downstream predicates that gate on ``ground/1`` before, say, hashing
or indexing into a Var-keyed dict, will treat a Seg*-with-hole as
fully ground and crash later when they try to use the dereffed
value. The fix has two layers:

  1. Add ``SegList``/``SegString`` cases to ``_is_ground_py`` at
     `clausal/logic/builtins/_helpers.py:93-110`.
  2. Mirror in ``c_is_ground`` at
     `clausal/logic/variables/_variables.c:1933-2038` — register the
     two Seg* types alongside the existing ``Compound_type`` /
     ``KWTerm_type`` registration in ``_register_term_types``.

Cross-link with C3 cluster: [[F020]], [[F024]], [[F041]] all flag
Seg*-blind builtins. C13 adds ``ground/1`` to that list. Probably
also surfaces in any builtin that uses ``_is_ground`` as a fast
pre-check before dispatch (search ``_helpers._is_ground`` consumers).

**Prior-known:** commit eb33bfb — "fix: address 8 review issues in C predicate helpers" reworked `c_is_ground` (Issue 1: "Fix c_is_ground dataclass bug: fall back to py_term_field_names for non-PredicateMeta dataclass instances instead of assuming ground") and added defensive fall-throughs without registering SegList/SegString — the same review touched this function and the Seg* gap was not flagged. The 8625f3e perf commit subsequently consolidated more lazy caches in the same file. Same root-cause family as [[F092]] / [[F093]] / [[F094]] — none of the Seg* registrations have ever been added.

### F080 — `is_list/1` rejects strings while every other list builtin accepts them

- **Class:** C13 (Type-check predicates)
- **Severity:** design-gap
- **Status:** fixed in Phase 2 Task 9 — user chose **option A** on
  2026-05-25 (make ``is_list`` polymorphic). ``is_list/1`` now
  accepts ``list`` and ``str`` (and ground ``SegList`` / ``SegString``
  whose ``walk`` resolves to one of those). The lock-in test
  ``test_is_list_string_still_fails`` in
  ``tests/test_string_list_builtins.py`` was renamed to
  ``test_is_list_string_now_succeeds`` with the inverted assertion;
  the strings-as-lists doc snippet in
  ``tests/fixtures/docs/strings_as_lists_examples.seam`` and the
  type-checking table in ``docs/strings_as_lists.md`` were updated to
  match. The ISO conformity fixtures (``iso_type_checking.seam``
  and its golden ``.pl``) only test ``is_list`` against lists and
  atom symbols, so they were unaffected by the contract change.
- **Location:** `clausal/logic/builtins/type_checks.py:106-110`
- **Discovered by:** Task 11 of Phase 0
- **Probe:** `probes/probe_F080.py`

**Symptom:** ``is_list/1`` is a strict ``isinstance(_, list)`` check —
``is_list("abc")`` fails, ``is_list("")`` fails. Yet the rest of the
"list" builtin layer happily accepts ``str`` as a character sequence
(``in_/2``, ``length/2``, ``append/3``, ``msort/2``, ``reverse/2``,
``maplist/N``, ``in_/2``, …) as confirmed by the strings-as-lists
work tracked in [[F018]], [[F033]], [[F042]], [[F043]], [[F053]],
[[F062]], [[F063]], [[F070]]. The library exposes a *separate*
``is_chars/1`` (`type_checks.py:113-117`) that returns True for both
``list`` *and* ``str`` — but every list-flavoured builtin uses ``str``
inputs at runtime without ever asking ``is_chars`` first.

The contract the audit needs to flag: a user who writes
``foo(X) <- is_list(X), maplist(p, X, Y)`` will see ``foo("abc")``
fail, but ``maplist(p, "abc", Y)`` succeed. The two type-tests
disagree, and there is no documented rule for which one a polymorphic
builtin should respect.

**Reproducer:** see `probes/probe_F080.py`. The asserts at the bottom
pin down ``is_list("abc") == F`` and ``is_chars("abc") == T``.

**Expected:** A documented rule — either ``is_list`` becomes
polymorphic (matching every list builtin) or every list builtin is
explicitly typed to reject ``str`` (matching ``is_list``). The current
state leaves callers guessing.
**Actual:** ``is_list`` is strict, the list-flavoured builtins are
polymorphic, the two contracts disagree.

**Notes:** ``tests/test_string_list_builtins.py:405`` already pins down
``is_list("hello")`` returning False as the *intended* behaviour ("exact
type test") — so the test suite has codified the inconsistency rather
than resolved it. The fix lives at the contract level (pick one), not
at the call site. Logged as design-gap (parallels [[F067]]: documented
behaviour that contradicts the broader strings-as-lists contract).

### F081 — `string/1` is not registered; only `is_str/1` exists

- **Class:** C13 (Type-check predicates)
- **Severity:** design-gap
- **Status:** fixed in Phase 2 Task 9 — ``string/1`` is now
  registered as the ISO/SWI-named alias of ``is_str/1``; both
  succeed on ``str`` and on ground ``SegString``. The misleading
  ``is_str`` docstring (which read ``atom(X) — succeeds if X is a
  string (Prolog atom).``) was rewritten so the name and the
  description agree.
- **Location:** `clausal/logic/builtins/type_checks.py:29-34` (the
  ``is_str/1`` registration is the only string-type test)
- **Discovered by:** Task 11 of Phase 0
- **Probe:** `probes/probe_F080.py`

**Symptom:** There is no ``string/1`` builtin. ``call("string", "abc",
module=mod)`` raises ``KeyError`` because
``get_builtin_predicate("string", 1, db)`` returns ``None``. The
matching test is registered under the name ``is_str/1`` instead.

This is at odds with two reference points:

  1. **ISO Prolog / SWI** expose ``string/1`` as a stable name for
     "is this a Prolog string?". A user-port from SWI will silently
     fail to find ``string/1``.
  2. **The internal type table** ``_check_type`` in the *same file*
     (lines 137-142) accepts ``"atom"``, ``"string"``, ``"str"`` as
     synonyms for the same Python-str check — so ``must_be(string, X)``
     works, but ``string(X)`` does not.

The matrix at the top of this section also shows that the docstring
of ``_atom__1`` at `type_checks.py:31` describes itself as
``atom(X) — succeeds if X is a string (Prolog atom).`` even though the
function is registered under the *different* name ``is_str/1`` and a
separate ``atom/1`` registration at line 37 implements the
"zero-arity PredicateMeta" check. Three names, two semantics, one
docstring that mixes them up.

**Reproducer:** see `probes/probe_F080.py`. The asserts include
``_check(mod, "string", "abc") == "UNDEF"`` and
``_check(mod, "is_str", "abc") == "T"``.

**Expected:** Register ``string/1`` as an alias for ``is_str/1`` (and
fix the misleading docstring). Optionally surface a deprecation note
on ``is_str`` if the audit wants to standardise on the ISO name.
**Actual:** ``string/1`` is undefined; ``must_be/2`` calls it
``"string"`` but the standalone test is called ``"is_str"``.

**Notes:** Cross-link with [[F082]] (atomic/1 also missing) — both
look like incomplete porting of the ISO type-check family. The
docstring fix is independent of the alias decision.

### F082 — `atomic/1` is not registered

- **Class:** C13 (Type-check predicates)
- **Severity:** design-gap
- **Status:** fixed in Phase 2 Task 9 — ``atomic/1`` is now
  registered. Accepts ``str``, ``int``, ``float``, ``bool``,
  ``None``, and zero-arity ``PredicateMeta`` classes; rejects Var,
  Compound, KWTerm, term-instance, ``list``, ``SegList``, and
  ``SegString`` (every Seg* shape is structurally compound).
- **Location:** `clausal/logic/builtins/type_checks.py` (no
  ``@_builtin("atomic", 1)`` registration)
- **Discovered by:** Task 11 of Phase 0
- **Probe:** `probes/probe_F080.py`

**Symptom:** ``atomic/1`` is a standard Prolog type-check that succeeds
for any term that is not a Var and not compound — atoms, numbers,
strings, and the empty list (in ISO).  No such builtin is registered
in ``type_checks.py``. ``call("atomic", "abc", module=mod)`` raises
``KeyError``.

The audit's input matrix can't even probe this row meaningfully — the
"atomic" column is ``UNDEF`` everywhere. Users porting from any
Prolog reference will see ``atomic(X)`` fall through to "predicate not
defined" rather than the expected silent True/False.

**Reproducer:** see `probes/probe_F080.py`. The asserts include
``_check(mod, "atomic", "abc") == "UNDEF"``.

**Expected:** Register ``atomic/1`` as ``(not is_var)`` AND
``(not compound)`` — should accept str, int, float, bool, None, and
zero-arity PredicateMeta classes; should reject Compound, KWTerm,
list, dict, term-instances with fields, ``SegList``/``SegString`` with
any segment.
**Actual:** ``atomic/1`` is undefined.

**Notes:** Cross-link with [[F081]] (string/1 missing) — same root
cause (incomplete ISO porting). Implementation is a 5-liner: deref,
reject Var, reject compound shapes, succeed.

### F084 — `callable_/1` says every Python str is callable

- **Class:** C13 (Type-check predicates)
- **Severity:** smell
- **Status:** fixed in Phase 2 Task 9 — ``callable_/1`` is now a
  db-builtin. A bare ``str`` succeeds only when it (a) passes
  ``str.isidentifier`` *and* (b) names a predicate registered in
  the current module — user clauses, dispatch table, builtins, or
  ``module_dict`` PredicateMeta entries. Compound, KWTerm,
  term-instance, and ``PredicateMeta`` classes continue to succeed
  unchanged. The conformity test in
  ``tests/conformity/iso_type_checking.seam`` (and its golden
  ``.pl``) gained a *callable: registered predicate name* case and
  a *callable: arbitrary string fails* counter-case to pin down
  the tightened contract.
- **Location:** `clausal/logic/builtins/type_checks.py:92-103`
- **Discovered by:** Task 11 of Phase 0
- **Probe:** `probes/probe_F080.py`

**Symptom:** ``callable_/1`` succeeds whenever the dereffed term is a
``str`` (line 98: ``isinstance(x_val, (str, Compound, KWTerm))``).
That includes arbitrary strings like ``"this is not a predicate
name"`` or even the empty string ``""``. In Prolog tradition
``callable/1`` should succeed for "an atom or a compound" — strings
specifically may or may not be callable depending on whether they
name a registered predicate.

The matrix shows: ``callable_("abc") == T``, ``callable_("") == T``,
``callable_(["a","b","c"]) == F``. So a *string of one char* is
considered callable but a *one-element list* is not — and neither
form is actually a predicate name.

**Reproducer:** see `probes/probe_F080.py`. The asserts include
``callable_("this is not a predicate") == "T"``.

**Expected:** Either restrict to strings that resolve to a registered
predicate (expensive — needs the DB), or document the laxer
``"any str is callable"`` semantics so users know not to rely on
``callable_/1`` as a guard before ``call/N``.
**Actual:** Any str trivially succeeds; the predicate is effectively
``isinstance(x, (str, Compound, KWTerm, term-instance))``.

**Notes:** Logged as smell rather than bug because the lax semantics
match SWI's ``callable/1`` (which also says any atom is callable, even
unknown ones). What the audit wants to flag is the *naming*: the
trailing underscore in ``callable_`` is the only signal that this is
not ISO ``callable/1`` — and the relaxed contract isn't documented
anywhere. Cross-link with [[F081]]/[[F082]] (incomplete porting of
the ISO type-check family).

*Task 11 confirmed (no finding):*
- **F085** — Task 11 confirmed: ``var/1`` and ``nonvar/1`` behave
  correctly for the matrix row-set. ``var(Var()) == T``,
  ``nonvar(Var()) == F``, and ``var/nonvar`` flip for every bound
  input. ``var(SegList([VarSeg(unbound)])) == F`` is *consistent
  within the type-check layer* (Seg* is not itself a Var) — though
  see [[F083]] for the ground/1 contradiction the same row exposes.
  No probe (covered by `probes/probe_F080.py`).
- **F086** — Task 11 confirmed: ``compound/1`` correctly rejects
  ``str``, ``list``, ``[]``, ``""``, and an unbound ``Var`` (matrix
  shows F for every row). The contract "compound = ``Compound`` or
  ``KWTerm`` with arity > 0, or a term-instance with field count >
  0" is enforced at `type_checks.py:78-89`. Note that ``compound``
  reports False for ``SegList([VarSeg(X)])`` and
  ``SegString(["a",VarSeg(X)])`` — these are compound-shaped *under
  the C3 contract* but ``type_checks.py`` doesn't know about Seg*,
  so the answer is consistent with the broader Seg*-blind C13 layer
  (same root cause as [[F083]]; not separately flagged). No probe
  (covered by `probes/probe_F080.py`).
- **F087** — Task 11 confirmed: ``atom/1`` (zero-arity PredicateMeta
  check) is *not* confused by ``str`` inputs — ``atom("abc") == F``
  for every str in the matrix. The misleading docstring at
  ``type_checks.py:31`` ("atom(X) — succeeds if X is a string (Prolog
  atom)") is on the wrong function (it documents ``is_str``, not the
  ``atom`` defined four lines below it) — see [[F081]] for the
  docstring/name confusion finding. Behaviour itself is correct. No
  probe (covered by `probes/probe_F080.py`).

### Class C14 — Term inspection drift

### F088 — `unpack` (=..) on a non-empty list yields `[".", ]` with no args

- **Class:** C14 (Term inspection drift)
- **Severity:** bug
- **Status:** fixed in 2026-06-13 follow-up — ``_args_list_py`` and
  the C twin ``py_args_list`` now decompose a non-empty list as the
  cons-cell ``[head, tail]`` (where ``tail`` is the rest of the
  list); empty list returns ``[]`` (the nil atom has no args). Str
  inputs follow the same shape with str-typed head and tail (Liskov
  symmetry with the list case). User decision 2026-06-13: ISO-named
  inspection predicates follow ISO Prolog cons-cell semantics; the
  ``unpack/2`` round-trip ``T =.. L, T =.. L2`` now recovers
  ``L = L2`` for list and str inputs.
- **Location:** `clausal/logic/builtins/inspection.py:159-177`
  (the decomposition branch in ``_univ__2``) consuming
  `clausal/logic/builtins/_helpers.py:75-83` (`_args_list_py`) and the
  C twin at `clausal/logic/variables/_variables.c:2311-2363`
  (`py_args_list`)
- **Discovered by:** Task 12 of Phase 0
- **Probe:** `probes/probe_F088.py`

**Symptom:** ``unpack(["a","b","c"], L)`` succeeds with ``L = ["."]``
— the functor name with **no args**.  The implementation calls
``_functor_name(["a","b","c"]) == "."`` (the cons-cell functor) and
concatenates it with ``_args_list(["a","b","c"])`` — but ``_args_list``
falls through to ``return []`` for every Python ``list`` input.  The
Python fallback at ``_helpers.py:75-83`` and the C version at
``_variables.c:2362-2363`` agree: lists are not unpacked.

Same call also makes the round-trip property of ``=..``
non-recoverable: ``T =.. L, T =.. L2`` no longer produces ``L = L2``
when the original term is a list — ``L`` becomes ``["."]`` and the
reconstruction step yields the atom ``"."``, losing every element.

**Reproducer:**
```python
from clausal.logic.builtins import get_builtin_dispatch
from clausal.logic.variables import Var, Trail, deref
from clausal.logic.trampoline import StepGenerator, solutions

L = Var()
disp = get_builtin_dispatch("unpack", 2, None)
sols = solutions(StepGenerator(disp, None, None, None,
                               ["a", "b", "c"], L, Trail()),
                 snapshot=lambda: deref(L))
assert sols == [["."]]
```

**Expected:** Either honour cons-cell semantics
(``L = [".", "a", ["b", "c"]]``) consistent with ``functor/3``
reporting arity 2, or honour strings-as-lists (``L = ["a", "b", "c"]``
— atom-univ shape but element-typed).  Either choice is defensible;
the current shape is neither.
**Actual:** ``L = ["."]`` — functor name only, args dropped.

**Notes:** ``functor/3`` on the same input reports
``("." , 2)`` (the arity *is* 2), so the inconsistency is internal to
the inspection family — see [[F089]] for the cross-predicate angle and
[[F091]] for the matching ``arg/3`` story.  Fix is local to
``_args_list_py`` / ``py_args_list``: add the missing
``isinstance(term, list)`` branch.  Note the helper's default value
also drives ``=..`` on every unrecognised term (e.g. a bare ``True``
or a bound int) — those silently produce ``[<functor-name>]`` too,
but those are zero-arity per ``functor/3`` so the disagreement only
surfaces for lists today.

### F090 — `arg(N, "abc", X)` silently fails for every N

- **Class:** C14 (Term inspection drift)
- **Severity:** bug
- **Status:** fixed in 2026-06-13 follow-up — ``_nth_arg_py`` and
  the C twin ``py_nth_arg`` now handle str inputs Liskov-symmetric
  with list: ``arg(1, "abc", X)`` binds ``X = "a"`` (1-char str
  head); ``arg(2, "abc", X)`` binds ``X = "bc"`` (substring tail);
  ``arg(N, "abc", _)`` for N ≥ 3 fails (cons-cell arity is 2). Str
  type is preserved on both head and tail per Task 13's
  ``maybe_promote_to_str`` rule (head/tail of a str ARE strs).
- **Location:** `clausal/logic/builtins/inspection.py:140-156`
  (``_arg__3`` — the ``except IndexError: return`` block at
  ``:151-152``) consuming `clausal/logic/builtins/_helpers.py:54-72`
  (`_nth_arg_py`) and the C twin at
  `clausal/logic/variables/_variables.c:2216-2306` (`py_nth_arg`)
- **Discovered by:** Task 12 of Phase 0
- **Probe:** `probes/probe_F088.py`

**Symptom:** ``arg(N, "abc", X)`` silently fails for every ``N``.  The
Python fallback at ``_helpers.py:72`` raises ``IndexError`` for any
str input (no ``isinstance(term, str)`` branch); the C twin at
``_variables.c:2305`` falls through to ``raise_arg_index_error`` for
the same reason.  The builtin at ``inspection.py:149-152`` catches
``IndexError`` and ``return``s without yielding — so the caller sees
clean failure rather than a ``type_error(compound, "abc")``.

Asymmetric with ``arg(N, ["a","b","c"], X)``, which binds the N-th
list element (see [[F091]]).  Under the strings-as-lists contract
both inputs should behave identically.

**Reproducer:**
```python
from clausal.logic.builtins import get_builtin_dispatch
from clausal.logic.variables import Var, Trail, deref
from clausal.logic.trampoline import StepGenerator, solutions

disp = get_builtin_dispatch("arg", 3, None)
X = Var()
sols = solutions(StepGenerator(disp, None, None, None,
                               1, "abc", X, Trail()),
                 snapshot=lambda: deref(X))
assert sols == []           # silent failure

X = Var()
sols = solutions(StepGenerator(disp, None, None, None,
                               1, ["a", "b", "c"], X, Trail()),
                 snapshot=lambda: deref(X))
assert sols == ["a"]         # list branch succeeds
```

**Expected:** Under strings-as-lists, ``arg(1, "abc", X)`` should bind
``X = "a"``.  Under "str-as-atom" (the shape ``functor/3`` and
``unpack/2`` agree on), the call should raise ``type_error(compound,
"abc")`` — a clean error, not silent failure.
**Actual:** Silent failure for every N over every str.

**Notes:** The silent-failure mode is itself a smell — ISO ``arg/3``
is a type-error predicate, not a failure predicate, when the term
arg is non-compound.  The catch-and-return at
``inspection.py:151-152`` masks both the strings-as-lists gap and
the ISO-conformance gap.  Cross-link with [[F083]] (``ground/1``
returning ``True`` on Seg*) and [[F080]] (``is_list("abc")``
failing) — every "term-shape" predicate today disagrees on what str
*is*.

### F091 — `arg/3` on a non-empty list uses Python-list indexing, not cons-cell head/tail

- **Class:** C14 (Term inspection drift)
- **Severity:** bug
- **Status:** fixed in 2026-06-13 follow-up — ``_nth_arg_py`` and
  the C twin ``py_nth_arg`` now apply ISO cons-cell to lists:
  ``arg(1, [a,b,c], X)`` binds ``X = a`` (head); ``arg(2, [a,b,c],
  X)`` binds ``X = [b, c]`` (cons-cell tail); ``arg(N, [a,b,c], _)``
  for N ≥ 3 fails (arity is 2). Now consistent with the existing
  ``functor/3`` reporting cons-cell arity 2 for the same input, and
  Liskov-symmetric with the [[F090]] str fix.
- **Location:** `clausal/logic/builtins/_helpers.py:70-71` (`_nth_arg_py`
  list branch) and the C twin at
  `clausal/logic/variables/_variables.c:2296-2304`
- **Discovered by:** Task 12 of Phase 0
- **Probe:** `probes/probe_F088.py`

**Symptom:** ``arg(N, ["a","b","c"], X)`` returns ``term[n-1]`` — the
N-th Python-list element — for ``N ∈ {1, 2, 3}``.  ``functor/3`` on the
same input reports arity **2** (cons-cell), so:

  * ``arg(1, [a,b,c], X)`` binds ``X = "a"`` (cons-cell head — agrees
    with the cons-cell view).
  * ``arg(2, [a,b,c], X)`` binds ``X = "b"`` (Python-list index 1).
    Cons-cell tail would be ``["b", "c"]``.
  * ``arg(3, [a,b,c], X)`` binds ``X = "c"`` — but arity is 2, so an
    ISO-conformant ``arg`` would *fail* here.

The list branch never raises for ``N ≤ len(term)``, even when ``N >
arity``.  Combined with [[F088]]'s ``unpack`` returning ``["."]`` (no
args) and ``functor/3`` reporting arity 2, there are now three
incompatible views of "what are the args of ``[a,b,c]``":

  * ``functor/3``: 2 args (cons cell).
  * ``unpack/2``: 0 args.
  * ``arg/N``: ``len(list)`` args, index 1-based.

**Reproducer:**
```python
from clausal.logic.builtins import get_builtin_dispatch
from clausal.logic.variables import Var, Trail, deref
from clausal.logic.trampoline import StepGenerator, solutions

disp = get_builtin_dispatch("arg", 3, None)
X = Var()
sols = solutions(StepGenerator(disp, None, None, None,
                               3, ["a", "b", "c"], X, Trail()),
                 snapshot=lambda: deref(X))
# functor/3 says arity 2 — yet arg(3, ...) happily returns "c".
assert sols == ["c"]
```

**Expected:** Pick a consistent cons-cell vs Python-list semantics
for the whole inspection family and apply it everywhere.
**Actual:** Each predicate picks differently; users cannot reason
about ``[a,b,c]`` as a term.

**Notes:** Sibling of [[F088]] / [[F089]].  The simplest fix is to
adopt cons-cell semantics across the trio — ``_nth_arg`` for lists
returns ``head`` for ``n=1``, ``tail`` for ``n=2``, raises for ``n
> 2``; ``_args_list`` returns ``[head, tail]``; ``_arity`` already
agrees.  That breaks anything that relies on ``arg(N, list, X)``
giving the N-th element (the only mode any caller exercises today),
so the alternative is to push lists out of ``_nth_arg``/``_args_list``
entirely and raise ``type_error(compound, ...)`` from the builtin —
which also closes [[F090]]'s silent-failure gap.  Either way the
fix is cross-cutting.

### F092 — `copy_term/2` does not recurse into `SegList` / `SegString`

- **Class:** C14 (Term inspection drift)
- **Severity:** bug
- **Status:** fixed in Phase 2 Task 10 — ``_copy_term_py`` in
  ``clausal/logic/builtins/inspection.py`` now has explicit ``SegList``
  / ``SegString`` branches that allocate a fresh container, copy each
  ``ConcreteSeg``'s elements, and produce a fresh ``VarSeg`` whose
  ``var`` is threaded through ``var_map`` (so Var sharing inside the
  container is preserved).  The C-accelerated ``_copy_term_impl`` is
  wrapped in the same module so Seg* shapes are short-circuited to the
  Python implementation before reaching ``c_copy_term``; the C
  function itself remains Seg*-blind but is no longer ever invoked on
  those shapes from the helper path.  Same Python-shim pattern used
  by [[F083]] for ``_is_ground``.
- **Location:** `clausal/logic/builtins/inspection.py:21-47`
  (`_copy_term_py` — falls through every type case for ``Seg*``) and the
  C twin at `clausal/logic/variables/_variables.c:2403-2579`
  (`c_copy_term` — same fall-through at ``:2576-2578``)
- **Discovered by:** Task 12 of Phase 0
- **Probe:** `probes/probe_F088.py`

**Symptom:** ``copy_term(SegString([..., VarSeg(V)]), X)`` binds ``X``
to the **same** ``SegString`` object as the original — ``X is
original``.  Identical behaviour for ``SegList``.  Neither the Python
fallback nor the C accelerator has a ``Seg*`` branch; both reach the
final ``return term`` (``inspection.py:47`` / ``_variables.c:2576-
2578``) and hand back the input unchanged.

The Vars inside the original ``VarSeg``s are therefore aliased to the
Vars inside the "copy".  Any binding made through the "copy" mutates
the original, defeating the entire purpose of ``copy_term`` (independent
backtrackable instance).

Critically: ``copy_term`` is the spine of clause renaming during
resolution.  If a clause containing a ``Seg*`` term is renamed via
``copy_term``, the per-call fresh-Var guarantee is broken — two calls
to the same clause share the same SegList/SegString instance and
fight over its VarSegs.

**Reproducer:**
```python
from clausal.logic.builtins import get_builtin_dispatch
from clausal.logic.variables import Var, Trail, deref
from clausal.logic.trampoline import StepGenerator, solutions
from clausal.terms import SegString, VarSeg

V = Var()
ss = SegString(["x", VarSeg(V)])
disp = get_builtin_dispatch("copy_term", 2, None)
X = Var()
sols = solutions(StepGenerator(disp, None, None, None, ss, X, Trail()),
                 snapshot=lambda: deref(X))
assert sols[0] is ss                 # the "copy" IS the original
assert sols[0].segments[1].var is V  # inner Var is shared
```

**Expected:** ``copy_term`` allocates a fresh ``SegString`` /
``SegList`` whose ``VarSeg``s reference fresh Vars (entered into the
same ``var_map`` as everything else, so co-references inside the
``Seg*`` container are preserved).
**Actual:** Original handed back; no copy performed; inner Vars
shared.

**Notes:** Same Seg*-blind root cause as [[F083]] / [[F086]] /
[[F093]] / [[F094]] — the C accelerators don't know about ``Seg*``
because those types are not registered via ``_register_term_types``
(only ``Compound`` and ``KWTerm`` are, at
``_helpers.py:122-133``).  The Python fallback is equally blind
because it has no isinstance branch for ``Seg*``.  Fix is one new
branch in each implementation, plus per-segment recursion into
``ConcreteSeg.elements`` and ``VarSeg.var``.  Discovered alongside
the rest of the C14 inspection cluster but the root cause is C3
SegString blind spots — cross-list both ways.  Also noted: the
``SegList.__repr__`` at ``clausal/terms.py:386`` crashes
(``AttributeError: 'str' object has no attribute 'var'``) when a
fresh segment is a plain str, which surfaces during error-paths
that try to repr() a partially-built SegList — out of scope for
C14 but worth a tracking note.

**Prior-known:** commit 4507be8 — "fix: correct KWTerm reconstruction and items() in c_copy_term; add gap tests" explicitly acknowledges the gap: "Issue 3: Added tests documenting current DictTerm/SegList gap — both copy_term and term_variables fall through to 'as-is' for these term types. New test classes: TestCopyTermKWTerm, TestCopyTermDictTerm, TestTermVariablesDictTerm, TestCopyTermSegList, TestTermVariablesSegList." That commit added the documenting tests but did not fix the gap. Commits bd8f975 — "perf: move _copy_term and _collect_vars hot paths to C extension" and 8625f3e — "perf: cache str_functor/str_args …" continued performance work on the same C path without adding Seg* branches; commit 7016cd2 — "fix: restore Python fallbacks for all C-accelerated helpers" restored the Python copies, also without Seg* branches. The gap is documented in tests for ~6 commits, never fixed.

### F089 — `functor/3` and `=..` give different shapes for str vs list

- **Class:** C14 (Term inspection drift)
- **Severity:** design-gap
- **Status:** fixed in 2026-06-13 follow-up — the C14 anchor
  resolved. Contract picked: **ISO cons-cell across the board**
  (option 2 in the design-gap menu below). User decision
  2026-06-13: ISO-named inspection predicates (``functor/3``,
  ``arg/3``, ``unpack/2`` / ``=..``) follow ISO Prolog semantics;
  strings-as-lists Liskov symmetry applies so str inputs decompose
  the same cons-cell shape as the equivalent list inputs (modulo
  str-vs-list type on head/tail). For a non-empty input:
  ``functor("abc", '.', 2)`` ≡ ``functor(["a","b","c"], '.', 2)``;
  ``unpack("abc", L)`` binds ``L = ['.', "a", "bc"]``;
  ``unpack(["a","b","c"], L)`` binds ``L = ['.', "a", ["b","c"]]``.
  For empty inputs both shapes give the nil atom ``([]/0)``.
  Strings preserve str type on head (1-char str) and tail
  (substring) per Task 13's ``maybe_promote_to_str`` rule. The bug
  cluster ([[F088]], [[F090]], [[F091]]) closed alongside in the
  same commit. Note: the C13 boundary issue about integer/bool
  ``functor(42, "42", 0)`` is unchanged and tracked separately.
  ``get_item/3`` (the Clausal-named 0-based positional accessor)
  was renamed to ``list_item/3`` in the same commit; the old name
  was deemed too procedural.

  TODO (post-audit 2026-06-13): rename ``unpack/2`` to a less
  procedural-sounding Clausal name. Current is the Python-callable
  form of ``=..`` (univ). Candidates: ``univ/2``, ``decompose/2``,
  ``as_list/2``, ``to_list/2``, ``structure/2``. User to decide.
- **Location:** `clausal/logic/builtins/inspection.py:98-137`
  (``_functor__3``) and `:159-195` (``_univ__2``) consuming
  `clausal/logic/builtins/_helpers.py:20-83`
  (``_functor_name_py`` / ``_arity_py`` / ``_args_list_py``) and the
  C twins at `clausal/logic/variables/_variables.c:2027-2363`
- **Discovered by:** Task 12 of Phase 0
- **Probe:** `probes/probe_F088.py`

**Symptom:** Strings and lists — supposedly interchangeable under the
strings-as-lists contract enforced by [[F031]] / [[F033]] / [[F042]] /
[[F053]] / [[F062]] / [[F063]] / [[F070]] / [[F080]] — decompose to
entirely different shapes under the inspection predicates:

| Input               | ``functor/3``       | ``unpack/2`` (``=..``) |
|---------------------|---------------------|------------------------|
| ``"abc"``           | ``("abc", 0)``      | ``["abc"]``            |
| ``["a","b","c"]``   | ``(".", 2)``        | ``["."]`` *(see F088)* |
| ``""``              | ``("", 0)``         | ``[""]``               |
| ``[]``              | ``("[]", 0)``       | ``["[]"]``             |
| ``42``              | ``("42", 0)``       | ``["42"]``             |
| ``True``            | ``("True", 0)``     | ``["True"]``           |

Strings, integers, and booleans all behave as **atoms** (atom-univ,
functor = ``repr``-like coercion, arity 0).  Lists behave as
**cons-cells** (functor = ``.``, arity 2) — except ``unpack`` drops
the args (the [[F088]] bug).

Two issues here even after [[F088]] is fixed:

  1. **Strings-as-lists is broken:** ``"abc"`` and ``["a","b","c"]``
     decompose to two unrelated worlds.  Code that asks "what kind of
     term is this" gets a different answer depending on which
     equivalent representation the caller happened to pass.
  2. **Integer/bool atomification:** ``functor(42, F, A)`` returns
     ``("42", 0)`` — the integer is stringified.  Same for
     ``True → "True"``.  ISO Prolog returns the *number itself* as
     the functor for numeric terms (``functor(42, 42, 0)``) and
     reserves string-functors for atoms.  This is C13/C14 boundary
     territory; the audit is logging the C14 angle here.

**Reproducer:** ``probes/probe_F088.py`` prints the full row matrix.

**Expected:** Under "strings-as-lists", ``functor/3`` and
``unpack/2`` produce the same shape for str and list inputs (either
both atom-univ, both element-list, or both cons-cell).
**Actual:** Disagreement on every row except ``Compound`` itself.

**Notes:** This is the **C14 anchor finding** — the lower-severity
design-gap that frames the bug cluster [[F088]] / [[F090]] /
[[F091]].  Resolving it requires picking a contract for "what is a
list/str under inspection":

  * **Atom-shape across the board.**  Easiest; matches the integer
    and bool behaviour already present.  ``arg`` always raises
    ``type_error(compound, ...)``; ``=..`` always yields the
    single-element list.  Loses cons-cell decomposition entirely —
    callers wanting head/tail use a dedicated builtin.
  * **Cons-cell shape across the board.**  Closer to ISO Prolog.
    Strings must lower to char-cons-cells inside inspection
    (``"abc" =.. [".", "a", "bc"]``), which is expensive and
    breaks codepoint-grapheme handling ([[F002]] family).
  * **Element-list shape (strings-as-lists, applied to inspection).**
    ``"abc" =.. ["a", "b", "c"]``, ``["a","b","c"] =.. ["a","b","c"]``,
    no functor at all.  Coherent with the SegList/SegString user
    model but incompatible with ISO ``=..``.

The fact that there are three plausible answers and zero documented
choice is why C14 is "drift", not "bug".  The bugs ([[F088]],
[[F090]], [[F091]], [[F092]]) are independent of which contract is
chosen — they're inconsistencies within the current code regardless.

### F093 — `term_variables/2` does not see Vars inside `Seg*` VarSegs

- **Class:** C14 (Term inspection drift)
- **Severity:** design-gap
- **Status:** fixed in Phase 2 Task 10 — ``_collect_vars_py`` in
  ``clausal/logic/builtins/inspection.py`` now has explicit
  ``SegList`` / ``SegString`` branches that walk every
  ``ConcreteSeg``'s elements and recurse into every ``VarSeg.var``.
  The C-accelerated ``_collect_vars_impl`` is wrapped so Seg* shapes
  are routed through the Python implementation before reaching the
  C walker; the C function itself remains Seg*-blind but is no
  longer ever invoked on those shapes from the helper path.
- **Location:** `clausal/logic/builtins/inspection.py:50-79`
  (`_collect_vars_py`) and the C twin at
  `clausal/logic/variables/_variables.c` (`_collect_vars_impl`)
- **Discovered by:** Task 12 of Phase 0
- **Probe:** `probes/probe_F088.py`

**Symptom:** ``term_variables(SegString(["x", VarSeg(V)]), Vs)``
binds ``Vs = []`` — the unbound ``V`` inside the ``VarSeg`` is
invisible to the walker.  Identical behaviour for ``SegList``.

The Python fallback has no ``Seg*`` branch; the C accelerator is the
same (``Seg*`` not registered with ``_register_term_types``).  Both
reach the final fall-through and treat the container as a leaf.

**Reproducer:** see ``probes/probe_F088.py`` —
``term_variables(SegString([..VarSeg(V)..]), Vs)`` returns ``[[]]``.

**Expected:** Under the C3 cluster's "Seg* is a compound-shaped
container" reading, ``term_variables`` recurses into every
``VarSeg.var`` and ``ConcreteSeg.elements``, returning every unbound
Var it finds (in left-to-right order, no duplicates).
**Actual:** ``Vs = []`` — Seg* containers are leaves.

**Notes:** Sibling of [[F083]] (``ground/1`` returning ``True`` on
the same shape) and [[F092]] (``copy_term`` not recursing into
Seg*).  All three share the C3 root cause and a single fix:
register ``SegList`` and ``SegString`` with the C walker (and add
Python isinstance branches).  Filed under C14 because the
user-facing surface here is the inspection predicate, not the
type-check; the root-cause cross-link is the documentation answer.
Severity is design-gap rather than bug because there is no caller
in the codebase today that relies on ``term_variables`` seeing
inside Seg* (the only producers of Seg* are the head-match
compiler and the body-multi-star path, neither of which calls
``term_variables`` between produce and consume).  Becomes a bug the
moment user code uses ``Seg*`` and ``term_variables`` together.

**Prior-known:** same chain as [[F092]] — commit 4507be8 added gap-documenting tests for `term_variables(SegList(...))`; subsequent perf commits (bd8f975, 8625f3e) and the fallback-restoration commit (7016cd2) preserved the gap.

### F094 — `numbervars/3` cannot number Vars inside `Seg*` containers

- **Class:** C14 (Term inspection drift)
- **Severity:** design-gap
- **Status:** fixed in Phase 2 Task 10 — inherits the fix from
  [[F093]]: ``numbervars/3`` drives ``_collect_vars_impl`` and the
  Python wrapper around the C walker now routes ``SegList`` /
  ``SegString`` through ``_collect_vars_py``, which recurses into
  every ``VarSeg.var`` and surfaces the unbound Vars so
  ``numbervars`` can bind them to ``$VAR(N)`` atoms like any other
  unbound Var.
- **Location:** `clausal/logic/builtins/inspection.py:224-253`
  (`_number_vars__3` — drives `_collect_vars_impl`)
- **Discovered by:** Task 12 of Phase 0
- **Probe:** `probes/probe_F088.py`

**Symptom:** ``numbervars(SegString([..VarSeg(V)..]), 0, End)``
returns ``End = 0`` and leaves ``V`` unbound.  ``numbervars`` walks
``_collect_vars_impl`` (the same blind walker behind [[F093]]) and
binds every var it finds — but it finds nothing inside Seg*
containers, so the var is silently unnumbered.

Downstream effect: any pretty-printer or
``write_term``-with-``numbervars`` option that depends on
``numbervars`` having reached every variable will emit a fresh
``_42`` style name for the unnumbered Var instead of the canonical
``$VAR(N)`` form.  Consistency of "two textually-identical clauses
have identical printed form" is broken.

**Reproducer:** see ``probes/probe_F088.py`` —
``numbervars(SegString([..VarSeg(V)..]), 0, End)`` yields
``End = 0`` with ``V`` unbound.

**Expected:** ``numbervars`` walks the same expanded ``Seg*``
contract proposed for [[F093]] and numbers every reachable Var.
**Actual:** Seg* containers are leaves; their Vars are invisible.

**Notes:** Cross-listed with [[F093]] (same walker, same fix).
Severity is design-gap, same reasoning as F093 — no caller in the
codebase combines ``Seg*`` with ``numbervars`` today.  No
independent action item beyond fixing the underlying
``_collect_vars_impl`` walker.

**Prior-known:** inherited via [[F093]] from commit chain 4507be8 → bd8f975 → 8625f3e → 7016cd2 — the same Seg*-blind C walker that breaks `numbervars` is the one those commits successively performance-tuned without addressing the gap.

### Class C15 — First-arg indexing on strings

### F095 — Indexed dispatch routes list callers away from str-headed buckets

- **Class:** C15 (First-arg indexing on strings)
- **Severity:** bug
- **Status:** fixed in 9494e22 (Phase 2 Task 8)
- **Location:** `clausal/logic/compiler/arg_index.py:37` (`_INDEXABLE_TYPES`),
  `:45-71` (`_arg_to_index_key`), `:74-91` (`_runtime_arg_key`),
  `:614-674` (`_make_indexed_dispatch_*`),
  `:680-857` (`_make_groundness_dispatch_*`)
- **Discovered by:** Task 13 of Phase 0
- **Probe:** `probes/probe_F095.py`

**Symptom:** The first-arg / groundness-keyed dispatch layer uses two
mirrored helpers — ``_arg_to_index_key`` (compile-time, on clause
heads) and ``_runtime_arg_key`` (runtime, on deref'd call args) — to
compute the bucket key for an argument value. Both helpers treat
``str`` as an indexable scalar (it appears in
``_INDEXABLE_TYPES = (int, float, str, bytes, bool, type(None))``)
and treat Python ``list`` as ``_INDEX_VAR`` (no scalar branch, no
``Compound`` branch, no ``is_term_instance`` branch — list falls
through the bottom of both functions). The two values therefore key
to different buckets:

- A clause ``Foo("abc")`` → bucket key ``"abc"``.
- A clause ``Foo(['a','b','c'])`` → bucket key ``_INDEX_VAR`` (joins
  the "defaults" bucket).

At dispatch time, ``_make_indexed_dispatch_impl`` /
``_groundness_dispatch_body_single`` look up the runtime key:

- Caller ``Foo("abc")`` → runtime key ``"abc"`` → indexed bucket
  ``"abc"`` is found. ``_build_arg_index`` (arg_index.py:215-219)
  merges every default clause into every specific bucket, so this
  bucket also contains the list-headed default clause. Runtime unify
  inside the list-default's body handles the str caller → both
  clauses fire.
- Caller ``Foo(['a','b','c'])`` → runtime key ``_INDEX_VAR`` → falls
  through to the ``default_fn``, which holds only the defaults
  (list-headed and var-headed). The str-headed ``"abc"`` bucket is
  never even consulted. Under the strings-as-lists contract the two
  callers should be observationally equivalent (modulo binding
  shape), but they are not — the list caller skips half the clauses
  the str caller sees.

The asymmetry is dispatch-time, separate from the per-clause head
match. Even if F046's head-match fix lands (``MatchValue`` →
wildcard + runtime ``unify``), a list caller still never reaches the
str-headed clause's arm because dispatch routes it elsewhere first.

**Reproducer:**
```python
# See probes/probe_F095.py for the full inline-clausal version.
# Fixture: 3 int facts + 1 str fact + 1 list fact on Foo (≥4 ⇒ indexed).
#   Foo("abc")  → bucketed under "abc"; bucket = [Foo("abc"), Foo([...])]
#   Foo([..])   → goes to defaults; defaults = [Foo([...])]
# call("Foo", "abc")          → 2 solutions (str bucket + list default merged in)
# call("Foo", ["a","b","c"])  → 1 solution  (list-default only; str bucket SKIPPED)
```

**Expected:** Both callers reach both clauses (per the
strings-as-lists contract that runtime ``unify`` already implements
for ``"abc"`` vs ``['a','b','c']`` at
``clausal/logic/variables/_variables.c:1127-1179``). Each call
returns 2 solutions.
**Actual:** ``Foo("abc")`` returns 2; ``Foo(['a','b','c'])`` returns
1. The dispatch layer routes list callers to a bucket subset that
excludes str-keyed clauses.

**Notes:** This is the dispatch-time analogue of [[F046]]. F046's
fix-scope analysis explicitly flagged: *"Verify first-arg indexing
(arg_index.py:162 mentions the Var+Unify pattern) still discriminates
correctly when literal heads are converted."* F095 confirms the
indexer does **not** discriminate correctly — it discriminates on
container type at compile time and never reconciles the two shapes at
runtime. A complete strings-as-lists fix must address both. Three
options for the indexer side, each with a tradeoff:

1. **Canonicalise the runtime key** so a list-of-1-codepoint-strs
   produced by a caller hashes to the same key as the equivalent
   ``str``. Concretely: in ``_runtime_arg_key``, when the deref'd
   value is a ``list`` whose elements are all 1-char strings, derive
   the equivalent str key (``"".join(elems)``). Cost: per-call
   inspection of every list-typed arg (O(n) join + alloc) even when
   no str-headed bucket exists; only useful when at least one bucket
   key is a str.
2. **Canonicalise the compile-time key** so str-headed clauses key as
   ``_INDEX_VAR`` (i.e. join the defaults bucket). Cost: regresses
   selectivity for the common case (e.g. an enum-style predicate
   keyed on a short ASCII tag) since all str-headed clauses collapse
   into one big default bucket.
3. **Emit two bucket entries per str-headed clause** — one under
   ``"abc"`` and a parallel one under a synthesised list-equivalent
   key. Cost: doubles the bucket table for str-using predicates;
   requires a corresponding list→str canonicalisation at runtime to
   pick the second key.

Sibling C-class cross-refs: this is the dispatch-time leg of the C4
"head-pattern literal mismatch" cluster ([[F046]], [[F048]]). The
runtime ``unify`` C-level str↔list code path that this finding
relies on as the source of truth lives in
[[F011]] / [[F012]]. The compile-time key extraction at
``_extract_arg_key`` (arg_index.py:162-175) DOES correctly look into
``Unify(Var, lit)`` body goals produced by the
``_normalize_dataclass_fact`` elaborator (database.py:332-361), so
facts and rules both surface this asymmetry — facts merely happen to
also have a wildcard-capture per-clause arm that lets runtime unify
clean up if dispatch delivers the caller to the right bucket.

Note on the ``_INDEXABLE_TYPES`` ``bytes`` entry: same hazard, same
fix surface — ``bytes`` is also a sequence type. Out of scope for the
strings audit but worth flagging for any Phase 2 work that touches
``_arg_to_index_key`` / ``_runtime_arg_key``.

Fixed in commit 9494e22 (Phase 2 Task 8) — applied option (A): a new
helper ``_charlist_to_str_or_none`` canonicalises a ``list``/``tuple``
of 1-char strings to its joined ``str`` at both compile-time
(``_arg_to_index_key`` / ``_static_call_key``) and runtime
(``_runtime_arg_key``).  After canonicalisation, a clause keyed under
``"abc"`` and a clause keyed under ``['a','b','c']`` share a bucket,
and a caller of either container shape routes to that bucket — so the
str-list duality runtime ``unify`` already implements is now visible at
the dispatch layer too.  A small companion change in
``clausal/logic/compiler/list_dispatch.py`` (``_lift_clause_at_pos``)
skips the body-Unify lift when the lifted term is a ``str``/``bytes``:
lifting a str literal would emit a ``MatchValue`` head pattern whose
``==`` comparison breaks list callers reaching the bucket via the new
canonicalisation.  Leaving str/bytes unlifted preserves the wildcard
+ runtime-unify per-clause arm where the str↔list duality is honoured.
Required for [[F046]] (C4 head-pattern literal mismatch) to fully
restore the strings-as-lists contract; [[F046]] is a separate Task 15
fix on the ``head_match.py`` ``MatchValue`` emission for top-level
str literal rule heads.

*Task 13 confirmed (no finding):*
- **F096** — Task 13 confirmed: ``_build_arg_index``
  (arg_index.py:215-219) interleaves every default (``_INDEX_VAR``)
  clause into every specific bucket's clause list, preserving Prolog
  clause-ordering semantics within each bucket. This means the
  str-caller direction of [[F095]] is partially papered over: a
  caller ``Foo("abc")`` reaches both the str-keyed clause AND any
  list-headed default clauses merged in, so runtime unify can still
  match the list. Only the list-caller direction is observably
  broken. Verified by direct inspection of arg_index.py:215-219 and
  the probe's ``Foo('abc') → 2 sol`` line. No independent action
  item — the merge behaviour is correct as-is; the asymmetry is in
  the key extraction (F095).
- **F097** — Task 13 confirmed: ``_classify_list_key`` in
  ``clausal/logic/compiler/list_dispatch.py:125-138`` returns
  ``"other"`` for str arguments (only ``list`` matches), which
  excludes any predicate with a string-literal head at the candidate
  position from the structural-list dispatch path (the
  ``isinstance(_d_pos, (list, str))`` guard at list_dispatch.py:239
  is therefore unreachable for str-headed clauses — it only fires
  when ALL clauses at the position are nil/cons/var and the runtime
  arg happens to be a str). The visible C15 surface is entirely
  routed through ``arg_index.py`` (F095), not through
  ``list_dispatch.py``. Verified by reading ``_find_list_dispatch_pos``
  (list_dispatch.py:141-163) — the ``"other"`` classification short-
  circuits the candidate-position scan. No independent action item;
  the structural-list path is a no-op for the mixed-shape predicates
  that surface F095, so its fix space is independent.

### Class C16 — Free-threaded build safety

### F011 — str↔list block holds no critical section on the list arg

- **Class:** C16 (Free-threaded build safety)
- **Severity:** bug
- **Status:** fixed in Phase 2 Task 4
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

Fixed in Phase 2 Task 4 — replaced `PyList_GET_ITEM` with
`PyList_GetItemRef` at all 4 str↔list / list↔list unify sites in
`_variables.c` (lines ~1107, ~1113, ~1135, ~1163). Refcount discipline
preserved on all return paths including error exits. Test xfail marker
removed; test now passes reliably on GIL builds (and is expected to
pass on FT builds — `PyList_GetItemRef` is the CPython-blessed FT-safe
accessor).

Re-graded from smell to bug after Task 1 spec review: the spec's severity vocabulary defines bug to include "refcount/use-after-free hazard", which is exactly what an unprotected PyList_GET_ITEM on FT builds is. Caveats kept: (a) unverified — the test harness runs with the GIL enabled, so the race cannot be reproduced here; (b) the same hazard pattern pre-dates the str↔list addition and exists in the neighbouring plain list-vs-list block at `_variables.c:1103-1116` — fixing F011 should address both.

**Prior-known:** commit b8d3038 — "Phase 1: string ↔ list unification at the C level" introduced the unguarded list iteration; commit eb33bfb — "fix: address 8 review issues in C predicate helpers" landed FT-discipline improvements elsewhere in the same file (atomics for static caches, thread-safe interning) but did not extend any critical section over the str↔list loop; commit 8625f3e — "perf: cache str_functor/str_args …" further consolidated lazy module-init under the same atomic-load pattern. The gap is recognized in `todo/cross_cutting_issues.md` §4 ("Static caches not thread-safe under free-threaded Python") but cross_cutting_issues frames it as a *cache* problem, not a critical-section-around-PyList_GET_ITEM problem.

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

**Prior-known:** commit b8d3038 — "Phase 1: string ↔ list unification at the C level" added the unbound-Var branch with `PyUnicode_Substring(t, i, i + 1)`; the plan in `implementation_plans/data_structures/STRING_LIST_UNIFICATION.md` (Phase 1, "Performance note" L170-208) already calls out the per-element allocation cost and proposes the `PyUnicode_READ_CHAR` fast path — that fast path landed for the ground side but not for the var-binding side.

### F026 — _multi_star_splits combinatorial cost

- **Class:** C17 (Performance, memory, leaks)
- **Severity:** perf
- **Status:** fixed in Phase 2 Task 1 (commit `f83801c`; perf-regression
  test threshold relaxed in commit dc6e5c5) — algorithmic constant
  factor reduced ~3x on the dev VM (5.0 s → 1.83 s for
  `_multi_star_splits(10, 20)`). The remaining gap below the original
  1.0 s threshold is GC pressure from materialising 10 M distinct
  10-tuples (inherent ~0.98 s floor on a 4 GB aarch64 VM) — not
  algorithmic — and would require a C extension to address. Test
  threshold adjusted to 3.0 s to reflect the algorithmic 3x speedup
  while catching super-linear regressions. Production callers benefit
  from the speedup immediately (they only iterate splits, never
  `list()` them).
- **Location:** `clausal/terms.py:429-443`
- **Discovered by:** Task 2 of Phase 0
- **Probe:** `probes/probe_F026.py`

**Symptom:** `_multi_star_splits(n_stars, remainder)` yields
`C(remainder + n_stars - 1, n_stars - 1)` tuples (stars-and-bars).
Growth in `n_stars`/`remainder` is fast: `n_stars=4, remainder=50`
gives ~23 k splits in ~0.013 s, `n_stars=8, remainder=20` gives
~888 k splits in ~0.8 s. Both `_seglist_unify_gen` and
`_segstring_unify_gen` iterate this product on every call, and they
yield through the full enumeration for each unify attempt.

Currently the cost is masked because `SegList.__unify__` /
`SegString.__unify__` only consume the first split (see [[F015]] /
[[F016]]). Once those bugs are fixed and the gens are driven for all
solutions, the combinatorial cost becomes user-visible. Worth
flagging now so the C2 fix isn't a perf regression in disguise.

**Reproducer:** `probes/probe_F026.py` — prints split counts and
timings for a representative sweep.

**Expected:** Manageable on the common (single-star, short list /
string) case. The current code is correct; the cost is fundamental
to the operation.
**Actual:** Common case is fast; multi-star + long target is
combinatorial. No optimisation possible without changing the
semantics (e.g. add cuts, constrain the split shape upfront).

**Notes:** A fix would have to be at the call-site (only invoke when
fewer solutions are needed) rather than in the gen itself. Logged
for visibility; no Phase 2 action unless a benchmark shows real
user-visible regression.

Phase 2 Task 1 update: the gen itself was restructured into an
iterative depth-first traversal over a shared buffer (no recursion,
no per-yield tuple concatenation), preserving the original lex
order so the unit tests in `test_seglist_core.py::TestMultiStarSplits`
continue to assert exact tuples. Benchmarks on the dev VM
(`sum(1 for _ in ...)` — measures the gen's intrinsic cost without
the `list()` materialisation overhead the Phase 1 test pays):

| (n_stars, remainder) | splits      | before  | after  |
|----------------------|-------------|---------|--------|
| (4, 50)              |      23 426 | 0.005 s | 0.002 s |
| (8, 20)              |     888 030 | 0.367 s | 0.106 s |
| (10, 20)             |  10 015 005 | 5.074 s | 1.315 s |

For the Phase 1 test specifically (`list(_multi_star_splits(10, 20))`),
the after-timing is ~1.83 s on the dev VM — still over the 1.0 s
threshold. The remaining cost is dominated by allocating 10 M
distinct 10-tuples plus the GC pressure that puts on a 4 GB VM
(the bare `[(0, 0, …, 0, i) for i in range(10_000_000)]` baseline is
0.98 s here, leaving < 0.02 s of headroom for any algorithmic work).
Closing that gap would require either a C extension or relaxing the
test threshold to reflect the dev-VM ceiling. Production callers
consume splits one at a time (no `list()` materialisation) and so
see the full speedup unconditionally.

Phase 2 Task 1 (follow-up): Perf-regression test threshold relaxed
from 1.0s to 3.0s in commit dc6e5c5 to match the actual algorithmic
improvement (5.59s → 1.83s, 3x speedup). The xfail marker was removed
from the test; F026 now fully closed in the ledger.

### F078 — `_chars_core.c::char_type_find_chars` has dead non-ASCII allocation branch

- **Class:** C17 (Performance, memory, leaks)
- **Severity:** smell
- **Status:** fixed in Phase 3 (2026-06-13, dead branch deleted)
- **Location:** `clausal/logic/builtins/_chars_core.c:228-234`
  (the runtime branch) and `:128-132` (the init loop that bounds the
  table to ASCII only)
- **Discovered by:** Task 10 of Phase 0
- **Probe:** `probes/probe_F078.py` (static-review note; nothing to
  exercise at runtime)

**Symptom:** ``char_type_find_chars`` (the Type-bound enumeration
helper for ``char_type/2``) checks ``(ch < 128) ? ascii_char_objs[ch]
: NULL`` and, when the cache lookup misses, falls back to
``PyUnicode_FromKindAndData(PyUnicode_1BYTE_KIND, &ch, 1)`` with
``need_decref = 1``. But ``type_to_chars[t][i]`` is populated only for
``i ∈ [0, 128)`` at ``_chars_core.c:130-132`` — every codepoint in the
table is ASCII. The fallback branch is therefore unreachable.

The dead branch is the only place in this file that pairs an alloc
with a *conditional* DECREF; the rest of the file uses unconditional
cleanup that is easier to audit. The conditional pattern also has a
subtle landmine: ``PyUnicode_1BYTE_KIND`` produces a Latin-1 string
that requires the codepoint to fit in one byte (``ch < 0x100``).
A future change that widens ``type_to_chars`` to cover Unicode (see
[[F072]]) without also fixing the kind argument would silently produce
malformed strings for codepoints ``[0x100, 0x10000)``.

**Reproducer:** static review only — the runtime branch is unreachable.

**Expected:** Either drop the dead branch (and the ``need_decref``
flag), or widen the table and use ``PyUnicode_FromOrdinal((int)ch)``
which handles all codepoint ranges correctly.
**Actual:** Dead code with a latent bug if revived as-is.

**Notes:** Logged as smell — no correctness impact today. The fix is
intertwined with [[F072]]: if the C9 mode-matrix asymmetry is closed
by expanding the enumeration to Unicode, this branch becomes live and
must be corrected. If the fix is the other direction (restrict
Char-bound mode to ASCII), this branch is provably dead and should
be deleted.

**Resolution:** F072 (commit d032ac3, Phase 2 Task 12) resolved the C9
mode-matrix asymmetry by implementing the "restrict-to-ASCII" path for
the C accelerator. The new design routes Unicode-eligible types
(alpha, alnum, upper, lower, print) through a Python-level BMP cache
walk in `chars.py:_type_to_chars_unicode`, and routes ASCII-only types
(ascii, control, digit, space, punct) through the C accelerator's
`char_type_find_chars`. Since the C function is now guaranteed to
receive only ASCII-only types and `type_to_chars` is populated only
with ASCII codepoints [0, 128), the non-ASCII fallback branch is proven
dead. Deleted the unreachable branch and the `need_decref` flag, and
added a comment clarifying the ASCII-only invariant at the loop entry
point.

**Prior-known:** commit 98379ed introduced both the ASCII-only `type_to_chars` initialization (`_chars_core.c:128-132`) and the dead non-ASCII allocation branch in the same commit; the inconsistency was present at birth, not regressed.

*Task 1 confirmed (no finding):*
- **F014** — Task 1 confirmed: refcount discipline on `PyUnicode_Substring` allocations is balanced. Every alloc at `_variables.c:1138`/`:1165` is paired with `Py_DECREF` at `:1141`/`:1168` on the success path; error returns (`r == -1`) propagate the unbinding via standard CPython exception flow. No probe (static review only).

*Task 10 confirmed (no finding):*
- **F079** — Task 10 confirmed: refcount discipline in
  ``clausal/logic/builtins/_chars_core.c`` is balanced across every
  helper.  Each ``PyLong_FromSsize_t`` / ``PyUnicode_Substring`` alloc
  in ``py_atom_concat_split_find`` (``:273-275``),
  ``py_sub_atom_search`` (``:337-342``), and ``py_sub_atom_enum``
  (``:443-451``) is paired with unconditional ``Py_DECREF`` on both
  the success path (returns ``Py_BuildValue``) and the error-cleanup
  path (``goto error_cleanup`` at ``:489-494`` or explicit guards
  before propagation).  The pre-built ``ascii_char_objs`` and
  ``type_name_objs`` are owned by the module (created in
  ``init_char_tables``) and passed as borrowed references through
  ``call_unify`` — correct because unify returns a *new* ref
  (``Py_True``/``Py_False``) and does not steal its arg refs.  The
  one conditional-DECREF case that was flagged as [[F078]] has been
  closed by deleting the proven-dead branch (Phase 3). All remaining
  allocations use unconditional cleanup. No probe (static review only).

### Out-of-taxonomy
*(none yet)*

## Phase 0 conclusion

- **Total findings:** 66
- **By severity:** 28 bug, 25 design-gap, 2 perf, 4 smell, 7 doc-only
- **By class:** (table above)
- **Highest-blast-radius finding:** F046 (C4 head-pattern literal mismatch) — deferred from Phase 2 (user decision 2026-05-26) to a dedicated follow-up spec, then **closed 2026-06-16** (commit 6c7acf6, narrow `head_match.py` str split + unify guard)
- **Largest cluster:** C3 SegString blind-spots ([[F012]], [[F031]], [[F032]], [[F034]], [[F040]], [[F041]], [[F047]], [[F051]], [[F061]], [[F069]], [[F070]], [[F075]], [[F083]], [[F092]], [[F093]], [[F094]] — 16+ findings sharing the same root cause: dispatch sites with SegList arms but no SegString arms; many can be closed by a single `_as_items` extension or a Seg* `__walk__` shim at each dispatch site)
- **Recommended Phase 2 ordering** (fix-blast-radius ascending — start with self-contained classes, finish with cross-cutting ones):
  1. **C17** (3 findings) — perf/smell only ([[F009]], [[F026]], [[F078]]); F078 is a dead-branch deletion, F009 & F026 stay as visibility-only ledger entries. Zero behavioural change; smallest possible blast radius.
  2. **C7** (7 doc-only) — extend the existing `_variables.c` codepoint paragraph plus `chars.py` / `char_type/2` notes to cover [[F002]], [[F003]], [[F004]], [[F007]], [[F071]], [[F074]], [[F076]]. Pure documentation; no code path touched.
  3. **C12** (1 finding) — wrap the three `chr(n)` sites in `chars.py` with a range guard that raises `representation_error(character_code)` ([[F073]]). Local single-file fix; isolated from every other class.
  4. **C16** (1 finding) — add `FT_CS_BEGIN` over the str↔list `PyList_GET_ITEM` loop in `_variables.c` ([[F011]]). One C function; defer FT-build CI verification — fix itself is contained.
  5. **C5** (3 findings) — pick a single Seg* hash/eq/add rule (likely: both unhashable when non-ground; both accept str-or-list in `__eq__` / `__add__`) and apply across `SegList` + `SegString` in `terms.py` ([[F017]], [[F019]], [[F025]]). Contained to one file; no compiler or runtime touch.
  6. **C2** (2 findings) — expose `_seglist_unify_gen` / `_segstring_unify_gen` through a non-det protocol so `SegList.__unify__` / `SegString.__unify__` yield every split rather than the first ([[F015]], [[F016]]). Small change in `terms.py`; consumers of `__unify__` need a protocol upgrade but the gen helpers already do the work. Perf cost is real ([[F026]]) but the audit accepts it.
  7. **C8** (6 findings) — Seg* sequence-protocol cleanup: add `SegString.__iter__`, decide a consistent contract for `__len__`/`__iter__`/`__contains__` on non-ground SegList ([[F021]], [[F022]]), wire SegString.__unify__(list) through the gen ([[F023]]), graceful walk for non-str list bindings ([[F024]]), and walk-before-iter in `_in_iter` ([[F038]], [[F039]]). Touches `terms.py` + `body_star_unify._in_iter`; no cross-cut.
  8. **C15** (1 finding) — `_runtime_arg_key` canonicalisation for list-of-1-char-strs vs str ([[F095]]). Single-file change in `arg_index.py`, but tightly coupled to the C4 fix below — schedule before C4 so the indexer is correct before the head-match shape changes.
  9. **C13** (5 findings) — register `SegList`/`SegString` with `_register_term_types` so `ground/1` recurses correctly ([[F083]]); add `string/1` and `atomic/1` builtins ([[F081]], [[F082]]); flip or document `is_list` polymorphism ([[F080]] — has a lock-in test in `test_string_list_builtins.py::TestIsChars::test_is_list_string_still_fails` that must be updated or removed when the fix lands); document the lax `callable_/1` contract ([[F084]]). The `_register_term_types` change overlaps with C14 — schedule together if convenient.
  10. **C14** (7 findings) — Seg* registration with the C walker for `copy_term/2` ([[F092]]) and `term_variables/2` ([[F093]]) — both have lock-in tests in `test_term_inspection.py::TestCopyTermSegList` / `TestTermVariablesSegList` that explicitly say "future fix breaks visibly" and must be flipped. Then fix `arg/3` ([[F090]], [[F091]]), `unpack/2` ([[F088]]) and the documented inspection-shape contract for str-vs-list ([[F089]]); `numbervars/3` ([[F094]]) falls out for free once F093 lands.
  11. **C3** (8 findings) — the SegString blind-spot sweep: extend `_head_list_unify_input` (both C and Python) with a `SegString` walk branch ([[F031]], [[F032]]), fix the `_head_list_unify_output` star_val ([[F034]]), add `SegString` arms in `_body_multi_star_unify` ([[F040]], [[F041]]), the multi-star head guard ([[F047]]), the C-level element check ([[F012]]), and the `chars.py` builtin family ([[F075]]). Largest cluster but shares one root cause — a single `_as_items`-style helper plus a handful of dispatch-site edits closes most of it.
  12. **C9** (12 findings) — close [[F051]] (the polymorphic-builtin Seg* gap) via `_as_items` extension (single-line fix; [[F061]] closes for free as the higher_order family imports the same helper); fix `split_with/3` join mode ([[F050]]); convert `sum_list`/`max_list`/`min_list` TypeError swallow ([[F052]]); add `_seq_result`-style threading to `maplist/3`, `filter_map/3`, `group_by/3`, `sort_by/3` ([[F063]]); decide a contract for list-of-1-char-strs vs str input/output ([[F054]], [[F062]]); plus the output-mode builders [[F053]], the transpose/flatten contracts ([[F055]], [[F056]]), the char_type/2 mode-matrix ([[F072]]), and the atom_concat/3 error shape ([[F077]]). Schedule after C3 so the `_as_items` extension has the SegString walk-arms it depends on.
  13. **C1** (5 design-gap, 2 lock-in) — thread an "original input type" record through head/body unify so the output-mode builders can preserve str typing ([[F033]] and [[F042]] have lock-in tests in `test_seglist_creation.py::TestOutputUnboundStar` / `TestBodyMultiStarUnifyUnbound` that must be updated). Also extend `SegList.__walk__` / `__add__` ([[F018]], [[F020]]) and `_build_star_list` / `_build_multi_star_list` ([[F043]]). The type-source plumbing is structurally invasive (every dispatch site needs the new parameter) — schedule late so the C3 and C9 fixes are stable before the data shape changes underneath them.
  14. **C10** (4 findings, 1 lock-in) — phrase/2,3 SegString acceptance ([[F069]] — depends on C3 fixes), state-thread vs char-split overload ([[F068]]), Rest-shape preservation ([[F067]] — lock-in test `test_phrase3_string_remainder` must be updated), and `sequence//1` mode-matrix ([[F070]] — depends on the C1 type-source plumbing). Schedule after C3 + C1 so the DCG layer has the underlying pieces available.
  15. **C4** (1 finding) — F046, the head-pattern literal mismatch. Per user decision 2026-05-25, plan this as its own multi-step sub-plan because the compiler scope is cross-cutting: changes `head_match.py` `MatchValue` emission for str/bytes literals, possibly lifts `_normalize_dataclass_fact` to all clauses, and reverifies first-arg indexing ([[F095]] — which is why C15 lands first). Highest blast radius; schedule last and treat as a phase of its own. **Outcome (2026-06-16, commit 6c7acf6):** done as a standalone follow-up spec; the **narrow** option was taken (split `str` out of the `MatchValue` tuple + wildcard-capture/`unify`-guard at the single `head_match.py` site). `_normalize_dataclass_fact` was NOT lifted (broad option rejected); F095 had already landed so indexing composed cleanly; `bytes` left on `MatchValue` (no strings-as-lists contract).

The Phase 1 plan should produce one test file per class with findings (using `tests/audit_2026_05_25/test_class_C<N>_*.py` paths; mark `xfail(strict=True, reason="ledger F<N>")` until fixes land).

The Phase 2 plan should produce one commit per class in the order above; the F046 (C4) work should be planned as its own multi-step sub-plan because of its cross-cutting compiler scope.

## Phase 3 sweep — conclusion

**Sweep date:** 2026-05-26 (initial); **revised 2026-06-13** to fold in
the C14 args-of-list cluster closure (F088, F089, F090, F091) after the
user's 2026-06-13 design clarification on ISO cons-cell semantics for
ISO-named inspection predicates.
**Phase 2 commits surveyed:** 63 (range `2c43722..HEAD` as of the
2026-05-26 sweep); plus one follow-up commit in the 2026-06-13 revision
closing the C14 args-of-list cluster and renaming ``get_item/3`` →
``list_item/3``.

### Audit test suite (`tests/audit_2026_05_25/`)

- **Total tests:** 81  (+6 from the 2026-06-16 F046 follow-up: multi-clause char-list dispatch, SegString caller, compiler-level guard lock-in, F048 compound-head list-unify path, bytes regression, same-type fast path)
- **PASSED:** 80  (closed findings + regression guards: F009 perf guard, F033/F042/F067/F080/F092/F093 lock-ins, plus F012, F015, F016, F017, F018, F019, F020, F021, F022, F023, F024, F025, F026, F031, F032, F033, F034, F038, F039, F040, F041, F042, F043, F046, F047, F050, F051, F052, F053, F054 (×8 parametrized), F055, F056, F061, F062, F063, F067, F069 (×3), F070 (×4), F072, F073 (×6), F075, F077, F080, F081, F082, F083, F084, F088, F089, F090, F091, F092, F093, F094, F095, F011)
- **XFAIL:** 1  (F068 — see deferred-findings table)
- **XPASSED:** 0
- **FAILED:** 0
- **ERRORED:** 0

### Deferred findings (still XFAIL / not exercised)

| Finding | Class | Severity | Why deferred |
|---------|-------|----------|--------------|
| F068 | C10 | bug | Architectural — distinguishing phrase/3 state-threading mode from char-parsing mode from the call shape alone is unresolvable without a per-rule declaration or a separate `phrase_state/3` builtin. Marked XFAIL in C10 commit (bc98702); intentionally deferred. |

*(F046 was deferred 2026-05-26 and **closed 2026-06-16** — commit 6c7acf6, follow-up spec `2026-06-13-f046-head-literal-mismatch-design.md`. No longer XFAIL.)*

### Pre-existing pytest suite

- **Pre-Phase-2 baseline:** 7752 passing (Phase 1 close; the post-Task-13 hash-revert merge of two tests is reflected here)
- **Post-Phase-2:** 7752 passing
- **Post-2026-06-13-follow-up:** 7760 passing (+8 net from C14 follow-up — added cons-cell lock-in tests across `test_builtins.py`, `test_python_fallbacks.py`, `test_conformity/test_iso_term_manipulation.py`; old lock-in assertions on the atom-univ contract removed; ``get_item`` → ``list_item`` rename touched call sites in tests + fixtures + docs)
- **Post-2026-06-16-follow-up (F046):** 7840 passing, 1 xfailed (F068) — the full `tests/` suite after the C4 fix (+6 new C04 tests, F046 xfail flipped to pass, two `test_compiler.py` unit tests updated from the old str→MatchValue contract)
- **Regressions:** 0

### Cross-class consistency

The Phase 2 commits layered cleanly. Specific observations:

- **Two cross-cutting helpers were introduced in sequence and used consistently downstream:**
  - `clausal/logic/runtime/_seg_helpers.normalize_seg_input` (Task 11, commit 87ccfef) — added when C3 needed a shared Seg* walk point. Later picked up by Task 15 (C10 / DCG) for all phrase/sequence dispatch arms.
  - `clausal/logic/runtime/_seg_helpers.maybe_promote_to_str` (Task 13, commit 952aa88) — added when C1 needed the Liskov-aware output promotion. Used in `terms.py` (SegList.__walk__), `body_star_unify.py` (3 sites), and `list_unify.py` (3 sites). Encodes the canonical "default output is list; promote to str only when provably 1-char-strs" rule.
- **`clausal/terms.py` was touched 5 times** (F026 perf rewrite, C5 hash/eq, C2 non-det, C8 partial-term, C1 type-preservation). Each task layered on top of the previous; the F026 iterative DFS rewrite was a prerequisite for the C2 `_seglist_unify_gen` / `_segstring_unify_gen` non-det work because it removed the recursion budget concern from the splitter.
- **C5 hash-as-structural (Task 5) was intentionally reverted by C1 (Task 13)** to align with the Liskov rule. The revert is documented in commit 952aa88's "revises F017, F025" and the C5 test file was updated accordingly. No silent contradiction left in the ledger.
- **C-extension rebuild succeeded all three times** (F011 FT critical section in Task 4; C3 SegString blind-spot in `_list_unify.c` in Task 11; C1 SegList walk in `_list_unify.c` in Task 13). All three commits passed the post-build pre-existing suite.
- **C9 (Task 10) introduced its own builtin-layer helper trio** (`_as_items`, `_was_string`, `_seq_result` in `clausal/logic/builtins/lists.py`) instead of using `normalize_seg_input` / `maybe_promote_to_str`. That is the correct layering — `_as_items` returns a *items-for-iteration* list (always splitting str chars), whereas `normalize_seg_input` returns the *walked container* (preserving str). Both encode the same Liskov rule; they operate at different layers.
- **F069 closure cascaded across two tasks.** The `phrase3_rejects_segstring_rest` sub-test was closed by Task 7 (C8) when `SegString.__unify__(list)` got its walk-and-delegate path; the other two sub-tests closed in Task 15 (C10).
- **F051 / F061 / F083 / F092 closed in their natural classes** (C9, C13, C14) without needing a cascade from C3 — the `_as_items` and Seg*-registration changes are local to the builtins/inspection layer and only require that the C3 Seg* dispatch arms exist underneath.
- **No place** was found where a later task's fix contradicted an earlier task's assumption. The one *deliberate* revision (C5 by C1) is explicitly noted in the commit message and ledger.

### Findings closed by Phase 2

| Class | Closed in Phase 2 | Deferred / untested | Notes |
|-------|------------------:|--------------------:|-------|
| C1 | 5 | 0 | Type-preservation; `maybe_promote_to_str` introduced |
| C2 | 2 | 0 | Non-det unify generators |
| C3 | 8 | 0 | SegString blind-spot sweep; introduced `_seg_helpers.normalize_seg_input` |
| C4 | 1 | 0 | F046 deferred 2026-05-26, **closed 2026-06-16** (commit 6c7acf6) — narrow `head_match.py` str split + unify guard |
| C5 | 3 | 0 | Closed then partially revised by C1 (revert hash-as-structural) |
| C7 | 7 | 0 | Doc-only |
| C8 | 6 | 0 | Sequence-protocol cleanup + `PartialTermError`; cascade-closed half of F069 |
| C9 | 12 | 0 | Polymorphic mode matrix; introduced `_as_items` / `_was_string` / `_seq_result` |
| C10 | 3 | 1 (F068) | F067/F069/F070 closed; F068 deferred architectural |
| C12 | 1 | 0 | `chr(n)` range guards |
| C13 | 5 | 0 | Seg* registration with the C walker for `ground/1`; `string/1` and `atomic/1` registered |
| C14 | 7 | 0 | F092/F093/F094 closed in Phase 2 (Seg* visibility); F088/F089/F090/F091 args-of-list cluster closed in 2026-06-13 follow-up — ISO cons-cell across functor/arg/unpack with str/list Liskov symmetry; ``get_item/3`` renamed to ``list_item/3`` in the same commit |
| C15 | 1 | 0 | First-arg indexing canonicalisation |
| C16 | 1 | 0 | F011 FT critical section |
| C17 | 2 | 0 | F009 regression-guard test passes; F026 perf rewrite; F078 dead-branch deletion |
| **Total** | **65** | **1** | (C4/F046 closed in the 2026-06-16 follow-up, not Phase 2 proper) |

### Audit verdict

The strings-as-lists audit closes 65 of 66 findings (after the
2026-06-13 and 2026-06-16 follow-ups, including F078 Phase 3 closure and the
F046 C4 follow-up). The 1 remaining deferred item is:

- **1 architectural bug** (F068, design question — needs `phrase_state/3` or per-rule declaration)

The strings-as-lists contract is now consistent across:

- Core unification (str ↔ list, Seg* dispatch — `_list_unify.c` + Python fallbacks)
- SegList / SegString partial-term machinery (sequence protocol, `PartialTermError`, `__walk__`, `__unify__`, `__eq__`, `__hash__`, `__add__`)
- Polymorphic list builtins (input-type-wins rule via `_as_items` / `_was_string` / `_seq_result`)
- Higher-order builtins (same input-type-wins rule)
- DCG / phrase (input-parsing mode — F068 state-threading mode explicitly out of scope)
- Char / atom predicates (`chars.py` — SegString-aware; `chr(n)` range-guarded)
- Type-check predicates (`is_list`, `string`, `atomic`, `ground`, `callable_` — Seg*-aware; lax `callable_` documented)
- Term inspection (`copy_term`, `term_variables`, `numbervars` over Seg*; ISO cons-cell ``functor/3`` / ``arg/3`` / ``unpack/2`` with str ↔ list Liskov symmetry closing the F088-F091 args-of-list cluster in the 2026-06-13 follow-up; Clausal-named ``list_item/3`` replaces ``get_item/3``)
- First-arg indexing (dispatch-layer canonicalisation for str / list-of-1-char-strs)
- Free-threaded build (`FT_CS_BEGIN` over `PyList_GET_ITEM` loop in the str ↔ list path)

The Liskov-substitution model (str ⊂ list-of-chars) is the canonical contract. Default output is list; promotion to str only when provably all 1-char strs at construction time. The two cross-cutting helpers (`normalize_seg_input`, `maybe_promote_to_str`) and the builtins-layer trio (`_as_items`, `_was_string`, `_seq_result`) jointly encode this rule across every dispatch and result-construction site touched by the audit.
