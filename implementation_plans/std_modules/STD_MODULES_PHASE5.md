# Std Modules Phase 5 — extend Existing Builtins (Gap-Filling)

**Status: COMPLETE**

**Depends on:** V2-6 (CLP(FD)), V2-8 (Reified ITE), V2-12 (Arithmetic), V2-17
(DCGs), Phase 4 (Sleep/1 already in py.process)

**Goal:** Fill the remaining gaps in Clausal's existing builtin modules by
adding predicates that Scryer Prolog's standard library provides. Each
addition is small and self-contained — this phase is not a new module design
but rather 25 additions across 9 existing areas.

**Non-goal:** Redesigning any existing module. These are additive changes only.

---

## Design Principles

1. **Same registration pattern as existing builtins.** Simple-mode predicates
   use `@_builtin`. Trampoline-mode predicates use `@_trampoline_builtin`.
   CLP(FD) additions are core constraint functions in `clpfd.py` with thin
   builtin wrappers in `builtins/constraints.py`.

2. **Leverage Python stdlib.** `math.lcm`, `pow(a, b, m)`, `int.bit_count()`,
   `int.bit_length()` — Python already has the number-theoretic primitives.

3. **Relational where possible.** `numlist/3` with unbound N generates
   lazily. `same_length/2` with both unbound generates pairs of lists.
   `group_pairs_by_key/2` collects into a DictTerm.

4. **Clausal naming conventions.** TitleCase predicates, expanded names.

---

## 5a — Arithmetic Additions

**File:** `clausal/logic/builtins/arithmetic.py` (extend existing)

**Test file:** `tests/test_arithmetic.py` (extend existing)

### Predicates (5 new)

| Predicate | Description |
|---|---|
| `lcm/3` | `lcm(X, Y, L)` — L is the least common multiple of X and Y. Both X and Y must be ground integers. |
| `exp_mod/4` | `exp_mod(Base, Exp, Mod, Result)` — Result is Base^Exp mod Mod. Uses Python's `pow(base, exp, mod)` for efficiency. |
| `popcount/2` | `popcount(X, Count)` — Count is the number of set bits in X (non-negative integer). Uses `int.bit_count()`. |
| `msb/2` | `msb(X, Bit)` — Bit is the position of the most significant set bit (0-indexed). X must be a positive integer. Uses `int.bit_length() - 1`. |
| `lsb/2` | `lsb(X, Bit)` — Bit is the position of the least significant set bit (0-indexed). X must be a positive integer. Uses `(X & -X).bit_length() - 1`. |

### Implementation notes

- `lcm/3`: `math.lcm(x, y)` (Python 3.9+). For older Python: `abs(x * y) // math.gcd(x, y)`.
- `exp_mod/4`: `pow(base, exp, mod)` — Python's built-in modular exponentiation.
- `popcount/2`: `x.bit_count()` (Python 3.10+). Fallback: `bin(x).count('1')`.
- `msb/2`: `x.bit_length() - 1`. Fail on x <= 0.
- `lsb/2`: `(x & -x).bit_length() - 1`. Fail on x <= 0.
- All are simple `@_builtin` predicates, same pattern as `gcd/3`.

### Test plan (~15 tests)

- `lcm(4, 6, L)` → L = 12. `lcm(0, 5, L)` → L = 0. Unbound args fail.
- `exp_mod(2, 10, 1000, R)` → R = 24. `exp_mod(3, 0, 7, R)` → R = 1. Mod = 0 fails.
- `popcount(0, C)` → C = 0. `popcount(255, C)` → C = 8. Negative fails.
- `msb(1, B)` → B = 0. `msb(8, B)` → B = 3. Zero/negative fails.
- `lsb(12, B)` → B = 2. `lsb(1, B)` → B = 0. Zero/negative fails.

---

## 5b — List Additions

**File:** `clausal/logic/builtins/lists.py` (extend existing)

**Test file:** `tests/test_builtins.py` or `tests/test_lists_extended.py` (new)

### Predicates (4 new, counting multi-arity)

