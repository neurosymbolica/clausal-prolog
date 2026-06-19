# bytes-as-lists Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Python `bytes` a first-class sequence in Clausal under the same unification-equivalence contract that governs `str`, so `b"abc"` unifies with `[97, 98, 99]` (the classical Prolog `codes` model), with the `bytes` object type-preserved.

**Architecture:** Mirror the strings-as-lists implementation surface-for-surface, substituting the `int ∈ [0,255]` element domain for the 1-char-`str` domain and a new `SegBytes` term for `SegString`. Build bottom-up so each layer is testable before the next depends on it: (1) `SegBytes` term, (2) core C unify `bytes`↔list, (3) seg-unify runtime, (4) compiler head-match + indexing, (5) DCG/`phrase`, (6) consolidated adversarial suite + benchmark.

**Tech Stack:** Python 3.13+ (free-threaded-aware), CPython C extensions (`_variables.c`, `_list_unify.c`) built via `setup.py`, pytest.

## Global Constraints

- **Codes model, not chars model:** a `bytes` decomposes to **ints** (`b"a"[0] == 97`), not 1-char `bytes`. `bytes` has no fixed point — never treat `b"a"` as its own element.
- **Type preservation (C1 rule for bytes):** a `bytes` stays `bytes` — `.decode()`/`.hex()`/`b'a'[0]==97` all remain callable. The int list is a *logical view*, never a representation. Decomposition to ints happens only when a `bytes` is unified against a list pattern.
- **No spurious bytes (promiscuity guard):** the `bytes`↔list contract fires **only when a `bytes` object is actually present on one side**. Two plain int-lists unify as int-lists. Output reconstruction promotes a list to `bytes` only at sites where a `bytes`/`SegBytes` source was present — never unconditionally.
- **Out of range fails, never raises:** `unify(b"...", [256, ...])` produces no solution; it is not an error. A non-int where a byte is expected likewise fails to unify.
- **No `str`↔`bytes` cross-unification:** `"abc"` does not unify with `b"abc"`; `['a','b','c']` does not unify with `b"abc"`. Distinct domains.
- **Additive only:** strings-as-lists behaviour is unchanged. Only immutable `bytes` is in scope; `bytearray` is not.
- **Rebuild C extensions after editing any `.c` file:** `python setup.py build_ext --inplace` (from `/workspace/clausal-string_audit`).
- **Run tests:** `pytest` from project root (config in `pyproject.toml`; `pythonpath=["."]`, 10s timeout).

---

## File Structure

| File | Responsibility | Tasks |
|---|---|---|
| `clausal/terms.py` | New `SegBytes` term + `_segbytes_unify_gen` (mirror `SegString` at 734–1077) | 1, 2, 3 |
| `clausal/logic/variables/_variables.c` | Core `bytes`↔list unify branches + codes-model decomposition in inspect helpers | 4, 5 |
| `clausal/logic/runtime/_seg_helpers.py` | `maybe_promote_to_bytes` + `SegBytes` in `normalize_seg_input` | 6 |
| `clausal/logic/runtime/list_unify.py` | `bytes`/`SegBytes` handling in Python input/output fallbacks | 7 |
| `clausal/logic/runtime/_list_unify.c` | `SegBytesType` registration + `bytes`/`SegBytes` output branches + C `maybe_promote_to_bytes` | 8 |
| `clausal/logic/runtime/body_star_unify.py` | `bytes`/`SegBytes` branches in body-star helpers | 9 |
| `clausal/logic/compiler/head_match.py` | Move `bytes` off `MatchValue` → unify-guard branch | 10 |
| `clausal/logic/compiler/arg_index.py` | `_bytelist_to_bytes_or_none` canonicaliser + 3 call sites | 11 |
| `clausal/logic/builtins/dcg.py` | `bytes` modes in `sequence//3`; `phrase` over `bytes` | 12 |
| `tests/test_segbytes.py` | `SegBytes` unit tests | 1, 2, 3 |
| `tests/test_bytes_list_unification.py` | Core unify + adversarial suite (9 spec categories) | 4, 6, 13 |
| `tests/test_bytes_dcg.py` | DCG-over-bytes tests | 12 |
| `tests/audit_2026_05_25/test_class_C04_head_literal_mismatch.py` | **Flip** the F046 bytes regression test | 10 |
| `tests/test_bytes_indexing.py` | First-arg indexing buckets | 11 |
| `benchmarks/bench_bytes_dispatch.py` | Micro-benchmark mirroring `bench_f046_head_dispatch.py` | 14 |

---

## Task 1: SegBytes core — construction, walk, repr

**Files:**
- Modify: `clausal/terms.py` (add `SegBytes` class + `_segbytes_unify_gen` after `SegString`/`_segstring_unify_gen`, ~line 1077)
- Test: `tests/test_segbytes.py`

**Interfaces:**
- Consumes: `VarSeg` (`terms.py:202`), `ConcreteSeg` (`terms.py:195`), `SegList` (`terms.py:240`), `PartialTermError` (`terms.py:49`), `_seg_unify_cache_key` (`terms.py:207`), `_multi_star_splits` (`terms.py:669`), `walk`/`unify` from `clausal.logic.variables`.
- Produces: `SegBytes(segments: list)` with `.segments` property, `.__walk__()` returning `bytes` when ground / `SegBytes` when partial / `b""` when empty, `._concrete_prefix() -> (bytes, bool)`, `.__repr__()`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_segbytes.py`:

```python
import pytest

from clausal.terms import SegBytes, VarSeg, PartialTermError
from clausal.logic.variables import Var, Trail, unify, deref


class TestSegBytesConstruction:
    def test_accepts_bytes_and_varseg(self):
        # nv
        SegBytes([b"GET", VarSeg(Var())])

    def test_rejects_str_segment(self):
        # nv
        with pytest.raises(PartialTermError):
            SegBytes(["GET", VarSeg(Var())])

    def test_rejects_int_segment(self):
        # nv
        with pytest.raises(PartialTermError):
            SegBytes([71, VarSeg(Var())])


class TestSegBytesWalk:
    def test_ground_returns_bytes(self):
        # nv
        assert SegBytes([b"hello"]).__walk__() == b"hello"

    def test_ground_returns_bytes_type(self):
        # nv
        assert type(SegBytes([b"hello"]).__walk__()) is bytes

    def test_adjacent_bytes_merge(self):
        # nv
        assert SegBytes([b"hel", b"lo"]).__walk__() == b"hello"

    def test_empty_returns_empty_bytes(self):
        # nv
        assert SegBytes([]).__walk__() == b""

    def test_bound_varseg_to_bytes_collapses(self):
        # nv
        trail = Trail()
        X = Var()
        unify(X, b"lo wor", trail)
        ss = SegBytes([b"hel", VarSeg(X), b"ld"])
        assert ss.__walk__() == b"hello world"

    def test_bound_varseg_to_intlist_joins_to_bytes(self):
        # nv  — VarSeg bound to int-codes joins back to bytes
        trail = Trail()
        X = Var()
        unify(X, [108, 111], trail)  # b"lo"
        ss = SegBytes([b"hel", VarSeg(X)])
        assert ss.__walk__() == b"hello"

    def test_varseg_bound_to_out_of_range_int_raises(self):
        # nv
        trail = Trail()
        X = Var()
        unify(X, [256], trail)
        with pytest.raises(PartialTermError):
            SegBytes([b"a", VarSeg(X)]).__walk__()

    def test_non_ground_returns_segbytes(self):
        # nv
        ss = SegBytes([b"hel", VarSeg(Var())])
        w = ss.__walk__()
        assert isinstance(w, SegBytes)


class TestSegBytesConcretePrefix:
    def test_ground(self):
        # nv
        prefix, has_var = SegBytes([b"abc"])._concrete_prefix()
        assert prefix == b"abc" and has_var is False

    def test_non_ground(self):
        # nv
        prefix, has_var = SegBytes([b"ab", VarSeg(Var()), b"cd"])._concrete_prefix()
        assert prefix == b"abcd" and has_var is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_segbytes.py -x`
Expected: FAIL with `ImportError: cannot import name 'SegBytes'`.

- [ ] **Step 3: Implement SegBytes core in terms.py**

Insert after `_segstring_unify_gen` (ends ~line 1077). This mirrors `SegString.__init__`/`__walk__`/`_concrete_prefix`/`__repr__`, substituting `bytes` for `str`, `b"".join` for `"".join`, `bytes(v)` for `"".join(v)`, and the `int ∈ [0,255]` element check for the 1-char-str check:

```python
class SegBytes:
    """A segmented byte string: concrete ``bytes`` literals alternating with
    ``VarSeg`` holes. The codes-model analog of :class:`SegString`.

    VarSegs bind to ``bytes`` substrings (never int-lists, never ``str``).
    Ground SegBytes walk to a plain ``bytes`` object; the int-code list is
    only what it *unifies-with*, preserving ``.decode()``/``.hex()``/identity.
    """

    def __init__(self, segments: list):
        # Mirror SegString.__init__ (F024): the SegBytes contract permits
        # only ``bytes`` literals and ``VarSeg`` holes. Reject anything else
        # at construction with a typed clausal exception.
        for i, seg in enumerate(segments):
            if not isinstance(seg, (bytes, VarSeg)):
                raise PartialTermError(
                    f"SegBytes segment [{i}] is {type(seg).__name__} "
                    f"({seg!r}); expected bytes or VarSeg. SegBytes accepts "
                    f"only bytes literals and variable-length holes."
                )
        self._segments = list(segments)
        self._unify_gens: dict = {}

    @property
    def segments(self):
        return self._segments

    def __walk__(self):
        """Normalise: collapse bound VarSegs, merge adjacent bytes. Returns a
        plain ``bytes`` when fully ground."""
        from .logic.variables import walk
        new_segs: list = []
        for seg in self._segments:
            if isinstance(seg, bytes):
                if new_segs and isinstance(new_segs[-1], bytes):
                    new_segs[-1] = new_segs[-1] + seg
                else:
                    new_segs.append(seg)
            else:  # VarSeg
                v = walk(seg.var)
                if isinstance(v, bytes):
                    if new_segs and isinstance(new_segs[-1], bytes):
                        new_segs[-1] = new_segs[-1] + v
                    else:
                        new_segs.append(v)
                elif isinstance(v, list):
                    # VarSeg bound to an int-code list — join into bytes.
                    # Mirror SegString's char-list guard (F024): validate the
                    # codes domain before bytes(...) so a malformed binding
                    # raises a typed PartialTermError, not a bare ValueError.
                    for i, elem in enumerate(v):
                        if not (isinstance(elem, int) and not isinstance(elem, bool)
                                and 0 <= elem <= 255):
                            raise PartialTermError(
                                f"SegBytes VarSeg bound to a non-byte-list: "
                                f"element [{i}] is {type(elem).__name__} "
                                f"({elem!r}), expected int in [0, 255]. "
                                f"Full binding: {v!r}"
                            )
                    b = bytes(v)
                    if new_segs and isinstance(new_segs[-1], bytes):
                        new_segs[-1] = new_segs[-1] + b
                    else:
                        new_segs.append(b)
                elif isinstance(v, SegBytes):
                    walked_inner = v.__walk__()
                    if isinstance(walked_inner, bytes):
                        if new_segs and isinstance(new_segs[-1], bytes):
                            new_segs[-1] = new_segs[-1] + walked_inner
                        else:
                            new_segs.append(walked_inner)
                    else:
                        for inner_seg in walked_inner._segments:
                            if isinstance(inner_seg, bytes):
                                if new_segs and isinstance(new_segs[-1], bytes):
                                    new_segs[-1] = new_segs[-1] + inner_seg
                                else:
                                    new_segs.append(inner_seg)
                            else:
                                new_segs.append(inner_seg)
                else:
                    new_segs.append(VarSeg(v))

        if all(isinstance(s, bytes) for s in new_segs):
            return b"".join(new_segs)
        new_segs = [s for s in new_segs if not (isinstance(s, bytes) and not s)]
        if not new_segs:
            return b""
        return SegBytes(new_segs)

    def _concrete_prefix(self) -> tuple[bytes, bool]:
        """Return (concrete_bytes, has_var_seg) for the walked SegBytes."""
        w = self.__walk__()
        if isinstance(w, bytes):
            return w, False
        parts: list = []
        has_var = False
        for seg in w._segments:
            if isinstance(seg, bytes):
                parts.append(seg)
            else:
                has_var = True
        return b"".join(parts), has_var

    def __repr__(self):
        return f"SegBytes({self._segments!r})"
