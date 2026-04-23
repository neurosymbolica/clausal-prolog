# Strings as Lists of Characters

## Motivation

in_ Prolog (especially Scryer Prolog), strings are lists of characters. This isn't a historical
accident — it's a logical uniformity principle. when strings *are* lists:

1. **One sequence type, one set of predicates.** `append/3`, `member/2`, `length/2`, `reverse/2`,
   `maplist/2` all work on strings for free. No duplication.
2. **Pattern matching via unification.** `[H|T] = "hello"` gives `H = h, T = "ello"`.
   Multi-element patterns like `append(X, "orld", "world")` just work.
3. **DCGs parse strings directly.** DCGs consume lists; strings *are* lists; grammars handle
   character-level text parsing with zero conversion.
4. **Full relational reasoning.** Strings participate in the same relational framework — partial
   instantiation, constraint propagation, backtracking over structure.

Clausal uses Python `str` for strings and Python `list` for lists. These are completely separate
types. This creates three concrete pain points:

| Problem | Severity | Example |
|---------|----------|---------|
| **Predicate duplication** | Moderate | `append/3` vs `atom_concat/3`, `length/2` vs `atom_length/2` |
| **DCGs can't parse strings** | High | Must call `atom_chars` first, then `phrase` on the char list |
| **No structural pattern matching on strings** | High | Can't write `[*Prefix, 'a', *Suffix]` against a string |

The goal of this plan is to make strings behave *logically* as lists of single-character strings
while keeping Python `str` as the internal representation for performance and Python interop. This
is a Liskov-style subtyping approach: anywhere a list of characters is expected, a string works.

Python `str` already satisfies the sequence protocol — `len("hello")` returns 5, `"hello"[0]`
returns `"h"`, iteration yields single characters. The logic layer just needs to recognise this.

## Key Insight: What NOT to Do

Do **not** make strings internally be lists. That would be a performance disaster (Python `str` is
far faster than `list` of single-char strings for concatenation, comparison, hashing, I/O) and
would break Python interop. The correct approach is to make the *logic layer* treat strings as
sequences of characters when they interact with list operations, while preserving `str` identity.

---

## Design Decisions

### D1: What is a "character" in Clausal?

A character is a single-character Python string: `"a"`, `"Z"`, `" "`, etc. This matches what
`atom_chars/2` already produces (`chars.py:192`: `unify(chars, list(va), trail)` — `list("hello")`
yields `['h', 'e', 'l', 'l', 'o']`).

### D2: when does a string behave as a list?

A string behaves as a list of characters in these contexts:
- **Unification** against a list or SegList
- **List builtins** that accept sequence arguments
- **DCG operations** that consume lists
- **SegList pattern matching** (multi-star patterns)

A string does NOT behave as a list in these contexts:
- **String-vs-string unification** remains fast equality (`"abc" = "abc"`)
- **`is_list/1`** does NOT succeed for strings (strings are a subtype, but `is_list` tests the
  exact type; we add `is_chars/1` for the union type — see Phase 4)
- **`is_str/1`** continues to succeed for strings only
- **Python interop** — strings remain `str` when passed to Python functions

### D3: What type do results have?

when a list builtin operates on string inputs and produces a sequence result:
- If **all** sequence inputs are strings and the result is a valid string (sequence of single-char
  strings) → return `str`
- Otherwise → return `list`

Examples:
- `append("hel", "lo", X)` → `X = "hello"` (string)
- `append("hel", [1, 2], X)` → `X = ['h', 'e', 'l', 1, 2]` (list)
- `reverse("hello", X)` → `X = "olleh"` (string)
- `in_(X, "hello")` → `X = "h"` ; `X = "e"` ; ... (single-char strings)

### D4: SegList unification with strings

when a SegList unifies against a string, the string is treated as a sequence of single-char
strings. The VarSegs bind to **lists** of characters (not substrings), because the VarSeg
contract is to bind to a list. To get a substring result, use `atom_chars` or the new `is_chars`
predicate.

Wait — actually, this needs more thought. Consider:

```clausal
split_at_comma([*Before, ',', *After], Before, After)
```

If called with `split_at_comma("hello,world", B, A)`, the SegList machinery would bind:
- `Before = ['h', 'e', 'l', 'l', 'o']` (list)
- `After = ['w', 'o', 'r', 'l', 'd']` (list)

This is correct and consistent — VarSegs always bind to lists. If the user wants strings back,
they can use `atom_chars` to reconstitute. However, it may be more ergonomic to have VarSegs bind
to strings when the match target was a string. We defer this decision:

- **Phase 2 (initial):** VarSegs bind to lists of chars when matching a string.
- **Phase 5 (optional enhancement):** Add a `SegString` type or flag that causes VarSegs to bind
  to substrings instead. This is an optimisation/ergonomics improvement, not a correctness issue.

### D5: DCG difference lists

DCGs operate on difference lists. when the input is a string, the difference-list remainder
should also be a string (for consistency and because string slicing is O(n) anyway). So:

```clausal
greeting >> (["h", "i"])
```

`phrase(greeting, "hi")` should work. Internally, `S0 = "hi"`, `S = ""` (empty string remainder).
This means DCG code needs to handle `str` alongside `list` for the S0/S arguments.

---

## Phase 1: C-Level String–List Unification

**Goal:** Make `"abc" = ['a', 'b', 'c']` succeed in unification. This is the foundation.

### Changes

#### `_variables.c` — `do_unify` function (line 967)

Currently, `do_unify` handles list-vs-list at lines 967–979, then falls through to `__unify__`
hooks (989–1023), then to `PyObject_RichCompareBool` equality (1030). Strings hit the equality
path and never interact with lists.

**Add a new branch** between the list-vs-list block (line 979) and the `__unify__` hook (line 989)
to handle string-vs-list and list-vs-string unification:

