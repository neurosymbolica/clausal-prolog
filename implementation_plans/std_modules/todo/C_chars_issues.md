# _chars_core.c — known issues and future work

Follow-up issues from the C accelerated inner loops for char/string predicates.

## ~~1. `is_alnum` and `is_punct` classifiers wrong for non-ASCII~~ DONE

Added `Py_UNICODE_ISNUMERIC(c)` to `is_alnum`.  Rewrote `is_punct` to call
`is_alnum()` instead of inlining an incomplete check.  Verified with `'½'`
(U+00BD): C and Python now agree (`['alnum', 'print']`).

## ~~2. `ascii_char_objs` init is wrong on big-endian architectures~~ DONE

Replaced `PyUnicode_FromKindAndData(PyUnicode_1BYTE_KIND, &ch, 1)` with
`PyUnicode_FromOrdinal(i)`.  Endian-safe and benefits from CPython's
internal Latin-1 singleton cache (no extra allocation for chars 0–255).

## ~~3. `sub_atom_enum` has dead/redundant code in b-range logic~~ DONE

Collapsed the `vb_fixed >= 0` branch to a single guard:
```c
if (vb_fixed > n || b_start > vb_fixed) Py_RETURN_NONE;
b_lo = vb_fixed;
b_hi = vb_fixed + 1;
```
Removed the dead `vl_fixed < 0` check from the inner branch.

## ~~4. Out-of-range bound Before/Length causes O(n^2) wasted unifications~~ DONE

Added early-return checks in the Python caller before entering the C loop:
```python
if not is_var(vb) and isinstance(vb, int) and (vb < 0 or vb > n):
    return
if not is_var(vl) and isinstance(vl, int) and vl < 0:
    return
```
Simplified the `vb_fixed`/`vl_fixed` guards to remove the now-redundant
range checks (the early return guarantees in-range if bound).

## 5. No C acceleration for the 8 deterministic predicates — DEFERRED

Only the 3 predicates with inner loops got C helpers: `char_type/2`,
`atom_concat/3`, `sub_atom/5`.  The remaining 8 (`char_code/2`,
`upcase_atom/2`, `downcase_atom/2`, `atom_length/2`, `atom_chars/2`,
`atom_codes/2`, `number_chars/2`, `number_codes/2`) are still pure Python.

These are all single-unify deterministic predicates — each does one deref, one
type check, and one unify call.  The per-call saving from C would be small
(eliminating Python method dispatch for deref/is_var/unify).  The benefit
would primarily show in tight loops calling these predicates many times.

Could use an "Option C" pattern: a single C function that does the entire
predicate (deref, validate, compute, unify) and returns True/False, called
from a thin Python wrapper.

## 6. `sub_atom_enum` flat encoding could overflow for very long strings — NO ACTION NEEDED

The flat position encoding uses `stride = n + 2`, so `flat = b * (n+2) + l`.
For strings approaching `PY_SSIZE_T_MAX` in length, the multiplication could
overflow `Py_ssize_t`.  In practice, Python cannot allocate strings anywhere
near that size (memory exhaustion well before), so this is theoretical.

## 7. Module state is global (`m_size = -1`) — NO ACTION NEEDED

The module uses `m_size = -1` (no per-module state), meaning all static
arrays (`ascii_char_objs`, `type_name_objs`, lookup tables) are global.
This is incompatible with sub-interpreters (PEP 684).

All existing C extensions in this repo use the same pattern, so this is
consistent.  Would need `Py_mod_multiple_interpreters` and per-module state
structs if sub-interpreter support is ever required.

## 8. `PyUnicode_Substring` allocations in `atom_concat_split_find` — DEFERRED

Each split iteration allocates two new `PyUnicode` objects for prefix and
suffix.  For long strings with many splits, this creates GC pressure.

Could be optimized with `PyUnicode_Substring` only for the successful
unification, and use `PyUnicode_GET_LENGTH`-based comparison for early
rejection when the target variable is already bound to a different-length
string.  Alternatively, for pure-ASCII strings, could use
`PyUnicode_FromKindAndData` on slices of the underlying buffer without
copying.
