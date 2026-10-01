# Clausal Predicate Index

Complete index of all built-in and standard-library predicates. Predicates are listed as `Name/arity`.

Behaviour follows ISO 13211-1 first, and Scryer Prolog where ISO is silent. Error terms are Scryer's `error(Formal, Culprit)`; see [Exceptions](exceptions.md). Which of these the 1.0 release covers is set out in [Public API](public-api.md).

**Documented on their own pages, not here:** the ISO comparison builtins are summarised [below](#iso-comparison-and-term-order-quoted-forms) and in [Operators](operators.md); `is_chars/1`, `is_codes/1` in [Type checking](type_checking.md); `time_goal/1` in [Control](control.md); `has_units/2`, `quantity/…` in [Units](units.md); `rational/1` and `rdiv` in [Arithmetic](arithmetic.md); CLP(ℚ)/CLP(ℝ) (`in_q`, `in_real`, `label_real`, `minimize`, `maximize`, `inf`, `sup`, `bb_inf`, `entailed`, `dump_q`, …) in [CLP(ℚ)](clpq.md) and [CLP(ℝ)](clpr.md); and the solver packages (`z3.*`, `ortools.*`, `pysat.*`) in their own pages.

Notation in signature lines:
- `+` = must be bound (input)
- `-` = output (unified with result)
- `?` = either input or output

---

??? abstract "Builtin term constructors (Python)"

    Every builtin with a Python-identifier name is also an object on the
    `clausal` module (`clausal.append`, `clausal.between`, ...).  Calling it
    **builds a cell** -- the plain tuple `(functor, *args)`, exactly what
    `make_cell` builds; it runs nothing:

    ```python
    import clausal
    from clausal import Var, Module, make_cell, solve

    Z = Var()
    clausal.append([1, 2], [3, 4], Z)      # ('append', [1, 2], [3, 4], Z)
    make_cell("append", [1, 2], [3, 4], Z) # the same cell
    clausal.between(low=1, high=10, x=Z)   # keywords name a registered arity's fields
    clausal.between(1, 10)                 # ('between', 1, 10): built as written, never padded
    clausal.nl()                           # 'nl': a 0-arity builtin builds its atom

    X = Var()
    for _ in solve(clausal.between(1, 3, X), module=Module("scratch")):
        print(X.value)                     # 1, 2, 3
    ```

    `solve` needs `module=` even for a builtin goal: a cell carries no module
    of its own. Inside a `.seam` file, query with the goal-position seam
    instead (`for X in --between(1, 3, X): ...`; see
    [Python integration](python_integration.md)).  The objects are covered as
    *predicates*, not as Python objects; see [Public API](public-api.md).
    `get_builtin_class(name)` still returns them but is internal.

    **Passing builtins to higher-order predicates.** A builtin's name is a
    goal: pass it straight to `maplist`, `include`, `exclude`, `foldl`,
    `call/N`, ... with no lambda wrapper:

    ```
    all_numbers(XS) <- maplist(number, XS)
    keep_ints(XS, INTS) <- include(integer, XS, INTS)
    incremented(XS, YS) <- maplist(succ, XS, YS)
    ```

    ---

## Summary

| Category | Predicates |
|---|---|
| [Control Flow](#control-flow) | once/1, `not`, if_/3, throw/1, catch_recover/3, catch/3, halt/0,1, setup_call_cleanup/3, call_cleanup/2 |
| [Coroutining](#coroutining) | freeze/2, when/2 |
| [Meta-Predicates](#meta-predicates) | findall/3,4, bagof/3, setof/3, forall/2, call_nth/2, count_all/2 |
| [Higher-Order Call](#higher-order-call) | call/1..8, call_goal/1..8 |
| [DCG (Definite Clause Grammars)](#dcg-definite-clause-grammars) | phrase/2, phrase/3 |
| [Term Inspection](#term-inspection) | functor/3, arg/3, unpack/2, copy_term/2, term_variables/2, numbervars/3, gensym/2, module_constant/3 |
| [Runtime Database](#runtime-database) | assertz/1, asserta/1, retract/1, clause/2, abolish_table/2, abolish_all_tables/0 |
| [Prolog Flags](#prolog-flags) | set_prolog_flag/2, current_prolog_flag/2 |
| [Keyword-Term Introspection](#keyword-term-introspection) | vary/3, unbound_keys/2, signature/3 |
| [Attributed Variables](#attributed-variables) | put_attr/3, get_attr/3, del_attr/2, get_attrs/2, put_attrs/2, attvar/1, term_attvars/2 |
| [Constraint Predicates](#constraint-predicates) | dif/2, eq/3, dif_t/3, =/3, dif/3 |
| [CLP(ℤ) — Integer Constraints](#clpfd-integer-constraints) | in_domain/3, label/1, all_different/1, structural_eq/2, sum_/3, scalar_product/4, element/3, circuit/1 |
| [CLP(B) — Boolean Constraints](#clpb-boolean-constraints) | sat/1, taut/2, sat_count/2, bool_labeling/1 |
| [Type Checks](#type-checks) | var/1, nonvar/1, atom/1, string/1, is_str/1, atomic/1, number/1, integer/1, float_/1, compound/1, callable_/1, is_list/1, ground/1, must_be/2, can_be/2 |
| [Dict and Set Predicates](#dict-and-set-predicates) | get/3,4, get_strict/3, tri_get/3, delete/3, is_dict/1, dict_get/3, dict_put/4, dict_merge/3, gen_dict/3, sub_dict/2, is_set/1, set_union/3, set_subset/2, gen_set/2 |
| [Arithmetic](#arithmetic) | between/3, succ/2, plus/3, abs_/2, max_/3, min_/3, sign/2, gcd/3, divmod_/4, lcm/3, exp_mod/4, popcount/2, msb/2, lsb/2 |
| [List Predicates](#list-predicates) | in_/2, append/3, length/2, reverse/2, sort/2, permutation/2, select/3, flatten/2, take/3, drop/3, zip_/3, map_list_to_pairs/3, split_with/3, numlist/2,3, same_length/2, transpose/2 |
| [Higher-Order List Predicates](#higher-order-list-predicates) | maplist/2..9, include/3, exclude/3, partition/4, tfilter/3, tpartition/4, foldl/4,5,6, take_while/3, drop_while/3, span/4, group_by/3, sort_by/3, filter_map/3 |
| [Character/String](#characterstring) | char_type/2, char_code/2, upcase_atom/2, downcase_atom/2, atom_length/2, atom_chars/2, atom_codes/2, atom_concat/3, sub_atom/5, number_chars/2, number_codes/2 |
| [I/O](#io) | write/1, writeq/1, write_canonical/1, write_term/2, writeln/1, write_text/1, writeln_text/1, print_term/1, nl/0, tab/1, write_to_string/2, write_text_to_string/2, term_to_string/2, listing/1, portray_clause/1 |
| [Logging (`log` module)](#logging-log-module) | get_logger, debug, info, warning, error, critical, log, set_level, get_level, stream_handler, file_handler |
| [Date & Time (`date_time` module)](#date--time-date_time-module) | now, now_utc, today, date, time, datetime, timedelta, date_add, date_sub, date_diff, datetime_string, timestamp, datetime_string_iso, date_string_iso, date_of, days_between, weekday, date_between, date_max, date_min, ordinal |
| [Time & statistics](#time--statistics) | current_time/1, statistics/2 |
| [ISO comparison and term order](#iso-comparison-and-term-order-quoted-forms) | `'='/2`, `'\\='/2`, `'=='/2`, `'\\=='/2`, `'@<'/2` ..., `compare/3`, `'=..'/2`, `'is'/2`, `'=:='/2`, `'<'/2` ... |
| [Operator Syntax (Compiler Special Forms)](#operator-syntax-compiler-special-forms) | `is`, `is not`, `==`, `!=`, `<`, `<=`, `>`, `>=`, `in`, `not in`, `not` |
| Solver packages | `z3.*`, `ortools.*`, `pysat.*`, `clpq.*`, `clpr.*`: see their own pages ([Constraints](constraints.md)) |

---

## Control Flow

These are **compiler special forms** — transformed at compile time, not dispatched via the builtin registry.

### `once/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:once_1"
```
Commit to the first solution of `Goal`; succeeds at most once even if `Goal` has multiple solutions.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/once_member.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `not/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:not_1"
```
Negation as failure (NAF). Succeeds if `Goal` has no solutions. Written as the Python keyword, `not goal`, in a clause body; `Not` (TitleCase) is a load-time `SyntaxError` like every TitleCase name.
For tabled predicates, uses well-founded semantics (delayed negation); see [WFS](wfs.md).

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/wfs_win.clausal`, `tests/fixtures/wfs_win_asym.clausal`
    **Python tests:** `tests/test_compiled_programs.py`, `tests/test_wfs.py`

---

### `if_/3` (If-Then-Else)
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:if_3"
```
The reified if-then-else (see [Reified if-then-else](reified_ite.md)); Clausal has no cut and no `->`. `Then` runs for **every** solution of `Cond` and `Else` only when `Cond` has none, so nothing is committed: `if_(in_(Y, [1, 2]), X is Y, X is 0)` answers `X = 1` and `X = 2`. A unification condition (`X is 1`) is reified: with `X` unbound both branches are explored, the `Else` branch under `dif(X, 1)`.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/reified_memberd.clausal`, `tests/fixtures/tabled_ite.clausal`, `tests/fixtures/reified_max.clausal`
    **Python tests:** `tests/test_reified_ite.py`

---

### `throw/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:throw_1"
```
Raise a logic-level exception carrying `Term`. The exception propagates through the generator/trampoline chain until caught by `catch/3` or surfaces as a Python `LogicException`.

??? info "Implementation & tests"
    **Exception class:** `clausal/logic/exceptions.py` (`LogicException`)
    **Clausal tests:** `tests/clausal_modules/exceptions.clausal`
    **Python tests:** `tests/test_exceptions.py`

---

### `catch_recover/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:catch_recover_3"
```
Execute `Goal`. If it throws and the thrown term unifies with `Error`, execute `Recovery`. It never re-raises: a thrown term that does not unify with `Error` makes `catch_recover` **fail**. For ISO behaviour (re-raise on mismatch) use `catch/3`.

??? info "Implementation & tests"

---

### `catch/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:catch_3"
```
Execute `Goal`. If `Goal` throws, unify the thrown term with `Catcher`. If unification succeeds, execute `Recovery`; otherwise re-raise. If `Goal` succeeds without throwing, `catch/3` is transparent — all solutions pass through.

An ISO error arrives in Scryer's form, `error(Formal, Culprit)`, where `Culprit` is the predicate indicator (`catch(atom_length(1, _), E, true)` binds `E = error(type_error(atom, 1), atom_length/2)`); see [Exceptions](exceptions.md). A Python exception raised inside `Goal` (for example from `++expr`) is caught as the cell `(ClassName, Message)`: `catch(++int("x"), E, true)` binds `E` to `('ValueError', "invalid literal for int() with base 10: 'x'")`. Bindings made by the failing goal are undone before recovery runs.

??? info "Implementation & tests"
    **Clausal tests:** `tests/clausal_modules/exceptions.clausal`
    **Python tests:** `tests/test_exceptions.py`

---

### `halt/0`, `halt/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:halt_0"
```
Terminate execution by raising `SystemExit`. `halt/0` exits with code 0; `halt/1` exits with the given code. `catch/3` does not absorb it.

A 0-arity predicate in goal position is written bare, as in ISO Prolog — `halt`, `nl`, `abolish_all_tables` — or with parentheses (`halt()`, `nl()`); both spellings call it. An `-import_from`'d 0-arity predicate is called the same way. `true`, `fail` and `false` are written bare.

??? info "Implementation & tests"
    **Python tests:** `tests/test_exceptions.py`

---

### `setup_call_cleanup/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:setup_call_cleanup_3"
```
Deterministic resource management (`try/finally` for logic). Setup runs once (first solution only). Call runs normally. Cleanup runs **exactly once** regardless of how Call terminates — success, failure, or exception. If Setup fails, Cleanup does not run.

??? info "Implementation & tests"
    **Python tests:** `tests/test_coroutining.py::TestSetupCallCleanup`
    **Clausal tests:** `tests/fixtures/coroutining.clausal`

---

### `call_cleanup/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:call_cleanup_2"
```
Sugar for `setup_call_cleanup(true, Call, Cleanup)` — no setup step, just guaranteed cleanup.

??? info "Implementation & tests"
    **Python tests:** `tests/test_coroutining.py::TestCallCleanup`
    **Clausal tests:** `tests/fixtures/coroutining.clausal`

---

## Coroutining

Coroutining predicates delay goal execution until variables are bound. They use the attributed variable hook infrastructure.

*Full documentation: [Coroutining](coroutining.md)*

### `freeze/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:freeze_2"
```
Delay `Goal` until `X` is bound. If `X` is already bound, runs `Goal` immediately. If `X` is unbound, attaches Goal as an attribute; when `X` is later unified, the frozen goal fires synchronously — failure rejects the unification.

??? info "Implementation & tests"
    **Python tests:** `tests/test_coroutining.py::TestFreeze`
    **Clausal tests:** `tests/fixtures/coroutining.clausal`

---

### `when/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:when_2"
```
Generalized coroutining: delay `Goal` until `Condition` is satisfied. Supported conditions: `nonvar(X)`, `ground(X)`, conjunction `(C1, C2)`, disjunction `(C1 ; C2)`.

??? info "Implementation & tests"
    **Python tests:** `tests/test_coroutining.py::TestWhen`
    **Clausal tests:** `tests/fixtures/coroutining.clausal`

---

## Meta-Predicates

These are **compiler special forms** recognized by name in `compile_goal`/`compile_goal_trampoline`. Inner goals compile in simple mode as sub-generators.

### `findall/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:findall_3"
```
Collect all bindings of `Template` produced by `Goal` into `Bag` (a list). Succeeds with `[]` if `Goal` has no solutions.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/meta_test.clausal`
    **Python tests:** `tests/test_meta.py`

---

### `findall/4`

`findall(Template, Goal, Bag, Tail)`: as `findall/3`, but the collected list
ends in `Tail` instead of `[]` (Scryer's difference-list form):
`findall(X, member(X, [1, 2]), L, [3])` gives `L = [1, 2, 3]`. `Bag` and
`Tail` must each be a list or a partial list (`type_error(list, _)`).

??? info "Implementation & tests"
    **Python tests:** `tests/iso_l3/test_l3_s4_constructs.py`

---

### `bagof/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:bagof_3"
```
Like `findall/3` but fails if `Goal` has no solutions, and collects one bag
per binding of the goal's free variables (those in neither `Template` nor a
leading `Var ^`), backtracking over the bags in the standard order of those
bindings (ISO 8.10.2). A bag preserves duplicate solutions. See
[Meta-Predicates](meta_predicates.md#bagof3).

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/meta_test.clausal`
    **Python tests:** `tests/test_meta.py`

---

### `setof/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:setof_3"
```
Like `bagof/3` (one set per binding of the free variables, `^` for
existential ones) but removes duplicates and sorts each set.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/meta_test.clausal`
    **Python tests:** `tests/test_meta.py`

---

### `forall/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:forall_2"
```
Universal quantification: succeeds if `Action` succeeds for every solution of `Cond`. Desugars to `not(Cond and not(Action))`.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/meta_test.clausal`
    **Python tests:** `tests/test_meta.py`

---

### `call_nth/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:call_nth_2"
```
Call `Goal` and succeed only on the **Nth solution** (1-indexed). Skips the first N-1 solutions. Fails if Goal has fewer than N solutions. Raises `type_error` if N is not a positive integer.

??? info "Implementation & tests"
    **Python tests:** `tests/test_coroutining.py::TestCallNth`
    **Clausal tests:** `tests/fixtures/coroutining.clausal`

---

### `count_all/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:count_all_2"
```
Count the number of solutions of `Goal` without collecting them. Unifies `Count` with the integer result. Bindings from the inner goal are not visible after counting (the trail is unwound).

??? info "Implementation & tests"
    **Python tests:** `tests/test_coroutining.py::TestCountAll`
    **Clausal tests:** `tests/fixtures/coroutining.clausal`

---

## Time & statistics

### `current_time/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:current_time_1"
```
Unify T with the current Unix timestamp as a float (seconds since epoch).

---

### `statistics/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:statistics_2"
```
Query runtime statistics. With Key bound, looks up a specific stat. With Key unbound, enumerates all available stats via backtracking.

| Key | Value |
|---|---|
| `'wall_time'` | Wall-clock seconds since process start (float) |
| `'cpu_time'` | CPU seconds used by this process (float) |
| `'memory'` | Peak RSS memory in bytes (int, Linux/macOS only) |

---

## Higher-Order Call

### `call/1..8`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:call"
```
Call `Goal` (a lambda or dispatch function) with 0–7 extra arguments appended. Aliases for `call_goal/1..8`.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_call.clausal`
    **Python tests:** `tests/test_meta.py`, `tests/test_higher_order.py`

---

### `call_goal/1`, `call_goal/2`, `call_goal/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:call_goal_1"
```
Core implementation of higher-order call. `Goal` must be a callable (lambda or `_get_dispatch()` object). `call_goal/4..8` are generated via `_make_call_goal_n`.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_call.clausal`
    **Python tests:** `tests/test_meta.py`, `tests/test_higher_order.py`

---

## DCG (Definite Clause Grammars)

### `phrase/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:phrase_2"
```
Invoke a DCG rule and require it to consume the entire input list. `RuleBody` is either a predicate name (0 extra args, e.g. `greeting`) or a partial term (N extra args, e.g. `digit(D)`). equivalent to calling the rule with `List` as the input state and `[]` as the output state. A `RuleBody` built at run time as a control construct is a DCG body, as in ISO: the conjunction `','(A, B)`, the disjunctions `';'(A, B)` and `'|'(A, B)`, and `'\+'(A)`, with lists and strings inside them as terminals — `G =.. [',', inc, inc], phrase(G, [0], [N])`. (`(inc, inc)` written in source is the compound `inc(inc)`, not a conjunction.)

??? info "Implementation & tests"
    **Python tests:** `tests/test_dcg.py`

---

### `phrase/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:phrase_3"
```
Invoke a DCG rule for partial parsing. Like `phrase/2`, but the remaining unconsumed input is unified with `Rest` instead of requiring `[]`.

Also used for **state-passing DCGs**: encode state as a single-element list `[State]`, thread it through DCG nonterminals using `phrase(Rule, [InitialState], [FinalState])`. See [DCGs — state threading](dcg.md#state-threading) for the full pattern.

??? info "Implementation & tests"
    **Python tests:** `tests/test_dcg.py`

---

### `sequence//1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:sequence"
```
DCG non-terminal that matches a list of terminals in sequence. `sequence([a, b, c])` consumes `a`, `b`, `c` from the input. equivalent to inlining the terminals as a grammar rule body.

```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:sequence_ex2"
```

---

## Term Inspection

### `functor/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:functor_3"
```
Decompose a term into its functor name and arity, or construct a term from a name and arity (fields are fresh vars).

**The Name position is an ATOM**, in both directions — never a bare spelling, never a string:

| Call | Answer |
|---|---|
| `functor(foo(a), N, A)` | `N = foo` (an atom), `A = 1` |
| `functor(bar, N, A)` | `N = bar`, `A = 0` |
| `functor(42, N, A)` | `N = 42`, `A = 0` |
| `functor([], N, A)` | `N = []`, `A = 0` (as in Scryer) |
| `functor([1, 2], N, A)` | `N = '.'`, `A = 2` — a list is the `'.'/2` structure |
| `functor("ab", N, A)` | `N = '.'`, `A = 2` — a string is the list of its chars |
| `functor("", N, A)` | `N = []`, `A = 0` |
| `functor(T, foo, 2)` | `T = foo(_, _)` |
| `functor(T, foo, 0)` | `T = foo` |
| `functor(T, '.', 2)` | `T = [_ \| _]` — a partial LIST, never a `'.'/2` cell |
| `functor(T, "foo", 1)` | `type_error(atomic, "foo")` — a string is a compound |
| `functor(T, 42, 2)` | `type_error(atom, 42)` |

The `'.'/2` reading is a **view**: decomposition answers virtually (`arg(2, "hello", T)` gives the string `"ello"`), and construction through the name position builds the engine's real list shapes, never a `(".", H, T)` cell. See `write_canonical/1` for the same view in the writer.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_inspect.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `arg/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:arg_3"
```
Unify `arg` with the `N`-th argument of `Term` (1-based indexing). `N` must
be bound: an unbound `N` is `instantiation_error` (ISO 8.5.2.3, as Scryer; it
used to enumerate the `(N, arg)` pairs, an SWI extension).

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_inspect.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `unpack/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:unpack_2"
```
Decompose a term to a `[functor | args]` list, or construct a term from such a list. (Prolog's `=..` operator.) The head of the list is an **ATOM**, the same name position `functor/3` uses:

| Call | Answer |
|---|---|
| `unpack(foo(a, "b"), L)` | `L = [foo, a, "b"]` |
| `unpack(bar, L)` | `L = [bar]` |
| `unpack(42, L)` | `L = [42]` |
| `unpack([1, 2], L)` | `L = ['.', 1, [2]]` |
| `unpack("abc", L)` | `L = ['.', a, "bc"]` |
| `unpack(T, [foo, 1])` | `T = foo(1)`, a cell |
| `unpack(T, ['.', a, "bc"])` | `T = "abc"` — a char consed onto a string is a string |
| `unpack(T, ['.', 1, [2]])` | `T = [1, 2]` — a Python list |
| `unpack(T, ["foo", 1])` | `type_error(atom, "foo")` |
| `unpack(T, ["foo"])` | `type_error(atomic, "foo")` |

Constructed compounds are **cells** (plain tuples) — Python code tests a constructed term's shape with `clausal.cell_functor` / `clausal.cell_args`.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_inspect.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `copy_term/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:copy_term_2"
```
Unify `Copy` with a deep copy of `Original` where every unbound `Var` is replaced by a fresh one. Structural sharing is preserved: if the same `Var` appears in multiple positions in `Original`, the same fresh `Var` appears in all corresponding positions of `Copy`. Already-bound variables are followed and their values are copied rather than replaced.

??? info "Implementation & tests"
    **Clausal tests:** `tests/clausal_modules/term_inspection.clausal`
    **Python tests:** `tests/test_term_inspection.py`

---

### `term_variables/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:term_variables_2"
```
Unify `Vars` with a list of all unbound `Var`s in `Term`, collected left-to-right with duplicates removed (same `Var` appearing multiple times in `Term` appears only once in `Vars`). Bound variables are followed and not collected.

??? info "Implementation & tests"
    **Clausal tests:** `tests/clausal_modules/term_inspection.clausal`
    **Python tests:** `tests/test_term_inspection.py`

---

### `numbervars/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:numbervars_3"
```
Number all unbound `Var`s in `Term` left-to-right, binding each to the cell `("$VAR", N)` where `N` starts at `Start` and increments. `End` is unified with the next unused number after all variables are numbered. Useful for pretty-printing terms with named variables. `Start` must be a bound integer.

??? info "Implementation & tests"
    **Clausal tests:** `tests/clausal_modules/term_inspection.clausal`
    **Python tests:** `tests/test_term_inspection.py`

---

### `gensym/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:gensym_2"
```
Generate a unique atom by appending a monotonically increasing counter to `Prefix`. `gensym(x, A)` produces the atoms `x_1`, `x_2`, etc. on successive calls. The counter is **not trailed** — it survives backtracking (impure, matches Prolog's `gensym/2`). Thread-safe via lock. Different prefixes maintain independent counters. `Prefix` must be a bound atom; anything else (unbound, a `"..."` string, a number) fails.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/inspection.py` (`gensym/2`)
    **Python tests:** `tests/test_term_inspection.py`

---

### `global_atom/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:global_atom_2"
```
Reflect on the process-wide global atom dict — the registry that backs global atom identity (see [Atoms](syntax.md#atoms)). `Name` is an **atom**, read by its spelling; a bound `Name` that is not an atom (a string, a char list under `-double_quotes(chars)`, a number) raises `type_error(atom, Name)` rather than failing. Four modes:

- **`(+Name, -Atom)` — mint on demand.** Look `Name`'s spelling up in the global dict; if absent, install `mint(spelling)`. Idempotent: a second call with the same spelling unifies `Atom` with the same atom. This is the sanctioned way to **reach** the global atom for a name from a module that has shadowed it via `-import_from` or a local declaration — though a quoted literal (`'date'`) already denotes the atom in any mode and needs no declaration.
- **`(+Name, +Atom)` — guard.** Succeeds iff `Atom` **equals** the atom registered under `Name`'s spelling (`==`, the correct test: two atoms of one spelling are one atom, the same interned `str` — interning makes `is` agree too, but `==` is what to write).
- **`(-Name, +Atom)` — reverse lookup.** Succeeds iff `Atom` is genuinely the registered global atom for its spelling (not a module-local namesake). Unifies `Name` with that atom.
- **`(-Name, -Atom)` — enumerate.** Yields one solution per registered atom. The registry holds only atoms that reached it (through this builtin's mint mode, or a manual install), not every atom a program mentions; it can be empty. Ordering is **not guaranteed**.

To obtain an atom from **text** (a string or char list), use `atom_chars/2` or `atom_codes/2`.

`global_atom/2` is the reflection escape hatch for reaching a global atom by
name when a module-local declaration or an import shadows it — and the sanctioned
way for a strict-default file to obtain a global atom it does not list.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/inspection.py` (`global_atom/2`)
    **Python tests:** `tests/test_term_inspection.py` (`TestGlobalAtom`)

---

### `constant_value/2`

```text
constant_value(Name, Value)
```

The constant *Name* names. `Name` is an **atom**; `Value` is its frozen ground value.

This is Markus Triska's name for the cross-implementation convention (2026-09-10), so the
spelling and arity are not Clausal's to vary: an exported `.pl` and any expansion prelude must
use exactly this.

```seam
-module(m, [retry_limit/1, max_retries])
-constant_value(max_retries, 3)

retry_limit(N) <- constant_value(max_retries, N)
```

!!! warning "Scope: program-wide, not module-implicit"
    In a Prolog system there is one program, so `constant_value/2` is a fact about it. Clausal
    has modules, and the module-implicit reading would need the **calling** module — which a
    builtin does not get: the registry hands dispatch functions their arguments and a trail,
    and nothing else. So this enumerates every loaded Clausal module's own declarations,
    exactly as `module_constant(-Module, +Name, ?Value)` does. Two modules declaring the same
    constant name both answer. Use [`module_constant/3`](#module_constant3) when the module
    matters.

### `constant_number_units/3`

!!! note "Scope: the OWNING module, resolved at compile time (2026-09-12)"
    Unlike [`constant_value/2`](#constant_value2) above, this is **module-scoped**, and the
    difference is worth understanding because the constraint they face is identical.

    A builtin cannot receive the calling module. But the **compiler** knows it, so a written
    `constant_number_units(Name, N, U)` is compiled to
    [`module_constant_units/4`](#module_constant_units4) with the owning module inserted —
    the same way `$module` is handed to the registration when a declaration is lowered.
    Reading works the way writing already does.

    The module inserted is the name's **owner**, which is not always the caller: an imported
    constant is registered on the module that declared it, so the compiler uses the module the
    import named.

    Consequences, all of them intentional:

    * a name this module neither declares nor imports **cannot be written** — it is a
      compile-time error naming the way out, rather than silently answering with some other
      module's declaration in load order;
    * an **imported** constant answers here (it did not before);
    * with the name **unbound** this enumerates, but only this module's own declarations.

    `constant_value/2` keeps the program-wide reading: its name and arity are fixed by
    cross-implementation convention, so its scope is not ours to vary.


```text
constant_number_units(Name, Number, Units)
```

A constant declared with [`-constant_number_units`](directives.md#-constant_number_units).
`Name` is an **atom**, `Number` the magnitude, `Units` the unit expression.

Named for what it can hold: **only numbers carry units**, which is why this is not
`constant_value_units/3`. The directive enforces it — a non-numeric value is a load-time
error naming the directive.

A constant declared *without* units has no solution here. It has a value but no units, and
[`constant_value/2`](#constant_value2) is the predicate that relates it; answering with a
dimensionless marker would make every constant look united.

!!! important "It reports the DECLARATION, not the stored value"
    These differ whenever the declared unit is not the base of its own dimension, because the
    units library rescales to that base. `-constant_number_units(standstill, 30, day)` stores
    `Quantity(2592000, second)` — both the `30` and the `day` are unrecoverable from the value.

    | | |
    | --- | --- |
    | `constant_number_units(standstill, N, U)` | `N = 30`, `U = day` |
    | `constant_value(standstill, V)` | `V = 2592000 second` |

    The two disagree about the number **on purpose**: `constant_value/2` is the value view,
    and this one exists to report what the declaration said. That is what lets a check assert
    a parameter's declared unit matches the unit its *name* claims — impossible against the
    normalised pair, where every duration is `second` whatever was written.

`Units` is the unit expression as declared:

| declared | `Units` |
| --- | --- |
| `-constant_number_units(max_fine, 5000, euro)` | `euro` |
| `-constant_number_units(speed, 3, metre / second)` | `metre / second` |
| `-constant_number_units(area, 7, metre ** 2)` | `metre ** 2` |

```seam
-module(m, [limit/2, max_fine])
-import_from(european_union, [euro])
-constant_number_units(max_fine, 5000, euro)

limit(N, U) <- constant_number_units(max_fine, N, U)
```

### `module_constant_units/4`

```text
module_constant_units(Module, Name, Number, Units)
```

The **declared pair**, scoped to one module — standing to
[`constant_number_units/3`](#constant_number_units3) exactly as
[`module_constant/3`](#module_constant3) stands to [`constant_value/2`](#constant_value2).

`Module` is a module object; `Name` is the constant's spelling. Reports the **declaration**,
not the stored value, for the reasons given at `constant_number_units/3`.

A module that does not declare `Name` simply **fails**. This is a lookup, not an assertion —
the error for a name nothing declares belongs at the `constant_number_units/3` call site, where
the compiler can see the name was written as a literal and refuse it before anything runs.

This is also the relation `constant_number_units/3` compiles to, with the owning module
inserted. Writing it by hand is for the case where the module you want is not the one you are
in and not one you imported the name from.

### `module_constant/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:module_constant_3"
```
Reflect on a module's own [`-constant_value`](directives.md#-constant_value) declarations,
naming the module explicitly. `Module` is the Python module object a `-import_module(...)`
directive binds — the same object a qualified constant reference like `other_module.pi`
resolves against; `Name` is the constant's declaration spelling as an **atom**
(`max_retries`); `Value` is the
constant's frozen value — the identical object the declaring module's own clause bodies embed.

```text
# m.clausal
-module(m, [])
-constant_value(max_retries, 3)

# caller.clausal
-import_module(m)
retry_limit(N) <- module_constant(m, max_retries, N)
```

Four modes, following directly from which of `Module`/`Name` are bound:

- **`(+Module, +Name, ?Value)` — look up / check.** Fails if `Module` declares no constant
  named `Name`; otherwise checks/binds `Value`.
- **`(+Module, -Name, ?Value)` — enumerate a module's constants.** One solution per
  `(Name, Value)` pair `Module` declares.
- **`(-Module, +Name, ?Value)` — find the declaring module(s).** Searches every *loaded*
  Clausal module (a snapshot of `sys.modules`) for one that declares a constant named `Name`;
  `Module` need not be imported into the querying file.
- **`(-Module, -Name, ?Value)` — enumerate everything.** One solution per
  `(Module, Name, Value)` triple across every loaded Clausal module.

**Only a module's own declarations are reflected** — a constant reached via `-import_from` or
`-import_module` is *not* re-registered on the importer, so `module_constant/3` never sees it
there. Query the module that actually declared it instead (see
[Importing constants](import.md#importing-constants)).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/inspection.py` (`module_constant/3`),
    `clausal/logic/constants.py` (`register_module_constant`),
    `clausal/logic/database.py` (`Module.constants`)
    **Python tests:** `tests/test_module_constant_reflection.py`

---

## Runtime Database

These work only on a predicate declared [`-dynamic`](database_ops.md#declare-first-the-dynamic-directive) (declare first). A static predicate raises `error(permission_error(modify, static_procedure, Name/Arity), assertz/1)` (or `asserta/1`, `retract/1`); a name with no declaration is refused by assertz/asserta, unless the module sets the flag [`assert_creates_dynamic`](flags.md#assert_creates_dynamic), which creates it as dynamic (ISO 7.5.2(2)). See [Database operations](database_ops.md).

### `assertz/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:assertz_1"
```
Add the fact `Clause` at the **end** of its predicate's clause list. Only facts can be asserted: a rule raises `permission_error(assert, rule, Head)`. The predicate must be declared `-dynamic`: a static one, or one nothing declares (static by default, ISO 7.5.2), raises `error(permission_error(modify, static_procedure, Name/Arity), assertz/1)`; an unbound `Clause` raises `instantiation_error`.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_db.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `asserta/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:asserta_1"
```
Add `Clause` at the **front** of its predicate's clause list.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_db.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `retract/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:retract_1"
```
Remove the **first** clause whose head unifies with `Term`. Not backtrackable — removes exactly one clause per call. As in ISO (8.9.3) and Scryer: it fails when nothing matches, including for a name nothing declares (there is no clause to remove); a static predicate, a declared data functor or a builtin raises `error(permission_error(modify, static_procedure, Name/Arity), retract/1)`; an unbound `Term` raises `instantiation_error`. (`retractall/1` and `abolish/1` are not provided.)

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_db.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `clause/2`
```text
clause(+Head, ?Body)
```
ISO 8.8.1: `Body` unifies with the body of each clause of a **dynamic**
predicate whose head unifies with `Head` (`True` for a fact), in the logical
update view. A static predicate raises
`permission_error(access, private_procedure, Name/Arity)`, as does a builtin
or control construct; an unknown one fails.

```seam
-dynamic(edge/2)
-dynamic(path/2)

edge(1, 2),
path(X, Y) <- edge(X, Y)

test("fact body is True") <- clause(edge(1, _), True)
test("rule body is a term") <- (clause(path(A, B), BODY), BODY is edge(A, B))
```

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/clause_ops.py`
    **Python tests:** `tests/test_clause_2_iso.py`

---

### `abolish_table/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:abolish_table_2"
```
Remove all cached answers for the named tabled predicate, forcing re-computation on the next call.

??? info "Implementation & tests"
    **Clausal tests:** none
    **Python tests:** `tests/test_tabling.py`

---

### `abolish_all_tables/0`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:abolish_all_tables_0"
```
Remove all cached tabling answers for every predicate in the current database.

??? info "Implementation & tests"
    **Clausal tests:** none
    **Python tests:** `tests/test_tabling.py`

---

## Prolog Flags

The ISO flags and `assert_creates_dynamic`; the table of flags, values and
scopes is in [Prolog Flags](flags.md).

### `set_prolog_flag/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:set_prolog_flag_2"
```
Set a flag (ISO 8.17.1). A module-scoped flag (`assert_creates_dynamic`) is set
for the calling module; `double_quotes` is set only by the directive
[`-set_prolog_flag`](directives.md#-set_prolog_flag). Errors are ISO's:
`instantiation_error`, `type_error(atom, F)`, `domain_error(prolog_flag, F)`,
`domain_error(flag_value, F+V)`, and `permission_error(modify, flag, F)` for a
read-only flag or a value this engine does not implement.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/flags.py`
    **Python tests:** `tests/iso/test_prolog_flags_scryer.py`

---

### `current_prolog_flag/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:current_prolog_flag_2"
```
The value of a flag (ISO 8.17.2); a module-scoped flag reports the calling
module's value. With `Flag` unbound it enumerates every flag that has a value
(`max_integer` and `min_integer` have none: integers are unbounded).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/flags.py`
    **Python tests:** `tests/iso/test_prolog_flags_scryer.py`

---

## Keyword-Term Introspection

These predicates address a term's fields by name; the names come from the functor's declaration (`-private([point(x, y, z)])`). See [Term Inspection § Fields by name](term_inspection.md#fields-by-name). The keyword construction spelling `point(x=1)`, `KWTerm` and `extend/3` are gone.

### `vary/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:vary_3"
```
Produce a copy of `Term` with field values replaced by `Overrides` (a Python `dict`). Works on declared functor cells.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_keywords.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `unbound_keys/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:unbound_keys_2"
```
Unify `Keys` with a list of field names whose values are unbound `Var`s in `Term`.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_keywords.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `signature/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:signature_3"
```
Reflect the registered parameter name list for the predicate `FunctorName/Arity`. Fails if no signature is registered.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_keywords.clausal`
    **Python tests:** `tests/test_builtins.py`

---

## Attributed Variables

Attributed variables carry key-value metadata that survives through unification. This is the mechanism that powers CLP(ℤ), CLP(B), CLP(ℝ), dif/2, and units constraints internally. These predicates expose the API so users can build custom constraint solvers.

Attribute keys are **atoms** — `put_attr(X, my_key, V)`, or `'my key'` when the name needs quoting. A string key raises `type_error(atom, Key)`. Attribute values can be any term. All mutations are trailed (undone on backtracking).

### `put_attr/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:put_attr_3"
```
Attach attribute `Value` under the atom `Key` to an unbound variable. Overwrites any existing value for that key. Trailed.

---

### `get_attr/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:get_attr_3"
```
Retrieve the attribute stored under `Key`. Fails if `Var` has no attribute for `Key`, or if `Var` is not an unbound variable.

---

### `del_attr/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:del_attr_2"
```
Remove the attribute under `Key`. Succeeds even if no attribute existed (no-op). Trailed.

---

### `get_attrs/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:get_attrs_2"
```
Unify `Attrs` with a `DictTerm` containing all attributes on `Var`, keyed by the same atoms `put_attr/3` takes. Empty `DictTerm` if no attributes.

---

### `put_attrs/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:put_attrs_2"
```
Set multiple attributes from a `DictTerm`. Each key-value pair is applied via `put_attr`.

---

### `attvar/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:attvar_1"
```
Succeeds if `Var` is an unbound variable with at least one attribute. Fails for bound terms and for bare (non-attributed) variables.

---

### `term_attvars/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:term_attvars_2"
```
Collect all attributed variables occurring in `Term` into a list. Traverses compound terms, lists, DictTerms, and term instances recursively. Each variable appears at most once.

---

## Constraint Predicates

### `dif/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:dif_2"
```
Disequality constraint. Succeeds if `X` and `Y` can remain different (posts a constraint if either is unbound). Implemented via attributed variables; propagates through unification.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_dif.clausal`
    **Python tests:** `tests/test_dif.py`

---

### `eq/3` (reified)
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:eq_3"
```
Reified equality. `T` is unified with `True` if `X = Y`, `False` if `dif(X, Y)`. Suspends if neither is determined yet.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/reif_eq_test.clausal`, `tests/fixtures/builtins_dif.clausal`
    **Python tests:** `tests/test_reif_builtins.py`

---

### `dif_t/3` (reified)
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:dif_t_3"
```
Reified disequality. `T` is `True` if `dif(X, Y)`, `False` if `X = Y`.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_dif.clausal`
    **Python tests:** `tests/test_reif_builtins.py`

---

### `=/3` and `dif/3` (library(reif))

Scryer's library(reif) names: `=(X, Y, T)` is `eq/3` (`T = True` with
`X = Y` first, then `T = False` with `dif(X, Y)`), and `dif(X, Y, T)` is its
negation in the SAME answer order (`T = False` first; `dif_t/3` answers
`True` first). A `.pl` file's `if_(X = Y, ...)` and closures such as
`tfilter(=(a), ...)` run on them. `if_/3`'s library(reif) meaning for a
`.pl` file is described in [Reified if-then-else](reified_ite.md).

??? info "Implementation & tests"
    **Python tests:** `tests/iso_l3/test_l3_s4_constructs.py`

---

## CLP(ℤ) — Integer Constraints

CLP(ℤ) operates over **all integers** — variables default to the entire integer line `(-∞, +∞)` until constrained. Comparison operators (`==`, `!=`, `<`, `<=`, `>`, `>=`) are handled as **compiler special forms** mapping to `_fd_eq`, `_fd_ne`, `_fd_lt`, `_fd_le`, `_fd_gt`, `_fd_ge`. The predicates below are the builtin-registry interface.

### `in_domain/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:in_domain_3"
```
Post the integer domain `[Lo, Hi]` on a logic variable or a list of logic variables. Required before `label/1` can enumerate values.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/clpfd_queens.clausal`, `tests/fixtures/clpfd_sendmore.clausal`
    **Python tests:** `tests/test_clpfd.py`

---

### `label/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:label_1"
```
Enumerate concrete values for a list of constrained variables, backtracking over all consistent assignments. Variables must have finite domains (via `in_domain/3` or comparison constraints) — raises `ValueError` on unbounded domains.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/clpfd_queens.clausal`, `tests/fixtures/clpfd_sendmore.clausal`
    **Python tests:** `tests/test_clpfd.py`

---

### `all_different/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:all_different_1"
```
Post an all-different constraint on a list of integer-constrained variables. Propagates bounds and eliminates assigned values from other domains.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/clpfd_queens.clausal`, `tests/fixtures/clpfd_sendmore.clausal`
    **Python tests:** `tests/test_clpfd.py`

---

### `structural_eq/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:structural_eq_2"
```
True structural equality (ISO `==/2`, also written `'=='(T1, T2)`). Succeeds if `T1` and `T2` are identical after dereferencing variables, **without** binding any variables and **without** evaluating arithmetic. Recursively walks compound terms (cells), lists, SegLists, DictTerms, and user-defined term dataclasses.

For structural inequality use `not structural_eq(T1, T2)`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/constraints.py` → `clausal/logic/constraints.py:structural_eq`
    **Tests:** `tests/conformity/test_iso_unification.py:TestStructuralEquality`
    **Python tests:** `tests/test_clpfd.py`

---

### `sum_/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:sum__3"
```
Constrain the sum of `Vars` (a list of FD variables or integers) under comparison operator `Op` to `Value`. Supported operators: `#=`, `#<`, `#>`, `#=<`, `#>=`, `#\=`.

```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:sum__3_ex2"
```

For `#=`, posts a `SumConstraint` that propagates bounds in both directions: narrows `Value` to `[min_sum, max_sum]` and narrows each variable using the remaining slack. For inequality operators, an intermediate variable is introduced and chained with the appropriate binary relational constraint. Ground lists with a ground `Value` are checked immediately without posting a constraint.

---

### `scalar_product/4`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:scalar_product_4"
```
Weighted sum constraint: `Σ(Coeffs[i] * Vars[i]) Op Value`. Coefficients must be ground integers. Lists must be the same length. Supports negative coefficients — division direction is flipped accordingly when narrowing individual variables.

```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:scalar_product_4_ex2"
```

Uses the same bounds-consistency approach as `sum_/3` (`ScalarProductConstraint`). For inequality operators, an intermediate variable is introduced and chained with a binary relational constraint.

---

### `element/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:element_3"
```
`Value` is the `Index`-th element of `List` (1-based indexing). when Index is ground, performs direct lookup. when Index is an FD variable, posts an `ElementConstraint` that propagates bidirectionally: narrows `Index` to positions whose list element overlaps `Value`'s domain, and narrows `Value` to the union of the domains at valid positions. Then enumerates the surviving valid indices.

```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:element_3_ex2"
```

---

### `circuit/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:circuit_1"
```
Constrain `Vars` to form a single Hamiltonian circuit. `Vars[i] = j` means the successor of node `i+1` is node `j` (1-based). Posts a `CircuitConstraint` that: restricts all domains to `[1, n]`, removes self-loop values, enforces all_different, and detects premature sub-tours via forced-chain analysis — pruning values that would close a cycle shorter than `n`. Labeling then enumerates remaining candidates.

```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:circuit_1_ex2"
```

---

## CLP(B) — Boolean Constraints

CLP(B) uses reduced ordered BDDs (Binary Decision Diagrams) for Boolean constraint solving. Expressions use Python's bitwise operators: `&` (AND), `|` (OR), `^` (XOR), `~` (NOT), plus `BoolEq` (equivalence) and `BoolImpl` (implication) term constructors.

### `sat/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:sat_1"
```
Post a Boolean constraint. The expression must evaluate to true. Fails if unsatisfiable. Propagates forced values (e.g., `sat(X & Y)` forces both to 1).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/constraints.py` → `clausal/logic/clpb.py`
    **Clausal tests:** `tests/fixtures/clpb_circuit.clausal`
    **Python tests:** `tests/test_clpb.py`

---

### `taut/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:taut_2"
```
Tautology check. Unify `T` with 1 if `Expr` is always true, 0 if always false. Fail if indeterminate.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/constraints.py` → `clausal/logic/clpb.py`
    **Clausal tests:** none
    **Python tests:** `tests/test_clpb.py`

---

### `sat_count/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:sat_count_2"
```
Count the number of satisfying assignments for `Expr`. Unify `N` with the count.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/constraints.py` → `clausal/logic/clpb.py`
    **Clausal tests:** none
    **Python tests:** `tests/test_clpb.py`

---

### `bool_labeling/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:bool_labeling_1"
```
Enumerate 0/1 assignments for a list of Boolean variables. Backtracks over all satisfying assignments.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/constraints.py` → `clausal/logic/clpb.py`
    **Clausal tests:** `tests/fixtures/clpb_circuit.clausal`
    **Python tests:** `tests/test_clpb.py`

---

## Type Checks

### `var/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:var_1"
```
Succeeds if `X` is an unbound logic variable.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `nonvar/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:nonvar_1"
```
Succeeds if `X` is bound (not an unbound `Var`).

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `atom/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:atom_1"
```
Succeeds if `X` is an **atom**: the interned Python `str` itself. Written bare
(`red`, declared via `-private([red, blue])`, `-module(m, [red])` or an
import) or single-quoted (`'hello world'`, no declaration
needed). A **string** is not an atom — use `string/1` / `is_str/1` for that —
and neither is `[]`. From Python, build one with
`clausal.logic.atoms.mint("red")` and read its spelling with `spelling/1`.

---

### `is_str/1` and `string/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:is_str_1"
```
Succeeds if `X` is a **string** — the term a `"…"` literal denotes, which is the list of its character atoms. Does not match atoms (a bare `str` is an atom, not a string) — use `atom/1` for those — and note that `atomic/1` rejects a string, because a string is a list. See [Type Checking](type_checking.md#string1-and-is_str1) for the full table.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/type_checks.py`
    **Python tests:** `tests/test_builtins.py`

---

### `atomic/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:atomic_1"
```
Succeeds if `X` is an atomic constant: an **atom**, a number, a bool, or another indivisible value. It is **false for a string**, which is a list, and false for a compound term.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/type_checks.py`
    **Python tests:** `tests/test_builtins.py`

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `number/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:number_1"
```
Succeeds if `X` is an `int` or `float` (excludes `bool`).

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `integer/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:integer_1"
```
Succeeds if `X` is an `int` (excludes `bool`).

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `float_/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:float__1"
```
Succeeds if `X` is a Python `float`.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `compound/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:compound_1"
```
Succeeds if `X` is a compound term with arity > 0: a cell `('f', …)`, or a non-empty list or string (the `'.'/2` structure, as in ISO). An **atom** is arity 0, so `compound/1` rejects it, and so is `[]` (= `""`).

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `callable_/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:callable__1"
```
Succeeds if `X` is an **atom** or a compound term — something that could appear as a goal. As in ISO, a non-empty string is a `'.'/2` compound and so is callable: `call("foo")` raises `existence_error(procedure, '.'/2)`, not a type error.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `is_list/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:is_list_1"
```
Succeeds if `X` is list-shaped: a Python `list`, or a **string**, which *is* the list of its character atoms. Use `is_str/1` when you need to tell a character sequence (string) apart from a plain list — a bare atom (`str`) satisfies neither.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `ground/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:ground_1"
```
Succeeds if `X` contains no unbound `Var`s (is fully instantiated).

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `must_be/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:must_be_2"
```
Assert that `Term` is of the given type. Succeeds silently if it matches. Throws `instantiation_error` if Term is unbound, and `error(type_error(Type, Term), must_be/2)` if Term is ground but of the wrong type.

The Type argument is an **atom**. Supported types: `integer`, `float`, `number`, `atom`, `string` / `str`, `list`, `boolean`, `callable`, `dict`, `compound`. `atom` and `string` are separate types: `must_be('atom', "abc")` raises, and so does `must_be('string', abc)`.

!!! warning "Quote a type name that is also a builtin"
    `integer`, `float`, `number`, `atom`, `callable` and `compound` are also builtin predicate names, and a bare builtin name in an argument is the builtin's object, not the atom: `must_be(integer, 3)` raises `type_error(atom, <builtin integer/1>)`. Write `must_be('integer', 3)`.

---

### `can_be/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:can_be_2"
```
Assert that `Term` could possibly be of the given type. Succeeds if Term is unbound (it could become anything) or already matches the type. Throws `type_error` only when Term is ground and definitely the wrong type. The Type argument is an **atom**, and the same types `must_be/2` takes.

---

## Dict and Set Predicates

Dict and set builtins operate on `DictTerm`/`SetTerm` values **and equally on plain Python `dict`/`set`** — the plain flavor is accepted wherever the Term flavor is (they unify and compare equal; outputs bind the Term flavor). See [Dicts and Sets](dicts_sets.md) for the full design, including the always-available [Python dict surface](dicts_sets.md#the-python-dict-surface): `P[key]` subscript, `get/3`, `get/4`, `tri_get/3`, `key in P`, `{**P, k: v}` splat-merge, and `delete/3`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/dict_set.py`
    **Python tests:** `tests/test_dict_set_builtins.py` (79 tests)
    **Fixture:** `tests/fixtures/dict_set_builtins.clausal`

### `get/3`, `get/4`, `get_strict/3`, `tri_get/3`, `delete/3` — the dict surface

The DICT-first read/removal family mirroring Python's `dict.get`/`del`:
`get(Dict, Key, Value)` soft-fails on an absent key, `get(Dict, Key, Value,
Default)` binds the default, `tri_get(Dict, Key, Value)` binds `Undefined`,
and `delete(Dict, Key, NewDict)` removes functionally (throws on absent).
The strict read is the subscript, `V is Dict[Key]`, and its predicate form
`get_strict(Dict, Key, Value)` (same argument order as `get/3`), which throws
`existence_error(dict_key, Key)` on an absent key with the subscript's other
errors too — the one strict read ISO syntax (`.pl`) can spell. From `.seam`
it is an ordinary call, `get_strict(D, 'k', V)`. Documented in full at
[The Python dict surface](dicts_sets.md#the-python-dict-surface).

---

### `is_dict/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:is_dict_1"
```
Succeeds if `Term` is a `DictTerm` or a plain `dict`.

---

### `dict_size/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:dict_size_2"
```
`N` is the number of keys in `Dict`.

---

### `dict_keys/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:dict_keys_2"
```
`Keys` is the sorted list of keys (sorted by `repr` for cross-type determinism).

---

### `dict_values/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:dict_values_2"
```
`Values` is the list of values in key-sorted order.

---

### `dict_pairs/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:dict_pairs_2"
```
Bidirectional: `Dict` ↔ list of `Key-Value` pairs (the `'-'(Key, Value)` cell, as `pairs_keys_values/3`). In dict→pairs direction, pairs are sorted by key.

---

### `dict_get/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:dict_get_3"
```
Semidet lookup. Fails if `Key` is absent or unbound.

---

### `dict_put/4`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:dict_put_4"
```
Functional update: `NewDict` is `OldDict` with `Key → Value` set. Returns a new `DictTerm`.

---

### `dict_put_pairs/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:dict_put_pairs_3"
```
Bulk update from a list of `Key-Value` pairs, equivalent to repeated `dict_put/4`.

---

### `dict_remove/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:dict_remove_3"
```
`NewDict` is `OldDict` without `Key`. Fails if `Key` is absent.

---

### `dict_merge/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:dict_merge_3"
```
union of `D1` and `D2`. Where keys conflict, `D2`'s value wins.

---

### `gen_dict/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:gen_dict_3"
```
Nondeterministic enumeration. Yields one `Key`/`Value` binding per solution on backtracking. Can be filtered by binding `Key` before the call.

---

### `sub_dict/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:sub_dict_2"
```
Partial dict matching. Succeeds when every key in `Pattern` is present in `Dict` and the values unify. Extra keys in `Dict` are ignored. See [sub_dict](dicts_sets.md#partial-dict-matching--subdict2) for examples.

---

### `is_set/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:is_set_1"
```
Succeeds if `Term` is a `SetTerm`.

---

### `set_size/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:set_size_2"
```
`N` is the cardinality of `Set`.

---

### `set_list/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:set_list_2"
```
Bidirectional: `Set` ↔ sorted list. In list→set direction, duplicates are removed.

---

### `set_union/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:set_union_3"
```
Set union.

---

### `set_intersection/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:set_intersection_3"
```
Set intersection.

---

### `set_subtract/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:set_subtract_3"
```
`Diff` = elements in `S1` not in `S2`.

---

### `set_sym_diff/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:set_sym_diff_3"
```
Symmetric difference: elements in exactly one of `S1`, `S2`.

---

### `set_subset/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:set_subset_2"
```
Succeeds if `Sub` is a subset of `Super` (including equal sets and the empty set).

---

### `set_disjoint/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:set_disjoint_2"
```
Succeeds if `S1` and `S2` share no elements.

---

### `set_add/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:set_add_3"
```
`NewSet` is `OldSet` with `Elem` added. No-op if already present.

---

### `set_remove/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:set_remove_3"
```
`NewSet` is `OldSet` with `Elem` removed. No-op if absent.

---

### `gen_set/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:gen_set_2"
```
Nondeterministic enumeration of set elements. Order is deterministic (sorted by `repr`).

---

## Arithmetic

Arithmetic uses `==` to post CLP(ℤ) constraints (e.g., `Y == X * 2`). The predicates below provide relational arithmetic usable in both input and output modes.

### `between/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:between_3"
```
Check or enumerate integers in `[Low, High]` inclusive. In check mode (X bound) succeeds iff `Low ≤ X ≤ High`. In generate mode (X unbound) backtracks over each integer.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_arith.clausal`
    **Python tests:** `tests/test_builtins.py`, `tests/test_search.py`

---

### `succ/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:succ_2"
```
Bidirectional successor: if `X` is bound, `Y = X + 1`; if `Y` is bound, `X = Y - 1`. Both must be non-negative integers.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_arith.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `plus/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:plus_3"
```
Relational addition: any two of `X`, `Y`, `Z` determine the third.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_arith.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `abs_/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:abs__2"
```
Absolute value.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_arith.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `max_/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:max__3"
```
??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_arith.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `min_/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:min__3"
```
??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_arith.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `sign/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:sign_2"
```
sign of X. Returns -1 for negative, 0 for zero, 1 for positive. Supports Quantity values (result is always a dimensionless integer).

---

### `gcd/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:gcd_3"
```
Greatest common divisor of two integers. Supports Quantity values — dimensions must agree; result preserves dimensions.

---

### `divmod_/4`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:divmod__4"
```
Integer division and modulus. Fails if Y is 0. Supports Quantity values — dimensions must agree; quotient Q is dimensionless, remainder R preserves dimensions.

---

### `lcm/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:lcm_3"
```
Least common multiple of two integers. Supports Quantity values — dimensions must agree; result preserves dimensions.

---

### `exp_mod/4`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:exp_mod_4"
```
Modular exponentiation using Python's efficient `pow(base, exp, mod)`. Integer-only (no Quantity support). Fails if Mod is 0.

---

### `popcount/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:popcount_2"
```
Population count (number of 1 bits). X must be a non-negative integer.

---

### `msb/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:msb_2"
```
Most significant bit position. X must be a positive integer. `msb(8, B)` gives B=3.

---

### `lsb/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:lsb_2"
```
Least significant bit position. X must be a positive integer. `lsb(12, B)` gives B=2.

---

!!! note "Quantity support in arithmetic"
    `plus`, `abs_`, `max_`, `min_`, `sign`, `gcd`, `divmod_`, and `lcm` all accept
    `Quantity` values (numbers with physical dimensions). Dimension mismatches
    raise `UnitsMismatch` — they are not silenced. `exp_mod`, `popcount`, `msb`,
    and `lsb` are integer-only (bitwise operations have no dimensional
    interpretation).

---

## List Predicates

!!! tip "Strings accepted"

    All list predicates accept strings as character lists. `append("hel", "lo", X)` yields `X = "hello"`. when all inputs are strings and the result is a character sequence, the result is returned as a string. See [Strings as Lists](strings_as_lists.md).

### `in_/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:in__2"
```
Enumerate or check membership. Backtracks over all elements.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/meta_test.clausal`, `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`, `tests/test_search.py`

---

### `in_check/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:in_check_2"
```
Deterministic membership check. Succeeds at most once; no backtracking.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `append/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:append_3"
```
List concatenation. Works in all modes: given any two, determines the third. Backtracks over splits when `L3` is bound and `L1`/`L2` are unbound.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`, `tests/test_search.py`

---

### `length/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:length_2"
```
List length in both directions.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `last/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:last_2"
```
Unify `Elem` with the last element of `List`.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`, `tests/test_search.py`

---

### `reverse/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:reverse_2"
```
??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`, `tests/test_search.py`

---

### `list_item/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:list_item_3"
```
Get the element at 0-based index `N`.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `flatten/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:flatten_2"
```
Recursively flatten a nested list structure.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `msort/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:msort_2"
```
sort `List` preserving duplicate elements (stable sort).

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `sort/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:sort_2"
```
sort `List` removing duplicate elements.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `permutation/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:permutation_2"
```
Enumerate all permutations of `List` via backtracking.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`, `tests/test_search.py`

---

### `select/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:select_3"
```
select `Elem` from `List`, unifying `Rest` with the remaining elements. Backtracks over all positions where `Elem` appears.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `subtract/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:subtract_3"
```
List difference: elements in `Set1` not in `Set2`.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `intersection/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:intersection_3"
```
Elements present in both `Set1` and `Set2`.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `union/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:union_3"
```
Elements in `Set1` or `Set2`, with duplicates removed.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `list_to_set/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:list_to_set_2"
```
Remove duplicates from `List` preserving the first-occurrence order.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `sum_list/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:sum_list_2"
```
sum_ all numeric elements of `List`.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `max_list/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:max_list_2"
```
Maximum element of a non-empty numeric list.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `min_list/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:min_list_2"
```
Minimum element of a non-empty numeric list.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `take/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:take_3"
```
First `N` elements of `List`. If `N > len(List)`, returns the whole list. If `N = 0`, returns `[]`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/lists.py` (`_take__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `drop/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:drop_3"
```
`List` after dropping the first `N` elements. If `N >= len(List)`, returns `[]`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/lists.py` (`_drop__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `split_at/4`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:split_at_4"
```
Split `List` at index `N` into `Left` (first N elements) and `Right` (rest). Clamps to list bounds.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/lists.py` (`_split_at__4`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `zip_/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:zip__3"
```
Pair up elements from two lists into `X-Y` pairs (the `'-'(X, Y)` cell). Truncates to the shorter list.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/lists.py` (`_zip__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `replicate/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:replicate_3"
```
`List` of `N` copies of `Elem`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/lists.py` (`_replicate__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `split_with/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:split_with_3"
```
Split `List` by separator `Sep` into sublists (`Parts`). In join mode, interleaves `Parts` with `Sep`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/lists.py` (`_split_with__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `pairs_keys_values/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:pairs_keys_values_3"
```
Relate a list of `Key-Value` pairs to separate `Keys` and `Values` lists, as in Scryer's `library(pairs)`. Works in every direction; a pair it builds is the cell `'-'(K, V)`. A non-list, or an element that is not a pair, fails (no error). See [Pairs](pairs.md).

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `pairs_keys/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:pairs_keys_2"
```
The keys of a list of `Key-Value` pairs: `pairs_keys_values(Pairs, Keys, _)`.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `pairs_values/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:pairs_values_2"
```
The values of a list of `Key-Value` pairs: `pairs_keys_values(Pairs, _, Values)`.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `group_pairs_by_key/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:group_pairs_by_key_2"
```
Group **adjacent** `Key-Value` pairs whose keys are identical (`==`), as in Scryer's `library(pairs)`. Groups is a list of `Key-Values`. It does not sort: sort the pairs first (`msort/2`) to collect every occurrence of a key into one group.

```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:group_pairs_by_key_2_ex2"
```

---

### `map_list_to_pairs/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:map_list_to_pairs_3"
```
`Pairs` is `[K1-E1, K2-E2, ...]` with `call(Goal, Ei, Ki)` for each element of `List`, as in Scryer's `library(pairs)`. Every solution of each call is an answer on backtracking. See [Pairs](pairs.md#map_list_to_pairs3).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_map_list_to_pairs__3`)
    **Python tests:** `tests/test_map_list_to_pairs.py`

---

### `numlist/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:numlist_3"
```
List is the list of integers from Low to High inclusive. Fails if Low > High.

```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:numlist_3_ex2"
```

---

### `numlist/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:numlist_2"
```
Shorthand for `numlist(1, High, List)`.

---

### `same_length/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:same_length_2"
```
Succeeds if L1 and L2 have the same length. If one is ground and the other is unbound, generates a list of fresh variables with matching length.

---

### `transpose/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:transpose_2"
```
Column-wise transposition of a list of lists. All rows must be the same length (fails on non-rectangular input). Empty matrix transposes to empty list.

```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:transpose_2_ex2"
```

---

## Higher-Order List Predicates

These predicates accept a **goal argument** (a lambda or named predicate). The goal is called for each list element; failures propagate as in standard higher-order patterns.

### `maplist/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:maplist_2"
```
Verify that `Goal(Elem)` succeeds for every element of `List`. Fails if any element fails.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_higher_order.clausal`
    **Python tests:** `tests/test_higher_order.py`

---

### `maplist/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:maplist_3"
```
Map `Goal(X, Y)` over `Xs` to produce `Ys`. Takes the first solution of `Goal` per element.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_higher_order.clausal`
    **Python tests:** `tests/test_higher_order.py`

---

### `maplist/4` .. `maplist/9`

`maplist(Goal, L1, ..., Ln)` calls `Goal(E1, ..., En)` on the elements of
the lists in step (Scryer's library(lists)); lists of different lengths give
no answer, an open list is enumerated as by `maplist/2,3`, and every
solution of every call is an answer on backtracking. `maplist/9` runs on
`call/9`.

??? info "Implementation & tests"
    **Python tests:** `tests/iso_l3/test_l3_s4_constructs.py`

---

### `include/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:include_3"
```
include `List` keeping only elements for which `Goal(Elem)` succeeds.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_higher_order.clausal`
    **Python tests:** `tests/test_higher_order.py`

---

### `exclude/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:exclude_3"
```
include `List` keeping only elements for which `Goal(Elem)` **fails**.

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_higher_order.clausal`
    **Python tests:** `tests/test_higher_order.py`

---

### `partition/4`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:partition_4"
```
Split `List` into two: `Included` contains elements where `Goal(Elem)` succeeds, `Excluded` contains elements where it fails.

```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:partition_4_ex2"
```

---

### `tfilter/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:tfilter_3"
```
Reified filter. Calls `Goal(Elem, T)` where T is a fresh variable bound to `True` or `False` by the goal. Keeps elements where T=True. Committed choice: only the first solution of Goal is used.

Useful with reified predicates like `eq/3` and `dif_t/3` that always succeed but bind their truth-value argument.

```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:tfilter_3_ex2"
```

---

### `tpartition/4`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:tpartition_4"
```
Reified partition. Calls `Goal(Elem, T)` for each element. Elements where T=True go into `Included`, T=False into `Excluded`.

```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:tpartition_4_ex2"
```

---

### `foldl/4`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:foldl_4"
```
Left fold. Calls `Goal(Elem, Acc0, Acc1)` for each element, threading the accumulator. `V0` is the initial value; `V` is the final result. `foldl/5` and `foldl/6` fold over two and three lists (`Goal(X, Y, Acc0, Acc1)`, ...), as Scryer's `library(lists)`. Every solution of each call is an answer on backtracking, and an open list enumerates (see [Higher-Order](higher_order.md#foldl4-foldl5-foldl6)).

??? info "Implementation & tests"
    **Clausal tests:** `tests/fixtures/builtins_higher_order.clausal`
    **Python tests:** `tests/test_higher_order.py`

---

### `take_while/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:take_while_3"
```
Longest prefix of `List` where `Goal(Elem)` succeeds for each element.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_take_while__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `drop_while/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:drop_while_3"
```
Suffix of `List` after dropping the longest prefix where `Goal(Elem)` succeeds.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_drop_while__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `span/4`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:span_4"
```
`take_while` + `drop_while` in one pass. `Yes` is the longest prefix where `Goal` succeeds; `No` is the rest.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_span__4`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `group_by/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:group_by_3"
```
Group consecutive elements by key projected via `Goal(Elem, Key)`. Elements with equal consecutive keys are collected into sublists.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_group_by__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `sort_by/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:sort_by_3"
```
sort `List` by key projected via `Goal(Elem, Key)`. Stable sort (preserves order of equal keys).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_sort_by__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `max_by/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:max_by_3"
```
element of `List` with the largest key projected via `Goal(Elem, Key)`. Fails on empty list.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_max_by__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `min_by/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:min_by_3"
```
element of `List` with the smallest key projected via `Goal(Elem, Key)`. Fails on empty list.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_min_by__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `filter_map/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:filter_map_3"
```
Map + filter in one pass. Calls `Goal(Elem, Out)` for each element; keeps `Out` when the goal succeeds, skips the element when it fails.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_filter_map__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

## Character/String

Logic-aware character and atom predicates that participate in unification and backtracking. Unlike Python string methods, these are *relations* — e.g. `atom_concat(A, B, hello)` with A and B unbound enumerates all splits, `char_type(C, digit)` enumerates digits.

!!! warning "These take ATOMS, not strings"

    Every predicate in this section whose ISO name begins `atom_` (plus `char_code/2`, `char_type/2`, `upcase_atom/2`, `downcase_atom/2`) takes an **atom** in the atom position and answers with atoms. Handing one a **string** raises `type_error(atom, S)` — `atom_length("abc", N)` is an error, not a failure. `char_code/2` raises `type_error(character, S)` for the same reason.

    That is the ISO/Scryer split: an atom is a symbol, a string is the list of its character atoms, and the two never unify. See [Atoms vs strings](syntax.md#atoms-vs-strings).

!!! note "Prefer list predicates for STRING operations"

    A string *is* a list, so `append/3` subsumes `atom_concat/3`, `length/2` subsumes `atom_length/2`, `list_item/3` indexes, `in_/2` tests membership, and `reverse/2` reverses. Reach for the `atom_*` family when you are working with an atom, or when you need it as the **bridge** between the two kinds: `atom_chars/2` turns an atom into the char list of its spelling and back. See [Strings as Lists](strings_as_lists.md).

```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:chars_family_kinds"
```

### `char_type/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:char_type_2"
```
Character classification as a relation. `Char` is a **char atom** (`'a'`), `Type` an atom. At least one argument must be bound. Types: `alpha`, `digit`, `alnum`, `space`, `upper`, `lower`, `ascii`, `punct`, `print`, `control`. With Char bound, enumerates matching types. With Type bound, enumerates matching ASCII characters. With both bound, tests membership.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/chars.py`
    **Python tests:** `tests/test_chars.py`

---

### `char_code/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:char_code_2"
```
Bidirectional char-atom ↔ integer code point conversion. `char_code('A', N)` unifies N with 65. `char_code(C, 65)` unifies C with the atom `'A'`. Both bound tests equality. Both unbound raises `instantiation_error`. A **string** in the Char position raises `type_error(character, S)` — `"a"` is the one-element list `['a']`, not the character.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/chars.py`
    **Python tests:** `tests/test_chars.py`

---

### `upcase_atom/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:upcase_atom_2"
```
Unify `Upper` with the uppercase version of `Atom` — atom in, atom out. The first argument must be a bound **atom**; a string raises `type_error(atom, …)`.

---

### `downcase_atom/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:downcase_atom_2"
```
Unify `Lower` with the lowercase version of `Atom` — atom in, atom out. The first argument must be a bound **atom**; a string raises `type_error(atom, …)`.

---

### `atom_length/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:atom_length_2"
```
Unify `length` with the number of characters in `Atom`'s spelling. The first argument must be a bound **atom**; `atom_length("abc", N)` raises `type_error(atom, "abc")` — use `length/2`, which counts a string's characters because a string is a list.

---

### `atom_chars/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:atom_chars_2"
```
Bidirectional conversion between an **atom** and the list of its character atoms — the bridge between atoms and text. `atom_chars(hi, L)` unifies L with `['h', 'i']`, which is the same term as the string `"hi"`. `atom_chars(A, ['h', 'i'])` and `atom_chars(A, "hi")` both unify A with the atom `hi`. A string in the first position raises `type_error(atom, "hi")`; a non-list in the second — an atom included — raises `type_error(list, hi)`.

---

### `atom_codes/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:atom_codes_2"
```
Bidirectional conversion between an **atom** and the list of its integer code points. `atom_codes(hi, L)` unifies L with `[104, 105]`.

---

### `atom_concat/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:atom_concat_3"
```
**Atom** concatenation as a relation. Forward: A and B bound → unify C with the atom of their concatenated spellings. Reverse: C bound, A and/or B unbound → enumerate all splits as atoms. `atom_concat(A, B, abc)` yields 4 solutions: `('', abc)`, `(a, bc)`, `(ab, c)`, `(abc, '')`. Optimized paths for prefix/suffix-bound cases. To concatenate **strings**, use `append/3`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/chars.py`
    **Python tests:** `tests/test_chars.py`

---

### `sub_atom/5`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:sub_atom_5"
```
Sub-atom relation. Relates an **atom** to the atoms of its sub-spellings with position information: `Before + length + After = len(Atom)`, `Sub = Atom[Before:Before+length]`, and every `Sub` answer is an atom. Multi-modal — any combination of bound/unbound arguments works (Atom must be bound). With Sub bound, uses `str.find()` for efficient lookup. Otherwise enumerates all valid `(Before, length)` pairs. For **substrings of a string**, use `append/3` or the multi-star patterns of [Strings as Lists](strings_as_lists.md).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/chars.py`
    **Python tests:** `tests/test_chars.py`

---

### `number_chars/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:number_chars_2"
```
Bidirectional number ↔ character-list conversion. Number bound → `Chars` unifies with the list of the number's **character atoms** (which is the same term as the string of its digits). Chars a ground list (a char list or the string that is that list) → read as a number token (below) and unified with Number, whether or not Number is bound. Both unbound → instantiation error. Rejects `bool` values (not considered numbers).

A ground `Chars` is READ as a Prolog number token, as ISO 8.16.7 and Scryer read it: layout and comments may lead (`" 1"` is 1), a `-` may stand before the token, and `0x1A`, `0'a`, `1_000` and `1.5e-3` are numbers; nothing may follow the token (`"1 "`, `"+1"`, `"1e5"`, `"inf"` are not numbers). Text that is not a number raises Scryer's `syntax_error(unexpected_end_of_file)` (the text ended before a number was read) or `syntax_error(unexpected_char)` (context `number_chars/2:0`). With both arguments bound the text is read, so `number_chars(1, ['0', '1'])` holds. `number_codes/2` shares this behaviour. (Until 2026-09-30 the text was parsed with Python's `int()`/`float()` and a non-number FAILED.)

```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:number_chars_2_ex2"
```

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/chars.py`
    **Python tests:** `tests/test_chars.py`

---

### `number_codes/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:number_codes_2"
```
Bidirectional number ↔ code-point-list conversion. Like `number_chars/2` but uses integer code points (`ord`/`chr`) instead of character atoms.

```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:number_codes_2_ex2"
```

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/chars.py`
    **Python tests:** `tests/test_chars.py`

---

## I/O

### `write/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:write_1"
```
Print `Term` to stdout without a trailing newline, **unquoted** — ISO 8.14.2's `write_term(Term, [numbervars(true)])`. An atom prints its spelling bare; a STRING prints as the list of characters it is, so `write("abc")` prints `[a,b,c]` and `write([a, b])` prints `[a,b]`; a `b"…"` code list prints as its code numbers (`write(b"ab")` → `[97,98]`). List syntax is kept (`f(a,b)`, `[1,2]`), with **no space after a comma** — the ISO family's output is byte-comparable with other ISO systems. Logic variables are auto-dereferenced — bound vars print their value, unbound vars print `_N`.

For human text — and for f-strings — use `write_text/1` / `writeln_text/1`, which print a string as its characters. Use `print_term/1` when you need to tell an atom from a string.

??? info "Implementation & tests"
    **Python tests:** `tests/test_io.py`

---

### `writeq/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:writeq_1"
```
Print `Term` to stdout **quoted**, without a trailing newline — ISO 8.14.2's `write_term(Term, [quoted(true), numbervars(true)])`. An atom is quoted when its spelling is not a bare token (`'foo bar'`); a STRING is the list of its characters, as in `write/1`, so `writeq("abc")` prints `[a,b,c]` and `writeq(f(a, "b"))` prints `f(a,[b])`. List syntax is kept, unlike `write_canonical/1`, and so is the ISO comma spacing — none.

`print_term/1` and `term_to_string/2` are the Clausal *display* form — `write_term(Term, [quoted(true), double_quotes(true)])` — which prints `"abc"`; reach for those when you need to tell an atom from a string at a glance.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/io.py` (`writeq/1`)
    **Python tests:** `tests/test_writers_atoms_strings.py`

---

### `write_term/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:write_term_2"
```
Print `Term` to stdout under an ISO **write-option list** (ISO 8.14.2), without a trailing newline. Both Boolean options default to `false`, so `write_term(Term, [])` is the strict ISO display.

| Option | Effect |
|---|---|
| `quoted(Bool)` | quote an atom that would not read back as itself (`'foo bar'`) |
| `double_quotes(Bool)` | print a string — and the char list that *is* one — as `"abc"` rather than `[a,b,c]` |
| `ignore_ops(Bool)` | accepted, inert: the write family here never prints operator forms |
| `numbervars(Bool)` | accepted, inert: there is no `'$VAR'/1` convention here |

| Call | Output |
|---|---|
| `write_term("abc", [])` | `[a,b,c]` |
| `write_term("abc", [quoted(true)])` | `[a,b,c]` |
| `write_term("abc", [quoted(true), double_quotes(true)])` | `"abc"` |
| `write_term([a, b], [])` | `[a,b]` |
| `write_term('a b', [quoted(true)])` | `'a b'` |

`write_term(Term, [])` is exactly `write/1` and `write_term(Term, [quoted(true)])` is exactly `writeq/1`. `write_term(Term, [quoted(true), double_quotes(true)])` gives a string the *spelling* `print_term/1` and `term_to_string/2` give it; those two additionally keep the display comma spacing, which this writer, being ISO, does not. An unrecognised option raises `domain_error(write_option, Opt)`; a non-list `Options` raises `type_error(list, Options)`; an unbound or partial `Options` (`[quoted(true) | _]`) raises `instantiation_error`. Streams are out of scope, so there is no `write_term/3`, and `max_depth(N)` is not supported.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/io.py` (`write_term/2`)
    **Python tests:** `tests/test_writers_atoms_strings.py`

---

### `write_canonical/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:write_canonical_1"
```
Print `Term` to stdout quoted, ignoring operator syntax **and** list syntax: every list — a string included — prints as the `'.'/2` cons structure it denotes, with no space after commas, so the output is byte-comparable with other ISO systems.

| Term | `write_canonical` output |
|---|---|
| `"hello"` | `'.'(h,'.'(e,'.'(l,'.'(l,'.'(o,[])))))` |
| `[1, 2]` | `'.'(1,'.'(2,[]))` |
| `[]` | `[]` |
| `foo(a, "b")` | `foo(a,'.'(b,[]))` |
| `1 + 2` | `+(1,2)` |

The cons form is a **view**, not the representation: a string stays a compact `str` and a list stays a Python `list`. The same view is what `functor/3` and `=..` report for them.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/io.py` (`write_canonical/1`)
    **Python tests:** `tests/test_writers_atoms_strings.py`

---

### `writeln/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:writeln_1"
```
Like `write/1` (ISO, unquoted) but appends a newline. Not an ISO name; `writeln_text/1` is the text form.

??? info "Implementation & tests"
    **Python tests:** `tests/test_io.py`

---

### `write_text/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:write_text_1"
```
Print `Term` to stdout as **text**, without a trailing newline. A STRING prints as its characters and a char list as the text it spells (`write_text("abc")` → `abc`, `write_text([a, b])` → `ab`); an atom prints its bare spelling; every other term prints exactly as `write/1` prints it. `""` / `[]` print `[]`.

This is Clausal's `~s`, and it is where f-strings go: `write_text(f"X is {X}")`. `write/1` is the ISO writer and spells a string out as `[a,b,c]`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/io.py` (`write_text/1`)
    **Python tests:** `tests/test_io.py`

---

### `writeln_text/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:writeln_text_1"
```
Like `write_text/1` but appends a newline. `writeln_text(f"X is {X}")` is the idiomatic way to print an interpolated line.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/io.py` (`writeln_text/1`)
    **Python tests:** `tests/test_io.py`

---

### `print_term/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:print_term_1"
```
Print the Clausal **display** representation of `Term` — an atom quoted where it needs it, a string in double quotes (the spelling `write_term(Term, [quoted(true), double_quotes(true)])` gives), compounds as functor/args, and the display `", "` after a comma that the ISO family drops — followed by a newline. Useful for debugging, because it distinguishes an atom from a string.

??? info "Implementation & tests"
    **Python tests:** `tests/test_io.py`

---

### `nl/0`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:nl_0"
```
Print a newline to stdout.

??? info "Implementation & tests"
    **Python tests:** `tests/test_io.py`

---

### `tab/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:tab_1"
```
Print `N` spaces to stdout. `N` must be a bound non-negative integer.

??? info "Implementation & tests"
    **Python tests:** `tests/test_io.py`

---

### `write_to_string/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:write_to_string_2"
```
Unify `String` with the **ISO** (`write/1`) rendering of `Term`, as a string — a string spells itself out as `[a,b,c]`. Does not print anything. `write_text_to_string/2` is the text form.

??? info "Implementation & tests"
    **Python tests:** `tests/test_io.py`

---

### `write_text_to_string/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:write_text_to_string_2"
```
Unify `String` with the **text** (`write_text/1`) rendering of `Term`, as a string — a string passes through as its characters. Does not print anything. This is the one to build human-readable text with.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/io.py` (`write_text_to_string/2`)
    **Python tests:** `tests/test_io.py`

---

### `term_to_string/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:term_to_string_2"
```
Unify `String` with the Clausal **display** rendering of `Term`, as a string — the `write_term(Term, [quoted(true), double_quotes(true)])` spelling plus the display `", "` after a comma. Does not print anything.

??? info "Implementation & tests"
    **Python tests:** `tests/test_io.py`

---

### `listing/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:listing_1"
```
Print all clauses of a predicate to stdout in readable Clausal syntax. Follows Scryer Prolog's contract (operator ruling 2026-09-25): the argument is a predicate indicator, `Name/Arity` or `Name//Arity` (the latter names `Name/(Arity+2)`); an unbound argument, or an indicator naming no predicate or one with no clauses, FAILS; any other term (a bare atom, a compound, a string, a number) raises `type_error(predicate_indicator, PI)`; a malformed operand raises `functor/3`'s error (`instantiation_error`, `type_error(integer, A)`, `domain_error(not_less_than_zero, A)`, `type_error(atomic, N)` for a string name, `type_error(atom, N)` for a number name). A user-written `foo/2` / `foo // 2` compiles to a runtime `Div` / `FloorDiv` node (`/` and `//` are arithmetic operators); the cells `('/', Name, Arity)` / `('//', Name, Arity)` are also accepted. Prints a header comment with clause count, followed by each clause formatted as `head.` (fact) or `head <- (body).` (rule). An indicator naming an IMPORTED predicate resolves to the exporter's predicate, so `listing(qq/1)` from a module that `-import_from`s `qq` prints what the exporter's `listing(qq/1)` prints. From Python it also takes a predicate HANDLE (each arity it is defined at is listed) or a builtin predicate (`"% name/arity — builtin"`).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/io.py` (`listing/1`)
    **Python tests:** `tests/test_listing.py`

---

### `portray_clause/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:portray_clause_1"
```
Pretty-print a term with indentation for multi-line display using `term_pformat`. Short terms appear on one line; deeply nested terms are expanded with depth indentation.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/io.py` (`portray_clause/1`)
    **Python tests:** `tests/test_listing.py`

---

## Logging (`log` module)

Standard library module wrapping Python's `logging`. Import via `-import_from(log, [...])`. See [logging.md](logging.md) for full documentation.

All logging predicates always succeed (side-effect only). Messages below the logger's configured level are silently discarded.

### `get_logger/1`, `get_logger/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:getlogger_1"
```
Unify `Logger` with a Python `logging.Logger` instance. Arity-1 returns the default `"clausal"` logger. Same name always returns same logger instance.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/logging.py`
    **Python tests:** `tests/test_logging_module.py`

---

### `debug/1`, `debug/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:debug_1"
```
log at DEBUG level. Arity-1 uses default `"clausal"` logger.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/logging.py`

---

### `info/1`, `info/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:info_1"
```
log at INFO level.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/logging.py`

---

### `warning/1`, `warning/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:warning_1"
```
log at WARNING level.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/logging.py`

---

### `error/1`, `error/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:error_1"
```
log at ERROR level.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/logging.py`

---

### `critical/1`, `critical/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:critical_1"
```
log at CRITICAL level.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/logging.py`

---

### `log/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:log_3"
```
log at an arbitrary level. `Level` is a string (`"debug"`, `"info"`, etc.) or integer.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/logging.py`

---

### `set_level/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:setlevel_2"
```
Set the logger's effective level.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/logging.py`

---

### `get_level/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:getlevel_2"
```
Unify `Level` with the logger's effective level name (e.g. `"DEBUG"`).

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/logging.py`

---

### `is_enabled_for/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:isenabledfor_2"
```
Succeeds if the logger would process a message at `Level`; fails otherwise. The only logging predicate that can fail.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/logging.py`

---

### `stream_handler/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:streamhandler_2"
```
Create a `logging.StreamHandler`. `StreamName` is `"stdout"` or `"stderr"`.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/logging.py`

---

### `file_handler/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:filehandler_2"
```
Create a `logging.FileHandler` for the given path.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/logging.py`

---

### `set_formatter/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:setformatter_2"
```
Set a `logging.Formatter` on the handler using Python format string syntax.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/logging.py`

---

### `add_handler/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:addhandler_2"
```
Add a handler to the logger.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/logging.py`

---

### `remove_handler/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:removehandler_2"
```
Remove a handler from the logger.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/logging.py`

---

### `basic_config/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:basicconfig_1"
```
Call `logging.basicConfig()` with a dict of options (level, format, datefmt, filename, filemode, stream).

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/logging.py`

---

## Date & Time (`date_time` module)

Standard library module wrapping Python's `datetime`. Import via `-import_from(date_time, [now, today, date, ...])`. All predicates produce and consume **real Python `datetime` objects** — `datetime.date`, `datetime.time`, `datetime.datetime`, `datetime.timedelta` — not custom term types. Unification uses Python's native `==`. Any `datetime` method can be called via `++()` interop (e.g. `S is ++D.isoformat()`).

### `now/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:now_1"
```
Unify `DT` with `datetime.datetime.now()` (naive, local time).

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/datetime.py`
    **Python tests:** `tests/test_date_time.py`

---

### `now_utc/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:nowutc_1"
```
Unify `DT` with `datetime.datetime.now(datetime.timezone.utc)` (timezone-aware).

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/datetime.py`

---

### `today/1`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:today_1"
```
Unify `D` with `datetime.date.today()`.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/datetime.py`

---

### `date/4`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:date_4"
```
Bidirectional. If `DateObj` is unbound, constructs `datetime.date(Year, Month, Day)`. If `DateObj` is a `datetime.date` (or `datetime.datetime`), decomposes into `Year`, `Month`, `Day`. Fails on invalid dates (e.g. month 13, Feb 29 in non-leap year).

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/datetime.py`
    **Python tests:** `tests/test_date_time.py`

---

### `time/4`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:time_4"
```
Bidirectional. If `TimeObj` is unbound, constructs `datetime.time(Hour, Minute, Second)`. If `TimeObj` is a `datetime.time`, decomposes into `Hour`, `Minute`, `Second`.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/datetime.py`

---

### `datetime/7`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:datetime_7"
```
Bidirectional. If `DtObj` is unbound, constructs `datetime.datetime(Year, Month, Day, Hour, Minute, Second)`. If `DtObj` is a `datetime.datetime`, decomposes into all six components.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/datetime.py`

---

### `timedelta/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:timedelta_3"
```
Bidirectional. If `TdObj` is unbound, constructs `datetime.timedelta(days=Days, seconds=Seconds)`. If `TdObj` is a `datetime.timedelta`, decomposes into `Days` and `Seconds`.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/datetime.py`

---

### `date_add/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:dateadd_3"
```
`Result = DateOrDatetime + Timedelta`. Both inputs must be ground.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/datetime.py`

---

### `date_sub/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:datesub_3"
```
`Result = DateOrDatetime - Timedelta`. Both inputs must be ground.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/datetime.py`

---

### `date_diff/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:datediff_3"
```
`Timedelta = D1 - D2`. Both inputs must be `datetime.date` or `datetime.datetime`. Result is a `datetime.timedelta` (may be negative).

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/datetime.py`

---

### `datetime_string/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:datetime_string_3"
```
Bidirectional. Format mode (`DateTime` has `strftime`): `String = DateTime.strftime(Format)`. Parse mode (`DateTime` unbound, `String` a string): `DateTime = datetime.strptime(String, Format)`. `Format` must be a ground string. Note: `strptime` always yields a `datetime`, so a `date` round-trips to a midnight `datetime`.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/datetime.py`

---

### `weekday/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:weekday_2"
```
`Weekday = DateOrDatetime.weekday()`. Monday = 0, Sunday = 6.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/datetime.py`

---

### `date_between/3`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:datebetween_3"
```
Nondeterministic — generates one solution for each `datetime.date` in `[Start, End]` (inclusive). Fails if `Start > End`. This is the only date_time predicate that backtracks.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/datetime.py`
    **Python tests:** `tests/test_date_time.py`

---

### `timestamp/2`
```seam
--8<-- "tests/fixtures/docs/builtins_sigs.txt:timestamp_2"
```
Bidirectional. Forward (`DateTime` is a `datetime.datetime`): `Stamp = DateTime.timestamp()` (float epoch seconds); with `Stamp` already bound this acts as a check. Inverse (`DateTime` unbound, `Stamp` a number): `DateTime = datetime.fromtimestamp(Stamp)`. A plain `date` has no `timestamp()` — the forward direction requires a `datetime`.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/datetime.py`
    **Python tests:** `tests/test_date_time.py`

---

### `datetime_string_iso/2`, `date_string_iso/2`
```seam
--8<-- "tests/fixtures/docs/date_time_sigs.txt:iso"
```
Bidirectional ISO-8601 helpers without a format argument. `datetime_string_iso/2` forward requires a `datetime.datetime` and produces the full ISO-8601 string via `isoformat()`; inverse parses via `fromisoformat`. `date_string_iso/2` forward requires a plain `datetime.date` (a `datetime` is rejected); inverse parses via `date.fromisoformat`. Both predicates catch `(TypeError, ValueError)` and fail cleanly; both-unbound fails.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/py/datetime.py`
    **Python tests:** `tests/test_date_time.py`

---

## ISO comparison and term order (quoted forms)

ISO's comparison and term-order predicates are builtins under their ISO
names, written **quoted** (a bare `==` or `<` is a constraint, see below).
They follow ISO 13211-1, and Scryer where ISO is silent:

| Builtin | Meaning |
|---|---|
| `'='(A, B)`, `'\\='(A, B)` | unification; not unifiable |
| `'=='(A, B)`, `'\\=='(A, B)` | identical / not identical in the standard order of terms |
| `'@<'`, `'@>'`, `'@=<'`, `'@>='` (arity 2) | standard order of terms |
| `compare(Order, A, B)` | `Order` is `'<'`, `'='` or `'>'` |
| `'=..'(Term, List)` | univ; the same relation as `unpack/2` |
| `'is'(X, Expr)` | ISO `is/2`: evaluates `Expr` |
| `'=:='`, `'=\\='`, `'<'`, `'>'`, `'=<'`, `'>='` (arity 2) | ISO arithmetic comparison, both sides evaluated |
| `'#='`, `'#\\='`, `'#<'`, `'#>'`, `'#=<'`, `'#>='` (arity 2) | CLP(ℤ) constraints under clpz's names |

```seam
test("quoted ISO forms") <- (
    '\\=='(1, 2),
    '@<'(1, 'a'),
    compare(O, 1, 2), O == '<',
    'is'(X, 7 // 2), X == 3,
    '=:='(1, 1.0)
)
```

Which operator meaning applies to which spelling (bare = Python, quoted =
Scryer) is set out in [Operators](operators.md); the evaluable functors are in
[Arithmetic](arithmetic.md).

---

## Operator Syntax (Compiler Special Forms)

These bare spellings are syntax, compiled directly rather than looked up as
builtins. [Operators](operators.md) is the reference for their meaning.

| Syntax | Meaning |
|--------|---------|
| `X is Y` | **unification**, no evaluation (`X is 1 + 2` binds `X` to the term `1 + 2`; for ISO `is/2` write `'is'(X, E)` or `eval_(E, X)`) |
| `X is not Y` | disequality constraint (`dif/2`) |
| `X == Y`, `X != Y` | arithmetic equality / disequality constraint (clpz's `#=` / `#\\=`) |
| `X < Y`, `X <= Y`, `X > Y`, `X >= Y` | arithmetic ordering constraints |
| `X in Coll` | membership: enumerates the elements of `Coll` |
| `X not in Coll` | negated membership check |
| `not Goal` | negation as failure |

---

??? abstract "Test Fixtures Summary"

    | Fixture | Predicates under test |
    |---------|----------------------|
    | `tests/fixtures/edge_graph.clausal` | user-defined `edge/2`, `reach/2` |
    | `tests/fixtures/fibonacci.clausal` | user-defined `fib/2` |
    | `tests/fixtures/dynamic_pred.clausal` | `-dynamic` directive, `color/2` |
    | `tests/fixtures/static_pred.clausal` | `-discontiguous` directive |
    | `tests/fixtures/tabled_fib.clausal` | `-table` directive, tabled `fib/2` |
    | `tests/fixtures/tabled_path.clausal` | tabled `path/2`, cyclic graph |
    | `tests/fixtures/tabled_mutual_rec.clausal` | tabled mutual recursion |
    | `tests/fixtures/tabled_left_rec.clausal` | tabled left recursion |
    | `tests/fixtures/tabled_same_gen.clausal` | tabled same-generation |
    | `tests/fixtures/tabled_ite.clausal` | `if_/3` with tabled predicate |
    | `tests/fixtures/clpfd_queens.clausal` | `in_domain/3`, `all_different/1`, `label/1` |
    | `tests/fixtures/clpfd_sendmore.clausal` | `in_domain/3`, `all_different/1`, `label/1` |
    | `tests/fixtures/wfs_win.clausal` | well-founded semantics, `not` on tabled |
    | `tests/fixtures/wfs_win_asym.clausal` | well-founded semantics, asymmetric |
    | `tests/fixtures/reified_memberd.clausal` | `if_/3`, `dif/2` (reified ITE) |
    | `tests/fixtures/reified_max.clausal` | `if_/3` with arithmetic |
    | `tests/fixtures/reif_eq_test.clausal` | `eq/3` |
    | `tests/fixtures/once_member.clausal` | `once/1` |
    | `tests/fixtures/meta_test.clausal` | `findall/3`, `setof/3`, `forall/2`, `in_/2` |
    | `tests/fixtures/builtins_inspect.clausal` | `functor/3`, `arg/3`, `unpack/2` |
    | `tests/clausal_modules/term_inspection.clausal` | `copy_term/2`, `term_variables/2`, `numbervars/3` |
    | `tests/fixtures/builtins_db.clausal` | `assertz/1`, `asserta/1`, `retract/1` |
    | `tests/fixtures/builtins_types.clausal` | `var/1`, `nonvar/1`, `is_str/1`, `number/1`, `integer/1`, `float_/1`, `compound/1`, `callable_/1`, `is_list/1`, `ground/1` |
    | `tests/fixtures/builtins_arith.clausal` | `between/3`, `succ/2`, `plus/3`, `abs_/2`, `max_/3`, `min_/3` |
    | `tests/fixtures/builtins_lists.clausal` | `in_/2`, `in_check/2`, `append/3`, `length/2`, `last/2`, `reverse/2`, `list_item/3`, `flatten/2`, `msort/2`, `sort/2`, `permutation/2`, `select/3`, `subtract/3`, `intersection/3`, `union/3`, `list_to_set/2`, `sum_list/2`, `max_list/2`, `min_list/2`, `pairs_keys_values/3`, `pairs_keys/2`, `pairs_values/2` |
    | `tests/fixtures/builtins_higher_order.clausal` | `maplist/2`, `maplist/3`, `include/3`, `exclude/3`, `foldl/4` |
    | `tests/fixtures/list_util.clausal` | `take/3`, `drop/3`, `split_at/4`, `zip_/3`, `replicate/3`, `split_with/3`, `take_while/3`, `drop_while/3`, `span/4`, `group_by/3`, `sort_by/3`, `max_by/3`, `min_by/3`, `filter_map/3` |
    | `tests/fixtures/builtins_keywords.clausal` | `vary/3`, `unbound_keys/2`, `signature/3` |
    | `tests/fixtures/builtins_dif.clausal` | `dif/2`, `eq/3`, `dif_t/3` |
    | `tests/fixtures/builtins_call.clausal` | `Call/N`, `call_goal/N` |
    | `tests/fixtures/coroutining.clausal` | `call_nth/2`, `count_all/2`, `setup_call_cleanup/3`, `call_cleanup/2`, `freeze/2`, `when/2` |
    | `tests/test_python_interop.py` | `++()` Python interop (13 tests) |
    | `tests/test_dcg.py` | DCG rules, `phrase/2`, `phrase/3` (26 tests) |
    | `tests/fixtures/dcg_grammar.clausal` | `phrase/2`, `phrase/3`, DCG with non-terminals, inline goals, pushback, negation |
    | `tests/fixtures/clpb_circuit.clausal` | `sat/1`, `bool_labeling/1`, `BoolEq` — HalfAdder, FullAdder, PigeonHole |
    | `tests/fixtures/logging_basic.clausal` | `get_logger`, `set_level`, `get_level`, `is_enabled_for`, `debug`, `info`, `warning`, `error`, `critical`, `log`, `stream_handler`, `set_formatter`, `add_handler`, `remove_handler` |
    | `tests/test_date_time.py` (99 tests) | `now`, `now_utc`, `today`, `date`, `time`, `datetime`, `timedelta`, `date_add`, `date_sub`, `date_diff`, `datetime_string`, `weekday`, `date_between`, `timestamp`, `datetime_string_iso`, `date_string_iso` |
    | `packages/clausal-yaml/tests/test_yaml_module.py` | `Read`, `write`, `ReadAll`, `WriteAll`, `ReadFile`, `WriteFile`, `Get` (45 tests) |
