# Running ISO Prolog Programs in Clausal: Compatibility Report

*Prepared for discussion with Markus Triska, 2026-03-25*

## Executive Summary

Clausal already has a comprehensive bidirectional Prolog translator (tokenizer, Pratt parser, AST, dialect-aware emission) and covers most ISO builtins. The main obstacles to *running* translated ISO Prolog programs are:

1. **Cut (`!/0`)** — fundamentally at odds with Clausal's exhaustive search
2. **Atoms vs. strings** — ISO atoms are a distinct type; Clausal uses Python `str`
3. **List representation** — Python lists vs. cons-pairs (./2)
4. **Operator syntax** — Python's fixed operator set vs. user-defined operators
5. **Arithmetic semantics** — floor vs. truncate division; `1 == 1.0` in Python
6. **If-then-else** — ISO `(C -> T ; E)` committed-choice vs. Clausal's reified/general ITE
7. **Module system** — ISO `module/2` + `use_module/1` vs. Clausal's `-import_from`/`-import_module`
8. **Minor builtin gaps** — a few ISO builtins not yet implemented

---

## Issue 1: Cut (`!/0`)

### The Problem

Cut is the most fundamental incompatibility. ISO Prolog's cut prunes the search
tree — it commits to the current clause and discards remaining clauses for the
predicate, plus any choice points created since the clause head was entered.

Clausal compiles predicates to Python generators. Each clause is a `case` arm in
a `match` statement. There is no mechanism to "skip remaining case arms" from
within a body goal, because Python generators don't support that kind of non-local
control flow.

### How Cut Is Used in Practice

Most real-world uses of cut fall into a few patterns:

1. **Green cut (determinism commit):** "I found the right clause, don't try the others"
   ```prolog
   max(X, Y, X) :- X >= Y, !.
   max(_, Y, Y).
   ```

2. **Red cut (negation by failure):** "If this succeeds, don't try the alternative"
   ```prolog
   classify(X, positive) :- X > 0, !.
   classify(X, zero) :- X =:= 0, !.
   classify(_, negative).
   ```

3. **Once/commit:** "Find the first solution and stop"
   ```prolog
   first_member(X, L) :- member(X, L), !.
   ```

4. **If-then-else desugaring:** `(C -> T ; E)` is defined as `(C, !, T ; E)` in ISO.

### Options

#### Option A: Translate cut to `Once()` + guarded clauses (recommended for import)

During Prolog-to-Clausal translation, recognize cut patterns and translate them
to Clausal idioms:

```
% Prolog green cut
max(X, Y, X) :- X >= Y, !.
max(_, Y, Y).

% Clausal translation
Max(X, Y, Z) <- (X >= Y and Z is X) or (X < Y and Z is Y),
```

Or using if-then-else:

```
Max(X, Y, Z) <- (Z is X if X >= Y else Z is Y),
```

For the `member(X,L), !` pattern, translate to `Once(In(X, L))`.

**Pros:** Clean, no new runtime mechanism needed.
**Cons:** Pattern recognition is imperfect; some cut uses are complex.

#### Option B: Committed-choice blocks (new syntax)

Introduce a `.commit()` method or `commit` keyword that says "if the preceding
goals succeeded, don't try further clauses":

```python
# Syntax option 1: .commit() method on goal tuple
Max(X, Y, X) <- (X >= Y).commit(),
Max(_, Y, Y),

# Syntax option 2: commit as a separator
Max(X, Y, X) <- (X >= Y, commit, <goals after>),
Max(_, Y, Y),

# Syntax option 3: >> operator (but already used for DCG)
Max(X, Y, X) <- (X >= Y) >> True,
Max(_, Y, Y),
```

**Implementation sketch:** When the compiler sees `commit` in a clause body at
position `i`, it splits the body into `guard` (goals 0..i-1) and `continuation`
(goals i+1..end). The generated code:

```python
case Max(x=_v0, y=_v1, z=_v2):
    mark = trail.mark()
    # guard goals
    if deref(_v0) >= deref(_v1):
        if unify(_v2, _v0, trail):
            # continuation goals (here just yield)
            yield None
    trail.undo(mark)
    return  # ← THIS is the cut: skip remaining case arms
```