```c
/* ── String ↔ List unification ─────────────────────────────────────────
 * Treat a Python str as a list of single-character strings.
 * "abc" unifies with ['a', 'b', 'c'] element-wise.
 */
if (PyUnicode_Check(t1) && PyList_Check(t2)) {
    Py_ssize_t n = PyUnicode_GET_LENGTH(t1);
    if (n != PyList_GET_SIZE(t2)) return 0;
    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *ch = PyUnicode_Substring(t1, i, i + 1);
        if (!ch) return -1;
        int r = do_unify(ch, PyList_GET_ITEM(t2, i),
                         trail, depth + 1, oc);
        Py_DECREF(ch);
        if (r != 1) return r;
    }
    return 1;
}
if (PyList_Check(t1) && PyUnicode_Check(t2)) {
    /* Symmetric case — delegate to above by swapping */
    Py_ssize_t n = PyUnicode_GET_LENGTH(t2);
    if (PyList_GET_SIZE(t1) != n) return 0;
    for (Py_ssize_t i = 0; i < n; i++) {
        PyObject *ch = PyUnicode_Substring(t2, i, i + 1);
        if (!ch) return -1;
        int r = do_unify(PyList_GET_ITEM(t1, i), ch,
                         trail, depth + 1, oc);
        Py_DECREF(ch);
        if (r != 1) return r;
    }
    return 1;
}
```

**Important:** This block must go **after** the list-vs-list block (967) and **before** the
`__unify__` hook block (989). The existing string-vs-string equality at line 1030 still handles
`"abc" = "abc"` via fast-path `PyObject_RichCompareBool`.

**Performance note:** `PyUnicode_Substring` creates a new string object per character. For the
common case (string vs ground list of single-char strings), this is acceptable. If profiling
reveals a bottleneck, we can add a fast path that checks if all list elements are single-char
strings and uses `PyUnicode_READ_CHAR` for direct comparison.

**Alternative (faster) implementation** — avoid allocating char objects:

```c
if (PyUnicode_Check(t1) && PyList_Check(t2)) {
    Py_ssize_t n = PyUnicode_GET_LENGTH(t1);
    if (n != PyList_GET_SIZE(t2)) return 0;
    int kind = PyUnicode_KIND(t1);
    void *data = PyUnicode_DATA(t1);
    for (Py_ssize_t i = 0; i < n; i++) {
        Py_UCS4 c1 = PyUnicode_READ(kind, data, i);
        PyObject *elem = PyList_GET_ITEM(t2, i);
        /* Deref the list element in case it's a Var */
        elem = var_deref(elem);
        if (Var_Check(elem)) {
            /* List element is an unbound var — bind it to the char */
            PyObject *ch = PyUnicode_Substring(t1, i, i + 1);
            if (!ch) return -1;
            int r = do_unify(ch, elem, trail, depth + 1, oc);
            Py_DECREF(ch);
            if (r != 1) return r;
        } else if (PyUnicode_Check(elem) &&
                   PyUnicode_GET_LENGTH(elem) == 1 &&
                   PyUnicode_READ_CHAR(elem, 0) == c1) {
            continue;  /* Match — no allocation needed */
        } else {
            return 0;  /* Mismatch */
        }
    }
    return 1;
}
```

This avoids allocating a new string for each character in the ground-ground case (which is the
most common), only falling back to `PyUnicode_Substring` when binding a Var.

### Tests

Create `tests/test_string_list_unification.py`:

```python
"""Tests for Phase 1: string ↔ list unification at the C level."""

from clausal.logic.variables import Var, Trail, unify, deref

class TestStringListUnification:
    """String treated as list of characters in unification."""

    def test_string_unifies_with_char_list(self):
        """'abc' = ['a', 'b', 'c'] succeeds."""
        trail = Trail()
        assert unify("abc", ['a', 'b', 'c'], trail)

    def test_char_list_unifies_with_string(self):
        """Symmetric: ['a', 'b', 'c'] = 'abc' succeeds."""
        trail = Trail()
        assert unify(['a', 'b', 'c'], "abc", trail)

    def test_string_list_length_mismatch_fails(self):
        """'ab' = ['a', 'b', 'c'] fails (length mismatch)."""
        trail = Trail()
        assert not unify("ab", ['a', 'b', 'c'], trail)

    def test_string_list_content_mismatch_fails(self):
        """'abc' = ['a', 'x', 'c'] fails (content mismatch)."""
        trail = Trail()
        assert not unify("abc", ['a', 'x', 'c'], trail)

    def test_string_vs_string_equality(self):
        """'abc' = 'abc' still works (equality fast path)."""
        trail = Trail()
        assert unify("abc", "abc", trail)

    def test_string_vs_string_mismatch(self):
        """'abc' != 'def' still fails."""
        trail = Trail()
        assert not unify("abc", "def", trail)

    def test_string_list_with_vars(self):
        """'abc' = [X, Y, Z] binds X='a', Y='b', Z='c'."""
        trail = Trail()
        X, Y, Z = Var("X"), Var("Y"), Var("Z")
        assert unify("abc", [X, Y, Z], trail)
        assert deref(X) == "a"
        assert deref(Y) == "b"
        assert deref(Z) == "c"

    def test_string_list_partial_vars(self):
        """'abc' = ['a', X, 'c'] binds X='b'."""
        trail = Trail()
        X = Var("X")
        assert unify("abc", ['a', X, 'c'], trail)
        assert deref(X) == "b"

    def test_string_list_var_mismatch(self):
        """'abc' = ['a', X, 'z'] fails at position 2."""
        trail = Trail()
        X = Var("X")
        assert not unify("abc", ['a', X, 'z'], trail)

    def test_empty_string_empty_list(self):
        """'' = [] succeeds."""
        trail = Trail()
        assert unify("", [], trail)

    def test_single_char_string_singleton_list(self):
        """'a' = ['a'] succeeds."""
        trail = Trail()
        assert unify("a", ['a'], trail)

    def test_string_vs_non_char_list_fails(self):
        """'abc' = [1, 2, 3] fails (int elements, not chars)."""
        trail = Trail()
        assert not unify("abc", [1, 2, 3], trail)

    def test_string_vs_multi_char_list_fails(self):
        """'abc' = ['ab', 'c'] fails (length 3 vs length 2)."""
        trail = Trail()
        assert not unify("abc", ['ab', 'c'], trail)

    def test_string_list_backtracking(self):
        """Bindings are properly trailed and undone."""
        trail = Trail()
        X = Var("X")
        mark = trail.mark()
        assert unify("abc", ['a', X, 'c'], trail)
        assert deref(X) == "b"
        trail.undo(mark)
        assert deref(X) is X  # Unbound again

    def test_unicode_string_list(self):
        """Unicode strings work: '日本' = ['日', '本'] succeeds."""
        trail = Trail()
        assert unify("日本", ['日', '本'], trail)

    def test_unicode_string_list_with_var(self):
        """'日本語' = [X, '本', Y] binds X='日', Y='語'."""
        trail = Trail()
        X, Y = Var("X"), Var("Y")
        assert unify("日本語", [X, '本', Y], trail)
        assert deref(X) == "日"
        assert deref(Y) == "語"

    def test_nested_list_with_string(self):
        """[1, 'abc', 2] = [1, ['a', 'b', 'c'], 2] succeeds."""
        trail = Trail()
        assert unify([1, "abc", 2], [1, ['a', 'b', 'c'], 2], trail)

    def test_list_of_strings_vs_list_of_lists(self):
        """['ab', 'cd'] = [['a','b'], ['c','d']] succeeds (recursive)."""
        trail = Trail()
        assert unify(["ab", "cd"], [['a', 'b'], ['c', 'd']], trail)
```

