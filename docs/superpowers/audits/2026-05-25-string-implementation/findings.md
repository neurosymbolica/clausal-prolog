# String Implementation Audit — Findings Ledger

**Spec:** [../../specs/2026-05-25-string-implementation-audit-design.md](../../specs/2026-05-25-string-implementation-audit-design.md)
**Phase 0 plan:** [../../plans/2026-05-25-string-audit-phase-0.md](../../plans/2026-05-25-string-audit-phase-0.md)
**Status:** Phase 0 in progress

## Summary by class

| Class | Title | Bug | Design-gap | Perf | Smell | Doc-only |
|-------|-------|-----|-----------:|-----:|------:|---------:|
| C1 | Type preservation | 0 | 2 | 0 | 0 | 0 |
| C2 | Non-det collapsed to first | 2 | 0 | 0 | 0 | 0 |
| C3 | SegString blind spots vs SegList | 0 | 1 | 0 | 0 | 0 |
| C4 | Head-pattern literal mismatch | 0 | 0 | 0 | 0 | 0 |
| C5 | Hash/eq asymmetries | 1 | 2 | 0 | 0 | 0 |
| C6 | Hashable vs unhashable bridges | 0 | 0 | 0 | 0 | 0 |
| C7 | Unicode / multi-codepoint | 0 | 0 | 0 | 0 | 4 |
| C8 | Partial-term short-circuits | 2 | 1 | 0 | 1 | 0 |
| C9 | Polymorphic builtin mode matrix | 0 | 0 | 0 | 0 | 0 |
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

*Task 2 confirmed (no finding):*
- **F030** — `SegList.__unify__(SegList)` (`terms.py:328-329`) and
  `SegString.__unify__(SegString)` (`terms.py:574-575`) both return
  `NotImplemented`, and the top-level `unify` consequently returns
  `False` for SegList-vs-SegList and SegString-vs-SegString. This is
  the deferred "Phase 6" SegList-vs-SegList unification feature
  explicitly out-of-scope per the audit spec; `wontfix: deferred`
  applies. Confirmed by direct calls.

### Class C4 — Head-pattern literal mismatch
*(none yet)*

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
