# Clausal Predicate Index

Complete index of all built-in and standard-library predicates. Predicates are listed as `Name/arity`.

Notation in signature lines:
- `+` = must be bound (input)
- `-` = output (unified with result)
- `?` = either input or output

---

## Control Flow

These are **compiler special forms** — transformed at compile time, not dispatched via the builtin registry.

### `Once/1`
```
Once(+Goal)
```
Commit to the first solution of `Goal`; succeeds at most once even if `Goal` has multiple solutions.

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

**Implementation:** `clausal/logic/compiler.py:1507`
**Clausal tests:** `tests/fixtures/wfs_win.clausal`, `tests/fixtures/wfs_win_asym.clausal`
**Python tests:** `tests/test_compiled_programs.py`, `tests/test_wfs.py`

---

### `If/3` (If-Then-Else)
```
If(+Cond, +Then, +Else)
```
If `Cond` has a solution, run `Then`; otherwise run `Else`. Soft-cut: only the first solution of `Cond` is tried. Compiles to a reified if-then-else that propagates constraints in both branches.

**Implementation:** `clausal/logic/compiler.py` (`_compile_ite_trampoline`)
**Clausal tests:** `tests/fixtures/reified_memberd.clausal`, `tests/fixtures/tabled_ite.clausal`, `tests/fixtures/reified_max.clausal`
**Python tests:** `tests/test_reified_ite.py`

---

## Meta-Predicates

These are **compiler special forms** recognized by name in `compile_goal`/`compile_goal_trampoline`. Inner goals compile in simple mode as sub-generators.

### `FindAll/3`
```
FindAll(+Template, +Goal, -Bag)
```
Collect all bindings of `Template` produced by `Goal` into `Bag` (a list). Succeeds with `[]` if `Goal` has no solutions.

**Implementation:** `clausal/logic/compiler.py:1623` (`_compile_find_all_core`)
**Clausal tests:** `tests/fixtures/meta_test.clausal`
**Python tests:** `tests/test_meta.py`

---

### `BagOf/3`
```
BagOf(+Template, +Goal, -Bag)
```
Like `FindAll/3` but fails if `Goal` has no solutions. Bag preserves duplicate solutions.

**Implementation:** `clausal/logic/compiler.py:1630`
**Clausal tests:** `tests/fixtures/meta_test.clausal`
**Python tests:** `tests/test_meta.py`

---

### `SetOf/3`
```
SetOf(+Template, +Goal, -Set)
```
Like `BagOf/3` but removes duplicates and sorts the result.

**Implementation:** `clausal/logic/compiler.py:1637`
**Clausal tests:** `tests/fixtures/meta_test.clausal`
**Python tests:** `tests/test_meta.py`

---

### `ForAll/2`
```
ForAll(+Cond, +Action)
```
Universal quantification: succeeds if `Action` succeeds for every solution of `Cond`. Desugars to `not(Cond and not(Action))`.

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

**Implementation:** `clausal/logic/builtins.py:1479`
**Clausal tests:** `tests/fixtures/builtins_call.clausal`
**Python tests:** `tests/test_meta.py`, `tests/test_higher_order.py`

---

## Term Inspection

### `Functor/3`
```
Functor(+Term, -Name, -Arity)   % decompose
Functor(-Term, +Name, +Arity)   % construct
```
Decompose a term into its functor name and arity, or construct a term from a name and arity (fields are fresh vars).

**Implementation:** `clausal/logic/builtins.py:353`
**Clausal tests:** `tests/fixtures/builtins_inspect.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `Arg/3`
```
Arg(+N, +Term, -Arg)
```
Unify `Arg` with the `N`-th argument of `Term` (1-based indexing).

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

**Implementation:** `clausal/logic/builtins.py:413`
**Clausal tests:** `tests/fixtures/builtins_inspect.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `CopyTerm/2`
```
CopyTerm(+Original, -Copy)
```
Unify `Copy` with a deep copy of `Original` where every unbound `Var` is replaced by a fresh one. Structural sharing is preserved: if the same `Var` appears in multiple positions in `Original`, the same fresh `Var` appears in all corresponding positions of `Copy`. Already-bound variables are followed and their values are copied rather than replaced.

**Implementation:** `clausal/logic/builtins.py` (`_copy_term`, `CopyTerm/2`)
**Clausal tests:** `tests/clausal_modules/term_inspection.clausal`
**Python tests:** `tests/test_term_inspection.py`

---

