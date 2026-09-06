# Atoms as arity-0 cells; plain `str` is a string — design

**Date:** 2026-09-06
**Todo:** `todo/strings-lost-in-the-atom-pivot-double-quotes-are-char-lists-2026-09-06.md`
(rulings R-S1, R-S2, R-S3′, R-S4)
**Design note:** `implementation_plans/strings-representation-options-2026-09-06.md`
(Options A–D compared; D ruled 2026-09-06)
**Prior spec:** `implementation_plans/tagged-tuple-term-representation.md`
§1/§1b (the cell representation this design completes)
**Census (file:line evidence for every claim below):** three read-only
sweeps of the tree at `bec5ab4f`, 2026-09-06 — unifier/order/list machinery,
atom minting/consumption, boundaries/writers/reader. Where this document
says "today", it means that tree.

## 1. Problem

The P3-1 pivot made an atom *be* its spelling: a plain Python `str`. That
retired strings. `"hello"` is the atom `hello`; `"hello" = [h,e,l,l,o]` fails;
foreign text (a file line, a JSON value, an environment variable) arrives as
an atom; `'foo'` and `"foo"` are the same term; a JSON object round-trips its
string values as atoms and its atom values as strings.

ISO Prolog — Scryer in particular, the reference this project tracks (R-S1)
— has both: an atom is an atomic constant with a spelling; a double-quoted
literal is a list of one-character atoms. The two never unify. The chars
family (`atom_chars/2`, `atom_length/2`, …) works on atoms and raises
`type_error(atom, …)` on anything else; the list family (`append/3`,
`length/2`, `nth0/3`, …) works on strings because they are lists.

The operator ruled the representation on 2026-09-06 (R-S3′, "Option D"):

> An atom is an arity-0 cell `("bar",)` — the same shape P3-2 gave every
> compound at arity 0. Functor slot 0 stays the plain spelling. A plain
> `str` anywhere a term can be is a string. `foo(bar, "baz")` is
> `("foo", ("bar",), "baz")`.

This document is the design of that flip: the term model, every rule that
follows from it, the boundaries it crosses, how it lands without a red
window, and what is deliberately left out.

## 2. Rulings of record (binding; not re-litigated here)

| Ruling | Statement |
|---|---|
| **R-S1** | Scryer semantics. `"hello"` unifies with `[h,e,l,l,o]`; chars are atoms; strings and atoms never unify. |
| **R-S2** | No materialisation. A string is stored as a `str` (or `SegString` while partial); it is never expanded to a list of char cells unless a caller asks for the list shape. Storage is an implementation freedom; the *term* is the char list. |
| **R-S3′** | Atom = 1-tuple cell `("bar",)`; plain `str` = string; slot 0 of any cell stays the plain spelling. Supersedes R-S3's C0-tag mechanism. |
| **R-S4** | `-double_quotes/1` is a **ratchet**, not a flag: `atom` keeps today's meaning for a module that declares it, `chars` is the destination, and the directive is deleted from the engine (its use pinned as a load error) once the last module drops it. |
| **Bridge-entry ruling** (`cells.py:41–53`) | Functor comparison is *equality*, never identity. Extended here to atoms: no `is`-pin on an atom survives this design. |
| **ISO functor rule** | A double-quoted string is never a functor. `"foo"(1)` is a syntax error under every `double_quotes` mode; no runtime path places a string in slot 0. |
| **Migration policy** | The engine flip does not reach the canonical repo before every downstream module carries `-double_quotes(atom)`; the default flips to `chars` only after that; the directive is deleted only after every module has dropped it. |

Standing preferences applied throughout: design questions are recorded in
§14 and a todo, not asked; "Task N" is written in full.

## 3. Goals

1. One term model: an atom is a cell, so every cell-aware path (`do_unify`,
   the funnel accessors, `head_key`, `arg_index`, `copy_term`, `ground`,
   `call/N`, `solve`) handles atoms with **no new arm**. The census confirms
   `("bar",)` already compiles, solves, indexes as `("bar", 0)`, and answers
   `functor/3` correctly.
2. Strings exist again, with Scryer semantics, stored compactly (R-S2).
3. Every builtin that reads or writes the **name position** of a term
   (§6.4) speaks atoms, never bare spellings, in both directions.
4. A ratchet path that keeps the engine suite green at every commit and lets
   downstream modules migrate one at a time (§10).
5. Loud leaks: an atom that escapes to Python code that expected text
   raises (`getattr`, `%s`, `re`, `"".join`), it never silently succeeds.

## 4. Non-goals

- **The ISO translator's outbound emit** (`clausal/tools/clausal_to_prolog.py`,
  `_convert_constant` :715–727 maps every `str` to `PString`). The translator
  lane owns it (todo item J); §9.6 records the interface it must meet.
- **Downstream module migration** (todo item K): inserting
  `-double_quotes(atom)`, then dropping it domain by domain. Downstream lanes
  own it; §11 is the announcement they receive.
- **The surface (Phase 3) parser.** It is user-owned and already emits the
  right shapes on the toklex path (`prolog_reader.py:155–172`: `PAtom →`
  name, `PString →` char list). §9.7 updates that contract; nothing else.
- **A `compare/3` / `@</2` / `keysort/2` / `predsort/3` family.** None exists
  today (`prolog_to_clausal.py:696–716` rejects them). This design fixes the
  standard-order *key* because the flip forces it; adding the predicates is
  a separate todo.
