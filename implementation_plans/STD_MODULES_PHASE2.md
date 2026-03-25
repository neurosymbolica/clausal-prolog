# Std Modules Phase 2 — Character/String Utilities & Clause Inspection

**Status: COMPLETE**

**Depends on:** V2-15 (I/O builtins), Predicate-as-Class refactor (PredicateMeta)

**Goal:** Add ISO-standard character and string predicates (`CharType/2`,
`CharCode/2`, `AtomConcat/3`, `SubAtom/5`, etc.) and clause inspection
predicates (`Listing/1`, `PortrayClause/1`). These fill the main remaining
gap in Clausal's standard library: logic-aware string manipulation with
backtracking, and runtime predicate introspection.

**Non-goal:** Formatted output (`format/2,3`). Prolog's `~a`, `~w`, `~d`
format directives exist because Prolog lacks string formatting. Clausal has
Python's f-strings (already integrated in V2-15) and `str.format()` — there
is no reason to reimplement a worse version under a Prolog API.

---

## Design Principles

1. **Logic-aware string operations.** The point of these predicates (vs `++()`)
   is that they participate in unification and backtracking. `AtomConcat(A, B,
   "hello")` with A and B unbound enumerates all 6 splits. `CharType(C, digit)`
   enumerates '0'..'9'. Pure Python string methods can't do this — they're
   functions, not relations.

2. **All builtins, no compiler special forms.** None of these predicates need
   inline compilation. Standard `@_builtin` registration via the registry.

3. **Reuse existing infrastructure.** `term_str()` for term formatting,
   `is_term_instance()`/`term_field_names()` for clause head reconstruction,
   `_format_term_for_io()` for I/O output.

4. **Multi-arity registration uses existing `_merge` mechanism.** The registry
   already handles multiple arities for the same functor name (Match/2,3,
   Search/2,3 in regex). Register each arity separately with `@_builtin`.

---

## 2a — CharType/2 and CharCode/2

**Files:** `clausal/logic/builtins/chars.py` (new), `tests/test_chars.py` (new)

### Semantics

`CharType(Char, Type)` — character classification as a *relation*:

- Both bound → test: succeeds iff Char has the given Type.
- Char bound, Type unbound → enumerate all matching types.
- Type bound, Char unbound → enumerate all ASCII chars of that type.

`CharCode(Char, Code)` — bidirectional char ↔ integer code point:

- Char bound → unify Code with `ord(Char)`.
- Code bound → unify Char with `chr(Code)`.
- Both bound → test equality.
- Both unbound → `instantiation_error`.

### Character Types

| Type | Python test | Description |
|---|---|---|
| `alpha` | `str.isalpha()` | Alphabetic |
| `digit` | `str.isdigit()` | Decimal digit (0-9) |
| `alnum` | `str.isalnum()` | Alphanumeric |
| `space` | `str.isspace()` | Whitespace |
| `upper` | `str.isupper()` | Uppercase letter |
| `lower` | `str.islower()` | Lowercase letter |
| `ascii` | `ord(c) < 128` | ASCII character |
| `punct` | `not alnum, not space, printable` | Punctuation |
| `print` | `str.isprintable()` | Printable character |
| `control` | `ord(c) < 32 or ord(c) == 127` | Control character |

### Implementation

```python
_CHAR_TYPES = {
    "alpha": str.isalpha,
    "digit": str.isdigit,
    "alnum": str.isalnum,
    "space": str.isspace,
    "upper": str.isupper,
    "lower": str.islower,
    "ascii": lambda c: ord(c) < 128,
    "punct": lambda c: not c.isalnum() and not c.isspace() and c.isprintable(),
    "print": str.isprintable,
    "control": lambda c: ord(c) < 32 or ord(c) == 127,
}
```

Design question: should `CharType(C, Type)` with *both* unbound enumerate all
(char, type) pairs? In standard Prolog `char_type/2`, both-unbound is an
`instantiation_error`. But since there are only ~1280 valid (char, type)
pairs in ASCII (128 chars × ~10 types, with many non-matches), enumeration
is feasible. **Decision: require at least one argument bound.** Both unbound →
`instantiation_error`. This matches ISO semantics and avoids surprising
quadratic enumeration.

