# Phase 6 — Advanced Z3 Theories

Expose Z3-only theories that have no CLP equivalent: bitvectors, arrays,
strings/sequences, sets, algebraic datatypes, and quantifiers.

**Depends on:** Phase 1 (core infrastructure), Phase 5 (for propagator-backed theories)

---

## Files to Modify/Create

| File | Action |
|------|--------|
| `clausal/logic/clpz3.py` | Add sort declarations, operations, labeling for each theory |
| `clausal/logic/builtins/z3_constraints.py` | Register builtins |
| `tests/test_clpz3_bv.py` | Bitvector tests |
| `tests/test_clpz3_array.py` | Array tests |
| `tests/test_clpz3_string.py` | String tests |
| `tests/test_clpz3_set.py` | Set tests |
| `tests/test_clpz3_quant.py` | Quantifier tests |
| `tests/test_clpz3_datatype.py` | Algebraic datatype tests |

---

## 1. Bitvectors

Fixed-width machine arithmetic with overflow, shifts, and bitwise operations.
Useful for verification, cryptography, and hardware modeling.

### API

```python
def in_z3_bv(var_or_list, width, trail: Trail) -> bool:
    """Declare bitvector variable(s) of given bit-width."""
    state = get_z3_state(trail)
    sort = _z3.BitVecSort(width)
    var_or_list = _to_var_list(var_or_list)
    for v in var_or_list:
        v = deref(v)
        if is_var(v):
            z3_var_for(v, sort, trail)
        elif isinstance(v, int):
            pass  # ground — no registration needed
        else:
            raise TypeError(f"in_z3_bv: expected int or Var, got {type(v).__name__}")
    return True


def label_z3_bv(vars_list, trail: Trail):
    """Enumerate bitvector solutions. Same blocking-clause pattern as label_z3."""
    state = get_z3_state(trail)
    vars_list = _to_var_list(deref(vars_list))
    z3_vars, clausal_vars = _partition_vars(vars_list, state, trail)

    if not z3_vars:
        yield None
        return

    enum_mark = trail.mark()
    z3_push(trail)

    while state.solver.check() == _z3.sat:
        m = state.solver.model()
        values = [m.eval(z3v, model_completion=True).as_long() for z3v in z3_vars]
        mark = trail.mark()
        ok = all(unify(cv, val, trail) for cv, val in zip(clausal_vars, values))
        if ok:
            yield None
        trail.undo(mark)
        state.solver.add(_z3.Or([z3v != m.eval(z3v, model_completion=True)
                                 for z3v in z3_vars]))
```

### Bitvector Operations

Expose Z3's bitvector operations as Clausal builtins or as expression
translation rules:

| Clausal | Z3 | Description |
|---------|----|-------------|
| `bv_add(X, Y)` | `x + y` (BV) | Addition with wrap |
| `bv_sub(X, Y)` | `x - y` (BV) | Subtraction with wrap |
| `bv_mul(X, Y)` | `x * y` (BV) | Multiplication with wrap |
| `bv_udiv(X, Y)` | `z3.UDiv(x, y)` | Unsigned division |
| `bv_sdiv(X, Y)` | `x / y` (BV) | Signed division |
| `bv_urem(X, Y)` | `z3.URem(x, y)` | Unsigned remainder |
| `bv_srem(X, Y)` | `z3.SRem(x, y)` | Signed remainder |
| `bv_and(X, Y)` | `x & y` (BV) | Bitwise AND |
| `bv_or(X, Y)` | `x \| y` (BV) | Bitwise OR |
| `bv_xor(X, Y)` | `x ^ y` (BV) | Bitwise XOR |
| `bv_not(X)` | `~x` (BV) | Bitwise NOT |
| `bv_shl(X, N)` | `x << n` (BV) | Shift left |
| `bv_lshr(X, N)` | `z3.LShR(x, n)` | Logical shift right |
| `bv_ashr(X, N)` | `x >> n` (BV) | Arithmetic shift right |
| `bv_ult(X, Y)` | `z3.ULT(x, y)` | Unsigned less-than |
| `bv_ule(X, Y)` | `z3.ULE(x, y)` | Unsigned less-equal |
| `bv_ugt(X, Y)` | `z3.UGT(x, y)` | Unsigned greater-than |
| `bv_slt(X, Y)` | `x < y` (BV) | Signed less-than |
| `bv_concat(X, Y)` | `z3.Concat(x, y)` | Concatenation |
| `bv_extract(Hi, Lo, X)` | `z3.Extract(hi, lo, x)` | Bit extraction |
| `bv_zext(X, N)` | `z3.ZeroExt(n, x)` | Zero extension |
| `bv_sext(X, N)` | `z3.SignExt(n, x)` | Sign extension |