### Edge Cases

| Input | Expected | Rationale |
|-------|----------|-----------|
| `"" = []` | Succeeds | Empty string ≡ empty list |
| `"a" = ['a']` | Succeeds | Single char |
| `"abc" = ['a', 'b', 'c']` | Succeeds | Standard case |
| `"abc" = "abc"` | Succeeds | Equality fast path (unchanged) |
| `"abc" = ['a', X, 'c']` | Succeeds, `X='b'` | Var binding |
| `"abc" = [1, 2, 3]` | Fails | Ints ≠ chars |
| `"abc" = ['ab', 'c']` | Fails | length 3 ≠ 2 |
| `"abc" = ['a', 'b']` | Fails | length mismatch |
| `"abc" = [X, Y]` | Fails | length mismatch |
| `"日本" = ['日', '本']` | Succeeds | Unicode |

### Build & Rebuild

The C extension must be recompiled after editing `_variables.c`:

```bash
cd clausal && pip install -e . && pytest tests/test_string_list_unification.py -v
```

---

## Phase 2: SegList Accepts Strings

**Goal:** `[*A, 'l', *B]` matches against `"hello"`. Multi-star list patterns work on strings.

### Changes

#### `terms.py` — `SegList.__unify__` (line 282)

Currently:
```python
def __unify__(self, other, trail):
    if isinstance(other, list):
        walked = self.__walk__()
        if isinstance(walked, list):
            return walked == other
        for _ in _seglist_unify_gen(walked, other, trail):
            return True
        return False
    if isinstance(other, SegList):
        return NotImplemented
    return NotImplemented
```

Change to accept `str`:
```python
def __unify__(self, other, trail):
    if isinstance(other, (list, str)):
        walked = self.__walk__()
        if isinstance(walked, list):
            if isinstance(other, str):
                # Compare ground SegList (now a list) against string-as-char-list
                return walked == list(other)
            return walked == other
        # Convert string to char list for the generator
        target = list(other) if isinstance(other, str) else other
        for _ in _seglist_unify_gen(walked, target, trail):
            return True
        return False
    if isinstance(other, SegList):
        return NotImplemented
    return NotImplemented
```

The key insight: `_seglist_unify_gen` already works on plain lists. We just need to convert the
string to a list of characters before passing it in. The generator at `terms.py:360` doesn't need
any changes — it already handles arbitrary list elements.

#### `terms.py` — `_seglist_unify_gen` (line 360)

No changes needed. The function already operates on any Python list. After `list("hello")` yields
`['h', 'e', 'l', 'l', 'o']`, the existing logic handles it.

#### `compiler.py` — `_body_multi_star_unify` (line 425)

Currently at line 437:
```python
if not isinstance(d, list):
    if isinstance(d, SegList):
```

Add string handling:
```python
if isinstance(d, str):
    d = list(d)  # Convert to char list for multi-star splitting
elif not isinstance(d, list):
    if isinstance(d, SegList):
```

This is the runtime path for body-position multi-star patterns. The compiled guard path
(`_compile_multi_star_guard`) generates code that calls `_body_multi_star_unify`, so this single
change covers both.

### Tests

Add to `tests/test_string_list_unification.py`:

```python
from clausal.terms import SegList, ConcreteSeg, VarSeg

class TestSegListStringUnification:
    """SegList patterns match against strings."""

    def test_seglist_head_tail_string(self):
        """[X, *T] matches 'hello' → X='h', T=['e','l','l','o']."""
        trail = Trail()
        X, T = Var("X"), Var("T")
        sl = SegList([ConcreteSeg([X]), VarSeg(T)])
        assert unify(sl, "hello", trail)
        assert deref(X) == "h"
        assert deref(T) == ['e', 'l', 'l', 'o']

    def test_seglist_multi_star_string(self):
        """[*A, 'l', *B] matches 'hello' (multiple solutions)."""
        trail = Trail()
        A, B = Var("A"), Var("B")
        sl = SegList([VarSeg(A), ConcreteSeg(['l']), VarSeg(B)])
        # Collect all solutions
        from clausal.terms import _seglist_unify_gen
        walked = sl.__walk__()
        target = list("hello")
        solutions = []
        for _ in _seglist_unify_gen(walked, target, trail):
            solutions.append((list(deref(A)), list(deref(B))))
            trail.undo(trail.mark())
        # 'hello' has 'l' at positions 2 and 3
        assert len(solutions) >= 2

    def test_seglist_prefix_suffix_string(self):
        """[*Prefix, ',', *Suffix] matches 'a,b'."""
        trail = Trail()
        P, S = Var("P"), Var("S")
        sl = SegList([VarSeg(P), ConcreteSeg([',']), VarSeg(S)])
        assert unify(sl, "a,b", trail)
        assert deref(P) == ['a']
        assert deref(S) == ['b']

    def test_seglist_empty_string(self):
        """[*A] matches '' → A=[]."""
        trail = Trail()
        A = Var("A")
        sl = SegList([VarSeg(A)])
        assert unify(sl, "", trail)
        assert deref(A) == []

    def test_seglist_full_concrete_string(self):
        """['h', 'i'] matches 'hi'."""
        trail = Trail()
        sl = SegList([ConcreteSeg(['h', 'i'])])
        assert unify(sl, "hi", trail)

    def test_seglist_full_concrete_string_fail(self):
        """['h', 'i'] does NOT match 'ho'."""
        trail = Trail()
        sl = SegList([ConcreteSeg(['h', 'i'])])
        assert not unify(sl, "ho", trail)
```