Edge case: what counts as a "char" in Clausal? Python strings are Unicode, but
a single character is a length-1 string. Unlike Prolog, Clausal has no distinct
`atom` vs `char` type — a char is just a length-1 `str`. The predicate must
validate `isinstance(c, str) and len(c) == 1`.

### Sub-steps for 2a

1. **Create `clausal/logic/builtins/chars.py`** with `_CHAR_TYPES` dict and
   `CharType/2` builtin implementing three modes (test, enum types, enum chars).

2. **Add `CharCode/2`** — bidirectional `ord`/`chr` conversion. Error if both
   unbound. Error if char is not length-1 string. Error if code is negative.

3. **Register** in `clausal/logic/builtins/__init__.py` by importing the module.

4. **Tests** in `tests/test_chars.py` (~15 tests):
   - `CharType('a', "alpha")` → succeeds
   - `CharType('1', "digit")` → succeeds
   - `CharType('a', "digit")` → fails
   - `CharType('A', "upper")` → succeeds
   - `CharType(' ', "space")` → succeeds
   - `CharType('!', "punct")` → succeeds
   - `CharType(C, "digit")` → enumerates '0'..'9' (10 solutions)
   - `CharType('a', TYPE)` → enumerates "alpha", "alnum", "lower", "ascii", "print" (5 solutions)
   - `CharType(C, T)` both unbound → error
   - `CharType("ab", "alpha")` → fails (not length-1)
   - `CharCode('A', N)` → N = 65
   - `CharCode(C, 65)` → C = 'A'
   - `CharCode('A', 65)` → succeeds (both bound, match)
   - `CharCode('A', 66)` → fails (both bound, mismatch)
   - `CharCode(C, N)` both unbound → error

---

## 2b — Case Conversion Predicates

**Files:** `clausal/logic/builtins/chars.py`, `tests/test_chars.py`

### Semantics

| Predicate | Description |
|---|---|
| `UpcaseAtom(Atom, Upper)` | Unify Upper with uppercase version of Atom |
| `DowncaseAtom(Atom, Lower)` | Unify Lower with lowercase version of Atom |

These are unidirectional — the first argument must be bound to a string.
If the first argument is unbound, throw `instantiation_error`. These match
SWI-Prolog's `upcase_atom/2` and `downcase_atom/2`.

### Implementation

Straightforward wrappers around `str.upper()` and `str.lower()`:

```python
@_builtin("UpcaseAtom", 2)
def _upcase_atom__2(atom, upper, trail, k):
    a = deref(atom)
    if is_var(a):
        raise LogicException(instantiation_error("upcase_atom/2"))
    if not isinstance(a, str):
        raise LogicException(type_error("atom", a, "upcase_atom/2"))
    mark = trail.mark()
    if unify(upper, a.upper(), trail):
        yield None
    trail.undo(mark)
```

### Sub-steps for 2b

1. **Add `UpcaseAtom/2` and `DowncaseAtom/2`** to `chars.py`.
2. **Tests** (~6 tests):
   - `UpcaseAtom("hello", S)` → S = "HELLO"
   - `UpcaseAtom("Hello World", S)` → S = "HELLO WORLD"
   - `DowncaseAtom("HELLO", S)` → S = "hello"
   - `UpcaseAtom("", S)` → S = ""
   - `UpcaseAtom(X, S)` with X unbound → instantiation_error
   - `UpcaseAtom(42, S)` → type_error

---

## 2c — AtomLength/2, AtomChars/2, AtomCodes/2

**Files:** `clausal/logic/builtins/chars.py`, `tests/test_chars.py`

### Semantics

`AtomLength(Atom, Length)` — unify Length with the length of Atom. First
argument must be bound.

`AtomChars(Atom, Chars)` — bidirectional conversion between a string and a
list of single-character strings:
- Atom bound → unify Chars with `list(Atom)`.
- Chars bound → unify Atom with `"".join(Chars)`.
- Both bound → test equality.

