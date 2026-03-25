# SegList: Segmented Partial List

## Motivation

Clausal uses Python lists as the runtime representation of Prolog lists. This works well
when list arguments are fully bound (ground), but breaks down in the fully-relational case:
when a list contains splat variables (`*VAR`) representing variable-length unknown subsequences
at arbitrary positions. The current compiler handles multi-star patterns only against ground
lists, raising `TypeError` or silently failing otherwise.

A `SegList` is a first-class term representing a list that may have one or more variable-length
"holes" interspersed among known concrete segments — e.g. `[1, 2, *MID, 5, *TAIL]`. It is the
minimal structure needed to make list patterns fully relational.

## The Problem in Detail

Current state (all fail for unbound targets):

| Site | Failure mode |
|------|-------------|
| `_compile_multi_star_guard` | `TypeError: Cannot match multi-star pattern against unbound variable` |
| `_body_multi_star_unify` | Same explicit TypeError |
| `_body_star_unify` (construction with unbound `*VAR`) | TypeError: cannot build partial list |
| `_sequence__3` (DCG) with both S0, S unbound | Silent fail — yields no solutions |
| `Append/3` with unbound result | Silent fail |
| `In/2` with unbound list | Silent fail |

All stem from the same root: no way to represent `[concrete... *VAR concrete... *VAR ...]`
as a first-class term.

## Research Findings

- **No existing Python library** implements sequence unification with variable-length wildcards
  in arbitrary positions. `unification`, `kanren`, `pylog` all restrict partial lists to a
  variable *tail* only (standard cons+Var encoding).
- **General word equations** (sequence unification with wildcards anywhere) are PSPACE-complete
  (Makanin 1977, Plandowski 2004). However, Clausal's use case is more constrained: unifying
  a SegList against a *ground* Python list, which reduces to split-point enumeration — already
  done in `_compile_multi_star_guard` for the compile-time case.
- **Reference C extension**: `pyrsistent/pvectorcmodule.c` is the best open-source example of
  `PySequenceMethods` wiring. CPython's own `listobject.c` is authoritative.
- **Clausal's existing C extension** (`clausal/logic/variables/`) already provides the
  `__walk__`/`__unify__`/`__occurs_check__` hook protocol used by `DictTerm`/`SetTerm`
  (introduced in Dicts/Sets Phase 2). SegList reuses the same protocol.

## Data Structure

A `SegList` is a flat list of alternating segments:

```python
@dataclass
class ConcreteSeg:
    elements: list  # may contain Var instances as individual element vars

@dataclass
class VarSeg:
    var: Var  # splat var — represents a variable-length subsequence
```

```python
class SegList:
    segments: list[ConcreteSeg | VarSeg]
```

Examples:

| Clausal pattern | SegList |
|----------------|---------|
| `[1, 2, *T]` | `SegList([ConcreteSeg([1, 2]), VarSeg(T)])` |
| `[*A, 5, *B]` | `SegList([VarSeg(A), ConcreteSeg([5]), VarSeg(B)])` |
| `[*H, X, *M, Y, *T]` | `SegList([VarSeg(H), ConcreteSeg([X]), VarSeg(M), ConcreteSeg([Y]), VarSeg(T)])` |
| `[*A, *B]` | `SegList([VarSeg(A), VarSeg(B)])` |

A plain Python list is the special case with zero VarSegs.

A SegList is **ground** when every VarSeg's var is bound to a concrete list (recursively). When
ground, a SegList can be **flattened** to a plain Python list.

The invariant maintained by `walk()`:
- No two adjacent ConcreteSegs (merged on walk)
- No VarSeg whose var dereferences to a concrete list (collapsed on walk)
- A fully-ground SegList normalizes to a plain Python list on walk

## Use Cases as Tests

### 1. Construction — single-star with unbound tail

```python
# Python
def test_construction_unbound_tail():
    T, R = Var(), Var()
    H = 1
    trail = Trail()
    # R is [H, *T] with T unbound
    # Should bind R to SegList([ConcreteSeg([1]), VarSeg(T)])
    sl = SegList([ConcreteSeg([H]), VarSeg(T)])
    unify(R, sl, trail)
    assert is_seglist(deref(R))
    # Later, T gets bound
    unify(T, [2, 3], trail)
    assert walk_seglist(deref(R)) == [1, 2, 3]
```

```clausal
% .clausal
BuildPartial(H, T, R) <- R is [H, *T].

test_build_partial :-
    BuildPartial(1, T_, R_),
    R_ = [1 | T_],    % R_ is a partial list
    T_ = [2, 3],
    R_ = [1, 2, 3].   % now fully ground
```

### 2. Body multi-star with unbound target

```python
# Python
def test_body_multi_star_unbound():
    A, B, L = Var(), Var(), Var()
    trail = Trail()
    # [*A, *B] is L with L unbound
    # Should bind L to SegList([VarSeg(A), VarSeg(B)])
    results = list(run_goal(Is([StarUnpack(A), StarUnpack(B)], L), trail))
    assert len(results) == 1
    assert is_seglist(deref(L))
    # Then unify L against [1, 2, 3] — should backtrack splits
    splits = list(unify_seglist(deref(L), [1, 2, 3], trail))
    assert splits == [
        ({A: [], B: [1,2,3]}),
        ({A: [1], B: [2,3]}),
        ({A: [1,2], B: [3]}),
        ({A: [1,2,3], B: []}),
    ]
```

```clausal
BodySplit(L, A, B) <- [*A, *B] is L.

test_body_split_construction :-
    BodySplit(L_, _, _),
    L_ = [1, 2],      % unify partial list against [1,2]
    findall(A_-B_, BodySplit([1,2], A_, B_), Splits),
    Splits = []-[1,2] ; [1]-[2] ; [1,2]-[].
```

### 3. Head-position multi-star with unbound argument

```clausal
Split([*A, *B], A, B).

test_split_unbound :-
    Split(LIST_, A_, B_),   % LIST_ unbound
    % LIST_ is now SegList([VarSeg(A_), VarSeg(B_)])
    LIST_ = [1, 2, 3],      % unify → enumerate splits
    A_ = [1], B_ = [2, 3].  % one solution
```