### Integration Tests (Clausal source level)

```clausal
# test_string_seglist.clausal
# skip
starts_with([*Prefix, *_], Prefix)
ends_with([*_, *Suffix], Suffix)
contains_char([*_, C, *_], C)

Test("starts_with string") <- starts_with("hello", ['h', 'e'])
Test("ends_with string") <- ends_with("hello", ['l', 'o'])
Test("contains comma") <- contains_char("a,b,c", ',')
```

---

## Phase 3: DCGs Accept Strings

**Goal:** `phrase(Grammar, "hello")` works directly. No `atom_chars` conversion needed.

### Changes

#### `dcg.py` — `_sequence__3` (line 67)

Currently at line 75:
```python
if is_var(lst_val) or not isinstance(lst_val, list):
    yield (parent, DONE)
    return
```

Change to:
```python
if is_var(lst_val) or not isinstance(lst_val, (list, str)):
    yield (parent, DONE)
    return
# Normalise string to char list for uniform processing
if isinstance(lst_val, str):
    lst_val = list(lst_val)
```

At line 80:
```python
if isinstance(s0_val, list):
```

Change to:
```python
if isinstance(s0_val, (list, str)):
```

At line 83 (the slicing logic):
```python
if len(s0_val) >= n and s0_val[:n] == lst_val:
```

This already works for strings because Python string slicing and comparison work the same way.
However, since we converted `lst_val` to a list above, we need to handle the comparison:

```python
if isinstance(s0_val, str):
    s0_chars = list(s0_val)
else:
    s0_chars = s0_val
if len(s0_chars) >= n and s0_chars[:n] == lst_val:
    mark = trail.mark()
    if unify(s, s0_chars[n:], trail):
        yield (parent, None)
    trail.undo(mark)
```

Wait — this changes the remainder `S` from a string to a list. That may be surprising. Better
approach: keep string identity where possible.

**Revised approach for `_sequence__3`:**

```python
@_trampoline_builtin("sequence", 3, fields=("list", "s0", "s"))
def _sequence__3(this_generator, parent, lst, s0, s, trail):
    lst_val = deref(lst)
    if is_var(lst_val) or not isinstance(lst_val, (list, str)):
        yield (parent, DONE)
        return
    # Normalise lst to a list for uniform element comparison
    lst_items = list(lst_val) if isinstance(lst_val, str) else lst_val
    s_val = deref(s)
    s0_val = deref(s0)
    if isinstance(s0_val, (list, str)):
        s0_items = list(s0_val) if isinstance(s0_val, str) else s0_val
        n = len(lst_items)
        if len(s0_items) >= n and s0_items[:n] == lst_items:
            # Remainder preserves input type when possible
            remainder = s0_items[n:]
            if isinstance(s0_val, str):
                remainder = "".join(remainder)
            mark = trail.mark()
            if unify(s, remainder, trail):
                yield (parent, None)
            trail.undo(mark)
    elif isinstance(s_val, (list, str)):
        s_items = list(s_val) if isinstance(s_val, str) else s_val
        expected = lst_items + s_items
        if isinstance(s0_val, str) or (isinstance(s_val, str) and isinstance(lst_val, str)):
            expected_str = "".join(expected) if all(isinstance(e, str) and len(e) == 1 for e in expected) else expected
            if isinstance(expected_str, str):
                mark = trail.mark()
                if unify(s0, expected_str, trail):
                    yield (parent, None)
                trail.undo(mark)
                yield (parent, DONE)
                return
        mark = trail.mark()
        if unify(s0, expected, trail):
            yield (parent, None)
        trail.undo(mark)
    else:
        from clausal.terms import SegList, ConcreteSeg, VarSeg
        sl = SegList([ConcreteSeg(lst_items), VarSeg(s_val)])
        mark = trail.mark()
        if unify(s0, sl, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)
```

This is getting complex. Simpler approach: just convert strings to char lists at the `phrase`
boundary, then everything works via existing list-based DCG infrastructure:

#### Simpler: Convert at `phrase/2` and `phrase/3` boundary

in_ `dcg.py` `_phrase__2` (line 13) and `_phrase__3` (line 41):

```python
# in_ _phrase__2, after line 16:
if isinstance(list_val, str):
    list_val = list(list_val)

# in_ _phrase__3, after line 44-45:
if isinstance(list_val, str):
    list_val = list(list_val)
```

This is the simplest correct approach. The DCG machinery operates on lists internally. Strings
are converted once at the entry point. The remainder (`Rest` in `phrase/3`) will be a list of
chars, not a string — this is acceptable and consistent.

For `sequence//1` at line 75, add string acceptance:

```python
if is_var(lst_val) or not isinstance(lst_val, (list, str)):
    yield (parent, DONE)
    return
if isinstance(lst_val, str):
    lst_val = list(lst_val)
```

And for the S0/S checks at lines 80 and 88:

```python
if isinstance(s0_val, (list, str)):
    if isinstance(s0_val, str):
        s0_val = list(s0_val)
    # ... existing logic with s0_val as list ...

elif isinstance(s_val, (list, str)):
    if isinstance(s_val, str):
        s_val = list(s_val)
    # ... existing logic with s_val as list ...
```

### Tests