`AtomCodes(Atom, Codes)` — bidirectional conversion between a string and a
list of integer character codes:
- Atom bound → unify Codes with `[ord(c) for c in Atom]`.
- Codes bound → unify Atom with `"".join(chr(c) for c in Codes)`.

### Implementation

The bidirectional predicates need mode detection (which argument is bound?).
This is the same pattern used extensively in existing builtins (e.g.,
`Functor/3`, `Unpack/2`, `AtomConcat/3` in Phase 2d).

Design question for `AtomChars/2`: Clausal lists are native Python lists
(not cons cells). So `AtomChars("hi", L)` should unify L with `['h', 'i']`
(a Python list). This is correct — Clausal already uses Python lists throughout.

Design question for `AtomCodes/2`: same pattern — produce `[104, 105]` for
`"hi"`. The reverse direction must validate all elements are integers.

### Sub-steps for 2c

1. **Add `AtomLength/2`** — simple wrapper, Atom must be bound.
2. **Add `AtomChars/2`** — bidirectional with mode detection.
3. **Add `AtomCodes/2`** — bidirectional with mode detection.
4. **Tests** (~12 tests):
   - `AtomLength("hello", N)` → N = 5
   - `AtomLength("", N)` → N = 0
   - `AtomLength("hello", 5)` → succeeds
   - `AtomLength("hello", 3)` → fails
   - `AtomLength(X, N)` → instantiation_error
   - `AtomChars("hi", L)` → L = ['h', 'i']
   - `AtomChars(A, ['h', 'i'])` → A = "hi"
   - `AtomChars("hi", ['h', 'i'])` → succeeds (both bound)
   - `AtomChars("", L)` → L = []
   - `AtomCodes("hi", L)` → L = [104, 105]
   - `AtomCodes(A, [104, 105])` → A = "hi"
   - `AtomCodes("hi", [104, 105])` → succeeds

---

## 2d — AtomConcat/3

**Files:** `clausal/logic/builtins/chars.py`, `tests/test_chars.py`

### Semantics

`AtomConcat(A, B, C)` — string concatenation as a *relation*:

- A and B bound → unify C with `A + B` (forward).
- C bound, A and/or B unbound → enumerate all splits (reverse).
- All three bound → test `A + B == C`.

This is one of the more interesting predicates because the reverse mode
produces multiple solutions via backtracking. `AtomConcat(A, B, "abc")` has
4 solutions: `("","abc")`, `("a","bc")`, `("ab","c")`, `("abc","")`.

### Implementation

The forward direction is trivial. The reverse direction is the interesting
part. When C is bound and at least one of A, B is unbound:

```python
# C is bound (string of length n)
# Enumerate all splits: for i in range(len(C) + 1):
#   A = C[:i], B = C[i:]
for i in range(len(vc) + 1):
    mark = trail.mark()
    if unify(a, vc[:i], trail) and unify(b, vc[i:], trail):
        yield None
    trail.undo(mark)
```

Edge case: what if A is bound but B is unbound, and C is bound? We should
check that C starts with A, and if so, unify B with the remainder. This is
more efficient than enumerating all splits. But the naive enumeration is
correct — the `unify(a, vc[:i], trail)` call will fail for all splits where
`vc[:i] != A`, leaving only the correct one. For short strings this is fine.
For very long strings, the optimized check is better.

**Decision: implement the optimized path** when exactly one of A, B is bound
(string prefix/suffix check + remainder unification). Fall back to enumeration
when both are unbound.