### Implementation Strategy

**Option A: Builtins for each operation.** Register `bv_add/3`, `bv_shl/3`, etc.
The builtin posts a Z3 constraint `result == op(x, y)`.

```python
@_builtin("bv_add", 3)
def _bv_add__3(x, y, result, trail, k):
    """bv_add(X, Y, Result) — bitvector addition."""
    from clausal.logic.clpz3 import bv_binop
    if bv_binop(x, y, result, lambda a, b: a + b, trail):
        yield None

def bv_binop(x, y, result, op, trail):
    state = get_z3_state(trail)
    z3_x = clausal_to_z3(x, trail)
    z3_y = clausal_to_z3(y, trail)
    z3_r = z3_var_for(deref(result), z3_x.sort(), trail) if is_var(deref(result)) \
           else clausal_to_z3(result, trail)
    state.solver.add(z3_r == op(z3_x, z3_y))
    return True
```

**Option B: Expression translation.** Extend `clausal_to_z3()` to handle BV
operation nodes. Requires defining new AST node types or using `Compound` with
specific functors.

**Recommendation: Option A for Phase 6.** Simpler, explicit. Option B can be
added later for syntactic sugar.

### Clausal Syntax Examples

```prolog
# 8-bit overflow detection
Overflow(X, Y, SUM, OVERFLOW) <- (
    in_z3_bv([X, Y, SUM], 8),
    bv_add(X, Y, SUM),
    bv_ult(SUM, X, OVERFLOW),         # overflow if sum < operand
    label_z3_bv([X, Y])
)

# Bit manipulation: count leading zeros (simplified)
CLZ(X, N) <- (
    in_z3_bv(X, 32),
    in_z3(N, 0, 32),
    # ... constraint encoding ...
)
```

### Tests

```python
class TestBitvectors:
    def test_8bit_add(self):
        trail = Trail()
        x, y, s = Var(), Var(), Var()
        in_z3_bv([x, y, s], 8, trail)
        bv_add(x, y, s, trail)
        z3_eq_bv(x, 200, trail)  # need BV-aware eq
        z3_eq_bv(y, 100, trail)
        for _ in label_z3_bv([s], trail):
            assert deref(s) == 44  # (200 + 100) mod 256 = 44

    def test_shift_left(self):
        trail = Trail()
        x, r = Var(), Var()
        in_z3_bv([x, r], 8, trail)
        bv_shl(x, 2, r, trail)  # r = x << 2
        z3_eq_bv(x, 3, trail)
        for _ in label_z3_bv([r], trail):
            assert deref(r) == 12

    def test_extract(self):
        trail = Trail()
        x, r = Var(), Var()
        in_z3_bv(x, 8, trail)
        in_z3_bv(r, 4, trail)
        bv_extract(7, 4, x, r, trail)  # upper nibble
        z3_eq_bv(x, 0xAB, trail)
        for _ in label_z3_bv([r], trail):
            assert deref(r) == 0xA
```

---

## 2. Arrays

SMT arrays with `select` (read) and `store` (write) operations. Useful for
modeling memory, lookup tables, and functional maps.

### API