The key is the `return` after the guard succeeds (even if the continuation fails).
If the guard fails, fall through to the next clause as normal.

**Pros:** Direct semantic equivalent of green/red cut. Simple to implement.
**Cons:** New keyword/syntax. Still doesn't handle cut in the *middle* of a body
with goals after it (though this is rare and arguably bad style).

#### Option C: `Committed` wrapper for entire predicate

```python
# Mark predicate as "first clause that matches wins"
-committed([Max/3])

Max(X, Y, X) <- X >= Y,
Max(_, Y, Y),
```

This is like Mercury's `det`/`semidet` determinism declarations. The compiler
generates code that returns after the first clause whose guard (all goals up to
the first call) succeeds.

**Pros:** Very clean for the common case. No per-clause annotation.
**Cons:** Too coarse — some predicates use cut in only some clauses.

#### Option D: Soft-cut / `if-then-else` only (status quo + documentation)

Don't add cut at all. Document that:
- Green cuts → use if-then-else or `Once()`
- Red cuts → use if-then-else with explicit conditions
- Once-style cuts → use `Once(Goal)`
- Complex cuts → refactor to use `Once()`, `FindAll()`, or explicit guards

The Prolog translator already handles `(C -> T ; E)` → `IfExpr`. Extend it to
recognize more cut patterns.

**Pros:** No new syntax. Forces cleaner code.
**Cons:** Some valid Prolog programs can't be translated automatically.

### Recommendation

**Use a combination of B and D:**

1. Add a `commit` goal to the language (Option B, syntax 2):
   ```python
   Max(X, Y, X) <- (X >= Y, commit),
   Max(_, Y, Y),
   ```
   This is a reserved goal name, not an operator. It means "if we reached this
   point, commit to this clause — don't try alternatives." The compiler emits a
   `return` after the committed continuation.

2. For the translator, recognize common cut patterns and emit `commit`, `Once()`,
   or `IfExpr` as appropriate (Option A). Fall back to a `commit` + warning
   comment for unrecognized patterns.