```

- [ ] **Step 4: Add SegBytes to the module export list (if present)**

If `terms.py` defines `__all__`, add `"SegBytes"` next to `"SegString"`. Run: `grep -n "__all__" clausal/terms.py` — if no `__all__`, skip this step.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_segbytes.py -x`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add clausal/terms.py tests/test_segbytes.py
git commit -m "feat(terms): SegBytes core — construction, walk, concrete-prefix"
```

---

## Task 2: SegBytes.__unify__ + _segbytes_unify_gen

**Files:**
- Modify: `clausal/terms.py` (add `__unify__` to `SegBytes`; add `_segbytes_unify_gen` after the class)
- Test: `tests/test_segbytes.py`

**Interfaces:**
- Consumes: `SegBytes` (Task 1), `_seg_unify_cache_key`, `_multi_star_splits`, `ConcreteSeg`, `SegList`, `unify`.
- Produces: `SegBytes.__unify__(other, trail)` (against `bytes`: ground `==` / non-ground generator; against `list`: ground delegates to core `unify`, non-ground delegates to `SegList`; against `SegBytes`/`SegList`: `NotImplemented`); `_segbytes_unify_gen(segbytes, target_bytes, trail)`.

> **Sequencing note:** the *ground-against-`list`* path (`unify(walked_bytes, other_list, trail)`) routes to the core C `bytes`↔list branch that does not exist until Task 4. Its dedicated test lands in Task 6. This task tests against-`bytes` (both ground and generator) and against-`list` *non-ground* (SegList delegation), both of which work with existing machinery.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_segbytes.py`:

```python
from clausal.terms import _segbytes_unify_gen


class TestSegBytesUnifyAgainstBytes:
    def test_ground_equal(self):
        # nv
        assert SegBytes([b"hello"]).__unify__(b"hello", Trail()) is True

    def test_ground_unequal(self):
        # nv
        assert SegBytes([b"hello"]).__unify__(b"world", Trail()) is False

    def test_prefix_peel(self):
        # nv  — SegBytes([b"GET", VarSeg(Rest)]) vs b"GET /" binds Rest=b" /"
        trail = Trail()
        Rest = Var()
        ss = SegBytes([b"GET", VarSeg(Rest)])
        assert ss.__unify__(b"GET /", trail) is True
        assert deref(Rest) == b" /"

    def test_varseg_binds_to_bytes_not_intlist(self):
        # nv  — the bound value must be a bytes object, not an int-list
        trail = Trail()
        Rest = Var()
        SegBytes([b"GET", VarSeg(Rest)]).__unify__(b"GET /", trail)
        assert type(deref(Rest)) is bytes

    def test_two_varseg_multiple_splits(self):
        # nv
        trail = Trail()
        A, B = Var(), Var()
        ss = SegBytes([VarSeg(A), b",", VarSeg(B)])
        walked = ss.__walk__()
        solutions = []
        for _ in _segbytes_unify_gen(walked, b"a,b,c", trail):
            solutions.append((deref(A), deref(B)))
        assert (b"a", b"b,c") in solutions
        assert (b"a,b", b"c") in solutions
        assert len(solutions) == 2

    def test_too_short_fails(self):
        # nv
        assert SegBytes([b"hello", VarSeg(Var())]).__unify__(b"hi", Trail()) is False


class TestSegBytesUnifyAgainstList:
    def test_non_ground_against_intlist(self):
        # nv  — SegBytes([b"ab", VarSeg(Rest)]) vs [97,98,99] binds Rest=[99]
        trail = Trail()
        Rest = Var()
        ss = SegBytes([b"ab", VarSeg(Rest)])
        assert ss.__unify__([97, 98, 99], trail) is True
        assert deref(Rest) == [99]

    def test_against_segbytes_notimplemented(self):
        # nv
        ss = SegBytes([b"a", VarSeg(Var())])
        assert ss.__unify__(SegBytes([b"a"]), Trail()) is NotImplemented
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_segbytes.py::TestSegBytesUnifyAgainstBytes -x`
Expected: FAIL with `AttributeError: 'SegBytes' object has no attribute '__unify__'` (or `_segbytes_unify_gen` import error).

- [ ] **Step 3: Add `__unify__` to SegBytes**

Insert into the `SegBytes` class (after `_concrete_prefix`, before `__repr__`). Mirror `SegString.__unify__` (`terms.py:871`):

```python
    def __unify__(self, other, trail):
        from .logic.variables import unify
        if isinstance(other, bytes):
            walked = self.__walk__()
            if isinstance(walked, bytes):
                return walked == other
            key = _seg_unify_cache_key(other, trail)
            gen = self._unify_gens.get(key)
            if gen is None:
                gen = _segbytes_unify_gen(walked, other, trail)
                self._unify_gens[key] = gen
            try:
                next(gen)
                return True
            except StopIteration:
                self._unify_gens.pop(key, None)
                return False
        if isinstance(other, list):
            # Ground SegBytes → bytes, then let C-level bytes↔list
            # unification handle the comparison.
            walked = self.__walk__()
            if isinstance(walked, bytes):
                return unify(walked, other, trail)
            # Non-ground: convert bytes segments to ConcreteSeg-of-int-codes
            # (list(b"GET") == [71,69,84]) and delegate to the SegList
            # generator-driven enumeration. Mirrors SegString's list arm
            # (F023 precedent).
            equivalent_segs: list = []
            for seg in walked._segments:
                if isinstance(seg, bytes):
                    equivalent_segs.append(ConcreteSeg(list(seg)))
                else:  # VarSeg
                    equivalent_segs.append(seg)
            return SegList(equivalent_segs).__unify__(other, trail)
        if isinstance(other, (SegBytes, SegList)):
            return NotImplemented
        return NotImplemented
```

- [ ] **Step 4: Add `_segbytes_unify_gen` after the class**

Insert after the `SegBytes` class. Mirror `_segstring_unify_gen` (`terms.py:1044`):

```python
def _segbytes_unify_gen(segbytes, target_bytes, trail):
    """Non-deterministic generator: yield True for each valid split of
    *target_bytes* across the VarSegs of *segbytes*.

    *segbytes* must be a walked (non-ground) SegBytes.
    *target_bytes* must be a plain Python bytes. VarSegs bind to ``bytes``
    substrings.
    """
    from .logic.variables import unify
    min_len = sum(len(s) for s in segbytes.segments if isinstance(s, bytes))
    n = len(target_bytes)
    if n < min_len:
        return
    n_stars = sum(1 for s in segbytes.segments if isinstance(s, VarSeg))
    remainder = n - min_len
    for split in _multi_star_splits(n_stars, remainder):
        mark = trail.mark()
        ok = True
        pos = 0
        si = 0
        for seg in segbytes.segments:
            if isinstance(seg, VarSeg):
                sz = split[si]; si += 1
                ok = ok and unify(seg.var, target_bytes[pos:pos + sz], trail)
                pos += sz
            else:  # bytes
                end = pos + len(seg)
                if target_bytes[pos:end] != seg:
                    ok = False
                pos = end
            if not ok:
                break
        if ok:
            yield True
        trail.undo(mark)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_segbytes.py -x`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add clausal/terms.py tests/test_segbytes.py
git commit -m "feat(terms): SegBytes.__unify__ + _segbytes_unify_gen"
```

---

## Task 3: SegBytes __eq__/__hash__ + sequence protocol

**Files:**
- Modify: `clausal/terms.py` (add `__eq__`, `__hash__`, `__len__`, `__iter__`, `__contains__`, `__getitem__` to `SegBytes`)
- Test: `tests/test_segbytes.py`

**Interfaces:**
- Consumes: `SegBytes` (Tasks 1–2), `PartialTermError`.
- Produces: `SegBytes.__eq__` (against `SegBytes` structural / `bytes` walk-compare / `list` int-codes compare), `__hash__` (unconditionally raises `TypeError`), `__len__`/`__iter__`/`__contains__`/`__getitem__` (ground iterates the walked `bytes` as **ints**).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_segbytes.py`:

```python
class TestSegBytesEqHash:
    def test_eq_structural(self):
        # nv
        assert SegBytes([b"a"]) == SegBytes([b"a"])

    def test_eq_ground_bytes(self):
        # nv
        assert SegBytes([b"ab", b"c"]) == b"abc"

    def test_eq_intlist(self):
        # nv  — codes-model: SegBytes(b"abc") == [97,98,99]
        assert SegBytes([b"abc"]) == [97, 98, 99]

    def test_neq_out_of_range_intlist(self):
        # nv
        assert SegBytes([b"abc"]) != [97, 98, 999]

    def test_unhashable(self):
        # nv
        with pytest.raises(TypeError):
            hash(SegBytes([b"a"]))


class TestSegBytesSequence:
    def test_iter_yields_ints(self):
        # nv  — list(SegBytes(b"abc")) == [97,98,99], honouring list(b"abc")
        assert list(SegBytes([b"abc"])) == [97, 98, 99]

    def test_len_ground(self):
        # nv
        assert len(SegBytes([b"abc"])) == 3

    def test_len_concrete_prefix(self):
        # nv
        assert len(SegBytes([b"ab", VarSeg(Var())])) == 2

    def test_contains_int(self):
        # nv
        assert 97 in SegBytes([b"abc"])

    def test_getitem_ground_is_int(self):
        # nv
        assert SegBytes([b"abc"])[0] == 97

    def test_getitem_past_prefix_raises(self):
        # nv
        with pytest.raises(PartialTermError):
            SegBytes([b"ab", VarSeg(Var())])[5]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_segbytes.py::TestSegBytesEqHash -x`
Expected: FAIL (default `__eq__`/`__hash__` and no sequence protocol).

- [ ] **Step 3: Implement eq/hash/sequence in SegBytes**

Insert into the `SegBytes` class (before `__repr__`). Mirror `SegString` `__eq__`/`__hash__` (`terms.py:1012`) and sequence protocol (`terms.py:955`):

```python
    def __len__(self) -> int:
        prefix, _ = self._concrete_prefix()
        return len(prefix)

    def __iter__(self):
        # Ground: iterate the walked bytes as ints (matches list(b"abc")
        # == [97,98,99]). Non-ground: yield the concrete int prefix.
        prefix, _ = self._concrete_prefix()
        return iter(prefix)

    def __contains__(self, item) -> bool:
        w = self.__walk__()
        if isinstance(w, bytes):
            try:
                return item in w
            except TypeError:
                return False
        has_var = False
        for seg in w._segments:
            if isinstance(seg, bytes):
                try:
                    if item in seg:
                        return True
                except TypeError:
                    pass
            else:
                has_var = True
        return has_var

    def __getitem__(self, index):
        w = self.__walk__()
        if isinstance(w, bytes):
            return w[index]
        parts = bytearray()
        for seg in w._segments:
            if isinstance(seg, bytes):
                parts.extend(seg)
            else:
                if isinstance(index, int) and 0 <= index < len(parts):
                    return parts[index]
                raise PartialTermError(
                    f"SegBytes[{index!r}] requires resolving an unbound "
                    f"VarSeg; only the concrete prefix (indices "
                    f"0..{len(parts) - 1}) is knowable. SegBytes={self!r}"
                )
        return bytes(parts)[index]

    def __eq__(self, other):
        if isinstance(other, SegBytes):
            return self._segments == other._segments
        if isinstance(other, bytes):
            w = self.__walk__()
            return w == other if isinstance(w, bytes) else False
        if isinstance(other, list):
            # Codes-model symmetry: int-list unifies with bytes at runtime.
            w = self.__walk__()
            if isinstance(w, bytes):
                if all(isinstance(c, int) and not isinstance(c, bool)
                       and 0 <= c <= 255 for c in other):
                    return w == bytes(other)
                return False
            return False
        return NotImplemented

    def __hash__(self):
        # Unconditionally unhashable, symmetric with SegString (F017) and
        # Python's list. Convert a ground SegBytes via bytes(...) for hashing.
        raise TypeError("unhashable type: 'SegBytes'")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_segbytes.py -x`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add clausal/terms.py tests/test_segbytes.py