### `TermVariables/2`
```
TermVariables(+Term, -Vars)
```
Unify `Vars` with a list of all unbound `Var`s in `Term`, collected left-to-right with duplicates removed (same `Var` appearing multiple times in `Term` appears only once in `Vars`). Bound variables are followed and not collected.

**Implementation:** `clausal/logic/builtins.py` (`_collect_vars`, `TermVariables/2`)
**Clausal tests:** `tests/clausal_modules/term_inspection.clausal`
**Python tests:** `tests/test_term_inspection.py`

---

### `NumberVars/3`
```
NumberVars(+Term, +Start, -End)
```
Number all unbound `Var`s in `Term` left-to-right, binding each to `Compound("$VAR", (N,))` where `N` starts at `Start` and increments. `End` is unified with the next unused number after all variables are numbered. Useful for pretty-printing terms with named variables. `Start` must be a bound integer.

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

**Implementation:** `clausal/logic/builtins.py:507`
**Clausal tests:** `tests/fixtures/builtins_db.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `AssertFirst/1`
```
AssertFirst(+Clause)
```
Add `Clause` at the **front** of its predicate's clause list.

**Implementation:** `clausal/logic/builtins.py:545`
**Clausal tests:** `tests/fixtures/builtins_db.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `Retract/1`
```
Retract(+Term)
```
Remove the **first** clause whose head unifies with `Term`. Not backtrackable — removes exactly one clause per call. Fails on locked predicates.

**Implementation:** `clausal/logic/builtins.py:580`
**Clausal tests:** `tests/fixtures/builtins_db.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `ClearTable/2`
```
ClearTable(+Functor, +Arity)
```
Remove all cached answers for the named tabled predicate, forcing re-computation on the next call.

**Implementation:** `clausal/logic/builtins.py:661`
**Clausal tests:** none
**Python tests:** `tests/test_tabling.py`

---

### `ClearAllTables/0`
```
ClearAllTables
```
Remove all cached tabling answers for every predicate in the current database.

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

**Implementation:** `clausal/logic/builtins.py:692`
**Clausal tests:** `tests/fixtures/builtins_keywords.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `Extend/3`
```
Extend(+Additions, +Term, -NewTerm)
```
Produce a copy of `Term` (must be a `KWTerm`) with additional fields from `Additions` (a Python `dict`). Dataclass terms have fixed schemas so only `KWTerm` is supported.

**Implementation:** `clausal/logic/builtins.py:727`
**Clausal tests:** `tests/fixtures/builtins_keywords.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `UnboundKeys/2`
```
UnboundKeys(+Term, -Keys)
```
Unify `Keys` with a list of field names whose values are unbound `Var`s in `Term`.

**Implementation:** `clausal/logic/builtins.py:754`
**Clausal tests:** `tests/fixtures/builtins_keywords.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `Signature/3`
```
Signature(+FunctorName, +Arity, -Names)
```
Reflect the registered parameter name list for the predicate `FunctorName/Arity`. Fails if no signature is registered.

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

**Implementation:** `clausal/logic/builtins.py:801` → `clausal/logic/constraints.py`
**Clausal tests:** `tests/fixtures/builtins_dif.clausal`
**Python tests:** `tests/test_dif.py`

---

### `Eq/3` (reified)
```
Eq(+X, +Y, -T)
```
Reified equality. `T` is unified with `True` if `X = Y`, `False` if `Dif(X, Y)`. Suspends if neither is determined yet.

**Implementation:** `clausal/logic/builtins.py:812` → `clausal/logic/reif.py`
**Clausal tests:** `tests/fixtures/reif_eq_test.clausal`, `tests/fixtures/builtins_dif.clausal`
**Python tests:** `tests/test_reif_builtins.py`

---

### `DifT/3` (reified)
```
DifT(+X, +Y, -T)
```
Reified disequality. `T` is `True` if `Dif(X, Y)`, `False` if `X = Y`.

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

**Implementation:** `clausal/logic/builtins.py:829` → `clausal/logic/clpfd.py`
**Clausal tests:** `tests/fixtures/clpfd_queens.clausal`, `tests/fixtures/clpfd_sendmore.clausal`
**Python tests:** `tests/test_clpfd.py`

---

### `Label/1`
```
Label(+Vars)
```
Enumerate concrete values for a list of FD-constrained variables, backtracking over all consistent assignments.

