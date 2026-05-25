# String Implementation Audit — Findings Ledger

**Spec:** [../../specs/2026-05-25-string-implementation-audit-design.md](../../specs/2026-05-25-string-implementation-audit-design.md)
**Phase 0 plan:** [../../plans/2026-05-25-string-audit-phase-0.md](../../plans/2026-05-25-string-audit-phase-0.md)
**Status:** Phase 0 in progress

## Summary by class

| Class | Title | Bug | Design-gap | Perf | Smell | Doc-only |
|-------|-------|-----|-----------:|-----:|------:|---------:|
| C1 | Type preservation | 0 | 5 | 0 | 0 | 0 |
| C2 | Non-det collapsed to first | 2 | 0 | 0 | 0 | 0 |
| C3 | SegString blind spots vs SegList | 5 | 2 | 0 | 0 | 0 |
| C4 | Head-pattern literal mismatch | 1 | 0 | 0 | 0 | 0 |
| C5 | Hash/eq asymmetries | 1 | 2 | 0 | 0 | 0 |
| C6 | Hashable vs unhashable bridges | 0 | 0 | 0 | 0 | 0 |
| C7 | Unicode / multi-codepoint | 0 | 0 | 0 | 0 | 4 |
| C8 | Partial-term short-circuits | 4 | 1 | 0 | 1 | 0 |
| C9 | Polymorphic builtin mode matrix | 3 | 4 | 0 | 0 | 0 |
| C10 | DCG / phrase interaction | 0 | 0 | 0 | 0 | 0 |
| C11 | Trail/backtracking around partials | 0 | 0 | 0 | 0 | 0 |
| C12 | Char representation drift | 0 | 0 | 0 | 0 | 0 |
| C13 | Type-check predicates | 0 | 0 | 0 | 0 | 0 |
| C14 | Term inspection drift | 0 | 0 | 0 | 0 | 0 |
| C15 | First-arg indexing on strings | 0 | 0 | 0 | 0 | 0 |
| C16 | Free-threaded build safety | 1 | 0 | 0 | 0 | 0 |
| C17 | Performance, memory, leaks | 0 | 0 | 2 | 0 | 0 |
| —   | Out-of-taxonomy | 0 | 0 | 0 | 0 | 0 |

(Counts updated at the end of each task.)

## Findings

<!-- Findings appended below, grouped by class then severity. -->

### Class C1 — Type preservation

### F018 — SegList.__walk__ expands VarSeg-bound str into char list

- **Class:** C1 (Type preservation)
- **Severity:** design-gap
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

### F033 — `_head_list_unify_output` always builds a list, never a str

- **Class:** C1 (Type preservation)
- **Severity:** design-gap
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

### F020 — SegList.__add__ / __radd__ rejects str

- **Class:** C1 (Type preservation)
- **Severity:** design-gap
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

### F042 — `_body_multi_star_unify` unbound-target branch always builds SegList

- **Class:** C1 (Type preservation)
- **Severity:** design-gap
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

### F043 — `_build_star_list` / `_build_multi_star_list` lose str type for list-of-chars and non-ground SegString stars

- **Class:** C1 (Type preservation)
- **Severity:** design-gap
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

### F016 — SegString.__unify__ returns only the first valid split

- **Class:** C2 (Non-det collapsed to first)
- **Severity:** bug
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

### F032 — `_head_list_unify_input` rejects *ground* SegString too

- **Class:** C3 (SegString blind spots vs SegList)
- **Severity:** bug
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

### F034 — `_head_list_unify_output` never walks SegString star_val

- **Class:** C3 (SegString blind spots vs SegList)
- **Severity:** design-gap
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

### F040 — `_body_multi_star_unify` rejects ground SegString target