```python
def z3_array(var, domain_sort, range_sort, trail: Trail) -> bool:
    """Declare an array variable: Array(domain_sort, range_sort)."""
    state = get_z3_state(trail)
    var = deref(var)
    sort = _z3.ArraySort(domain_sort, range_sort)
    z3_var_for(var, sort, trail)
    return True

def z3_select(array, index, value, trail: Trail) -> bool:
    """Select(array, index) == value."""
    state = get_z3_state(trail)
    z3_arr = clausal_to_z3(array, trail)
    z3_idx = clausal_to_z3(index, trail)
    z3_val = clausal_to_z3(value, trail) if not is_var(deref(value)) \
             else z3_var_for(deref(value), z3_arr.sort().range(), trail)
    state.solver.add(_z3.Select(z3_arr, z3_idx) == z3_val)
    return True

def z3_store(array, index, value, result, trail: Trail) -> bool:
    """result == Store(array, index, value)."""
    state = get_z3_state(trail)
    z3_arr = clausal_to_z3(array, trail)
    z3_idx = clausal_to_z3(index, trail)
    z3_val = clausal_to_z3(value, trail)
    z3_res = z3_var_for(deref(result), z3_arr.sort(), trail) if is_var(deref(result)) \
             else clausal_to_z3(result, trail)
    state.solver.add(z3_res == _z3.Store(z3_arr, z3_idx, z3_val))
    return True

def z3_const_array(value, domain_sort, result, trail: Trail) -> bool:
    """result is a constant array where every element is value."""
    state = get_z3_state(trail)
    z3_val = clausal_to_z3(value, trail)
    arr = _z3.K(domain_sort, z3_val)
    z3_res = z3_var_for(deref(result), arr.sort(), trail)
    state.solver.add(z3_res == arr)
    return True
```

### Clausal Syntax Examples

```prolog
ArrayExample(V) <- (
    z3_array(A, int, int),
    z3_store(A, 0, 42, A1),
    z3_store(A1, 1, 99, A2),
    z3_select(A2, 0, V),
    label_z3([V])                # V = 42
)

Test("array store/select") <- ArrayExample(42)
```

### Gotchas

- **Array equality:** Two arrays are equal iff they agree on all indices.
  Z3 handles this via extensionality.
- **No enumeration:** Arrays have infinite domains. `label_z3` on array
  variables doesn't make sense. Only label the elements.
- **Nested arrays:** `Array(Int, Array(Int, Int))` for 2D arrays. Works
  but complex.

---

## 3. Strings and Sequences

Z3's string theory supports regex constraints, length constraints, and
string operations.

### API

```python
def z3_string(var, trail: Trail) -> bool:
    """Declare a string variable."""
    z3_var_for(deref(var), _z3.StringSort(), trail)
    return True

def z3_str_length(s, n, trail: Trail) -> bool:
    """Length(s) == n."""
    state = get_z3_state(trail)
    z3_s = clausal_to_z3(s, trail)
    z3_n = clausal_to_z3(n, trail, default_sort=_z3.IntSort())
    state.solver.add(_z3.Length(z3_s) == z3_n)
    return True

def z3_str_contains(s, substr, trail: Trail) -> bool:
    """Contains(s, substr)."""
    state = get_z3_state(trail)
    z3_s = clausal_to_z3(s, trail)
    z3_sub = _z3.StringVal(deref(substr)) if isinstance(deref(substr), str) \
             else clausal_to_z3(substr, trail)
    state.solver.add(_z3.Contains(z3_s, z3_sub))
    return True

def z3_str_concat(s1, s2, result, trail: Trail) -> bool:
    """result == Concat(s1, s2)."""
    state = get_z3_state(trail)
    z3_s1 = clausal_to_z3(s1, trail)
    z3_s2 = clausal_to_z3(s2, trail)
    z3_r = z3_var_for(deref(result), _z3.StringSort(), trail) \
           if is_var(deref(result)) else clausal_to_z3(result, trail)
    state.solver.add(z3_r == _z3.Concat(z3_s1, z3_s2))
    return True

def z3_str_regex(s, pattern, trail: Trail) -> bool:
    """s matches the regular expression pattern (Z3 Re syntax)."""
    state = get_z3_state(trail)
    z3_s = clausal_to_z3(s, trail)
    z3_re = _z3.Re(pattern) if isinstance(pattern, str) else pattern
    state.solver.add(_z3.InRe(z3_s, z3_re))
    return True
```

