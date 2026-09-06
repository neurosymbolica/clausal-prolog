# Running ISO Prolog Programs in Clausal: Compatibility Report

*Prepared for discussion with Markus Triska, 2026-03-25.*
*Updated 2026-03-25 after discussion with Markus.*

*For practical instructions on importing and running Prolog programs, see [Importing Prolog Code](importing_prolog.md).*

!!! warning "Historical record — the representation has moved on"
    This report records decisions as of 2026-03-25. The *semantics* it settles
    still stand (strings are lists of characters; atoms are a distinct type),
    but the **representation** described under Issues 2 and 3 does not: an atom
    is now the arity-0 cell `("red",)`, not a zero-field `PredicateMeta` class,
    and the elements of a character list are one-character **atoms**, not
    one-character strings. Atoms are compared by value equality, never by `is`.
    See [Atoms vs strings](syntax.md#atoms-vs-strings) and
    [Strings as Lists](strings_as_lists.md) for the current model.

## Executive Summary

Clausal has a comprehensive bidirectional Prolog translator (tokenizer, Pratt
parser, AST, dialect-aware emission) and covers most ISO builtins. After
discussion with Markus Triska, the approach to running ISO Prolog programs in
Clausal is:

1. **Cut and if-then-else are out of scope** — programs using them must be
   rewritten. Clausal will not add cut or any surrogate.
2. **Strings are lists of characters** — matching ISO/Scryer semantics.
3. **Atoms are a distinct type** — declared atoms are zero-field PredicateMeta classes (implemented).
4. **Prolog modules imported via `use_module`** — translated through the Prolog
   translation layer. `import_from`/`import_module` remain for Python/Clausal modules.
5. **Operators and arithmetic** — handled entirely in the translation layer.

---

## Issue 1: Cut (`!/0`) and If-Then-Else (`->/2`)

### Decision: Not Supported

Per Markus's recommendation, cut and if-then-else are **completely excluded**
from Clausal's scope. Programs that use cut must be rewritten to use Clausal's
native control flow.

### Rationale

Markus argues (and we agree) that cut is a misfeature of Prolog. It breaks
declarative semantics, makes programs harder to reason about, and is the source
of many subtle bugs. Well-written Prolog programs avoid cut entirely, using
instead:

- **`dif/2`** and constraints for mutual exclusion between clauses
- **`if_/3`** (reified conditionals) for deterministic branching
- **`once/1`** for first-solution commit where needed
- **Proper indexing** to achieve determinism without cut

The same applies to `(C -> T ; E)`, which is defined in terms of cut in ISO
and inherits its problems.

### What Clausal Offers Instead

Clausal already has clean alternatives for every legitimate use of cut:

| Cut pattern | Clausal equivalent |
|-------------|-------------------|
| Green cut (determinism) | [First-argument indexing](indexing.md) + [`dif/2`](constraints.md) guards |
| `member(X,L), !` | [`once(in_(X, L))`](control.md) |
| `(C -> T ; E)` | [Reified if-then-else](reified_ite.md): `(T if C else E)` |
| Red cut (negation) | `not Goal` (NAF) or `dif/2` |
| Committed choice | `once(Goal)` or if-then-else |

### Translation Layer — Implemented

The Prolog-to-Clausal translator now:

- **Rejects** programs containing cut with `PrologTranslationError`, including
  a clear error message explaining that the program must be rewritten and
  listing pure alternatives (dif/2, once/1, indexing, reified ITE)
- **Rejects** `(C -> T ; E)` and bare `(C -> T)` with `PrologTranslationError`,
  suggesting reified conditionals, separate clauses with dif/2 guards, or constraints
- In the **reverse direction**, Clausal's reified `THEN if COND else ELSE` is
  also rejected when translating to Prolog, since the semantics differ

---

## Issue 2: Strings Are Lists of Characters

### Decision: Strings Are Character Lists

Following ISO Prolog and Scryer Prolog, double-quoted strings in Prolog
programs are lists of characters. This is the correct, declarative
representation.

### What This Means

```prolog
% In Prolog
X = "hello"    % X = [h, e, l, l, o]  (list of atoms, each a single char)
```

In Clausal, when running translated Prolog code, `"hello"` must behave as
`['h', 'e', 'l', 'l', 'o']` — a list of single-character atoms.

### Implementation

The translation layer should:

1. Convert Prolog `"string"` literals to character lists in the translated
   Clausal code
2. String-processing builtins (`atom_chars/2`, `atom_codes/2`, etc.) must
   work with character lists
3. Clausal's native `str` type remains available for Python interop — the
   distinction is between Prolog-layer code (character lists) and Python-layer
   code (native strings)

### Interaction with Atom Type

Single characters in character lists are single-character strings.
`atom_chars("hello", Cs)` produces a list of single-character Python strings.

---

## Issue 3: Atoms Are a Distinct Type

### Decision: Zero-Field PredicateMeta Classes (Implemented)

Declared atoms (`-private([red, blue])` or `-module(m, [red, blue])`) are
now zero-field PredicateMeta classes. The class IS the atom value —
`red() is red` holds. No separate `Atom` type is needed.

### Rationale

- `atom/1` type checking must distinguish atoms from strings and other types
- functor names are atoms; they should not be conflated with string data
- Zero-arity predicates and atoms sit on the same continuum (zero fields
  vs N fields) — no new type needed
- Classes have identity (`is` works), are hashable, callable, and support
  module scoping naturally

### Design

Atoms declared in `-private` or `-module` directives become zero-field
PredicateMeta classes:

```python
class red(metaclass=PredicateMeta):
    _fields = ()

red() is red        # True — __call__ returns cls for zero-arity
hash(red)           # Works — type.__hash__
red is not blue     # True — different classes
```

Undeclared atoms (strings, enum members, any Python object) continue to
work in unification as atomic data without any wrapping.

### Type Checking Builtins

| Builtin | Tests for |
|---------|-----------|
| `atom/1` | Zero-arity PredicateMeta class |
| `is_str/1` | `isinstance(x, str)` (excludes declared atoms) |
| `callable_/1` | `str`, `Compound`, `KWTerm`, term instances, or declared atoms |

### String Builtins

`atom_chars/2`, `atom_codes/2`, `atom_length/2`, `upcase_atom/2`,
`downcase_atom/2`, `atom_concat/3`, and `sub_atom/5` all accept both
plain strings and declared atoms (extracting `__name__` for the latter).
Results of string operations are plain strings (undeclared atoms).

### API

```python
from clausal.logic.predicate import make_atom, is_atom_value, make_predicate, is_atom

red = make_atom("red")           # The atom itself: the plain str 'red'
is_atom_value(red)               # True

Red = make_predicate("red", [])  # The zero-arity PredicateMeta CLASS
is_atom(Red)                     # True
Red() is Red                     # True
```

---

## Issue 4: Module System — `use_module` for Prolog, `import_from` for Python

### Decision: Two Import Mechanisms

- **`-use_module(library(lists))`** — imports a Prolog module, passing it through
  the Prolog-to-Clausal translation layer first
- **`-import_from(regex, [match, search])`** / **`-import_module(regex)`** — imports
  a Python/Clausal module directly (existing mechanism, unchanged)

### How `use_module` Works

```
  .clausal source
       |
       v
  -use_module(library(clpfd))
       |
       v
  1. Locate .pl file in Prolog library path
  2. Run through prolog_to_clausal translator
  3. Compile translated source as a Clausal module
  4. Inject exported predicates into caller's namespace
```

The translation is cached (like `__pycache__` for `.clausal` files). The
Prolog library path is configurable and includes standard library locations
for SWI-Prolog, Scryer Prolog, etc.

### Qualified Calls

- Prolog `lists:member(X, L)` → Clausal `lists.in_(X, L)` (via BUILTIN_NAME_MAP)
- For non-builtin predicates: `mymod:foo(X)` → `mymod.Foo(X)` (snake_to_pascal)

### Library Mapping

The dialect configuration (`prolog_dialect.py`) already has a `library_map`
for mapping Prolog library names to Clausal equivalents:

| Prolog | Clausal |
|--------|---------|
| `library(clpfd)` / `library(clpz)` | `clausal.logic.clpfd` |
| `library(clpb)` | `clausal.logic.clpb` |
| `library(lists)` | `clausal.logic.builtins.lists` |
| `library(dcgs)` | built-in (DCG support is native) |

extend this mapping as more Prolog libraries are supported.

---

## Issue 5: Operators and Arithmetic — Translation Layer Only

### Decision: Handled in Translation

Operator syntax differences and arithmetic semantics are resolved entirely
in the Prolog-to-Clausal translation layer. No changes to Clausal's runtime
or compiler are needed.

### Operator Mapping (Already Implemented)

| Prolog | Clausal | Notes |
|--------|---------|-------|
| `X = Y` | `X is Y` | Unification |
| `X \= Y` | `X is not Y` | Dis-unification (dif/2) |
| `\+ G` | `not G` | Negation-as-failure |
| `Y is X * 2` | `eval_(X * 2, Y)` | Eager arithmetic evaluation |
| `Y =:= X * 2` | `Y == X * 2` | Arithmetic equality; atomic-operand `X =:= Y` imports as structural `==` (lossy, pending A11-D008) |
| `X =\= Y` | `X != Y` | Arithmetic disequality constraint |
| `A ; B` | `A or B` | Disjunction |
| `X =< Y` | `X <= Y` | Less-or-equal |
| `X =.. L` | `unpack(X, L)` | Univ |
| `X mod Y` | `prolog.TruncMod(X, Y)` | Floored modulo (see Arithmetic Semantics below) |
| `X /\ Y` | `X & Y` | Bitwise AND |
| `X \/ Y` | `X \| Y` | Bitwise OR |
| `X xor Y` | `X ^ Y` | Bitwise XOR |

### Arithmetic Semantics

Python uses floor division and floor modulo; ISO Prolog implementations vary.
The translation layer handles this:

- Prolog `//` → Clausal `prolog.TruncDiv(X, Y)` — integer division truncated
  toward zero (ISO `(//)/2`; Python's `//` floors instead)
- Prolog `mod` → Clausal `prolog.TruncMod(X, Y)` — floored modulo, sign
  follows the divisor (ISO `mod/2`; equivalent to Python's `%`; the `Trunc`
  prefix is a legacy family name, the operation is not truncating)
- Prolog `rem` → Clausal `prolog.Rem(X, Y)` — truncating remainder, sign
  follows the dividend (ISO `rem/2`)

The translator emits an `-import_module(prolog)` preamble whenever any of
these appear; the helpers live in `clausal/modules/prolog.py`.

Alternatively, since most well-written Prolog uses CLP(FD)/CLP(Z) for integer
arithmetic (per Markus's advocacy), the floor-vs-truncate distinction is
largely irrelevant — constraint-based arithmetic doesn't have this ambiguity.

### User-Defined Operators

Prolog `:- op(Prec, Type, Name)` directives are consumed by the translation
layer's parser (the operator table is mutable during parsing). In the emitted
Clausal code, uses of user-defined operators become predicate calls:

```prolog
:- op(700, xfx, <>).
X <> Y :- dif(X, Y).
% Usage: foo(X) :- X <> bar.
```

Translates to:

```python
NotEqual(X, Y) <- dif(X, Y),
# Usage: Foo(X) <- NotEqual(X, Atom("bar")),
```

---

## Issue 6: List Representation

### Current State

Clausal uses Python lists. ISO Prolog uses cons-pairs (`.(H, T)`).

### Differences That Matter

| Feature | ISO Prolog | Clausal |
|---------|-----------|---------|
| `[H\|T]` pattern | Cons destructuring | `[H, *T]` spread pattern |
| Partial lists | `[1, 2 \| X]` (X unbound) | Not directly supported |
| Difference lists | Common idiom | Use `SegList` or accumulators |
| `[]` type | Atom | Python `list` (empty) |
| `.(a, b)` | Valid (dotted pair) | Not supported |

### Recommendation

Python lists are adequate for the vast majority of translated Prolog programs.
The translation layer should:

1. Convert `[H|T]` → `[H, *T]` (already done)
2. Convert difference-list patterns to accumulator style where recognizable
3. Emit a warning for partial-list constructions that can't be represented
4. Map `[]` to `[]` (Python empty list), not `Atom("[]")`

Programs that fundamentally rely on partial lists (e.g., some DCG
implementations) use Clausal's `SegList` type, which already handles this.

---

## Issue 7: Naming Conventions

### Already Handled

The translator handles bidirectional name conversion:

| Prolog | Clausal | Rule |
|--------|---------|------|
| `member` | `in_` | BUILTIN_NAME_MAP |
| `foo_bar` | `FooBar` | snake_to_pascal |
| `X` | `X` | Single uppercase letter |
| `Head` | `HEAD` | Titlecase var → ALLCAPS (preferred) |
| `Xs` | `XS` | Titlecase var → ALLCAPS |
| `_` | `_` | Anonymous variable |
| `_Ignored` | `_ignored_` | Leading underscore → trailing |

### Improvement: Prefer ALLCAPS for Variables

when translating Prolog variables to Clausal, prefer ALLCAPS over leading
underscore for readability:

- `List` → `LIST` (not `_list`)
- `Head` → `HEAD` (not `_head`)
- `Result` → `RESULT` (not `_result`)
- `Xs` → `XS` (not `_xs`)

---

## Issue 8: Specific Missing ISO Builtins

### Already Implemented (Comprehensive)

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
- Higher-order: `maplist/2,3`, `include/3` (include), `exclude/3`, `foldl/4`
- Constraints: [`dif/2`, CLP(ℤ)](constraints.md), [CLP(B)](clpb.md)
- DCG: [`phrase/2,3`](dcg.md)

### Still Missing

| Predicate | ISO Section | Priority | Notes |
|-----------|-------------|----------|-------|
| `compare/3` | §8.4.1 | **High** | Standard term ordering |
| `@</2`, `@>/2`, `@=</2`, `@>=/2` | §8.4.1 | **High** | Term ordering operators |
| `read_term/2,3` | §8.14 | Medium | Parse Prolog terms from input |
| `write_term/2,3` | §8.14 | Medium | write with options |
| `read/1` | §8.14 | Medium | Read term from stdin |
| `clause/2` | §8.8 | Medium | Clause inspection |
| `current_predicate/1` | §8.8 | Medium | Predicate inspection |
| `retractall/1` | extension | Medium | Remove all matching |
| `open/4`, `close/1` | §8.11 | Low | Stream I/O |
| `get_char/1`, `put_char/1` | §8.12 | Low | Character I/O |
| `stream_property/2` | §8.11 | Low | Stream inspection |
| `set_prolog_flag/2` | §8.17 | Low | Flag management |
| `current_prolog_flag/2` | §8.17 | Low | Flag inspection |
| `abolish/1` | §8.9 | Low | Remove predicate |
| `write_canonical/1` | §8.14 | Low | Canonical form output |

---

## Issue 9: Negation Semantics

### No Incompatibility

Clausal's `not Goal` matches ISO `\+/1` exactly: the inner goal is called;
if it succeeds, negation fails; if it fails, negation succeeds. Bindings from
the inner goal are not visible outside.

For [tabled](tabling.md) predicates, Clausal goes further with [Well-Founded Semantics](wfs.md) (WFS),
handling cycles through negation that ISO leaves undefined. This is a strict
superset — no incompatibility.

---

## Issue 10: Exception Handling

### Mostly Compatible

Clausal has [`catch/3` and `throw/1`](exceptions.md) with `LogicException`. Should verify that
error terms match ISO structure: `error(ErrorKind, ImplDefined)` where ErrorKind
is `type_error/2`, `instantiation_error/0`, `existence_error/2`,
`permission_error/3`, etc.

Low priority — most Prolog programs that avoid cut also handle errors cleanly.

---

## Summary: Priority Matrix

| Issue | Decision | Effort | Notes |
|-------|----------|--------|-------|
| Cut | **Reject** | **Done** | `PrologTranslationError` with suggested alternatives |
| If-then-else | **Reject** | **Done** | `PrologTranslationError` with suggested alternatives |
| Strings | **Char lists** | Medium | `"abc"` → `[Atom('a'), Atom('b'), Atom('c')]` |
| Atoms | **Done** | — | Declared atoms are zero-field PredicateMeta classes |
| Module system | **`use_module`** | Medium | Prolog modules via translation; Python via `import_from` |
| Operators | **Translation layer** | None | Already handled |
| Arithmetic | **Translation layer** | None | Already handled |
| List representation | **Python lists** | None | Status quo; adequate for translated code |
| Naming | **Already done** | Low | Prefer ALLCAPS for variables |
| Missing builtins | **Incremental** | Medium | Prioritize `Compare/3`, term ordering |
| Negation | **Compatible** | None | NAF + WFS is a superset of ISO |
| Exceptions | **Mostly done** | Low | Verify error term structure |

---

## Implementation Phases

### Phase 1: Declared Atoms as Zero-Field PredicateMeta (Done)

1. `PredicateMeta.__call__` returns `cls` for zero-arity (atoms)
2. `-private`/`-module` bare atoms generate zero-field PredicateMeta classes
3. `atom/1` checks for zero-arity PredicateMeta
4. `is_str/1` unchanged (tests `isinstance(x, str)`)
5. String builtins accept both strings and declared atoms via `_atom_to_str`
6. `make_atom()` and `is_atom()` helpers added to `clausal.logic.predicate`

### Phase 2: `use_module` Directive

1. Add `-use_module(library(Name))` directive parsing
2. Implement Prolog library path resolution
3. Wire up: locate `.pl` → translate → compile → inject exports
4. Add translation caching (alongside `__pycache__`)
5. extend `library_map` in `prolog_dialect.py`

### Phase 3: Missing Builtins

1. `Compare/3` and term ordering operators
2. `clause/2`, `current_predicate/1`
3. `retractall/1`
4. `read/1`, `read_term/2,3`, `write_term/2,3`

### Phase 4: Cut/ITE Rejection in Translator — DONE

Implemented in `prolog_to_clausal.py` and `clausal_to_prolog.py`:

1. `PrologTranslationError` raised when Prolog source contains `!/0` (cut)
2. `PrologTranslationError` raised for `(C -> T ; E)` (if-then-else) and bare `(C -> T)`
3. Clear error messages suggest pure alternatives (dif/2, once/1, reified ITE, indexing)
4. reverse direction: Clausal's reified `THEN if COND else ELSE` is also rejected
   when translating to Prolog, since it cannot be faithfully represented as `(C -> T ; E)`

### Scryer Prolog Embedding — DONE

For programs that need full ISO conformance rather than the translation-based compatibility described above, Clausal now embeds Scryer Prolog in-process via PyO3. `.clausal` files can be loaded directly into the embedded engine, which translates them to Prolog automatically and executes with lazy iteration over solutions. This provides a complementary path: instead of translating Prolog *into* Clausal's native engine, run it on a real ISO Prolog engine from within Python. See [Scryer Prolog Embedding](scryer.md).
