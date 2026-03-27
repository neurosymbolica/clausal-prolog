# Clausal Predicate Index

Complete index of all built-in and standard-library predicates. Predicates are listed as `Name/arity`.

Notation in signature lines:
- `+` = must be bound (input)
- `-` = output (unified with result)
- `?` = either input or output

---

??? abstract "Builtin Predicate Classes"

    Every built-in predicate has a constructable `PredicateMeta` class, so you can build canonical term trees in Python:

    ```python
    from clausal.logic.builtins import get_builtin_class
    from clausal.logic.variables import Var

    append = get_builtin_class("append")
    between = get_builtin_class("between")

    X_ = Var()
    Z_ = Var()

    # Positional construction
    t = append([1, 2], [3, 4], Z_)
    # → append(l1=[1, 2], l2=[3, 4], l3=Var())

    # Keyword construction with partial fill (missing fields → Var())
    t2 = between(low=1, high=10)
    # → between(low=1, high=10, x=Var())

    # Pattern matching works via __match_args__
    match t:
        case append(a, b, c):
            print(a, b, c)
    ```

    Each builtin class is a full `PredicateMeta` with `_fields`, `_functor`, `_arity`, `__eq__`, `__repr__`, and `__match_args__`. Stateless builtins also have `_dispatch_fn` set (so `_get_dispatch()` works directly). DB-dependent builtins (assertz, retract, etc.) have `_dispatch_fn = None` since they need a live database; use them for term construction only.

    **Passing builtins to higher-order predicates:** Builtin predicates can be passed directly as arguments to `maplist`, `include`, `exclude`, `foldl`, `Call/N`, and other higher-order builtins — no lambda wrapper is needed:

    ```
    AllNumbers(XS) <- maplist(number, XS)
    KeepInts(XS, INTS) <- include(integer, XS, INTS)
    Incremented(XS, YS) <- maplist(succ, XS, YS)
    ```

    This works for any builtin or user-defined predicate whose arity matches what the higher-order predicate expects.

    **Multi-arity builtins** (maplist/2,3 and phrase/2,3) are wrapped in `MultiArityBuiltin`, which routes `__call__` by argument count:

    ```python
    maplist = get_builtin_class("maplist")
    maplist(goal, [1, 2])           # → maplist/2 term
    maplist(goal, [1, 2], [2, 4])   # → maplist/3 term
    ```

    All builtin classes are locked (`_locked = True`) — they cannot be modified via assertz/retract.

    **Registry access:**
    - `get_builtin_class(functor)` — returns the class or `MultiArityBuiltin`, or `None`
    - `_BUILTIN_CLASSES` — dict mapping functor name → class/wrapper
    - `_BUILTIN_FIELDS` — dict mapping `(functor, arity)` → field name tuple

    **Tests:** `tests/test_builtin_classes.py` (41 tests)

    ---

## Summary