```python
@_builtin("AtomConcat", 3)
def _atom_concat__3(a, b, c, trail, k):
    va, vb, vc = deref(a), deref(b), deref(c)
    a_bound = not is_var(va) and isinstance(va, str)
    b_bound = not is_var(vb) and isinstance(vb, str)
    c_bound = not is_var(vc) and isinstance(vc, str)

    if a_bound and b_bound:
        # Forward: A + B → C
        mark = trail.mark()
        if unify(c, va + vb, trail):
            yield None
        trail.undo(mark)
    elif c_bound and a_bound:
        # C and A bound: check prefix, unify remainder
        if vc.startswith(va):
            mark = trail.mark()
            if unify(b, vc[len(va):], trail):
                yield None
            trail.undo(mark)
    elif c_bound and b_bound:
        # C and B bound: check suffix, unify prefix
        if vc.endswith(vb):
            mark = trail.mark()
            if unify(a, vc[:len(vc) - len(vb)], trail):
                yield None
            trail.undo(mark)
    elif c_bound:
        # C bound, A and B unbound: enumerate all splits
        for i in range(len(vc) + 1):
            mark = trail.mark()
            if unify(a, vc[:i], trail) and unify(b, vc[i:], trail):
                yield None
            trail.undo(mark)
    else:
        # C unbound and not enough info to compute it
        raise LogicException(instantiation_error("atom_concat/3"))
```

### Sub-steps for 2d

1. **Add `AtomConcat/3`** with optimized mode dispatch.
2. **Tests** (~10 tests):
   - `AtomConcat("hel", "lo", S)` → S = "hello"
   - `AtomConcat("", "hello", S)` → S = "hello"
   - `AtomConcat("hello", "", S)` → S = "hello"
   - `AtomConcat(A, B, "abc")` → 4 solutions: ("","abc"), ("a","bc"), ("ab","c"), ("abc","")
   - `AtomConcat("a", B, "abc")` → B = "bc"
   - `AtomConcat(A, "bc", "abc")` → A = "a"
   - `AtomConcat("a", "bc", "abc")` → succeeds (all bound, match)
   - `AtomConcat("x", "bc", "abc")` → fails (all bound, mismatch)
   - `AtomConcat(A, B, C)` all unbound → instantiation_error
   - `AtomConcat("abc", B, C)` C unbound → instantiation_error

---

## 2e — SubAtom/5

**Files:** `clausal/logic/builtins/chars.py`, `tests/test_chars.py`

### Semantics

`SubAtom(Atom, Before, Length, After, Sub)` — the most complex predicate in
this phase. Relates a string to its substrings with position information:

- **Atom** — the full string (must be bound)
- **Before** — number of characters before the substring
- **Length** — length of the substring
- **After** — number of characters after the substring
- **Sub** — the substring itself

Constraint: `Before + Length + After = len(Atom)` where all are non-negative.

This is a five-argument relation with many valid modes. The key insight is that
any three of {Before, Length, After, len(Atom)} determine the fourth, and then
Sub is determined. When fewer are known, we enumerate.

### Mode Analysis

The general approach: iterate over all valid (Before, Length) pairs consistent
with the bound arguments, compute After and Sub, and unify.

| Known | Strategy |
|---|---|
| All of Before, Length, After, Sub | Verify consistency |
| Before + Length | Compute After, extract Sub, unify |
| Before + After | Compute Length = len(Atom) - Before - After, extract Sub |
| Before + Sub | Length = len(Sub), compute After, check Sub matches |
| Length + After | Compute Before = len(Atom) - Length - After, extract Sub |
| Length + Sub | Find all positions where Sub occurs with given length |
| After + Sub | Compute Before + Length from After, check Sub matches |
| Sub only | Find all positions of Sub in Atom |
| Before only | Enumerate all Lengths 0..len(Atom)-Before |
| Length only | Enumerate all Before values 0..len(Atom)-Length |
| After only | Enumerate all Before values 0..len(Atom)-After |
| None bound | Enumerate all (Before, Length) pairs |

This is complex but the implementation can be unified: enumerate all valid
(Before, Length) pairs, compute After and Sub, and try to unify all four
output arguments. The unification will fail for pairs that don't match the
bound arguments, so we don't need separate code paths for each mode.

### Implementation

The brute-force approach is clean and correct:

```python
@_builtin("SubAtom", 5)
def _sub_atom__5(atom, before, length, after, sub, trail, k):
    va = deref(atom)
    if is_var(va) or not isinstance(va, str):
        if is_var(va):
            raise LogicException(instantiation_error("sub_atom/5"))
        raise LogicException(type_error("atom", va, "sub_atom/5"))

    n = len(va)
    vb, vl, vaf, vs = deref(before), deref(length), deref(after), deref(sub)

    # Optimization: if Sub is bound, use str.find to locate occurrences
    # instead of enumerating all (Before, Length) pairs.
    if not is_var(vs) and isinstance(vs, str):
        sub_len = len(vs)
        start = 0
        while True:
            pos = va.find(vs, start)
            if pos == -1:
                break
            b, l, a = pos, sub_len, n - pos - sub_len
            mark = trail.mark()
            if (unify(before, b, trail) and unify(length, l, trail)
                    and unify(after, a, trail) and unify(sub, vs, trail)):
                yield None
            trail.undo(mark)
            start = pos + 1
        return

    # General case: enumerate (Before, Length) pairs
    for b in range(n + 1):
        for l in range(n - b + 1):
            a = n - b - l
            s = va[b:b + l]
            mark = trail.mark()
            if (unify(before, b, trail) and unify(length, l, trail)
                    and unify(after, a, trail) and unify(sub, s, trail)):
                yield None
            trail.undo(mark)
```

The Sub-bound optimization is important: `SubAtom("abcabc", _, _, _, "bc")`
should find positions 1 and 4 using `str.find()` (O(n) per occurrence), not
enumerate all O(n²) substring pairs.

When Before or Length is bound, the inner loop could be narrowed. But the
unification-based filtering is correct and fast enough for typical string
lengths. Only optimize if profiling shows this is a bottleneck.

### Sub-steps for 2e

1. **Add `SubAtom/5`** with Sub-bound optimization and general enumeration.
2. **Tests** (~12 tests):
   - `SubAtom("hello", 1, 3, 1, S)` → S = "ell"
   - `SubAtom("hello", 0, 5, 0, S)` → S = "hello" (whole string)
   - `SubAtom("hello", 0, 0, 5, S)` → S = "" (empty prefix)
   - `SubAtom("hello", B, L, A, "ell")` → B=1, L=3, A=1
   - `SubAtom("abcabc", B, _, _, "bc")` → B=1 and B=4 (two occurrences)
   - `SubAtom("abc", B, 1, A, S)` → 3 solutions: (0,1,2,"a"), (1,1,1,"b"), (2,1,0,"c")
   - `SubAtom("abc", B, L, A, S)` → 10 solutions (all substrings)
   - `SubAtom("abc", 0, L, A, S)` → 4 solutions: ("","ab","abc","a") — no wait, (0,0,3,""), (0,1,2,"a"), (0,2,1,"ab"), (0,3,0,"abc")
   - `SubAtom("hello", 1, 3, 2, "ell")` → fails (After=2 but should be 1)
   - `SubAtom("hello", 1, 3, 1, "ell")` → succeeds (all bound, consistent)
   - `SubAtom(X, _, _, _, _)` → instantiation_error
   - `SubAtom("", B, L, A, S)` → 1 solution: (0,0,0,"")

---

## 2f — Listing/1

**Files:** `clausal/logic/builtins/io.py`, `tests/test_listing.py` (new)

### Semantics

`Listing(Pred)` — print all clauses of a predicate to stdout in readable
Clausal syntax. The primary debugging predicate for inspecting definitions
at runtime.

Takes a predicate class (a PredicateMeta class object, not an instance).

### The Hard Problem: Reconstructing Clause Source

This is the most complex predicate in this phase because of how clauses are
stored internally.

**What we have:** `pred_cls._clauses` is a `list[Clause]`. Each `Clause` has:
- `head`: a **PredicateMeta instance** (e.g., `fib(n=0, f=Var())`) with field
  values that may include Var objects from the original parse.
- `body`: a **list of `clausal.pythonic_ast.nodes` objects** (Call, BinOp,
  Compare, etc.) — these are Clausal's custom AST nodes, NOT Python's `ast`
  module nodes.

**What we need:** readable output like:
```
fib(0, 1).
fib(N_, F_) <- (N_ > 0, N1_ is N_ - 1, fib(N1_, F1_), F_ is F1_ * N_).
```