```python
"""Tests for Phase 3: DCGs accept strings."""

class TestDCGStrings:
    def test_phrase_string_input(self):
        """phrase(Grammar, 'hello') works without atom_chars."""
        # Load a .clausal module with a DCG rule that matches "hello"
        # greeting >> (["h", "e", "l", "l", "o"])
        # phrase(greeting, "hello") should succeed

    def test_phrase3_string_input(self):
        """phrase(Grammar, 'hello world', Rest) parses prefix."""
        # greeting >> (["h", "e", "l", "l", "o"])
        # phrase(greeting, "hello world", Rest) → Rest = [' ', 'w', 'o', 'r', 'l', 'd']

    def test_sequence_string(self):
        """sequence(['a', 'b']) matches string 'abc' with remainder ['c']."""

    def test_dcg_character_grammar(self):
        """A character-level DCG parses a string directly."""
        # digit >> ([D], {char_type(D, digit)})
        # digits >> (digit, digits)
        # digits >> (digit)
        # phrase(digits, "123") should succeed

    def test_dcg_mixed_input(self):
        """DCG rules still work with list input (no regression)."""
```

### Integration Tests (Clausal source level)

```clausal
# test_dcg_strings.clausal
digit >> ([D], {char_type(D, digit)})
digits >> (digit)
digits >> (digit, digits)

Test("parse digits from string") <- phrase(digits, "123")
Test("parse single digit") <- phrase(digits, "5")
Test("phrase3 remainder") <- (
    phrase(digits, "12ab", Rest),
    Rest == ['a', 'b']
)
```

---

## Phase 4: Polymorphic List Builtins

**Goal:** List predicates accept strings transparently. This is the largest phase.

### Approach

We add a helper function `_as_sequence(val)` that returns a uniform representation:

```python
def _as_sequence(val):
    """Normalise a ground sequence value for list builtins.

    Returns (items, is_string) where items is a list and is_string indicates
    the original was a string (so we can reconstruct a string result).
    Returns None if val is not a sequence type.
    """
    if isinstance(val, list):
        return val, False
    if isinstance(val, str):
        return list(val), True
    return None
```

And a result-reconstruction helper:

```python
def _seq_result(items, was_string):
    """Reconstruct a string if the input was a string and all items are single chars."""
    if was_string and all(isinstance(c, str) and len(c) == 1 for c in items):
        return "".join(items)
    return items
```

These go in `lists.py` (or a shared `_helpers.py` module).

### Builtins to Update (in `lists.py`)

Each builtin currently checks `isinstance(val, list)`. We change these to use `_as_sequence`.

#### Priority 1: Most impactful (used constantly)

| Builtin | Line | Change |
|---------|------|--------|
| `in_/2` | 21 | Accept string; yield single chars |
| `append/3` | 58 | Accept strings; return string when all inputs are strings |
| `length/2` | 87 | Accept string; return `len()` |
| `reverse/2` | 117 | Accept string; return reversed string |
| `get_item/3` | 130 | Accept string; return char |
| `last/2` | 105 | Accept string; return last char |

#### Priority 2: Useful for string processing

| Builtin | Line | Change |
|---------|------|--------|
| `take/3` | 352 | Accept string; return substring |
| `drop/3` | 365 | Accept string; return substring |
| `split_at/4` | 378 | Accept string; return two substrings |
| `flatten/2` | 155 | Accept string (flatten is identity for strings) |

#### Priority 3: Lower priority (set/sort operations)