### Clausal Syntax Examples

```prolog
StringExample(S) <- (
    z3_string(S),
    z3_str_contains(S, "hello"),
    z3_str_length(S, 5),
    z3_check()
    # S must be exactly "hello"
)

Test("string contains + length") <- StringExample("hello")
```

### Gotchas

- **String sort vs Clausal strings:** Clausal strings are Python `str`.
  Z3 strings are `SeqRef` with `StringSort`. The `clausal_to_z3` translator
  must handle `str` → `StringVal`.
- **String labeling:** `label_z3_str` would need to extract string values
  from Z3 models. Use `m.eval(z3_s).as_string()`.
- **Regex syntax:** Z3 uses its own regex constructors (`Re`, `Star`, `Plus`,
  `Option`, `Union`, `Intersect`). Not POSIX regex. May need a translator.
- **Performance:** Z3's string solver is less mature than arithmetic. Complex
  string constraints may return `unknown`.

---

## 4. Sets

Z3 sets are represented as arrays from elements to Bool (characteristic
function encoding).

### API

```python
def z3_set(var, elem_sort, trail: Trail) -> bool:
    """Declare a set variable over elem_sort."""
    sort = _z3.SetSort(elem_sort)
    z3_var_for(deref(var), sort, trail)
    return True

def z3_set_member(elem, s, trail: Trail) -> bool:
    """elem ∈ s."""
    state = get_z3_state(trail)
    z3_e = clausal_to_z3(elem, trail)
    z3_s = clausal_to_z3(s, trail)
    state.solver.add(_z3.IsMember(z3_e, z3_s))
    return True

def z3_set_union(s1, s2, result, trail: Trail) -> bool:
    """result = s1 ∪ s2."""
    state = get_z3_state(trail)
    z3_s1 = clausal_to_z3(s1, trail)
    z3_s2 = clausal_to_z3(s2, trail)
    z3_r = z3_var_for(deref(result), z3_s1.sort(), trail)
    state.solver.add(z3_r == _z3.SetUnion(z3_s1, z3_s2))
    return True

def z3_set_intersect(s1, s2, result, trail: Trail) -> bool:
    """result = s1 ∩ s2."""
    state = get_z3_state(trail)
    z3_s1 = clausal_to_z3(s1, trail)
    z3_s2 = clausal_to_z3(s2, trail)
    z3_r = z3_var_for(deref(result), z3_s1.sort(), trail)
    state.solver.add(z3_r == _z3.SetIntersect(z3_s1, z3_s2))
    return True

def z3_set_subset(s1, s2, trail: Trail) -> bool:
    """s1 ⊆ s2."""
    state = get_z3_state(trail)
    z3_s1 = clausal_to_z3(s1, trail)
    z3_s2 = clausal_to_z3(s2, trail)
    state.solver.add(_z3.IsSubset(z3_s1, z3_s2))
    return True

def z3_set_add(s, elem, result, trail: Trail) -> bool:
    """result = s ∪ {elem}."""
    state = get_z3_state(trail)
    z3_s = clausal_to_z3(s, trail)
    z3_e = clausal_to_z3(elem, trail)
    z3_r = z3_var_for(deref(result), z3_s.sort(), trail)
    state.solver.add(z3_r == _z3.SetAdd(z3_s, z3_e))
    return True
```

### Gotchas

- **Sets are arrays internally.** `SetSort(IntSort)` is `ArraySort(IntSort, BoolSort)`.
- **Empty set:** `z3.EmptySet(IntSort())`.
- **No enumeration of set contents.** Sets are symbolic. You can check
  membership but not list elements.

---

## 5. Quantifiers

Z3 supports universal (`ForAll`) and existential (`Exists`) quantification
with E-matching.

### API

