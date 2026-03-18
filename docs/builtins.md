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

## Control Flow

These are **compiler special forms** — transformed at compile time, not dispatched via the builtin registry.

### `Once/1`
```
Once(+Goal)
```
Commit to the first solution of `Goal`; succeeds at most once even if `Goal` has multiple solutions.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py:1619` (`_compile_once`)
    **Clausal tests:** `tests/fixtures/once_member.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Not/1`
```
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
```
If(+Cond, +Then, +Else)
```
If `Cond` has a solution, run `Then`; otherwise run `Else`. Soft-cut: only the first solution of `Cond` is tried. Compiles to a reified if-then-else that propagates constraints in both branches.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py` (`_compile_ite_trampoline`)
    **Clausal tests:** `tests/fixtures/reified_memberd.clausal`, `tests/fixtures/tabled_ite.clausal`, `tests/fixtures/reified_max.clausal`
    **Python tests:** `tests/test_reified_ite.py`

---

### `throw/1`
```
throw(+Term)
```
Raise a logic-level exception carrying `Term`. The exception propagates through the generator/trampoline chain until caught by `catch/3` or surfaces as a Python `LogicException`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py` (`_compile_throw`)
    **Exception class:** `clausal/logic/exceptions.py` (`LogicException`)
    **Clausal tests:** `tests/clausal_modules/exceptions.clausal`
    **Python tests:** `tests/test_exceptions.py`

---

### `catch/3`
```
catch(+Goal, ?Catcher, +Recovery)
```
Execute `Goal`. If `Goal` throws a `LogicException`, unify the thrown term with `Catcher`. If unification succeeds, execute `Recovery`; otherwise re-raise. If `Goal` succeeds without throwing, `catch/3` is transparent — all solutions pass through.

Trail bindings from the failing goal are undone before recovery runs. The `Catcher` can be a variable (catches everything) or a specific term (selective).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py` (`_compile_catch`, `_compile_catch_trampoline`)
    **Clausal tests:** `tests/clausal_modules/exceptions.clausal`
    **Python tests:** `tests/test_exceptions.py`

---

### `halt/0`, `halt/1`
```
halt
halt(+Code)
```
Terminate execution by raising `SystemExit`. `halt/0` exits with code 0; `halt/1` exits with the given code.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py` (inline in `compile_goal`/`compile_goal_trampoline`)
    **Python tests:** `tests/test_exceptions.py`

---

## Meta-Predicates

These are **compiler special forms** recognized by name in `compile_goal`/`compile_goal_trampoline`. Inner goals compile in simple mode as sub-generators.

### `FindAll/3`
```
FindAll(+Template, +Goal, -Bag)
```
Collect all bindings of `Template` produced by `Goal` into `Bag` (a list). Succeeds with `[]` if `Goal` has no solutions.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py:1623` (`_compile_find_all_core`)
    **Clausal tests:** `tests/fixtures/meta_test.clausal`
    **Python tests:** `tests/test_meta.py`

---

### `BagOf/3`
```
BagOf(+Template, +Goal, -Bag)
```
Like `FindAll/3` but fails if `Goal` has no solutions. Bag preserves duplicate solutions.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py:1630`
    **Clausal tests:** `tests/fixtures/meta_test.clausal`
    **Python tests:** `tests/test_meta.py`

---

### `SetOf/3`
```
SetOf(+Template, +Goal, -Set)
```
Like `BagOf/3` but removes duplicates and sorts the result.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py:1637`
    **Clausal tests:** `tests/fixtures/meta_test.clausal`
    **Python tests:** `tests/test_meta.py`

---

### `ForAll/2`
```
ForAll(+Cond, +Action)
```
Universal quantification: succeeds if `Action` succeeds for every solution of `Cond`. Desugars to `not(Cond and not(Action))`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/compiler.py:1644`
    **Clausal tests:** `tests/fixtures/meta_test.clausal`
    **Python tests:** `tests/test_meta.py`

---

## Higher-Order Call

### `Call/1..8`
```
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
```
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
```
phrase(+RuleBody, +List)
```
Invoke a DCG rule and require it to consume the entire input list. `RuleBody` is either a predicate class (0 extra args, e.g. `greeting`) or a partial term (N extra args, e.g. `digit(D)`). Equivalent to calling the rule with `List` as the input state and `[]` as the output state.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`_phrase__2`)
    **Python tests:** `tests/test_dcg.py`

---

### `phrase/3`
```
phrase(+RuleBody, +List, ?Rest)
```
Invoke a DCG rule for partial parsing. Like `phrase/2`, but the remaining unconsumed input is unified with `Rest` instead of requiring `[]`.