### 4. Multi-star sandwich with element vars in concrete segment

```python
def test_sandwich_unbound():
    X, A, B = Var(), Var(), Var()
    sl = SegList([VarSeg(A), ConcreteSeg([X]), VarSeg(B)])
    # Unify [*A, X, *B] against [1, 2, 3]
    solutions = unify_solutions(sl, [1, 2, 3], trail)
    # A=[], X=1, B=[2,3]
    # A=[1], X=2, B=[3]
    # A=[1,2], X=3, B=[]
    assert len(solutions) == 3
```

```clausal
Around([*A, X, *B], X, A, B).

test_around_unbound :-
    Around(LIST_, 2, A_, B_),
    LIST_ = [1, 2, 3],
    A_ = [1], B_ = [3].
```

### 5. DCG Sequence with both ends unbound

```python
def test_sequence_both_unbound():
    S0, S = Var(), Var()
    trail = Trail()
    # phrase(Sequence([a, b, c]), S0, S) with both S0, S unbound
    # Should bind S0 to SegList([ConcreteSeg([a,b,c]), VarSeg(S)])
    list(solve(phrase(sequence([a, b, c]), S0, S), trail))
    walked = walk(S0)
    assert is_seglist(walked)
    assert walked == SegList([ConcreteSeg([a, b, c]), VarSeg(deref(S))])
```

```clausal
test_sequence_unbound :-
    phrase(Sequence([hello, world]), S0_, S_),
    S0_ = [hello, world | S_].   % S0_ is partial list with S_ as tail
```

### 6. Append with unbound second argument

```clausal
test_append_partial :-
    append([1, 2], Y_, Z_),
    % Z_ should be SegList([ConcreteSeg([1,2]), VarSeg(Y_)])
    Y_ = [3, 4],
    Z_ = [1, 2, 3, 4].

test_append_partial_then_unify :-
    append([1, 2], Y_, Z_),
    Z_ = [1, 2, 3],       % unify result against ground list
    Y_ = [3].             % Y_ gets determined by unification
```

```python
def test_append_unbound_suffix():
    Y, Z = Var(), Var()
    trail = Trail()
    # append([1, 2], Y, Z) with Y unbound
    solutions = query(Append([1, 2], Y, Z), trail)
    assert len(solutions) == 1
    walked_z = walk(Z)
    assert is_seglist(walked_z)
    # Unify Z against [1, 2, 3, 4] → Y = [3, 4]
    unify(walked_z, [1, 2, 3, 4], trail)
    assert walk(Y) == [3, 4]
```

### 7. In/2 (member) with unbound list

```clausal
test_member_unbound_list :-
    In(5, LIST_),             % LIST_ unbound
    % LIST_ = SegList([VarSeg(_), ConcreteSeg([5]), VarSeg(_)])
    LIST_ = [1, 2, 5, 3],
    true.                     % succeeds — 5 is in [1,2,5,3]

test_member_enumerate_positions :-
    findall(I_-L_, (In(5, L_), L_ = [1,2,5,3,5], nth0(I_, L_, 5)), Pairs),
    Pairs = [2-[1,2,5,3,5], 4-[1,2,5,3,5]].
```

### 8. Walk/normalization when vars bind

```python
def test_walk_normalizes():
    A, B = Var(), Var()
    sl = SegList([ConcreteSeg([1]), VarSeg(A), ConcreteSeg([4]), VarSeg(B)])
    trail = Trail()
    unify(A, [2, 3], trail)
    unify(B, [], trail)
    # After walk: should normalize to plain Python list [1, 2, 3, 4]
    assert walk(sl) == [1, 2, 3, 4]
```

### 9. SegList as predicate argument (round-trip)

```clausal
ProcessList([*PREFIX, LAST], PREFIX, LAST) <-
    integer(LAST).

test_process_partial :-
    ProcessList(LIST_, PREFIX_, LAST_),
    LIST_ = [1, 2, 3],
    LAST_ = 3,
    PREFIX_ = [1, 2].
```

### 10. Concat via ++ on SegLists

```python
def test_seglist_concat():
    T = Var()
    sl = SegList([ConcreteSeg([1, 2]), VarSeg(T)])
    # sl ++ [3, 4] = SegList([ConcreteSeg([1,2]), VarSeg(T), ConcreteSeg([3,4])])
    result = sl + [3, 4]
    assert isinstance(result, SegList)
    unify(T, [99], Trail())
    assert walk(result) == [1, 2, 99, 3, 4]
```

---

## API Design: Drop-In Replacement

When a SegList is **ground**, all Python list operations work identically:

| Operation | Ground | Partially unbound |
|-----------|--------|-------------------|
| `len(sl)` | ✓ | raises `UnboundError` |
| `sl[i]` | ✓ | ✓ if index is in a resolved ConcreteSeg, else raises |
| `iter(sl)` | ✓ | raises `UnboundError` |
| `x in sl` | ✓ | ✓ for elements provably in ConcreteSegs; uncertain otherwise |
| `sl + other` | ✓ | ✓ → new SegList (lazy) |
| `sl == other` | ✓ | deferred (structural equality via unification) |
| `list(sl)` | ✓ → flattens | raises `UnboundError` |
| `sl[i:j]` | ✓ | may raise |

Key design rule: **when ground, SegList is indistinguishable from a Python list**. The
`__iter__`, `__len__`, `__getitem__` implementations call `self.to_list()` after walking, so any
code that iterates a ground SegList works without changes.

The `__walk__` hook (called by the C `deref`/`walk` machinery) normalizes the SegList after
each variable binding. When the last VarSeg binds to a concrete list, `__walk__` returns a
plain Python list — so the SegList "disappears" and downstream code sees a normal list.

---

## Implementation Plan

The phases are ordered so that SegList *consumption* (teaching existing code to accept a
SegList it receives) is complete before SegList *creation* (changing code to produce SegLists
instead of failing). This means the highest-regression-risk change (`_head_list_unify_output`)
lands into a codebase that can already handle the values it will start producing.

### Phase 1 — Core `SegList` type (pure Python, no compiler changes) ✅ DONE

