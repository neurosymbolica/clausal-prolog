# Truth values as atoms: census, recommendation, prototype (2026-09-30)

Branch `proto/truth-values-as-atoms-2026-09-30`, worktree `/workspace/_d47`,
base 60f9921f.  Nothing lands from here without the operator's word.

## The ruling and its cost

`true`/`false`/`undefined` are the only spellings; the underlying objects are
Python `True`/`False`/`Undefined` for interop "unless there's a good reason".
The seam folds the spellings (`term_rewriting._TRUTH_ALIASES`), the native
`.pl` reader folds data-position occurrences (slice 4, `tools/iso_l3.py
_truth_value`).  The engine then treats the objects as what Python says they
are: a `bool` is an `int` (`True == 1`, `hash(True) == hash(1)`), and
`Undefined` is an opaque Python value.

Measured on BOTH front ends before any change (probe in the scratchpad,
`probe_truth.py`; Scryer column from
`/workspace/scryer-prolog-clpq/target/release/scryer-prolog`):

| case | engine (native = seam unless noted) | Scryer |
|---|---|---|
| `true = 1`, `false = 0`, `f(true) = f(1)`, `[true] = [1]` | succeed | fail |
| `true \= 1` | fail | succeed |
| `true == 1` | fail | fail (already right: `_numeric_types_agree` tags bool) |
| `atom(true)`, `atom(false)`, `atom(undefined)` | fail | succeed |
| `callable(true)` | native: existence_error callable/1 (unrelated); seam `callable_`: fail | succeed |
| `atomic(true)`, `number(true)`, `integer(true)` | yes / no / no | same |
| `atom_length(false, N)`, `atom_codes`, `sub_atom`, `atom_concat` | `type_error(atom, False)` | 5, codes, `t`, `truex` |
| `atom_chars(X, [t,r,u,e])` | `X = 'true'` (a **str**, not `True`; `X == true` then FAILS) | `true` |
| `functor(F, true, 1)`, `F =.. [true, x]` | `type_error(atom, True)` | `true(_)`, `true(x)` |
| `functor(true, N, A)`, `true =.. L` | `True-0`, `[True]` | `true-0`, `[true]` |
| `compare(O, true, a)` | `<` (number band) | `>` |
| `sort([true, false, undefined, a, z], L)` | `[False, True, a, z, Undefined]` | `[a, false, true, undefined, z]` |
| `sort([1, true, 0, false], L)` | `[0, False, 1, True]` | `[0, 1, false, true]` |
| `list_to_set([1, true, 0, false], L)` | `[1, 0]` (dedupes `true` with 1) | `[1, true, 0, false]` |
| `T = true, X is T + 1` | `X = 2` | `type_error(evaluable, true/0)` |
| `T = true, 1 < T` | native: `type_error(evaluable, True/0)`; seam: silent **fail** (CLP(FD) `$fd_lt`, `_eval_ground` keeps a bool "pending") | `type_error(evaluable, true/0)`; `1 #< true` is `domain_error(clpz_expression, true)` |
| `p(true). p(1). p(false). p(0). p(a).` then `p(true)` | **2 answers** (first-arg buckets keyed by the raw bool collide with the int's) | 1 |
| `member(true, [1])`, `memberchk(1, [true])` | succeed | fail |
| `write(true)`, `writeq(false)`, `write(undefined)` | `True`, `False`, `Undefined` | `true`, `false`, `undefined` |
| `length(L, true)`, `between(true, 3, X)`, `char_code(C, true)` | type_error(integer, ...) | same (already right) |
| tabling variant keys | already type-tag bools (A04-F006) | n/a |

## Census: every site that decides

The engine has no one place that says "is this an atom?".  Sites, by layer:

### Identity layer (the objects)
- `clausal/terms.py:2964` `_UndefinedType`: singleton, identity-`__eq__`, so
  `Undefined = Undefined` already holds and `Undefined = 1` already fails.
  No `__unify__`; renders as `Undefined`.
- `True`/`False`: CPython singletons, `int` subclass.  Identity fast path in
  `do_unify` (`t1 == t2`) handles `true = true`; the RichCompare fallback is
  what conflates `true = 1`.

### Unification (C, no Python twin exists: `VarAPI->unify` is the only unify)
- `clausal/logic/variables/_variables.c:1557` `do_unify` fallback
  `PyObject_RichCompareBool(t1, t2, Py_EQ)` — the `true = 1` site.
- `_variables.c:1448` and `:1486` bytes<->list arms: "A bool is a PyLong
  subclass (True==1) and matches by value" — `[true] = b"\x01"` succeeds.
- `clausal/logic/runtime/_list_unify.c:298` already excludes bools from the
  codes domain (`!PyLong_Check(e) || PyBool_Check(e)`).
- `_constraints_dif.c` (`_structural_unify_oc`) delegates to `VarAPI->unify_oc`;
  `_lists_core.c` (member/memberchk/append/select/permutation) delegates to
  `VarAPI->unify` — both follow whatever `do_unify` does.
- `clausal/logic/constraints.py:45` `structural_eq` (Python, `==`/dif/setof):
  atomic fast path `left == right` over `(bool, int, ...)` — `structural_eq(True, 1)`
  is True; `'=='/2` only gets the right answer because `_numeric_types_agree`
  tags bool separately (`iso_compare._numeric_tag`).

### Standard order of terms
- `clausal/logic/builtins/_helpers.py:704` `term_key`: bool keys in the
  NUMBER band (`_NUMERIC_RANK[bool] = 2`), `Undefined` in the OPAQUE band.
  Drives `compare/3`, `@<` family, `sort/2`, `msort/2`, `predsort`, `keysort`,
  `setof`.
- `clausal/logic/builtins/iso_compare.py:264` `_numeric_tag`: bool is a
  number kind.

### Type tests
- `clausal/logic/atoms.py:387` `is_atom` (`type(term) is str`), `:395`
  `spelling`; `predicate.py:2629` `is_atom_value` → the one `atom/1`
  definition `type_checks._is_atom_term`, also `callable_/1`,
  `must_be(atom, X)` (`_check_type`), `functor/3`/`=..` admission
  (`inspection.py:340,403,543`), `io.py` write options, `control.py:274`,
  `database_ops.py:784`, 68 `is_atom(` callers in all.
- `atoms.py:113` `is_mangled`: `is_atom(value) and HIDDEN_SEP in value[0]` —
  indexes the value; would raise `TypeError` on `True` once `is_atom` admits it.

### Atom builtins (`clausal/logic/builtins/chars.py`)
- Acceptance is `_term_is_atom(v)` + `spelling(v)` at lines 78, 183, 309,
  324, 345, 372, 418, 467, 532, 543, 548 — all route through the two
  `atoms.py` helpers, so they follow whatever those say.
- Construction is `mint("...")` at lines 218, 311, 326, 394, 438, 478, 485,
  492, 509, 618 (`atom_chars`, `atom_codes`, `atom_concat`, `sub_atom`,
  `upcase_atom`, `downcase_atom`, `char_type`) — mint returns the interned
  str, so a runtime-built `'true'` is NOT the `True` object.
- `_chars_core.c` holds no atom acceptance (only `char_type` tables).

### functor/3, =..
- `inspection.py:340` `_construct_named`: name must be `_term_is_atom`; builds
  `(spelling(name), *args)`.  `:403` / `:543` admit `bool` as ATOMIC (so
  `functor(T, true, 0)` gives `T = true` today) but the arity>0 arm raises
  `type_error(atom, True)`.
- Decomposition (`_helpers._functor_name`/`_arity`) returns the cell's slot-0
  str: `functor(true(x), N, _)` gives the str `'true'`.

### Arithmetic
- `clausal/logic/exact_arith.py:908` `evaluate`: a `bool` "passes through, to
  meet Python's operators" (`True + 1 = 2`).  `_is_term(True)` is False.
- `iso_compare.py:152` `_iso_eval` rejects a bool RESULT only; culprit is
  `_evaluable_culprit(True)` = `('/', True, 0)` (renders `True/0`).
- `clausal/logic/clpfd.py:1554` `_eval_ground`: bool → `None` ("keep
  pending") — the seam's `<`/`>`/`=<`/`>=` are CLP(FD) posts, so `1 < true`
  silently fails there.  `_clpfd_propagate.c:513,569` and
  `_arithmetic_core.c:61,70` already exclude bools.

### Indexing (first-argument and joint)
- `clausal/logic/compiler/arg_index.py:49` `_INDEXABLE_TYPES = (int, float,
  bytes, bool, NoneType)`: a bool keys as ITSELF in `_arg_to_index_key`
  (:121), `_runtime_arg_key` (:342) and `_static_call_key` (:404) — the bucket
  dict conflates it with the int (`p(true)` reaches `p(1)`'s bucket and vice
  versa).  `Undefined` is unindexable (`_INDEX_VAR`, full scan).

### Rendering
- `clausal/terms.py:3295` `term_str`: `isinstance(t, bool): return str(t)` →
  `True`; `:3483` `term_canonical` likewise; `Undefined.__repr__` → `Undefined`.
  `io.py` `_format_term_iso` routes through `term_str`.  Reified renderer /
  `render_source` untested here.

### Dedup / membership by Python `==`
- `clausal/logic/builtins/lists.py:927` `list_to_set`: `x not in seen`.
- `clausal/logic/tabling.py:480` + `_tabling_core.c:91`: already type-tag
  bools (A04-F006) — nothing to do.
- `DictTerm` keys (`terms.py:1884`, `atoms.as_dict_key`): a Python dict, so
  `{true: a}` and `{1: a}` share a key.  RESIDUAL — needs a key wrapper
  like nil's `NIL_KEY`, with a reverse map on `items()`; not prototyped.

### Places that RELY on `True == 1` (engine code)
1. `_variables.c` bytes<->list arms (above) — deliberate, documented.
2. `arg_index._INDEXABLE_TYPES` — bool keyed raw, relies on hash equality
   with int only by accident (it is what makes the bucket collide).
3. `exact_arith.evaluate` — lets `bool` reach Python `+`.
4. `lists.list_to_set` — Python `in`.
5. `constraints.structural_eq` atomic fast path — Python `==`.
6. `lists.sum_list`/`max_list`/`min_list` — Python `sum`/`max` over elements
   (`sum_list([true], S)` gives 1; Scryer: not a library predicate).  NOT
   changed by the prototype.
7. `reif.py:39-90`, `coroutining.py:119`: `unify(t, True, trail)` — bind a
   reified truth to the OBJECT.  Correct under both readings (Scryer's reif
   binds the atoms `true`/`false`); unaffected.
8. `clpz_surface.unify_01(b, 0|1)`: CLP(Z) reification uses INTS 0/1, as
   Scryer's clpz does; unaffected.
- No engine Python passes `True` where an int 1 is meant (grep of `unify(`
  with a bool literal: 9 sites, all reif/coroutining truth flags).

### Tests that read the Python objects (why the objects must stay)
- 1025 assertion lines in 138 test files compare answers with `True`/`False`/
  `Undefined` (`== [True]`, `is True`, `is Undefined`...).  75 in-tree
  `.clausal`/`.seam` files mention the spellings.  Flipping the
  representation to the str atoms (option B below) would touch all of them
  and the whole Python boundary; the ruling is right that the objects stay.

### Tests that pin today's behaviour (change under the fix)
- `tests/test_terms.py:63,67,118,122` — `term_str(True) == "True"`.
- `tests/test_comparison_twin_parity.py:52` (`"bool,int", True, 1`) — parity
  case, both twins move together.
- `tests/test_rdiv_decimal_order_guard.py:120` (`("decimal", True, 1)` is
  not a number) — unchanged.
- `tests/iso_l3/test_l3_s4_constructs.py:377` D35 strict-xfails (6) — flip.
- The box gate is the real count (see the results section).

## Options

(a) FULL: the objects stay; ONE definition of "the truth atoms" in
`atoms.py` (`is_truth_atom`, `truth_spelling`, `TRUTH_ATOMS`), and every
deciding site above reads it: unify (C), structural_eq, term_key /
`_numeric_tag`, `is_atom`/`spelling`, functor/=.., `evaluate`/`_eval_ground`,
index keys, `term_str`/`term_canonical`, `list_to_set`, `mint`
(canonicalises the three spellings to the objects so a runtime-built atom IS
the truth value).  Residual: dict keys.
Cost: ~12 files, one C rebuild (`_variables.c`), the 4 `term_str` test lines.
Risk to seam programs: a seam program that relies on `true = 1` (or on
`p(true)` matching a `p(1)` clause, or on `X == true + 1`) changes answer.
Nothing in-tree does — the 75 files use the spellings as truth values — and
a program that did would be one no Prolog reading agrees with.

(b) SMALLER: unify + compare + arithmetic only.  Leaves `atom(true)` false,
the atom builtins raising, the buckets colliding and `write(true)` printing
`True`.  Cheaper by ~5 files, but the D35 xfails a1-a4 stay red and the
engine keeps two answers to "is `true` an atom?" (unify says yes, atom/1
says no).  Not recommended: the sites are all small and the inconsistency is
worse than the diff.

(c) DON'T FIX, document: keep the six D35 xfails as the pinned divergence.
Then `true = 1` succeeding, and first-arg buckets merging `p(true)`/`p(1)`,
stand as engine behaviour on BOTH front ends.  The bucket one is a silent
wrong-answer class (a rulebase with `status(true)`/`status(1)` clauses
returns both) and is the reason not to choose this.

RECOMMENDATION: (a), prototyped below.  The `mint` canonicalisation is a
separate commit so it can be dropped alone.

## Prototype: four commits on the branch (4bdca566, 8d5294f6, 224c37b2, 2b44990d)

Option (a), in one engine commit (the `mint` canonicalisation is the 5-line
hunk in `atoms.mint`; dropping it alone leaves `atom_chars(X, [t,r,u,e])`
answering the str `'true'` -- still the same atom to unify/==/compare, but
not the object a Python caller expects).

### Sites changed (12 engine files; two C extensions rebuilt)
| layer | file | change |
|---|---|---|
| the definition | `clausal/logic/atoms.py` | `TRUTH_SPELLINGS`, `is_truth_atom`, `truth_spelling`, `truth_atom`; `is_atom` admits the objects, `spelling` names them, `mint("true")` is `True`; `is_mangled` stops indexing the value |
| the object | `clausal/terms.py` | `Undefined` registers itself; `_UndefinedType.__unify__` answers the str spelling; `term_str`/`term_canonical` print the spelling |
| unify (C) | `clausal/logic/variables/_variables.c` do_unify | truth-atom arm before the RichCompare fallback; bytes<->list arms exclude bool elements. **`_variables.so` changed** |
| ==/2 | `clausal/logic/constraints.py` structural_eq | truth-atom rule before the atomic `==` path |
| standard order | `clausal/logic/builtins/_helpers.py` term_key, `_NUMERIC_RANK`; `iso_compare._numeric_tag` | atom band by spelling; bool is not a number kind; `_functor_name`/`_arity` name the atom |
| indexing | `clausal/logic/compiler/arg_index.py` | `_INDEXABLE_TYPES` drops bool; the three key functions key `(spelling, 0)`; `_is_deeply_ground` still counts a bool as ground |
| arithmetic | `clausal/logic/exact_arith.py` evaluate; `clausal/logic/clpfd.py` `_eval_ground` + both operand guards; `clausal/logic/_clpfd_propagate.c` ne fast path | `type_error(evaluable, true/0)` for is/2 and the ISO comparisons; `domain_error(clpz_expression, true)` for the CLP posts (the seam's `==`/`<`), Scryer's clpz answer. **`_clpfd_propagate.so` changed** |
| rendering | `clausal/logic/builtins/io.py` `_format_term_as_text`, `_format_term_iso` | the spelling at top level (the compound arm already went through term_str) |
| dedup | `clausal/logic/builtins/lists.py` list_to_set | by `==`/2 (also stops deduping 1 with 1.0, Scryer-consistent) |

### The test table (both front ends; before = 60f9921f, after = 4bdca566)
| case | before | after | Scryer |
|---|---|---|---|
| `true = 1` / `false = 0` / `f(true) = f(1)` / `[true] = [1]` | succeed | fail | fail |
| `true \= 1` | fail | ok | ok |
| `atom(true)`, `atom(false)`, `atom(undefined)` | fail | ok | ok |
| `atomic(true)` / `number(true)` / `integer(true)` | ok / fail / fail | same | same |
| `atom_length(false, N)` | type_error(atom, False) | 5 | 5 |
| `atom_codes(true, C)` | type_error | [116,114,117,101] | same |
| `atom_chars(X, [t,r,u,e])` | `'true'` (str) | `True`; `X == true` holds | true |
| `sub_atom(true, 0, 1, _, S)` / `atom_concat(true, x, X)` | type_error | t / truex | t / truex |
| `functor(F, true, 1), F = true(x)` / `F =.. [true, x]` | type_error(atom, True) | true(x) | true(x) |
| `functor(true, N, A)` / `true =.. L` | True-0 / [True] | same (the object) | true-0 / [true] |
| `functor(true(x), N, 1), N == true` | n/a (raised) | ok | ok |
| `compare(O, true, a)` | `<` | `>` | `>` |
| `compare(O, true, 1)` | `>` (by accident: bool ranked after int) | `>` | `>` |
| `true @< 1` / `1 @< true` | fail / ok | fail / ok | fail / ok |
| `sort([true, false, undefined, a, z], L)` | [false,true,a,z,undefined] | [a,false,true,undefined,z] | same |
| `sort([1, true, 0, false], L)` | [0,false,1,true] | [0,1,false,true] | same |
| `msort([true,1,a,false,undefined,1.5,f(x),[s]], L)` | [false,1,true,1.5,a,f(x),[s],undefined] | [1,1.5,a,false,true,undefined,f(x),[s]] | (no msort/2 in Scryer; ISO 7.2.1 order) |
| `list_to_set([1, true, 0, false], L)` | [1, 0] | [1,true,0,false] | (no list_to_set/2; ==/2 dedup) |
| `T = true, X is T + 1` | 2 | type_error(evaluable, true/0) | same |
| `T = true, T =:= 1` | type_error(evaluable, True/0) (renders `True`) | type_error(evaluable, true/0) | same |
| seam `T is true, X == T + 1` (a `#=` post) | 2 | domain_error(clpz_expression, true) | `X #= true`: same |
| seam `T is true, 1 < T` (ground `<`) | silent FAIL | type_error(orderable, true), as `1 < a` | `1 #< true`: domain_error(clpz_expression, true) (a clpz post; the seam's ground `<` is not one) |
| `p(true). p(1). p(false). p(0). p(a).` -> `p(true)`, `p(1)`, `p(0)`, `p(false)` | 2 answers each | 1 each | 1 each |
| `member(true, [1])` / `memberchk(1, [true])` | ok | fail | fail |
| `length(L, true)` | type_error(integer, True) | type_error(integer, true) | same |
| `write(true)`, `writeq(false)`, `write(undefined)`, `writeq(g(true,[false]))` | `True` `False` `Undefined` `g(true,[false])` | `true` `false` `undefined` `g(true,[false])` | same |
| Python reads back `atom_chars(X, ...)`, `true =.. L`, the sorted list | str / object / object | `True`, `True`, `Undefined` objects | n/a (the ruling) |

### Existing tests that moved (5 assertions, 6 xfails)
- `tests/test_terms.py` (4 lines): `term_str(True) == "true"`, `"false"`.
- `tests/test_first_arg_index.py::test_bool_key`: the key is `("true", 0)`.
- `tests/iso/test_iso_answers_scryer.py::test_length_bool_is_a_type_error`:
  the culprit renders `true`/`false` (Scryer's text).
- `tests/iso/test_iso_compare_scryer.py` representation table: the
  `(True, 1)` row is not even structurally equal now.
- `tests/iso_l3/test_l3_s4_constructs.py::test_d40_native`: the
  existence_error indicator walks as `('/', True, 2)` (the name IS the
  atom `true`, whose object is `True`; the str still unifies with it).
- The six D35 strict-xfails flipped to passing.
- New: `tests/test_truth_atoms_engine.py` (primitives) and
  `tests/iso_l3/test_l3_truth_atoms.py` (one program, both front ends, the
  Scryer column as data).

### Review round (roborev job 318, claude-code) and the second commit 8d5294f6
The review's High finding was REAL and measured: widening `is_atom` turned
every `spelling(x) if is_atom(x) else x` site that hands a term to Python
into a str converter -- `unwrap_atom(True)` gave `'true'` (a `++` escape or
f-string then received an always-truthy non-empty string), `to_python
(Undefined)` gave `'undefined'`, JSON `true` became the string `"true"`,
`z3.set_option/2` and the py.* wrappers' `to_text` likewise.  Census of the
idiom: 30 sites; 5 are boundaries (fixed through one helper,
`atoms.crossing_value`: a truth atom crosses as its OBJECT, any other atom
as its spelling), the other 25 read an option/type/order/name atom by its
spelling to compare with a keyword and are right as they are.  The two Low
findings were taken too: the tabling key normalisers (Python + C twin,
`_tabling_core.so` rebuilt) key a bool as its spelling so the object and
the str are one variant; the dead `or type(val) is bool` clause is gone.
The `test_ground_scalar` tabling row moves with it.  New test file:
`tests/test_truth_atoms_python_boundary.py`.

### Box gate d47-1 (4bdca566): 21 NEW, 1 GONE -- and the third commit 224c37b2
GONE: `audit_2026_05_25/test_class_C17_perf_memory.py::test_F026_...` (a
timing test; flake).  NEW, sorted:
- ONE real regression, 10 rows: the reif fixtures (`builtins_dif.clausal`
  `reified eq/dif true/false`, `reif_eq_test.clausal`, `docs/builtins_sig_
  tests.clausal`) write `TRUTH == True` -- the seam's `==` is a CLP(FD)
  post, and the first commit's operand guard rejected a bool BEFORE the
  both-ground early return.  Measured on the base engine, a plain atom in
  the seam's ground comparators gives `a == a` ok, `a == 1` fail, `a != 1`
  ok, `1 < a` type_error(orderable, a); the truth atom gave `true != 1`
  FAIL and `1 < true` silent FAIL (the `True == 1` leak).  Fix (commit 3):
  `_cells_as_nodes`, the normaliser every comparator runs, reads a truth
  atom as the str of its spelling, so it takes exactly the plain atom's
  path: `X == True` holds, `true != 1` holds, `1 < true` is the same
  type_error(orderable, true) as `1 < a`, a var beside one is the same
  domain_error(clpz_expression, ...) as beside any atom; a bool LEAF inside
  an expression (`X == T + 1`) is `_eval_ground`'s domain_error, Scryer's
  `X #= true + 1`.  The guards go back to their shape.
- 11 pins of `True == 1`, each moved with a `D35 closed` comment:
  `audit_2026_07_05/test_01_term_layer.py` (d001 characterization:
  `unify(1, True)`), `audit_2026_07_05/test_02_compiler_heads.py` (a True
  caller reached the int bucket), `test_bytes_adversarial.py`
  (`b"\x01" = [true]`), `test_callsite_specialization.py` +
  `test_resolve_and_argkey.py` x3 (the bool's key is now `("true", 0)`),
  `test_clause_2_iso.py` x3 (a `true/0` indicator walks as `(True, 0)`),
  `test_integral_rationals.py` (`_eval_ground(True)` raises instead of
  "pending"), `test_variables.py::test_bool_int`.
- 1 tooling artefact: `test_atom_class_deprecation.py` census -- terms.py
  bound the atoms MODULE by alias, which the census counts; the import is
  now name-level.

### Box gate d47-2 (8d5294f6): the d47-1 set + 1 -- and the fourth commit
`test_process_module.py::test_shell_accepts_an_atom_command` writes
`shell(mint("true"))`: the shell PROGRAM `true`.  The second commit had
put `crossing_value` under the py.* wrappers' `to_text` as well, and
`to_text` is a TEXT position, not a value boundary -- the atom's spelling
is what it wants.  Reverted there (commit 4); the four value boundaries
(`to_python`, `unwrap_atom`, JSON, z3 options) keep `crossing_value`.  The
rule the census settles on: an atom crosses to Python as its OBJECT where
the Python side receives a VALUE, and as its SPELLING where it receives
TEXT.

### Box gates d47-3 (224c37b2) and d47-4 (2b44990d, the tip)
d47-3: NEW = the one `to_text` process-module case (fixed in 2b44990d),
GONE = the perf-timing flake.  d47-4: 146 failed / 20489 passed / 67
skipped / 33 xfailed / 2 xpassed in 8:43, run completed, import verified
from the gate worktree; **NEW empty**; GONE = `audit_2026_05_25/
test_class_C17_perf_memory.py::test_F026_multi_star_splits_bounded_for_
moderate_input` (a timing test, gone on all four runs -- a flake against
the baseline, not this change).  The two xpassed are pre-existing.

### Residuals (documented, not changed)
- `DictTerm` keys: a Python dict, so `{true: a}` and `{1: a}` share a key.
  Needs a key wrapper like nil's `NIL_KEY` plus a reverse map on `items()`.
- (Tabling variant keys: closed in 8d5294f6 -- the object and the str key
  alike.)
- `sum_list`/`max_list`/`min_list` still use Python `sum`/`max`
  (`sum_list([true], S)` gives 1) -- not ISO library predicates.
- The native reader does not map ISO `callable/1` to `callable_/1`
  (strict-xfail pinned in the new test file; a reader gap, not D35).
- `_evaluable_culprit(True)` is `('/', True, 0)`: right as a term (renders
  `true/0`), and a test comparing walked terms writes it with `True`.

### Open questions for the operator
1. Is `mint("true") is True` wanted (a runtime-built atom IS the object),
   or should only the source folds produce the objects?  The prototype says
   yes; the D40 indicator expectation is the visible consequence.
2. The str spelling as a second spelling of the atom (unify/==/compare
   accept `"true"` for `True`): keep as the safety net (nil precedent), or
   refuse and make a str `'true'` from a Python caller a distinct term?
3. `list_to_set/2` by `==`/2 also stops deduping `1` with `1.0` -- wanted
   here, or split out?
4. The DictTerm key residual: fix now, or park with a todo?