```python
def z3_forall(var_sorts, body_fn, trail: Trail) -> bool:
    """ForAll quantification.

    var_sorts: list of (name, sort) pairs for quantified variables
    body_fn: callable that takes Z3 bound variables and returns a BoolRef

    Example: z3_forall([("x", IntSort())], lambda x: x > 0 implies f(x) > 0)
    """
    state = get_z3_state(trail)
    bound_vars = [_z3.Const(name, sort) for name, sort in var_sorts]
    body = body_fn(*bound_vars)
    state.solver.add(_z3.ForAll(bound_vars, body))
    return True

def z3_exists(var_sorts, body_fn, trail: Trail) -> bool:
    """Exists quantification."""
    state = get_z3_state(trail)
    bound_vars = [_z3.Const(name, sort) for name, sort in var_sorts]
    body = body_fn(*bound_vars)
    state.solver.add(_z3.Exists(bound_vars, body))
    return True
```

### Clausal Syntax Challenge

Quantifiers require lambda-like syntax for the body. In `.clausal` files,
this could use Clausal's existing lambda support:

```prolog
AllPositive(F) <- (
    z3_function(F, [int], int),
    z3_forall_int(X, z3_implies(X > 0, z3_app(F, X) > 0)),
    z3_check()
)
```

**This is the hardest API to design for Clausal syntax.** Defer the `.clausal`
syntax to a later iteration; start with Python-level API only.

### Gotchas

- **E-matching:** Z3 uses E-matching heuristics for quantifier instantiation.
  Providing patterns helps: `ForAll(x, body, patterns=[f(x)])`.
- **Decidability:** Quantified formulas over integers are undecidable in general.
  Z3 may return `unknown`. Linear arithmetic quantifiers are decidable.
- **Performance:** Quantifiers can make solving very slow. Use sparingly.

---

## 6. Algebraic Datatypes

Z3 supports recursive algebraic datatypes (like ML/Haskell datatypes).

### API

```python
def z3_declare_datatype(name, constructors, trail: Trail):
    """Declare an algebraic datatype.

    constructors: list of (constructor_name, [(field_name, sort), ...])

    Example:
        z3_declare_datatype("Tree", [
            ("Leaf", [("val", IntSort())]),
            ("Node", [("left", "Tree"), ("right", "Tree")]),
        ])
    """
    dt = _z3.Datatype(name)
    for ctor_name, fields in constructors:
        processed_fields = []
        for fname, fsort in fields:
            if isinstance(fsort, str):
                # Self-reference
                processed_fields.append((fname, dt))
            else:
                processed_fields.append((fname, fsort))
        dt.declare(ctor_name, *processed_fields)
    sort = dt.create()
    # Store in Z3State for later use
    state = get_z3_state(trail)
    if not hasattr(state, 'datatypes'):
        state.datatypes = {}
    state.datatypes[name] = sort
    return sort
```

### Clausal Syntax (Future)

```prolog
# Declare a Color enum
-z3_enum(Color, [red, green, blue])

# Declare a Tree datatype
-z3_datatype(Tree, [
    leaf(val: int),
    node(left: Tree, right: Tree)
])
```

**Defer `.clausal` syntax to a later iteration.** Start with Python API.

---

## 7. Uninterpreted Functions

Z3 supports uninterpreted functions — functions with no fixed interpretation,
constrained only by the assertions.

```python
def z3_function(var, domain_sorts, range_sort, trail: Trail):
    """Declare an uninterpreted function.

    Returns the Z3 FuncDeclRef.
    """
    state = get_z3_state(trail)
    func = _z3.Function(f"f_{state._counter}", *domain_sorts, range_sort)
    state._counter += 1
    # Store reference
    if is_var(deref(var)):
        # Can't directly store FuncDeclRef as a Clausal term easily
        # Use put_attr to associate with the Var
        put_attr(deref(var), Z3_KEY, Z3FuncInfo(func, domain_sorts, range_sort), trail)
    return func

def z3_app(func_var, args, result, trail: Trail) -> bool:
    """Apply an uninterpreted function: result == f(args...)."""
    state = get_z3_state(trail)
    info = get_attr(deref(func_var), Z3_KEY)
    z3_args = [clausal_to_z3(a, trail) for a in args]
    z3_r = z3_var_for(deref(result), info.range_sort, trail) if is_var(deref(result)) \
           else clausal_to_z3(result, trail)
    state.solver.add(z3_r == info.func(*z3_args))
    return True
```