**File**: `clausal/terms.py` (alongside `DictTerm`, `SetTerm`)

1. Define `ConcreteSeg(elements: list)` and `VarSeg(var: Var)` as simple dataclasses.
2. Define `SegList(segments: list[ConcreteSeg | VarSeg])` with:
   - `__walk__(self)` — call `walk()` on each VarSeg var and each element inside ConcreteSegs;
     if a VarSeg's var dereferences to a plain list, inline its elements into the adjacent
     concrete region; if it dereferences to another SegList, inline that SegList's segments;
     merge all adjacent ConcreteSegs; if no VarSegs remain, return a plain Python list.
     See the worked example in §Gotchas EC-3 for the nested-SegList case.
   - `is_ground(self)` — True if `__walk__()` returns a plain list
   - `to_list(self)` — calls `__walk__()`; asserts result is a plain list; returns it
   - `__occurs_check__(self, var)` — recurse into both ConcreteSeg elements and VarSeg vars
   - Sequence protocol (delegating to `to_list()` when ground):
     `__len__`, `__iter__`, `__contains__`, `__getitem__`, `__add__`, `__radd__`, `__eq__`
   - `__repr__` — readable syntax like `[1, *_A3, 5, *_B7]`; implement from the start, not
     later — test failure messages are unreadable without it
3. The C `do_unify` hook protocol requires no changes — it already dispatches to `__walk__`,
   `__unify__`, `__occurs_check__` via `PyObject_GetAttrString` for any Python object.
4. **Tests**: `tests/test_seglist_core.py` — construction, walk/normalization (including nested
   SegList inlining), ground detection, sequence protocol delegation, `__add__` concat,
   `__repr__`.

### Phase 2 — Unification protocol ✅ DONE (implemented alongside Phase 1)

**File**: `clausal/terms.py`

Both items were implemented as part of Phase 1:

**`_seglist_unify_gen(seglist, target_list, trail)` — the non-deterministic generator.**
This is the core algorithm, a direct runtime port of `_multi_star_splits` + the innermost body
of `_compile_multi_star_guard`. `_multi_star_splits` was added directly to `clausal/terms.py`
(not a separate `list_utils.py`) so both the compile-time guard generator and this runtime
generator can import it without circular imports. The compiler's own copy in `compiler.py` still
exists; Phase 3 step 3 should import from `terms.py` instead and remove the duplicate.

```python
def _seglist_unify_gen(seglist, target_list, trail):
    """Yield True once per valid split of target_list across seglist's VarSegs.
    seglist must be walk()-normalised before calling."""
    min_len = sum(len(s.elements) for s in seglist.segments
                  if isinstance(s, ConcreteSeg))
    n = len(target_list)
    if n < min_len:
        return
    n_stars = sum(1 for s in seglist.segments if isinstance(s, VarSeg))
    remainder = n - min_len
    for split in _multi_star_splits(n_stars, remainder):
        mark = trail.mark()
        ok = True
        pos = 0
        si = 0
        for seg in seglist.segments:
            if isinstance(seg, VarSeg):
                sz = split[si]; si += 1
                ok = ok and unify(seg.var, target_list[pos:pos+sz], trail)
                pos += sz
            else:
                for elem in seg.elements:
                    ok = ok and unify(elem, target_list[pos], trail)
                    pos += 1
            if not ok:
                break
        if ok:
            yield True
        trail.undo(mark)
```

**`SegList.__unify__(self, other, trail)` — deterministic cases only.**
`__unify__` is called by C `do_unify` as a regular bool-returning function (not a generator —
see §Gotchas). It handles only the cases where there is at most one valid split:

- `other` is a `Var` → return `NotImplemented` (C handles Var binding before reaching `__unify__`)
- `other` is a plain list → call `_seglist_unify_gen(walk(self), other, trail)`, take the first
  solution and return True; if there are multiple valid splits (n_stars ≥ 2 with remainder > 0)
  and more than one exists, return True for the first split only and document the limitation
  (EC-1). Callers that need all solutions must use `_seglist_unify_gen` in a `for` loop.
- `other` is a `SegList` → defer to Phase 6; return `NotImplemented` for now.
- anything else → return `NotImplemented`

**Tests**: These tests were included in `tests/test_seglist_core.py` rather than a separate
`test_seglist_unify.py` — all `_seglist_unify_gen` and `__unify__` cases from §Use Cases as
Tests are covered there (63 tests total).

### Phase 3 — Compiler: SegList *consumption* (zero regression risk) ✅ DONE

Teach every place that receives a list argument to also accept a SegList. This phase makes no
change to how SegLists are created — it only adds new code paths that fire when a SegList
arrives. The full test suite should pass unchanged after this phase.

**File**: `clausal/logic/compiler.py`

1. **`_head_list_unify_input`** — normalise SegList at entry: call `d.__walk__()`; if the
   result is a plain list, proceed as normal; if it's still a SegList (non-ground),
   return `False`. Non-ground SegList-vs-single-star unification is deferred to Phase 6
   (returning `None` to trigger output mode would be wrong — the target is not an unbound Var).

2. **`_body_star_unify`** — add an `isinstance(d, SegList)` branch that delegates directly
   to `_head_list_unify_input`, covering both ground (deconstruction) and non-ground (fail)
   cases uniformly.

3. **`_compile_multi_star_guard`** — emit a normalisation node immediately after the
   `deref` assignment:
   ```python
   if isinstance(_d, SegList):
       _d = _d.__walk__()
   ```
   A ground SegList becomes a plain list and the existing `isinstance(list)` loop fires.
   A non-ground SegList stays a SegList, falls past the `isinstance(list)` check →
   no solutions (graceful fail, no error). This avoids duplicating the loop AST.

4. **`_multi_star_splits`** — duplicate removed from `compiler.py`; imported from
   `clausal.terms`. `SegList`, `ConcreteSeg`, `VarSeg`, `_seglist_unify_gen` added to
   both simple-mode and trampoline-mode compiled-predicate globals dicts.