| Predicate | Description |
|---|---|
| `numlist/3` | `numlist(Low, High, List)` — List is the list of integers from Low to High inclusive. Both Low and High must be ground. |
| `numlist/2` | `numlist(High, List)` — shorthand for `numlist(1, High, List)`. |
| `same_length/2` | `same_length(L1, L2)` — succeeds if L1 and L2 have the same length. If one is ground and the other is unbound, generates a list of fresh variables. |
| `transpose/2` | `transpose(Matrix, Transposed)` — Matrix is a list of lists (rows). Transposed is the column-wise transposition. |

### Implementation notes

- `numlist/3`: `list(range(low, high + 1))`, unify with List. Fail if
  Low > High (empty numlist is debatable — follow SWI: fail on Low > High).
- `numlist/2`: delegate to `numlist/3` with Low=1.
- `same_length/2`: Both ground → check `len(l1) == len(l2)`. One unbound →
  generate list of `Var()` with matching length. Both unbound → generate
  pairs of increasing length (limit to reasonable bound or just fail).
- `transpose/2`: `list(map(list, zip(*matrix)))`. Fail if not rectangular
  or not a list of lists. Uses trampoline mode since it's in `lists.py`.

### Test plan (~15 tests)

- `numlist(1, 5, L)` → L = [1, 2, 3, 4, 5].
- `numlist(3, 3, L)` → L = [3].
- `numlist(5, 3, L)` → fails.
- `numlist(5, L)` → L = [1, 2, 3, 4, 5].
- `same_length([1,2,3], [a,b,c])` → succeeds.
- `same_length([1,2], [a,b,c])` → fails.
- `same_length([1,2,3], L)` where L unbound → L is list of 3 vars.
- `transpose([[1,2],[3,4]], T)` → T = [[1,3],[2,4]].
- `transpose([[1,2,3],[4,5,6]], T)` → T = [[1,4],[2,5],[3,6]].
- `transpose([], T)` → T = [].
- Non-rectangular matrix → fails.

---

## 5c — CLP(FD) Global Constraints

**File:** `clausal/logic/clpfd.py` (extend existing, core constraint logic),
`clausal/logic/builtins/constraints.py` (extend existing, thin wrappers)

**Test file:** `tests/test_clpfd.py` (extend existing)

### Predicates (4 new)