| Builtin | Line | Change |
|---------|------|--------|
| `msort/2` | 173 | Accept string; return sorted chars |
| `sort/2` | 189 | Accept string; return sorted unique chars |
| `permutation/2` | 210 | Accept string; yield char permutations |
| `select/3` | 223 | Accept string; select char |
| `subtract/3` | 238 | Accept strings |
| `intersection/3` | 252 | Accept strings |
| `union/3` | 266 | Accept strings |
| `list_to_set/2` | 282 | Accept string; return unique chars |
| `sum_list/2` | 298 | Skip (chars aren't numbers) |
| `max_list/2` | 315 | Accept string (max char by codepoint) |
| `min_list/2` | 332 | Accept string (min char by codepoint) |
| `zip_/3` | 391 | Accept strings |
| `split_with/3` | 426 | Accept string |
| `numlist/2,3` | 454 | Skip (generates integer lists) |
| `same_length/2` | 493 | Accept strings |
| `transpose/2` | 512 | Accept strings |

### Example: `append/3` Polymorphic Implementation

```python
@_trampoline_builtin("append", 3)
def _append__3(this_generator, parent, l1, l2, l3, trail):
    l1_val = deref(l1)
    l2_val = deref(l2)
    l3_val = deref(l3)

    l1_seq = _as_sequence(l1_val)
    l2_seq = _as_sequence(l2_val)
    l3_seq = _as_sequence(l3_val)

    if l1_seq and l2_seq:
        # Both known: concatenate
        items1, s1 = l1_seq
        items2, s2 = l2_seq
        result = items1 + items2
        result = _seq_result(result, s1 and s2)
        mark = trail.mark()
        if unify(l3, result, trail):
            yield (parent, None)
        trail.undo(mark)
    elif l1_seq and l3_seq:
        # L1 and L3 known: compute L2
        items1, s1 = l1_seq
        items3, s3 = l3_seq
        n = len(items1)
        if len(items3) >= n and items3[:n] == items1:
            remainder = items3[n:]
            result = _seq_result(remainder, s3)
            mark = trail.mark()
            if unify(l2, result, trail):
                yield (parent, None)
            trail.undo(mark)
    elif l3_seq:
        # Only L3 known: enumerate all splits
        items3, s3 = l3_seq
        for i in range(len(items3) + 1):
            prefix = _seq_result(items3[:i], s3)
            suffix = _seq_result(items3[i:], s3)
            mark = trail.mark()
            if unify(l1, prefix, trail) and unify(l2, suffix, trail):
                yield (parent, None)
            trail.undo(mark)
    yield (parent, DONE)
```

### Example: `in_/2` Polymorphic Implementation

```python
@_trampoline_builtin("in_", 2)
def _in__2(this_generator, parent, elem, lst, trail):
    lst_val = deref(lst)
    seq = _as_sequence(lst_val)
    if seq is None:
        yield (parent, DONE)
        return
    items, _ = seq
    for item in items:
        mark = trail.mark()
        if unify(elem, item, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)
```

### New Predicate: `is_chars/1`

Add to `type_checks.py`:

```python
@_builtin("is_chars", 1)
def _is_chars__1(x, trail, k):
    """is_chars(X) — succeeds if X is a list or a string (i.e. a character sequence)."""
    val = deref(x)
    if isinstance(val, (list, str)):
        yield None
```

### `is_list/1` Decision

**`is_list/1` should NOT succeed for strings.** It tests the exact type — "is this a Python list?"
This preserves backward compatibility and gives users a way to distinguish types when needed.
`is_chars/1` is the union predicate.

The existing test `test_is_list_string_fails` (`test_list_edge_cases.py:359`) stays as-is.

### Tests

```python
"""Tests for Phase 4: polymorphic list builtins."""

class TestPolymorphicAppend:
    def test_append_two_strings(self):
        """append('hel', 'lo', X) → X = 'hello'."""

    def test_append_string_list(self):
        """append('ab', [1, 2], X) → X = ['a', 'b', 1, 2]."""

    def test_append_split_string(self):
        """append(X, Y, 'hello') enumerates all splits as strings."""

    def test_append_prefix_match(self):
        """append('hel', X, 'hello') → X = 'lo'."""

    def test_append_suffix_match(self):
        """append(X, 'lo', 'hello') → X = 'hel'."""

class TestPolymorphicIn:
    def test_member_string(self):
        """in_(X, 'hello') yields 'h', 'e', 'l', 'l', 'o'."""

    def test_member_check_string(self):
        """in_('l', 'hello') succeeds."""

    def test_member_nonchar_string(self):
        """in_(1, 'hello') fails."""

class TestPolymorphicLength:
    def test_length_string(self):
        """length('hello', N) → N = 5."""

class TestPolymorphicReverse:
    def test_reverse_string(self):
        """reverse('hello', X) → X = 'olleh'."""

class TestPolymorphicGetItem:
    def test_getitem_string(self):
        """get_item('hello', 1, X) → X = 'e'."""

class TestPolymorphicTakeDrop:
    def test_take_string(self):
        """take(3, 'hello', X) → X = 'hel'."""

    def test_drop_string(self):
        """drop(3, 'hello', X) → X = 'lo'."""

    def test_split_at_string(self):
        """split_at(3, 'hello', X, Y) → X = 'hel', Y = 'lo'."""

class TestIsChars:
    def test_is_chars_string(self):
        """is_chars('hello') succeeds."""

    def test_is_chars_list(self):
        """is_chars([1, 2]) succeeds."""

    def test_is_chars_int(self):
        """is_chars(42) fails."""

    def test_is_list_string_still_fails(self):
        """is_list('hello') still fails (exact type test)."""
```

---

## Phase 5: Higher-Order Predicates Accept Strings

**Goal:** `maplist`, `foldl`, `include`, `exclude`, `findall` etc. work on strings.

### Changes

Locate higher-order predicates and update their input validation to accept strings.
The key predicates are likely in a `higher_order.py` or `meta.py` builtins file.

The pattern is the same as Phase 4: use `_as_sequence` for input, `_seq_result` for output.

Higher-order predicates that call a goal on each element:
- `maplist/2,3,4` — apply goal to each element
- `include/3` — filter elements by goal
- `exclude/3` — exclude elements by goal
- `foldl/4,5` — fold over elements

These should accept strings and (where the output is a sequence of single chars) produce strings.

### Tests

```python
class TestHigherOrderStrings:
    def test_maplist_string(self):
        """maplist(upcase_atom, 'abc', X) — but chars are already single, so..."""
        # Actually maplist operates on list elements. For strings,
        # each element is a char. So maplist(SomeCharPred, "abc") should work.

    def test_filter_string(self):
        """include(IsDigitChar, 'a1b2c3', X) → X = '123' or ['1','2','3']."""

    def test_foldleft_string(self):
        """foldl(Concat, '', 'abc', X) → X = 'abc' (fold chars)."""
```

---

## Phase 6: Deprecate String-Specific Predicates

**Goal:** Document that list predicates are the preferred interface for string processing. Keep
string-specific predicates for backward compatibility and ISO compliance.

### Changes

- `atom_concat/3` → thin wrapper or alias for polymorphic `append/3`
- `atom_length/2` → thin wrapper or alias for `length/2`
- `atom_chars/2` → still useful for explicit type conversion (string ↔ list)
- `atom_codes/2` → keep (code point conversion is distinct from char-list conversion)
- `sub_atom/5` → keep for ISO compatibility, but document that `[*A, Sub, *B]` patterns are preferred
- `char_type/2`, `char_code/2`, `upcase_atom/2`, `downcase_atom/2` → keep (character-specific operations)

### Documentation Updates

- `docs/lists.md` — add section on strings as character lists
- `docs/builtins.md` — update to show list predicates accepting strings
- `docs/dcg.md` — show `phrase(Grammar, "string")` examples
- `docs/type_checking.md` — document `is_chars/1`
- Create `docs/strings_as_lists.md` — dedicated explanation (see companion doc)

---

## Phase 7 (Optional): SegString Optimisation

**Goal:** Avoid materialising char lists for large strings during SegList matching.

This is a performance optimisation. Skip unless profiling shows the `list("large_string")`
conversion in Phase 2 is a bottleneck.

### Design

```python
class SegString:
    """A SegList-like term backed by string segments instead of list segments.

    SegString([ConcreteSeg("hel"), VarSeg(X), ConcreteSeg("ld")])

    when ground, __walk__ returns a plain str (not a list).
    VarSegs bind to substrings (str), not char lists.
    """
```

This would give ergonomic substring binding:
- `SegString([VarSeg(A), ConcreteSeg(","), VarSeg(B)])` matching `"hello,world"`
  → `A = "hello"`, `B = "world"` (strings, not char lists)

### Trade-offs

- **Pro:** More ergonomic for string-heavy code
- **Pro:** Avoids O(n) char-list materialisation for large strings
- **Con:** New type to maintain alongside SegList
- **Con:** Needs compiler support for string-specific patterns
- **Con:** Interactions with SegList (SegString ↔ SegList unification)

### Implementation sketch

- Add `SegString` to `terms.py` with `__walk__`, `__unify__`, `__occurs_check__`
- `__walk__` returns plain `str` when ground (join segments)
- `__unify__` against `str` uses string slicing (fast); against `list` converts
- Compiler detects string-context patterns and emits `SegString` instead of `SegList`

**Recommendation:** Defer this. Phases 1–4 give 90% of the benefit. SegString is a
nice-to-have optimisation for a future release.

---

## Implementation Order (Actual)

```
Phase 1: C-level unification ✅ (44 tests)
   ↓
Phase 2: SegList accepts strings ✅ (16 tests)
   ↓
Phase 3: DCGs accept strings ✅ (10 tests)
   ↓
Phase 4: Polymorphic builtins ✅ (50 tests)
   ↓
Phase 5: Higher-order predicates ✅ (16 tests)
   ↓
Phase 5b: Compiler head patterns ✅ (20 tests)  ← discovered post-hoc
   ↓
Phase 6: Documentation & deprecation ✅
   ↓
Phase 7: SegString optimisation ✅ (41 tests)
```

Total: 197 new tests, 7940 passing, 0 regressions.

---

## Files Modified (Actual)

| File | Phase | Nature of change |
|------|-------|-----------------|
| `clausal/logic/variables/_variables.c` | 1 | Add str↔list unification in `do_unify` |
| `clausal/terms.py` | 2 | `SegList.__unify__` accepts `str` |
| `clausal/logic/compiler.py` | 2, 5b | `_body_multi_star_unify`, `_head_list_unify_input`, dispatch guards |
| `clausal/logic/builtins/dcg.py` | 3 | `phrase/2,3` and `sequence//1` accept `str` |
| `clausal/logic/builtins/lists.py` | 4 | All 27 list builtins accept `str` via `_as_items`/`_seq_result` |
| `clausal/logic/builtins/type_checks.py` | 4 | Add `is_chars/1` |
| `clausal/logic/builtins/higher_order.py` | 5 | All 16 higher-order predicates accept `str` |
| `tests/test_string_list_unification.py` | 1, 2 | 60 tests: C unification + SegList |
| `tests/test_dcg.py` | 3 | 10 tests: DCG string input |
| `tests/test_string_list_builtins.py` | 4 | 50 tests: polymorphic builtins |
| `tests/test_string_higher_order.py` | 5 | 16 tests: higher-order on strings |
| `tests/test_string_head_patterns.py` | 5b | 20 tests: compiled head patterns |
| `tests/test_seglist_core.py` | 2 | Updated: string is no longer "non-list" |
| `tests/test_deep_indexing.py` | 5b | Updated: isinstance check recognises (list, str) |
| `tests/test_list_edge_cases.py` | 5b | Updated: user-defined is_list matches strings |
| `clausal/terms.py` | 7 | Add `SegString` class; `SegList.__unify__` passes strings directly; `__walk__` handles str-bound VarSegs |
| `clausal/logic/compiler.py` | 7 | `_body_multi_star_unify` preserves string type; `_build_star_list`/`_build_multi_star_list` string support |
| `tests/test_segstring.py` | 7 | 41 tests: SegString core, string-preserving matching, body multi-star, build helpers |
| `tests/test_string_list_unification.py` | 7 | Updated: SegList string tests expect substring bindings (not char lists) |

---

## Risks and Mitigations

### Risk: Breaking existing string equality semantics

**Mitigation:** String-vs-string unification is unchanged — the new str↔list branch only fires
when one side is `str` and the other is `list`. The `PyUnicode_Check(t1) && PyList_Check(t2)`
guard is mutually exclusive with the existing `PyObject_RichCompareBool` path.

### Risk: Performance regression for string-heavy code

**Mitigation:** The hot path (string-vs-string) is unchanged. The new branch only fires for
cross-type unification, which doesn't happen today at all. List builtins doing `list(s)` is O(n)
but so is any list operation — and Python's `list(str)` is a fast C-level operation.

### Risk: Confusing return types from polymorphic builtins

**Mitigation:** Clear rule — string in, string out (when possible). Document this in the
`_seq_result` helper and in user-facing docs.

### Risk: SegList VarSeg binding type (list vs string)

**Mitigation:** Phase 2 binds VarSegs to lists (not substrings). This is consistent with SegList's
existing semantics. Phase 7's SegString can provide substring binding later as an opt-in.

### Risk: DCG remainder type after parsing a string

**Mitigation:** `phrase/3` converts the string to a char list at entry. The remainder is a list.
This is documented and consistent — DCGs always work on lists internally.

### Risk: ISO compatibility

**Mitigation:** `atom_chars/2`, `atom_concat/3`, `sub_atom/5` etc. are preserved as-is. They
continue to work exactly as before. The new polymorphic list predicates are *additional*
capabilities, not replacements for ISO predicates.

---

## Acceptance Criteria

Phase 1 — DONE (commit acea65b, 44 tests):
- [x] `unify("abc", ['a', 'b', 'c'], trail)` succeeds
- [x] `unify("abc", [X, Y, Z], trail)` binds chars
- [x] `unify("abc", "abc", trail)` still works (fast path)
- [x] `unify("abc", [1, 2, 3], trail)` fails
- [x] All existing tests pass (no regression)

Phase 2 — DONE (commit cf3b0d5, 16 tests):
- [x] `SegList([VarSeg(A), ConcreteSeg(['l']), VarSeg(B)])` unifies with `"hello"`
- [x] `_body_multi_star_unify` handles string targets
- [x] Clause-level multi-star patterns match strings

Phase 3 — DONE (commit 09114a0, 10 tests):
- [x] `phrase(Grammar, "hello")` works
- [x] `phrase(Grammar, "hello world", Rest)` works
- [x] DCGs with `sequence//1` accept string inputs

Phase 4 — DONE (commit 5dd921a, 50 tests):
- [x] `in_(X, "hello")` yields chars
- [x] `append("hel", "lo", X)` yields `"hello"`
- [x] `length("hello", X)` yields 5
- [x] `reverse("hello", X)` yields `"olleh"`
- [x] `is_chars/1` succeeds for both lists and strings
- [x] `is_list("hello")` still fails (builtin exact type check)
- [x] User-defined `is_list([*_])` now succeeds for strings (correct)

Phase 5 — DONE (commit f9a6f01, 16 tests):
- [x] `maplist(Goal, "abc")` works
- [x] `include(Goal, "abc", Result)` works
- [x] All 16 higher-order predicates accept strings

Phase 5b — DONE (commit f878fda, 20 tests):
- [x] `_head_list_unify_input` accepts `(list, str)` — runtime destructuring
- [x] `_build_list_dispatch_guard` emits `isinstance(_, (list, str))` — AST dispatch
- [x] `_compile_multi_star_guard` emits `isinstance(_, (list, str))` — multi-star AST
- [x] `HeadTail("abc", H, T)` succeeds with `H='a', T='bc'`
- [x] Recursive predicates (length, last) work on strings
- [x] String type preserved through recursion (tail stays `str`)

Phase 6 — DONE:
- [x] `docs/strings_as_lists.md` — reviewed for accuracy post-implementation, no changes needed
- [x] `docs/lists.md` — added tip admonition and see-also link for string acceptance
- [x] `docs/dcg.md` — added "Strings as input" section with `phrase(grammar, "string")` examples
- [x] `docs/type_checking.md` — documented `is_chars/1` with comparison table
- [x] `docs/builtins.md` — added string acceptance tip to List Predicates, preference note to Character/String
- [x] `chars.py` predicates — updated module docstring and added preference notes to `atom_concat/3` and `atom_length/2`

Phase 7 — DONE (41 tests):
- [x] `SegString` type for substring-preserving pattern matching
- [x] VarSegs bind to substrings when matching strings (SegList passes strings directly)
- [x] `_body_multi_star_unify` preserves string type (no char-list conversion)
- [x] `_build_star_list` / `_build_multi_star_list` return strings when inputs are string-compatible
- [x] `SegList.__walk__` handles VarSegs bound to strings
- [x] SegList/compiler path asymmetry eliminated — all paths bind star vars to substrings


---

## Phase 5b: Compiler Head Pattern Guards (Post-Hoc Discovery)

### Problem

Phases 1–5 made the runtime (builtins, DCGs, unification) accept strings as character
sequences, but the **compiler** generates code for clause head patterns that only accepted
`list`. A user-defined predicate like:

```clausal
HeadTail([H, *T], H, T)
```

would silently fail when called with `HeadTail("hello", H, T)` because the compiled guard
rejected the string before `_head_list_unify_input` was ever called.

### Root Cause

Three sites in the compiler emit `isinstance(_, list)` checks that exclude strings:

| Site | Function | What it does |
|------|----------|-------------|
| `compiler.py:4715` | `_build_list_dispatch_guard()` | Structural dispatch: routes list args to nil/cons branches |
| `compiler.py:6557` | `_compile_multi_star_guard()` | Multi-star pattern guard: `[*A, x, *B]` |
| `compiler.py:209` | `_head_list_unify_input()` | Runtime function that destructures `[H, *T]` patterns |

### Why It Wasn't Caught Earlier

The runtime builtins (append, in_, etc.) call their own Python functions which we already
updated. The compiler path is separate — it generates Python AST/bytecode that calls
`_head_list_unify_input` guarded by `isinstance` checks. Tests for Phases 1–5 exercised
builtins but not user-defined predicates with list heads.

### Fix

1. **`_head_list_unify_input`** (line 209): Changed `isinstance(d, list)` to
   `isinstance(d, (list, str))`. The function's indexing (`d[i]`) and slicing
   (`d[n_before:star_end]`) already work identically on strings.

2. **`_build_list_dispatch_guard`** (line 4715): Changed AST generation from
   `_name("list")` to `ast.Tuple(elts=[_name("list"), _name("str")])`.

3. **`_compile_multi_star_guard`** (line 6557): Same AST change.

### Key Insight: String Type Preservation

when `_head_list_unify_input` destructures a string, Python slicing preserves the `str` type:
- `"hello"[0]` → `"h"` (single-char string)
- `"hello"[1:]` → `"ello"` (string, not list)

This means `[H, *T]` on `"hello"` gives `H='h'`, `T='ello'`. The tail `T` remains a string,
so recursive predicates like:

```clausal
length([], 0)
length([_, *T], N) <- (length(T, N1), N := N1 + 1)
```

work naturally on strings. Each recursive call gets a shorter string — `"hello"` → `"ello"` →
`"llo"` → ... → `""` — and `""` is falsy in Python (like `[]`), so the nil base case matches.

This is actually **better** than Phase 2's SegList approach, which converts strings to char
lists. The compiler path preserves string identity throughout recursion with zero conversion
overhead.

### Consistency Notes

| Operation | Input | Result type |
|-----------|-------|-------------|
| `[H, *T]` head pattern | `"hello"` | `H='h'` (str), `T='ello'` (str) |
| `[H, *T]` head pattern | `['h','e','l','l','o']` | `H='h'` (str), `T=['e','l','l','o']` (list) |
| `SegList([VarSeg(A)])` unify | `"hello"` | `A=['h','e','l','l','o']` (list) |
| `append(X, Y, "hello")` | `"hello"` | `X='he'` (str), `Y='llo'` (str) |

The SegList path (Phase 2) converts to char list; the compiler path (this phase) preserves
strings. This is an asymmetry. The SegList path is used for body-position patterns and
runtime unification; the compiler path is used for head patterns. Both are correct; the
compiler path is more efficient for strings.

### Existing Test Updates

- `test_deep_indexing.py`: Updated `_has_isinstance_check` and `_count_isinstance_checks`
  to recognise `isinstance(_, (list, str))` tuple form alongside `isinstance(_, list)`.
- `test_list_edge_cases.py`: Changed `test_is_list_string_fails` to
  `test_is_list_string_succeeds` — user-defined `is_list([*_])` now matches strings
  (correct: strings match list patterns).