**Problem 1 — Head formatting:** `term_str()` falls through to `repr(t)` for
PredicateMeta instances (line 716 of `terms.py`). The `__repr__` generated by
`_make_repr` produces `fib(n=0, f=1)` with keyword syntax and `repr()` on
field values. This is *usable* but not ideal — we want positional syntax to
match what the user wrote: `fib(0, 1)`, not `fib(n=0, f=1)`.

**Solution:** Use `is_term_instance()` and `term_field_names()` from
`clausal/logic/predicate.py` to detect PredicateMeta instances in the
`_format_clause_head` helper:

```python
def _format_clause_head(head):
    """Format a clause head as 'functor(arg1, arg2, ...)'."""
    from clausal.logic.predicate import is_term_instance, term_field_names
    if is_term_instance(head):
        name = type(head).__name__
        fields = term_field_names(head)
        args = [_format_clause_term(getattr(head, f)) for f in fields]
        return f"{name}({', '.join(args)})"
    return term_str(head)
```

**Problem 2 — Body goal formatting:** Body goals are `clausal.pythonic_ast.nodes`
objects. These have `__str__` methods that produce readable output (e.g.,
`Call.__str__` returns `"fib(N1_, F1_)"`, `BinOp.__str__` returns `"N_ - 1"`).
So `str(goal)` *should* work.

But wait — do the AST node `__str__` methods handle Var objects correctly?
The AST nodes store their arguments as other AST nodes (LoadName, Literal,
etc.), not as Var objects. The Var objects are only in the *head* — the body
is pure AST. So `str(goal)` on body goals should produce correct Clausal
syntax because the body was never transformed from its AST representation.

Let me verify this by tracing the flow:
1. Parser reads `fib(N_, F_) <- (N_ > 0, fib(N1_, F1_))`.
2. `TermTransformer` transforms the head into a PredicateMeta instance with
   Var field values.
3. The body remains as AST nodes: `[Compare(LoadName("N_"), [Gt()], [Literal(0)]),
   Call(LoadName("fib"), [LoadName("N1_"), LoadName("F1_")])]`.
4. `_flatten_body` flattens And-chains to a list.

So body goals are AST nodes with `LoadName("N_")` references — their `__str__`
produces `"N_ > 0"` and `"fib(N1_, F1_)"`. This is correct and readable.

**Problem 3 — Var naming in heads:** The clause head has actual Var objects
for its unbound fields. When we format them, we need to recover the original
variable names. But Var objects are anonymous — they only have numeric IDs
(`_42`), not names.

How does the existing system handle this? During compilation, variable names
come from the AST (LoadName nodes). The compiler maps AST variable names to
Var objects. But this mapping is not stored on the Clause object — it's
ephemeral, used only during compilation.

**Options:**

**Option A — Store variable name mapping on Clause:**
Add a `var_names: dict[int, str]` field to the `Clause` dataclass that maps
`id(var)` → original name. The import hook populates this during clause
creation by walking the head AST and matching positional args to field names.

Problem: `id(var)` is unstable (objects can be garbage collected and IDs
reused). Better to use the Var object directly as a key, but Var objects are
unhashable (mutable).

Problem: the head is already transformed from AST to a term instance by the
time the Clause is created. The original AST variable names are lost.

**Option B — Use field names as variable names:**
For PredicateMeta instances, the field names *are* the variable names (by
convention). `fib(n=Var(), f=Var())` → display as `fib(N_, F_)` by
title-casing the field name and adding underscore. This is a heuristic —
it works for simple facts but breaks for clauses like
`append([H | T], L, [H | R])` where field names don't correspond to the
head variable names.

Wait — how are clause heads stored for rules with complex patterns? Let me
think about what `append([H_ | T_], L_, [H_ | R_]) <- (append(T_, L_, R_))`
looks like as a Clause:

The head would be: `append(first=[H_ | T_], second=L_, third=[H_ | R_])`.
Here the field values are list patterns with Var objects. The Vars inside
the head *are* the same Var objects used (via name) in the body AST... but
the body is AST nodes with `LoadName("H_")`, `LoadName("T_")`, etc. The
connection between head Vars and body variable names exists only through
the compiler's variable mapping.