---

## 8. Helper: `_to_var_list` and `_partition_vars`

Several functions need the same list-conversion and var-partitioning logic:

```python
def _to_var_list(var_or_list):
    """Convert to Python list, handling SegList and single values."""
    if isinstance(var_or_list, list):
        return var_or_list
    from clausal.terms import cons_to_list
    try:
        return cons_to_list(var_or_list)
    except (ValueError, TypeError):
        return [var_or_list]

def _partition_vars(vars_list, state, trail):
    """Separate into (z3_vars, clausal_vars) pairs, skipping ground values."""
    z3_vars = []
    clausal_vars = []
    for v in vars_list:
        v = deref(v)
        if is_var(v):
            z3_v = state.var_map.get(id(v))
            if z3_v is None:
                raise ValueError("Variable not registered with Z3")
            z3_vars.append(z3_v)
            clausal_vars.append(v)
    return z3_vars, clausal_vars
```

---

## 9. Tests

### `tests/test_clpz3_bv.py` — Key Test Cases

- 8-bit addition with wraparound
- Signed vs unsigned comparison
- Shift operations
- Bit extraction and concatenation
- Overflow detection pattern
- All-zeros, all-ones edge cases
- Width mismatch (should error)

### `tests/test_clpz3_array.py` — Key Test Cases

- Store then select (same index) → get stored value
- Store then select (different index) → get original value
- Two stores to same index → last write wins
- Constant array → all selects return same value
- Array equality with identical stores

### `tests/test_clpz3_string.py` — Key Test Cases

- Length constraint
- Contains constraint
- Concatenation constraint
- Regex membership (simple patterns)
- Empty string edge case
- Unicode handling

### `tests/test_clpz3_set.py` — Key Test Cases

- Member after add → succeeds
- Union/intersection with concrete sets
- Subset constraint
- Empty set
- Complement

### `tests/test_clpz3_quant.py` — Key Test Cases

- Simple ForAll (linear arithmetic)
- Simple Exists
- Quantifier with uninterpreted function
- Known undecidable case → Z3 returns `unknown`

---

## 10. Gotchas

1. **Sort inference:** For new theories, the expression translator needs
   to handle new sorts. `clausal_to_z3` should be extended with a sort
   parameter or auto-detect from context.

2. **Cross-theory constraints:** Z3's theory combination handles Int + BV
   or Array + Int automatically. But Clausal's expression translator must
   produce the right sorts. Don't mix `IntVal` and `BitVecVal` in the same
   expression.

3. **Model extraction:** Each theory has its own model extraction method.
   `z3_to_python` needs cases for `BitVecNumRef`, `ArrayRef`, `SeqRef`, etc.

4. **Performance:** BV solving is NP-complete (bit-blasting). Large bitvectors
   (64-bit, 128-bit) can be very slow.

5. **Labeling semantics:** Only BV and Int variables can be meaningfully
   enumerated. Arrays, strings, sets, and functions have infinite domains.
   Provide `label_z3_bv` but not `label_z3_array`.

---

## Implementation Order

1. Helper functions (`_to_var_list`, `_partition_vars`)
2. Bitvectors: `in_z3_bv`, BV operations, `label_z3_bv`
3. Arrays: `z3_array`, `z3_select`, `z3_store`
4. Sets: `z3_set`, `z3_set_member`, `z3_set_union`, etc.
5. Strings: `z3_string`, `z3_str_length`, `z3_str_contains`, etc.
6. Uninterpreted functions: `z3_function`, `z3_app`
7. Quantifiers: `z3_forall`, `z3_exists` (Python API only)
8. Algebraic datatypes: `z3_declare_datatype` (Python API only)
9. Builtin registration for all theories
10. Tests for each theory