| Predicate | Description |
|---|---|
| `sum_/3` | `sum_(Vars, Op, Value)` — constrain the sum of Vars list under comparison Op (#=, #<, #>, #=<, #>=, #\=) to Value. E.g. `sum_([X, Y, Z], #=, 10)`. |
| `scalar_product/4` | `scalar_product(Coeffs, Vars, Op, Value)` — weighted sum: Σ(Coeffs[i]·Vars[i]) Op Value. |
| `element/3` | `element(Index, List, Value)` — Value is the Index-th element of List (1-based). Index can be an FDVar constrained to valid range. Propagates domain narrowing bidirectionally. |
| `circuit/1` | `circuit(Vars)` — Vars form a single Hamiltonian circuit. Vars[i] = j means successor of node i is node j. Classic assignment constraint. |

### Implementation notes

- **sum_/3**: Implemented with bounds-consistency propagation (`SumConstraint`).
  Computes `min_sum`/`max_sum` from variable domains, narrows Value's domain
  and each variable's domain based on slack. Queue-based fixpoint loop.

- **scalar_product/4**: Same as sum_ but each variable's contribution is
  multiplied by its coefficient. `Σ coeff[i] * var[i] Op value`.

- **element/3**: Implemented with AC3-style arc-consistency (`ElementConstraint`).
  Domain of Index narrowed to indices whose List element is in Value's domain;
  domain of Value narrowed to `{List[i] : i ∈ domain(Index)}`. Propagates
  bidirectionally on each narrowing event.

- **circuit/1**: Implemented with `CircuitConstraint` combining all_different +
  sub-tour elimination. when a variable's domain is a singleton, follows the
  partial chain and prunes values that would close a premature cycle.

### Semantics

```
sum_([X, Y, Z], #=, 10)          % X + Y + Z = 10
scalar_product([2, 3], [X, Y], #=, 12)   % 2X + 3Y = 12
element(I, [10, 20, 30], V)     % I in 1..3, V is list[I]
circuit([2, 3, 1])              % 1→2→3→1 (valid circuit)
```

### Test plan (~20 tests)

**sum_/3:**
- `sum_([X, Y], #=, 5)` with X in 1..3, Y in 1..3 → enumerate valid pairs.
- `sum_([], #=, 0)` → succeeds.
- Ground list: `sum_([1, 2, 3], #=, 6)` → succeeds.
- `sum_([1, 2, 3], #=, 7)` → fails.

**scalar_product/4:**
- `scalar_product([1, 1], [X, Y], #=, 5)` equivalent to sum_.
- `scalar_product([2, 3], [X, Y], #=, 12)` with domains → enumerate.
- Mismatched lengths → fails.

**element/3:**
- `element(2, [10, 20, 30], V)` → V = 20.
- `element(I, [10, 20, 30], 20)` → I = 2.
- `element(I, [10, 20, 30], V)` with I in 1..3 → enumerate all.
- Index out of range → fails.

**circuit/1:**
- `circuit([2, 3, 1])` → succeeds.
- `circuit([1, 2, 3])` → fails (self-loops / sub-tours).
- `circuit([X, Y, Z])` with domains 1..3, all_different → enumerate valid circuits.

---

## 5d — DCG Helper

**File:** `clausal/logic/builtins/dcg.py` (extend existing)

**Test file:** `tests/test_dcg.py` (extend existing)

### Predicates (1 new)

| Predicate | Description |
|---|---|
| `sequence//1` | `sequence(List)` — match/generate a list of terminals as a DCG rule. `sequence([a, b, c])` matches the terminals a, b, c in sequence. |

### Implementation notes

- `sequence//1` is a DCG non-terminal that consumes the elements of List from
  the difference list. Implemented as a trampoline builtin with arity 3
  (List, S0, S): unify S0 with `List ++ S` using list append.
  in_ practice: `deref(list_arg)`, compute `list_arg + deref(s)`,
  `unify(s0, computed)`.

- This is a DCG helper, so it takes the two extra difference-list
  arguments (S0, S) that DCG rules get. Register as builtin with arity 3.

### Test plan (~5 tests)

- `phrase(sequence([a, b, c]), [a, b, c])` → succeeds.
- `phrase(sequence([a, b, c]), [a, b])` → fails (not enough input).
- `phrase(sequence([]), [])` → succeeds.
- `phrase(sequence([a, b]), [a, b, c], Rest)` → Rest = [c].
- `phrase(sequence([a]), [b])` → fails.

---

## 5e — Tabling Management

**File:** `clausal/logic/builtins/control.py` (extend existing) or
`clausal/logic/builtins/tabling.py` (new)

**Test file:** `tests/test_tabling.py` (extend existing)

### Predicates (2 new)

| Predicate | Description |
|---|---|
| `AbolishAllTables/0` | Clear all tabled results. Requires the database reference. |
| `AbolishTable/1` | `AbolishTable(Pred)` — clear tabled results for a specific predicate. Pred should be a `functor/arity` term or a predicate class. |

### Implementation notes

- The methods `Database.abolish_all_tables()` and `Database.abolish_table(functor, arity)`
  **already exist** (database.py lines 216–218). This phase just exposes them
  as user-callable builtins.

- `AbolishAllTables/0` is a **database-aware builtin** (needs `db` parameter).
  Use `@_db_builtin("AbolishAllTables", 0)` pattern.

- `AbolishTable/1` takes a predicate reference. The argument should be a
  predicate class (e.g. `fib`) — extract `functor` and `arity` from
  `pred_cls._name` and `len(pred_cls._fields)`, then call
  `db.abolish_table(functor, arity)`.

### Test plan (~6 tests)

- Call tabled predicate, verify cached. AbolishAllTables, call again — recomputes.
- AbolishTable for specific predicate — only that table cleared.
- AbolishTable with non-tabled predicate — succeeds silently (no-op).
- AbolishAllTables when no tables exist — succeeds.

---

## 5f — Pairs Addition

**File:** `clausal/logic/builtins/pairs.py` (extend existing)

**Test file:** `tests/test_builtins.py` (extend existing) or `tests/test_pairs_extended.py` (new)

### Predicates (1 new)

| Predicate | Description |
|---|---|
| `group_pairs_by_key/2` | `group_pairs_by_key(Pairs, Groups)` — group a list of `[Key, Value]` pairs by key. Groups is a list of `[Key, Values]` pairs where Values collects all values for that key. Order preserved. |

### Implementation notes

- Deref the Pairs list. Iterate through, collecting values per key in insertion
  order (use `dict` which preserves insertion order in Python 3.7+).
- Result: `[[k, [v1, v2, ...]], ...]` for each unique key.
- Trampoline builtin (same pattern as existing pair predicates).

### Semantics

```
group_pairs_by_key([[a, 1], [b, 2], [a, 3]], Groups)
% Groups = [[a, [1, 3]], [b, [2]]]
```

### Test plan (~5 tests)

- Group with repeated keys → values collected.
- All unique keys → single-element value lists.
- Empty list → empty list.
- Single pair → single group.
- Order preservation: first occurrence of key determines group order.

---

## 5g — Error Checking Predicates

**File:** `clausal/logic/builtins/errors.py` (new) or add to existing

**Test file:** `tests/test_exceptions.py` (extend existing)

### Predicates (2 new)

| Predicate | Description |
|---|---|
| `must_be/2` | `must_be(Type, Term)` — assert that Term is of the given type. Succeeds silently if yes, throws `error(type_error(Type, Term), must_be/2)` if not. |
| `can_be/2` | `can_be(Type, Term)` — assert that Term could possibly be of the given type. Succeeds if Term is unbound (could become anything) or already is of the type. Throws if Term is ground and definitely not the type. |

### Supported types

| Type atom | Check |
|---|---|
| `"integer"` | `isinstance(term, int) and not isinstance(term, bool)` |
| `"float"` | `isinstance(term, float)` |
| `"number"` | `isinstance(term, (int, float)) and not isinstance(term, bool)` |
| `"atom"` / `"string"` | `isinstance(term, str)` |
| `"list"` | `isinstance(term, list)` |
| `"boolean"` | `isinstance(term, bool)` |
| `"callable"` | has `_get_dispatch` or is a type with `_get_dispatch` |
| `"dict"` | `isinstance(term, DictTerm)` |

### Implementation notes

- `must_be/2`: simple `@_builtin`. Deref Type and Term. If Term doesn't
  match Type, raise `LogicException(type_error(type_str, term, "must_be/2"))`.
  Otherwise yield once.
- `can_be/2`: same but if Term is an unbound Var, always succeed (it *could*
  become the right type). Only throw when Term is ground and wrong type.
- Use the existing `type_error()` helper from `clausal.logic.exceptions`.

### Test plan (~10 tests)

- `must_be("integer", 42)` → succeeds.
- `must_be("integer", "hello")` → throws type_error.
- `must_be("integer", X)` where X unbound → throws instantiation_error.
- `can_be("integer", 42)` → succeeds.
- `can_be("integer", "hello")` → throws type_error.
- `can_be("integer", X)` where X unbound → succeeds (could become integer).
- `must_be("list", [1, 2])` → succeeds.
- `must_be("number", 3.14)` → succeeds.
- `must_be("atom", 42)` → throws.
- `can_be("dict", DictTerm(...))` → succeeds.

---

## 5h — Reified Predicates ✓

Initially dropped, but later reinstated and implemented:

- **`tfilter/3`** — reified filter using Goal(Elem, T); keeps elements
  where T=True. Implemented in `builtins/higher_order.py`.
- **`tpartition/4`** — reified partition; splits list into Included (T=True)
  and Excluded (T=False). Implemented in `builtins/higher_order.py`.

---

## 5i — Time & statistics

**File:** `clausal/logic/builtins/control.py` (extend existing) or
`clausal/logic/builtins/time.py` (new)

**Test file:** `tests/test_control_extended.py` (new)

### Predicates (2 new)

| Predicate | Description |
|---|---|
| `current_time/1` | `current_time(T)` — unify T with the current Unix timestamp (float, seconds since epoch). |
| `statistics/2` | `statistics(Key, Value)` — query runtime statistics. Key bound → look up that stat. Key unbound → enumerate all available stats. |

### Available statistics keys

| Key | Value |
|---|---|
| `"wall_time"` | Wall-clock seconds since process start (float). |
| `"cpu_time"` | CPU seconds used by this process (float). |
| `"memory"` | Current RSS memory in bytes (int), via `resource` module. |

### Implementation notes

- `current_time/1`: `time.time()`, unify with T. Simple `@_builtin`.
- `statistics/2`: Use `time.monotonic()` for wall_time (store start time
  at module load), `time.process_time()` for cpu_time, `resource.getrusage()`
  for memory. when Key is unbound, enumerate all stats with trail mark/undo.
- Sleep/1 is already in `py.process` — no need to duplicate.

### Test plan (~8 tests)

- `current_time(T)` → T is a float > 0.
- Two calls to current_time: T2 >= T1.
- `statistics("cpu_time", V)` → V is a non-negative float.
- `statistics("wall_time", V)` → V is a non-negative float.
- `statistics("memory", V)` → V is a positive integer.
- `statistics(Key, V)` with Key unbound → at least 3 solutions.
- `statistics("nonexistent", V)` → fails.

---

## File Summary

### New files

| File | Purpose |
|---|---|
| `tests/test_lists_extended.py` | numlist, same_length, transpose tests (~15) |
| `tests/test_control_extended.py` | current_time, statistics tests (~8) |

### Modified files

| File | Change |
|---|---|
| `clausal/logic/builtins/arithmetic.py` | Add lcm/3, exp_mod/4, popcount/2, msb/2, lsb/2 |
| `clausal/logic/builtins/lists.py` | Add numlist/2,3, same_length/2, transpose/2 |
| `clausal/logic/builtins/dcg.py` | Add sequence//1 (as arity-3 builtin) |
| `clausal/logic/builtins/pairs.py` | Add group_pairs_by_key/2 |
| `clausal/logic/builtins/constraints.py` | Add sum_/3, scalar_product/4, element/3, circuit/1 wrappers; add AbolishAllTables/0, AbolishTable/1 |
| `clausal/logic/clpfd.py` | Add sum_constraint, scalar_product, element_constraint, circuit core logic |
| `clausal/logic/builtins/control.py` | Add current_time/1, statistics/2 |
| `clausal/logic/exceptions.py` | (unchanged — helpers already exist) |
| `clausal/logic/builtins/__init__.py` | Update docstring |
| `tests/test_clpfd.py` | Add sum_, scalar_product, element, circuit tests |
| `tests/test_dcg.py` | Add sequence tests |
| `tests/test_tabling.py` | Add AbolishAllTables, AbolishTable tests |
| `tests/test_arithmetic.py` | Add lcm, exp_mod, popcount, msb, lsb tests |
| `tests/test_exceptions.py` | Add must_be, can_be tests |

---

## Implementation Order

1. **5a — Arithmetic** (simplest, pure functions, no dependencies)
2. **5b — Lists** (simple, self-contained)
3. **5f — Pairs** (one predicate, trivial)
4. **5g — Error checking** (small, uses existing infrastructure)
5. **5i — Time & statistics** (small, no dependencies)
6. **5d — DCG helper** (needs understanding of DCG difference lists)
7. **5e — Tabling management** (uses existing Database methods)
8. **5c — CLP(FD) global constraints** (most complex — constraint propagation)

Sub-phases 1–7 are independent and can be done in any order or in parallel.
Sub-phase 8 (CLP(FD)) is the most substantial single piece of work.

---

## Total additions: 21 predicates, ~82 tests

| Sub-phase | Area | Predicates | Tests |
|---|---|---|---|
| 5a | Arithmetic | 5 | ~15 |
| 5b | Lists | 4 | ~15 |
| 5c | CLP(FD) | 4 | ~20 |
| 5d | DCGs | 1 | ~5 |
| 5e | Tabling | 2 | ~6 |
| 5f | Pairs | 1 | ~5 |
| 5g | Error | 2 | ~10 |
| ~~5h~~ | ~~Reif~~ | ~~dropped~~ | |
| 5i | Time | 2 | ~8 |
| **Total** | | **21** | **~84** |