- **Zero-arity predicate classes used as values.** A `PredicateMeta` with no
  fields still reaches value position in places (`head_key` :1274 "the class
  IS the atom", `_standard_order_key` :593, `chars._atom_to_str` :63). Every
  site that accepts one today keeps accepting it with spelling `__name__`;
  nothing new is added for them. They are outside the term model.
- **`[]` as an ISO atom.** `[]` stays a Python list; `atom([])` and
  `atomic([])` keep today's answers (false). Parked in §14.
- **Numbers, bools, `None`, bytes, `Undefined`, `TUPLE_TAG` cells, dicts,
  sets, `Quantity`.** Unchanged.
- **SWI-Prolog compatibility.** Not a target (operator, 2026-09-06): no
  distinct `foo()` term, no SWI string type, no SWI-only builtins. The
  references are ISO, Scryer and Trealla.
- **Operator-aware printing.** `writeq(1+2)` prints `+(1, 2)` as `term_str`
  does today.

## 5. The term model

### 5.1 Shapes

| Term | Representation | Notes |
|---|---|---|
| atom `bar` | `("bar",)` | slot 0 is an interned `str` |
| compound `foo(bar, 1)` | `("foo", ("bar",), 1)` | unchanged shape; atom argument is now a cell |
| string `"abc"` | `"abc"` (`str`) or a `SegString` while partial | denotes the list `[("a",), ("b",), ("c",)]` |
| empty string `""` | `""` | denotes `[]`; `"" = []` is true |
| char `a` | `("a",)` | an ordinary atom of length 1 |
| codes `b"ab"` | `b"ab"` | unchanged (`bytes`-as-lists, the codes model) |
| Python tuple data `("bar",)` | `("bar",)` | **the same term as the atom** — THE DISCIPLINE (`cells.py:53–64`, pinned by `tests/test_funnel_accessors.py::TestCellFunnelAwareness`) |
| `foo()` | — | **not a term form.** ISO, Scryer and Trealla have no zero-arity compound; `foo()` is a syntax error on the surface reader. On the Python surface `foo()` is only the 0-arity *predicate* call/head shape (`halt_in_callee()`), a procedure; the atom `("foo",)` is what names that procedure through `call/1`. Inside a `++` escape `foo()` is ordinary Python. (Operator, 2026-09-06: SWI's distinct `foo()` term is not a target.) |

The discipline is unchanged and is what makes D free: a non-empty tuple
whose slot 0 is a `str` is a cell by shape, full stop, and a 1-tuple is the
arity-0 case. There is no atom "tag", no atom class, no registry a term must
be in to count.

### 5.2 Identity and interning

Equality is the semantics; identity is an optimisation.

- `clausal/logic/atoms.py` gains the public atom API (§6.1). `mint(spelling)`
  returns the canonical cell for that spelling from a process-wide table,
  with the spelling `sys.intern`ed. Two equal atoms compare equal by tuple
  `==`, which on interned slot-0 strings is an identity hit per element
  (measured 21.7 ns canonical vs 29.5 ns distinct-but-equal; F7 of the
  design note).
- The compiler is free to emit atom **constants** (`("bar",)` folds into
  `co_consts`; verified `compile('x=("bar",)').co_consts == (('bar',), …)`,
  marshal-clean). A constant unmarshalled from a `.pyc` is *not* the minted
  instance; that is fine because nothing may depend on identity.
- Every `is`-pin on an atom is retired: `import_hook.py:128–132`
  (`leaked_pool_atom`), `compiler_v2.py:1433–1436`, the `setdefault` sharing
  at `compiler_v2.py:1494` and `import_hook.py:147/166` (purpose stated at
  `compiler_v2.py:1489–1493` as identity), and `global_atom/2` guard mode
  (`inspection.py:540`). Each becomes `==`. The `predicate_builtins` atom
  pool keeps existing as the strict-atoms **vocabulary** (a set of declared
  spellings mapped to minted atoms); its identity-sharing rationale is
  deleted with the pins.
- Hot dict keys (`DictTerm` data, `$intern_atom` results, the pool) use
  `mint()` so the fast path is hit; nothing is incorrect if it is not.
- Threads and subinterpreters: the mint table is a plain dict updated with
  `setdefault` (atomic under the GIL and under free-threading); equality
  semantics make a per-interpreter table correct without coordination.

### 5.3 `-hide` mangling

A hidden atom is `("m\x1fbar",)`. `mangle` still produces the spelling;
`is_mangled`/`demangle`/`demangle_for_display` gain the one-line unwrap so
they accept the atom as well as the spelling. Nothing else changes; the
`atom_chars/2` forgery route stays documented out-of-warranty (`atoms.py:36–41`).

### 5.4 Efficient representations, always (R-S2 corollary; operator 2026-09-06)

`'.'/2` is how a list *looks* through `functor/3`, `arg/3`, `=..` and
`write_canonical/1` — never how one is *stored*. No runtime path
constructs a `(".", H, T)` cell:

- A proper list is a Python `list`; a string is a `str`; a partial list
  (`[H | T]` with an unbound tail) is the engine's existing `SegList`
  (`SegString` for a partial string). These are the only list shapes the
  runtime holds.
- Construction through the name position builds those shapes:
  `T =.. ['.', a, []]` → `T = [a]`; `T =.. ['.', a, "bc"]` → `T = "abc"`
  (a char atom consed onto a string stays a string); `T =.. ['.', 1, [2]]`
  → `T = [1, 2]`; `functor(T, '.', 2)` → `T = [_ | _]` (a `SegList` with a
  fresh head and an unbound tail); `T =.. ['.', a, X]` with `X` unbound →
  the same partial-list shape with head `a`.
- Decomposition answers virtually: `arg(2, "hello", T)` → `T = "ello"` is a
  `str` slice; `arg(2, [1, 2, 3], T)` → `[2, 3]` is a list slice. Nothing
  is expanded.
- A `(".", H, T)` cell handed in from Python is just a cell whose functor
  is spelled `.` — it is not a list, does not unify with one, and gets no
  special treatment. The one producer of such cells in the tree is the
  toklex reader's IR for `[H | Tail]` (`prolog_reader._cons_cell`, the
  locked §1c contract), which the Phase 3 compiler lowers before any term
  reaches the runtime.

## 6. Semantics

### 6.1 Public atom API (`clausal/logic/atoms.py`)

```python
def mint(spelling: str) -> tuple[str]      # canonical atom for a spelling
def is_atom(term) -> bool                  # type(term) is tuple and len 1 and type(term[0]) is str
def spelling(atom) -> str                  # atom[0]; TypeError if not an atom
def char_atom(ch: str) -> tuple[str]       # mint for a 1-char spelling; cached table, used by the unifier
```

- `predicate.make_atom(name)` returns `mint(name)` (API continuity, as its
  docstring already promises).
- `predicate.is_atom_value(x)` delegates to `atoms.is_atom` (plus the
  zero-field-class exception of §4). `predicate.is_atom` — which today tests
  "zero-field `PredicateMeta` class" (`predicate.py:1472–1474`) — is renamed
  to say so; the name `is_atom` means the term test from now on.
- `$intern_atom` (`import_hook._make_intern_atom` :70–168) returns `mint(name)`.
- `chars._atom_to_str` (`chars.py:48–72`) becomes the funnel for "read an
  atom's spelling in a builtin": accepts an atom (and the §4 class case);
  **no longer accepts `str` or `SegString`** — those are strings now and the
  caller raises `type_error(atom, …)`.
- Plan 0 (§10) ships this API **before** the flip with `mint` returning
  today's representation, so downstream code written against
  `mint`/`is_atom`/`spelling` is representation-agnostic and survives the
  flip unchanged.

### 6.2 Unification (`_variables.c do_unify`, the only implementation — no Python twin)

| Left | Right | Result |
|---|---|---|
| `("a",)` | `("a",)` | succeeds (existing tuple×tuple arm :1118–1131, length then element-wise) |
| `("a",)` | `"a"` | **fails** (existing mixed guard :1310–1312) |
| `("a",)` | `("a", 1)` | fails (length) |
| `"abc"` | `"abc"` | succeeds (`==` :1314) |
| `"abc"` | `[X, Y, Z]` | `X = ("a",)`, `Y = ("b",)`, `Z = ("c",)` — **reinstated str↔list arm** (retired at :1168–1179), written on the pattern of the bytes↔list arms :1188–1258: Var element → bind to `char_atom(c)`; element already a char atom → compare spelling, no allocation; anything else → fail |
| `"abc"` | `[("a",), ("b",), ("c",)]` | succeeds |
| `""` | `[]` | succeeds |
| `"abc"` | `[H \| T]` (head/body list unify) | `H = ("a",)`, `T = "bc"` — the tail stays a `str` slice (R-S2), as `_list_unify.c` star handling already does for `str` today |
| `"a"` | `("a",)` | **fails** — `"a"` is the list `[("a",)]`, not the char |
| `1` | `1.0` | succeeds (no numeric arm today; unchanged, out of scope) |

Consequences pinned:

- `_list_unify.c` / `runtime/list_unify.py` (twins): `seq_getitem` on a
  `str` yields `char_atom(c)` instead of a 1-char `str`; the four
  "list is really a string" promotions (`_seg_helpers.maybe_promote_to_str`,
  `_list_unify.c:111–137`, `lists._seq_result` :126–143,
  `_lists_core.make_seq_result` :66–80) test "every element is a char atom".
  The P3-1 `star_was_str` anti-back-door gate (:366–372, :696–707) and its
  Python twin (`list_unify.py:185–195`) are deleted: the hazard they guarded
  (two 1-char atoms coalescing into a str) cannot occur when chars are
  cells.
- A list of 1-char **strings** `["a", "b"]` is `[[("a",)], [("b",)]]` — two
  strings, not a string. No promotion applies.
- `SegString` (`terms.py:1002–1324`) keeps `str | VarSeg` segments. Its
  `__walk__` list acceptance (:1064–1087) takes a list of char atoms (or a
  `str`) and joins spellings; its `__unify__` list arm (:1182) and `__eq__`
  list arm (:1301–1309) compare against char atoms. A ground `SegString`
  walks to a `str` and is a string everywhere a `str` is.
- `SegBytes`, bytes↔list arms: unchanged.
- The stale comment at `compiler/head_match.py:357–366` (str head literal
  honours str↔char-list) becomes true again *for string literals*; it is
  rewritten to say which literals it applies to under §7.

### 6.3 Type checks (`builtins/type_checks.py`)

| Predicate | `("bar",)` | `"bar"` | `""` / `[]` | `("f", 1)` | number |
|---|---|---|---|---|---|
| `atom/1` | true | **false** | false | false | false |
| `string/1`, `is_str/1` | false | true (`str` or ground `SegString`) | true | false | false |
| `atomic/1` | **true** | false (it is a list) | false (today's answer, §4) | false | true |
| `compound/1` | false (arity 0) | false (a list is not compound today; unchanged) | false | true | false |
| `callable/1` | true | **false** | false | true | false |
| `is_list/1` | false | true | true | false | false |
| `is_chars/1` | false | true | true | false | false |
| `ground/1` | true | true | true | per args | true |

`must_be/2`, `can_be/2`: the Type argument is an atom (it arrives as
`("atom",)` from source); `_check_type` reads its spelling. The
`"atom"/"string"/"str"` single entry (:348–353) splits: `atom` → `is_atom`;
`string`/`str` → string test; `compound` gains the cell branch it lacks
(:373–380); `callable` follows the table above.

### 6.4 The name position — atoms in, atoms out

Everything that decomposes or constructs a term by name speaks **atoms**
for the name and **spellings** only internally (slot 0). The census shows
today's builtins hand back the bare spelling and construct a `Compound` or
a bare `str`; after this design they are cells end to end.

| Builtin | Rule |
|---|---|
| `functor(T, N, A)`, T bound | `N` is `mint(slot0)` for a cell; the atom itself for an atom; `N = T, A = 0` for a number/bool/`None`; for a list `N = ("[]",)`, `A = 0` (empty) or `N = (".",)`, `A = 2` — the funnel's answers today, now as atoms — and for a string the same as for the list it denotes (today `_arity("ab")` is 0 because a `str` is an atom; it becomes 2). |
| `functor(T, N, A)`, T unbound | `N` an atom, `A = 0` → `T = N`. `N` an atom, `A > 0` → the cell `(spelling(N), V1, …, VA)`. `N` a number and `A = 0` → `T = N`. `N` a **string** → `type_error(atomic, N)` (ISO 8.5.1.3 e: a string is a compound). `N` a number, `A > 0` → `type_error(atom, N)`. Today's construction returns a bare `str` (:294–295) or a `Compound` (`_construct_named` :270); both are replaced. |
| `T =.. L` (`unpack/2`), T bound | `L = [mint(slot0) \| args]` for a cell; `[atom]` for an atom; `[T]` for atomic. |
| `T =.. L`, T unbound | `[N]` with `N` atomic → `T = N`; `[N \| Args]`, `N` an atom → the cell; `[S]` or `[S \| Args]` with `S` a string → `type_error(atomic, S)` / `type_error(atom, S)` respectively; `[N \| Args]` with `N` a number and `Args ≠ []` → `type_error(atom, N)`. |
| `arg/3` | unchanged (arguments are terms). |
| `'.'`/2 in name position | builds the engine list shape, never a cell — §5.4. |
| `call(G, A1, …)` | `G` an atom → `(spelling(G), A1, …)`; `G` a cell → fold; `G` a **string** → `type_error(callable, G)`. `_resolve_named_goal`'s plain-`str` branch (`higher_order.py:123–126`) is deleted, as are the `str`→`(s,)` wraps at `solve.py:211–219` and `cells.py:453–454`: a `str` goal is a string and raises. `_ZERO_ARITY_CONTROL_GOALS` keys stay spellings (they are read from slot 0). |
| `listing/1` | accepts an atom (name), `name/arity`, an imported predicate; a string → `type_error(predicate_indicator, …)` — the `isinstance(val, str)` branch at `io.py:388` becomes the atom branch. |
| `abolish_table/2`, `global_atom/2`, `gensym/2`, `char_type/2` (Type), `resolve_module` designator, `(":", M, G)` | name/type/prefix arguments are atoms read by spelling; a string raises `type_error(atom, …)`. `global_atom/2` mints with `mint`; its guard mode compares with `==`. `resolve_module` keeps accepting a Python `str` from the **Python** API (`solve(goal, module="pkg.mod")`) — that is a Python argument, not a term. |
| Exception terms (`logic/exceptions.py` :137–236) | `error(type_error(atom, X), Context)` is the cell `("error", ("type_error", ("atom",), X), Context)`: the formal term and its type/domain/operation names are atoms; `Context` is a **string** (it is human text). Every `catch/3` pattern written in source already compiles to that cell shape. |
| Compiler-side name consumers (`PredRow.key`, `head_key`, `$disp_…`, `_arg_to_index_key`'s cell branch, `KWTerm` field names, `LoadAttr` attrs) | consume slot-0 / identifier **spellings**, which stay `str`. Unchanged. |

### 6.5 Standard order (`builtins/_helpers.py:497–624`)

Today lists **and tuples** share `_ORD_SEQ` (:597), so a cell orders as a
sequence next to the list of its elements and `("bar",)` keys identically to
`["bar"]`. Fixed here, arity-first as ISO 7.2:

```
Var 0 < Number 1 < Atom 2 < Bytes 3 < Sequence 4 < Compound 5 < Dict 6 < Set 7 < Other 8

atom       → (2, spelling)                       # ("bar",) keys like today's "bar"
string     → (4, ((2,"a"), (2,"b"), …))          # the key of the char list it denotes
list       → (4, (key(e) …))                     # unchanged
cell f(a…) → (5, arity, (0, f), _CF_POSITIONAL, (key(a) …))   # NEW: was (4, …)
TUPLE_TAG  → (5, arity, (1, ""), _CF_POSITIONAL, …)
```

`"ab"` and `[("a",), ("b",)]` have equal keys. `sort/2` dedups by **key
equality** (today `==`, :519–522), so the string and its char list collapse
to one element, the first occurrence surviving; `msort/2` keeps both.
Consumers unchanged: `sort/2`, `msort/2`, `sort_by/max_by/min_by`, `setof`.

### 6.6 The chars family (`builtins/chars.py`)

Inputs in atom position go through `_atom_to_str` (§6.1); outputs mint.

| Call | Result |
|---|---|
| `atom_chars(("ab",), L)` | `L = [("a",), ("b",)]`; `L = "ab"` also succeeds (same term) |
| `atom_chars(A, "ab")` / `atom_chars(A, [("a",),("b",)])` | `A = ("ab",)` |
| `atom_chars("ab", L)` | `type_error(atom, "ab")` |
| `atom_codes(("ab",), C)` | `C = b"ab"` (codes model, unchanged shape) |
| `atom_length(("abc",), N)` | `N = 3`; `atom_length("abc", N)` → `type_error(atom, "abc")` |
| `atom_concat(("a",), ("b",), X)` | `X = ("ab",)`; split modes enumerate atoms; numbers accepted as ISO allows |
| `sub_atom(("abc",), B, L, A, S)` | `S` atoms |
| `upcase_atom/2`, `downcase_atom/2` | atom → atom |
| `char_code(("a",), C)` | `C = 97`; `char_code("a", C)` → `type_error(character, "a")` |
| `char_type(("a",), alpha)` | Char is a char atom; Type atom |
| `number_chars(N, "12")`, `number_chars(N, [("1",),("2",)])` | `N = 12` (both spell the same list); `number_chars(12, L)` → `L = [("1",), ("2",)]` |
| `number_codes/2` | unchanged |

`length/2`, `append/3`, `nth0/3`, `member/2`, `reverse/2`, `msort/2`, … work
on strings because they are lists: `append("ab", "cd", X)` → `X = "abcd"`
(promotion keeps it compact); `nth0(0, "abc", C)` → `C = ("a",)`;
`member("a", "abc")` fails (a 1-char string is not a char).

### 6.7 Writers

Three writers, as ISO/Scryer: `write/1` (and `writeln/1`,
`write_to_string/2` — the text family), `writeq/1` (quoted,
`double_quotes`-aware; `print_term/1`, `term_to_string/2` and `term_str`
are this family — they exist to show structure, as they do today), and
`write_canonical/1`
(quoted, ignores operators AND the `double_quotes` flag: every list — a
string included — prints as the `'.'/2` structure it denotes). Scryer,
verified by the operator 2026-09-06:
`write_canonical("hello")` → `'.'(h,'.'(e,'.'(l,'.'(l,'.'(o,[])))))`.
The representation stays a `str` (R-S2); the writer makes it *look like*
the cons structure, exactly as the funnel already answers
`functor("hello", '.', 2)` and `arg(2, "hello", "ello")` (§6.4).

| Term | `write` / `term_str(quoted=False)` | `writeq` / `print_term` / `term_str` | `write_canonical` |
|---|---|---|---|
| `("foo",)` | `foo` | `foo` | `foo` |
| `("foo bar",)` | `foo bar` | `'foo bar'` (ISO 6.4.2 quoting: bare iff a solo, graphic, or lowercase-initial identifier token) | `'foo bar'` |
| `("m\x1fbar",)` | `m.bar` (demangled display, as today) | `m.bar` | `m.bar` |
| `"abc"` | `abc` | `"abc"` | `'.'(a,'.'(b,'.'(c,[])))` |
| `[("a",), ("b",)]` | `ab` | `"ab"` — a list of chars *is* a string (Scryer prints it so) | `'.'(a,'.'(b,[]))` |
| `[1, 2]` | `[1, 2]` | `[1, 2]` | `'.'(1,'.'(2,[]))` |
| `""` / `[]` | `[]` | `[]` | `[]` |
| `("foo", ("bar",), "baz")` | `foo(bar, baz)` | `foo(bar, "baz")` | `foo(bar,'.'(b,'.'(a,'.'(z,[]))))` |
| `("+", 1, 2)` | `+(1, 2)` | `+(1, 2)` | `+(1,2)` |
| unbound `Var` | as today (`_N`) | as today | `_N` |
| `b"ab"` | as today | as today | as today (codes model, out of scope) |

Rules:

- `write_canonical/1` prints no space after commas and no operator forms
  (`f(a,b)`, `'.'(1,[])`) so its output is byte-comparable with Scryer's;
  `write/1` and `writeq/1` keep the engine's display spacing (`f(a, b)`),
  which existing tests pin. A partial list `[h, e | T]` prints as
  `'.'(h,'.'(e,_N))`; a `SegString`/`SegList` is walked first and printed as
  what it walks to.
- The cell branch of every renderer (`terms.py` `term_str` :2400–2424,
  `term_pformat` :2571–2584, `term_html` :2721–2730; `io._format_term_for_io`
  :20–47, `io._format_clause_term` :135–160; `reflection._ClauseRenderer.term`
  :563–613) gains the arity-0 case: today all six print `flag()`.
- The `str` branch of each renderer becomes the string branch; the colour
  role `'string'` finally means string, `'atom'` means atom.
- `reflection.Atom` (`reflection.py:99`) and
  `testing._atomize_declared_atoms` (`testing.py:1517–1545`) — the heuristic
  that guessed which `str`s were atoms so they would print unquoted — are
  retired; the shape says so now.
- The reified-source renderer emits an atom as a bare name when it is a
  declared identifier, else as `'…'`; a string as `"…"`; and the module it
  writes carries `-double_quotes(chars)` while the engine default is still
  `atom` (§7), so its output re-reads as the terms it rendered.

### 6.8 Dicts and sets

`DictTerm` keys are compared by Python equality (`terms.py:1674–1682`,
`__unify__` :1701–1727). Atom keys are cells (`{foo: 1}` compiles its key
through `$intern_atom` → `mint("foo")`); string keys are `str`; the two are
distinct, which makes `docs/dicts_sets.md:154–156` true for the first time.
Dot access `D.foo` looks up `("foo",)`. A Python-side dict literal
`{"k": 1}` has a string key.

### 6.9 Indexing (`compiler/arg_index.py`)

Atoms move from the scalar branch (:100) to the cell branch (:102–105)
unchanged in code and key `("bar", 0)` at compile time and run time alike.
Strings are **not indexable**: `str` leaves `_INDEXABLE_TYPES` and a string
head argument keys `_INDEX_VAR`, exactly as a list head does, because a
string head and a char-list head are the same term and must land in the
same (full-scan) bucket. `[]`, `""` and `b""` are checked to key
consistently with each other. The R8 rationale comment (:79–86) is
rewritten. Perf consequence: a fact table keyed by string first arguments
loses first-argument indexing — that is the intended pressure to write
atoms as atoms.

## 7. Literals in `.clausal` source

The Python-surface compiler sees `ast.Constant` with the quote character
erased (`term_rewriting.py:1585–1588 visit_Constant` is a no-op; the only
tokenize-based quote recovery in the tree is `fmt/emit.py:320–343`, which is
the precedent). Rules:

| Source | Meaning |
|---|---|
| bare `foo` | atom (existing `visit_Name` path :1920–1921, now emitting `("foo",)`) |
| `'foo'` | **atom, always**, in every mode |
| `"foo"` | per the module's `double_quotes` mode: `atom` → `("foo",)`; `chars` → `"foo"` |
| `b"…"`, `b'…'` | codes (`bytes`), unchanged; quote style irrelevant |
| `f"…"` | a thunk (Python text) → a **string** result, §9.1 |
| `'+'(a, b)`, `'foo'(1)` | functor sugar (the existing rewrite at :1435–1440), kept for the single-quoted spelling |
| `"foo"(1)` | **`SyntaxError`** in every mode (ISO functor rule) |
| `"a" "b"` (implicit concatenation) | one literal; its mode is that of its first token; mixing `'` and `"` parts is a `SyntaxError` |
| `r"…"`, `u"…"`, `"""…"""` | the quote character after any prefix decides |
| module docstrings and other expression-statement literals | not terms; unchanged |

Mechanism: `EmbedTransformer` builds a `(lineno, col_offset) → quote-char`
map once per file with `tokenize.generate_tokens` over `source_lines`
(character columns; `ast.col_offset` is a UTF-8 **byte** offset — convert by
encoding the line prefix, the way `_is_arrow_adjacent` :218–261 already
reasons about bytes), threads it into every per-clause `TermTransformer`
through `_make_term_transformer` :4238–4259 (the funnel that already carries
`source_lines`), and `visit_Constant` consults it.

`-double_quotes(Mode)` (`_handle_double_quotes_directive` :4921–4959)
becomes a **file-scoped, position-sensitive** switch stored on the
`EmbedTransformer` instance (the `-allow_singletons` :3809 shape, not the
module-item shape, which is drained post-hoc and cannot govern only the
literals below it). `chars` is accepted from the flip commit on; `atom` is a
no-op while the default is `atom` and the opt-out after the default flips;
`codes` and anything else are refused (codes are spelled `b"…"`). The
directive is deleted, and its use pinned as a load error, at the end of the
ratchet (R-S4).

`.pl` files loaded through `PrologLoader` (`prolog_to_clausal.py`): a
`PString` is emitted as `"…"` and the generated module carries
`-double_quotes(chars)`; a quoted `PAtom` is emitted as `'…'`. Today
`:616` emits `repr(value)`, which re-reads as an atom.

## 8. Truth aliases

`true`, `false`, `undefined` are folded to Python `True`/`False`/`Undefined`
before the atom path (`_TRUTH_ALIASES` :379–385, four fold sites). Unchanged.
`call(("true",))`, `call(("fail",))` keep their control meaning through
`_ZERO_ARITY_CONTROL_GOALS` (spelling-keyed); they arise from `=..`, the
Prolog reader, or Python, never from source.

## 9. Boundaries

### 9.1 Python callees — one conversion, both directions

Today there are four independent term↔Python crossings: `_deep_deref`
(`modules/py/_helpers.py:42–71`, the `py.*` wrappers), the `PyThunk`
argument list (`terms_to_ast.py:1177–1205`, `++`/f-strings: single-level
`$deref`, no conversion), `_format_term_for_io`, and the JSON codec. After
this design there is one outbound helper, `to_python(term)`, used by the
`py.*` wrappers **and** the thunk argument path:

- atom → its spelling (`str`); string → `str` (a ground `SegString` walks
  first); cell → tuple with converted elements (as `_deep_deref` does today,
  tuples deliberately preserved for the reasons its docstring gives);
  `DictTerm` → `dict` (keys converted too: atom keys become `str` keys);
  list → list; everything else raw.
- Inbound stays raw `unify(result, out)`: a Python `str` **is a string**, a
  Python tuple whose slot 0 is a `str` is a cell, a `dict` is a `DictTerm` on
  the paths that convert it today.

So `X = bar, Y = ++X, X == Y` fails: the atom crossed out as text and came
back as a string. That is Scryer's rule (foreign text is a string, R-S3) and
it is loud. Programs that need an atom back use `atom_chars/2` or `mint`.

Perf: the thunk path gains a walk over its arguments. It is covered by the
interleaved A/B gate (§12); if it costs more than the bar on the benchmarks
that use `++`, the thunk path unwraps a **top-level** atom only and the
difference is documented — that fallback is the only alternative on the
table.

### 9.2 JSON (`modules/py/json.py`, the only JSON site)

- parse: object keys → atoms (`mint`); string values → strings; numbers,
  booleans, `null` as today.
- generate: atom → JSON string (its spelling); string → JSON string; a
  `DictTerm` with atom or string keys → object; cells → error
  (`type_error(json_term, …)`, not a stdlib `TypeError`).
- `json.parse/3` with `Options = [atoms(Spellings)]`: a string value whose
  text is in `Spellings` is minted as an atom. That is the whole vocabulary
  hook; profile-loader-style "atoms by vocabulary" is built on it downstream.

### 9.3 Module attributes and the bytecode cache

- `mod.bar` is `("bar",)`. The generated assignment
  (`_make_atom_str_assign_ast` :2656–2710) becomes `foo = $mint('foo')` so
  the module binding is the canonical instance.
- `CLAUSAL_BYTECODE_TAG` goes 8 → 9 (`import_hook.py:409`; the comment at
  :396–408 documents exactly this contract: a stale pre-flip `.pyc` would
  bind `foo = 'foo'`, a string, under the new runtime).
- Nothing is marshalled except the transformed AST; `terms_to_ast` output is
  generated at import time and never cached (:170–232), so no other cache
  invalidation is needed.

### 9.4 `py.*` wrapper contracts

Every wrapper that documents "returns an atom" for text (file lines, env
values, header names, regex groups, …) now returns a **string**; wrappers
that take a name (`os.getenv(Name, V)`, header names, …) accept an atom or
a string (both convert to the same `str`). Documented per wrapper in the
plan; no wrapper grows a mode flag.

### 9.5 Threads, subinterpreters, free-threading

Covered by §5.2: equality semantics, per-interpreter mint table, atomic
`setdefault`. No cross-interpreter sharing is required or attempted.

### 9.6 Interface to the ISO translator lane (out of scope, recorded)

Outbound, an atom must go through `_quote_atom` and a string through the
`PString` branch; `_convert_constant` (`clausal_to_prolog.py:715–727`) maps
every `str` to `PString` today and cannot tell the two apart on the raw
Python AST — the translator lane consumes the quote map of §7 (or the
compiled terms) to fix it. Inbound is handled in §7 (`.pl` loader).

### 9.7 Reader contract (`clausal/tools/prolog_reader.py:13–24`, locked §1c)

The two lines that change: `PAtom → mint(node.name)` (was the bare `str`),
`PString → node.value` as a `str` (was a list of 1-char strings). Functor
position is unaffected (`PCompound → (functor, *args)`, slot 0 a `str`).
The Phase 3 compiler that consumes ReaderItems is user-owned; the change is
announced in §11.

## 10. Sequencing — the ratchet

Every commit keeps the engine gate (§12) green. No representation flag: the
representation flips in one commit, made small by the widening before it.

**Plan 0 — the API, before the flip.** `atoms.mint/is_atom/spelling/
char_atom` exported with `mint` returning **today's** representation and
`is_atom`/`spelling` accepting it; `make_atom` delegates. Announced to
downstream lanes (§11) so Python-side code that builds or reads atoms can
become representation-agnostic first. Tiny; lands with, or right after, the
ratchet-directive acceptance already on this branch.

**Plan 1 — the flip.** Three stages, in one implementation plan:

- *Stage A — widen (green, additive, many independent tasks).* Every
  consumer accepts the 1-tuple atom **alongside** the `str` atom: `is_atom_value`,
  `atomic/1`, `callable/1` alignment, the standard-order key (§6.5 — the cell
  band fix lands here), the six renderers' arity-0 case (§6.7), the chars
  family's `_atom_to_str`, `functor/3`/`=..` constructing cells (§6.4),
  `listing/1`, `resolve_module`, `global_atom/2`, `gensym/2`, `must_be/2`,
  exception constructors, `is_mangled`/`demangle`, `_deep_deref`/`to_python`,
  JSON codec, `DictTerm` docs. Each task is testable with a `("foo",)` probe
  while the suite's `str` atoms keep working.
- *Stage B — flip (one task).* The compiler mints `("foo",)` (`visit_Name`,
  the `-module`/`-private`/`-hide` assigns, `$intern_atom`, `make_atom`,
  `mint`); `'…'` always atom, `"…"` per mode, `"foo"(1)` refused, quote map
  threaded; `-double_quotes(chars)` accepted; `str` stops being an atom
  (`is_atom_value` narrows, `chars._atom_to_str` rejects `str`, the plain-`str`
  goal wraps deleted); the `do_unify` str↔list arm and the `_list_unify.c`
  char-atom changes land; thunk arguments go through `to_python`;
  `CLAUSAL_BYTECODE_TAG` 8 → 9; the identity pins go; the suite's own
  atom-result assertions migrate (the census counts 672 `== "word"`
  comparisons across 144 files as the upper bound; only those asserting an
  atom result change, to `== mint("word")`); engine-internal `.clausal`
  fixtures that mean strings get `-double_quotes(chars)`.
- *Stage C — cleanup.* Delete dual-acceptance code left from Stage A that
  no longer has a `str` caller, rewrite `docs/syntax.md` §"Atoms vs strings"
  (:629–664, wrong since P3-2), `docs/strings_as_lists.md`,
  `docs/dicts_sets.md:154–156`, `docs/directives.md` `-double_quotes`,
  `docs/builtins.md` (chars family, new `writeq/1`, `write_canonical/1`),
  `docs/type_checking.md`, `docs/io.md`, `docs/python_integration.md`.

**Plan 2 — default becomes `chars`.** Precondition: downstream lanes report
every module carries `-double_quotes(atom)` (§11), and no in-repo module
relies on `"…"` meaning atom (a census task: each in-repo `"…"` literal that
means an atom is rewritten `'…'` or bare). Then the default constant flips
and `-double_quotes(atom)` becomes the opt-out. Small.

**Plan 3 — delete the directive.** After downstream lanes report every
module has dropped it: `-double_quotes/1` is removed and its use pinned as a
load error (R-S4). Tiny; owned by this lane, scheduled by the lanes' report.

## 11. Downstream announcement (contents; sent through the coordination channel)

1. Plan 0: `from clausal.logic.atoms import mint, is_atom, spelling` — write
   new Python-side atom handling against these; they survive the flip.
2. Plan 1 lands: `mod.bar` is `("bar",)`; a Python callee reached through
   `py.*` or `++` receives the spelling `str`; a Python `str` coming back is
   a string; JSON keys are atoms, values strings, `atoms(...)` option to
   mint; `'x'` is always an atom in `.clausal` source; `"x"` follows the
   module's `-double_quotes` mode (default still `atom`); `"foo"(1)` is a
   syntax error; the reader contract emits `mint(name)` for `PAtom` and a
   `str` for `PString`; `writeq/1` and `write_canonical/1` exist; tests that
   compared an atom result to a bare `str` compare to `mint(...)`.
3. Request: insert `-double_quotes(atom)` in every module (kit first, then
   the repos that consume it); report when a grep shows every module carries
   it. Plan 2 waits on that report.
4. After Plan 2: migrate domain by domain (drop the directive, write strings
   as `"…"`, atoms as bare names or `'…'`); report when none remain. Plan 3
   waits on that report.

The announcement names no downstream project, corpus domain, or battery
size (information barrier).

## 12. Gates

- **Suite:** the full engine suite's failing-name set is byte-identical to
  `.superpowers/sdd/p33-state-relocation/task-3-base-failed-names.txt` (145
  names) after every task, with the assertion migrations of Stage B counted
  as part of Stage B, not as new failures. A run must be shown to have
  executed before its diff is trusted.
- **Perf:** interleaved A/B against the pre-flip tree on the standard
  benchmarks (`bench_struct_tabling`, `bench_fib`, the list/string benches,
  and one `++`-heavy bench) under the 3% bar; the thunk-path walk of §9.1 is
  the one item expected to register and has its fallback stated there.
- **Round trip:** `T =.. L, T2 =.. L, T == T2` and
  `functor(T, N, A), functor(T2, N, A)` for atoms, cells, strings.
- **Boundary:** `.pyc` written by the pre-flip tree is rejected (tag);
  JSON parse→generate→parse fixed point on a document with atom keys and
  string values; `py.*` round trip returns strings.
- **Refusals:** `"foo"(1)`, `functor(T, "foo", 1)`, `T =.. ["foo", 1]`,
  `call("foo")`, `atom_length("abc", N)`, `-double_quotes(codes)`.

## 13. Acceptance rows

Beyond the Scryer table in the todo's §1 (which stands as written), the
following are pinned as tests in Plan 1:

| # | Goal | Expected |
|---|---|---|
| 1 | `atom(bar)`, `atom('bar')` | true |
| 2 | `atom("bar")` (chars mode) | false; `string("bar")` true; `is_list("bar")` true |
| 3 | `bar = 'bar'` | true; `bar = "bar"` false; `bar == ("bar",)` (from Python) true |
| 4 | `"abc" = [a, b, c]` | true |
| 5 | `"abc" = [H \| T]` | `H = a`, `T = "bc"`, `string(T)` true |
| 6 | `"" = []` | true; `"" == []` (standard order) equal keys |
| 7 | `functor(foo(a), N, A)` | `N = foo` (atom), `A = 1`; `atom(N)` true |
| 8 | `functor(T, foo, 2)` | `T = foo(_, _)`, a cell |
| 9 | `functor(T, "foo", 1)` | `type_error(atomic, "foo")` |
| 10 | `foo(a, "b") =.. L` | `L = [foo, a, "b"]`; `L = [foo, a, [b]]` also true |
| 11 | `T =.. [foo, 1]` | `T = foo(1)`, cell |
| 12 | `T =.. ["foo", 1]` | `type_error(atom, "foo")`; `T =.. ["foo"]` → `type_error(atomic, "foo")` |
| 13 | `call(foo, 1)` with `foo/1` defined | solves `foo(1)`; `call("foo")` → `type_error(callable, "foo")` |
| 14 | `atom_chars(A, "hi")` | `A = hi`; `atom_chars(hi, "hi")` true; `atom_chars("hi", _)` → `type_error(atom, "hi")` |
| 15 | `atom_length(hi, 2)` | true; `atom_length("hi", _)` → `type_error(atom, "hi")` |
| 16 | `msort([b, "a", 1, foo(x), [z]], L)` | `L = [1, b, "a", [z], foo(x)]` (atom < string/list < compound; `"a"` and `[z]` in the sequence band by element) |
| 17 | `sort(["ab", [a, b]], L)` | `L = ["ab"]` |
| 18 | `write(foo(bar, "baz"))` | `foo(bar, baz)`; `writeq` → `foo(bar, "baz")`; `writeq('a b')` → `'a b'`; `writeq([a, b])` → `"ab"` |
| 18b | `write_canonical("hello")` | `'.'(h,'.'(e,'.'(l,'.'(l,'.'(o,[])))))` (Scryer-verified); `write_canonical([1, 2])` → `'.'(1,'.'(2,[]))`; `write_canonical(foo(a, "b"))` → `foo(a,'.'(b,[]))`; `functor("hello", N, A)` → `N = '.'`, `A = 2`; `arg(2, "hello", T)` → `T = "ello"` |
| 18c | `T =.. ['.', a, "bc"]` | `T = "abc"`, `string(T)`; `T2 =.. ['.', 1, [2]]` → `T2 = [1, 2]` (Python list); `functor(T3, '.', 2)` → `T3 = [_ \| _]` (SegList); no `(".", H, T)` cell is ever built (§5.4) |
| 19 | `{foo: 1}.foo` | 1; `{"foo": 1}` (chars mode) has a string key; the two dicts do not unify |
| 20 | `json.parse("{\"k\": \"v\"}", D)` | `D = {k: "v"}` with `atom(k)`, `string(v)` |
| 21 | Python: `mod.bar == mint("bar")` | true; no test anywhere relies on `is` |
| 22 | `py.os.getenv(home, X)` (or any text-returning wrapper) | `string(X)` |
| 23 | `X = bar, Y = ++X` | `string(Y)`, `Y = "bar"`, `X \= Y` |
| 24 | `"foo"(1)` in source | `SyntaxError` naming the ISO functor rule |
| 25 | `'foo'(1)` in source | `foo(1)` |
| 26 | `-double_quotes(chars)` then `X = "ab"` | `string(X)`; same module with `atom` mode → `atom(X)` |
| 27 | `.pl` file `p("ab").` loaded | `p(X)` gives a string |
| 28 | reader: `transform_term(PAtom("hi"))` | `(("hi",), …)`; `PString("hi")` → `("hi", …)` |
| 29 | stale `.pyc` from tag 8 | recompiled, not loaded |
| 30 | `listing(foo)` | lists `foo/*`; `listing("foo")` → type error |

## 14. Parked questions (recorded, not asked; filed as a todo with the plan)

1. `[]` (and therefore `""`) as an ISO atom: `atom([])`, `atomic([])`,
   `T =.. [[]]`. Today false/false/type error; ISO says true/true/`T = []`.
   Decide with the ISO-compatibility program, not here.
2. `compare/3`, `@</2` family, `keysort/2`, `predsort/3`: absent; the key of
   §6.5 makes them a small addition.
3. `1 = 1.0` unifies (no numeric arm); ISO says no. Pre-existing.
4. Python `True` in goal position (`call(true)` from source folds to `True`).
   Pre-existing; unchanged here.
5. Thunk-path deep conversion cost (§9.1) — decided by the perf gate, with
   the fallback stated.
6. Whether `write_canonical/1` should ignore `-hide` demangling (print the
   raw spelling). This design prints the demangled display form in both
   families, matching today's writer guarantee; revisit if a re-read of
   `write_canonical` output must reproduce hidden atoms.
7. String first-argument indexing (§6.9) if a string-keyed fact table turns
   out to matter after migration: a "list of chars → str key" coalesce is
   possible but costs a walk per lookup.
8. **Memory-mapped strings** (operator, 2026-09-06, from a Scryer
   comparison): the string representation must be able to back a string
   with a memory-mapped file, as Scryer's partial strings can. R-S2 makes
   this a representation choice, not a term-model one. The extension
   point is the one `SegString` already uses — a string-like object that
   participates through `__unify__`/`__walk__`/the sequence protocol rather
   than by being a `str`; a `MappedString(mmap, encoding, start, end)` view
   that slices by offset without copying and decodes chars on demand is a
   third such representation. Python's `mmap` is a bytes-like buffer:
   for the codes model (`b"…"`) a mapped file is a code list once the
   bytes↔list arms accept any buffer object (`PyObject_CheckBuffer`, not
   `PyBytes_Check`); for the chars model the view decodes (byte offset =
   char offset for ASCII/Latin-1, a UTF-8 index otherwise). Binding on
   this plan: Task 11 introduces no new `type(x) is str` gate where a
   `SegString` is also accepted — every such site keeps routing through
   the walk/`normalize_seg_input` convention so a third string type slots
   in identically. The view itself is a later plan.

## 15. Risks

| Risk | Mitigation |
|---|---|
| The flip commit (Stage B) is large and cannot be split without a red window | Stage A moves everything additive out of it; Stage B is then minting + literal rule + `str`-demotion + tag + test migration, reviewed as one diff with the round-trip and refusal gates. |
| C twin drift (`_list_unify.c` / `list_unify.py`, `_lists_core.c` / `lists.py`) | Each pair changes in the same task; the existing parity tests run on both; `build_ext` before diffing failure sets. |
| A downstream module reads `mod.bar` as text and breaks loudly | Plan 0's API and the announcement precede the flip; the breakage is the designed loud leak, fixed with `spelling()`. |
| An in-repo `.clausal` fixture silently means "string" by `"…"` today | Plan 2's census task classifies every in-repo `"…"` before the default flips. |
| Identity pins hidden in out-of-tree wrappers | Announcement item 2; equality semantics are already the cell ruling. |
| `sort/2` dedup change (string vs char list) alters an existing answer | Only where a program mixes the two shapes, which is impossible today (strings do not exist). |
