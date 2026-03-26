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

    Append = get_builtin_class("Append")
    Between = get_builtin_class("Between")

    X_ = Var()
    Z_ = Var()

    # Positional construction
    t = Append([1, 2], [3, 4], Z_)
    # → Append(l1=[1, 2], l2=[3, 4], l3=Var())

    # Keyword construction with partial fill (missing fields → Var())
    t2 = Between(low=1, high=10)
    # → Between(low=1, high=10, x=Var())

    # Pattern matching works via __match_args__
    match t:
        case Append(a, b, c):
            print(a, b, c)
    ```

    Each builtin class is a full `PredicateMeta` with `_fields`, `_functor`, `_arity`, `__eq__`, `__repr__`, and `__match_args__`. Stateless builtins also have `_dispatch_fn` set (so `_get_dispatch()` works directly). DB-dependent builtins (Assert, Retract, etc.) have `_dispatch_fn = None` since they need a live database; use them for term construction only.

    **Passing builtins to higher-order predicates:** Builtin predicates can be passed directly as arguments to `MapList`, `Filter`, `Exclude`, `FoldLeft`, `Call/N`, and other higher-order builtins — no lambda wrapper is needed:

    ```
    AllNumbers(XS) <- MapList(IsNumber, XS)
    KeepInts(XS, INTS) <- Filter(IsInt, XS, INTS)
    Incremented(XS, YS) <- MapList(Succ, XS, YS)
    ```

    This works for any builtin or user-defined predicate whose arity matches what the higher-order predicate expects.

    **Multi-arity builtins** (MapList/2,3 and phrase/2,3) are wrapped in `MultiArityBuiltin`, which routes `__call__` by argument count:

    ```python
    MapList = get_builtin_class("MapList")
    MapList(goal, [1, 2])           # → MapList/2 term
    MapList(goal, [1, 2], [2, 4])   # → MapList/3 term
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
| [Control Flow](#control-flow) | Once, Not, If/3, throw/1, Catch/2, CatchRecover/3, catch/3, halt/0,1, SetupCallCleanup/3, CallCleanup/2 |
| [Coroutining](#coroutining) | Freeze/2, When/2 |
| [Meta-Predicates](#meta-predicates) | FindAll/3, BagOf/3, SetOf/3, ForAll/2, CallNth/2, CountAll/2 |
| [Higher-Order Call](#higher-order-call) | Call/1..8, CallGoal/1..8 |
| [DCG (Definite Clause Grammars)](#dcg-definite-clause-grammars) | phrase/2, phrase/3 |
| [Term Inspection](#term-inspection) | Functor/3, Arg/3, Unpack/2, CopyTerm/2, TermVariables/2, NumberVars/3, GenSym/2 |
| [Runtime Database](#runtime-database) | Assert/1, AssertFirst/1, Retract/1, ClearTable/2, ClearAllTables/0 |
| [Keyword-Term Introspection](#keyword-term-introspection) | Vary/3, Extend/3, UnboundKeys/2, Signature/3 |
| [Attributed Variables](#attributed-variables) | PutAttr/3, GetAttr/3, DelAttr/2, GetAttrs/2, PutAttrs/2, IsAttVar/1, TermAttributedVariables/2 |
| [Constraint Predicates](#constraint-predicates) | Dif/2, Eq/3, DifT/3 |
| [CLP(FD) — Finite Domain Constraints](#clpfd-finite-domain-constraints) | InDomain/3, Label/1, AllDifferent/1, Equivalent/2, Sum/3, ScalarProduct/4, Element/3, Circuit/1 |
| [CLP(B) — Boolean Constraints](#clpb-boolean-constraints) | Sat/1, Taut/2, SatCount/2, BoolLabeling/1 |
| [Type Checks](#type-checks) | IsVar/1, IsBound/1, IsStr/1, IsNumber/1, IsInt/1, IsFloat/1, IsCompound/1, IsCallable/1, IsList/1, IsGround/1, MustBe/2, CanBe/2 |
| [Dict and Set Predicates](#dict-and-set-predicates) | IsDict/1, DictGet/3, DictPut/4, DictMerge/3, GenDict/3, SubDict/2, IsSet/1, SetUnion/3, SetSubset/2, GenSet/2 |
| [Arithmetic](#arithmetic) | Between/3, Succ/2, Plus/3, Abs/2, Max/3, Min/3, Sign/2, Gcd/3, DivMod/4, Lcm/3, ExpMod/4, Popcount/2, Msb/2, Lsb/2 |
| [List Predicates](#list-predicates) | In/2, Append/3, Length/2, Reverse/2, Sort/2, Permutation/2, Select/3, Flatten/2, Take/3, Drop/3, Zip/3, SplitWith/3, Numlist/2,3, SameLength/2, Transpose/2 |
| [Higher-Order List Predicates](#higher-order-list-predicates) | MapList/2,3, Filter/3, Exclude/3, Partition/4, TFilter/3, TPartition/4, FoldLeft/4, TakeWhile/3, DropWhile/3, Span/4, GroupBy/3, SortBy/3, FilterMap/3 |
| [Character/String](#characterstring) | CharType/2, CharCode/2, UpcaseAtom/2, DowncaseAtom/2, AtomLength/2, AtomChars/2, AtomCodes/2, AtomConcat/3, SubAtom/5, NumberChars/2, NumberCodes/2 |
| [I/O](#io) | Write/1, Writeln/1, PrintTerm/1, Nl/0, Tab/1, WriteToString/2, TermToString/2, Listing/1, PortrayClause/1 |
| [Logging (`log` module)](#logging-log-module) | GetLogger, Debug, Info, Warning, Error, Critical, Log, SetLevel, GetLevel, StreamHandler, FileHandler |
| [Date & Time (`date_time` module)](#date--time-date_time-module) | Now, Today, Date, Time, DateTime, DateAdd, DateSub, DateDiff, FormatDate, ParseDate, DateBetween |
| [YAML (`yaml_module` module)](#yaml-yaml_module-module) | Read, Write, ReadAll, WriteAll, ReadFile, WriteFile, Get |
| [Time & Statistics](#time--statistics) | CurrentTime/1, Statistics/2 |
| [Operator Syntax (Compiler Special Forms)](#operator-syntax-compiler-special-forms) | `is`, `==`, `:=`, `!=`, `<`, `<=`, `>`, `>=`, `in`, `not in`, `not`, `If` |

---

## Control Flow

These are **compiler special forms** — transformed at compile time, not dispatched via the builtin registry.

### `Once/1`
```clausal
# skip
Once(+Goal)
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

### `CatchRecover/3`
```clausal
# skip
CatchRecover(+Goal, ?Error, +Recovery)
```
Execute `Goal`. If an exception is raised, unify `Error` against the exception term, then execute `Recovery`. Like `Catch/2` but with an explicit recovery goal.

`CatchRecover` never re-raises. For selective catch with re-raise on mismatch, use `catch/3`.

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

### `SetupCallCleanup/3`
```clausal
# skip
SetupCallCleanup(+Setup, +Call, +Cleanup)
```
Deterministic resource management (`try/finally` for logic). Setup runs once (first solution only). Call runs normally. Cleanup runs **exactly once** regardless of how Call terminates — success, failure, or exception. If Setup fails, Cleanup does not run.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py` (`_compile_setup_call_cleanup`)
    **Python tests:** `tests/test_coroutining.py::TestSetupCallCleanup`
    **Clausal tests:** `tests/fixtures/coroutining.clausal`

---

### `CallCleanup/2`
```clausal
# skip
CallCleanup(+Call, +Cleanup)
```
Sugar for `SetupCallCleanup(true, Call, Cleanup)` — no setup step, just guaranteed cleanup.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py` (`_compile_setup_call_cleanup`)
    **Python tests:** `tests/test_coroutining.py::TestCallCleanup`
    **Clausal tests:** `tests/fixtures/coroutining.clausal`

---

## Coroutining

Coroutining predicates delay goal execution until variables are bound. They use the attributed variable hook infrastructure.

*Full documentation: [Coroutining](coroutining.md)*

### `Freeze/2`
```clausal
# skip
Freeze(?X, +Goal)
```
Delay `Goal` until `X` is bound. If `X` is already bound, runs `Goal` immediately. If `X` is unbound, attaches Goal as an attribute; when `X` is later unified, the frozen goal fires synchronously — failure rejects the unification.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py` (`_compile_freeze`), `clausal/logic/coroutining.py` (`_freeze_hook`)
    **Python tests:** `tests/test_coroutining.py::TestFreeze`
    **Clausal tests:** `tests/fixtures/coroutining.clausal`

---

### `When/2`
```clausal
# skip
When(+Condition, +Goal)
```
Generalized coroutining: delay `Goal` until `Condition` is satisfied. Supported conditions: `IsBound(X)`, `IsGround(X)`, conjunction `(C1, C2)`, disjunction `(C1 ; C2)`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py` (`_compile_when`), `clausal/logic/coroutining.py` (`_install_when_ground`, `_install_when_disjunction`)
    **Python tests:** `tests/test_coroutining.py::TestWhen`
    **Clausal tests:** `tests/fixtures/coroutining.clausal`

---

## Meta-Predicates

These are **compiler special forms** recognized by name in `compile_goal`/`compile_goal_trampoline`. Inner goals compile in simple mode as sub-generators.

### `FindAll/3`
```clausal
# skip
FindAll(+Template, +Goal, -Bag)
```
Collect all bindings of `Template` produced by `Goal` into `Bag` (a list). Succeeds with `[]` if `Goal` has no solutions.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py:1623` (`_compile_find_all_core`)
    **Clausal tests:** `tests/fixtures/meta_test.clausal`
    **Python tests:** `tests/test_meta.py`

---

### `BagOf/3`
```clausal
# skip
BagOf(+Template, +Goal, -Bag)
```
Like `FindAll/3` but fails if `Goal` has no solutions. Bag preserves duplicate solutions.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py:1630`
    **Clausal tests:** `tests/fixtures/meta_test.clausal`
    **Python tests:** `tests/test_meta.py`

---

### `SetOf/3`
```clausal
# skip
SetOf(+Template, +Goal, -Set)
```
Like `BagOf/3` but removes duplicates and sorts the result.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py:1637`
    **Clausal tests:** `tests/fixtures/meta_test.clausal`
    **Python tests:** `tests/test_meta.py`

---

### `ForAll/2`
```clausal
# skip
ForAll(+Cond, +Action)
```
Universal quantification: succeeds if `Action` succeeds for every solution of `Cond`. Desugars to `not(Cond and not(Action))`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py:1644`
    **Clausal tests:** `tests/fixtures/meta_test.clausal`
    **Python tests:** `tests/test_meta.py`

---

### `CallNth/2`
```clausal
# skip
CallNth(+Goal, +N)
```
Call `Goal` and succeed only on the **Nth solution** (1-indexed). Skips the first N-1 solutions. Fails if Goal has fewer than N solutions. Raises `type_error` if N is not a positive integer.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py` (`_compile_call_nth`)
    **Python tests:** `tests/test_coroutining.py::TestCallNth`
    **Clausal tests:** `tests/fixtures/coroutining.clausal`

---

### `CountAll/2`
```clausal
# skip
CountAll(+Goal, -Count)
```
Count the number of solutions of `Goal` without collecting them. Unifies `Count` with the integer result. Bindings from the inner goal are not visible after counting (the trail is unwound).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py` (`_compile_count_all`)
    **Python tests:** `tests/test_coroutining.py::TestCountAll`
    **Clausal tests:** `tests/fixtures/coroutining.clausal`

---

## Time & Statistics

### `CurrentTime/1`
```clausal
# skip
CurrentTime(-T)
```
Unify T with the current Unix timestamp as a float (seconds since epoch).

---

### `Statistics/2`
```clausal
# skip
Statistics(?Key, -Value)
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
Invoke a DCG rule and require it to consume the entire input list. `RuleBody` is either a predicate class (0 extra args, e.g. `greeting`) or a partial term (N extra args, e.g. `digit(D)`). Equivalent to calling the rule with `List` as the input state and `[]` as the output state.

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

### `Sequence//1`
```clausal
# skip
Sequence(+List)   % as DCG non-terminal: Sequence(List, S0, S)
```
DCG non-terminal that matches a list of terminals in sequence. `Sequence([a, b, c])` consumes `a`, `b`, `c` from the input. Equivalent to inlining the terminals as a grammar rule body.

```clausal
# skip
phrase(Sequence(["hello", "world"]), ["hello", "world"])       % succeeds
phrase(Sequence(["a", "b"]), ["a", "b", "c"], REST)            % REST = ["c"]
```

---

## Term Inspection

### `Functor/3`
```clausal
# skip
Functor(+Term, -Name, -Arity)   % decompose
Functor(-Term, +Name, +Arity)   % construct
```
Decompose a term into its functor name and arity, or construct a term from a name and arity (fields are fresh vars).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:353`
    **Clausal tests:** `tests/fixtures/builtins_inspect.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Arg/3`
```clausal
# skip
Arg(+N, +Term, -Arg)
```
Unify `Arg` with the `N`-th argument of `Term` (1-based indexing).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:394`
    **Clausal tests:** `tests/fixtures/builtins_inspect.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Unpack/2`
```clausal
# skip
Unpack(+Term, -List)   % decompose: List = [Functor | Args]
Unpack(-Term, +List)   % construct: Term from [Functor | Args]
```
Decompose a term to `[functor | args]` list, or construct a term from such a list. (Prolog's `=..` operator.)

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:413`
    **Clausal tests:** `tests/fixtures/builtins_inspect.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `CopyTerm/2`
```clausal
# skip
CopyTerm(+Original, -Copy)
```
Unify `Copy` with a deep copy of `Original` where every unbound `Var` is replaced by a fresh one. Structural sharing is preserved: if the same `Var` appears in multiple positions in `Original`, the same fresh `Var` appears in all corresponding positions of `Copy`. Already-bound variables are followed and their values are copied rather than replaced.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`_copy_term`, `CopyTerm/2`)
    **Clausal tests:** `tests/clausal_modules/term_inspection.clausal`
    **Python tests:** `tests/test_term_inspection.py`

---

### `TermVariables/2`
```clausal
# skip
TermVariables(+Term, -Vars)
```
Unify `Vars` with a list of all unbound `Var`s in `Term`, collected left-to-right with duplicates removed (same `Var` appearing multiple times in `Term` appears only once in `Vars`). Bound variables are followed and not collected.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`_collect_vars`, `TermVariables/2`)
    **Clausal tests:** `tests/clausal_modules/term_inspection.clausal`
    **Python tests:** `tests/test_term_inspection.py`

---

### `NumberVars/3`
```clausal
# skip
NumberVars(+Term, +Start, -End)
```
Number all unbound `Var`s in `Term` left-to-right, binding each to `Compound("$VAR", (N,))` where `N` starts at `Start` and increments. `End` is unified with the next unused number after all variables are numbered. Useful for pretty-printing terms with named variables. `Start` must be a bound integer.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`NumberVars/3`)
    **Clausal tests:** `tests/clausal_modules/term_inspection.clausal`
    **Python tests:** `tests/test_term_inspection.py`

---

### `GenSym/2`
```clausal
# skip
GenSym(+Prefix, -Atom)
```
Generate a unique atom by appending a monotonically increasing counter to `Prefix`. `GenSym("x", A)` produces `"x_1"`, `"x_2"`, etc. on successive calls. The counter is **not trailed** — it survives backtracking (impure, matches Prolog's `gensym/2`). Thread-safe via lock. Different prefixes maintain independent counters. `Prefix` must be a bound string; unbound or non-string prefix → fail.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/inspection.py` (`GenSym/2`)
    **Python tests:** `tests/test_term_inspection.py`

---

## Runtime Database

These predicates require a live `Database` reference (`_DB_BUILTINS`). They recompile the affected predicate after modification.

### `Assert/1`
```clausal
# skip
Assert(+Clause)
```
Add `Clause` (a fact or rule) at the **end** of its predicate's clause list. Fails on locked (non-dynamic) predicates. Ground compound facts are normalized to `Var+Is` form for output-mode queries.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:507`
    **Clausal tests:** `tests/fixtures/builtins_db.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `AssertFirst/1`
```clausal
# skip
AssertFirst(+Clause)
```
Add `Clause` at the **front** of its predicate's clause list.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:545`
    **Clausal tests:** `tests/fixtures/builtins_db.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Retract/1`
```clausal
# skip
Retract(+Term)
```
Remove the **first** clause whose head unifies with `Term`. Not backtrackable — removes exactly one clause per call. Fails on locked predicates.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:580`
    **Clausal tests:** `tests/fixtures/builtins_db.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `ClearTable/2`
```clausal
# skip
ClearTable(+Functor, +Arity)
```
Remove all cached answers for the named tabled predicate, forcing re-computation on the next call.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:661`
    **Clausal tests:** none
    **Python tests:** `tests/test_tabling.py`

---

### `ClearAllTables/0`
```clausal
# skip
ClearAllTables
```
Remove all cached tabling answers for every predicate in the current database.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:678`
    **Clausal tests:** none
    **Python tests:** `tests/test_tabling.py`

---

## Keyword-Term Introspection

These predicates operate on `KWTerm` (open-world keyword terms) and `PredicateMeta` term instances.

### `Vary/3`
```clausal
# skip
Vary(+Overrides, +Term, -NewTerm)
```
Produce a copy of `Term` with field values replaced by `Overrides` (a Python `dict`). Works on functor dataclass instances and `KWTerm`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:692`
    **Clausal tests:** `tests/fixtures/builtins_keywords.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Extend/3`
```clausal
# skip
Extend(+Additions, +Term, -NewTerm)
```
Produce a copy of `Term` (must be a `KWTerm`) with additional fields from `Additions` (a Python `dict`). Dataclass terms have fixed schemas so only `KWTerm` is supported.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:727`
    **Clausal tests:** `tests/fixtures/builtins_keywords.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `UnboundKeys/2`
```clausal
# skip
UnboundKeys(+Term, -Keys)
```
Unify `Keys` with a list of field names whose values are unbound `Var`s in `Term`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:754`
    **Clausal tests:** `tests/fixtures/builtins_keywords.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Signature/3`
```clausal
# skip
Signature(+FunctorName, +Arity, -Names)
```
Reflect the registered parameter name list for the predicate `FunctorName/Arity`. Fails if no signature is registered.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:778`
    **Clausal tests:** `tests/fixtures/builtins_keywords.clausal`
    **Python tests:** `tests/test_builtins.py`

---

## Attributed Variables

Attributed variables carry key-value metadata that survives through unification. This is the mechanism that powers CLP(FD), CLP(B), CLP(R), dif/2, and units constraints internally. These predicates expose the API so users can build custom constraint solvers.

Attribute keys are strings. Attribute values can be any term. All mutations are trailed (undone on backtracking).

### `PutAttr/3`
```clausal
# skip
PutAttr(+Var, +Key, +Value)
```
Attach attribute `Value` under string `Key` to an unbound variable. Overwrites any existing value for that key. Trailed.

---

### `GetAttr/3`
```clausal
# skip
GetAttr(+Var, +Key, -Value)
```
Retrieve the attribute stored under `Key`. Fails if `Var` has no attribute for `Key`, or if `Var` is not an unbound variable.

---

### `DelAttr/2`
```clausal
# skip
DelAttr(+Var, +Key)
```
Remove the attribute under `Key`. Succeeds even if no attribute existed (no-op). Trailed.

---

### `GetAttrs/2`
```clausal
# skip
GetAttrs(+Var, -Attrs)
```
Unify `Attrs` with a `DictTerm` containing all attributes on `Var`. Empty `DictTerm` if no attributes.

---

### `PutAttrs/2`
```clausal
# skip
PutAttrs(+Var, +Attrs)
```
Set multiple attributes from a `DictTerm`. Each key-value pair is applied via `put_attr`.

---

### `IsAttVar/1`
```clausal
# skip
IsAttVar(?Var)
```
Succeeds if `Var` is an unbound variable with at least one attribute. Fails for bound terms and for bare (non-attributed) variables.

---

### `TermAttributedVariables/2`
```clausal
# skip
TermAttributedVariables(+Term, -Vars)
```
Collect all attributed variables occurring in `Term` into a list. Traverses compound terms, lists, DictTerms, and PredicateMeta instances recursively. Each variable appears at most once.

---

## Constraint Predicates

### `Dif/2`
```clausal
# skip
Dif(+X, +Y)
```
Disequality constraint. Succeeds if `X` and `Y` can remain different (posts a constraint if either is unbound). Implemented via attributed variables; propagates through unification.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:801` → `clausal/logic/constraints.py`
    **Clausal tests:** `tests/fixtures/builtins_dif.clausal`
    **Python tests:** `tests/test_dif.py`

---

### `Eq/3` (reified)
```clausal
# skip
Eq(+X, +Y, -T)
```
Reified equality. `T` is unified with `True` if `X = Y`, `False` if `Dif(X, Y)`. Suspends if neither is determined yet.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:812` → `clausal/logic/reif.py`
    **Clausal tests:** `tests/fixtures/reif_eq_test.clausal`, `tests/fixtures/builtins_dif.clausal`
    **Python tests:** `tests/test_reif_builtins.py`

---

### `DifT/3` (reified)
```clausal
# skip
DifT(+X, +Y, -T)
```
Reified disequality. `T` is `True` if `Dif(X, Y)`, `False` if `X = Y`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:819` → `clausal/logic/reif.py`
    **Clausal tests:** `tests/fixtures/builtins_dif.clausal`
    **Python tests:** `tests/test_reif_builtins.py`

---

## CLP(FD) — Finite Domain Constraints

CLP(FD) operators (`==`, `!=`, `<`, `<=`, `>`, `>=`) are handled as **compiler special forms** mapping to `_fd_eq`, `_fd_ne`, `_fd_lt`, `_fd_le`, `_fd_gt`, `_fd_ge`. The predicates below are the builtin-registry interface.

### `InDomain/3`
```clausal
# skip
InDomain(+VarOrList, +Lo, +Hi)
```
Post the finite domain `[Lo, Hi]` on a logic variable or a list of logic variables.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:829` → `clausal/logic/clpfd.py`
    **Clausal tests:** `tests/fixtures/clpfd_queens.clausal`, `tests/fixtures/clpfd_sendmore.clausal`
    **Python tests:** `tests/test_clpfd.py`

---

### `Label/1`
```clausal
# skip
Label(+Vars)
```
Enumerate concrete values for a list of FD-constrained variables, backtracking over all consistent assignments.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:837` → `clausal/logic/clpfd.py`
    **Clausal tests:** `tests/fixtures/clpfd_queens.clausal`, `tests/fixtures/clpfd_sendmore.clausal`
    **Python tests:** `tests/test_clpfd.py`

---

### `AllDifferent/1`
```clausal
# skip
AllDifferent(+Vars)
```
Post an all-different constraint on a list of FD variables. Propagates bounds and eliminates assigned values from other domains.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:844` → `clausal/logic/clpfd.py`
    **Clausal tests:** `tests/fixtures/clpfd_queens.clausal`, `tests/fixtures/clpfd_sendmore.clausal`
    **Python tests:** `tests/test_clpfd.py`

---

### `Equivalent/2`
```clausal
# skip
Equivalent(+T1, +T2)
```
Structural equality test (old `==` behavior before CLP(FD) remapping). Succeeds if `T1` and `T2` are structurally identical after dereferencing.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:852` → `clausal/logic/clpfd.py`
    **Clausal tests:** none
    **Python tests:** `tests/test_clpfd.py`

---

### `Sum/3`
```clausal
# skip
Sum(+Vars, +Op, +Value)
```
Constrain the sum of `Vars` (a list of FD variables or integers) under comparison operator `Op` to `Value`. Supported operators: `#=`, `#<`, `#>`, `#=<`, `#>=`, `#\=`.

```clausal
# skip
Sum([X, Y, Z], "#=", 10)   % X + Y + Z = 10
```

For `#=`, posts a `SumConstraint` that propagates bounds in both directions: narrows `Value` to `[min_sum, max_sum]` and narrows each variable using the remaining slack. For inequality operators, an intermediate variable is introduced and chained with the appropriate binary relational constraint. Ground lists with a ground `Value` are checked immediately without posting a constraint.

---

### `ScalarProduct/4`
```clausal
# skip
ScalarProduct(+Coeffs, +Vars, +Op, +Value)
```
Weighted sum constraint: `Σ(Coeffs[i] * Vars[i]) Op Value`. Coefficients must be ground integers. Lists must be the same length. Supports negative coefficients — division direction is flipped accordingly when narrowing individual variables.

```clausal
# skip
ScalarProduct([2, 3], [X, Y], "#=", 12)   % 2X + 3Y = 12
```

Uses the same bounds-consistency approach as `Sum/3` (`ScalarProductConstraint`). For inequality operators, an intermediate variable is introduced and chained with a binary relational constraint.

---

### `Element/3`
```clausal
# skip
Element(?Index, +List, ?Value)
```
`Value` is the `Index`-th element of `List` (1-based indexing). When Index is ground, performs direct lookup. When Index is an FD variable, posts an `ElementConstraint` that propagates bidirectionally: narrows `Index` to positions whose list element overlaps `Value`'s domain, and narrows `Value` to the union of the domains at valid positions. Then enumerates the surviving valid indices.

```clausal
# skip
Element(2, [10, 20, 30], V)   % V = 20
Element(I, [10, 20, 30], 20)  % I = 2 (propagated without labeling)
```

---

### `Circuit/1`
```clausal
# skip
Circuit(+Vars)
```
Constrain `Vars` to form a single Hamiltonian circuit. `Vars[i] = j` means the successor of node `i+1` is node `j` (1-based). Posts a `CircuitConstraint` that: restricts all domains to `[1, n]`, removes self-loop values, enforces AllDifferent, and detects premature sub-tours via forced-chain analysis — pruning values that would close a cycle shorter than `n`. Labeling then enumerates remaining candidates.

```clausal
# skip
Circuit([2, 3, 1])         % valid: 1→2→3→1
% Circuit([1, 2, 3]) fails — self-loop at node 1
% Circuit([2, 1, 4, 3]) fails — two sub-tours (detected during propagation)
```

---

## CLP(B) — Boolean Constraints

CLP(B) uses reduced ordered BDDs (Binary Decision Diagrams) for Boolean constraint solving. Expressions use Python's bitwise operators: `&` (AND), `|` (OR), `^` (XOR), `~` (NOT), plus `BoolEq` (equivalence) and `BoolImpl` (implication) term constructors.

### `Sat/1`
```clausal
# skip
Sat(+Expr)
```
Post a Boolean constraint. The expression must evaluate to true. Fails if unsatisfiable. Propagates forced values (e.g., `Sat(X & Y)` forces both to 1).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/constraints.py` → `clausal/logic/clpb.py`
    **Clausal tests:** `tests/fixtures/clpb_circuit.clausal`
    **Python tests:** `tests/test_clpb.py`

---

### `Taut/2`
```clausal
# skip
Taut(+Expr, -T)
```
Tautology check. Unify `T` with 1 if `Expr` is always true, 0 if always false. Fail if indeterminate.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/constraints.py` → `clausal/logic/clpb.py`
    **Clausal tests:** none
    **Python tests:** `tests/test_clpb.py`

---

### `SatCount/2`
```clausal
# skip
SatCount(+Expr, -N)
```
Count the number of satisfying assignments for `Expr`. Unify `N` with the count.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/constraints.py` → `clausal/logic/clpb.py`
    **Clausal tests:** none
    **Python tests:** `tests/test_clpb.py`

---

### `BoolLabeling/1`
```clausal
# skip
BoolLabeling(+Vars)
```
Enumerate 0/1 assignments for a list of Boolean variables. Backtracks over all satisfying assignments.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/constraints.py` → `clausal/logic/clpb.py`
    **Clausal tests:** `tests/fixtures/clpb_circuit.clausal`
    **Python tests:** `tests/test_clpb.py`

---

## Type Checks

### `IsVar/1`
```clausal
# skip
IsVar(?X)
```
Succeeds if `X` is an unbound logic variable.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:863`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `IsBound/1`
```clausal
# skip
IsBound(?X)
```
Succeeds if `X` is bound (not an unbound `Var`).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:870`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `IsStr/1`
```clausal
# skip
IsStr(+X)
```
Succeeds if `X` is a Python `str` (the atom equivalent).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:877`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `IsNumber/1`
```clausal
# skip
IsNumber(+X)
```
Succeeds if `X` is an `int` or `float` (excludes `bool`).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:885`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `IsInt/1`
```clausal
# skip
IsInt(+X)
```
Succeeds if `X` is an `int` (excludes `bool`).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:897`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `IsFloat/1`
```clausal
# skip
IsFloat(+X)
```
Succeeds if `X` is a Python `float`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:905`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `IsCompound/1`
```clausal
# skip
IsCompound(+X)
```
Succeeds if `X` is a compound term with arity > 0 (`Compound`, `KWTerm`, or `PredicateMeta` instance with at least one field).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:921`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `IsCallable/1`
```clausal
# skip
IsCallable(+X)
```
Succeeds if `X` is an atom (string) or a compound term.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:935`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `IsList/1`
```clausal
# skip
IsList(+X)
```
Succeeds if `X` is a Python `list`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:947`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `IsGround/1`
```clausal
# skip
IsGround(+X)
```
Succeeds if `X` contains no unbound `Var`s (is fully instantiated).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:954`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `MustBe/2`
```clausal
# skip
MustBe(+Type, +Term)
```
Assert that `Term` is of the given type. Succeeds silently if it matches. Throws `instantiation_error` if Term is unbound. Throws `type_error(Type, Term, "must_be/2")` if Term is ground but wrong type.

Supported type strings: `"integer"`, `"float"`, `"number"`, `"atom"` / `"string"`, `"list"`, `"boolean"`, `"callable"`, `"dict"`, `"compound"`.

---

### `CanBe/2`
```clausal
# skip
CanBe(+Type, ?Term)
```
Assert that `Term` could possibly be of the given type. Succeeds if Term is unbound (it could become anything) or already matches the type. Throws `type_error` only when Term is ground and definitely the wrong type. Same type strings as `MustBe/2`.

---

## Dict and Set Predicates

Dict and set builtins operate on `DictTerm` and `SetTerm` values. Plain Python `dict` and `set` are not accepted. See [Dicts and Sets](dicts_sets.md) for the full design.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/dict_set.py`
    **Python tests:** `tests/test_dict_set_builtins.py` (79 tests)
    **Fixture:** `tests/fixtures/dict_set_builtins.clausal`

### `IsDict/1`
```clausal
# skip
IsDict(+Term)
```
Succeeds if `Term` is a `DictTerm`.

---

### `DictSize/2`
```clausal
# skip
DictSize(+Dict, -N)
```
`N` is the number of keys in `Dict`.

---

### `DictKeys/2`
```clausal
# skip
DictKeys(+Dict, -Keys)
```
`Keys` is the sorted list of keys (sorted by `repr` for cross-type determinism).

---

### `DictValues/2`
```clausal
# skip
DictValues(+Dict, -Values)
```
`Values` is the list of values in key-sorted order.

---

### `DictPairs/2`
```clausal
# skip
DictPairs(?Dict, ?Pairs)
```
Bidirectional: `Dict` ↔ list of `[Key, Value]` 2-element lists. In dict→pairs direction, pairs are sorted by key.

---

### `DictGet/3`
```clausal
# skip
DictGet(+Key, +Dict, ?Value)
```
Semidet lookup. Fails if `Key` is absent or unbound.

---

### `DictPut/4`
```clausal
# skip
DictPut(+Key, +Value, +OldDict, -NewDict)
```
Functional update: `NewDict` is `OldDict` with `Key → Value` set. Returns a new `DictTerm`.

---

### `DictPutPairs/3`
```clausal
# skip
DictPutPairs(+Pairs, +OldDict, -NewDict)
```
Bulk update from a `[[Key, Value], ...]` list. Equivalent to repeated `DictPut/4`.

---

### `DictRemove/3`
```clausal
# skip
DictRemove(+Key, +OldDict, -NewDict)
```
`NewDict` is `OldDict` without `Key`. Fails if `Key` is absent.

---

### `DictMerge/3`
```clausal
# skip
DictMerge(+D1, +D2, -Merged)
```
Union of `D1` and `D2`. Where keys conflict, `D2`'s value wins.

---

### `GenDict/3`
```clausal
# skip
GenDict(?Key, +Dict, ?Value)
```
Nondeterministic enumeration. Yields one `Key`/`Value` binding per solution on backtracking. Can be filtered by binding `Key` before the call.

---

### `SubDict/2`
```clausal
# skip
SubDict(+Pattern, +Dict)
```
Partial dict matching. Succeeds when every key in `Pattern` is present in `Dict` and the values unify. Extra keys in `Dict` are ignored. See [SubDict](dicts_sets.md#partial-dict-matching--subdict2) for examples.

---

### `IsSet/1`
```clausal
# skip
IsSet(+Term)
```
Succeeds if `Term` is a `SetTerm`.

---

### `SetSize/2`
```clausal
# skip
SetSize(+Set, -N)
```
`N` is the cardinality of `Set`.

---

### `SetList/2`
```clausal
# skip
SetList(?Set, ?List)
```
Bidirectional: `Set` ↔ sorted list. In list→set direction, duplicates are removed.

---

### `SetUnion/3`
```clausal
# skip
SetUnion(+S1, +S2, -Union)
```
Set union.

---

### `SetIntersection/3`
```clausal
# skip
SetIntersection(+S1, +S2, -Inter)
```
Set intersection.

---

### `SetSubtract/3`
```clausal
# skip
SetSubtract(+S1, +S2, -Diff)
```
`Diff` = elements in `S1` not in `S2`.

---

### `SetSymDiff/3`
```clausal
# skip
SetSymDiff(+S1, +S2, -Sym)
```
Symmetric difference: elements in exactly one of `S1`, `S2`.

---

### `SetSubset/2`
```clausal
# skip
SetSubset(+Sub, +Super)
```
Succeeds if `Sub` is a subset of `Super` (including equal sets and the empty set).

---

### `SetDisjoint/2`
```clausal
# skip
SetDisjoint(+S1, +S2)
```
Succeeds if `S1` and `S2` share no elements.

---

### `SetAdd/3`
```clausal
# skip
SetAdd(+Elem, +OldSet, -NewSet)
```
`NewSet` is `OldSet` with `Elem` added. No-op if already present.

---

### `SetRemove/3`
```clausal
# skip
SetRemove(+Elem, +OldSet, -NewSet)
```
`NewSet` is `OldSet` with `Elem` removed. No-op if absent.

---

### `GenSet/2`
```clausal
# skip
GenSet(?Elem, +Set)
```
Nondeterministic enumeration of set elements. Order is deterministic (sorted by `repr`).

---

## Arithmetic

Arithmetic uses `==` to post CLP(FD) constraints (e.g., `Y == X * 2`). The predicates below provide relational arithmetic usable in both input and output modes.

### `Between/3`
```clausal
# skip
Between(+Low, +High, ?X)
```
Check or enumerate integers in `[Low, High]` inclusive. In check mode (X bound) succeeds iff `Low ≤ X ≤ High`. In generate mode (X unbound) backtracks over each integer.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:964`
    **Clausal tests:** `tests/fixtures/builtins_arith.clausal`
    **Python tests:** `tests/test_builtins.py`, `tests/test_search.py`

---

### `Succ/2`
```clausal
# skip
Succ(?X, ?Y)   % Y = X + 1
```
Bidirectional successor: if `X` is bound, `Y = X + 1`; if `Y` is bound, `X = Y - 1`. Both must be non-negative integers.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:987`
    **Clausal tests:** `tests/fixtures/builtins_arith.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Plus/3`
```clausal
# skip
Plus(?X, ?Y, ?Z)   % Z = X + Y
```
Relational addition: any two of `X`, `Y`, `Z` determine the third.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1008`
    **Clausal tests:** `tests/fixtures/builtins_arith.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Abs/2`
```clausal
# skip
Abs(+X, -Y)   % Y = abs(X)
```
Absolute value.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1035`
    **Clausal tests:** `tests/fixtures/builtins_arith.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Max/3`
```clausal
# skip
Max(+X, +Y, -Z)   % Z = max(X, Y)
```
??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1049`
    **Clausal tests:** `tests/fixtures/builtins_arith.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Min/3`
```clausal
# skip
Min(+X, +Y, -Z)   % Z = min(X, Y)
```
??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1062`
    **Clausal tests:** `tests/fixtures/builtins_arith.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Sign/2`
```clausal
# skip
Sign(+X, -S)   % S is -1, 0, or 1
```
Sign of X. Returns -1 for negative, 0 for zero, 1 for positive. Supports Quantity values (result is always a dimensionless integer).

---

### `Gcd/3`
```clausal
# skip
Gcd(+X, +Y, -G)   % G = gcd(X, Y)
```
Greatest common divisor of two integers. Supports Quantity values — dimensions must agree; result preserves dimensions.

---

### `DivMod/4`
```clausal
# skip
DivMod(+X, +Y, -Q, -R)   % Q = X // Y, R = X mod Y
```
Integer division and modulus. Fails if Y is 0. Supports Quantity values — dimensions must agree; quotient Q is dimensionless, remainder R preserves dimensions.

---

### `Lcm/3`
```clausal
# skip
Lcm(+X, +Y, -L)   % L = lcm(X, Y)
```
Least common multiple of two integers. Supports Quantity values — dimensions must agree; result preserves dimensions.

---

### `ExpMod/4`
```clausal
# skip
ExpMod(+Base, +Exp, +Mod, -Result)   % Result = Base^Exp mod Mod
```
Modular exponentiation using Python's efficient `pow(base, exp, mod)`. Integer-only (no Quantity support). Fails if Mod is 0.

---

### `Popcount/2`
```clausal
# skip
Popcount(+X, -Count)   % Count = number of set bits in X
```
Population count (number of 1 bits). X must be a non-negative integer.

---

### `Msb/2`
```clausal
# skip
Msb(+X, -Bit)   % Bit = position of most significant set bit (0-indexed)
```
Most significant bit position. X must be a positive integer. `Msb(8, B)` gives B=3.

---

### `Lsb/2`
```clausal
# skip
Lsb(+X, -Bit)   % Bit = position of least significant set bit (0-indexed)
```
Least significant bit position. X must be a positive integer. `Lsb(12, B)` gives B=2.

---

!!! note "Quantity support in arithmetic"
    `Plus`, `Abs`, `Max`, `Min`, `Sign`, `Gcd`, `DivMod`, and `Lcm` all accept
    `Quantity` values (numbers with physical dimensions). Dimension mismatches
    raise `UnitsMismatch` — they are not silenced. `ExpMod`, `Popcount`, `Msb`,
    and `Lsb` are integer-only (bitwise operations have no dimensional
    interpretation).

---

## List Predicates

### `In/2`
```clausal
# skip
In(?Elem, +List)
```
Enumerate or check membership. Backtracks over all elements.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1078`
    **Clausal tests:** `tests/fixtures/meta_test.clausal`, `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`, `tests/test_search.py`

---

### `InCheck/2`
```clausal
# skip
InCheck(+Elem, +List)
```
Deterministic membership check. Succeeds at most once; no backtracking.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1091`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Append/3`
```clausal
# skip
Append(?L1, ?L2, ?L3)   % L3 = L1 ++ L2
```
List concatenation. Works in all modes: given any two, determines the third. Backtracks over splits when `L3` is bound and `L1`/`L2` are unbound.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1105`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`, `tests/test_search.py`

---

### `Length/2`
```clausal
# skip
Length(+List, -N)   % N = len(List)
Length(-List, +N)   % construct list of N fresh vars
```
List length in both directions.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1141`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Last/2`
```clausal
# skip
Last(+List, -Elem)
```
Unify `Elem` with the last element of `List`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1159`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`, `tests/test_search.py`

---

### `Reverse/2`
```clausal
# skip
Reverse(+List, -Rev)
```
??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1170`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`, `tests/test_search.py`

---

### `GetItem/3`
```clausal
# skip
GetItem(+N, +List, -Elem)   % 0-based
```
Get the element at 0-based index `N`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1181`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Flatten/2`
```clausal
# skip
Flatten(+Nested, -Flat)
```
Recursively flatten a nested list structure.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1225`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `MergeSort/2`
```clausal
# skip
MergeSort(+List, -Sorted)
```
Sort `List` preserving duplicate elements (stable sort).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1248`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Sort/2`
```clausal
# skip
Sort(+List, -Sorted)
```
Sort `List` removing duplicate elements.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1265`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Permutation/2`
```clausal
# skip
Permutation(+List, -Perm)
```
Enumerate all permutations of `List` via backtracking.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1286`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`, `tests/test_search.py`

---

### `Select/3`
```clausal
# skip
Select(?Elem, +List, -Rest)
```
Select `Elem` from `List`, unifying `Rest` with the remaining elements. Backtracks over all positions where `Elem` appears.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1300`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Subtract/3`
```clausal
# skip
Subtract(+Set1, +Set2, -Diff)
```
List difference: elements in `Set1` not in `Set2`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1314`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Intersection/3`
```clausal
# skip
Intersection(+Set1, +Set2, -Inter)
```
Elements present in both `Set1` and `Set2`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1328`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Union/3`
```clausal
# skip
Union(+Set1, +Set2, -Union)
```
Elements in `Set1` or `Set2`, with duplicates removed.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1342`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `ToSet/2`
```clausal
# skip
ToSet(+List, -Set)
```
Remove duplicates from `List` preserving the first-occurrence order.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1359`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `SumList/2`
```clausal
# skip
SumList(+List, -Sum)
```
Sum all numeric elements of `List`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1375`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `MaxList/2`
```clausal
# skip
MaxList(+List, -Max)
```
Maximum element of a non-empty numeric list.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1391`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `MinList/2`
```clausal
# skip
MinList(+List, -Min)
```
Minimum element of a non-empty numeric list.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1407`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Take/3`
```clausal
# skip
Take(+N, +List, -Taken)
```
First `N` elements of `List`. If `N > len(List)`, returns the whole list. If `N = 0`, returns `[]`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/lists.py` (`_take__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `Drop/3`
```clausal
# skip
Drop(+N, +List, -Rest)
```
`List` after dropping the first `N` elements. If `N >= len(List)`, returns `[]`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/lists.py` (`_drop__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `SplitAt/4`
```clausal
# skip
SplitAt(+N, +List, -Left, -Right)
```
Split `List` at index `N` into `Left` (first N elements) and `Right` (rest). Clamps to list bounds.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/lists.py` (`_split_at__4`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `Zip/3`
```clausal
# skip
Zip(+List1, +List2, -Pairs)
```
Pair up elements from two lists into `[X, Y]` sublists. Truncates to the shorter list.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/lists.py` (`_zip__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `Replicate/3`
```clausal
# skip
Replicate(+N, +Elem, -List)
```
`List` of `N` copies of `Elem`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/lists.py` (`_replicate__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `SplitWith/3`
```clausal
# skip
SplitWith(+Sep, +List, -Parts)    % split mode
SplitWith(+Sep, -List, +Parts)    % join mode
```
Split `List` by separator `Sep` into sublists (`Parts`). In join mode, interleaves `Parts` with `Sep`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/lists.py` (`_split_with__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `Unzip/3`
```clausal
# skip
Unzip(?Pairs, ?Keys, ?Values)
```
Relate a list of `[K, V]` pairs to separate `Keys` and `Values` lists. Works in both directions.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1426`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `PairKeys/2`
```clausal
# skip
PairKeys(+Pairs, -Keys)
```
Extract the key (first element) from each pair.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1450`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `PairValues/2`
```clausal
# skip
PairValues(+Pairs, -Values)
```
Extract the value (second element) from each pair.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1463`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `GroupPairsByKey/2`
```clausal
# skip
GroupPairsByKey(+Pairs, -Groups)
```
Group a list of `[Key, Value]` pairs by key. Groups is a list of `[Key, Values]` where Values collects all values for that key. Order is preserved (first occurrence of key determines group order).

```clausal
# skip
GroupPairsByKey([["a", 1], ["b", 2], ["a", 3]], GROUPS)
% GROUPS = [["a", [1, 3]], ["b", [2]]]
```

---

### `Numlist/3`
```clausal
# skip
Numlist(+Low, +High, -List)
```
List is the list of integers from Low to High inclusive. Fails if Low > High.

```clausal
# skip
Numlist(1, 5, L)   % L = [1, 2, 3, 4, 5]
```

---

### `Numlist/2`
```clausal
# skip
Numlist(+High, -List)
```
Shorthand for `Numlist(1, High, List)`.

---

### `SameLength/2`
```clausal
# skip
SameLength(?L1, ?L2)
```
Succeeds if L1 and L2 have the same length. If one is ground and the other is unbound, generates a list of fresh variables with matching length.

---

### `Transpose/2`
```clausal
# skip
Transpose(+Matrix, -Transposed)
```
Column-wise transposition of a list of lists. All rows must be the same length (fails on non-rectangular input). Empty matrix transposes to empty list.

```clausal
# skip
Transpose([[1, 2], [3, 4]], T)   % T = [[1, 3], [2, 4]]
```

---

## Higher-Order List Predicates

These predicates accept a **goal argument** (a lambda or named predicate). The goal is called for each list element; failures propagate as in standard higher-order patterns.

### `MapList/2`
```clausal
# skip
MapList(+Goal, +List)
```
Verify that `Goal(Elem)` succeeds for every element of `List`. Fails if any element fails.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1541`
    **Clausal tests:** `tests/fixtures/builtins_higher_order.clausal`
    **Python tests:** `tests/test_higher_order.py`

---

### `MapList/3`
```clausal
# skip
MapList(+Goal, +Xs, -Ys)
```
Map `Goal(X, Y)` over `Xs` to produce `Ys`. Takes the first solution of `Goal` per element.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1563`
    **Clausal tests:** `tests/fixtures/builtins_higher_order.clausal`
    **Python tests:** `tests/test_higher_order.py`

---

### `Filter/3`
```clausal
# skip
Filter(+Goal, +List, -Included)
```
Filter `List` keeping only elements for which `Goal(Elem)` succeeds.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1589`
    **Clausal tests:** `tests/fixtures/builtins_higher_order.clausal`
    **Python tests:** `tests/test_higher_order.py`

---

### `Exclude/3`
```clausal
# skip
Exclude(+Goal, +List, -Excluded)
```
Filter `List` keeping only elements for which `Goal(Elem)` **fails**.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1614`
    **Clausal tests:** `tests/fixtures/builtins_higher_order.clausal`
    **Python tests:** `tests/test_higher_order.py`

---

### `Partition/4`
```clausal
# skip
Partition(+Goal, +List, -Included, -Excluded)
```
Split `List` into two: `Included` contains elements where `Goal(Elem)` succeeds, `Excluded` contains elements where it fails.

```clausal
# skip
Partition(IsInt, [1, "a", 2, "b"], YES, NO)
% YES = [1, 2], NO = ["a", "b"]
```

---

### `TFilter/3`
```clausal
# skip
TFilter(+Goal, +List, -Filtered)
```
Reified filter. Calls `Goal(Elem, T)` where T is a fresh variable bound to `True` or `False` by the goal. Keeps elements where T=True. Committed choice: only the first solution of Goal is used.

Useful with reified predicates like `Eq/3` and `DifT/3` that always succeed but bind their truth-value argument.

```clausal
# skip
TFilter(Eq(_, 1), [1, 2, 1, 3], FILTERED)
% FILTERED = [1, 1]
```

---

### `TPartition/4`
```clausal
# skip
TPartition(+Goal, +List, -Included, -Excluded)
```
Reified partition. Calls `Goal(Elem, T)` for each element. Elements where T=True go into `Included`, T=False into `Excluded`.

```clausal
# skip
TPartition(Eq(_, 1), [1, 2, 1, 3], YES, NO)
% YES = [1, 1], NO = [2, 3]
```

---

### `FoldLeft/4`
```clausal
# skip
FoldLeft(+Goal, +List, +V0, -V)
```
Left fold. Calls `Goal(Elem, Acc0, Acc1)` for each element, threading the accumulator. `V0` is the initial value; `V` is the final result.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1639`
    **Clausal tests:** `tests/fixtures/builtins_higher_order.clausal`
    **Python tests:** `tests/test_higher_order.py`

---

### `TakeWhile/3`
```clausal
# skip
TakeWhile(+Goal, +List, -Prefix)
```
Longest prefix of `List` where `Goal(Elem)` succeeds for each element.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_take_while__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `DropWhile/3`
```clausal
# skip
DropWhile(+Goal, +List, -Suffix)
```
Suffix of `List` after dropping the longest prefix where `Goal(Elem)` succeeds.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_drop_while__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `Span/4`
```clausal
# skip
Span(+Goal, +List, -Yes, -No)
```
`TakeWhile` + `DropWhile` in one pass. `Yes` is the longest prefix where `Goal` succeeds; `No` is the rest.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_span__4`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `GroupBy/3`
```clausal
# skip
GroupBy(+Goal, +List, -Groups)
```
Group consecutive elements by key projected via `Goal(Elem, Key)`. Elements with equal consecutive keys are collected into sublists.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_group_by__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `SortBy/3`
```clausal
# skip
SortBy(+Goal, +List, -Sorted)
```
Sort `List` by key projected via `Goal(Elem, Key)`. Stable sort (preserves order of equal keys).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_sort_by__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `MaxBy/3`
```clausal
# skip
MaxBy(+Goal, +List, -Max)
```
Element of `List` with the largest key projected via `Goal(Elem, Key)`. Fails on empty list.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_max_by__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `MinBy/3`
```clausal
# skip
MinBy(+Goal, +List, -Min)
```
Element of `List` with the smallest key projected via `Goal(Elem, Key)`. Fails on empty list.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_min_by__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `FilterMap/3`
```clausal
# skip
FilterMap(+Goal, +List, -Result)
```
Map + filter in one pass. Calls `Goal(Elem, Out)` for each element; keeps `Out` when the goal succeeds, skips the element when it fails.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_filter_map__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

## Character/String

Logic-aware character and string predicates that participate in unification and backtracking. Unlike Python string methods, these are *relations* — e.g. `AtomConcat(A, B, "hello")` with A and B unbound enumerates all splits, `CharType(C, digit)` enumerates digits.

### `CharType/2`
```clausal
# skip
CharType(?Char, ?Type)
```
Character classification as a relation. At least one argument must be bound. Types: `alpha`, `digit`, `alnum`, `space`, `upper`, `lower`, `ascii`, `punct`, `print`, `control`. With Char bound, enumerates matching types. With Type bound, enumerates matching ASCII characters. With both bound, tests membership.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/chars.py`
    **Python tests:** `tests/test_chars.py`

---

### `CharCode/2`
```clausal
# skip
CharCode(?Char, ?Code)
```
Bidirectional char ↔ integer code point conversion. `CharCode('A', N)` unifies N with 65. `CharCode(C, 65)` unifies C with `'A'`. Both bound tests equality. Both unbound raises `instantiation_error`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/chars.py`
    **Python tests:** `tests/test_chars.py`

---

### `UpcaseAtom/2`
```clausal
# skip
UpcaseAtom(+Atom, -Upper)
```
Unify `Upper` with the uppercase version of `Atom`. First argument must be bound to a string.

---

### `DowncaseAtom/2`
```clausal
# skip
DowncaseAtom(+Atom, -Lower)
```
Unify `Lower` with the lowercase version of `Atom`. First argument must be bound to a string.

---

### `AtomLength/2`
```clausal
# skip
AtomLength(+Atom, ?Length)
```
Unify `Length` with the length of `Atom`. First argument must be bound.

---

### `AtomChars/2`
```clausal
# skip
AtomChars(?Atom, ?Chars)
```
Bidirectional conversion between a string and a list of single-character strings. `AtomChars("hi", L)` unifies L with `['h', 'i']`. `AtomChars(A, ['h', 'i'])` unifies A with `"hi"`.

---

### `AtomCodes/2`
```clausal
# skip
AtomCodes(?Atom, ?Codes)
```
Bidirectional conversion between a string and a list of integer code points. `AtomCodes("hi", L)` unifies L with `[104, 105]`.

---

### `AtomConcat/3`
```clausal
# skip
AtomConcat(?A, ?B, ?C)
```
String concatenation as a relation. Forward: A and B bound → unify C with `A + B`. Reverse: C bound, A and/or B unbound → enumerate all splits. `AtomConcat(A, B, "abc")` yields 4 solutions: `("","abc")`, `("a","bc")`, `("ab","c")`, `("abc","")`. Optimized paths for prefix/suffix-bound cases.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/chars.py`
    **Python tests:** `tests/test_chars.py`

---

### `SubAtom/5`
```clausal
# skip
SubAtom(+Atom, ?Before, ?Length, ?After, ?Sub)
```
Substring relation. Relates `Atom` to its substrings with position information: `Before + Length + After = len(Atom)`, `Sub = Atom[Before:Before+Length]`. Multi-modal — any combination of bound/unbound arguments works (Atom must be bound). With Sub bound, uses `str.find()` for efficient lookup. Otherwise enumerates all valid `(Before, Length)` pairs.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/chars.py`
    **Python tests:** `tests/test_chars.py`

---

### `NumberChars/2`
```clausal
# skip
NumberChars(?Number, ?Chars)
```
Bidirectional number ↔ character-list conversion. Number bound → `Chars` unifies with `list(str(Number))`. Chars bound (list of single-char strings) → parse as `int` or `float`. Both bound → test equality. Both unbound → instantiation error. Rejects `bool` values (not considered numbers).

```clausal
# skip
NumberChars(42, ["4", "2"])        # succeeds
NumberChars(-3.14, CHARS)          # CHARS = ["-", "3", ".", "1", "4"]
NumberChars(N, ["1", "0"])         # N = 10
```

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/chars.py`
    **Python tests:** `tests/test_chars.py`

---

### `NumberCodes/2`
```clausal
# skip
NumberCodes(?Number, ?Codes)
```
Bidirectional number ↔ code-point-list conversion. Like `NumberChars/2` but uses integer code points (`ord`/`chr`) instead of single-character strings.

```clausal
# skip
NumberCodes(42, [52, 50])          # succeeds (ord("4")=52, ord("2")=50)
NumberCodes(N, [52, 50])           # N = 42
```

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/chars.py`
    **Python tests:** `tests/test_chars.py`

---

## I/O

### `Write/1`
```clausal
# skip
Write(+Term)
```
Print `Term` to stdout without a trailing newline. Strings are printed as-is; other values use `str()`. Logic variables are auto-dereferenced — bound vars print their value, unbound vars print `_N`. F-strings work naturally: `f"{X}"` derefs `X` at search time.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`Write/1`)
    **Python tests:** `tests/test_io.py`

---

### `Writeln/1`
```clausal
# skip
Writeln(+Term)
```
Like `Write/1` but appends a newline.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`Writeln/1`)
    **Python tests:** `tests/test_io.py`

---

### `PrintTerm/1`
```clausal
# skip
PrintTerm(+Term)
```
Print the structured `term_str` representation of `Term` (strings are quoted, compounds show functor/args) followed by a newline. Useful for debugging.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`PrintTerm/1`)
    **Python tests:** `tests/test_io.py`

---

### `Nl/0`
```clausal
# skip
Nl
```
Print a newline to stdout. Equivalent to `Write("\n")`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`Nl/0`)
    **Python tests:** `tests/test_io.py`

---

### `Tab/1`
```clausal
# skip
Tab(+N)
```
Print `N` spaces to stdout. `N` must be a bound non-negative integer.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`Tab/1`)
    **Python tests:** `tests/test_io.py`

---

### `WriteToString/2`
```clausal
# skip
WriteToString(+Term, -String)
```
Unify `String` with the `Write`-style string representation of `Term` (strings pass through, others use `str()`). Does not print anything.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`WriteToString/2`)
    **Python tests:** `tests/test_io.py`

---

### `TermToString/2`
```clausal
# skip
TermToString(+Term, -String)
```
Unify `String` with the `term_str` representation of `Term` (structured, with quoted strings). Does not print anything.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`TermToString/2`)
    **Python tests:** `tests/test_io.py`

---

### `Listing/1`
```clausal
# skip
Listing(+Predicate)
```
Print all clauses of a predicate to stdout in readable Clausal syntax. Accepts a `PredicateMeta` class or instance. Prints a header comment with clause count, followed by each clause formatted as `head.` (fact) or `head <- (body).` (rule). Reports "no clauses" for empty predicates and "builtin" for builtin predicates.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/io.py` (`Listing/1`)
    **Python tests:** `tests/test_listing.py`

---

### `PortrayClause/1`
```clausal
# skip
PortrayClause(+Term)
```
Pretty-print a term with indentation for multi-line display using `term_pformat`. Short terms appear on one line; deeply nested terms are expanded with depth indentation.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/io.py` (`PortrayClause/1`)
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

Standard library module wrapping Python's PyYAML. Import via `-import_from(yaml_module, [Read, Write, Get, ...])`. Data is represented as **native Python objects** — `dict`, `list`, `str`, `int`, `float`, `bool`, `None` — exactly what `yaml.safe_load` returns. Any Python method can be called on them via `++()` interop. See [yaml.md](yaml.md) for full documentation.

Only `yaml.safe_load` is used (no arbitrary object construction from YAML tags).

### `Read/2`

```clausal
# skip
Read(+YamlString, -Data)
```

Parse a YAML string into a Python object (dict/list/scalar). Fails on invalid YAML.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/yaml_module.py`

### `Write/2`

```clausal
# skip
Write(+Data, -YamlString)
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

Write a Python object as YAML to a file.

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
| `X is not Y` | Disequality constraint (`Dif/2`) | `compiler.py:1436` |
| `X == Expr` | Arithmetic constraint (CLP(FD)) | `compiler.py` (`Evaluate`) |
| `X == Y` | CLP(FD) equality constraint | `compiler.py:1444` |
| `X != Y` | CLP(FD) disequality constraint | `compiler.py:1451` |
| `X < Y` | CLP(FD) less-than constraint | `compiler.py:1459` |
| `X <= Y` | CLP(FD) less-or-equal constraint | `compiler.py:1466` |
| `X > Y` | CLP(FD) greater-than constraint | `compiler.py:1473` |
| `X >= Y` | CLP(FD) greater-or-equal constraint | `compiler.py:1480` |
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
    | `tests/fixtures/clpfd_queens.clausal` | `InDomain/3`, `AllDifferent/1`, `Label/1` |
    | `tests/fixtures/clpfd_sendmore.clausal` | `InDomain/3`, `AllDifferent/1`, `Label/1` |
    | `tests/fixtures/wfs_win.clausal` | well-founded semantics, `not` on tabled |
    | `tests/fixtures/wfs_win_asym.clausal` | well-founded semantics, asymmetric |
    | `tests/fixtures/reified_memberd.clausal` | `If/3`, `Dif/2` (reified ITE) |
    | `tests/fixtures/reified_max.clausal` | `If/3` with arithmetic |
    | `tests/fixtures/reif_eq_test.clausal` | `Eq/3` |
    | `tests/fixtures/once_member.clausal` | `Once/1` |
    | `tests/fixtures/meta_test.clausal` | `FindAll/3`, `SetOf/3`, `ForAll/2`, `In/2` |
    | `tests/fixtures/builtins_inspect.clausal` | `Functor/3`, `Arg/3`, `Unpack/2` |
    | `tests/clausal_modules/term_inspection.clausal` | `CopyTerm/2`, `TermVariables/2`, `NumberVars/3` |
    | `tests/fixtures/builtins_db.clausal` | `Assert/1`, `AssertFirst/1`, `Retract/1` |
    | `tests/fixtures/builtins_types.clausal` | `IsVar/1`, `IsBound/1`, `IsStr/1`, `IsNumber/1`, `IsInt/1`, `IsFloat/1`, `IsCompound/1`, `IsCallable/1`, `IsList/1`, `IsGround/1` |
    | `tests/fixtures/builtins_arith.clausal` | `Between/3`, `Succ/2`, `Plus/3`, `Abs/2`, `Max/3`, `Min/3` |
    | `tests/fixtures/builtins_lists.clausal` | `In/2`, `InCheck/2`, `Append/3`, `Length/2`, `Last/2`, `Reverse/2`, `GetItem/3`, `Flatten/2`, `MergeSort/2`, `Sort/2`, `Permutation/2`, `Select/3`, `Subtract/3`, `Intersection/3`, `Union/3`, `ToSet/2`, `SumList/2`, `MaxList/2`, `MinList/2`, `Unzip/3`, `PairKeys/2`, `PairValues/2` |
    | `tests/fixtures/builtins_higher_order.clausal` | `MapList/2`, `MapList/3`, `Filter/3`, `Exclude/3`, `FoldLeft/4` |
    | `tests/fixtures/list_util.clausal` | `Take/3`, `Drop/3`, `SplitAt/4`, `Zip/3`, `Replicate/3`, `SplitWith/3`, `TakeWhile/3`, `DropWhile/3`, `Span/4`, `GroupBy/3`, `SortBy/3`, `MaxBy/3`, `MinBy/3`, `FilterMap/3` |
    | `tests/fixtures/builtins_keywords.clausal` | `Vary/3`, `Extend/3`, `UnboundKeys/2`, `Signature/3` |
    | `tests/fixtures/builtins_dif.clausal` | `Dif/2`, `Eq/3`, `DifT/3` |
    | `tests/fixtures/builtins_call.clausal` | `Call/N`, `CallGoal/N` |
    | `tests/fixtures/coroutining.clausal` | `CallNth/2`, `CountAll/2`, `SetupCallCleanup/3`, `CallCleanup/2`, `Freeze/2`, `When/2` |
    | `tests/test_python_interop.py` | `++()` Python interop (13 tests) |
    | `tests/test_dcg.py` | DCG rules, `phrase/2`, `phrase/3` (26 tests) |
    | `tests/fixtures/dcg_grammar.clausal` | `phrase/2`, `phrase/3`, DCG with non-terminals, inline goals, pushback, negation |
    | `tests/fixtures/clpb_circuit.clausal` | `Sat/1`, `BoolLabeling/1`, `BoolEq` — HalfAdder, FullAdder, PigeonHole |
    | `tests/fixtures/logging_basic.clausal` | `GetLogger`, `SetLevel`, `GetLevel`, `IsEnabledFor`, `Debug`, `Info`, `Warning`, `Error`, `Critical`, `Log`, `StreamHandler`, `SetFormatter`, `AddHandler`, `RemoveHandler` |
    | `tests/test_date_time.py` | `Now`, `NowUTC`, `Today`, `Date`, `Time`, `DateTime`, `TimeDelta`, `DateAdd`, `DateSub`, `DateDiff`, `FormatDate`, `ParseDate`, `DayOfWeek`, `DateBetween` (64 tests) |
    | `tests/test_yaml_module.py` | `Read`, `Write`, `ReadAll`, `WriteAll`, `ReadFile`, `WriteFile`, `Get` (45 tests) |
    | `tests/fixtures/yaml_basic.clausal` | `Read`, `Write`, `Get` — parsing, nested access, round-trip |