Also used for **state-passing DCGs**: encode state as a single-element list `[State]`, thread it through DCG nonterminals using `phrase(Rule, [InitialState], [FinalState])`. See [syntax.md](syntax.md#dcgs-as-general-state-passing) for the full pattern.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`_phrase__3`)
    **Python tests:** `tests/test_dcg.py`

---

## Term Inspection

### `Functor/3`
```
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
```
Arg(+N, +Term, -Arg)
```
Unify `Arg` with the `N`-th argument of `Term` (1-based indexing).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:394`
    **Clausal tests:** `tests/fixtures/builtins_inspect.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Unpack/2`
```
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
```
CopyTerm(+Original, -Copy)
```
Unify `Copy` with a deep copy of `Original` where every unbound `Var` is replaced by a fresh one. Structural sharing is preserved: if the same `Var` appears in multiple positions in `Original`, the same fresh `Var` appears in all corresponding positions of `Copy`. Already-bound variables are followed and their values are copied rather than replaced.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`_copy_term`, `CopyTerm/2`)
    **Clausal tests:** `tests/clausal_modules/term_inspection.clausal`
    **Python tests:** `tests/test_term_inspection.py`

---

### `TermVariables/2`
```
TermVariables(+Term, -Vars)
```
Unify `Vars` with a list of all unbound `Var`s in `Term`, collected left-to-right with duplicates removed (same `Var` appearing multiple times in `Term` appears only once in `Vars`). Bound variables are followed and not collected.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`_collect_vars`, `TermVariables/2`)
    **Clausal tests:** `tests/clausal_modules/term_inspection.clausal`
    **Python tests:** `tests/test_term_inspection.py`

---

### `NumberVars/3`
```
NumberVars(+Term, +Start, -End)
```
Number all unbound `Var`s in `Term` left-to-right, binding each to `Compound("$VAR", (N,))` where `N` starts at `Start` and increments. `End` is unified with the next unused number after all variables are numbered. Useful for pretty-printing terms with named variables. `Start` must be a bound integer.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`NumberVars/3`)
    **Clausal tests:** `tests/clausal_modules/term_inspection.clausal`
    **Python tests:** `tests/test_term_inspection.py`

---

## Runtime Database

These predicates require a live `Database` reference (`_DB_BUILTINS`). They recompile the affected predicate after modification.

### `Assert/1`
```
Assert(+Clause)
```
Add `Clause` (a fact or rule) at the **end** of its predicate's clause list. Fails on locked (non-dynamic) predicates. Ground compound facts are normalized to `Var+Is` form for output-mode queries.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:507`
    **Clausal tests:** `tests/fixtures/builtins_db.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `AssertFirst/1`
```
AssertFirst(+Clause)
```
Add `Clause` at the **front** of its predicate's clause list.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:545`
    **Clausal tests:** `tests/fixtures/builtins_db.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Retract/1`
```
Retract(+Term)
```
Remove the **first** clause whose head unifies with `Term`. Not backtrackable — removes exactly one clause per call. Fails on locked predicates.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:580`
    **Clausal tests:** `tests/fixtures/builtins_db.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `ClearTable/2`
```
ClearTable(+Functor, +Arity)
```
Remove all cached answers for the named tabled predicate, forcing re-computation on the next call.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:661`
    **Clausal tests:** none
    **Python tests:** `tests/test_tabling.py`

---

### `ClearAllTables/0`
```
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
```
Vary(+Overrides, +Term, -NewTerm)
```
Produce a copy of `Term` with field values replaced by `Overrides` (a Python `dict`). Works on functor dataclass instances and `KWTerm`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:692`
    **Clausal tests:** `tests/fixtures/builtins_keywords.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Extend/3`
```
Extend(+Additions, +Term, -NewTerm)
```
Produce a copy of `Term` (must be a `KWTerm`) with additional fields from `Additions` (a Python `dict`). Dataclass terms have fixed schemas so only `KWTerm` is supported.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:727`
    **Clausal tests:** `tests/fixtures/builtins_keywords.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `UnboundKeys/2`
```
UnboundKeys(+Term, -Keys)
```
Unify `Keys` with a list of field names whose values are unbound `Var`s in `Term`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:754`
    **Clausal tests:** `tests/fixtures/builtins_keywords.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Signature/3`
```
Signature(+FunctorName, +Arity, -Names)
```
Reflect the registered parameter name list for the predicate `FunctorName/Arity`. Fails if no signature is registered.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:778`
    **Clausal tests:** `tests/fixtures/builtins_keywords.clausal`
    **Python tests:** `tests/test_builtins.py`

---

## Constraint Predicates

### `Dif/2`
```
Dif(+X, +Y)
```
Disequality constraint. Succeeds if `X` and `Y` can remain different (posts a constraint if either is unbound). Implemented via attributed variables; propagates through unification.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:801` → `clausal/logic/constraints.py`
    **Clausal tests:** `tests/fixtures/builtins_dif.clausal`
    **Python tests:** `tests/test_dif.py`

---

### `Eq/3` (reified)
```
Eq(+X, +Y, -T)
```
Reified equality. `T` is unified with `True` if `X = Y`, `False` if `Dif(X, Y)`. Suspends if neither is determined yet.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:812` → `clausal/logic/reif.py`
    **Clausal tests:** `tests/fixtures/reif_eq_test.clausal`, `tests/fixtures/builtins_dif.clausal`
    **Python tests:** `tests/test_reif_builtins.py`

---

### `DifT/3` (reified)
```
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
```
InDomain(+VarOrList, +Lo, +Hi)
```
Post the finite domain `[Lo, Hi]` on a logic variable or a list of logic variables.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:829` → `clausal/logic/clpfd.py`
    **Clausal tests:** `tests/fixtures/clpfd_queens.clausal`, `tests/fixtures/clpfd_sendmore.clausal`
    **Python tests:** `tests/test_clpfd.py`

---

### `Label/1`
```
Label(+Vars)
```
Enumerate concrete values for a list of FD-constrained variables, backtracking over all consistent assignments.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:837` → `clausal/logic/clpfd.py`
    **Clausal tests:** `tests/fixtures/clpfd_queens.clausal`, `tests/fixtures/clpfd_sendmore.clausal`
    **Python tests:** `tests/test_clpfd.py`

---

### `AllDifferent/1`
```
AllDifferent(+Vars)
```
Post an all-different constraint on a list of FD variables. Propagates bounds and eliminates assigned values from other domains.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:844` → `clausal/logic/clpfd.py`
    **Clausal tests:** `tests/fixtures/clpfd_queens.clausal`, `tests/fixtures/clpfd_sendmore.clausal`
    **Python tests:** `tests/test_clpfd.py`

---

### `Equivalent/2`
```
Equivalent(+T1, +T2)
```
Structural equality test (old `==` behavior before CLP(FD) remapping). Succeeds if `T1` and `T2` are structurally identical after dereferencing.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:852` → `clausal/logic/clpfd.py`
    **Clausal tests:** none
    **Python tests:** `tests/test_clpfd.py`

---

## CLP(B) — Boolean Constraints

CLP(B) uses reduced ordered BDDs (Binary Decision Diagrams) for Boolean constraint solving. Expressions use Python's bitwise operators: `&` (AND), `|` (OR), `^` (XOR), `~` (NOT), plus `BoolEq` (equivalence) and `BoolImpl` (implication) term constructors.

### `Sat/1`
```
Sat(+Expr)
```
Post a Boolean constraint. The expression must evaluate to true. Fails if unsatisfiable. Propagates forced values (e.g., `Sat(X_ & Y_)` forces both to 1).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/constraints.py` → `clausal/logic/clpb.py`
    **Clausal tests:** `tests/fixtures/clpb_circuit.clausal`
    **Python tests:** `tests/test_clpb.py`

---

### `Taut/2`
```
Taut(+Expr, -T)
```
Tautology check. Unify `T` with 1 if `Expr` is always true, 0 if always false. Fail if indeterminate.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/constraints.py` → `clausal/logic/clpb.py`
    **Clausal tests:** none
    **Python tests:** `tests/test_clpb.py`

---

### `SatCount/2`
```
SatCount(+Expr, -N)
```
Count the number of satisfying assignments for `Expr`. Unify `N` with the count.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/constraints.py` → `clausal/logic/clpb.py`
    **Clausal tests:** none
    **Python tests:** `tests/test_clpb.py`

---

### `BoolLabeling/1`
```
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
```
IsVar(?X)
```
Succeeds if `X` is an unbound logic variable.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:863`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `IsBound/1`
```
IsBound(?X)
```
Succeeds if `X` is bound (not an unbound `Var`).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:870`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `IsStr/1`
```
IsStr(+X)
```
Succeeds if `X` is a Python `str` (the atom equivalent).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:877`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `IsNumber/1`
```
IsNumber(+X)
```
Succeeds if `X` is an `int` or `float` (excludes `bool`).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:885`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `IsInt/1`
```
IsInt(+X)
```
Succeeds if `X` is an `int` (excludes `bool`).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:897`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `IsFloat/1`
```
IsFloat(+X)
```
Succeeds if `X` is a Python `float`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:905`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `IsCompound/1`
```
IsCompound(+X)
```
Succeeds if `X` is a compound term with arity > 0 (`Compound`, `KWTerm`, or `PredicateMeta` instance with at least one field).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:921`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `IsCallable/1`
```
IsCallable(+X)
```
Succeeds if `X` is an atom (string) or a compound term.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:935`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `IsList/1`
```
IsList(+X)
```
Succeeds if `X` is a Python `list`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:947`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `IsGround/1`
```
IsGround(+X)
```
Succeeds if `X` contains no unbound `Var`s (is fully instantiated).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:954`
    **Clausal tests:** `tests/fixtures/builtins_types.clausal`
    **Python tests:** `tests/test_builtins.py`

---

## Dict and Set Predicates

Dict and set builtins operate on `DictTerm` and `SetTerm` values. Plain Python `dict` and `set` are not accepted. See [Dicts and Sets](dicts_sets.md) for the full design.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/dict_set.py`
    **Python tests:** `tests/test_dict_set_builtins.py` (79 tests)
    **Fixture:** `tests/fixtures/dict_set_builtins.clausal`

### `IsDict/1`
```
IsDict(+Term)
```
Succeeds if `Term` is a `DictTerm`.

---

### `DictSize/2`
```
DictSize(+Dict, -N)
```
`N` is the number of keys in `Dict`.

---

### `DictKeys/2`
```
DictKeys(+Dict, -Keys)
```
`Keys` is the sorted list of keys (sorted by `repr` for cross-type determinism).

---

### `DictValues/2`
```
DictValues(+Dict, -Values)
```
`Values` is the list of values in key-sorted order.

---

### `DictPairs/2`
```
DictPairs(?Dict, ?Pairs)
```
Bidirectional: `Dict` ↔ list of `[Key, Value]` 2-element lists. In dict→pairs direction, pairs are sorted by key.

---

### `DictGet/3`
```
DictGet(+Key, +Dict, ?Value)
```
Semidet lookup. Fails if `Key` is absent or unbound.

---

### `DictPut/4`
```
DictPut(+Key, +Value, +OldDict, -NewDict)
```
Functional update: `NewDict` is `OldDict` with `Key → Value` set. Returns a new `DictTerm`.

---

### `DictPutPairs/3`
```
DictPutPairs(+Pairs, +OldDict, -NewDict)
```
Bulk update from a `[[Key, Value], ...]` list. Equivalent to repeated `DictPut/4`.

---

### `DictRemove/3`
```
DictRemove(+Key, +OldDict, -NewDict)
```
`NewDict` is `OldDict` without `Key`. Fails if `Key` is absent.

---

### `DictMerge/3`
```
DictMerge(+D1, +D2, -Merged)
```
Union of `D1` and `D2`. Where keys conflict, `D2`'s value wins.

---

### `GenDict/3`
```
GenDict(?Key, +Dict, ?Value)
```
Nondeterministic enumeration. Yields one `Key`/`Value` binding per solution on backtracking. Can be filtered by binding `Key` before the call.

---

### `SubDict/2`
```
SubDict(+Pattern, +Dict)
```
Partial dict matching. Succeeds when every key in `Pattern` is present in `Dict` and the values unify. Extra keys in `Dict` are ignored. See [SubDict](dicts_sets.md#partial-dict-matching--subdict2) for examples.

---

### `IsSet/1`
```
IsSet(+Term)
```
Succeeds if `Term` is a `SetTerm`.

---

### `SetSize/2`
```
SetSize(+Set, -N)
```
`N` is the cardinality of `Set`.

---

### `SetList/2`
```
SetList(?Set, ?List)
```
Bidirectional: `Set` ↔ sorted list. In list→set direction, duplicates are removed.

---

### `SetUnion/3`
```
SetUnion(+S1, +S2, -Union)
```
Set union.

---

### `SetIntersection/3`
```
SetIntersection(+S1, +S2, -Inter)
```
Set intersection.

---

### `SetSubtract/3`
```
SetSubtract(+S1, +S2, -Diff)
```
`Diff` = elements in `S1` not in `S2`.

---

### `SetSymDiff/3`
```
SetSymDiff(+S1, +S2, -Sym)
```
Symmetric difference: elements in exactly one of `S1`, `S2`.

---

### `SetSubset/2`
```
SetSubset(+Sub, +Super)
```
Succeeds if `Sub` is a subset of `Super` (including equal sets and the empty set).

---

### `SetDisjoint/2`
```
SetDisjoint(+S1, +S2)
```
Succeeds if `S1` and `S2` share no elements.

---

### `SetAdd/3`
```
SetAdd(+Elem, +OldSet, -NewSet)
```
`NewSet` is `OldSet` with `Elem` added. No-op if already present.

---

### `SetRemove/3`
```
SetRemove(+Elem, +OldSet, -NewSet)
```
`NewSet` is `OldSet` with `Elem` removed. No-op if absent.

---

### `GenSet/2`
```
GenSet(?Elem, +Set)
```
Nondeterministic enumeration of set elements. Order is deterministic (sorted by `repr`).

---

## Arithmetic

Arithmetic **evaluation** uses `:=` (e.g., `Y_ := X_ * 2`). The predicates below provide relational arithmetic usable in both input and output modes.

### `Between/3`
```
Between(+Low, +High, ?X)
```
Check or enumerate integers in `[Low, High]` inclusive. In check mode (X bound) succeeds iff `Low ≤ X ≤ High`. In generate mode (X unbound) backtracks over each integer.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:964`
    **Clausal tests:** `tests/fixtures/builtins_arith.clausal`
    **Python tests:** `tests/test_builtins.py`, `tests/test_search.py`

---

### `Succ/2`
```
Succ(?X, ?Y)   % Y = X + 1
```
Bidirectional successor: if `X` is bound, `Y = X + 1`; if `Y` is bound, `X = Y - 1`. Both must be non-negative integers.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:987`
    **Clausal tests:** `tests/fixtures/builtins_arith.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Plus/3`
```
Plus(?X, ?Y, ?Z)   % Z = X + Y
```
Relational addition: any two of `X`, `Y`, `Z` determine the third.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1008`
    **Clausal tests:** `tests/fixtures/builtins_arith.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Abs/2`
```
Abs(+X, -Y)   % Y = abs(X)
```
Absolute value.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1035`
    **Clausal tests:** `tests/fixtures/builtins_arith.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Max/3`
```
Max(+X, +Y, -Z)   % Z = max(X, Y)
```
??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1049`
    **Clausal tests:** `tests/fixtures/builtins_arith.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Min/3`
```
Min(+X, +Y, -Z)   % Z = min(X, Y)
```
??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1062`
    **Clausal tests:** `tests/fixtures/builtins_arith.clausal`
    **Python tests:** `tests/test_builtins.py`

---

## List Predicates

### `In/2`
```
In(?Elem, +List)
```
Enumerate or check membership. Backtracks over all elements.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1078`
    **Clausal tests:** `tests/fixtures/meta_test.clausal`, `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`, `tests/test_search.py`

---

### `InCheck/2`
```
InCheck(+Elem, +List)
```
Deterministic membership check. Succeeds at most once; no backtracking.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1091`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Append/3`
```
Append(?L1, ?L2, ?L3)   % L3 = L1 ++ L2
```
List concatenation. Works in all modes: given any two, determines the third. Backtracks over splits when `L3` is bound and `L1`/`L2` are unbound.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1105`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`, `tests/test_search.py`

---

### `Length/2`
```
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
```
Last(+List, -Elem)
```
Unify `Elem` with the last element of `List`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1159`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`, `tests/test_search.py`

---

### `Reverse/2`
```
Reverse(+List, -Rev)
```
??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1170`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`, `tests/test_search.py`

---

### `GetItem/3`
```
GetItem(+N, +List, -Elem)   % 0-based
```
Get the element at 0-based index `N`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1181`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Flatten/2`
```
Flatten(+Nested, -Flat)
```
Recursively flatten a nested list structure.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1225`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `MergeSort/2`
```
MergeSort(+List, -Sorted)
```
Sort `List` preserving duplicate elements (stable sort).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1248`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Sort/2`
```
Sort(+List, -Sorted)
```
Sort `List` removing duplicate elements.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1265`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Permutation/2`
```
Permutation(+List, -Perm)
```
Enumerate all permutations of `List` via backtracking.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1286`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`, `tests/test_search.py`

---

### `Select/3`
```
Select(?Elem, +List, -Rest)
```
Select `Elem` from `List`, unifying `Rest` with the remaining elements. Backtracks over all positions where `Elem` appears.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1300`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Subtract/3`
```
Subtract(+Set1, +Set2, -Diff)
```
List difference: elements in `Set1` not in `Set2`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1314`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Intersection/3`
```
Intersection(+Set1, +Set2, -Inter)
```
Elements present in both `Set1` and `Set2`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1328`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Union/3`
```
Union(+Set1, +Set2, -Union)
```
Elements in `Set1` or `Set2`, with duplicates removed.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1342`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `ToSet/2`
```
ToSet(+List, -Set)
```
Remove duplicates from `List` preserving the first-occurrence order.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1359`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `SumList/2`
```
SumList(+List, -Sum)
```
Sum all numeric elements of `List`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1375`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `MaxList/2`
```
MaxList(+List, -Max)
```
Maximum element of a non-empty numeric list.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1391`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `MinList/2`
```
MinList(+List, -Min)
```
Minimum element of a non-empty numeric list.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1407`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `Take/3`
```
Take(+N, +List, -Taken)
```
First `N` elements of `List`. If `N > len(List)`, returns the whole list. If `N = 0`, returns `[]`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/lists.py` (`_take__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `Drop/3`
```
Drop(+N, +List, -Rest)
```
`List` after dropping the first `N` elements. If `N >= len(List)`, returns `[]`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/lists.py` (`_drop__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `SplitAt/4`
```
SplitAt(+N, +List, -Left, -Right)
```
Split `List` at index `N` into `Left` (first N elements) and `Right` (rest). Clamps to list bounds.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/lists.py` (`_split_at__4`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `Zip/3`
```
Zip(+List1, +List2, -Pairs)
```
Pair up elements from two lists into `[X, Y]` sublists. Truncates to the shorter list.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/lists.py` (`_zip__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `Replicate/3`
```
Replicate(+N, +Elem, -List)
```
`List` of `N` copies of `Elem`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/lists.py` (`_replicate__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `SplitWith/3`
```
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
```
Unzip(?Pairs, ?Keys, ?Values)
```
Relate a list of `[K, V]` pairs to separate `Keys` and `Values` lists. Works in both directions.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1426`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `PairKeys/2`
```
PairKeys(+Pairs, -Keys)
```
Extract the key (first element) from each pair.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1450`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

### `PairValues/2`
```
PairValues(+Pairs, -Values)
```
Extract the value (second element) from each pair.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1463`
    **Clausal tests:** `tests/fixtures/builtins_lists.clausal`
    **Python tests:** `tests/test_builtins.py`

---

## Higher-Order List Predicates

These predicates accept a **goal argument** (a lambda or named predicate). The goal is called for each list element; failures propagate as in standard higher-order patterns.

### `MapList/2`
```
MapList(+Goal, +List)
```
Verify that `Goal(Elem)` succeeds for every element of `List`. Fails if any element fails.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1541`
    **Clausal tests:** `tests/fixtures/builtins_higher_order.clausal`
    **Python tests:** `tests/test_higher_order.py`

---

### `MapList/3`
```
MapList(+Goal, +Xs, -Ys)
```
Map `Goal(X, Y)` over `Xs` to produce `Ys`. Takes the first solution of `Goal` per element.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1563`
    **Clausal tests:** `tests/fixtures/builtins_higher_order.clausal`
    **Python tests:** `tests/test_higher_order.py`

---

### `Filter/3`
```
Filter(+Goal, +List, -Included)
```
Filter `List` keeping only elements for which `Goal(Elem)` succeeds.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1589`
    **Clausal tests:** `tests/fixtures/builtins_higher_order.clausal`
    **Python tests:** `tests/test_higher_order.py`

---

### `Exclude/3`
```
Exclude(+Goal, +List, -Excluded)
```
Filter `List` keeping only elements for which `Goal(Elem)` **fails**.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1614`
    **Clausal tests:** `tests/fixtures/builtins_higher_order.clausal`
    **Python tests:** `tests/test_higher_order.py`

---

### `FoldLeft/4`
```
FoldLeft(+Goal, +List, +V0, -V)
```
Left fold. Calls `Goal(Elem, Acc0, Acc1)` for each element, threading the accumulator. `V0` is the initial value; `V` is the final result.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py:1639`
    **Clausal tests:** `tests/fixtures/builtins_higher_order.clausal`
    **Python tests:** `tests/test_higher_order.py`

---

### `TakeWhile/3`
```
TakeWhile(+Goal, +List, -Prefix)
```
Longest prefix of `List` where `Goal(Elem)` succeeds for each element.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_take_while__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `DropWhile/3`
```
DropWhile(+Goal, +List, -Suffix)
```
Suffix of `List` after dropping the longest prefix where `Goal(Elem)` succeeds.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_drop_while__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `Span/4`
```
Span(+Goal, +List, -Yes, -No)
```
`TakeWhile` + `DropWhile` in one pass. `Yes` is the longest prefix where `Goal` succeeds; `No` is the rest.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_span__4`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `GroupBy/3`
```
GroupBy(+Goal, +List, -Groups)
```
Group consecutive elements by key projected via `Goal(Elem, Key)`. Elements with equal consecutive keys are collected into sublists.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_group_by__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `SortBy/3`
```
SortBy(+Goal, +List, -Sorted)
```
Sort `List` by key projected via `Goal(Elem, Key)`. Stable sort (preserves order of equal keys).

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_sort_by__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `MaxBy/3`
```
MaxBy(+Goal, +List, -Max)
```
Element of `List` with the largest key projected via `Goal(Elem, Key)`. Fails on empty list.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_max_by__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `MinBy/3`
```
MinBy(+Goal, +List, -Min)
```
Element of `List` with the smallest key projected via `Goal(Elem, Key)`. Fails on empty list.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_min_by__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

### `FilterMap/3`
```
FilterMap(+Goal, +List, -Result)
```
Map + filter in one pass. Calls `Goal(Elem, Out)` for each element; keeps `Out` when the goal succeeds, skips the element when it fails.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins/higher_order.py` (`_filter_map__3`)
    **Clausal tests:** `tests/fixtures/list_util.clausal`
    **Python tests:** `tests/test_list_util.py`

---

## I/O

### `Write/1`
```
Write(+Term)
```
Print `Term` to stdout without a trailing newline. Strings are printed as-is; other values use `str()`. Logic variables are auto-dereferenced — bound vars print their value, unbound vars print `_N`. F-strings work naturally: `f"{X_}"` derefs `X_` at search time.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`Write/1`)
    **Python tests:** `tests/test_io.py`

---

### `Writeln/1`
```
Writeln(+Term)
```
Like `Write/1` but appends a newline.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`Writeln/1`)
    **Python tests:** `tests/test_io.py`

---

### `PrintTerm/1`
```
PrintTerm(+Term)
```
Print the structured `term_str` representation of `Term` (strings are quoted, compounds show functor/args) followed by a newline. Useful for debugging.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`PrintTerm/1`)
    **Python tests:** `tests/test_io.py`

---

### `Nl/0`
```
Nl
```
Print a newline to stdout. Equivalent to `Write("\n")`.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`Nl/0`)
    **Python tests:** `tests/test_io.py`

---

### `Tab/1`
```
Tab(+N)
```
Print `N` spaces to stdout. `N` must be a bound non-negative integer.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`Tab/1`)
    **Python tests:** `tests/test_io.py`

---

### `WriteToString/2`
```
WriteToString(+Term, -String)
```
Unify `String` with the `Write`-style string representation of `Term` (strings pass through, others use `str()`). Does not print anything.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`WriteToString/2`)
    **Python tests:** `tests/test_io.py`

---

### `TermToString/2`
```
TermToString(+Term, -String)
```
Unify `String` with the `term_str` representation of `Term` (structured, with quoted strings). Does not print anything.

??? info "Implementation & tests"
    **Implementation:** `clausal/logic/builtins.py` (`TermToString/2`)
    **Python tests:** `tests/test_io.py`

---

## Logging (`log` module)

Standard library module wrapping Python's `logging`. Import via `-import_from(log, [...])`. See [logging.md](logging.md) for full documentation.

All logging predicates always succeed (side-effect only). Messages below the logger's configured level are silently discarded.

### `GetLogger/1`, `GetLogger/2`
```
GetLogger(-Logger)
GetLogger(+Name, -Logger)
```
Unify `Logger` with a Python `logging.Logger` instance. Arity-1 returns the default `"clausal"` logger. Same name always returns same logger instance.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`
    **Python tests:** `tests/test_logging_module.py`

---

### `Debug/1`, `Debug/2`
```
Debug(+Msg)
Debug(+Logger, +Msg)
```
Log at DEBUG level. Arity-1 uses default `"clausal"` logger.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

### `Info/1`, `Info/2`
```
Info(+Msg)
Info(+Logger, +Msg)
```
Log at INFO level.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

### `Warning/1`, `Warning/2`
```
Warning(+Msg)
Warning(+Logger, +Msg)
```
Log at WARNING level.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

### `Error/1`, `Error/2`
```
Error(+Msg)
Error(+Logger, +Msg)
```
Log at ERROR level.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

### `Critical/1`, `Critical/2`
```
Critical(+Msg)
Critical(+Logger, +Msg)
```
Log at CRITICAL level.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

### `Log/3`
```
Log(+Logger, +Level, +Msg)
```
Log at an arbitrary level. `Level` is a string (`"debug"`, `"info"`, etc.) or integer.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

### `SetLevel/2`
```
SetLevel(+Logger, +Level)
```
Set the logger's effective level.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

### `GetLevel/2`
```
GetLevel(+Logger, -Level)
```
Unify `Level` with the logger's effective level name (e.g. `"DEBUG"`).

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

### `IsEnabledFor/2`
```
IsEnabledFor(+Logger, +Level)
```
Succeeds if the logger would process a message at `Level`; fails otherwise. The only logging predicate that can fail.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

### `StreamHandler/2`
```
StreamHandler(+StreamName, -Handler)
```
Create a `logging.StreamHandler`. `StreamName` is `"stdout"` or `"stderr"`.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

### `FileHandler/2`
```
FileHandler(+Path, -Handler)
```
Create a `logging.FileHandler` for the given path.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

### `SetFormatter/2`
```
SetFormatter(+Handler, +FormatString)
```
Set a `logging.Formatter` on the handler using Python format string syntax.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

### `AddHandler/2`
```
AddHandler(+Logger, +Handler)
```
Add a handler to the logger.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

### `RemoveHandler/2`
```
RemoveHandler(+Logger, +Handler)
```
Remove a handler from the logger.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

### `BasicConfig/1`
```
BasicConfig(+Opts)
```
Call `logging.basicConfig()` with a dict of options (level, format, datefmt, filename, filemode, stream).

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/log.py`

---

## Date & Time (`date_time` module)

Standard library module wrapping Python's `datetime`. Import via `-import_from(date_time, [Now, Today, Date, ...])`. All predicates produce and consume **real Python `datetime` objects** — `datetime.date`, `datetime.time`, `datetime.datetime`, `datetime.timedelta` — not custom term types. Unification uses Python's native `==`. Any `datetime` method can be called via `++()` interop (e.g. `S_ is ++D_.isoformat()`).

### `Now/1`
```
Now(-DT)
```
Unify `DT` with `datetime.datetime.now()` (naive, local time).

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/date_time.py`
    **Python tests:** `tests/test_date_time.py`

---

### `NowUTC/1`
```
NowUTC(-DT)
```
Unify `DT` with `datetime.datetime.now(datetime.timezone.utc)` (timezone-aware).

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/date_time.py`

---

### `Today/1`
```
Today(-D)
```
Unify `D` with `datetime.date.today()`.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/date_time.py`

---

### `Date/4`
```
Date(?Year, ?Month, ?Day, ?DateObj)
```
Bidirectional. If `DateObj` is unbound, constructs `datetime.date(Year, Month, Day)`. If `DateObj` is a `datetime.date` (or `datetime.datetime`), decomposes into `Year`, `Month`, `Day`. Fails on invalid dates (e.g. month 13, Feb 29 in non-leap year).

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/date_time.py`
    **Python tests:** `tests/test_date_time.py`

---

### `Time/4`
```
Time(?Hour, ?Minute, ?Second, ?TimeObj)
```
Bidirectional. If `TimeObj` is unbound, constructs `datetime.time(Hour, Minute, Second)`. If `TimeObj` is a `datetime.time`, decomposes into `Hour`, `Minute`, `Second`.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/date_time.py`

---

### `DateTime/7`
```
DateTime(?Year, ?Month, ?Day, ?Hour, ?Minute, ?Second, ?DtObj)
```
Bidirectional. If `DtObj` is unbound, constructs `datetime.datetime(Year, Month, Day, Hour, Minute, Second)`. If `DtObj` is a `datetime.datetime`, decomposes into all six components.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/date_time.py`

---

### `TimeDelta/3`
```
TimeDelta(?Days, ?Seconds, ?TdObj)
```
Bidirectional. If `TdObj` is unbound, constructs `datetime.timedelta(days=Days, seconds=Seconds)`. If `TdObj` is a `datetime.timedelta`, decomposes into `Days` and `Seconds`.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/date_time.py`

---

### `DateAdd/3`
```
DateAdd(+DateOrDatetime, +Timedelta, -Result)
```
`Result = DateOrDatetime + Timedelta`. Both inputs must be ground.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/date_time.py`

---

### `DateSub/3`
```
DateSub(+DateOrDatetime, +Timedelta, -Result)
```
`Result = DateOrDatetime - Timedelta`. Both inputs must be ground.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/date_time.py`

---

### `DateDiff/3`
```
DateDiff(+D1, +D2, -Timedelta)
```
`Timedelta = D1 - D2`. Both inputs must be `datetime.date` or `datetime.datetime`. Result is a `datetime.timedelta` (may be negative).

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/date_time.py`

---

### `FormatDate/3`
```
FormatDate(+DateOrDatetime, +FormatStr, -ResultStr)
```
`ResultStr = DateOrDatetime.strftime(FormatStr)`. Works with `datetime.date`, `datetime.time`, and `datetime.datetime`.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/date_time.py`

---

### `ParseDate/3`
```
ParseDate(+String, +FormatStr, -DatetimeObj)
```
`DatetimeObj = datetime.datetime.strptime(String, FormatStr)`. Fails if the string does not match the format.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/date_time.py`

---

### `DayOfWeek/2`
```
DayOfWeek(+DateOrDatetime, -Weekday)
```
`Weekday = DateOrDatetime.weekday()`. Monday = 0, Sunday = 6.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/date_time.py`

---

### `DateBetween/3`
```
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

```
Read(+YamlString, -Data)
```

Parse a YAML string into a Python object (dict/list/scalar). Fails on invalid YAML.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/yaml_module.py`

### `Write/2`

```
Write(+Data, -YamlString)
```

Serialize a Python object to a YAML string (block style, human-readable).

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/yaml_module.py`

### `ReadAll/2`

```
ReadAll(+YamlString, -DocList)
```

Parse a multi-document YAML string (with `---` separators) into a list of Python objects.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/yaml_module.py`

### `WriteAll/2`

```
WriteAll(+DocList, -YamlString)
```

Serialize a list of Python objects to a multi-document YAML string.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/yaml_module.py`

### `ReadFile/2`

```
ReadFile(+Path, -Data)
```

Read and parse a YAML file. Fails if the file does not exist or contains invalid YAML.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/yaml_module.py`

### `WriteFile/2`

```
WriteFile(+Path, +Data)
```

Write a Python object as YAML to a file.

??? info "Implementation & tests"
    **Implementation:** `clausal/modules/yaml_module.py`

### `Get/3`

```
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
| `X_ is Y_` | Unification (structural) | `compiler.py:1415` |
| `X_ is not Y_` | Disequality constraint (`Dif/2`) | `compiler.py:1436` |
| `X_ := Expr` | Arithmetic evaluation then unify | `compiler.py` (`Evaluate`) |
| `X_ == Y_` | CLP(FD) equality constraint | `compiler.py:1444` |
| `X_ != Y_` | CLP(FD) disequality constraint | `compiler.py:1451` |
| `X_ < Y_` | CLP(FD) less-than constraint | `compiler.py:1459` |
| `X_ <= Y_` | CLP(FD) less-or-equal constraint | `compiler.py:1466` |
| `X_ > Y_` | CLP(FD) greater-than constraint | `compiler.py:1473` |
| `X_ >= Y_` | CLP(FD) greater-or-equal constraint | `compiler.py:1480` |
| `X_ in Coll` | For-loop over collection | `compiler.py:1570` |
| `X_ not in Coll` | Negated membership check | `compiler.py:1594` |
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
    | `tests/test_python_interop.py` | `++()` Python interop (13 tests) |
    | `tests/test_dcg.py` | DCG rules, `phrase/2`, `phrase/3` (26 tests) |
    | `tests/fixtures/dcg_grammar.clausal` | `phrase/2`, `phrase/3`, DCG with non-terminals, inline goals, pushback, negation |
    | `tests/fixtures/clpb_circuit.clausal` | `Sat/1`, `BoolLabeling/1`, `BoolEq` — HalfAdder, FullAdder, PigeonHole |
    | `tests/fixtures/logging_basic.clausal` | `GetLogger`, `SetLevel`, `GetLevel`, `IsEnabledFor`, `Debug`, `Info`, `Warning`, `Error`, `Critical`, `Log`, `StreamHandler`, `SetFormatter`, `AddHandler`, `RemoveHandler` |
    | `tests/test_date_time.py` | `Now`, `NowUTC`, `Today`, `Date`, `Time`, `DateTime`, `TimeDelta`, `DateAdd`, `DateSub`, `DateDiff`, `FormatDate`, `ParseDate`, `DayOfWeek`, `DateBetween` (64 tests) |
    | `tests/test_yaml_module.py` | `Read`, `Write`, `ReadAll`, `WriteAll`, `ReadFile`, `WriteFile`, `Get` (45 tests) |
    | `tests/fixtures/yaml_basic.clausal` | `Read`, `Write`, `Get` — parsing, nested access, round-trip |