git commit -m "feat(terms): SegBytes eq/hash + sequence protocol (iterates as ints)"
```

---

## Task 4: Core C unify — bytes↔list symmetric branches

**Files:**
- Modify: `clausal/logic/variables/_variables.c` (insert after the `PyList_Check(t1) && PyUnicode_Check(t2)` block, ~line 1250, inside `do_unify`)
- Test: `tests/test_bytes_list_unification.py`

**Interfaces:**
- Consumes: `do_unify`, `var_deref`, `Var_Check`, `PyList_GetItemRef` (existing in `_variables.c`).
- Produces: `unify(b"abc", [97,98,99], trail)` and the reverse succeed; element binding works; length mismatch / out-of-range int / non-int-element all fail (return 0); `str` does not cross with `bytes`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bytes_list_unification.py`:

```python
from clausal.logic.variables import Var, Trail, unify, deref


class TestBytesUnifiesWithIntList:
    def test_basic(self):
        # nv
        assert unify(b"abc", [97, 98, 99], Trail())

    def test_symmetric(self):
        # nv
        assert unify([97, 98, 99], b"abc", Trail())

    def test_empty(self):
        # nv
        assert unify(b"", [], Trail())

    def test_length_mismatch_fails(self):
        # nv
        assert not unify(b"abc", [97, 98], Trail())


class TestBytesListVarBinding:
    def test_all_vars(self):
        # nv
        trail = Trail()
        X, Y, Z = Var(), Var(), Var()
        assert unify(b"abc", [X, Y, Z], trail)
        assert deref(X) == 97 and deref(Y) == 98 and deref(Z) == 99

    def test_partial_vars(self):
        # nv
        trail = Trail()
        X = Var()
        assert unify(b"abc", [97, X, 99], trail)
        assert deref(X) == 98


class TestBytesPromiscuityAndGuards:
    def test_out_of_range_int_fails(self):
        # nv  — no byte equals 256; unification fails (not an error)
        assert not unify(b"abc", [256, 98, 99], Trail())

    def test_non_int_element_fails(self):
        # nv
        assert not unify(b"abc", ["a", 98, 99], Trail())

    def test_promiscuity_intentional(self):
        # nv  — documented: a bytes present on one side coerces the match
        assert unify(b"\x01\x02\x03", [1, 2, 3], Trail())

    def test_plain_intlists_stay_intlists(self):
        # nv  — no bytes present → no coercion, still unify as int-lists
        assert unify([1, 2, 3], [1, 2, 3], Trail())


class TestBytesNoCrossWithStr:
    def test_str_does_not_unify_with_bytes(self):
        # nv
        assert not unify("abc", b"abc", Trail())

    def test_charlist_does_not_unify_with_bytes(self):
        # nv
        assert not unify(["a", "b", "c"], b"abc", Trail())


class TestBytesNoFixedPoint:
    def test_byte_decomposes_to_int(self):
        # nv  — b"a" decomposes to [97], not to itself
        assert unify(b"a", [97], Trail())

    def test_byte_does_not_unify_with_singleton_bytes_list(self):
        # nv  — b"a" does not unify with [b"a"]
        assert not unify(b"a", [b"a"], Trail())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_bytes_list_unification.py::TestBytesUnifiesWithIntList -x`
Expected: FAIL — `unify(b"abc", [97,98,99])` returns False (no `bytes`↔list branch yet).

- [ ] **Step 3: Insert the bytes↔list branches in `do_unify`**

In `clausal/logic/variables/_variables.c`, immediately after the closing brace of the `if (PyList_Check(t1) && PyUnicode_Check(t2)) { ... return 1; }` block (~line 1250), insert. This mirrors the str↔list branches (L1138–1250), substituting the int-code domain — `b"abc"[i]` is already an int, so the fast path compares `PyLong` values directly:

```c
    /* ---- Bytes ↔ List unification (codes model) ----
     * Treat a Python bytes as a list of ints in [0, 255]:
     * b"abc" unifies element-wise with [97, 98, 99].
     * bytes-vs-bytes still falls through to PyObject_RichCompareBool below.
     * Mirror of the str↔list branch above; the fast path compares int
     * values with no allocation, allocating a PyLong only to bind a Var or
     * delegate to a custom term's __unify__. */
    if (PyBytes_Check(t1) && PyList_Check(t2)) {
        Py_ssize_t n = PyBytes_GET_SIZE(t1);
        if (n != PyList_GET_SIZE(t2)) return 0;
        if (n == 0) return 1;
        const unsigned char *data = (const unsigned char *)PyBytes_AS_STRING(t1);
        for (Py_ssize_t i = 0; i < n; i++) {
            long c1 = (long)data[i];
            PyObject *elem_raw = PyList_GetItemRef(t2, i);
            if (elem_raw == NULL) return -1;
            PyObject *elem = var_deref(elem_raw);
            if (Var_Check(elem)) {
                PyObject *code = PyLong_FromLong(c1);
                if (!code) { Py_DECREF(elem_raw); return -1; }
                int r = do_unify(code, elem, trail, depth + 1, oc);
                Py_DECREF(code);
                Py_DECREF(elem_raw);
                if (r != 1) return r;
            } else if (PyLong_Check(elem)) {
                /* Ground int element — compare value, no allocation. A
                 * bool is a PyLong subclass (True==1) and matches by value. */
                int overflow = 0;
                long v = PyLong_AsLongAndOverflow(elem, &overflow);
                Py_DECREF(elem_raw);
                if (overflow || v != c1) return 0;
            } else {
                /* Not a Var, not an int — could be a SegBytes or other
                 * custom term. Allocate the code and delegate to do_unify. */
                PyObject *code = PyLong_FromLong(c1);
                if (!code) { Py_DECREF(elem_raw); return -1; }
                int r = do_unify(code, elem, trail, depth + 1, oc);
                Py_DECREF(code);
                Py_DECREF(elem_raw);
                if (r != 1) return r;
            }
        }
        return 1;
    }
    if (PyList_Check(t1) && PyBytes_Check(t2)) {
        /* Symmetric: list on left, bytes on right. */
        Py_ssize_t n = PyBytes_GET_SIZE(t2);
        if (PyList_GET_SIZE(t1) != n) return 0;
        if (n == 0) return 1;
        const unsigned char *data = (const unsigned char *)PyBytes_AS_STRING(t2);
        for (Py_ssize_t i = 0; i < n; i++) {
            long c2 = (long)data[i];
            PyObject *elem_raw = PyList_GetItemRef(t1, i);
            if (elem_raw == NULL) return -1;
            PyObject *elem = var_deref(elem_raw);
            if (Var_Check(elem)) {
                PyObject *code = PyLong_FromLong(c2);
                if (!code) { Py_DECREF(elem_raw); return -1; }
                int r = do_unify(elem, code, trail, depth + 1, oc);
                Py_DECREF(code);
                Py_DECREF(elem_raw);
                if (r != 1) return r;
            } else if (PyLong_Check(elem)) {
                int overflow = 0;
                long v = PyLong_AsLongAndOverflow(elem, &overflow);
                Py_DECREF(elem_raw);
                if (overflow || v != c2) return 0;
            } else {
                PyObject *code = PyLong_FromLong(c2);
                if (!code) { Py_DECREF(elem_raw); return -1; }
                int r = do_unify(elem, code, trail, depth + 1, oc);
                Py_DECREF(code);
                Py_DECREF(elem_raw);
                if (r != 1) return r;
            }
        }
        return 1;
    }
```

> Note: `str`↔`bytes` needs no guard — neither branch fires (both require a `list`), so `"abc" == b"abc"` falls through to `PyObject_RichCompareBool`, which is `False` in Python 3. Out-of-range and non-int elements naturally return 0.

- [ ] **Step 4: Rebuild the C extension**

Run: `python setup.py build_ext --inplace`
Expected: compiles `_variables.c` with no warnings/errors.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_bytes_list_unification.py -x`
Expected: PASS (all classes).

- [ ] **Step 6: Run the str regression suite (additive guarantee)**

Run: `pytest tests/test_string_list_unification.py -x`
Expected: PASS — strings-as-lists unchanged.

- [ ] **Step 7: Commit**

```bash
git add clausal/logic/variables/_variables.c tests/test_bytes_list_unification.py
git commit -m "feat(unify): core C bytes<->list unification (codes model)"
```

---

## Task 5: Core C — codes-model decomposition in inspect helpers

**Files:**
- Modify: `clausal/logic/variables/_variables.c` — `py_functor_name` (~L2158), `py_arity` (~L2247), `py_nth_arg` (~L2391), `py_args_list` (~L2483)
- Test: `tests/test_bytes_list_unification.py`

**Interfaces:**
- Consumes: existing `raise_arg_index_error`, `PyBytes_*` macros.
- Produces: `bytes` decomposes as a cons-cell parallel to `str`, but **head is an int** (`b"abc"` → head `97`, tail `b"bc"`) and **tail preserves `bytes`**. `functor_name(b"abc") == "."`, `arity(b"abc") == 2`, `args_list(b"abc") == [97, b"bc"]`.

> `c_is_ground`, `c_copy_term`, `c_collect_vars` already treat `bytes` as a ground scalar with no vars — exactly as they treat `str`. Leave them unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bytes_list_unification.py`:

```python
from clausal.logic.variables import _functor_name, _arity, _nth_arg, _args_list


class TestBytesDecomposition:
    def test_functor_name_nonempty(self):
        # nv
        assert _functor_name(b"abc") == "."

    def test_functor_name_empty(self):
        # nv
        assert _functor_name(b"") == "[]"

    def test_arity_nonempty(self):
        # nv
        assert _arity(b"abc") == 2

    def test_arity_empty(self):
        # nv
        assert _arity(b"") == 0

    def test_nth_arg_head_is_int(self):
        # nv  — codes model: head is an int, no fixed point
        assert _nth_arg(b"abc", 1) == 97

    def test_nth_arg_tail_is_bytes(self):
        # nv
        assert _nth_arg(b"abc", 2) == b"bc"

    def test_args_list(self):
        # nv
        assert _args_list(b"abc") == [97, b"bc"]

    def test_args_list_empty(self):
        # nv
        assert _args_list(b"") == []
```