**Implementation:** `clausal/logic/builtins.py:837` → `clausal/logic/clpfd.py`
**Clausal tests:** `tests/fixtures/clpfd_queens.clausal`, `tests/fixtures/clpfd_sendmore.clausal`
**Python tests:** `tests/test_clpfd.py`

---

### `AllDifferent/1`
```
AllDifferent(+Vars)
```
Post an all-different constraint on a list of FD variables. Propagates bounds and eliminates assigned values from other domains.

**Implementation:** `clausal/logic/builtins.py:844` → `clausal/logic/clpfd.py`
**Clausal tests:** `tests/fixtures/clpfd_queens.clausal`, `tests/fixtures/clpfd_sendmore.clausal`
**Python tests:** `tests/test_clpfd.py`

---

### `Equivalent/2`
```
Equivalent(+T1, +T2)
```
Structural equality test (old `==` behavior before CLP(FD) remapping). Succeeds if `T1` and `T2` are structurally identical after dereferencing.

**Implementation:** `clausal/logic/builtins.py:852` → `clausal/logic/clpfd.py`
**Clausal tests:** none
**Python tests:** `tests/test_clpfd.py`

---

## Type Checks

### `IsVar/1`
```
IsVar(?X)
```
Succeeds if `X` is an unbound logic variable.

**Implementation:** `clausal/logic/builtins.py:863`
**Clausal tests:** `tests/fixtures/builtins_types.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `IsBound/1`
```
IsBound(?X)
```
Succeeds if `X` is bound (not an unbound `Var`).

**Implementation:** `clausal/logic/builtins.py:870`
**Clausal tests:** `tests/fixtures/builtins_types.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `IsStr/1`
```
IsStr(+X)
```
Succeeds if `X` is a Python `str` (the atom equivalent).

**Implementation:** `clausal/logic/builtins.py:877`
**Clausal tests:** `tests/fixtures/builtins_types.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `IsNumber/1`
```
IsNumber(+X)
```
Succeeds if `X` is an `int` or `float` (excludes `bool`).

**Implementation:** `clausal/logic/builtins.py:885`
**Clausal tests:** `tests/fixtures/builtins_types.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `IsInt/1`
```
IsInt(+X)
```
Succeeds if `X` is an `int` (excludes `bool`).

**Implementation:** `clausal/logic/builtins.py:897`
**Clausal tests:** `tests/fixtures/builtins_types.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `IsFloat/1`
```
IsFloat(+X)
```
Succeeds if `X` is a Python `float`.

**Implementation:** `clausal/logic/builtins.py:905`
**Clausal tests:** `tests/fixtures/builtins_types.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `IsCompound/1`
```
IsCompound(+X)
```
Succeeds if `X` is a compound term with arity > 0 (`Compound`, `KWTerm`, or `PredicateMeta` instance with at least one field).

**Implementation:** `clausal/logic/builtins.py:921`
**Clausal tests:** `tests/fixtures/builtins_types.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `IsCallable/1`
```
IsCallable(+X)
```
Succeeds if `X` is an atom (string) or a compound term.

**Implementation:** `clausal/logic/builtins.py:935`
**Clausal tests:** `tests/fixtures/builtins_types.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `IsList/1`
```
IsList(+X)
```
Succeeds if `X` is a Python `list`.

**Implementation:** `clausal/logic/builtins.py:947`
**Clausal tests:** `tests/fixtures/builtins_types.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `IsGround/1`
```
IsGround(+X)
```
Succeeds if `X` contains no unbound `Var`s (is fully instantiated).

**Implementation:** `clausal/logic/builtins.py:954`
**Clausal tests:** `tests/fixtures/builtins_types.clausal`
**Python tests:** `tests/test_builtins.py`

---

## Arithmetic

Arithmetic **evaluation** uses `:=` (e.g., `Y_ := X_ * 2`). The predicates below provide relational arithmetic usable in both input and output modes.

### `Between/3`
```
Between(+Low, +High, ?X)
```
Check or enumerate integers in `[Low, High]` inclusive. In check mode (X bound) succeeds iff `Low ≤ X ≤ High`. In generate mode (X unbound) backtracks over each integer.

**Implementation:** `clausal/logic/builtins.py:964`
**Clausal tests:** `tests/fixtures/builtins_arith.clausal`
**Python tests:** `tests/test_builtins.py`, `tests/test_search.py`

---

### `Succ/2`
```
Succ(?X, ?Y)   % Y = X + 1
```
Bidirectional successor: if `X` is bound, `Y = X + 1`; if `Y` is bound, `X = Y - 1`. Both must be non-negative integers.

**Implementation:** `clausal/logic/builtins.py:987`
**Clausal tests:** `tests/fixtures/builtins_arith.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `Plus/3`
```
Plus(?X, ?Y, ?Z)   % Z = X + Y
```
Relational addition: any two of `X`, `Y`, `Z` determine the third.