**Option C — Accept imperfect output:**
Display head Vars as `_N` (their default `str()` representation) and body
goals via `str(goal)`. The output won't be perfectly round-trippable but
will be informative:

```
% append/3 — 2 clause(s)
append([], _42, _42).
append([_43 | _44], _42, [_43 | _45]) <- (append(_44, _42, _45)).
```

This is what SWI-Prolog does when variable names aren't available — it uses
`_G123` style names. It's not beautiful but it's *correct* and useful for
debugging.

**Option D — Store source text on Clause objects (simplest):**
Add a `source: str | None = None` field to the `Clause` dataclass. When the
import hook processes `.clausal` files, store the original source line(s) on
each Clause. `Listing` just prints `clause.source` if available, falling back
to reconstructed output for dynamically asserted clauses.

This is the least work and gives the best output for the common case (clauses
loaded from `.clausal` files). Dynamically asserted clauses (via `Assert`) get
the reconstructed `_N`-variable output, which is fine.

**Decision: Option D (store source text) with Option C as fallback.**

The import hook already has access to the original source text (it reads the
`.clausal` file). We can slice the relevant lines and attach them to each
Clause. For dynamic clauses, fall back to `repr(head)` + `str(body_goal)`.

Actually — is the source text readily available at clause creation time? The
import hook calls `Module.define_predicate(predicate_node)` where
`predicate_node` is a `Predicate` AST node from the parser. The `Predicate`
node has `head` and `body` sub-nodes with source positions (line numbers).

Wait — do Clausal's custom AST nodes have source position info? Let me check.

Looking at `clausal/pythonic_ast/nodes.py`: the base `Node` class likely has
line/col attributes (common for AST nodes). If so, we can extract the source
text from the original file using the line numbers.

But this adds complexity. The simpler approach: the `Predicate` node itself
can be `str()`'d — it has a `__str__` method (or its sub-nodes do). If
`str(predicate_node)` produces readable output, we can store that.

Actually, the `Predicate` node's `__str__` would need to format `head <- body`
which depends on head/body `__str__` methods. The body nodes have `__str__`,
but the head might already be transformed to a term instance.

**Revised decision: Option C (accept imperfect output) for the first
implementation.** If users request better output, upgrade to Option D later.
The reconstructed output is good enough for debugging:

```python
def _format_clause(clause):
    """Format a Clause for Listing output."""
    head_str = _format_clause_head(clause.head)
    if clause.is_fact():
        return f"{head_str}."
    body_strs = [str(g) for g in clause.body]
    body = ", ".join(body_strs)
    if len(clause.body) > 1:
        return f"{head_str} <- ({body})."
    return f"{head_str} <- {body}."
```

For head formatting, use `is_term_instance` to detect PredicateMeta instances
and format field values with `_format_clause_term`:

```python
def _format_clause_term(val):
    """Format a term value for clause display."""
    from clausal.logic.variables import deref, is_var, Var
    val = deref(val)
    if is_var(val):
        return str(val)  # _N format
    if isinstance(val, list):
        return "[" + ", ".join(_format_clause_term(e) for e in val) + "]"
    return repr(val) if isinstance(val, str) else str(val)
```

### Sub-steps for 2f

1. **Add `_format_clause_head(head)` helper** to `io.py` — uses
   `is_term_instance`/`term_field_names` for PredicateMeta instances, falls
   back to `term_str` for Compound/Call heads.

2. **Add `_format_clause_term(val)` helper** — recursive term formatter for
   head field values (handles Var, list, nested terms).

3. **Add `_format_clause(clause)` helper** — combines head + body formatting.

4. **Add `Listing/1` builtin** — iterates `pred_cls._clauses`, prints header
   and formatted clauses.

5. **Handle edge cases:**
   - Argument is a PredicateMeta *class* (not instance) → correct usage.
   - Argument is a PredicateMeta *instance* → extract the class via `type(val)`.
   - Argument is not a predicate → `type_error`.
   - Predicate has no clauses → print `% name/arity — no clauses`.
   - Predicate is a builtin → print `% name/arity — builtin`.