5. **Tests**: `tests/test_seglist_passthrough.py` (11 tests) — ground SegList inputs to
   single-star head patterns (`Append`, `Last`), multi-star head patterns (`Split`, `Split3`,
   `Around`), body-position Is patterns (`HeadTail`, `InitLast`), SegList concat as arg,
   and non-ground SegList to multi-star (confirmed: no solutions, no error).

### Phase 4 — Compiler: SegList *creation* (highest regression risk) ✅ DONE

Change the compiler to produce SegLists instead of failing when a star var is unbound. Run the
full test suite after each sub-step.

**File**: `clausal/logic/compiler.py`

**4a. `_head_list_unify_output`** — the highest-risk change. Change:
```python
if is_var(s):
    return False   # was: suppresses yield
```
to:
```python
if is_var(s):
    sl = SegList([ConcreteSeg([deref(v) for v in before_vals]),
                  VarSeg(s),
                  ConcreteSeg([deref(v) for v in after_vals])])
    return unify(target, sl, trail)
```
Run the full test suite immediately. Expect regressions in `Append`, `Last`, `Reverse` reverse
mode — these were previously suppressed, now they yield SegLists. Fix each regression by
updating the relevant test expectations OR by verifying the new SegList-yielding behaviour is
correct and updating the test to reflect it.

**4b. `_body_star_unify`** — when target is an unbound Var, `_head_list_unify_output` now
handles construction (picked up transitively). No change needed here if 4a is done first.
Verify with `test_body_star_decon.py`.

**4c. `_body_multi_star_unify`** — replace the TypeError for unbound Var with SegList
construction:
```python
if is_var(d):
    sl = SegList([VarSeg(deref(var)) if kind == "star"
                  else ConcreteSeg([deref(v) for v in vals])
                  for kind, vals in segments
                  for var in ([vals] if kind == "star" else [])])
    # simpler: build directly from segments
    segs = []
    for kind, val in segments:
        if kind == "star":
            segs.append(VarSeg(deref(val)))
        else:
            segs.append(ConcreteSeg([deref(v) for v in val]))
    return unify(d, SegList(segs), trail), but this is a generator...
```
Note: `_body_multi_star_unify` is a **generator** (yields True per solution), not a bool
function. For the unbound Var case, it should `yield True` once after binding the target to the
SegList, then stop:
```python
if is_var(d):
    segs = [VarSeg(deref(v)) if k == "star"
            else ConcreteSeg([deref(e) for e in v])
            for k, v in segments]
    mark = trail.mark()
    if unify(d, SegList(segs), trail):
        yield True
    trail.undo(mark)
    return
```

**4d. `_build_star_list`** — the runtime function emitted by `term_to_ast_expr` for single-star
body construction. Change:
```python
if is_var(star_d):
    raise TypeError(...)    # was
```
to:
```python
if is_var(star_d):
    return SegList([ConcreteSeg(before), VarSeg(star_d), ConcreteSeg(after)])
```

**4e. Multi-star body construction** — `term_to_ast_expr` currently finds only the first
`StarUnpack` in a list (uses `next(i for ...)`). For multi-star body lists, add a
`_build_multi_star_list(segments_tuple)` runtime helper (mirrors `_body_multi_star_unify`'s
segment format) and update `term_to_ast_expr` to use `_parse_star_segments` (already exists)
instead of the single-index approach.

**Tests**: extend `tests/test_body_star_decon.py` and `tests/test_search.py`
`TestMultiStarPatterns` with unbound-target cases.

### Phase 5 — Builtin integration

**File**: `clausal/logic/builtins/lists.py`, `clausal/logic/builtins/dcg.py`

Update builtins to construct SegLists for unbound arguments. In each case, the builtin itself
is a generator — so calling `_seglist_unify_gen` in a `for` loop is natural.

Also add the `as_list(x)` helper (using `walk()`, not `deref()`) to a shared location and
replace `d = deref(x); isinstance(d, list)` patterns throughout builtins:

```python
def as_list(x):
    w = walk(x)
    if isinstance(w, list): return w
    if isinstance(w, SegList): return w.to_list() if w.is_ground() else None
    return None
```

| Builtin | Change |
|---------|--------|
| `Append/3` | When L2 unbound: construct `SegList([ConcreteSeg(L1_val), VarSeg(Var())])`, unify with L3 and bind L2 to the fresh var |
| `In/2` | When list arg unbound: construct `SegList([VarSeg(Var()), ConcreteSeg([deref(elem)]), VarSeg(Var())])`, unify with list arg; yields one solution |
| `Sequence//3` | When both S0, S unbound: construct `SegList([ConcreteSeg(lst_val), VarSeg(deref(s))])`, unify with S0 |
| `Length/2` | No change to existing modes; defer both-unbound case |
| `Select/3` | When list unbound: `SegList([VarSeg(Var()), ConcreteSeg([deref(elem)]), VarSeg(Var())])` |

Lower-priority (skip for now): `Flatten`, `Permutation`, `SumList`, `MaxList`, `MinList`,
`GetItem` with unbound list.

**Tests**: `tests/test_seglist_builtins.py` + extensions to existing builtin test files.

### Phase 6 — SegList-vs-SegList unification

When two SegLists are unified against each other. Practical cases:

- **One side is ground** — `__unify__` / `_seglist_unify_gen` already handle this
- **Anchored from both ends** — peel matching ConcreteSegs from each end; if both sides have
  the same leading/trailing concrete elements, the middle becomes a smaller SegList-vs-SegList
  problem. If after peeling only VarSeg-vs-VarSeg remains in the middle, unify the two star
  vars together (one becomes an alias of the other)
- **Ambiguous middle** — defer; raise `NotImplementedError` with a clear message

Implement `SegList.__unify__` for the SegList-vs-SegList case using the anchored algorithm.
**Tests**: `tests/test_seglist_seglist.py`.

### Phase 7 — C extension (optimization, defer until profiling)

**File**: `clausal/logic/variables/` (existing C extension)

Move the hot path to C only after profiling shows it matters:

1. `seglist_walk(seglist)` — inline `__walk__` in C
2. A C iterator object for `_seglist_unify_gen` with `tp_iternext` carrying split-point state
   (analogous to CPython's `range_iterator`)

**Reference**: `pyrsistent/pvectorcmodule.c` for `PySequenceMethods` wiring; CPython
`Objects/listobject.c`; existing `clausal/logic/variables/` for hook protocol.

---

## Integration with Existing Code

| Component | Change needed | Phase |
|-----------|---------------|-------|
| `clausal/terms.py` | Add `ConcreteSeg`, `VarSeg`, `SegList` | 1 |
| `clausal/logic/list_utils.py` (new) | `_multi_star_splits` moved here from compiler.py | 3 |
| `clausal/logic/compiler.py` | `_head_list_unify_input`, `_compile_multi_star_guard` (consumption) | 3 |
| `clausal/logic/compiler.py` | `_head_list_unify_output`, `_body_multi_star_unify`, `_build_star_list`, `_build_multi_star_list` (creation) | 4 |
| `clausal/logic/builtins/lists.py` | `Append`, `In`, `Length`, `Select` + `as_list` helper | 5 |
| `clausal/logic/builtins/dcg.py` | `_sequence__3` | 5 |
| `clausal/logic/variables/` (C) | No changes required for Phases 1–6; optional optimisation in Phase 7 | 7 |

`as_list(x)` helper — must use `walk()`, not `deref()`:

```python
def as_list(x):
    """Walk x and return a Python list, or None if partially unbound."""
    w = walk(x)           # walk calls __walk__, normalising ground SegLists to plain list
    if isinstance(w, list):
        return w
    if isinstance(w, SegList):
        return None       # partially unbound; caller handles separately
    return None
```

---

## What the C Extension Is (and Isn't) Needed For

The C extension is **not** needed for correctness. A pure Python `SegList` with `__walk__` and
`__unify__` hooks gives correct fully-relational behaviour.

The C extension becomes worthwhile when:
- `unify(SegList, large_ground_list, trail)` is called in a tight loop (e.g. DCG parsing over
  long token streams)
- The `__walk__` normalization overhead is measurable

Phase 6 (C extension) should be deferred until Phase 4 is complete and profiling identifies a
hotspot.

---

## Gotchas and Edge Cases

### CRITICAL: `__unify__` is a bool-returning method, not a generator

The Phase 2 description says `__unify__` should "yield after each successful assignment for
backtracking". **This is wrong.** The C `do_unify` hook calls `__unify__(other, trail)` as a
regular function and reads its return value with `PyObject_IsTrue`. It does not iterate it.
There is no way to return multiple solutions from `__unify__`.

**What `__unify__` can handle (deterministic cases only):**
- `SegList.__unify__(other_seglist, trail)` — structural check when both have the same segment
  shape (same number/position of VarSegs). Returns True/False.
- `SegList.__unify__(plain_list, trail)` — **only** when there is exactly zero or one valid
  split (e.g. a SegList with a single trailing VarSeg `[1, 2, *T]` unified against `[1, 2, 3,
  4]` — unambiguous, binds T to `[3, 4]`, returns True). Returns False if lengths or fixed
  elements don't match.
- Return `NotImplemented` for cases it can't handle deterministically — the C caller falls
  through to `==` comparison.

**The non-deterministic case (multiple splits) requires a separate generator:**

```python
def _seglist_unify_gen(seglist, target_list, trail):
    """Generator: yields True once per valid split-point assignment.
    Caller wraps in a for-loop and handles backtracking (same as _body_multi_star_unify).
    """
    # The split-point enumeration logic from _compile_multi_star_guard,
    # but operating on runtime SegList segments instead of compile-time patterns.
    for split in _compute_splits(seglist.segments, len(target_list)):
        mark = trail.mark()
        ok = True
        for seg, sublist in zip(seglist.segments, split):
            if isinstance(seg, VarSeg):
                ok = ok and unify(seg.var, sublist, trail)
            else:  # ConcreteSeg
                for elem, val in zip(seg.elements, sublist):
                    ok = ok and unify(elem, val, trail)
                if not ok:
                    break
        if ok:
            yield True
        trail.undo(mark)
```

This generator is called explicitly from:
1. Compiler-generated head-pattern code (new `elif isinstance(_d, SegList)` branch — see below)
2. `_body_multi_star_unify` when target is a SegList (not just a ground list)
3. Any builtin that may encounter a SegList argument

### Compiler-generated head code needs a SegList branch

`_compile_multi_star_guard` currently generates:

```python
_d = deref(_cap)
if is_var(_d): _head_multi_star_error()
if isinstance(_d, list):
    _n = len(_d)
    if _n >= <min_len>:
        for _sp0 in range(...): ...
```

When a SegList is passed as a predicate argument (e.g. constructed by a caller and passed to
`foo([*A, *B])`), `_d` will be a SegList — it falls through with no solution. A third branch
is needed:

```python
elif isinstance(_d, SegList):
    for _ in _seglist_unify_gen(<pattern_seglist>, _d, trail):
        <body_stmts>
```

The pattern SegList is constructed from the compile-time segments at the same time as the
compile-time loop is generated — i.e. the compiler emits *both* the `isinstance(list)` loop
*and* the `isinstance(SegList)` generator call as branches of the same `if`.

The same applies to **single-star head patterns** (via `_head_list_unify_input`): if the
captured value is a SegList, `isinstance(d, list)` is False and the pattern silently fails.
`_head_list_unify_input` needs an `elif isinstance(d, SegList)` branch that calls
`_seglist_unify_gen`.

### `_build_star_list` runtime function must be updated

`term_to_ast_expr` emits `_build_star_list(before, star, after)` calls for single-star list
construction. Currently (around line 279-295 in compiler.py), this function raises TypeError
when `star` is an unbound Var. This must be changed to construct and return a SegList:

```python
def _build_star_list(before, star, after):
    star_d = deref(star)
    if isinstance(star_d, list):
        return before + star_d + after      # existing fast path
    if is_var(star_d):
        return SegList([ConcreteSeg(before), VarSeg(star_d), ConcreteSeg(after)])
    raise TypeError(...)
```

For multi-star body construction (`term_to_ast_expr` currently only handles single-star),
a new `_build_multi_star_list(segments_tuple)` runtime helper is needed, where `segments_tuple`
is the same `[("fixed", [...]), ("star", var), ...]` format used by `_body_multi_star_unify`.

### `deref` vs `walk` — use `walk` for SegList normalization

`deref(x)` follows Var chains but does NOT call `__walk__`. A variable bound to a SegList
returns the SegList from `deref()`, never a plain list. Only `walk(x)` calls `__walk__()` and
can return a normalized plain list.

The `as_list` helper in the Integration section uses `deref()` — **this is wrong for the
normalization case**. The correct version:

```python
def as_list(x):
    """Walk x and return a Python list, or None if not yet ground."""
    w = walk(x)           # NOT deref — walk calls __walk__ on SegList
    if isinstance(w, list):
        return w
    if isinstance(w, SegList):
        return None       # partially unbound; caller must handle
    return None
```

Builtins that want to check "is this a ground list?" should call `walk()` then check
`isinstance`. Builtins that just want to follow Var chains cheaply (not normalize) can keep
using `deref()`.

### `__walk__` must also walk elements within ConcreteSegs

ConcreteSeg elements can be individual logic variables (e.g. `ConcreteSeg([X])` where X is a
Var). `__walk__` must call `walk()` on each element:

```python
def __walk__(self):
    from .logic.variables import walk, is_var
    new_segs = []
    for seg in self.segments:
        if isinstance(seg, VarSeg):
            v = walk(seg.var)
            if isinstance(v, list):
                # Resolved — inline into adjacent ConcreteSeg
                if new_segs and isinstance(new_segs[-1], ConcreteSeg):
                    new_segs[-1] = ConcreteSeg(new_segs[-1].elements + v)
                else:
                    new_segs.append(ConcreteSeg(v))
                continue
            if isinstance(v, SegList):
                # Inline nested SegList segments
                new_segs.extend(v.segments)
                continue
            new_segs.append(VarSeg(v))  # v is a (possibly different) Var
        else:
            walked_elems = [walk(e) for e in seg.elements]
            if new_segs and isinstance(new_segs[-1], ConcreteSeg):
                new_segs[-1] = ConcreteSeg(new_segs[-1].elements + walked_elems)
            else:
                new_segs.append(ConcreteSeg(walked_elems))
    # Merge done; check if fully ground
    if all(isinstance(s, ConcreteSeg) for s in new_segs):
        return [e for s in new_segs for e in s.elements]
    return SegList(new_segs)
```

### VarSeg var may itself bind to a SegList (not just a plain list)

If `append([1,2], Y, Z)` constructs `Z = SegList([ConcreteSeg([1,2]), VarSeg(Y)])` and Y is
later bound to another SegList (e.g. from a second append call), `__walk__` must inline the
nested SegList's segments — the `isinstance(v, SegList): new_segs.extend(v.segments)` branch
above handles this. Without it, you get a SegList containing a VarSeg whose var is itself bound
to a SegList — `walk()` would not fully normalize.

### `__occurs_check__` must recurse into ConcreteSeg elements

Standard occurs check: `unify(X, [X])` must fail. With SegList, the Var can appear inside a
ConcreteSeg element, not just as a VarSeg var:

```python
def __occurs_check__(self, var):
    from .logic.variables import occurs_check
    for seg in self.segments:
        if isinstance(seg, VarSeg):
            if occurs_check(var, seg.var):
                return True
        else:
            if any(occurs_check(var, e) for e in seg.elements):
                return True
    return False
```

### `term_to_ast_expr` multi-star case currently only handles single-star

The current `term_to_ast_expr` list branch finds the **first** `StarUnpack` and treats the rest
of the list as `after`. For `[*A, X, *B]` it would misidentify the structure. Before changing
`term_to_ast_expr` for SegList construction, verify (or fix) the multi-star case — it should
use `_parse_star_segments` (already exists) rather than `next(i for ... StarUnpack ...)`.

### Trail interactions for `_seglist_unify_gen`

The generator must mark/undo the trail **per split attempt**, not once for the whole
enumeration. Pattern from `_body_multi_star_unify`:

```python
for split in ...:
    mark = trail.mark()
    ok = (unify(...) and unify(...) and ...)
    if ok:
        yield True          # caller runs body
    trail.undo(mark)        # undo whether ok or not, before next iteration
```

`trail.undo(mark)` is safe even if no bindings were made (idempotent).

### `isinstance(x, list)` guards in builtins — systematic audit needed

~15 builtins check `isinstance(d, list)` after a `deref()`. None of them handle SegList. Two
approaches:

1. **Normalize eagerly**: change the `d = deref(x)` line to `d = walk(x)`. If `d` is a ground
   SegList, `walk` returns a plain list and the rest of the builtin works unchanged. If `d` is a
   partially-unbound SegList, `walk` returns a SegList and the `isinstance(d, list)` check
   fails — the builtin correctly "doesn't know" the answer yet.

2. **Use `as_list`**: replace `d = deref(x); isinstance(d, list)` patterns with `d = as_list(x)`
   (but `as_list` must use `walk`, not `deref` — see above).

Option 1 is simpler for the ground case; option 2 is more explicit. Either way, the **partial
(non-ground SegList) case** needs bespoke handling per builtin — there is no universal fallback.

---

## Edge Cases Revealed by Existing Tests

### EC-1: Lazy non-determinism is lost through `=` body goals

The most subtle semantic issue. When a SegList with multiple VarSegs is created by one goal and
later unified against a ground list via a `=` body goal (compiled as `if unify(...)`), the
`__unify__` hook is single-shot — only the first valid split is found and all others are
silently discarded.

Concrete example from `test_body_star_decon.py` `BodySplit` pattern:

```clausal
BodySplit(LIST, A, B) <- [*A, *B] is LIST.

% This works (non-determinism from the Is-goal directly):
test1 :- BodySplit([1,2,3], A, B).      % → 4 solutions via _body_multi_star_unify generator

% This loses solutions (non-determinism deferred via =):
test2 :- BodySplit(L, A, B), L = [1,2,3].  % L gets SegList, then unify() called once
```

**Recommended approach for Phase 1-4**: document this limitation explicitly. The non-deterministic
case must be expressed through direct Is-goals or head patterns, not by binding a multi-VarSeg
SegList and then unifying via `=`. Most real use cases (DCG `Sequence`, `Append` with unbound
suffix, `In`) are deterministic or single-VarSeg and avoid this problem.

If full lazy non-determinism via `=` is needed (Phase 5+), the options are:

a. **`__unify_gen__` protocol**: add a second C hook `__unify_gen__(other, trail)` that returns
   a generator; `do_unify` checks for this before `__unify__`. Requires C extension change.
b. **Compile `=` body goals as for-loops**: emit `for _ in _unify_or_gen(lhs, rhs, trail):
   body` where `_unify_or_gen` is a generator that wraps `unify()` for non-SegList cases and
   calls `_seglist_unify_gen` for SegList cases. Adds a runtime isinstance check to every `=`
   goal — measure overhead first.

### EC-2: Regression risk — `_head_list_unify_output` behavior change

`_head_list_unify_output` currently returns `False` when the star var is unbound (line ~268):
```python
s = deref(star_val)
if is_var(s):
    return False    # ← currently suppresses the yield
```

Changing this to construct a SegList means every predicate with a star in its output-mode head
will now yield a SegList value instead of being suppressed. This is the correct semantics, but
it is a **behaviour change** for existing predicates.

Specifically: `_wrap_yields_with_output_guards` wraps every yield with an output guard call.
For `Append([HEAD, *TAIL], RHS, [HEAD, *REST]) <- Append(TAIL, RHS, REST)`, in the recursive
case, REST may still be unbound at the yield point. Currently: yield suppressed. With SegList:
yield with `REST_arg = SegList([ConcreteSeg([HEAD_val]), VarSeg(REST)])`.

**Before changing `_head_list_unify_output`**, audit all predicates that have star patterns
in output-position head args and verify the SegList-yielding behaviour is correct for each.
The regression test suite (`test_search.py`, `test_body_star_decon.py`) will catch most cases,
but a deliberate audit is warranted before the change.

### EC-3: Chained Is-goals produce nested SegLists

From `body_star.clausal` `Second` predicate:
```clausal
Second(LIST, X) <- [_, *T] is LIST, [X, *_] is T.
```

When `LIST` is unbound:
1. `[_, *T] is LIST` → LIST = `SegList([ConcreteSeg([anon1]), VarSeg(T)])`
2. `[X, *_] is T` — T is still unbound → T = `SegList([ConcreteSeg([X]), VarSeg(anon2)])`

Now LIST contains a VarSeg(T) and T is itself a SegList. When LIST later unifies against
`[1, 2, 3]`, `__walk__` must inline the nested SegList:

```
walk(LIST)
→ SegList([ConcreteSeg([anon1]), VarSeg(T)])
→ walk T → SegList([ConcreteSeg([X]), VarSeg(anon2)])
→ inline: SegList([ConcreteSeg([anon1]), ConcreteSeg([X]), VarSeg(anon2)])
→ merge adjacent ConcreteSegs: SegList([ConcreteSeg([anon1, X]), VarSeg(anon2)])
```

This is the "VarSeg var binds to SegList" path in `__walk__` — already noted in the gotchas
section. The key thing this test reveals is that the merging must happen **during `__walk__`**,
before the result is used for unification. If `__walk__` doesn't inline nested SegLists, the
unification with `[1,2,3]` will fail because `SegList.__unify__` doesn't expect `VarSeg(T)`
where T is itself a SegList.

**Corollary**: `_seglist_unify_gen` must call `walk()` (not `deref()`) on the SegList before
beginning enumeration, to get a fully normalized segment structure.

### EC-4: Single-star Is-goal `_body_star_unify` with SegList target

The plan focuses on `_body_multi_star_unify` for the unbound case, but `_body_star_unify`
(single-star) also hits the same wall. From `body_star.clausal` `SumTail`:

```clausal
SumTail(LIST, TAIL_LENGTH) <- [_, *TAIL] is LIST, Length(TAIL, TAIL_LENGTH).
```

With LIST unbound:
1. `[_, *TAIL] is LIST` → calls `_body_star_unify(LIST, [anon], TAIL, [], trail)`
2. `d = deref(LIST)` → is a Var
3. → `_head_list_unify_output(LIST, [anon], TAIL, [], trail)` → currently returns False (TAIL unbound)
4. With SegList: → constructs `SegList([ConcreteSeg([anon]), VarSeg(TAIL)])`, binds LIST to it

Then `Length(TAIL, TAIL_LENGTH)` is called with TAIL still unbound. Length/2 with both args
unbound currently fails silently. This chain of effects must be considered: constructing the
SegList doesn't automatically constrain TAIL's length.

The fix for `_head_list_unify_output` is the same for single-star and multi-star: when the
target is unbound AND the star is unbound, construct a SegList. The single-star case constructs
`SegList([ConcreteSeg(before), VarSeg(star), ConcreteSeg(after)])`.

**All three compiler list-unification functions need updating**:
- `_head_list_unify_output` (single-star output mode)
- `_body_star_unify` (calls _head_list_unify_output — picks up the fix transitively)
- `_body_multi_star_unify` (multi-star generator — needs explicit unbound-target branch)
- `_compile_multi_star_guard` (head position multi-star — needs SegList input branch)
- `_head_list_unify_input` (head position single-star — needs SegList input branch)

### EC-5: SegList received as head argument in recursive predicates

When a SegList propagates through a predicate call into the head of a recursive clause, the
head pattern code must handle it. From `lists.clausal`:

```clausal
Append([HEAD, *TAIL], RHS, [HEAD, *REST]) <- Append(TAIL, RHS, REST)
```

In the case where `Append(seg_list, rhs, result)` is called with `seg_list` being a SegList:
- The compiled head pattern checks `isinstance(d, list)` → False
- Falls through to `elif is_var(d)` → False (it's a SegList, not a Var)
- No match → predicate silently fails

This is the "SegList passed to predicate expecting a list" problem. **Every compiled predicate**
that has a list pattern (star or no star) in a head position needs an `elif isinstance(d,
SegList)` branch. For predicates without star patterns (e.g. `foo([H|T])`), the SegList branch
can call `_head_list_unify_input` with the SegList-vs-SegList alignment logic.

This is potentially a large surface area. The systematic fix: update
`_head_list_unify_input` to handle SegList targets (call `_seglist_align_gen` for alignment),
and since `_head_list_unify_input` is the shared runtime helper for all single-star head
patterns, the fix propagates automatically.

For **multi-star head patterns** (generated inline loops), the `isinstance(d, list)` check is
generated inline — there's no shared runtime helper — so `_compile_multi_star_guard` must
emit the `elif isinstance(d, SegList)` branch explicitly.

### EC-6: The minimum-length check with SegList

`_head_list_unify_input` checks `len(d) >= n_before + n_after` before attempting unification.
For a SegList target, `len()` raises `UnboundError` if the SegList has unresolved VarSegs. The
alignment logic for SegList-vs-pattern must handle this differently:

- If the SegList has fewer ConcreteSegs than the pattern requires → fail
- If the SegList's known concrete regions are sufficient to anchor the fixed elements →
  proceed with alignment
- If there are insufficient anchors → enumerate (or defer)

The minimum-length check cannot be directly applied to a SegList. Instead, the alignment
algorithm peels from the ends (ConcreteSegs against ConcreteSegs) and only uses the minimum-
length logic for the middle variable region.

### EC-7: Multi-star `_compile_multi_star_guard` generates inline code, not a helper call

Unlike `_head_list_unify_input` (a shared runtime function), `_compile_multi_star_guard`
generates **inline AST** with hard-coded variable names (`_msp{cap}_{i}`, `_mmark{cap}`,
`_n{cap}`). This means the SegList branch cannot reuse the generated loop — it must call a
runtime helper `_seglist_unify_gen(pattern_seglist, d, trail)` where `pattern_seglist` is
constructed from the compile-time segments.

The compiler must also **construct the pattern SegList at compile time** (emit AST that
constructs it). For a pattern `[*A, X, *B]`, the emitted SegList constructor is:

```python
SegList([VarSeg(deref(_A_name)), ConcreteSeg([deref(_X_name)]), VarSeg(deref(_B_name))])
```

where `_A_name`, `_X_name`, `_B_name` are the captured variable names from the head match.

### EC-8: `_multi_star_splits` logic must be replicated for runtime use

The compile-time helper `_multi_star_splits(n_stars, total)` generates all split distributions
at query time (for a known ground list length). For runtime `_seglist_unify_gen`, the same
logic is needed but operating on a runtime list length. This is a direct port — the algorithm
is the same, just called at runtime instead of compile time. The existing `_multi_star_splits`
should be importable/reusable in `terms.py` or extracted to a shared utilities location.

### EC-9: `Around([*A, X, *B], X, A, B)` with LIST unbound but X bound

When the pattern has fixed elements (individual element Vars) interspersed among VarSegs,
and the individual element Var is already bound (X=5), but the list is unbound:

```clausal
Around(LIST, 5, A, B)  % LIST unbound, X already = 5
```

The SegList constructed should be `SegList([VarSeg(A), ConcreteSeg([5]), VarSeg(B)])` — the
known value 5 is embedded in the ConcreteSeg. When LIST is later unified against `[1,5,3]`,
the split-point search finds position 1 (only slot where value is 5) — deterministic.

If X is also unbound (`Around(LIST, X, A, B)` with all unbound), the ConcreteSeg contains
`ConcreteSeg([Var(X)])`. When LIST is unified against `[1,2,3]`, three splits are found with
X=1, X=2, or X=3. This involves unifying the ConcreteSeg element Var (X) against the list
element — the per-element `unify(elem, val, trail)` call in `_seglist_unify_gen` handles this
correctly, including trail undo.

### EC-10: Empty SegList and empty list interactions

Tests show these must all work:
- `[*A, *B] unify []` → one solution: A=[], B=[]
- `[*ALL] unify []` → one solution: ALL=[]
- `[H, *T] unify []` → no solutions (requires at least one element)
- `SegList([VarSeg(A), ConcreteSeg([]), VarSeg(B)]) unify []` → one solution: A=[], B=[]

The `n < fixed_total` length check in `_body_multi_star_unify` handles the "too short" case.
The same minimum-length check must be in `_seglist_unify_gen` — the min length is the sum of
all ConcreteSeg element counts.

### EC-11: SegList `__repr__` must be readable for debugging

Test failures will be very hard to diagnose without a useful repr. The repr should mirror the
Clausal source syntax:

```python
SegList([VarSeg(A), ConcreteSeg([5, X]), VarSeg(B)])
→ "[*_A5, 5, _X3, *_B7]"   # uses var._id or var name if available
```

Implement `__repr__` and `__str__` from the start (Phase 1) — don't defer.

### EC-12: SegList in `isinstance(x, list)` checks inside compiled clause bodies

Compiled clause bodies check `isinstance` in various places beyond just the head pattern
guards. For example, recursive predicates check the list type in their own guards. If a
SegList value escapes to a context that does `isinstance(d, list)` without a SegList branch,
it silently fails. The systematic fix is:

1. Run the full test suite after Phase 3 with an assertion in `SegList.__iter__`/`__len__`
   that logs a warning when a SegList is used as a plain list — helps locate all sites.
2. OR: make `SegList` a subclass of something that `isinstance(x, list)` catches. This is
   tempting but dangerous — it would make SegList pass guards that assume a ground concrete
   list, potentially causing incorrect behaviour rather than a clean failure.

**Do not** make SegList a subclass of `list`. Prefer the warning/logging approach during
development to find all call sites systematically.

---

## Out of Scope

- **Lazy/infinite SegLists** (streams) — would require coroutine-based list generation; deferred
- **Constraint propagation over SegList length** — e.g. `length([*A, *B], N)` constraining N;
  deferred to a CLP(FD) integration step
- **General word equation solving** (SegList-vs-SegList with multiple VarSegs on both sides,
  no anchoring) — PSPACE-complete; not worth implementing
- **Mutable SegList** — Clausal terms are immutable (trail-based undo); SegList follows this