**Implementation:** `clausal/logic/builtins.py:1008`
**Clausal tests:** `tests/fixtures/builtins_arith.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `Abs/2`
```
Abs(+X, -Y)   % Y = abs(X)
```
Absolute value.

**Implementation:** `clausal/logic/builtins.py:1035`
**Clausal tests:** `tests/fixtures/builtins_arith.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `Max/3`
```
Max(+X, +Y, -Z)   % Z = max(X, Y)
```
**Implementation:** `clausal/logic/builtins.py:1049`
**Clausal tests:** `tests/fixtures/builtins_arith.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `Min/3`
```
Min(+X, +Y, -Z)   % Z = min(X, Y)
```
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

**Implementation:** `clausal/logic/builtins.py:1078`
**Clausal tests:** `tests/fixtures/meta_test.clausal`, `tests/fixtures/builtins_lists.clausal`
**Python tests:** `tests/test_builtins.py`, `tests/test_search.py`

---

### `InCheck/2`
```
InCheck(+Elem, +List)
```
Deterministic membership check. Succeeds at most once; no backtracking.

**Implementation:** `clausal/logic/builtins.py:1091`
**Clausal tests:** `tests/fixtures/builtins_lists.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `Append/3`
```
Append(?L1, ?L2, ?L3)   % L3 = L1 ++ L2
```
List concatenation. Works in all modes: given any two, determines the third. Backtracks over splits when `L3` is bound and `L1`/`L2` are unbound.

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

**Implementation:** `clausal/logic/builtins.py:1141`
**Clausal tests:** `tests/fixtures/builtins_lists.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `Last/2`
```
Last(+List, -Elem)
```
Unify `Elem` with the last element of `List`.

**Implementation:** `clausal/logic/builtins.py:1159`
**Clausal tests:** `tests/fixtures/builtins_lists.clausal`
**Python tests:** `tests/test_builtins.py`, `tests/test_search.py`

---

### `Reverse/2`
```
Reverse(+List, -Rev)
```
**Implementation:** `clausal/logic/builtins.py:1170`
**Clausal tests:** `tests/fixtures/builtins_lists.clausal`
**Python tests:** `tests/test_builtins.py`, `tests/test_search.py`

---

### `GetItem/3`
```
GetItem(+N, +List, -Elem)   % 0-based
```
Get the element at 0-based index `N`.

**Implementation:** `clausal/logic/builtins.py:1181`
**Clausal tests:** `tests/fixtures/builtins_lists.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `Flatten/2`
```
Flatten(+Nested, -Flat)
```
Recursively flatten a nested list structure.

**Implementation:** `clausal/logic/builtins.py:1225`
**Clausal tests:** `tests/fixtures/builtins_lists.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `MergeSort/2`
```
MergeSort(+List, -Sorted)
```
Sort `List` preserving duplicate elements (stable sort).

**Implementation:** `clausal/logic/builtins.py:1248`
**Clausal tests:** `tests/fixtures/builtins_lists.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `Sort/2`
```
Sort(+List, -Sorted)
```
Sort `List` removing duplicate elements.

**Implementation:** `clausal/logic/builtins.py:1265`
**Clausal tests:** `tests/fixtures/builtins_lists.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `Permutation/2`
```
Permutation(+List, -Perm)
```
Enumerate all permutations of `List` via backtracking.

**Implementation:** `clausal/logic/builtins.py:1286`
**Clausal tests:** `tests/fixtures/builtins_lists.clausal`
**Python tests:** `tests/test_builtins.py`, `tests/test_search.py`

---

### `Select/3`
```
Select(?Elem, +List, -Rest)
```
Select `Elem` from `List`, unifying `Rest` with the remaining elements. Backtracks over all positions where `Elem` appears.

**Implementation:** `clausal/logic/builtins.py:1300`
**Clausal tests:** `tests/fixtures/builtins_lists.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `Subtract/3`
```
Subtract(+Set1, +Set2, -Diff)
```
List difference: elements in `Set1` not in `Set2`.