- **Class:** C3 (SegString blind spots vs SegList)
- **Severity:** bug
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
fixture in ``tests/clausal_modules/list_edge_cases.clausal`` with four
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
- **Status:** open (folded into this audit's Phase 2 per user decision 2026-05-25; large-blast-radius candidate — fix-scope assessment in Notes will inform Phase 2 plan ordering)
- **Location:** `clausal/logic/compiler/head_match.py:253-254` (the `MatchValue` branch for str/bytes literals)
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

*Task 5 confirmed (no finding):*
- **F048** — Task 5 confirmed: compound heads containing list literals (e.g. ``Zorp(['a','b','c']) <- body``) and list-literal-only paths are subsumed by the successful elaboration + wildcard-capture + runtime-unify mechanism. Direct inspection of the compiled clause shows the parser/elaborator lifts the entire argument into a body Unify:
  ``Clause(head=Zorp(arg_0=AttVar(_0)), body=[Unify(left=AttVar(_0), right=['a','b','c'])])`` —
  the head pattern is a wildcard capture; runtime unify handles the list value, and calls with str-typed args match via the strings-as-lists contract. List-literal heads therefore work. However, compound heads and string-literal heads inherit the F046 bug: ``Quux(foo("abc")) <- body`` lifts the entire compound argument into a body Unify, but when that Call expression at runtime produces a str, the head pattern becomes a `MatchValue(Constant(...))` branch if the indexing bucket was specialized — or survives as a wildcard if unindexed. Str-literal heads in rules with non-trivial bodies (e.g. ``Quux("abc") <- Helper(1)``) expose the C4 gap directly. No separate probe for F048 (verified by direct module inspection); F046's probe covers the core issue.

### Class C5 — Hash/eq asymmetries

### F017 — SegString.__hash__ violates the Python eq/hash invariant

- **Class:** C5 (Hash/eq asymmetries)
- **Severity:** bug
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

### F019 — SegList vs SegString __eq__ asymmetry against str / list

- **Class:** C5 (Hash/eq asymmetries)
- **Severity:** design-gap
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

### F025 — SegList.__hash__ unconditional vs SegString.__hash__ conditional

- **Class:** C5 (Hash/eq asymmetries)
- **Severity:** design-gap
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

### F021 — SegList sequence protocol crashes on non-ground

- **Class:** C8 (Partial-term short-circuits)
- **Severity:** bug
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

### F022 — SegList.__contains__ silently incomplete on VarSegs

- **Class:** C8 (Partial-term short-circuits)
- **Severity:** design-gap
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

### F023 — SegString.__unify__(list) silently fails when non-ground

- **Class:** C8 (Partial-term short-circuits)
- **Severity:** bug
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

### F024 — SegString.__walk__ raises TypeError on non-str list binding

- **Class:** C8 (Partial-term short-circuits)
- **Severity:** smell
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

### F038 — `_in_iter` raises on ground SegString (no `__iter__`)

- **Class:** C8 (Partial-term short-circuits)
- **Severity:** bug
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

### F052 — `sum_list/max_list/min_list` swallow TypeError into silent failure

- **Class:** C9 (Polymorphic builtin mode matrix)
- **Severity:** bug
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

### F053 — `length(Var, N)`, `replicate/3`, `same_length` always build list output

- **Class:** C9 (Polymorphic builtin mode matrix)
- **Severity:** design-gap
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

### F054 — `_seq_result` asymmetry: list-of-1-char-str input ≠ str-promoted output

- **Class:** C9 (Polymorphic builtin mode matrix)
- **Severity:** design-gap
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

### F026 — _multi_star_splits combinatorial cost

- **Class:** C17 (Performance, memory, leaks)
- **Severity:** perf
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

*Task 1 confirmed (no finding):*
- **F014** — Task 1 confirmed: refcount discipline on `PyUnicode_Substring` allocations is balanced. Every alloc at `_variables.c:1138`/`:1165` is paired with `Py_DECREF` at `:1141`/`:1168` on the success path; error returns (`r == -1`) propagate the unbinding via standard CPython exception flow. No probe (static review only).

### Out-of-taxonomy
*(none yet)*