> Confirm the public names: run `python -c "from clausal.logic.variables import _functor_name, _arity, _nth_arg, _args_list"`. If they differ, `grep -n "functor_name\|args_list\|nth_arg\|arity" clausal/logic/variables/__init__.py` and adjust the import + calls. `_nth_arg`/`_args_list` are the C functions `py_nth_arg`/`py_args_list`; match the wrapper signature (`_nth_arg(term, n)` vs `_nth_arg((term, n))`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_bytes_list_unification.py::TestBytesDecomposition -x`
Expected: FAIL — `functor_name(b"abc")` currently returns the repr `"b'abc'"`, `arity` returns 0, `args_list` returns `[]`.

- [ ] **Step 3a: `py_functor_name` — add bytes cons-cell, remove from primitives**

Find the `str` cons-cell branch (~L2159) and the primitives line listing `PyBytes_Check` (~L2165). Add a `bytes` branch right after the `str` branch:

```c
    /* Bytes — codes-model cons-cell, symmetric with str/list. */
    if (PyBytes_Check(term)) {
        if (PyBytes_GET_SIZE(term) == 0)
            return PyUnicode_FromString("[]");
        else
            return PyUnicode_FromString(".");
    }
```

Then remove `PyBytes_Check(term)` from the primitives disjunction that returns `PyObject_Repr(term)`:

```c
    /* Primitives */
    if (term == Py_None || PyBool_Check(term) || PyLong_Check(term) ||
        PyFloat_Check(term)) {
        return PyObject_Repr(term);
    }
```

- [ ] **Step 3b: `py_arity` — add bytes cons-cell, remove from primitives**

After the `str` branch (~L2247), add:

```c
    /* Bytes — codes-model cons-cell. */
    if (PyBytes_Check(term)) {
        return PyLong_FromLong(PyBytes_GET_SIZE(term) == 0 ? 0 : 2);
    }
```

Then remove `PyBytes_Check(term)` from the primitives-return-0 disjunction (~L2251):

```c
    /* Primitives */
    if (term == Py_None || PyBool_Check(term) || PyLong_Check(term) ||
        PyFloat_Check(term)) {
        return PyLong_FromLong(0);
    }
```

- [ ] **Step 3c: `py_nth_arg` — add bytes branch (int head, bytes tail)**

After the `str` branch (~L2391, before the trailing `return raise_arg_index_error(n, term);`), add:

```c
    /* Bytes — codes-model cons-cell: n=1 → int head (b[0] is an int, no
     * fixed point), n=2 → bytes tail (type preserved). */
    if (PyBytes_Check(term)) {
        Py_ssize_t len = PyBytes_GET_SIZE(term);
        if (len == 0) {
            return raise_arg_index_error(n, term);
        }
        if (n == 1) {
            const unsigned char *data =
                (const unsigned char *)PyBytes_AS_STRING(term);
            return PyLong_FromLong((long)data[0]);
        }
        if (n == 2) {
            const char *data = PyBytes_AS_STRING(term);
            return PyBytes_FromStringAndSize(data + 1, len - 1);
        }
        return raise_arg_index_error(n, term);
    }
```

- [ ] **Step 3d: `py_args_list` — add bytes branch ([int_head, bytes_tail])**

After the `str` branch (~L2483, before the `/* Default: empty list */ return PyList_New(0);`), add:

```c
    /* Bytes — codes-model cons-cell: non-empty → [int_head, bytes_tail];
     * empty → []. Head is an int (no fixed point); tail preserves bytes. */
    if (PyBytes_Check(term)) {
        Py_ssize_t len = PyBytes_GET_SIZE(term);
        if (len == 0) {
            return PyList_New(0);
        }
        const unsigned char *udata =
            (const unsigned char *)PyBytes_AS_STRING(term);
        PyObject *head = PyLong_FromLong((long)udata[0]);
        if (!head) return NULL;
        PyObject *tail =
            PyBytes_FromStringAndSize((const char *)udata + 1, len - 1);
        if (!tail) { Py_DECREF(head); return NULL; }
        PyObject *result = PyList_New(2);
        if (!result) { Py_DECREF(head); Py_DECREF(tail); return NULL; }
        PyList_SET_ITEM(result, 0, head);  /* steals */
        PyList_SET_ITEM(result, 1, tail);  /* steals */
        return result;
    }
```

- [ ] **Step 4: Rebuild and run tests**

Run: `python setup.py build_ext --inplace && pytest tests/test_bytes_list_unification.py -x`
Expected: PASS.

- [ ] **Step 5: Run the full inspect/str regression**

Run: `pytest tests/test_string_list_unification.py tests/test_segbytes.py -x`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add clausal/logic/variables/_variables.c tests/test_bytes_list_unification.py
git commit -m "feat(unify): codes-model bytes decomposition in functor/arity/nth_arg/args_list"
```

---

## Task 6: Seg-helpers — maybe_promote_to_bytes + normalize_seg_input

**Files:**
- Modify: `clausal/logic/runtime/_seg_helpers.py`
- Test: `tests/test_segbytes.py` (helper unit tests + the deferred SegBytes-ground-against-list integration test from Task 2)

**Interfaces:**
- Consumes: `SegBytes` (Tasks 1–3), core `bytes`↔list unify (Task 4).
- Produces: `maybe_promote_to_bytes(result)` (list of ints-in-[0,255] → `bytes`, else unchanged); `normalize_seg_input` walks `SegBytes`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_segbytes.py`:

```python
from clausal.logic.runtime._seg_helpers import (
    maybe_promote_to_bytes, normalize_seg_input,
)


class TestMaybePromoteToBytes:
    def test_promotes_int_list(self):
        # nv
        assert maybe_promote_to_bytes([97, 98, 99]) == b"abc"
        assert type(maybe_promote_to_bytes([97, 98, 99])) is bytes

    def test_leaves_out_of_range(self):
        # nv
        assert maybe_promote_to_bytes([97, 256]) == [97, 256]

    def test_leaves_non_int(self):
        # nv
        assert maybe_promote_to_bytes(["a", "b"]) == ["a", "b"]

    def test_leaves_empty(self):
        # nv
        assert maybe_promote_to_bytes([]) == []

    def test_leaves_bool(self):
        # nv  — bools must not become bytes
        assert maybe_promote_to_bytes([True, False]) == [True, False]


class TestNormalizeSegBytes:
    def test_walks_ground_segbytes_to_bytes(self):
        # nv
        assert normalize_seg_input(SegBytes([b"abc"])) == b"abc"


class TestSegBytesGroundAgainstList:
    # The deferred Task 2 integration test: now that core bytes<->list exists.
    def test_ground_segbytes_unifies_with_intlist(self):
        # nv
        trail = Trail()
        assert SegBytes([b"ab", b"c"]).__unify__([97, 98, 99], trail) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_segbytes.py::TestMaybePromoteToBytes -x`
Expected: FAIL with `ImportError: cannot import name 'maybe_promote_to_bytes'`.

- [ ] **Step 3: Add `maybe_promote_to_bytes` to `_seg_helpers.py`**

Append after `maybe_promote_to_str`:

```python
def maybe_promote_to_bytes(result: Any) -> Any:
    """If *result* is a list of all ground ints in [0, 255], return the
    equivalent ``bytes``. Otherwise return *result* unchanged.

    The codes-model parallel of :func:`maybe_promote_to_str`. Per the
    bytes-as-lists promiscuity guard, this is called ONLY at reconstruction
    sites where a ``bytes`` / ``SegBytes`` source was present on the input
    side — never unconditionally — so a plain int-list output never
    spuriously becomes ``bytes``. Bools are excluded (``True``/``False``
    must not coerce to bytes).
    """
    if isinstance(result, list) and result and all(
        isinstance(e, int) and not isinstance(e, bool) and 0 <= e <= 255
        for e in result
    ):
        return bytes(result)
    return result
```

- [ ] **Step 4: Add `SegBytes` to `normalize_seg_input`**

Edit the import and the body:

```python
    from clausal.terms import SegList, SegString, SegBytes
    if isinstance(x, SegList):
        return x.__walk__()
    if isinstance(x, SegString):
        return x.__walk__()
    if isinstance(x, SegBytes):
        return x.__walk__()
    return x
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_segbytes.py -x`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add clausal/logic/runtime/_seg_helpers.py tests/test_segbytes.py
git commit -m "feat(runtime): maybe_promote_to_bytes + SegBytes in normalize_seg_input"
```

---

## Task 7: Python fallback list_unify — bytes/SegBytes input & output

**Files:**
- Modify: `clausal/logic/runtime/list_unify.py` — `_head_list_unify_input_py` (~L89), `_head_list_unify_output_py` (~L167)
- Test: `tests/test_bytes_seg_runtime.py`

**Interfaces:**
- Consumes: `SegBytes`, `maybe_promote_to_bytes`, `ConcreteSeg`/`SegList`/`VarSeg`, `unify`/`deref`.
- Produces: `_head_list_unify_input_py`/`_head_list_unify_output_py` accept `bytes`/`SegBytes` targets and reconstruct `bytes` output when a `bytes`/`SegBytes` star source is present.

> The Python fallback must be correct independently of the C extension. We test it directly by aliasing the `_py` functions. The C version is updated in Task 8.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bytes_seg_runtime.py`:

```python
from clausal.logic.variables import Var, Trail, unify, deref
from clausal.logic.runtime.list_unify import (
    _head_list_unify_input_py, _head_list_unify_output_py,
)


class TestBytesInputPy:
    def test_destructure_bytes_head_tail(self):
        # nv  — [H, *T] against b"abc": H=97 (int), T=b"bc" (bytes)
        trail = Trail()
        H, T = Var(), Var()
        ok = _head_list_unify_input_py(b"abc", [H], T, [], trail)
        assert ok is True
        assert deref(H) == 97
        assert deref(T) == b"bc"


class TestBytesOutputPy:
    def test_star_bound_to_bytes_rebuilds_bytes(self):
        # nv  — building [*S] with S=b"abc" yields b"abc"
        trail = Trail()
        target = Var()
        S = Var()
        unify(S, b"abc", trail)
        ok = _head_list_unify_output_py(target, [], S, [], trail)
        assert ok is True
        assert deref(target) == b"abc"
        assert type(deref(target)) is bytes

    def test_plain_intlist_star_not_promoted(self):
        # nv  — building [*S] with S=[1,2,3] stays an int-list (no bytes)
        trail = Trail()
        target = Var()
        S = Var()
        unify(S, [1, 2, 3], trail)
        ok = _head_list_unify_output_py(target, [], S, [], trail)
        assert ok is True
        assert deref(target) == [1, 2, 3]
        assert type(deref(target)) is list
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_bytes_seg_runtime.py -x`
Expected: FAIL — input rejects `bytes` (not in `(list, str)`); output leaves a list-of-ints instead of `bytes`.

- [ ] **Step 3: Update imports in `list_unify.py`**

Add to the `from clausal.terms import ...` block: `SegBytes`. Add to the `from ._seg_helpers import ...` block: `maybe_promote_to_bytes`. (Confirm `ConcreteSeg`, `SegList`, `VarSeg` are already imported.)

- [ ] **Step 4: Add `bytes`/`SegBytes` to `_head_list_unify_input_py`**

After the `SegString` normalise block (~L121), add a parallel `SegBytes` block:

```python
    if isinstance(d, SegBytes):
        d = d.__walk__()
        if not isinstance(d, (list, bytes)):
            return None
```

Then widen the main container check from `isinstance(d, (list, str))` to include `bytes`:

```python
    if isinstance(d, (list, str, bytes)):
```

> Native indexing already implements the codes model: `b"abc"[i]` is an int (binds the var to a code) and `b"abc"[n:]` is `bytes` (star preserves the type). No further change to the loop body is needed.

- [ ] **Step 5: Add `bytes` and `SegBytes` star branches to `_head_list_unify_output_py`**

After the `elif isinstance(s, str):` branch (which falls through to the unconditional `maybe_promote_to_str` at the end), insert two new branches. These return early with a **bytes-specific** promotion, so a plain int-list star never reaches `maybe_promote_to_bytes`:

```python
        elif isinstance(s, bytes):
            # Codes-model parallel of the str-star branch: a bytes-bound
            # star is treated as a list of int codes. Iterating bytes yields
            # ints; promote the result back to bytes (only fires because a
            # bytes source is present here — no spurious bytes otherwise).
            result.extend(s)
            result.extend(deref(v) for v in after_vals)
            return unify(d, maybe_promote_to_bytes(result), trail)
        elif isinstance(s, SegBytes):
            walked = s.__walk__()
            if isinstance(walked, bytes):
                result.extend(walked)
                result.extend(deref(v) for v in after_vals)
                return unify(d, maybe_promote_to_bytes(result), trail)
            else:
                # Non-ground SegBytes: convert each bytes segment to a
                # ConcreteSeg of int codes (list(b"GET") == [71,69,84]) and
                # rebuild as a SegList for unification — mirrors the
                # SegString non-ground output path.
                after_result = [deref(v) for v in after_vals]
                segs = []
                if result:
                    segs.append(ConcreteSeg(result))
                for inner in walked.segments:
                    if isinstance(inner, bytes):
                        segs.append(ConcreteSeg(list(inner)))
                    else:  # VarSeg
                        segs.append(inner)
                if after_result:
                    segs.append(ConcreteSeg(after_result))
                return unify(d, SegList(segs), trail)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_bytes_seg_runtime.py -x`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add clausal/logic/runtime/list_unify.py tests/test_bytes_seg_runtime.py
git commit -m "feat(runtime): bytes/SegBytes in Python list-unify input & output fallbacks"
```

---

## Task 8: C accelerator _list_unify.c — bytes/SegBytes output + type registration

**Files:**
- Modify: `clausal/logic/runtime/_list_unify.c` — static type globals (~L23), `maybe_promote_to_str` neighbourhood (~L110), `py_head_list_unify_input` container check (~L216) + `SegBytes` walk normalise (~L199), `py_head_list_unify_output` star branches (~L344+), module init (~L611)
- Test: `tests/test_bytes_seg_runtime.py` (re-run against the C path)

**Interfaces:**
- Consumes: `SegBytes` (terms), `maybe_promote_to_str` pattern.
- Produces: the C `_head_list_unify_input`/`_head_list_unify_output` behave identically to the Python fallbacks for `bytes`/`SegBytes`. `SegBytesType` is registered and resolved in module init.

> After this task, `from clausal.logic.runtime._list_unify import _head_list_unify_input` shadows the Python fallback, so Task 7's tests now exercise the C path. They must still pass.

- [ ] **Step 1: Write the failing test (C-path assertion)**

Append to `tests/test_bytes_seg_runtime.py`:

```python
class TestCExtensionActive:
    def test_c_extension_loaded(self):
        # nv  — confirm we are testing the C path, not the Python fallback
        from clausal.logic.runtime import list_unify
        from clausal.logic.runtime import _list_unify  # noqa: F401
        assert list_unify._head_list_unify_input.__module__ != "clausal.logic.runtime.list_unify"

    def test_c_star_bound_to_bytes_rebuilds_bytes(self):
        # nv  — exercise the C output path directly
        from clausal.logic.runtime._list_unify import _head_list_unify_output
        trail = Trail()
        target, S = Var(), Var()
        unify(S, b"abc", trail)
        assert _head_list_unify_output(target, [], S, [], trail) is True
        assert deref(target) == b"abc"
        assert type(deref(target)) is bytes
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_bytes_seg_runtime.py::TestCExtensionActive -x`
Expected: FAIL — the C output path splats `bytes` differently or leaves a list (no `bytes` branch yet). `test_c_extension_loaded` may pass already.

- [ ] **Step 3: Add the `SegBytesType` static global**

After the existing static type globals (~L23–26):

```c
static PyTypeObject *SegBytesType    = NULL;
```

- [ ] **Step 4: Resolve `SegBytesType` in module init**

In `PyInit__list_unify` (~L626), after the `ss = PyObject_GetAttrString(terms_mod, "SegString");` line, add:

```c
    PyObject *sb = PyObject_GetAttrString(terms_mod, "SegBytes");
```

Add `sb` to the NULL-check and assign the type:

```c
    if (!sl || !ss || !sb || !cs || !vs) return NULL;
    SegListType     = (PyTypeObject *)sl;
    SegStringType   = (PyTypeObject *)ss;
    SegBytesType    = (PyTypeObject *)sb;
    ConcreteSegType = (PyTypeObject *)cs;
    VarSegType      = (PyTypeObject *)vs;
```

- [ ] **Step 5: Add a C `maybe_promote_to_bytes` helper**

After `maybe_promote_to_str` (~L136):

```c
/* maybe_promote_to_bytes(result) — codes-model parallel of
 * maybe_promote_to_str. If *result* is a non-empty list whose every element
 * is a ground int in [0, 255] (excluding bool), return the equivalent bytes;
 * otherwise return *result* unchanged (refcount-incremented). Called ONLY at
 * sites where a bytes / SegBytes source was present. Returns NULL on error. */
static PyObject *
maybe_promote_to_bytes(PyObject *result)
{
    if (!PyList_Check(result)) {
        Py_INCREF(result);
        return result;
    }
    Py_ssize_t n = PyList_GET_SIZE(result);
    if (n == 0) {
        Py_INCREF(result);
        return result;
    }
    /* Validate codes domain and fill a byte buffer. */
    char *buf = (char *)PyMem_Malloc(n);
    if (!buf) return PyErr_NoMemory();
    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *e = PyList_GET_ITEM(result, i);
        if (!PyLong_Check(e) || PyBool_Check(e)) {
            PyMem_Free(buf);
            Py_INCREF(result);
            return result;
        }
        int overflow = 0;
        long v = PyLong_AsLongAndOverflow(e, &overflow);
        if (overflow || v < 0 || v > 255) {
            PyMem_Free(buf);
            Py_INCREF(result);
            return result;
        }
        buf[i] = (char)(unsigned char)v;
    }
    PyObject *out = PyBytes_FromStringAndSize(buf, n);
    PyMem_Free(buf);
    return out;
}
```

- [ ] **Step 6: Accept `bytes`/`SegBytes` targets in `py_head_list_unify_input`**

In `py_head_list_unify_input`, after the `SegString` walk-normalise block (~L199), add the parallel `SegBytes` block:

```c
    if (PyObject_TypeCheck(d, SegBytesType)) {
        PyObject *walked = PyObject_CallMethod(d, "__walk__", NULL);
        Py_DECREF(d);
        if (!walked) return NULL;
        d = walked;
        if (!PyList_Check(d) && !PyBytes_Check(d)) {
            Py_DECREF(d);
            Py_RETURN_NONE;
        }
    }
```

Then widen the main container check (~L216) to include `bytes`. `seq_length`/`seq_getitem`/`seq_slice` already handle `bytes` via the CPython sequence protocol (`PySequence_GetItem(bytes, i)` → `int`; `PySequence_GetSlice(bytes,…)` → `bytes`):

```c
    if (PyList_Check(d) || PyUnicode_Check(d) || PyBytes_Check(d)) {
```

- [ ] **Step 7: Add `bytes`/`SegBytes` star branches in `py_head_list_unify_output`**

In the star-handling chain, after the `else if (PyUnicode_Check(s)) { ... }` block (~L357), insert a `bytes` branch that splats the int codes and promotes locally, then unifies and returns:

```c
        } else if (PyBytes_Check(s)) {
            /* Codes-model parallel of the str-star branch: splat the
             * bytes as its int codes, then promote the whole result back
             * to bytes via maybe_promote_to_bytes (only here, where a
             * bytes source is present). */
            Py_ssize_t slen = PyBytes_GET_SIZE(s);
            const unsigned char *sdata =
                (const unsigned char *)PyBytes_AS_STRING(s);
            for (Py_ssize_t i = 0; i < slen; i++) {
                PyObject *code = PyLong_FromLong((long)sdata[i]);
                if (!code) { Py_DECREF(s); goto error; }
                int rc = PyList_Append(result, code);
                Py_DECREF(code);
                if (rc < 0) { Py_DECREF(s); goto error; }
            }
            Py_DECREF(s);
            for (Py_ssize_t i = 0; i < n_after; i++) {
                PyObject *v = PyList_GET_ITEM(after_vals, i);
                PyObject *dv = call_deref(v);
                if (!dv) goto error;
                int rc = PyList_Append(result, dv);
                Py_DECREF(dv);
                if (rc < 0) goto error;
            }
            PyObject *promoted = maybe_promote_to_bytes(result);
            if (!promoted) { Py_DECREF(d); Py_DECREF(result); return NULL; }
            int ok = call_unify(d, promoted, trail);
            Py_DECREF(promoted);
            Py_DECREF(d);
            Py_DECREF(result);
            if (ok < 0) return NULL;
            if (ok) Py_RETURN_TRUE;
            Py_RETURN_FALSE;
```

Then extend the `SegList`/`SegString` walk branch condition to include `SegBytes`, and add a `bytes`-ground arm. Change the branch guard (~L358):

```c
        } else if (PyObject_TypeCheck(s, SegListType) ||
                   PyObject_TypeCheck(s, SegStringType) ||
                   PyObject_TypeCheck(s, SegBytesType)) {
```

Inside that branch, after `PyObject *walked = ...`, the ground arm currently tests `PyList_Check(walked) || PyUnicode_Check(walked)`. Add a separate `bytes`-ground arm *before* it so a ground `SegBytes` (which walks to `bytes`) is splatted as int codes and promoted to bytes:

```c
            if (PyBytes_Check(walked)) {
                /* Ground SegBytes → bytes: splat int codes, promote to bytes. */
                Py_ssize_t wlen = PyBytes_GET_SIZE(walked);
                const unsigned char *wdata =
                    (const unsigned char *)PyBytes_AS_STRING(walked);
                for (Py_ssize_t i = 0; i < wlen; i++) {
                    PyObject *code = PyLong_FromLong((long)wdata[i]);
                    if (!code) { Py_DECREF(walked); goto error; }
                    int rc = PyList_Append(result, code);
                    Py_DECREF(code);
                    if (rc < 0) { Py_DECREF(walked); goto error; }
                }
                Py_DECREF(walked);
                for (Py_ssize_t i = 0; i < n_after; i++) {
                    PyObject *v = PyList_GET_ITEM(after_vals, i);
                    PyObject *dv = call_deref(v);
                    if (!dv) goto error;
                    int rc = PyList_Append(result, dv);
                    Py_DECREF(dv);
                    if (rc < 0) goto error;
                }
                PyObject *promoted = maybe_promote_to_bytes(result);
                if (!promoted) { Py_DECREF(d); Py_DECREF(result); return NULL; }
                int ok = call_unify(d, promoted, trail);
                Py_DECREF(promoted);
                Py_DECREF(d);
                Py_DECREF(result);
                if (ok < 0) return NULL;
                if (ok) Py_RETURN_TRUE;
                Py_RETURN_FALSE;
            }
```

For the **non-ground** `SegBytes` arm: the existing rebuild path wraps `SegString` str segments via `PySequence_List(iseg)` (which for a `bytes` segment yields a list of ints — exactly the codes we want) into `ConcreteSeg`. Change the per-segment guard so a `bytes` inner segment is also converted:

```c
                    if ((walked_is_segstring && PyUnicode_Check(iseg)) ||
                        PyBytes_Check(iseg)) {
                        /* str segment → ConcreteSeg(list(seg)); bytes segment
                         * → ConcreteSeg(list(seg)) where list(bytes) == int
                         * codes. PySequence_List handles both. */
                        PyObject *chars = PySequence_List(iseg);
```

> `walked_is_segstring` stays as-is for the `SegString` case; the added `PyBytes_Check(iseg)` covers `SegBytes` segments regardless of that flag.

- [ ] **Step 8: Rebuild and run tests**

Run: `python setup.py build_ext --inplace && pytest tests/test_bytes_seg_runtime.py -x`
Expected: PASS (C extension active, bytes output reconstructs bytes).

- [ ] **Step 9: Run str regression**

Run: `pytest tests/test_string_list_unification.py tests/test_segstring.py -x`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add clausal/logic/runtime/_list_unify.c tests/test_bytes_seg_runtime.py
git commit -m "feat(runtime): C accelerator bytes/SegBytes output + SegBytesType registration"
```

---

## Task 9: body_star_unify — bytes/SegBytes branches

**Files:**
- Modify: `clausal/logic/runtime/body_star_unify.py` — imports, `_body_star_unify` (~L27), `_build_star_list` (~L59), `_build_multi_star_list` (~L142), `_body_multi_star_unify` (~L416); add `_segbytes_align` (parallel to `_segstring_align` ~L330)
- Test: `tests/test_bytes_seg_runtime.py`

**Interfaces:**
- Consumes: `SegBytes`, `maybe_promote_to_bytes`, `_multi_star_splits`.
- Produces: body-position star unification (`[X, *Xs] is b"..."`), construction promotes to `bytes`/`SegBytes`, multi-star deconstruction over `bytes`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bytes_seg_runtime.py`:

```python
from clausal.logic.runtime.body_star_unify import (
    _body_star_unify, _build_star_list, _body_multi_star_unify,
)
from clausal.terms import SegBytes, VarSeg, ConcreteSeg


class TestBodyStarBytes:
    def test_deconstruct_bytes(self):
        # nv  — [H, *T] is b"abc": H=97, T=b"bc"
        trail = Trail()
        H, T = Var(), Var()
        assert _body_star_unify(b"abc", [H], T, [], trail)
        assert deref(H) == 97 and deref(T) == b"bc"

    def test_build_star_list_bytes(self):
        # nv  — *S with S=b"bc", before=[97] → b"abc"
        result = _build_star_list([97], b"bc", [])
        assert result == b"abc"
        assert type(result) is bytes

    def test_multi_star_over_bytes(self):
        # nv  — [*A, 99, *B] is b"abcdc" enumerates splits, A/B bind to bytes
        trail = Trail()
        A, B = Var(), Var()
        sols = []
        for _ in _body_multi_star_unify(
            b"abcdc", [("star", A), ("fixed", [99]), ("star", B)], trail
        ):
            sols.append((deref(A), deref(B)))
        assert (b"ab", b"dc") in sols
        assert all(type(a) is bytes and type(b) is bytes for a, b in sols)
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_bytes_seg_runtime.py::TestBodyStarBytes -x`
Expected: FAIL — `_body_star_unify` rejects `bytes`; `_build_star_list` returns a list, not bytes.

- [ ] **Step 3: Update imports**

In the top-of-file import block, add `SegBytes` to the `from clausal.terms import (...)` tuple, and add `maybe_promote_to_bytes` to the `from ._seg_helpers import ...` line:

```python
from clausal.terms import (
    DictTerm,
    SegList, ConcreteSeg, VarSeg,
    SegString,
    SegBytes,
    _multi_star_splits,
)

from ._seg_helpers import maybe_promote_to_str, maybe_promote_to_bytes
```

- [ ] **Step 4: `_body_star_unify` — route bytes/SegBytes to input/output**

After the `if isinstance(d, SegString):` block (~L45), add a `SegBytes` block; and widen the `(list, str)` deconstruction check to include `bytes`:

```python
    if isinstance(d, SegBytes):
        return _head_list_unify_input(target, before_vals, star_val, after_vals, trail)

    if isinstance(d, (list, str, bytes)):
        return _head_list_unify_input(target, before_vals, star_val, after_vals, trail)
```

- [ ] **Step 5: `_build_star_list` — add bytes & SegBytes branches**

After the `if isinstance(d, str):` branch (~L70–78), add a `bytes` branch. Note `list(b"bc") == [98,99]` (ints), so before/after elements must be ints-in-[0,255] for the all-bytes promotion:

```python
    if isinstance(d, bytes):
        b = list(before)
        a = list(after)
        codes_ok = all(isinstance(e, int) and not isinstance(e, bool)
                       and 0 <= e <= 255 for e in b + a)
        if codes_ok:
            return bytes(b) + d + bytes(a)
        # Mixed — fall through to list construction (codes view).
        return b + list(d) + a
```

After the `if isinstance(d, SegString):` branch (~L97–131), add a `SegBytes` branch mirroring it (str→bytes, `""`→`b""`, `"".join`→`bytes(...)`, str segment→`ConcreteSeg(list(seg))` int codes):

```python
    if isinstance(d, SegBytes):
        walked = d.__walk__()
        b = list(before)
        a = list(after)
        codes_ok = all(isinstance(e, int) and not isinstance(e, bool)
                       and 0 <= e <= 255 for e in b + a)
        if isinstance(walked, bytes):
            if codes_ok:
                return bytes(b) + walked + bytes(a)
            return b + list(walked) + a
        # non-ground SegBytes
        if codes_ok:
            new_segs = []
            prefix = bytes(b)
            if prefix:
                new_segs.append(prefix)
            new_segs.extend(walked.segments)
            suffix = bytes(a)
            if suffix:
                new_segs.append(suffix)
            return SegBytes(new_segs)
        # Mixed — convert SegBytes segments to SegList segments (int codes).
        segs = []
        if b:
            segs.append(ConcreteSeg(b))
        for seg in walked.segments:
            if isinstance(seg, bytes):
                segs.append(ConcreteSeg(list(seg)))
            else:  # VarSeg
                segs.append(seg)
        if a:
            segs.append(ConcreteSeg(a))
        return SegList(segs)
```

- [ ] **Step 6: `_build_multi_star_list` — add a `bytes_mode` pass**

`string_mode` is detected first; ints fail its 1-char-str checks, so `bytes_mode` slots between `string_mode` and the `SegList` fallback. After the `if string_mode:` block ends (~L255, before the `# SegList path` comment), add a parallel detection + build. Fixed elements must be ints-in-[0,255]; stars must deref to `bytes`/`SegBytes`/int-code-list/ground-`SegList`-of-codes:

```python
    bytes_mode = True
    for kind, val in segments:
        if kind == "star":
            d = deref(val)
            if isinstance(d, bytes):
                continue
            if isinstance(d, SegBytes):
                continue
            if isinstance(d, list):
                if not all(isinstance(e, int) and not isinstance(e, bool)
                           and 0 <= e <= 255 for e in d):
                    bytes_mode = False
                    break
                continue
            if isinstance(d, SegList):
                walked = d.__walk__()
                if isinstance(walked, list) and all(
                    isinstance(e, int) and not isinstance(e, bool)
                    and 0 <= e <= 255 for e in walked
                ):
                    continue
                bytes_mode = False
                break
            bytes_mode = False
            break
        else:  # "fixed"
            elems = [deref(e) for e in val]
            if any(not (isinstance(e, int) and not isinstance(e, bool)
                        and 0 <= e <= 255) for e in elems):
                bytes_mode = False
                break

    if bytes_mode:
        byte_segs: list = []

        def _push_bytes(bb):
            if bb:
                if byte_segs and isinstance(byte_segs[-1], bytes):
                    byte_segs[-1] = byte_segs[-1] + bb
                else:
                    byte_segs.append(bb)

        for kind, val in segments:
            if kind == "star":
                d = deref(val)
                if isinstance(d, bytes):
                    _push_bytes(d)
                elif isinstance(d, SegBytes):
                    walked = d.__walk__()
                    if isinstance(walked, bytes):
                        _push_bytes(walked)
                    else:
                        for inner_seg in walked.segments:
                            if isinstance(inner_seg, bytes):
                                _push_bytes(inner_seg)
                            else:  # VarSeg
                                byte_segs.append(inner_seg)
                elif isinstance(d, list):
                    _push_bytes(bytes(d))
                elif isinstance(d, SegList):
                    _push_bytes(bytes(d.__walk__()))
            else:  # "fixed" — all ints in [0,255]
                _push_bytes(bytes(deref(e) for e in val))
        if all(isinstance(s, bytes) for s in byte_segs):
            return b"".join(byte_segs)
        return SegBytes(byte_segs)
```

- [ ] **Step 7: `_body_multi_star_unify` — accept bytes target + SegBytes alignment**

Widen the early type guard (~L430) and the Seg walk branch (~L434). Add `bytes` to the `(list, str)` check and `SegBytes` to the `(SegList, SegString)` walk check; add a non-ground `SegBytes` arm that calls a new `_segbytes_align`:

```python
    if not isinstance(d, (list, str, bytes)):
        if isinstance(d, (SegList, SegString, SegBytes)):
            d_walked = d.__walk__()
            if isinstance(d_walked, (list, str, bytes)):
                d = d_walked
            elif isinstance(d_walked, SegString):
                yield from _segstring_align(d_walked, segments, trail, target)
                return
            elif isinstance(d_walked, SegBytes):
                yield from _segbytes_align(d_walked, segments, trail, target)
                return
            else:
```

> The enumeration loop below (~L495) uses `d[pos]` (int for `bytes`) and `d[pos:pos+length]` (`bytes` slice) — both already correct for the codes model once `bytes` reaches the loop.

- [ ] **Step 8: Add `_segbytes_align`**

After `_segstring_align` (~L413), add the bytes parallel. VarSegs bind to `b""`; fixed slots unify against `collapsed[pos]` (an int code); star slots against `collapsed[pos:pos+length]` (`bytes`):

```python
def _segbytes_align(ss, segments, trail, target):
    """Align a non-ground SegBytes with a multi-star pattern. Parallel of
    :func:`_segstring_align`: bind every VarSeg to ``b""`` so the SegBytes
    collapses to its concrete byte prefix, then enumerate the pattern against
    that prefix (codes model: fixed slots see int codes, star slots see
    bytes slices)."""
    from clausal.terms import VarSeg as _VarSeg

    var_segs = [s for s in ss.segments if isinstance(s, _VarSeg)]
    if not var_segs:
        return

    mark = trail.mark()
    bind_ok = True
    for vs in var_segs:
        if not unify(vs.var, b"", trail):
            bind_ok = False
            break
    if not bind_ok:
        trail.undo(mark)
        return

    collapsed = ss.__walk__()
    if not isinstance(collapsed, bytes):
        trail.undo(mark)
        return

    fixed_total = sum(len(v) for k, v in segments if k == "fixed")
    n_stars = sum(1 for k, _ in segments if k == "star")
    n = len(collapsed)
    if n < fixed_total:
        trail.undo(mark)
        return

    remainder = n - fixed_total
    yielded = False
    for split in _multi_star_splits(n_stars, remainder):
        inner = trail.mark()
        ok = True
        pos = 0
        si = 0
        for kind, val in segments:
            if not ok:
                break
            if kind == "fixed":
                for v in val:
                    if not unify(v, collapsed[pos], trail):
                        ok = False
                        break
                    pos += 1
            else:  # star
                length = split[si]
                if not unify(val, collapsed[pos:pos + length], trail):
                    ok = False
                pos += length
                si += 1
        if ok:
            yield True
            yielded = True
        trail.undo(inner)
    if not yielded:
        trail.undo(mark)
        return
    trail.undo(mark)
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `pytest tests/test_bytes_seg_runtime.py -x`
Expected: PASS.

- [ ] **Step 10: Run str regression**

Run: `pytest tests/test_string_list_unification.py tests/test_segstring.py -x`
Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add clausal/logic/runtime/body_star_unify.py tests/test_bytes_seg_runtime.py
git commit -m "feat(runtime): bytes/SegBytes branches in body-star unification"
```

---

## Task 10: Compiler head-match — bytes off MatchValue (F046 extension)

**Files:**
- Modify: `clausal/logic/compiler/head_match.py` — `head_to_match_pattern` MatchValue tuple (L258) + new bytes capture branch (after L270); guard emission in `compile_head_to_match_case` (after the str-guards block ~L1095)
- Test (flip): `tests/audit_2026_05_25/test_class_C04_head_literal_mismatch.py` (~L277)
- Test (new): `tests/test_bytes_head_dispatch.py`

**Interfaces:**
- Consumes: the runtime `bytes`↔list contract (Tasks 4–9), the `str` guard pattern (`head_match.py:1068`).
- Produces: a `bytes`-literal head compiles to `if _bcap == b"abc" or unify(_bcap, b"abc", trail):` — so `Quux(b"abc")` matches a caller `Quux([97,98,99])`.

- [ ] **Step 1: Flip the F046 bytes regression test**

In `tests/audit_2026_05_25/test_class_C04_head_literal_mismatch.py`, replace `test_F046_bytes_literal_head_unaffected` (~L277–297) with the post-feature contract. The int-list assertion flips from `0` to `1`; the docstring updates to reference bytes-as-lists:

```python
def test_F046_bytes_literal_head_matches_int_list():
    """bytes-as-lists extension (supersedes F046's deliberate exclusion): a
    bytes-literal head now compiles to a wildcard-capture + unify guard, so
    an int-list caller matches it under the codes-model contract. A same-type
    bytes caller still hits the == fast path; a str caller still does not
    cross into the bytes domain.
    """
    source = """\
Helper(1),

Quux(b"abc") <- (Helper(1))
"""
    mod = load_inline_clausal("c04_f046_bytes", source).__dict__["$module"]

    # Same-type bytes caller matches (fast == path).
    assert sum(1 for _ in call("Quux", b"abc", module=mod)) == 1
    # bytes-as-lists: the int-code list form now matches (was 0 pre-feature).
    assert sum(1 for _ in call("Quux", [97, 98, 99], module=mod)) == 1
    # No str/bytes cross-unification: a str caller must NOT match.
    assert sum(1 for _ in call("Quux", "abc", module=mod)) == 0
```

- [ ] **Step 2: Write the new dispatch test**

Create `tests/test_bytes_head_dispatch.py`:

```python
import os
import tempfile

from clausal.import_hook import _load_module
from clausal.logic.solve import call


def _load_inline(name, source):
    with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w", delete=False) as f:
        f.write(source)
        f.flush()
        path = f.name
    try:
        return _load_module(name, path).__dict__["$module"]
    finally:
        os.unlink(path)


_SRC = """\
Helper(1),

Quux(b"abc") <- (Helper(1))
"""


def test_bytes_head_matched_by_bytes():
    # nv
    mod = _load_inline("bytes_head_a", _SRC)
    assert sum(1 for _ in call("Quux", b"abc", module=mod)) == 1


def test_bytes_head_matched_by_intlist():
    # nv
    mod = _load_inline("bytes_head_b", _SRC)
    assert sum(1 for _ in call("Quux", [97, 98, 99], module=mod)) == 1


def test_bytes_head_not_matched_by_wrong_intlist():
    # nv
    mod = _load_inline("bytes_head_c", _SRC)
    assert sum(1 for _ in call("Quux", [1, 2, 3], module=mod)) == 0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_bytes_head_dispatch.py tests/audit_2026_05_25/test_class_C04_head_literal_mismatch.py::test_F046_bytes_literal_head_matches_int_list -x`
Expected: FAIL — `Quux(b"abc")` still on `MatchValue`, so `[97,98,99]` yields 0.

- [ ] **Step 4: Move `bytes` out of the MatchValue tuple**

In `head_to_match_pattern`, change the scalar tuple (L258) and update the comment (L252–257) so `bytes` is no longer a `MatchValue`:

```python
    # Python scalar literals (non-string, non-bytes): C-level == inside the
    # match arm. str and bytes are handled below: a raw MatchValue compares
    # with ==, which rejects a char-list / int-list caller despite the
    # strings-as-lists / bytes-as-lists contracts (F046 + bytes-as-lists).
    if isinstance(term, (int, float, complex)):
        return ast.MatchValue(value=ast.Constant(value=term))
```

- [ ] **Step 5: Add the `bytes` capture branch**

Immediately after the `str` capture branch (L266–270), add a parallel `bytes` branch tagged `"bytes"`:

```python
    # Python bytes literal → wildcard capture + runtime unify guard, mirroring
    # the str path. Routes through unify() so the bytes-as-lists contract
    # (bytes ↔ int-code-list) is honoured for clause heads. The guard
    # short-circuits on a same-type bytes caller via `==` before unify().
    if isinstance(term, bytes):
        cap_name = f"_bcap{len(list_guards) if list_guards is not None else 0}"
        if list_guards is not None:
            list_guards.append(("bytes", cap_name, term))
        return ast.MatchAs(pattern=None, name=cap_name)
```

- [ ] **Step 6: Emit the bytes guards**

In `compile_head_to_match_case`, after the str-guards loop (~L1095), add a parallel bytes-guards loop. It is identical in shape to the str block (`_tag == "bytes"`, literal is a `bytes` constant), reusing the same `if _bcap == b"abc" or unify(_bcap, b"abc", trail):` structure:

```python
    # Emit bytes-literal guards (bytes-as-lists): wildcard capture +
    # same-type short-circuit. Mirrors the str-guards block above.
    bytes_guards = [g for g in list_guards if g and g[0] == "bytes"]
    for _tag, cap_name, literal in bytes_guards:
        inner = [ast.If(
            test=ast.BoolOp(
                op=ast.Or(),
                values=[
                    ast.Compare(
                        left=_name(cap_name),
                        ops=[ast.Eq()],
                        comparators=[ast.Constant(value=literal)],
                    ),
                    _call(
                        _name("unify"),
                        _name(cap_name),
                        ast.Constant(value=literal),
                        _name(trail_name),
                    ),
                ],
            ),
            body=inner,
            orelse=[],
        )]
```

> Verify how the str block obtains `trail_name`/`inner` and where the wrapped `inner` is spliced back into the case body (the str block's tail). Mirror that exactly — the bytes loop must wrap the same `inner` after (or before) the str loop so both guard sets nest around the body.

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_bytes_head_dispatch.py tests/audit_2026_05_25/test_class_C04_head_literal_mismatch.py -x`
Expected: PASS (including the flipped test and the rest of the C04 module).

- [ ] **Step 8: Run str head-dispatch regression**

Run: `pytest tests/audit_2026_05_25/ -x -k "C04 or head"`
Expected: PASS — str head dispatch unchanged.

- [ ] **Step 9: Commit**

```bash
git add clausal/logic/compiler/head_match.py tests/test_bytes_head_dispatch.py tests/audit_2026_05_25/test_class_C04_head_literal_mismatch.py
git commit -m "feat(compiler): move bytes off MatchValue to unify-guard (bytes-as-lists)"
```

---

## Task 11: First-arg indexing — _bytelist_to_bytes_or_none

**Files:**
- Modify: `clausal/logic/compiler/arg_index.py` — add `_bytelist_to_bytes_or_none` (after `_charlist_to_str_or_none` ~L65); add bytes call sites in `_arg_to_index_key` (~L88), `_runtime_arg_key` (~L121), `_static_call_key` (~L147)
- Test: `tests/test_bytes_indexing.py`

**Interfaces:**
- Consumes: the bytes head-dispatch contract (Task 10).
- Produces: a `bytes`-literal head and an int-list caller share a dispatch bucket (`_bytelist_to_bytes_or_none([97,98,99]) == b"abc"`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bytes_indexing.py`:

```python
import os
import tempfile

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.compiler.arg_index import _bytelist_to_bytes_or_none


def _load_inline(name, source):
    with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w", delete=False) as f:
        f.write(source)
        f.flush()
        path = f.name
    try:
        return _load_module(name, path).__dict__["$module"]
    finally:
        os.unlink(path)


class TestByteListCanonicaliser:
    def test_int_list_to_bytes(self):
        # nv
        assert _bytelist_to_bytes_or_none([97, 98, 99]) == b"abc"

    def test_empty_is_none(self):
        # nv
        assert _bytelist_to_bytes_or_none([]) is None

    def test_out_of_range_is_none(self):
        # nv
        assert _bytelist_to_bytes_or_none([97, 256]) is None

    def test_non_int_is_none(self):
        # nv
        assert _bytelist_to_bytes_or_none(["a"]) is None


_SRC = """\
Helper(1),

Code(b"red") <- (Helper(1))
Code(b"green") <- (Helper(1))
Code(b"blue") <- (Helper(1))
"""


class TestBytesDispatchBuckets:
    def test_intlist_caller_reaches_bytes_clause(self):
        # nv  — list(b"green") == [103,114,101,101,110]
        mod = _load_inline("bytes_idx_a", _SRC)
        assert sum(1 for _ in call("Code", list(b"green"), module=mod)) == 1

    def test_non_matching_intlist_matches_nothing(self):
        # nv
        mod = _load_inline("bytes_idx_b", _SRC)
        assert sum(1 for _ in call("Code", [1, 2, 3], module=mod)) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_bytes_indexing.py -x`
Expected: FAIL — `_bytelist_to_bytes_or_none` does not exist; int-list caller does not bucket with the bytes head.

- [ ] **Step 3: Add `_bytelist_to_bytes_or_none`**

After `_charlist_to_str_or_none` (~L65), mirror it for the codes model:

```python
def _bytelist_to_bytes_or_none(seq) -> bytes | None:
    """Canonicalise a list/tuple of ints in [0, 255] to its joined bytes.

    Returns ``None`` when *seq* is empty or contains any non-int / bool /
    out-of-range element. The bytes-as-lists analog of
    ``_charlist_to_str_or_none``: a head ``Foo(b"abc")`` and a caller passing
    ``[97, 98, 99]`` produce the same bucket key.
    """
    if not seq:
        return None
    for c in seq:
        if type(c) is not int or not (0 <= c <= 255):
            return None
    return bytes(seq)
```

> `type(c) is not int` already excludes `bool` (a `bool` is not exactly `int`), matching the strict canonicaliser style.

- [ ] **Step 4: Add the three call sites**

In `_arg_to_index_key` (~L88), after the existing `_charlist_to_str_or_none` attempt, try the bytes canonicaliser before falling back to `_INDEX_VAR`:

```python
    if isinstance(arg, (list, tuple)):
        s = _charlist_to_str_or_none(arg)
        if s is not None:
            return s
        b = _bytelist_to_bytes_or_none(arg)
        if b is not None:
            return b
        return _INDEX_VAR
```

In `_runtime_arg_key` (~L121), the same addition:

```python
    if isinstance(a, (list, tuple)):
        s = _charlist_to_str_or_none(a)
        if s is not None:
            return s
        b = _bytelist_to_bytes_or_none(a)
        if b is not None:
            return b
        return _INDEX_VAR
```

In `_static_call_key` (~L147–156), after building `elts`, try str canonicalisation then bytes:

```python
        s = _charlist_to_str_or_none(elts)
        if s is not None:
            return s
        return _bytelist_to_bytes_or_none(elts)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_bytes_indexing.py -x`
Expected: PASS.

- [ ] **Step 6: Run indexing regression**

Run: `pytest tests/ -x -k "index or dispatch"`
Expected: PASS — str/char-list bucketing unchanged.

- [ ] **Step 7: Commit**

```bash
git add clausal/logic/compiler/arg_index.py tests/test_bytes_indexing.py
git commit -m "feat(compiler): _bytelist_to_bytes_or_none indexing canonicaliser"
```

---

## Task 12: DCG / phrase over bytes

**Files:**
- Modify: `clausal/logic/builtins/dcg.py` — `_sequence__3` (~L93): add `bytes` to the `import` + container checks and the build-mode branches
- Test: `tests/test_bytes_dcg.py`

**Interfaces:**
- Consumes: `phrase//2,3` already walk inputs via `normalize_seg_input` (now `SegBytes`-aware, Task 6) and dispatch through `_head_list_unify_input`/`_body_star_unify` (now `bytes`-aware, Tasks 7–9). DCG terminals compile to `s_in is [t1,…,tn,*s_out]` constraints (`term_rewriting.py:_rewrite_dcg_body`) — no change needed there.
- Produces: a binary-protocol grammar driven by `phrase//` parses a `bytes` subject; the remainder is preserved as `bytes`; `sequence//1` builds `bytes`/`SegBytes`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bytes_dcg.py`. Use the project's DCG surface — confirm syntax against an existing DCG test (`grep -rl "phrase" tests/`), adapting the grammar declaration form as needed:

```python
import os
import tempfile

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


def _load_inline(name, source):
    with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w", delete=False) as f:
        f.write(source)
        f.flush()
        path = f.name
    try:
        return _load_module(name, path).__dict__["$module"]
    finally:
        os.unlink(path)


# A minimal binary-protocol grammar: match the literal b"GET " then bind the
# rest. Terminals are bytes literals decomposing to int codes.
_SRC = """\
get_line --> b"GET ", rest.
rest --> [].
"""


def test_phrase_over_bytes_parses_prefix():
    # nv  — phrase(get_line, b"GET ", Rest) leaves Rest = b""
    mod = _load_inline("bytes_dcg_a", _SRC)
    Rest = Var()
    sols = list(call("phrase", "get_line", b"GET ", Rest, module=mod))
    assert len(sols) >= 1
    assert deref(Rest) == b""


def test_phrase_remainder_preserved_as_bytes():
    # nv  — phrase(<match b"GET ">, b"GET /x", Rest) binds Rest=b"/x" (bytes)
    mod = _load_inline("bytes_dcg_b", "g --> b\"GET \".\n")
    Rest = Var()
    sols = list(call("phrase", "g", b"GET /x", Rest, module=mod))
    assert len(sols) >= 1
    assert deref(Rest) == b"/x"
    assert type(deref(Rest)) is bytes
```

> If the DCG grammar/`phrase` call surface differs (rule-reference form, arg arity), adjust to match an existing passing DCG test. The assertions on `bytes` preservation are the contract; the grammar syntax is incidental.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_bytes_dcg.py -x`
Expected: FAIL — `sequence//3`/state-threading rejects the `bytes` subject (`isinstance(s0_val, (list, str))` excludes `bytes`), so the remainder is not bound or not preserved as `bytes`.

- [ ] **Step 3: Add `bytes` handling to `_sequence__3`**

In `dcg.py`, `_sequence__3` (~L93):

(a) widen the input guard so a `bytes` `lst` is accepted (~L120): `if is_var(lst_val) or not isinstance(lst_val, (list, str, bytes)):`

(b) Mode A — widen the bound-`S0` check to include `bytes` (~L133): `if isinstance(s0_val, (list, str)):` → `if isinstance(s0_val, (list, str, bytes)):`. In the prefix-normalisation, normalise `bytes` to `list(bytes)` (int codes) so the `==` comparison crosses container types correctly:

```python
        s0_pref = s0_val[:n]
        lst_pref = lst_val
        s0_pref_norm = list(s0_pref) if isinstance(s0_pref, (str, bytes)) else s0_pref
        lst_pref_norm = list(lst_pref) if isinstance(lst_pref, (str, bytes)) else lst_pref
```

> `list(str)` yields 1-char strs and `list(bytes)` yields ints — they never compare equal across the `str`/`bytes` divide, preserving the no-cross-unification guard. `s0_val[n:]` is a `bytes` slice, so `S` binds to `bytes`.

(c) Mode B — when both `lst_val` and `s_val` are `bytes`, concatenate as `bytes` (~L150): add before the str/list fallback:

```python
        if isinstance(lst_val, bytes) and isinstance(s_val, bytes):
            expected = lst_val + s_val
        elif isinstance(lst_val, str) and isinstance(s_val, str):
            expected = lst_val + s_val
        else:
            ...
```

(d) Mode C — when `lst` is `bytes` and both ends unbound, build a `SegBytes` (~L167): add before the str/SegString branch:

```python
        if isinstance(lst_val, bytes):
            ss = SegBytes([lst_val, VarSeg(s_val)])
            mark = trail.mark()
            if unify(s0, ss, trail):
                yield (_proceed, None)
            trail.undo(mark)
        elif isinstance(lst_val, str):
            ...
```

(e) Update the local import (~L111) to include `SegBytes`:

```python
    from clausal.terms import SegList, SegString, SegBytes, ConcreteSeg, VarSeg
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_bytes_dcg.py -x`
Expected: PASS.

- [ ] **Step 5: Run the DCG / phrase regression (str unchanged)**

Run: `pytest tests/ -x -k "dcg or phrase or sequence"`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add clausal/logic/builtins/dcg.py tests/test_bytes_dcg.py
git commit -m "feat(dcg): bytes subjects & terminals through phrase// and sequence//"
```

---

## Task 13: Consolidated adversarial coverage audit

**Files:**
- Modify: `tests/test_bytes_list_unification.py` (add any of the 9 spec categories not yet covered: type preservation through recursion, `.hex()`/`.decode()` on bound results)
- Test: (the same file)

**Interfaces:**
- Consumes: the complete stack (Tasks 1–12).
- Produces: every numbered category from the spec's Testing section has at least one assertion across the test suite.

- [ ] **Step 1: Map spec categories to existing tests**

The 9 spec testing categories map to: (1) core unify → `test_bytes_list_unification.py::TestBytesUnifiesWithIntList`/`TestBytesListVarBinding`; (2) no fixed point → `TestBytesNoFixedPoint`; (3) type preservation → **add below**; (4) SegBytes partial → `test_segbytes.py`; (5) head literal → `test_bytes_head_dispatch.py` + flipped C04; (6) indexing → `test_bytes_indexing.py`; (7) DCG → `test_bytes_dcg.py`; (8) promiscuity → `TestBytesPromiscuityAndGuards`; (9) out-of-scope guards → `TestBytesNoCrossWithStr`. Only category (3) needs new assertions.

- [ ] **Step 2: Write the failing type-preservation tests**

Append to `tests/test_bytes_list_unification.py`:

```python
class TestBytesTypePreservation:
    def test_bound_var_stays_bytes_and_methods_work(self):
        # nv  — a bytes threaded through unify stays bytes; methods callable
        trail = Trail()
        X = Var()
        assert unify(X, b"\x48\x49", trail)
        v = deref(X)
        assert type(v) is bytes
        assert v.hex() == "4849"
        assert v.decode() == "HI"

    def test_tail_of_bytes_decomposition_stays_bytes(self):
        # nv  — [H, *T] is b"abc": T preserves bytes, supports .decode()
        from clausal.logic.runtime.body_star_unify import _body_star_unify
        trail = Trail()
        H, T = Var(), Var()
        assert _body_star_unify(b"abc", [H], T, [], trail)
        assert deref(T).decode() == "bc"
```

- [ ] **Step 3: Run tests to verify they pass (stack already supports this)**

Run: `pytest tests/test_bytes_list_unification.py::TestBytesTypePreservation -x`
Expected: PASS — the contract from Tasks 4/9 already preserves `bytes`. (If a test fails, that is a real coverage gap to fix in the relevant layer, not here.)

- [ ] **Step 4: Run the FULL suite (green-bar gate)**

Run: `pytest -q`
Expected: PASS — entire suite, str + bytes + all prior tests.

- [ ] **Step 5: Commit**

```bash
git add tests/test_bytes_list_unification.py
git commit -m "test(bytes): consolidate adversarial coverage — type preservation"
```

---

## Task 14: Benchmark — bench_bytes_dispatch.py

**Files:**
- Create: `benchmarks/bench_bytes_dispatch.py`

**Interfaces:**
- Consumes: the bytes head-dispatch path (Task 10).
- Produces: a runnable micro-benchmark mirroring `bench_f046_head_dispatch.py` — same-type `bytes` caller (fast `==`) vs int-list caller (`unify` path) vs an `int`-literal `MatchValue` baseline.

- [ ] **Step 1: Create the benchmark**

Mirror `benchmarks/bench_f046_head_dispatch.py`, substituting `bytes` literals for `str` literals and an int-list caller for the char-list caller:

```python
"""Micro-benchmark for the bytes-as-lists head-dispatch path.

After bytes-as-lists, a clause head pinning a bytes literal (e.g.
``Code(b"red") <- body``) compiles to a wildcard capture + same-type
short-circuit unify guard (``_bcap == b"red" or unify(_bcap, b"red", trail)``)
instead of a bare ``MatchValue``. This measures dispatch cost for:

  (i)  a same-type **bytes** caller — should hit the fast ``==`` disjunct;
  (ii) an **int-list** caller        — falls through to ``unify()`` (the
                                        codes-model path).

Compared against an ``int``-literal dispatch table (still ``MatchValue``).

Usage (from project root):
    python benchmarks/bench_bytes_dispatch.py
"""

from __future__ import annotations

import os
import tempfile
import timeit

from clausal.import_hook import _load_module
from clausal.logic.solve import call


def _load_inline(name: str, source: str):
    with tempfile.NamedTemporaryFile(
        suffix=".clausal", mode="w", delete=False
    ) as f:
        f.write(source)
        f.flush()
        path = f.name
    try:
        return _load_module(name, path).__dict__["$module"]
    finally:
        os.unlink(path)


_BYTES_SRC = """\
Helper(1),

Color(b"red") <- (Helper(1))
Color(b"green") <- (Helper(1))
Color(b"blue") <- (Helper(1))
Color(b"cyan") <- (Helper(1))
Color(b"magenta") <- (Helper(1))
Color(b"yellow") <- (Helper(1))
"""

_INT_SRC = """\
Helper(1),

Code(10) <- (Helper(1))
Code(20) <- (Helper(1))
Code(30) <- (Helper(1))
Code(40) <- (Helper(1))
Code(50) <- (Helper(1))
Code(60) <- (Helper(1))
"""

_bytes_mod = _load_inline("bench_bytes_str", _BYTES_SRC)
_int_mod = _load_inline("bench_bytes_int", _INT_SRC)


def _drain(functor: str, arg, mod) -> int:
    return sum(1 for _ in call(functor, arg, module=mod))


BENCHMARKS = [
    (
        "bytes head, bytes caller (fast == path)",
        lambda: _drain("Color", b"magenta", _bytes_mod),
    ),
    (
        "bytes head, int-list caller (unify path)",
        lambda: _drain("Color", list(b"magenta"), _bytes_mod),
    ),
    (
        "int head, int caller (MatchValue baseline)",
        lambda: _drain("Code", 50, _int_mod),
    ),
]

N = 100_000


if __name__ == "__main__":
    assert _drain("Color", b"magenta", _bytes_mod) == 1
    assert _drain("Color", list(b"magenta"), _bytes_mod) == 1
    assert _drain("Code", 50, _int_mod) == 1

    col_w = 44
    print(f"\n{'Dispatch':<{col_w}}  {'us/call':>10}  {'iterations':>12}")
    print("-" * (col_w + 28))
    for label, fn in BENCHMARKS:
        total_s = timeit.timeit(fn, number=N)
        us = total_s / N * 1e6
        print(f"{label:<{col_w}}  {us:>10.3f}  {N:>12,}")
    print()
```

- [ ] **Step 2: Run the benchmark (sanity asserts must pass)**

Run: `python benchmarks/bench_bytes_dispatch.py`
Expected: prints three timing rows; the embedded `assert` sanity checks pass (each probe yields exactly 1).

- [ ] **Step 3: Commit**

```bash
git add benchmarks/bench_bytes_dispatch.py
git commit -m "bench: bytes head-dispatch micro-benchmark"
```

---

## Task 15: Final integration verification + spec status

**Files:**
- Modify: `docs/superpowers/specs/2026-06-18-bytes-as-lists-design.md` (status line), `todo/bytes-as-lists.md` (mark done)

**Interfaces:**
- Consumes: all prior tasks.
- Produces: a clean-build, full-green checkpoint and updated bookkeeping.

- [ ] **Step 1: Clean rebuild of all C extensions**

Run: `python setup.py build_ext --inplace`
Expected: all extensions compile with no errors/warnings.

- [ ] **Step 2: Run the FULL test suite**

Run: `pytest -q`
Expected: PASS, no regressions. Confirm the 7 success criteria from the spec are each exercised by a passing test (cross-check against Task 13 Step 1 map + DCG/indexing/head tasks).

- [ ] **Step 3: Update spec + todo status**

In `docs/superpowers/specs/2026-06-18-bytes-as-lists-design.md`, change the `**Status:**` line to `Implemented (2026-06-18)`. In `todo/bytes-as-lists.md`, mark the feature done (mirror how other completed todos in that file are marked).

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-06-18-bytes-as-lists-design.md todo/bytes-as-lists.md
git commit -m "docs: mark bytes-as-lists implemented; full suite green"
```

---

## Self-Review

**Spec coverage** (each spec section → task):
- Goal `b"abc" ↔ [97,98,99]` → Tasks 4, 13.
- Architecture §1 core unify branches → Task 4; type-preserving walk/inspect/copy → Task 5 (copy/collect/is_ground deliberately unchanged, documented).
- Architecture §2 `SegBytes` term (all bullets: segments, validation, walk, unify ground/gen/list/NotImplemented, eq/hash unhashable, sequence-as-ints) → Tasks 1, 2, 3.
- Architecture §3 seg-runtime (`_list_unify.c`, `list_unify.py`, `_seg_helpers.py`) + element check `int ∈ [0,255]` → Tasks 6, 7, 8; body-star runtime → Task 9.
- Architecture §4 head-match `bytes` off `MatchValue` + same-type guard → Task 10.
- Architecture §5 first-arg indexing `_bytelist_to_bytes_or_none` + `_INDEXABLE_TYPES` (already lists bytes) → Task 11.
- Architecture §6 DCG/`phrase` (terminal decomposition, subject decomposition, remainder preserved/`SegBytes`) → Task 12; F068 left unresolved (adopts in-force phrase/3 contract, str not regressed — verified by Task 12 Step 5).
- Error handling (malformed segments → `PartialTermError`; out-of-range → fail; VarSeg non-bytes → `PartialTermError`) → Tasks 1, 4, plus `test_varseg_bound_to_out_of_range_int_raises`.
- Out of scope (no str↔bytes cross, no bytearray, str unchanged) → Task 4 `TestBytesNoCrossWithStr`, str regression runs in Tasks 4/5/8/9/10/12.
- Testing §1–9 → Task 13 Step 1 map (all covered); benchmark → Task 14.
- Success criteria 1–7 → Task 15 Step 2.

**Placeholder scan:** No "TBD"/"add error handling"/"similar to Task N" — every code step shows complete code or a precise old→new edit. Two steps (Task 5 Step 1, Task 12 Step 1) flag a `grep`/`confirm` because the exact public wrapper name / DCG grammar syntax must be verified against the live codebase before use; the contract assertions are concrete.

**Type consistency:** `SegBytes` (capital-B) used throughout; `.segments` property defined in Task 1, consumed in Tasks 2/7/8/9. `maybe_promote_to_bytes` signature `(result) -> bytes|list` consistent across `_seg_helpers.py` (Task 6), `list_unify.py` (Task 7), C (Task 8), `body_star_unify.py` (Task 9). `_bytelist_to_bytes_or_none` (Task 11) parallels `_charlist_to_str_or_none`. Guard-tag strings `"bytes"`/`"str"` (Task 10) match emission loops. `_segbytes_unify_gen`/`_segbytes_align` names consistent between definition and call sites.

---

**Plan complete and saved to `docs/superpowers/plans/2026-06-18-bytes-as-lists.md`.**