3. Document that arbitrary cut placement (e.g., `a, b, !, c, d` where `c` can
   fail and we still don't want backtracking into `a,b`) is not supported.
   This covers ~95% of real-world cut usage.

**Implementation complexity:** Low. The compiler already has `Once()` and `IfExpr`.
Adding `commit` is essentially "after the guard block, emit `return` instead of
`fall-through`."

---

## Issue 2: Atoms vs. Strings

### The Problem

In ISO Prolog, atoms and strings are distinct types:
- `foo` is an atom (interned symbol)
- `"foo"` is a list of character codes (ISO) or a string (SWI)
- Atoms have identity; `foo == foo` always.

In Clausal, atoms are Python strings:
- `"foo"` and `'foo'` are both Python `str` objects
- There is no separate atom type
- `IsStr/1` (Clausal's `atom/1`) tests for `str`

### Where This Matters

1. **`atom/1` type check:** In ISO, `atom([])` succeeds (empty list is an atom).
   In Clausal, `IsStr([])` fails (it's a list).

2. **Double-quoted strings:** ISO says `"abc"` = `[97,98,99]` (list of codes).
   SWI says `"abc"` is a string object. Clausal says `"abc"` is a `str`.

3. **Atom arithmetic:** ISO allows `atom_length(foo, N)` where `foo` is unquoted.
   In Clausal, `foo` would be a Python name (variable or function), not a string.

4. **Functor names:** In ISO, `f(a,b)` has functor `f` (an atom). In Clausal,
   functors are Python class names (PredicateMeta instances).

### Options

**Option A: Status quo + documentation (recommended)**

Accept that Clausal atoms are Python strings. Document the differences:
- Unquoted atoms in Prolog → string literals in Clausal: `foo` → `"foo"`
- `atom([])` → not supported (and shouldn't be — `[]` isn't an atom)
- The translator already handles this: Prolog `foo` → Clausal `"foo"` in data position

This is the right choice because:
- Adding a separate Atom type would break Python interop (the main selling point)
- SWI-Prolog itself moved toward treating strings as first-class (not code lists)
- Markus's Scryer Prolog uses proper atoms but the distinction rarely matters in practice

**Option B: Atom wrapper type**

Add `class Atom(str)` that behaves like `str` but is distinguishable:
```python
class Atom(str):
    """ISO Prolog atom — interned string."""
    pass
```

**Pros:** `isinstance(x, Atom)` distinguishes atoms from strings.
**Cons:** Adds complexity; Python code would need to wrap every atom. Not Pythonic.

### Recommendation

**Option A.** The translator should map Prolog atoms to Python string literals.
Document that `[]` is not an atom in Clausal. This matches SWI-Prolog's modern
direction.

---

## Issue 3: List Representation

### The Problem

ISO Prolog lists are cons-pairs: `.(H, T)` where `T` is either another cons-pair
or `[]`. This allows partial lists (where the tail is an unbound variable):

```prolog
X = [1, 2 | Y]   % Y is unbound — X is a partial list
```

Clausal uses Python lists, which are fixed-length arrays. The `[H, *T]` pattern
matching works for destructuring, but:

1. **Partial lists can't exist** — a Python list can't have an unbound tail
2. **Difference lists** — a common Prolog idiom — don't work
3. **`append/3` in output mode** — `Append(X, Y, [1,2,3])` needs to enumerate
   all splits, which works for Python lists but differs semantically from cons-based append

### Where This Matters

- DCGs internally use difference lists
- Many Prolog algorithms rely on partial lists for efficiency
- `=../2` (univ) returns a list — if the term has variable arguments, the list
  has variable elements (this works fine with Python lists)

### Current State

Clausal already has `SegList` (segment list) in `clausal/terms.py` for DCG state
threading — this is essentially a difference-list implementation. The compiler
handles list head/tail patterns via `_head_list_unify_input`/`_head_list_unify_output`.

### Options

**Option A: Status quo + SegList for DCGs (current approach)**

Python lists for normal use. SegList for DCGs. Document that difference lists
are not a general-purpose idiom in Clausal.

**Option B: Cons-cell type**

Add `Cons(head, tail)` as a term type alongside Python lists. Prolog programs
that use partial lists get translated to Cons-based code.

```python
class Cons:
    head: Any
    tail: Any  # Cons | list | Var
```

**Pros:** Full ISO list semantics.
**Cons:** Two list representations is confusing. Python interop suffers (can't
use Python list operations on Cons cells). Performance of Cons traversal is
worse than Python list indexing.

### Recommendation

**Option A.** Python lists are the right default. The translator should convert
Prolog partial-list patterns to explicit guard goals where needed. For the rare
case of difference lists, document that Clausal uses SegList for DCGs and
accumulator patterns for everything else.

---

## Issue 4: Operator Syntax

### The Problem

ISO Prolog allows user-defined operators via `op/3`:
```prolog
:- op(700, xfx, <>).
X <> Y :- X \= Y.
```

Python has a fixed set of operators. You cannot define new infix operators.

Additionally, some ISO operators have no Python equivalent:
- `=..` (univ) — two dots, not a valid Python token
- `\+` — backslash-plus, not valid Python
- `=:=`, `=\=` — compound operators, not valid Python
- `@<`, `@>`, `@=<`, `@>=` — term ordering operators

### Current State

The translator already maps ISO operators to Clausal equivalents:
- `=` → `is` (unification)
- `\+` → `not`
- `is` → `:=` (arithmetic evaluation)
- `;` → `or`
- `=..` → `Unpack(Term, List)` (builtin call)
- `=:=` → arithmetic comparison via `:=` + `==`

### What's Missing

- `@<`, `@=<`, `@>`, `@>=` — standard order comparison. Need `Compare/3` or
  dedicated builtins like `TermLt/2`, `TermLe/2`, `TermGt/2`, `TermGe/2`.
- User-defined operators — not supportable in Python syntax. Translate to
  predicate calls.

### Recommendation

1. Add `Compare/3` builtin (returns `<`, `=`, or `>` per ISO term ordering)
2. Add `TermLt/2`, `TermGt/2` etc. as convenience wrappers
3. Translate `:- op(...)` directives to comments/warnings during import
4. Translate uses of user-defined operators to predicate calls

---

## Issue 5: Arithmetic Semantics

### The Problem

Several arithmetic differences between Python and ISO Prolog:

| Operation | ISO Prolog | Python/Clausal |
|-----------|-----------|----------------|
| `-7 // 2` | `-3` (truncate) | `-4` (floor) |
| `-7 mod 2` | `-1` (truncate) | `1` (floor) |
| `1 =:= 1.0` | succeeds | succeeds (`==` in Python) |
| `1 = 1.0` | **fails** (structural) | **fails** (unification uses `is` identity) |
| `max_integer` | may overflow | arbitrary precision (no overflow) |
| `float_overflow` | may raise | `inf` (Python float semantics) |
| `0/0` | error | `ZeroDivisionError` |
| `2 ** -1` | error (some) or `0.5` | `0.5` (Python) |
| `1 + a` | type error | `TypeError` |

### What Clausal Already Does Right

- Arbitrary precision integers (Python default) — better than most Prologs
- Clear error on division by zero
- Arithmetic evaluation via `:=` is explicit and clean

### Recommendation

1. **Floor vs. truncate:** Add `truncate_div/2` and `truncate_mod/2` builtins for
   ISO compatibility. Keep Python-native `//` and `%` as defaults. The translator
   should map Prolog `//` to `truncate_div` and `mod`/`rem` to `truncate_mod`
   when targeting ISO mode.

2. **Float equality:** Document that `1 =:= 1.0` succeeds in both systems.
   Structural unification (`1 is 1.0`) fails in both (Clausal uses Python `is`
   identity for numeric unification, not `==`).

3. **Type errors:** Clausal already raises `TypeError` for `1 + "a"`. Map these
   to ISO `type_error(evaluable, a/0)` in the exception system.

---

## Issue 6: If-Then-Else

### The Problem

ISO defines `(C -> T ; E)` as:
```prolog
(C -> T ; E) :- C, !, T.
(C -> T ; E) :- E.
```

This is **committed choice** — if `C` succeeds, commit to `T`; backtracking into
`C` is not allowed. If `C` fails, try `E`.

Clausal has two ITE mechanisms:
1. **Reified ITE** — for `Unify`/`Dif`/CLP(FD) conditions: both branches explored
2. **General ITE** — sub-generator for condition, committed choice for then/else

### Current State

The general ITE already implements committed-choice semantics correctly:
the condition is run as a sub-generator; if it yields at least one solution,
the "then" branch runs (once per condition solution); if it yields none, the
"else" branch runs. This matches ISO `(C -> T ; E)`.

### What's Missing

The translator needs to reliably map `(C -> T ; E)` to Clausal's `IfExpr`:
```python
(T if C else E)   # Python ternary — maps to IfExpr node
```

And bare `(C -> T)` (without else) to:
```python
(T if C else False)   # or just Once(C), T
```

### Recommendation

This is mostly a translator issue, not a runtime issue. The machinery exists.
Ensure the Prolog-to-Clausal translator handles:
- `(C -> T ; E)` → `(T if C else E)` IfExpr
- `(C -> T)` → `(T if C else False)` or `Once(C), T`
- Nested `(C1 -> T1 ; C2 -> T2 ; E)` → chained IfExpr

---

## Issue 7: Module System

### The Problem

ISO Prolog's module system uses:
```prolog
:- module(lists, [member/2, append/3]).
:- use_module(library(lists)).
```

Clausal uses:
```python
-import_from(lists, [In, Append]),
-import_module(lists),
```

### Differences

| Feature | ISO Prolog | Clausal |
|---------|-----------|---------|
| Declaration | `module(Name, Exports)` | `-module(Name, Exports)` |
| Import | `use_module(library(X))` | `-import_from(X, [...])` |
| Qualified calls | `lists:member(X, L)` | `lists.In(X, L)` |
| Re-export | `reexport(module)` | Not supported |
| Meta-predicate decl | `:- meta_predicate maplist(2, +)` | Not needed (Python closures) |

### Recommendation

The translator should map:
- `:- module(Name, Exports)` → `-module(Name, Exports)`
- `:- use_module(library(X))` → `-import_from(X, [...])`
- `:- use_module(X, [pred/arity])` → `-import_from(X, [Pred])`
- Qualified calls `M:Goal` → `M.Goal`

Most of this is already handled in the translator. The main gap is that Clausal
doesn't have a standard library path mapping for all common Prolog libraries.
Add library mappings as needed.

---

## Issue 8: Naming Conventions

### The Problem

ISO Prolog uses lowercase for predicates and uppercase-initial for variables:
```prolog
member(X, [X|_]).
member(X, [_|T]) :- member(X, T).
```

Clausal uses PascalCase for predicates and ALLCAPS/trailing-underscore for variables:
```python
In(X, [X, *_]),
In(X, [_, *T]) <- In(X, T),
```

### Current State

The translator already handles this bidirectionally:
- `member` → `In` (via BUILTIN_NAME_MAP) or `Member` (via `snake_to_pascal`)
- `X` → `X` (single uppercase letter stays)
- `Head` → `head_` or `HEAD`
- `_` → `_`

### Edge Cases

- `x` in Prolog is an atom, but `x` in Clausal is also an atom (lowercase, no
  trailing underscore). This is correct.
- `X` in Prolog is a variable, `X` in Clausal is also a variable (single
  uppercase letter). Correct.
- `Xs` in Prolog is a variable. In Clausal it would be `xs_` or `XS`. The
  translator uses `xs_`.
- `foo_bar` in Prolog is an atom. In Clausal it's also an atom (no trailing `_`).
  Correct.
- `Foo_bar` in Prolog is a variable. In Clausal → `foo_bar_` (trailing `_`). Correct.

### Recommendation

The naming convention translation is solid. One improvement: when a Prolog
variable name is a common English word (e.g., `List`, `Head`, `Tail`, `Result`),
prefer ALLCAPS in Clausal (`LIST`, `HEAD`, `TAIL`, `RESULT`) over trailing
underscore (`list_`, `head_`, `tail_`, `result_`). This matches the preferred
Clausal style.

---

## Issue 9: Specific Missing ISO Builtins

### Already Implemented (comprehensive)

- Arithmetic: `is/2`, `=:=`, `=\=`, `<`, `>`, `=<`, `>=`, `+`, `-`, `*`, `/`,
  `//`, `mod`, `**`, `abs`, `sign`, `min`, `max`, `between/3`, `succ/2`, `plus/3`
- Unification: `=/2`, `\=/2` (as dif), `==/2`, `\==/2`
- Type checking: `var/1`, `nonvar/1`, `atom/1`, `integer/1`, `float/1`,
  `number/1`, `compound/1`, `callable/1`, `ground/1`, `is_list/1`
- Term manipulation: `functor/3`, `arg/3`, `=../2`, `copy_term/2`,
  `term_variables/2`, `numbervars/3`
- Lists: `member/2`, `append/3`, `length/2`, `reverse/2`, `sort/2`, `msort/2`,
  `last/2`, `nth0/3`, `flatten/2`, `select/3`, `permutation/2`
- Chars/atoms: `atom_length/2`, `atom_chars/2`, `atom_codes/2`, `atom_concat/3`,
  `sub_atom/5`, `char_code/2`, `upcase_atom/2`, `downcase_atom/2`,
  `number_chars/2`, `number_codes/2`
- Control: `true/0`, `fail/0`, `call/1..8`, `once/1`, `catch/3`, `throw/1`,
  `halt/0`, `halt/1`, `(,)/2`, `(;)/2`, `(\+)/1`
- Database: `assert/1`, `assertz/1`, `asserta/1`, `retract/1`
- Meta: `findall/3`, `bagof/3`, `setof/3`, `forall/2`
- I/O: `write/1`, `writeln/1`, `nl/0`, `tab/1`
- Higher-order: `maplist/2,3`, `include/3` (Filter), `exclude/3`, `foldl/4`
- Constraints: `dif/2`, CLP(FD), CLP(B)
- DCG: `phrase/2,3`

### Still Missing

| Predicate | ISO Section | Priority | Notes |
|-----------|-------------|----------|-------|
| `compare/3` | §8.4.1 | **High** | Standard term ordering |
| `@</2`, `@>/2`, `@=</2`, `@>=/2` | §8.4.1 | **High** | Term ordering operators |
| `number_vars/3` (ISO version) | §8.5.5 | Low | Already have NumberVars, check conformance |
| `char_type/2` | extension | Low | Already have CharType/2 |
| `read_term/2,3` | §8.14 | Medium | Parse Prolog terms from input |
| `write_term/2,3` | §8.14 | Medium | Write with options (quoted, numbervars, etc.) |
| `write_canonical/1` | §8.14 | Low | Canonical form output |
| `read/1` | §8.14 | Medium | Read term from stdin |
| `open/4`, `close/1` | §8.11 | Low | Stream I/O |
| `get_char/1`, `put_char/1` | §8.12 | Low | Character I/O |
| `stream_property/2` | §8.11 | Low | Stream inspection |
| `set_prolog_flag/2` | §8.17 | Low | Flag management |
| `current_prolog_flag/2` | §8.17 | Low | Flag inspection |
| `clause/2` | §8.8 | Medium | Clause inspection |
| `current_predicate/1` | §8.8 | Medium | Predicate inspection |
| `abolish/1` | §8.9 | Low | Remove predicate |
| `retractall/1` | extension | Medium | Remove all matching |
| `ground/1` | extension | Done | Already `IsGround/1` |
| `succ_or_zero/2` | extension | Low | Natural number successor |
| `msort/2` | extension | Done | Already `MergeSort/2` |

---

## Issue 10: Negation Semantics

### The Problem

ISO `\+/1` is simple negation-as-failure: the goal is called, and if it
succeeds, `\+` fails; if it fails, `\+` succeeds. Bindings from the inner
goal are **not** visible outside.

Clausal has two negation mechanisms:
1. **Simple NAF** (`not Goal`) — same as ISO `\+`
2. **Tabled NAF with WFS** — for tabled predicates, uses Well-Founded Semantics
   to handle cycles through negation

### Compatibility

Simple NAF matches ISO exactly. WFS goes beyond ISO (which doesn't define
behavior for cyclic negation). This is a strict superset — no incompatibility.

### Recommendation

No action needed. Document that Clausal's `not` is ISO `\+`, and WFS provides
additional power for stratified/cyclic programs.

---

## Issue 11: Exception Handling

### The Problem

ISO defines `catch/3` and `throw/1` with structured error terms:
```prolog
catch(Goal, error(type_error(integer, foo), _), Recovery).
```

Clausal has `catch/3` and `throw/1` with `LogicException`. The error term
structure may differ from ISO's `error(ErrorTerm, ImplDefined)` convention.

### Current State

Clausal's exception system uses `LogicException` with structured terms. The
`clausal/logic/exceptions.py` module provides helpers for creating ISO-style
error terms.

### Recommendation

Verify that error terms match ISO structure: `error(ErrorKind, ImplInfo)` where
ErrorKind is one of `type_error/2`, `instantiation_error/0`,
`existence_error/2`, `permission_error/3`, `representation_error/1`,
`evaluation_error/1`, `syntax_error/1`, `resource_error/1`,
`system_error/0`. Align any gaps.

---

## Issue 12: String/Code List Handling

### The Problem

ISO Prolog defines `"hello"` as a list of character codes `[104,101,108,108,111]`.
SWI-Prolog (with `set_prolog_flag(double_quotes, atom)`) treats it as an atom.
Scryer Prolog follows ISO (code list).

Clausal treats `"hello"` as a Python string.

### Recommendation

The translator should:
- When importing from ISO/Scryer: convert code-list operations to string operations
- When importing from SWI: treat double-quoted strings as Clausal strings (direct)
- When exporting to ISO: convert Clausal strings to quoted atoms (`'hello'`)

This is already mostly handled by the dialect system.

---

## Summary: Priority Matrix

| Issue | Severity | Effort | Recommendation |
|-------|----------|--------|----------------|
| Cut | **Critical** | Medium | Add `commit` goal + translator patterns |
| Atoms vs strings | Low | None | Status quo; document |
| List representation | Medium | None | Status quo; Python lists sufficient |
| Operators | Medium | Low | Add `Compare/3` + term ordering builtins |
| Arithmetic | Medium | Low | Add `truncate_div/mod`; document floor semantics |
| If-then-else | Low | Low | Already works; improve translator |
| Module system | Low | Low | Translator mapping; already mostly done |
| Naming | Low | None | Already handled well |
| Missing builtins | Medium | Medium | Prioritize `Compare/3`, `clause/2`, `read/1` |
| Negation | None | None | Already ISO-compatible + WFS extension |
| Exceptions | Low | Low | Verify ISO error term structure |
| String/codes | Low | None | Handled by dialect system |

---

## Appendix: The `commit` Design in Detail

### Syntax

```python
# In a clause body, `commit` is a goal that always succeeds
# but tells the compiler: "if we reached here, don't try other clauses"
Max(X, Y, X) <- (X >= Y, commit),
Max(_, Y, Y),

# With goals after commit
Classify(X, "positive") <- (X > 0, commit, Log("positive", X)),
Classify(X, "zero") <- (X == 0, commit, Log("zero", X)),
Classify(_, "negative"),

# Equivalent to ISO:
# classify(X, positive) :- X > 0, !, log(positive, X).
# classify(X, zero) :- X =:= 0, !, log(zero, X).
# classify(_, negative).
```

### Semantics

1. Goals before `commit` are the **guard**.
2. If the guard succeeds, the predicate is **committed** to this clause.
3. Goals after `commit` are the **continuation**.
4. If the continuation fails, the predicate fails — it does NOT try other clauses.
5. If the guard fails, fall through to the next clause as normal.

### Compilation

For simple mode:
```python
def classify__2(arg0, arg1, trail, k):
    # Clause 1: Classify(X, "positive") <- (X > 0, commit, Log("positive", X))
    mark = trail.mark()
    match (arg0, arg1):
        case (_v0, _v1):
            if deref(_v0) > 0:
                # COMMIT — guard succeeded
                if unify(_v1, "positive", trail):
                    # continuation goals
                    for _ in Log._get_dispatch()(deref("positive"), deref(_v0), trail, k):
                        yield None
                trail.undo(mark)
                return  # ← commit: skip all remaining clauses
    trail.undo(mark)

    # Clause 2: only reached if clause 1's guard failed
    mark = trail.mark()
    match (arg0, arg1):
        ...
```

The key difference from non-committed code: `return` after the guard block
instead of falling through to the next `match` case.

### Alternative Syntax Candidates

If `commit` feels too verbose or too Prolog-ish, alternatives:

1. **`!` as a goal name** (directly borrowed from Prolog):
   - Rejected: `!` is not a valid Python identifier.

2. **`CUT` as a goal name**:
   - `Max(X, Y, X) <- (X >= Y, CUT),`
   - Unambiguous but ugly; suggests exactly the thing we're trying to avoid.

3. **`det` (deterministic) as clause decorator**:
   - `-det` before the clause: `-det, Max(X, Y, X) <- X >= Y,`
   - Reads as "this clause is deterministic (commits on guard success)."

4. **`|` as guard separator** (Mercury/Curry style):
   - Can't use — `|` is already Python bitwise-or / set-union.

5. **Arrow within clause body** (guard → continuation):
   - Can't use `->` — it's Python's return type annotation.

6. **`then` keyword**:
   - `Max(X, Y, X) <- (X >= Y then True),`
   - Reads well but `then` isn't a Python keyword, would need creative encoding.

7. **Indexed block with `//`**:
   - `Max(X, Y, X) <- X >= Y // True,`
   - `//` is floor-division; overloading is confusing.

### Recommended: `commit`

`commit` reads naturally, is unambiguous, and clearly communicates intent:

```python
Classify(X, TYPE) <- (
    X > 0, commit,
    TYPE is "positive"
),
Classify(X, TYPE) <- (
    X == 0, commit,
    TYPE is "zero"
),
Classify(_, "negative"),
```

It's explicit about what's happening (unlike Prolog's `!` which is famously
obscure to newcomers). It's also easy to search for in code.