| Category | Predicates |
|---|---|
| [Control Flow](#control-flow) | once, Not, If/3, throw/1, Catch/2, catch_recover/3, catch/3, halt/0,1, setup_call_cleanup/3, call_cleanup/2 |
| [Coroutining](#coroutining) | freeze/2, when/2 |
| [Meta-Predicates](#meta-predicates) | findall/3, bagof/3, setof/3, forall/2, call_nth/2, count_all/2 |
| [Higher-Order Call](#higher-order-call) | Call/1..8, CallGoal/1..8 |
| [DCG (Definite Clause Grammars)](#dcg-definite-clause-grammars) | phrase/2, phrase/3 |
| [Term Inspection](#term-inspection) | functor/3, arg/3, unpack/2, copy_term/2, term_variables/2, numbervars/3, gensym/2 |
| [Runtime Database](#runtime-database) | assertz/1, asserta/1, retract/1, abolish_table/2, abolish_all_tables/0 |
| [Keyword-Term Introspection](#keyword-term-introspection) | vary/3, extend/3, unbound_keys/2, signature/3 |
| [Attributed Variables](#attributed-variables) | put_attr/3, get_attr/3, del_attr/2, get_attrs/2, put_attrs/2, attvar/1, term_attvars/2 |
| [Constraint Predicates](#constraint-predicates) | dif/2, eq/3, dif_t/3 |
| [CLP(ℤ) — Finite Domain Constraints](#clpfd-finite-domain-constraints) | in_domain/3, label/1, all_different/1, equivalent/2, sum_/3, scalar_product/4, element/3, circuit/1 |
| [CLP(B) — Boolean Constraints](#clpb-boolean-constraints) | sat/1, taut/2, sat_count/2, bool_labeling/1 |
| [Type Checks](#type-checks) | var/1, nonvar/1, atom/1, is_str/1, number/1, integer/1, float_/1, compound/1, callable_/1, is_list/1, ground/1, must_be/2, can_be/2 |
| [Dict and Set Predicates](#dict-and-set-predicates) | is_dict/1, dict_get/3, dict_put/4, dict_merge/3, gen_dict/3, sub_dict/2, is_set/1, set_union/3, set_subset/2, gen_set/2 |
| [Arithmetic](#arithmetic) | between/3, succ/2, plus/3, abs_/2, max_/3, min_/3, sign/2, gcd/3, divmod_/4, lcm/3, exp_mod/4, popcount/2, msb/2, lsb/2 |
| [List Predicates](#list-predicates) | in_/2, append/3, length/2, reverse/2, sort/2, permutation/2, select/3, flatten/2, take/3, drop/3, zip_/3, split_with/3, numlist/2,3, same_length/2, transpose/2 |
| [Higher-Order List Predicates](#higher-order-list-predicates) | maplist/2,3, include/3, exclude/3, partition/4, tfilter/3, tpartition/4, foldl/4, take_while/3, drop_while/3, span/4, group_by/3, sort_by/3, filter_map/3 |
| [Character/String](#characterstring) | char_type/2, char_code/2, upcase_atom/2, downcase_atom/2, atom_length/2, atom_chars/2, atom_codes/2, atom_concat/3, sub_atom/5, number_chars/2, number_codes/2 |
| [I/O](#io) | write/1, writeln/1, print_term/1, nl/0, tab/1, write_to_string/2, term_to_string/2, listing/1, portray_clause/1 |
| [Logging (`log` module)](#logging-log-module) | GetLogger, Debug, Info, Warning, Error, Critical, Log, SetLevel, GetLevel, StreamHandler, FileHandler |
| [Date & Time (`date_time` module)](#date--time-date_time-module) | Now, Today, Date, Time, DateTime, DateAdd, DateSub, DateDiff, FormatDate, ParseDate, DateBetween |
| [YAML (`yaml_module` module)](#yaml-yaml_module-module) | Read, write, ReadAll, WriteAll, ReadFile, WriteFile, Get |
| [Time & statistics](#time--statistics) | current_time/1, statistics/2 |
| [Operator Syntax (Compiler Special Forms)](#operator-syntax-compiler-special-forms) | `is`, `==`, `:=`, `!=`, `<`, `<=`, `>`, `>=`, `in`, `not in`, `not`, `If` |

---

## Control Flow

These are **compiler special forms** — transformed at compile time, not dispatched via the builtin registry.

### `once/1`
```clausal
# skip
once(+Goal)
```
Commit to the first solution of `Goal`; succeeds at most once even if `Goal` has multiple solutions.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py:1619` (`_compile_once`)
    **Clausal tests:** `tests/fixtures/once_member.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Not/1`
```clausal
# skip
not +Goal
```
Negation as failure (NAF). Succeeds if `Goal` has no solutions. Written as `not goal` in clause bodies.
For tabled predicates, uses well-founded semantics (delayed negation via `_naf_tabled`).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py:1507`
    **Clausal tests:** `tests/fixtures/wfs_win.clausal`, `tests/fixtures/wfs_win_asym.clausal`
    **Python tests:** `tests/test_compiled_programs.py`, `tests/test_wfs.py`

---

### `If/3` (If-Then-Else)
```clausal
# skip
If(+Cond, +Then, +Else)
```
If `Cond` has a solution, run `Then`; otherwise run `Else`. Soft-cut: only the first solution of `Cond` is tried. Compiles to a reified if-then-else that propagates constraints in both branches.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py` (`_compile_ite_trampoline`)
    **Clausal tests:** `tests/fixtures/reified_memberd.clausal`, `tests/fixtures/tabled_ite.clausal`, `tests/fixtures/reified_max.clausal`
    **Python tests:** `tests/test_reified_ite.py`

---

### `throw/1`
```clausal
# skip
throw(+Term)
```
Raise a logic-level exception carrying `Term`. The exception propagates through the generator/trampoline chain until caught by `catch/3` or surfaces as a Python `LogicException`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py` (`_compile_throw`)
    **Exception class:** `clausal/logic/exceptions.py` (`LogicException`)
    **Clausal tests:** `tests/clausal_modules/exceptions.clausal`
    **Python tests:** `tests/test_exceptions.py`

---

### `Catch/2`
```clausal
# skip
Catch(+Goal, ?Error)
```
Execute `Goal`. If an exception is raised (logic or Python), unify `Error` against the exception term and succeed. If `Goal` succeeds without throwing, `Catch/2` is transparent — all solutions pass through.

Python exceptions appear as `ClassName(Message)` — the same shape as any logic term — so no special handling is needed. `Catch/2` never re-raises; it is equivalent to `catch(Goal, Error, true)`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py` (`_compile_catch`)
    **Python tests:** `tests/test_units.py::TestPythonExceptionCatch`

---

### `catch_recover/3`
```clausal
# skip
catch_recover(+Goal, ?Error, +Recovery)
```
Execute `Goal`. If an exception is raised, unify `Error` against the exception term, then execute `Recovery`. Like `Catch/2` but with an explicit recovery goal.

`catch_recover` never re-raises. For selective catch with re-raise on mismatch, use `catch/3`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py` (`_compile_catch`)

---

### `catch/3`
```clausal
# skip
catch(+Goal, ?Catcher, +Recovery)
```
Execute `Goal`. If `Goal` throws, unify the thrown term with `Catcher`. If unification succeeds, execute `Recovery`; otherwise re-raise. If `Goal` succeeds without throwing, `catch/3` is transparent — all solutions pass through.

Python exceptions are wrapped as `ClassName(Message)` before unification against `Catcher`. Trail bindings from the failing goal are undone before recovery runs.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py` (`_compile_catch`, `_compile_catch_trampoline`)
    **Clausal tests:** `tests/clausal_modules/exceptions.clausal`
    **Python tests:** `tests/test_exceptions.py`

---

### `halt/0`, `halt/1`
```clausal
# skip
halt
halt(+Code)
```
Terminate execution by raising `SystemExit`. `halt/0` exits with code 0; `halt/1` exits with the given code.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py` (inline in `compile_goal`/`compile_goal_trampoline`)
    **Python tests:** `tests/test_exceptions.py`

---

### `setup_call_cleanup/3`
```clausal
# skip
setup_call_cleanup(+Setup, +Call, +Cleanup)
```
Deterministic resource management (`try/finally` for logic). Setup runs once (first solution only). Call runs normally. Cleanup runs **exactly once** regardless of how Call terminates — success, failure, or exception. If Setup fails, Cleanup does not run.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py` (`_compile_setup_call_cleanup`)
    **Python tests:** `tests/test_coroutining.py::TestSetupCallCleanup`
    **Clausal tests:** `tests/fixtures/coroutining.clausal`

---

### `call_cleanup/2`
```clausal
# skip
call_cleanup(+Call, +Cleanup)
```
Sugar for `setup_call_cleanup(true, Call, Cleanup)` — no setup step, just guaranteed cleanup.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py` (`_compile_setup_call_cleanup`)
    **Python tests:** `tests/test_coroutining.py::TestCallCleanup`
    **Clausal tests:** `tests/fixtures/coroutining.clausal`

---

## Coroutining

Coroutining predicates delay goal execution until variables are bound. They use the attributed variable hook infrastructure.

*Full documentation: [Coroutining](coroutining.md)*

### `freeze/2`
```clausal
# skip
freeze(?X, +Goal)
```
Delay `Goal` until `X` is bound. If `X` is already bound, runs `Goal` immediately. If `X` is unbound, attaches Goal as an attribute; when `X` is later unified, the frozen goal fires synchronously — failure rejects the unification.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py` (`_compile_freeze`), `clausal/logic/coroutining.py` (`_freeze_hook`)
    **Python tests:** `tests/test_coroutining.py::TestFreeze`
    **Clausal tests:** `tests/fixtures/coroutining.clausal`

---

### `when/2`
```clausal
# skip
when(+Condition, +Goal)
```
Generalized coroutining: delay `Goal` until `Condition` is satisfied. Supported conditions: `nonvar(X)`, `ground(X)`, conjunction `(C1, C2)`, disjunction `(C1 ; C2)`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py` (`_compile_when`), `clausal/logic/coroutining.py` (`_install_when_ground`, `_install_when_disjunction`)
    **Python tests:** `tests/test_coroutining.py::TestWhen`
    **Clausal tests:** `tests/fixtures/coroutining.clausal`

---

## Meta-Predicates

These are **compiler special forms** recognized by name in `compile_goal`/`compile_goal_trampoline`. Inner goals compile in simple mode as sub-generators.

### `findall/3`
```clausal
# skip
findall(+Template, +Goal, -Bag)
```
Collect all bindings of `Template` produced by `Goal` into `Bag` (a list). Succeeds with `[]` if `Goal` has no solutions.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py:1623` (`_compile_find_all_core`)
    **Clausal tests:** `tests/fixtures/meta_test.clausal`
    **Python tests:** `tests/test_meta.py`

---

### `bagof/3`
```clausal
# skip
bagof(+Template, +Goal, -Bag)
```
Like `findall/3` but fails if `Goal` has no solutions. Bag preserves duplicate solutions.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py:1630`
    **Clausal tests:** `tests/fixtures/meta_test.clausal`
    **Python tests:** `tests/test_meta.py`

---

### `setof/3`
```clausal
# skip
setof(+Template, +Goal, -Set)
```
Like `bagof/3` but removes duplicates and sorts the result.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py:1637`
    **Clausal tests:** `tests/fixtures/meta_test.clausal`
    **Python tests:** `tests/test_meta.py`

---

### `forall/2`
```clausal
# skip
forall(+Cond, +Action)
```
Universal quantification: succeeds if `Action` succeeds for every solution of `Cond`. Desugars to `not(Cond and not(Action))`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py:1644`
    **Clausal tests:** `tests/fixtures/meta_test.clausal`
    **Python tests:** `tests/test_meta.py`

---

### `call_nth/2`
```clausal
# skip
call_nth(+Goal, +N)
```
Call `Goal` and succeed only on the **Nth solution** (1-indexed). Skips the first N-1 solutions. Fails if Goal has fewer than N solutions. Raises `type_error` if N is not a positive integer.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py` (`_compile_call_nth`)
    **Python tests:** `tests/test_coroutining.py::TestCallNth`
    **Clausal tests:** `tests/fixtures/coroutining.clausal`

---

### `count_all/2`
```clausal
# skip
count_all(+Goal, -Count)
```
Count the number of solutions of `Goal` without collecting them. Unifies `Count` with the integer result. Bindings from the inner goal are not visible after counting (the trail is unwound).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py` (`_compile_count_all`)
    **Python tests:** `tests/test_coroutining.py::TestCountAll`
    **Clausal tests:** `tests/fixtures/coroutining.clausal`

---

## Time & statistics

### `current_time/1`
```clausal
# skip
current_time(-T)
```
Unify T with the current Unix timestamp as a float (seconds since epoch).

---

### `statistics/2`
```clausal
# skip
statistics(?Key, -Value)
```
Query runtime statistics. With Key bound, looks up a specific stat. With Key unbound, enumerates all available stats via backtracking.

| Key | Value |
|---|---|
| `"wall_time"` | Wall-clock seconds since process start (float) |
| `"cpu_time"` | CPU seconds used by this process (float) |
| `"memory"` | Peak RSS memory in bytes (int, Linux/macOS only) |

---

## Higher-Order Call

### `Call/1..8`
```clausal
# skip
Call(+Goal)
Call(+Goal, +A1)
Call(+Goal, +A1, +A2)
...
Call(+Goal, +A1, ..., +A7)
```
Call `Goal` (a lambda or dispatch function) with 0–7 extra arguments appended. Aliases for `CallGoal/1..8`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1532` (alias registration)
    **Clausal tests:** `tests/fixtures/builtins_call.clausal`
    **Python tests:** `tests/test_meta.py`, `tests/test_higher_order.py`

---

### `CallGoal/1`, `CallGoal/2`, `CallGoal/3`
```clausal
# skip
CallGoal(+Goal)
CallGoal(+Goal, +A1)
CallGoal(+Goal, +A1, +A2)
```
Core implementation of higher-order call. `Goal` must be a callable (lambda or `_get_dispatch()` object). `CallGoal/4..8` are generated via `_make_call_goal_n`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1479`
    **Clausal tests:** `tests/fixtures/builtins_call.clausal`
    **Python tests:** `tests/test_meta.py`, `tests/test_higher_order.py`

---

## DCG (Definite Clause Grammars)

### `phrase/2`
```clausal
# skip
phrase(+RuleBody, +List)
```
Invoke a DCG rule and require it to consume the entire input list. `RuleBody` is either a predicate class (0 extra args, e.g. `greeting`) or a partial term (N extra args, e.g. `digit(D)`). equivalent to calling the rule with `List` as the input state and `[]` as the output state.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`_phrase__2`)
    **Python tests:** `tests/test_dcg.py`

---

### `phrase/3`
```clausal
# skip
phrase(+RuleBody, +List, ?Rest)
```
Invoke a DCG rule for partial parsing. Like `phrase/2`, but the remaining unconsumed input is unified with `Rest` instead of requiring `[]`.

Also used for **state-passing DCGs**: encode state as a single-element list `[State]`, thread it through DCG nonterminals using `phrase(Rule, [InitialState], [FinalState])`. See [syntax.md](syntax.md#dcgs-as-general-state-passing) for the full pattern.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`_phrase__3`)
    **Python tests:** `tests/test_dcg.py`

---

### `sequence//1`
```clausal
# skip
sequence(+List)   % as DCG non-terminal: sequence(List, S0, S)
```
DCG non-terminal that matches a list of terminals in sequence. `sequence([a, b, c])` consumes `a`, `b`, `c` from the input. equivalent to inlining the terminals as a grammar rule body.

```clausal
# skip
phrase(sequence(["hello", "world"]), ["hello", "world"])       % succeeds
phrase(sequence(["a", "b"]), ["a", "b", "c"], REST)            % REST = ["c"]
```

---

## Term Inspection

### `functor/3`
```clausal
# skip
functor(+Term, -Name, -Arity)   % decompose
functor(-Term, +Name, +Arity)   % construct
```
Decompose a term into its functor name and arity, or construct a term from a name and arity (fields are fresh vars).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:353`
    **Clausal tests:** `tests/fixtures/builtins_inspect.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `arg/3`
```clausal
# skip
arg(+N, +Term, -arg)
```
Unify `arg` with the `N`-th argument of `Term` (1-based indexing).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:394`
    **Clausal tests:** `tests/fixtures/builtins_inspect.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `unpack/2`
```clausal
# skip
unpack(+Term, -List)   % decompose: List = [functor | Args]
unpack(-Term, +List)   % construct: Term from [functor | Args]
```
Decompose a term to `[functor | args]` list, or construct a term from such a list. (Prolog's `=..` operator.)

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:413`
    **Clausal tests:** `tests/fixtures/builtins_inspect.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `copy_term/2`
```clausal
# skip
copy_term(+Original, -Copy)
```
Unify `Copy` with a deep copy of `Original` where every unbound `Var` is replaced by a fresh one. Structural sharing is preserved: if the same `Var` appears in multiple positions in `Original`, the same fresh `Var` appears in all corresponding positions of `Copy`. Already-bound variables are followed and their values are copied rather than replaced.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`_copy_term`, `copy_term/2`)
    **Clausal tests:** `tests/clausal_modules/term_inspection.clausal`
    **Python tests:** `tests/test_term_inspection.py`

---

### `term_variables/2`
```clausal
# skip
term_variables(+Term, -Vars)
```
Unify `Vars` with a list of all unbound `Var`s in `Term`, collected left-to-right with duplicates removed (same `Var` appearing multiple times in `Term` appears only once in `Vars`). Bound variables are followed and not collected.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`_collect_vars`, `term_variables/2`)
    **Clausal tests:** `tests/clausal_modules/term_inspection.clausal`
    **Python tests:** `tests/test_term_inspection.py`

---

### `numbervars/3`
```clausal
# skip
numbervars(+Term, +Start, -End)
```
Number all unbound `Var`s in `Term` left-to-right, binding each to `Compound("$VAR", (N,))` where `N` starts at `Start` and increments. `End` is unified with the next unused number after all variables are numbered. Useful for pretty-printing terms with named variables. `Start` must be a bound integer.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`numbervars/3`)
    **Clausal tests:** `tests/clausal_modules/term_inspection.clausal`
    **Python tests:** `tests/test_term_inspection.py`

---

### `gensym/2`
```clausal
# skip
gensym(+Prefix, -Atom)
```
Generate a unique atom by appending a monotonically increasing counter to `Prefix`. `gensym("x", A)` produces `"x_1"`, `"x_2"`, etc. on successive calls. The counter is **not trailed** — it survives backtracking (impure, matches Prolog's `gensym/2`). Thread-safe via lock. Different prefixes maintain independent counters. `Prefix` must be a bound string; unbound or non-string prefix → fail.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/inspection.py` (`gensym/2`)
    **Python tests:** `tests/test_term_inspection.py`

---

## Runtime Database

These predicates require a live `Database` reference (`_DB_BUILTINS`). They recompile the affected predicate after modification.

### `assertz/1`
```clausal
# skip
assertz(+Clause)
```
Add `Clause` (a fact or rule) at the **end** of its predicate's clause list. Fails on locked (non-dynamic) predicates. Ground compound facts are normalized to `Var+Is` form for output-mode queries.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:507`
    **Clausal tests:** `tests/fixtures/builtins_db.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `asserta/1`
```clausal
# skip
asserta(+Clause)
```
Add `Clause` at the **front** of its predicate's clause list.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:545`
    **Clausal tests:** `tests/fixtures/builtins_db.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `retract/1`
```clausal
# skip
retract(+Term)
```
Remove the **first** clause whose head unifies with `Term`. Not backtrackable — removes exactly one clause per call. Fails on locked predicates.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:580`
    **Clausal tests:** `tests/fixtures/builtins_db.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `abolish_table/2`
```clausal
# skip
abolish_table(+functor, +Arity)
```
Remove all cached answers for the named tabled predicate, forcing re-computation on the next call.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:661`
    **Clausal tests:** none
    **Python tests:** `tests/test_tabling.py`

---

### `abolish_all_tables/0`
```clausal
# skip
abolish_all_tables
```
Remove all cached tabling answers for every predicate in the current database.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:678`
    **Clausal tests:** none
    **Python tests:** `tests/test_tabling.py`

---

## Keyword-Term Introspection

These predicates operate on `KWTerm` (open-world keyword terms) and `PredicateMeta` term instances.

### `vary/3`
```clausal
# skip
vary(+Overrides, +Term, -NewTerm)
```
Produce a copy of `Term` with field values replaced by `Overrides` (a Python `dict`). Works on functor dataclass instances and `KWTerm`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:692`
    **Clausal tests:** `tests/fixtures/builtins_keywords.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `extend/3`
```clausal
# skip
extend(+Additions, +Term, -NewTerm)
```
Produce a copy of `Term` (must be a `KWTerm`) with additional fields from `Additions` (a Python `dict`). Dataclass terms have fixed schemas so only `KWTerm` is supported.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:727`
    **Clausal tests:** `tests/fixtures/builtins_keywords.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `unbound_keys/2`
```clausal
# skip
unbound_keys(+Term, -Keys)
```
Unify `Keys` with a list of field names whose values are unbound `Var`s in `Term`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:754`
    **Clausal tests:** `tests/fixtures/builtins_keywords.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `signature/3`
```clausal
# skip
signature(+FunctorName, +Arity, -Names)
```
Reflect the registered parameter name list for the predicate `FunctorName/Arity`. Fails if no signature is registered.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:778`
    **Clausal tests:** `tests/fixtures/builtins_keywords.clausal`
    **Python tests:** `tests/test_builtins.py`

---

## Attributed Variables

Attributed variables carry key-value metadata that survives through unification. This is the mechanism that powers CLP(ℤ), CLP(B), CLP(ℝ), dif/2, and units constraints internally. These predicates expose the API so users can build custom constraint solvers.

Attribute keys are strings. Attribute values can be any term. All mutations are trailed (undone on backtracking).

### `put_attr/3`
```clausal
# skip
put_attr(+Var, +Key, +Value)
```
Attach attribute `Value` under string `Key` to an unbound variable. Overwrites any existing value for that key. Trailed.

---

### `get_attr/3`
```clausal
# skip
get_attr(+Var, +Key, -Value)
```
Retrieve the attribute stored under `Key`. Fails if `Var` has no attribute for `Key`, or if `Var` is not an unbound variable.

---

### `del_attr/2`
```clausal
# skip
del_attr(+Var, +Key)
```
Remove the attribute under `Key`. Succeeds even if no attribute existed (no-op). Trailed.

---

### `get_attrs/2`
```clausal
# skip
get_attrs(+Var, -Attrs)
```
Unify `Attrs` with a `DictTerm` containing all attributes on `Var`. Empty `DictTerm` if no attributes.

---

### `put_attrs/2`
```clausal
# skip
put_attrs(+Var, +Attrs)
```
Set multiple attributes from a `DictTerm`. Each key-value pair is applied via `put_attr`.

---

### `attvar/1`
```clausal
# skip
attvar(?Var)
```
Succeeds if `Var` is an unbound variable with at least one attribute. Fails for bound terms and for bare (non-attributed) variables.

---

### `term_attvars/2`
```clausal
# skip
term_attvars(+Term, -Vars)
```
Collect all attributed variables occurring in `Term` into a list. Traverses compound terms, lists, DictTerms, and PredicateMeta instances recursively. Each variable appears at most once.

---

## Constraint Predicates

### `dif/2`
```clausal
# skip
dif(+X, +Y)
```
Disequality constraint. Succeeds if `X` and `Y` can remain different (posts a constraint if either is unbound). Implemented via attributed variables; propagates through unification.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:801` → `clausal/logic/constraints.py`
    **Clausal tests:** `tests/fixtures/builtins_dif.clausal`
    **Python tests:** `tests/test_dif.py`

---

### `eq/3` (reified)
```clausal
# skip
eq(+X, +Y, -T)
```
Reified equality. `T` is unified with `True` if `X = Y`, `False` if `dif(X, Y)`. Suspends if neither is determined yet.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:812` → `clausal/logic/reif.py`
    **Clausal tests:** `tests/fixtures/reif_eq_test.clausal`, `tests/fixtures/builtins_dif.clausal`
    **Python tests:** `tests/test_reif_builtins.py`

---

### `dif_t/3` (reified)
```clausal
# skip
dif_t(+X, +Y, -T)
```
Reified disequality. `T` is `True` if `dif(X, Y)`, `False` if `X = Y`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:819` → `clausal/logic/reif.py`
    **Clausal tests:** `tests/fixtures/builtins_dif.clausal`
    **Python tests:** `tests/test_reif_builtins.py`

---

## CLP(ℤ) — Finite Domain Constraints

CLP(ℤ) operators (`==`, `!=`, `<`, `<=`, `>`, `>=`) are handled as **compiler special forms** mapping to `_fd_eq`, `_fd_ne`, `_fd_lt`, `_fd_le`, `_fd_gt`, `_fd_ge`. The predicates below are the builtin-registry interface.

### `in_domain/3`
```clausal
# skip
in_domain(+VarOrList, +Lo, +Hi)
```
Post the finite domain `[Lo, Hi]` on a logic variable or a list of logic variables.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:829` → `clausal/logic/clpfd.py`
    **Clausal tests:** `tests/fixtures/clpfd_queens.clausal`, `tests/fixtures/clpfd_sendmore.clausal`
    **Python tests:** `tests/test_clpfd.py`

---

### `label/1`
```clausal
# skip
label(+Vars)
```
Enumerate concrete values for a list of FD-constrained variables, backtracking over all consistent assignments.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:837` → `clausal/logic/clpfd.py`
    **Clausal tests:** `tests/fixtures/clpfd_queens.clausal`, `tests/fixtures/clpfd_sendmore.clausal`
    **Python tests:** `tests/test_clpfd.py`

---

### `all_different/1`
```clausal
# skip
all_different(+Vars)
```
Post an all-different constraint on a list of FD variables. Propagates bounds and eliminates assigned values from other domains.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:844` → `clausal/logic/clpfd.py`
    **Clausal tests:** `tests/fixtures/clpfd_queens.clausal`, `tests/fixtures/clpfd_sendmore.clausal`
    **Python tests:** `tests/test_clpfd.py`

---

### `equivalent/2`
```clausal
# skip
equivalent(+T1, +T2)
```
Structural equality test (old `==` behavior before CLP(ℤ) remapping). Succeeds if `T1` and `T2` are structurally identical after dereferencing.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:852` → `clausal/logic/clpfd.py`
    **Clausal tests:** none
    **Python tests:** `tests/test_clpfd.py`

---

### `sum_/3`
```clausal
# skip
sum_(+Vars, +Op, +Value)
```
Constrain the sum of `Vars` (a list of FD variables or integers) under comparison operator `Op` to `Value`. Supported operators: `#=`, `#<`, `#>`, `#=<`, `#>=`, `#\=`.

```clausal
# skip
sum_([X, Y, Z], "#=", 10)   % X + Y + Z = 10
```

For `#=`, posts a `SumConstraint` that propagates bounds in both directions: narrows `Value` to `[min_sum, max_sum]` and narrows each variable using the remaining slack. For inequality operators, an intermediate variable is introduced and chained with the appropriate binary relational constraint. Ground lists with a ground `Value` are checked immediately without posting a constraint.

---

### `scalar_product/4`
```clausal
# skip
scalar_product(+Coeffs, +Vars, +Op, +Value)
```
Weighted sum constraint: `Σ(Coeffs[i] * Vars[i]) Op Value`. Coefficients must be ground integers. Lists must be the same length. Supports negative coefficients — division direction is flipped accordingly when narrowing individual variables.

```clausal
# skip
scalar_product([2, 3], [X, Y], "#=", 12)   % 2X + 3Y = 12
```

Uses the same bounds-consistency approach as `sum_/3` (`ScalarProductConstraint`). For inequality operators, an intermediate variable is introduced and chained with a binary relational constraint.

---

### `element/3`
```clausal
# skip
element(?Index, +List, ?Value)
```
`Value` is the `Index`-th element of `List` (1-based indexing). when Index is ground, performs direct lookup. when Index is an FD variable, posts an `ElementConstraint` that propagates bidirectionally: narrows `Index` to positions whose list element overlaps `Value`'s domain, and narrows `Value` to the union of the domains at valid positions. Then enumerates the surviving valid indices.

```clausal
# skip
element(2, [10, 20, 30], V)   % V = 20
element(I, [10, 20, 30], 20)  % I = 2 (propagated without labeling)
```

---

### `circuit/1`
```clausal
# skip
circuit(+Vars)
```
Constrain `Vars` to form a single Hamiltonian circuit. `Vars[i] = j` means the successor of node `i+1` is node `j` (1-based). Posts a `CircuitConstraint` that: restricts all domains to `[1, n]`, removes self-loop values, enforces all_different, and detects premature sub-tours via forced-chain analysis — pruning values that would close a cycle shorter than `n`. Labeling then enumerates remaining candidates.

```clausal
# skip
circuit([2, 3, 1])         % valid: 1→2→3→1
% circuit([1, 2, 3]) fails — self-loop at node 1
% circuit([2, 1, 4, 3]) fails — two sub-tours (detected during propagation)
```

---

## CLP(B) — Boolean Constraints

CLP(B) uses reduced ordered BDDs (Binary Decision Diagrams) for Boolean constraint solving. Expressions use Python's bitwise operators: `&` (AND), `|` (OR), `^` (XOR), `~` (NOT), plus `BoolEq` (equivalence) and `BoolImpl` (implication) term constructors.

### `sat/1`
```clausal
# skip
sat(+Expr)
```
Post a Boolean constraint. The expression must evaluate to true. Fails if unsatisfiable. Propagates forced values (e.g., `sat(X & Y)` forces both to 1).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/constraints.py` → `clausal/logic/clpb.py`
    **Clausal tests:** `tests/fixtures/clpb_circuit.clausal`
    **Python tests:** `tests/test_clpb.py`

---

### `taut/2`
```clausal
# skip
taut(+Expr, -T)
```
Tautology check. Unify `T` with 1 if `Expr` is always true, 0 if always false. Fail if indeterminate.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/constraints.py` → `clausal/logic/clpb.py`
    **Clausal tests:** none
    **Python tests:** `tests/test_clpb.py`

---

### `sat_count/2`
```clausal
# skip
sat_count(+Expr, -N)
```
Count the number of satisfying assignments for `Expr`. Unify `N` with the count.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/constraints.py` → `clausal/logic/clpb.py`
    **Clausal tests:** none
    **Python tests:** `tests/test_clpb.py`

---

### `bool_labeling/1`
```clausal
# skip
bool_labeling(+Vars)
```
Enumerate 0/1 assignments for a list of Boolean variables. Backtracks over all satisfying assignments.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/constraints.py` → `clausal/logic/clpb.py`
    **Clausal tests:** `tests/fixtures/clpb_circuit.clausal`
    **Python tests:** `tests/test_clpb.py`

---

## Type Checks

### `var/1`
```clausal
# skip
var(?X)
```
Succeeds if `X` is an unbound logic variable.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:863`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `nonvar/1`
```clausal
# skip
nonvar(?X)
```
Succeeds if `X` is bound (not an unbound `Var`).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:870`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `atom/1`
```clausal
# skip
atom(+X)
```
Succeeds if `X` is a declared atom (a zero-arity PredicateMeta class).
Atoms are created by `-private([red, blue])` or `-module(m, [red])` directives,
or dynamically via `make_atom("name")`. Does not match plain strings — use
`is_str/1` for those.

---

### `is_str/1`
```clausal
# skip
is_str(+X)
```
Succeeds if `X` is a Python `str`. Does not match declared atoms (use
`atom/1` for those).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:877`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `number/1`
```clausal
# skip
number(+X)
```
Succeeds if `X` is an `int` or `float` (excludes `bool`).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:885`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `integer/1`
```clausal
# skip
integer(+X)
```
Succeeds if `X` is an `int` (excludes `bool`).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:897`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `float_/1`
```clausal
# skip
float_(+X)
```
Succeeds if `X` is a Python `float`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:905`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `compound/1`
```clausal
# skip
compound(+X)
```
Succeeds if `X` is a compound term with arity > 0 (`Compound`, `KWTerm`, or `PredicateMeta` instance with at least one field).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:921`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `callable_/1`
```clausal
# skip
callable_(+X)
```
Succeeds if `X` is an atom (string) or a compound term.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:935`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `is_list/1`
```clausal
# skip
is_list(+X)
```
Succeeds if `X` is a Python `list`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:947`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `ground/1`
```clausal
# skip
ground(+X)
```
Succeeds if `X` contains no unbound `Var`s (is fully instantiated).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:954`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `must_be/2`
```clausal
# skip
must_be(+Type, +Term)
```
assertz that `Term` is of the given type. Succeeds silently if it matches. Throws `instantiation_error` if Term is unbound. Throws `type_error(Type, Term, "must_be/2")` if Term is ground but wrong type.

Supported type strings: `"integer"`, `"float"`, `"number"`, `"atom"` / `"string"`, `"list"`, `"boolean"`, `"callable"`, `"dict"`, `"compound"`.

---

### `can_be/2`
```clausal
# skip
can_be(+Type, ?Term)
```
assertz that `Term` could possibly be of the given type. Succeeds if Term is unbound (it could become anything) or already matches the type. Throws `type_error` only when Term is ground and definitely the wrong type. Same type strings as `must_be/2`.

---

## Dict and Set Predicates

Dict and set builtins operate on `DictTerm` and `SetTerm` values. Plain Python `dict` and `set` are not accepted. See [Dicts and Sets](dicts_sets.md) for the full design.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/dict_set.py`
    **Python tests:** `tests/test_dict_set_builtins.py` (79 tests)
    **Fixture:** `tests/fixtures/dict_set_builtins.clausal`

### `is_dict/1`
```clausal
# skip
is_dict(+Term)
```
Succeeds if `Term` is a `DictTerm`.

---

### `dict_size/2`
```clausal
# skip
dict_size(+Dict, -N)
```
`N` is the number of keys in `Dict`.

---

### `dict_keys/2`
```clausal
# skip
dict_keys(+Dict, -Keys)
```
`Keys` is the sorted list of keys (sorted by `repr` for cross-type determinism).

---

### `dict_values/2`
```clausal
# skip
dict_values(+Dict, -Values)
```
`Values` is the list of values in key-sorted order.

---

### `dict_pairs/2`
```clausal
# skip
dict_pairs(?Dict, ?Pairs)
```
Bidirectional: `Dict` ↔ list of `[Key, Value]` 2-element lists. in_ dict→pairs direction, pairs are sorted by key.

---

### `dict_get/3`
```clausal
# skip
dict_get(+Key, +Dict, ?Value)
```
Semidet lookup. Fails if `Key` is absent or unbound.

---

### `dict_put/4`
```clausal
# skip
dict_put(+Key, +Value, +OldDict, -NewDict)
```
Functional update: `NewDict` is `OldDict` with `Key → Value` set. Returns a new `DictTerm`.

---

### `dict_put_pairs/3`
```clausal
# skip
dict_put_pairs(+Pairs, +OldDict, -NewDict)
```
Bulk update from a `[[Key, Value], ...]` list. equivalent to repeated `dict_put/4`.

---

### `dict_remove/3`
```clausal
# skip
dict_remove(+Key, +OldDict, -NewDict)
```
`NewDict` is `OldDict` without `Key`. Fails if `Key` is absent.

---

### `dict_merge/3`
```clausal
# skip
dict_merge(+D1, +D2, -Merged)
```
union of `D1` and `D2`. Where keys conflict, `D2`'s value wins.

---

### `gen_dict/3`
```clausal
# skip
gen_dict(?Key, +Dict, ?Value)
```
Nondeterministic enumeration. Yields one `Key`/`Value` binding per solution on backtracking. Can be filtered by binding `Key` before the call.

---

### `sub_dict/2`
```clausal
# skip
sub_dict(+Pattern, +Dict)
```
Partial dict matching. Succeeds when every key in `Pattern` is present in `Dict` and the values unify. Extra keys in `Dict` are ignored. See [sub_dict](dicts_sets.md#partial-dict-matching--subdict2) for examples.

---

### `is_set/1`
```clausal
# skip
is_set(+Term)
```
Succeeds if `Term` is a `SetTerm`.

---

### `set_size/2`
```clausal
# skip
set_size(+Set, -N)
```
`N` is the cardinality of `Set`.

---

### `set_list/2`
```clausal
# skip
set_list(?Set, ?List)
```
Bidirectional: `Set` ↔ sorted list. in_ list→set direction, duplicates are removed.

---

### `set_union/3`
```clausal
# skip
set_union(+S1, +S2, -union)
```
Set union.

---

### `set_intersection/3`
```clausal
# skip
set_intersection(+S1, +S2, -Inter)
```
Set intersection.

---

### `set_subtract/3`
```clausal
# skip
set_subtract(+S1, +S2, -Diff)
```
`Diff` = elements in `S1` not in `S2`.

---

### `set_sym_diff/3`
```clausal
# skip
set_sym_diff(+S1, +S2, -Sym)
```
Symmetric difference: elements in exactly one of `S1`, `S2`.

---

### `set_subset/2`
```clausal
# skip
set_subset(+Sub, +Super)
```
Succeeds if `Sub` is a subset of `Super` (including equal sets and the empty set).

---

### `set_disjoint/2`
```clausal
# skip
set_disjoint(+S1, +S2)
```
Succeeds if `S1` and `S2` share no elements.

---

### `set_add/3`
```clausal
# skip
set_add(+Elem, +OldSet, -NewSet)
```
`NewSet` is `OldSet` with `Elem` added. No-op if already present.

---

### `set_remove/3`
```clausal
# skip
set_remove(+Elem, +OldSet, -NewSet)
```
`NewSet` is `OldSet` with `Elem` removed. No-op if absent.

---

### `gen_set/2`
```clausal
# skip
gen_set(?Elem, +Set)
```
Nondeterministic enumeration of set elements. Order is deterministic (sorted by `repr`).

---

## Arithmetic

Arithmetic uses `==` to post CLP(ℤ) constraints (e.g., `Y == X * 2`). The predicates below provide relational arithmetic usable in both input and output modes.

### `between/3`
```clausal
# skip
between(+Low, +High, ?X)
```
Check or enumerate integers in `[Low, High]` inclusive. in_ check mode (X bound) succeeds iff `Low ≤ X ≤ High`. in_ generate mode (X unbound) backtracks over each integer.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:964`
    **Clausal tests:** `tests/fixtures/builtins_arith.clausal`
    **Python tests:** `tests/test_builtins.py`, `tests/test_search.py`

---

### `succ/2`
```clausal
# skip
succ(?X, ?Y)   % Y = X + 1
```
Bidirectional successor: if `X` is bound, `Y = X + 1`; if `Y` is bound, `X = Y - 1`. Both must be non-negative integers.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:987`
    **Clausal tests:** `tests/fixtures/builtins_arith.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `plus/3`
```clausal
# skip
plus(?X, ?Y, ?Z)   % Z = X + Y
```
Relational addition: any two of `X`, `Y`, `Z` determine the third.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1008`
    **Clausal tests:** `tests/fixtures/builtins_arith.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `abs_/2`
```clausal
# skip
abs_(+X, -Y)   % Y = abs(X)
```
Absolute value.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1035`
    **Clausal tests:** `tests/fixtures/builtins_arith.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `max_/3`
```clausal
# skip
max_(+X, +Y, -Z)   % Z = max(X, Y)
```
??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1049`
    **Clausal tests:** `tests/fixtures/builtins_arith.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `min_/3`
```clausal
# skip
min_(+X, +Y, -Z)   % Z = min(X, Y)
```
??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1062`
    **Clausal tests:** `tests/fixtures/builtins_arith.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `sign/2`
```clausal
# skip
sign(+X, -S)   % S is -1, 0, or 1
```
sign of X. Returns -1 for negative, 0 for zero, 1 for positive. Supports Quantity values (result is always a dimensionless integer).

---

### `gcd/3`
```clausal
# skip
gcd(+X, +Y, -G)   % G = gcd(X, Y)
```
Greatest common divisor of two integers. Supports Quantity values — dimensions must agree; result preserves dimensions.

---

### `divmod_/4`
```clausal
# skip
divmod_(+X, +Y, -Q, -R)   % Q = X // Y, R = X mod Y
```
Integer division and modulus. Fails if Y is 0. Supports Quantity values — dimensions must agree; quotient Q is dimensionless, remainder R preserves dimensions.

---

### `lcm/3`
```clausal
# skip
lcm(+X, +Y, -L)   % L = lcm(X, Y)
```
Least common multiple of two integers. Supports Quantity values — dimensions must agree; result preserves dimensions.

---

### `exp_mod/4`
```clausal
# skip
exp_mod(+Base, +Exp, +Mod, -Result)   % Result = Base^Exp mod Mod
```
Modular exponentiation using Python's efficient `pow(base, exp, mod)`. Integer-only (no Quantity support). Fails if Mod is 0.

---

### `popcount/2`
```clausal
# skip
popcount(+X, -Count)   % Count = number of set bits in X
```
Population count (number of 1 bits). X must be a non-negative integer.

---

### `msb/2`
```clausal
# skip
msb(+X, -Bit)   % Bit = position of most significant set bit (0-indexed)
```
Most significant bit position. X must be a positive integer. `msb(8, B)` gives B=3.

---

### `lsb/2`
```clausal
# skip
lsb(+X, -Bit)   % Bit = position of least significant set bit (0-indexed)
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
```clausal
# skip
in_(?Elem, +List)
```
Enumerate or check membership. Backtracks over all elements.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1078`
    **Clausal tests:** `tests/fixtures/meta_test.clausal`, `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`, `tests/test_search.py`

---

### `in_check/2`
```clausal
# skip
in_check(+Elem, +List)
```
Deterministic membership check. Succeeds at most once; no backtracking.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1091`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `append/3`
```clausal
# skip
append(?L1, ?L2, ?L3)   % L3 = L1 ++ L2
```
List concatenation. Works in all modes: given any two, determines the third. Backtracks over splits when `L3` is bound and `L1`/`L2` are unbound.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1105`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`, `tests/test_search.py`

---

### `length/2`
```clausal
# skip
length(+List, -N)   % N = len(List)
length(-List, +N)   % construct list of N fresh vars
```
List length in both directions.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1141`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `last/2`
```clausal
# skip
last(+List, -Elem)
```
Unify `Elem` with the last element of `List`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1159`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`, `tests/test_search.py`

---

### `reverse/2`
```clausal
# skip
reverse(+List, -Rev)
```
??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1170`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`, `tests/test_search.py`

---

### `get_item/3`
```clausal
# skip
get_item(+N, +List, -Elem)   % 0-based
```
Get the element at 0-based index `N`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1181`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `flatten/2`
```clausal
# skip
flatten(+Nested, -Flat)
```
Recursively flatten a nested list structure.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1225`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `msort/2`
```clausal
# skip
msort(+List, -Sorted)
```
sort `List` preserving duplicate elements (stable sort).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1248`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `sort/2`
```clausal
# skip
sort(+List, -Sorted)
```
sort `List` removing duplicate elements.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1265`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `permutation/2`
```clausal
# skip
permutation(+List, -Perm)
```
Enumerate all permutations of `List` via backtracking.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1286`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`, `tests/test_search.py`

---

### `select/3`
```clausal
# skip
select(?Elem, +List, -Rest)
```
select `Elem` from `List`, unifying `Rest` with the remaining elements. Backtracks over all positions where `Elem` appears.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1300`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `subtract/3`
```clausal
# skip
subtract(+Set1, +Set2, -Diff)
```
List difference: elements in `Set1` not in `Set2`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1314`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `intersection/3`
```clausal
# skip
intersection(+Set1, +Set2, -Inter)
```
Elements present in both `Set1` and `Set2`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1328`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `union/3`
```clausal
# skip
union(+Set1, +Set2, -union)
```
Elements in `Set1` or `Set2`, with duplicates removed.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1342`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `list_to_set/2`
```clausal
# skip
list_to_set(+List, -Set)
```
Remove duplicates from `List` preserving the first-occurrence order.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1359`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `sum_list/2`
```clausal
# skip
sum_list(+List, -sum_)
```
sum_ all numeric elements of `List`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1375`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `max_list/2`
```clausal
# skip
max_list(+List, -max_)
```
Maximum element of a non-empty numeric list.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1391`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `min_list/2`
```clausal
# skip
min_list(+List, -min_)
```
Minimum element of a non-empty numeric list.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1407`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `take/3`
```clausal
# skip
take(+N, +List, -Taken)
```
First `N` elements of `List`. If `N > len(List)`, returns the whole list. If `N = 0`, returns `[]`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/lists.py` (`_take__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `drop/3`
```clausal
# skip
drop(+N, +List, -Rest)
```
`List` after dropping the first `N` elements. If `N >= len(List)`, returns `[]`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/lists.py` (`_drop__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `split_at/4`
```clausal
# skip
split_at(+N, +List, -Left, -Right)
```
Split `List` at index `N` into `Left` (first N elements) and `Right` (rest). Clamps to list bounds.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/lists.py` (`_split_at__4`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `zip_/3`
```clausal
# skip
zip_(+List1, +List2, -Pairs)
```
Pair up elements from two lists into `[X, Y]` sublists. Truncates to the shorter list.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/lists.py` (`_zip__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `replicate/3`
```clausal
# skip
replicate(+N, +Elem, -List)
```
`List` of `N` copies of `Elem`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/lists.py` (`_replicate__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `split_with/3`
```clausal
# skip
split_with(+Sep, +List, -Parts)    % split mode
split_with(+Sep, -List, +Parts)    % join mode
```
Split `List` by separator `Sep` into sublists (`Parts`). in_ join mode, interleaves `Parts` with `Sep`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/lists.py` (`_split_with__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `pairs_keys_values/3`
```clausal
# skip
pairs_keys_values(?Pairs, ?Keys, ?Values)
```
Relate a list of `[K, V]` pairs to separate `Keys` and `Values` lists. Works in both directions.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1426`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `pairs_keys/2`
```clausal
# skip
pairs_keys(+Pairs, -Keys)
```
Extract the key (first element) from each pair.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1450`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `pairs_values/2`
```clausal
# skip
pairs_values(+Pairs, -Values)
```
Extract the value (second element) from each pair.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1463`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `group_pairs_by_key/2`
```clausal
# skip
group_pairs_by_key(+Pairs, -Groups)
```
Group a list of `[Key, Value]` pairs by key. Groups is a list of `[Key, Values]` where Values collects all values for that key. Order is preserved (first occurrence of key determines group order).

```clausal
# skip
group_pairs_by_key([["a", 1], ["b", 2], ["a", 3]], GROUPS)
% GROUPS = [["a", [1, 3]], ["b", [2]]]
```

---

### `numlist/3`
```clausal
# skip
numlist(+Low, +High, -List)
```
List is the list of integers from Low to High inclusive. Fails if Low > High.

```clausal
# skip
numlist(1, 5, L)   % L = [1, 2, 3, 4, 5]
```

---

### `numlist/2`
```clausal
# skip
numlist(+High, -List)
```
Shorthand for `numlist(1, High, List)`.

---

### `same_length/2`
```clausal
# skip
same_length(?L1, ?L2)
```
Succeeds if L1 and L2 have the same length. If one is ground and the other is unbound, generates a list of fresh variables with matching length.

---

### `transpose/2`
```clausal
# skip
transpose(+Matrix, -Transposed)
```
Column-wise transposition of a list of lists. All rows must be the same length (fails on non-rectangular input). Empty matrix transposes to empty list.

```clausal
# skip
transpose([[1, 2], [3, 4]], T)   % T = [[1, 3], [2, 4]]
```

---

## Higher-Order List Predicates

These predicates accept a **goal argument** (a lambda or named predicate). The goal is called for each list element; failures propagate as in standard higher-order patterns.

### `maplist/2`
```clausal
# skip
maplist(+Goal, +List)
```
Verify that `Goal(Elem)` succeeds for every element of `List`. Fails if any element fails.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1541`
    **Clausal tests:** `tests/fixtures/builtins_higher_order.clausal`
    **Python tests:** `tests/test_higher_order.py`

---

### `maplist/3`
```clausal
# skip
maplist(+Goal, +Xs, -Ys)
```
Map `Goal(X, Y)` over `Xs` to produce `Ys`. Takes the first solution of `Goal` per element.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1563`
    **Clausal tests:** `tests/fixtures/builtins_higher_order.clausal`
    **Python tests:** `tests/test_higher_order.py`

---

### `include/3`
```clausal
# skip
include(+Goal, +List, -Included)
```
include `List` keeping only elements for which `Goal(Elem)` succeeds.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1589`
    **Clausal tests:** `tests/fixtures/builtins_higher_order.clausal`
    **Python tests:** `tests/test_higher_order.py`

---

### `exclude/3`
```clausal
# skip
exclude(+Goal, +List, -Excluded)
```
include `List` keeping only elements for which `Goal(Elem)` **fails**.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1614`
    **Clausal tests:** `tests/fixtures/builtins_higher_order.clausal`
    **Python tests:** `tests/test_higher_order.py`

---

### `partition/4`
```clausal
# skip
partition(+Goal, +List, -Included, -Excluded)
```
Split `List` into two: `Included` contains elements where `Goal(Elem)` succeeds, `Excluded` contains elements where it fails.

```clausal
# skip
partition(integer, [1, "a", 2, "b"], YES, NO)
% YES = [1, 2], NO = ["a", "b"]
```

---

### `tfilter/3`
```clausal
# skip
tfilter(+Goal, +List, -Filtered)
```
Reified filter. Calls `Goal(Elem, T)` where T is a fresh variable bound to `True` or `False` by the goal. Keeps elements where T=True. Committed choice: only the first solution of Goal is used.

Useful with reified predicates like `eq/3` and `dif_t/3` that always succeed but bind their truth-value argument.

```clausal
# skip
tfilter(eq(_, 1), [1, 2, 1, 3], FILTERED)
% FILTERED = [1, 1]
```

---

### `tpartition/4`
```clausal
# skip
tpartition(+Goal, +List, -Included, -Excluded)
```
Reified partition. Calls `Goal(Elem, T)` for each element. Elements where T=True go into `Included`, T=False into `Excluded`.

```clausal
# skip
tpartition(eq(_, 1), [1, 2, 1, 3], YES, NO)
% YES = [1, 1], NO = [2, 3]
```

---

### `foldl/4`
```clausal
# skip
foldl(+Goal, +List, +V0, -V)
```
Left fold. Calls `Goal(Elem, Acc0, Acc1)` for each element, threading the accumulator. `V0` is the initial value; `V` is the final result.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1639`
    **Clausal tests:** `tests/fixtures/builtins_higher_order.clausal`
    **Python tests:** `tests/test_higher_order.py`

---

### `take_while/3`
```clausal
# skip
take_while(+Goal, +List, -Prefix)
```
Longest prefix of `List` where `Goal(Elem)` succeeds for each element.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_take_while__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `drop_while/3`
```clausal
# skip
drop_while(+Goal, +List, -Suffix)
```
Suffix of `List` after dropping the longest prefix where `Goal(Elem)` succeeds.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_drop_while__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `span/4`
```clausal
# skip
span(+Goal, +List, -Yes, -No)
```
`take_while` + `drop_while` in one pass. `Yes` is the longest prefix where `Goal` succeeds; `No` is the rest.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_span__4`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `group_by/3`
```clausal
# skip
group_by(+Goal, +List, -Groups)
```
Group consecutive elements by key projected via `Goal(Elem, Key)`. Elements with equal consecutive keys are collected into sublists.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_group_by__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `sort_by/3`
```clausal
# skip
sort_by(+Goal, +List, -Sorted)
```
sort `List` by key projected via `Goal(Elem, Key)`. Stable sort (preserves order of equal keys).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_sort_by__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `max_by/3`
```clausal
# skip
max_by(+Goal, +List, -max_)
```
element of `List` with the largest key projected via `Goal(Elem, Key)`. Fails on empty list.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_max_by__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `min_by/3`
```clausal
# skip
min_by(+Goal, +List, -min_)
```
element of `List` with the smallest key projected via `Goal(Elem, Key)`. Fails on empty list.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_min_by__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `filter_map/3`
```clausal
# skip
filter_map(+Goal, +List, -Result)
```
Map + filter in one pass. Calls `Goal(Elem, Out)` for each element; keeps `Out` when the goal succeeds, skips the element when it fails.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_filter_map__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

## Character/String

Logic-aware character and string predicates that participate in unification and backtracking. Unlike Python string methods, these are *relations* — e.g. `atom_concat(A, B, "hello")` with A and B unbound enumerates all splits, `char_type(C, digit)` enumerates digits.

!!! note "Prefer list predicates for common operations"

    Since strings behave as character lists, `append/3` subsumes `atom_concat/3` and `length/2` subsumes `atom_length/2`. The string-specific predicates below remain useful for ISO compatibility, explicit type conversion (`atom_chars/2`), code-point operations (`atom_codes/2`, `char_code/2`), character classification (`char_type/2`), and case conversion (`upcase_atom/2`, `downcase_atom/2`). See [Strings as Lists](strings_as_lists.md).

### `char_type/2`
```clausal
# skip
char_type(?Char, ?Type)
```
Character classification as a relation. At least one argument must be bound. Types: `alpha`, `digit`, `alnum`, `space`, `upper`, `lower`, `ascii`, `punct`, `print`, `control`. With Char bound, enumerates matching types. With Type bound, enumerates matching ASCII characters. With both bound, tests membership.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/chars.py`
    **Python tests:** `tests/test_chars.py`

---

### `char_code/2`
```clausal
# skip
char_code(?Char, ?Code)
```
Bidirectional char ↔ integer code point conversion. `char_code('A', N)` unifies N with 65. `char_code(C, 65)` unifies C with `'A'`. Both bound tests equality. Both unbound raises `instantiation_error`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/chars.py`
    **Python tests:** `tests/test_chars.py`

---

### `upcase_atom/2`
```clausal
# skip
upcase_atom(+Atom, -Upper)
```
Unify `Upper` with the uppercase version of `Atom`. First argument must be bound to a string.

---

### `downcase_atom/2`
```clausal
# skip
downcase_atom(+Atom, -Lower)
```
Unify `Lower` with the lowercase version of `Atom`. First argument must be bound to a string.

---

### `atom_length/2`
```clausal
# skip
atom_length(+Atom, ?length)
```
Unify `length` with the length of `Atom`. First argument must be bound.

---

### `atom_chars/2`
```clausal
# skip
atom_chars(?Atom, ?Chars)
```
Bidirectional conversion between a string and a list of single-character strings. `atom_chars("hi", L)` unifies L with `['h', 'i']`. `atom_chars(A, ['h', 'i'])` unifies A with `"hi"`.

---

### `atom_codes/2`
```clausal
# skip
atom_codes(?Atom, ?Codes)
```
Bidirectional conversion between a string and a list of integer code points. `atom_codes("hi", L)` unifies L with `[104, 105]`.

---

### `atom_concat/3`
```clausal
# skip
atom_concat(?A, ?B, ?C)
```
String concatenation as a relation. Forward: A and B bound → unify C with `A + B`. reverse: C bound, A and/or B unbound → enumerate all splits. `atom_concat(A, B, "abc")` yields 4 solutions: `("","abc")`, `("a","bc")`, `("ab","c")`, `("abc","")`. Optimized paths for prefix/suffix-bound cases.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/chars.py`
    **Python tests:** `tests/test_chars.py`

---

### `sub_atom/5`
```clausal
# skip
sub_atom(+Atom, ?Before, ?length, ?After, ?Sub)
```
Substring relation. Relates `Atom` to its substrings with position information: `Before + length + After = len(Atom)`, `Sub = Atom[Before:Before+length]`. Multi-modal — any combination of bound/unbound arguments works (Atom must be bound). With Sub bound, uses `str.find()` for efficient lookup. Otherwise enumerates all valid `(Before, length)` pairs.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/chars.py`
    **Python tests:** `tests/test_chars.py`

---

### `number_chars/2`
```clausal
# skip
number_chars(?Number, ?Chars)
```
Bidirectional number ↔ character-list conversion. Number bound → `Chars` unifies with `list(str(Number))`. Chars bound (list of single-char strings) → parse as `int` or `float`. Both bound → test equality. Both unbound → instantiation error. Rejects `bool` values (not considered numbers).

```clausal
# skip
number_chars(42, ["4", "2"])        # succeeds
number_chars(-3.14, CHARS)          # CHARS = ["-", "3", ".", "1", "4"]
number_chars(N, ["1", "0"])         # N = 10
```

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/chars.py`
    **Python tests:** `tests/test_chars.py`

---

### `number_codes/2`
```clausal
# skip
number_codes(?Number, ?Codes)
```
Bidirectional number ↔ code-point-list conversion. Like `number_chars/2` but uses integer code points (`ord`/`chr`) instead of single-character strings.

```clausal
# skip
number_codes(42, [52, 50])          # succeeds (ord("4")=52, ord("2")=50)
number_codes(N, [52, 50])           # N = 42
```

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/chars.py`
    **Python tests:** `tests/test_chars.py`

---

## I/O

### `write/1`
```clausal
# skip
write(+Term)
```
Print `Term` to stdout without a trailing newline. Strings are printed as-is; other values use `str()`. Logic variables are auto-dereferenced — bound vars print their value, unbound vars print `_N`. F-strings work naturally: `f"{X}"` derefs `X` at search time.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`write/1`)
    **Python tests:** `tests/test_io.py`

---

### `writeln/1`
```clausal
# skip
writeln(+Term)
```
Like `write/1` but appends a newline.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`writeln/1`)
    **Python tests:** `tests/test_io.py`

---

### `print_term/1`
```clausal
# skip
print_term(+Term)
```
Print the structured `term_str` representation of `Term` (strings are quoted, compounds show functor/args) followed by a newline. Useful for debugging.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`print_term/1`)
    **Python tests:** `tests/test_io.py`

---

### `nl/0`
```clausal
# skip
nl
```
Print a newline to stdout. equivalent to `write("\n")`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`nl/0`)
    **Python tests:** `tests/test_io.py`

---

### `tab/1`
```clausal
# skip
tab(+N)
```
Print `N` spaces to stdout. `N` must be a bound non-negative integer.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`tab/1`)
    **Python tests:** `tests/test_io.py`

---

### `write_to_string/2`
```clausal
# skip
write_to_string(+Term, -String)
```
Unify `String` with the `write`-style string representation of `Term` (strings pass through, others use `str()`). Does not print anything.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`write_to_string/2`)
    **Python tests:** `tests/test_io.py`

---

### `term_to_string/2`
```clausal
# skip
term_to_string(+Term, -String)
```
Unify `String` with the `term_str` representation of `Term` (structured, with quoted strings). Does not print anything.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`term_to_string/2`)
    **Python tests:** `tests/test_io.py`

---

### `listing/1`
```clausal
# skip
listing(+Predicate)
```
Print all clauses of a predicate to stdout in readable Clausal syntax. Accepts a `PredicateMeta` class or instance. Prints a header comment with clause count, followed by each clause formatted as `head.` (fact) or `head <- (body).` (rule). Reports "no clauses" for empty predicates and "builtin" for builtin predicates.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/io.py` (`listing/1`)
    **Python tests:** `tests/test_listing.py`

---

### `portray_clause/1`
```clausal
# skip
portray_clause(+Term)
```
Pretty-print a term with indentation for multi-line display using `term_pformat`. Short terms appear on one line; deeply nested terms are expanded with depth indentation.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/io.py` (`portray_clause/1`)
    **Python tests:** `tests/test_listing.py`

---

## Logging (`log` module)

Standard library module wrapping Python's `logging`. Import via `-import_from(log, [...])`. See [logging.md](logging.md) for full documentation.

All logging predicates always succeed (side-effect only). Messages below the logger's configured level are silently discarded.

### `GetLogger/1`, `GetLogger/2`
```clausal
# skip
GetLogger(-Logger)
GetLogger(+Name, -Logger)
```
Unify `Logger` with a Python `logging.Logger` instance. Arity-1 returns the default `"clausal"` logger. Same name always returns same logger instance.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`
    **Python tests:** `tests/test_logging_module.py`

---

### `Debug/1`, `Debug/2`
```clausal
# skip
Debug(+Msg)
Debug(+Logger, +Msg)
```
Log at DEBUG level. Arity-1 uses default `"clausal"` logger.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

### `Info/1`, `Info/2`
```clausal
# skip
Info(+Msg)
Info(+Logger, +Msg)
```
Log at INFO level.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

### `Warning/1`, `Warning/2`
```clausal
# skip
Warning(+Msg)
Warning(+Logger, +Msg)
```
Log at WARNING level.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

### `Error/1`, `Error/2`
```clausal
# skip
Error(+Msg)
Error(+Logger, +Msg)
```
Log at ERROR level.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

### `Critical/1`, `Critical/2`
```clausal
# skip
Critical(+Msg)
Critical(+Logger, +Msg)
```
Log at CRITICAL level.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

### `Log/3`
```clausal
# skip
Log(+Logger, +Level, +Msg)
```
Log at an arbitrary level. `Level` is a string (`"debug"`, `"info"`, etc.) or integer.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

### `SetLevel/2`
```clausal
# skip
SetLevel(+Logger, +Level)
```
Set the logger's effective level.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

### `GetLevel/2`
```clausal
# skip
GetLevel(+Logger, -Level)
```
Unify `Level` with the logger's effective level name (e.g. `"DEBUG"`).

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

### `IsEnabledFor/2`
```clausal
# skip
IsEnabledFor(+Logger, +Level)
```
Succeeds if the logger would process a message at `Level`; fails otherwise. The only logging predicate that can fail.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

### `StreamHandler/2`
```clausal
# skip
StreamHandler(+StreamName, -Handler)
```
Create a `logging.StreamHandler`. `StreamName` is `"stdout"` or `"stderr"`.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

### `FileHandler/2`
```clausal
# skip
FileHandler(+Path, -Handler)
```
Create a `logging.FileHandler` for the given path.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

### `SetFormatter/2`
```clausal
# skip
SetFormatter(+Handler, +FormatString)
```
Set a `logging.Formatter` on the handler using Python format string syntax.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

### `AddHandler/2`
```clausal
# skip
AddHandler(+Logger, +Handler)
```
Add a handler to the logger.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

### `RemoveHandler/2`
```clausal
# skip
RemoveHandler(+Logger, +Handler)
```
Remove a handler from the logger.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

### `BasicConfig/1`
```clausal
# skip
BasicConfig(+Opts)
```
Call `logging.basicConfig()` with a dict of options (level, format, datefmt, filename, filemode, stream).

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

## Date & Time (`date_time` module)

Standard library module wrapping Python's `datetime`. Import via `-import_from(date_time, [Now, Today, Date, ...])`. All predicates produce and consume **real Python `datetime` objects** — `datetime.date`, `datetime.time`, `datetime.datetime`, `datetime.timedelta` — not custom term types. Unification uses Python's native `==`. Any `datetime` method can be called via `++()` interop (e.g. `S is ++D.isoformat()`).

### `Now/1`
```clausal
# skip
Now(-DT)
```
Unify `DT` with `datetime.datetime.now()` (naive, local time).

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/date_time.py`
    **Python tests:** `tests/test_date_time.py`

---

### `NowUTC/1`
```clausal
# skip
NowUTC(-DT)
```
Unify `DT` with `datetime.datetime.now(datetime.timezone.utc)` (timezone-aware).

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/date_time.py`

---

### `Today/1`
```clausal
# skip
Today(-D)
```
Unify `D` with `datetime.date.today()`.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/date_time.py`

---

### `Date/4`
```clausal
# skip
Date(?Year, ?Month, ?Day, ?DateObj)
```
Bidirectional. If `DateObj` is unbound, constructs `datetime.date(Year, Month, Day)`. If `DateObj` is a `datetime.date` (or `datetime.datetime`), decomposes into `Year`, `Month`, `Day`. Fails on invalid dates (e.g. month 13, Feb 29 in non-leap year).

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/date_time.py`
    **Python tests:** `tests/test_date_time.py`

---

### `Time/4`
```clausal
# skip
Time(?Hour, ?Minute, ?Second, ?TimeObj)
```
Bidirectional. If `TimeObj` is unbound, constructs `datetime.time(Hour, Minute, Second)`. If `TimeObj` is a `datetime.time`, decomposes into `Hour`, `Minute`, `Second`.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/date_time.py`

---

### `DateTime/7`
```clausal
# skip
DateTime(?Year, ?Month, ?Day, ?Hour, ?Minute, ?Second, ?DtObj)
```
Bidirectional. If `DtObj` is unbound, constructs `datetime.datetime(Year, Month, Day, Hour, Minute, Second)`. If `DtObj` is a `datetime.datetime`, decomposes into all six components.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/date_time.py`

---

### `TimeDelta/3`
```clausal
# skip
TimeDelta(?Days, ?Seconds, ?TdObj)
```
Bidirectional. If `TdObj` is unbound, constructs `datetime.timedelta(days=Days, seconds=Seconds)`. If `TdObj` is a `datetime.timedelta`, decomposes into `Days` and `Seconds`.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/date_time.py`

---

### `DateAdd/3`
```clausal
# skip
DateAdd(+DateOrDatetime, +Timedelta, -Result)
```
`Result = DateOrDatetime + Timedelta`. Both inputs must be ground.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/date_time.py`

---

### `DateSub/3`
```clausal
# skip
DateSub(+DateOrDatetime, +Timedelta, -Result)
```
`Result = DateOrDatetime - Timedelta`. Both inputs must be ground.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/date_time.py`

---

### `DateDiff/3`
```clausal
# skip
DateDiff(+D1, +D2, -Timedelta)
```
`Timedelta = D1 - D2`. Both inputs must be `datetime.date` or `datetime.datetime`. Result is a `datetime.timedelta` (may be negative).

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/date_time.py`

---

### `FormatDate/3`
```clausal
# skip
FormatDate(+DateOrDatetime, +FormatStr, -ResultStr)
```
`ResultStr = DateOrDatetime.strftime(FormatStr)`. Works with `datetime.date`, `datetime.time`, and `datetime.datetime`.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/date_time.py`

---

### `ParseDate/3`
```clausal
# skip
ParseDate(+String, +FormatStr, -DatetimeObj)
```
`DatetimeObj = datetime.datetime.strptime(String, FormatStr)`. Fails if the string does not match the format.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/date_time.py`

---

### `DayOfWeek/2`
```clausal
# skip
DayOfWeek(+DateOrDatetime, -Weekday)
```
`Weekday = DateOrDatetime.weekday()`. Monday = 0, Sunday = 6.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/date_time.py`

---

### `DateBetween/3`
```clausal
# skip
DateBetween(+Start, +End, -D)
```
Nondeterministic — generates one solution for each `datetime.date` in `[Start, End]` (inclusive). Fails if `Start > End`. This is the only date_time predicate that backtracks.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/date_time.py`
    **Python tests:** `tests/test_date_time.py`

---

## YAML (`yaml_module` module)

Standard library module wrapping Python's PyYAML. Import via `-import_from(yaml_module, [Read, write, Get, ...])`. Data is represented as **native Python objects** — `dict`, `list`, `str`, `int`, `float`, `bool`, `None` — exactly what `yaml.safe_load` returns. Any Python method can be called on them via `++()` interop. See [yaml.md](yaml.md) for full documentation.

Only `yaml.safe_load` is used (no arbitrary object construction from YAML tags).

### `Read/2`

```clausal
# skip
Read(+YamlString, -Data)
```

Parse a YAML string into a Python object (dict/list/scalar). Fails on invalid YAML.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/yaml_module.py`

### `write/2`

```clausal
# skip
write(+Data, -YamlString)
```

Serialize a Python object to a YAML string (block style, human-readable).

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/yaml_module.py`

### `ReadAll/2`

```clausal
# skip
ReadAll(+YamlString, -DocList)
```

Parse a multi-document YAML string (with `---` separators) into a list of Python objects.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/yaml_module.py`

### `WriteAll/2`

```clausal
# skip
WriteAll(+DocList, -YamlString)
```

Serialize a list of Python objects to a multi-document YAML string.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/yaml_module.py`

### `ReadFile/2`

```clausal
# skip
ReadFile(+Path, -Data)
```

Read and parse a YAML file. Fails if the file does not exist or contains invalid YAML.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/yaml_module.py`

### `WriteFile/2`

```clausal
# skip
WriteFile(+Path, +Data)
```

write a Python object as YAML to a file.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/yaml_module.py`

### `Get/3`

```clausal
# skip
Get(+Data, +Path, -Value)
```

Navigate a nested dict/list structure. `Path` is a single key (string or int) or a list of keys for nested access. Fails if any key is missing or index is out of range.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/yaml_module.py`
    **Python tests:** `tests/test_yaml_module.py`

---
## Operator Syntax (Compiler Special Forms)

The following are not builtins in the registry — they are syntax forms compiled directly by `compile_goal`/`compile_goal_trampoline`.

| Syntax | Meaning | Compiler location |
|--------|---------|-------------------|
| `X is Y` | Unification (structural) | `compiler.py:1415` |
| `X is not Y` | Disequality constraint (`dif/2`) | `compiler.py:1436` |
| `X == Expr` | Arithmetic constraint (CLP(ℤ)) | `compiler.py` (`Evaluate`) |
| `X == Y` | CLP(ℤ) equality constraint | `compiler.py:1444` |
| `X != Y` | CLP(ℤ) disequality constraint | `compiler.py:1451` |
| `X < Y` | CLP(ℤ) less-than constraint | `compiler.py:1459` |
| `X <= Y` | CLP(ℤ) less-or-equal constraint | `compiler.py:1466` |
| `X > Y` | CLP(ℤ) greater-than constraint | `compiler.py:1473` |
| `X >= Y` | CLP(ℤ) greater-or-equal constraint | `compiler.py:1480` |
| `X in Coll` | For-loop over collection | `compiler.py:1570` |
| `X not in Coll` | Negated membership check | `compiler.py:1594` |
| `not Goal` | Negation as failure | `compiler.py:1507` |
| `If(Cond, Then, Else)` | If-Then-Else | `compiler.py` (`_compile_ite`) |

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
    | `tests/fixtures/tabled_ite.clausal` | `If/3` with tabled predicate |
    | `tests/fixtures/clpfd_queens.clausal` | `in_domain/3`, `all_different/1`, `label/1` |
    | `tests/fixtures/clpfd_sendmore.clausal` | `in_domain/3`, `all_different/1`, `label/1` |
    | `tests/fixtures/wfs_win.clausal` | well-founded semantics, `not` on tabled |
    | `tests/fixtures/wfs_win_asym.clausal` | well-founded semantics, asymmetric |
    | `tests/fixtures/reified_memberd.clausal` | `If/3`, `dif/2` (reified ITE) |
    | `tests/fixtures/reified_max.clausal` | `If/3` with arithmetic |
    | `tests/fixtures/reif_eq_test.clausal` | `eq/3` |
    | `tests/fixtures/once_member.clausal` | `once/1` |
    | `tests/fixtures/meta_test.clausal` | `findall/3`, `setof/3`, `forall/2`, `in_/2` |
    | `tests/fixtures/builtins_inspect.clausal` | `functor/3`, `arg/3`, `unpack/2` |
    | `tests/clausal_modules/term_inspection.clausal` | `copy_term/2`, `term_variables/2`, `numbervars/3` |
    | `tests/fixtures/builtins_db.clausal` | `assertz/1`, `asserta/1`, `retract/1` |
    | `tests/fixtures/builtins_types.clausal` | `var/1`, `nonvar/1`, `is_str/1`, `number/1`, `integer/1`, `float_/1`, `compound/1`, `callable_/1`, `is_list/1`, `ground/1` |
    | `tests/fixtures/builtins_arith.clausal` | `between/3`, `succ/2`, `plus/3`, `abs_/2`, `max_/3`, `min_/3` |
    | `tests/fixtures/builtins_lists.clausal` | `in_/2`, `in_check/2`, `append/3`, `length/2`, `last/2`, `reverse/2`, `get_item/3`, `flatten/2`, `msort/2`, `sort/2`, `permutation/2`, `select/3`, `subtract/3`, `intersection/3`, `union/3`, `list_to_set/2`, `sum_list/2`, `max_list/2`, `min_list/2`, `pairs_keys_values/3`, `pairs_keys/2`, `pairs_values/2` |
    | `tests/fixtures/builtins_higher_order.clausal` | `maplist/2`, `maplist/3`, `include/3`, `exclude/3`, `foldl/4` |
    | `tests/fixtures/list_util.clausal` | `take/3`, `drop/3`, `split_at/4`, `zip_/3`, `replicate/3`, `split_with/3`, `take_while/3`, `drop_while/3`, `span/4`, `group_by/3`, `sort_by/3`, `max_by/3`, `min_by/3`, `filter_map/3` |
    | `tests/fixtures/builtins_keywords.clausal` | `vary/3`, `extend/3`, `unbound_keys/2`, `signature/3` |
    | `tests/fixtures/builtins_dif.clausal` | `dif/2`, `eq/3`, `dif_t/3` |
    | `tests/fixtures/builtins_call.clausal` | `Call/N`, `CallGoal/N` |
    | `tests/fixtures/coroutining.clausal` | `call_nth/2`, `count_all/2`, `setup_call_cleanup/3`, `call_cleanup/2`, `freeze/2`, `when/2` |
    | `tests/test_python_interop.py` | `++()` Python interop (13 tests) |
    | `tests/test_dcg.py` | DCG rules, `phrase/2`, `phrase/3` (26 tests) |
    | `tests/fixtures/dcg_grammar.clausal` | `phrase/2`, `phrase/3`, DCG with non-terminals, inline goals, pushback, negation |
    | `tests/fixtures/clpb_circuit.clausal` | `sat/1`, `bool_labeling/1`, `BoolEq` — HalfAdder, FullAdder, PigeonHole |
    | `tests/fixtures/logging_basic.clausal` | `GetLogger`, `SetLevel`, `GetLevel`, `IsEnabledFor`, `Debug`, `Info`, `Warning`, `Error`, `Critical`, `Log`, `StreamHandler`, `SetFormatter`, `AddHandler`, `RemoveHandler` |
    | `tests/test_date_time.py` | `Now`, `NowUTC`, `Today`, `Date`, `Time`, `DateTime`, `TimeDelta`, `DateAdd`, `DateSub`, `DateDiff`, `FormatDate`, `ParseDate`, `DayOfWeek`, `DateBetween` (64 tests) |
    | `tests/test_yaml_module.py` | `Read`, `write`, `ReadAll`, `WriteAll`, `ReadFile`, `WriteFile`, `Get` (45 tests) |
    | `tests/fixtures/yaml_basic.clausal` | `Read`, `write`, `Get` — parsing, nested access, round-trip |