**Implementation:** `clausal/logic/builtins.py:1314`
**Clausal tests:** `tests/fixtures/builtins_lists.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `Intersection/3`
```
Intersection(+Set1, +Set2, -Inter)
```
Elements present in both `Set1` and `Set2`.

**Implementation:** `clausal/logic/builtins.py:1328`
**Clausal tests:** `tests/fixtures/builtins_lists.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `Union/3`
```
Union(+Set1, +Set2, -Union)
```
Elements in `Set1` or `Set2`, with duplicates removed.

**Implementation:** `clausal/logic/builtins.py:1342`
**Clausal tests:** `tests/fixtures/builtins_lists.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `ToSet/2`
```
ToSet(+List, -Set)
```
Remove duplicates from `List` preserving the first-occurrence order.

**Implementation:** `clausal/logic/builtins.py:1359`
**Clausal tests:** `tests/fixtures/builtins_lists.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `SumList/2`
```
SumList(+List, -Sum)
```
Sum all numeric elements of `List`.

**Implementation:** `clausal/logic/builtins.py:1375`
**Clausal tests:** `tests/fixtures/builtins_lists.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `MaxList/2`
```
MaxList(+List, -Max)
```
Maximum element of a non-empty numeric list.

**Implementation:** `clausal/logic/builtins.py:1391`
**Clausal tests:** `tests/fixtures/builtins_lists.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `MinList/2`
```
MinList(+List, -Min)
```
Minimum element of a non-empty numeric list.

**Implementation:** `clausal/logic/builtins.py:1407`
**Clausal tests:** `tests/fixtures/builtins_lists.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `Unzip/3`
```
Unzip(?Pairs, ?Keys, ?Values)
```
Relate a list of `[K, V]` pairs to separate `Keys` and `Values` lists. Works in both directions.

**Implementation:** `clausal/logic/builtins.py:1426`
**Clausal tests:** `tests/fixtures/builtins_lists.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `PairKeys/2`
```
PairKeys(+Pairs, -Keys)
```
Extract the key (first element) from each pair.

**Implementation:** `clausal/logic/builtins.py:1450`
**Clausal tests:** `tests/fixtures/builtins_lists.clausal`
**Python tests:** `tests/test_builtins.py`

---

### `PairValues/2`
```
PairValues(+Pairs, -Values)
```
Extract the value (second element) from each pair.

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

**Implementation:** `clausal/logic/builtins.py:1541`
**Clausal tests:** `tests/fixtures/builtins_higher_order.clausal`
**Python tests:** `tests/test_higher_order.py`

---

### `MapList/3`
```
MapList(+Goal, +Xs, -Ys)
```
Map `Goal(X, Y)` over `Xs` to produce `Ys`. Takes the first solution of `Goal` per element.

**Implementation:** `clausal/logic/builtins.py:1563`
**Clausal tests:** `tests/fixtures/builtins_higher_order.clausal`
**Python tests:** `tests/test_higher_order.py`

---

### `Filter/3`
```
Filter(+Goal, +List, -Included)
```
Filter `List` keeping only elements for which `Goal(Elem)` succeeds.

**Implementation:** `clausal/logic/builtins.py:1589`
**Clausal tests:** `tests/fixtures/builtins_higher_order.clausal`
**Python tests:** `tests/test_higher_order.py`

---

### `Exclude/3`
```
Exclude(+Goal, +List, -Excluded)
```
Filter `List` keeping only elements for which `Goal(Elem)` **fails**.

**Implementation:** `clausal/logic/builtins.py:1614`
**Clausal tests:** `tests/fixtures/builtins_higher_order.clausal`
**Python tests:** `tests/test_higher_order.py`

---

### `FoldLeft/4`
```
FoldLeft(+Goal, +List, +V0, -V)
```
Left fold. Calls `Goal(Elem, Acc0, Acc1)` for each element, threading the accumulator. `V0` is the initial value; `V` is the final result.

**Implementation:** `clausal/logic/builtins.py:1639`
**Clausal tests:** `tests/fixtures/builtins_higher_order.clausal`
**Python tests:** `tests/test_higher_order.py`

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

## Test Fixtures Summary

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
| `tests/fixtures/builtins_keywords.clausal` | `Vary/3`, `Extend/3`, `UnboundKeys/2`, `Signature/3` |
| `tests/fixtures/builtins_dif.clausal` | `Dif/2`, `Eq/3`, `DifT/3` |
| `tests/fixtures/builtins_call.clausal` | `Call/N`, `CallGoal/N` |