6. **Tests** in `tests/test_listing.py` (~12 tests):
   - Listing of a predicate with facts only → prints each fact
   - Listing of a predicate with rules → prints `head <- (body).`
   - Listing of a predicate with no clauses → prints "no clauses"
   - Listing of a predicate with multiple clauses → all shown
   - Listing with PredicateMeta instance (not class) → resolves to class
   - Listing with non-predicate argument → type_error
   - Listing with dynamically asserted clauses (Assert + Listing)
   - Listing of a fact with ground head → no Var names needed
   - `.clausal` integration test: load file, call Listing, verify output
   - Listing output includes header comment with clause count
   - Listing with complex body goals (arithmetic, nested calls)
   - Listing with list patterns in head

---

## 2g — PortrayClause/1

**Files:** `clausal/logic/builtins/io.py`, `tests/test_listing.py`

### Semantics

`PortrayClause(Term)` — pretty-print a term with indentation for multi-line
display. This is a thin wrapper around `term_pformat()` from `clausal/terms.py`.

Design question: is this distinct enough from `PrintTerm/1` to justify its
existence? Let's compare:

- `PrintTerm/1` uses `term_str()` — single-line, compact output.
- `PortrayClause/1` uses `term_pformat()` — multi-line, indented output for
  deeply nested terms.

The difference is meaningful for complex terms — `PrintTerm/1` produces a
single long line, while `PortrayClause/1` breaks it into readable indented
lines. This justifies having both.

### Implementation

```python
@_builtin("PortrayClause", 1)
def _portray_clause__1(term, trail, k):
    from clausal.logic.solve import _deref_walk
    from clausal.terms import term_pformat
    val = _deref_walk(term)
    print(term_pformat(val))
    yield None
```

### Sub-steps for 2g

1. **Add `PortrayClause/1`** to `io.py`.
2. **Tests** (~5 tests):
   - Simple term → single-line output (same as PrintTerm)
   - Deeply nested term → multi-line indented output
   - List of lists → indented bracket structure
   - Unbound vars → shown as `_`
   - DictTerm/SetTerm → properly formatted

---

## File Summary

| File | Action |
|---|---|
| `clausal/logic/builtins/chars.py` | **New** — CharType/2, CharCode/2, UpcaseAtom/2, DowncaseAtom/2, AtomLength/2, AtomChars/2, AtomCodes/2, AtomConcat/3, SubAtom/5 |
| `clausal/logic/builtins/io.py` | Add Listing/1, PortrayClause/1, helper functions |
| `clausal/logic/builtins/__init__.py` | Import chars module |
| `tests/test_chars.py` | **New** — character and string predicate tests |
| `tests/test_listing.py` | **New** — Listing/1 and PortrayClause/1 tests |
| `tests/fixtures/listing_test.clausal` | **New** — `.clausal` integration fixture for Listing |
| `docs/builtins.md` | Update with new predicates |

## Implementation Order

1. **2a (CharType + CharCode)** — standalone, no dependencies. Establishes the
   `chars.py` module and the registration pattern. Good warm-up.

2. **2b (UpcaseAtom, DowncaseAtom)** — trivial wrappers, adds to `chars.py`.

3. **2c (AtomLength, AtomChars, AtomCodes)** — bidirectional mode detection
   pattern, same module.

4. **2d (AtomConcat)** — reverse-mode enumeration, builds on the bidirectional
   pattern from 2c.

5. **2e (SubAtom)** — most complex predicate in the phase. Multi-modal
   5-argument relation with optimization for Sub-bound case.

6. **2g (PortrayClause)** — trivial wrapper around `term_pformat`.

7. **2f (Listing)** — depends on understanding the Clause object structure,
   PredicateMeta instance formatting, and body-goal `__str__` methods. Most
   design exploration required.

## Test Count Estimate

~72 tests across the phase:
- CharType/2 + CharCode/2: ~15 tests
- UpcaseAtom/2, DowncaseAtom/2: ~6 tests
- AtomLength/2, AtomChars/2, AtomCodes/2: ~12 tests
- AtomConcat/3: ~10 tests
- SubAtom/5: ~12 tests
- Listing/1: ~12 tests
- PortrayClause/1: ~5 tests
