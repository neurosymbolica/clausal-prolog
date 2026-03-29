# Move type-check and term-inspection predicates to C

## Context

Two builtin modules implement fundamental type checking and term inspection:

- `clausal/logic/builtins/type_checks.py` (209 lines) — 14 ISO Prolog type checks
- `clausal/logic/builtins/inspection.py` (258 lines) — 7 ISO term inspection predicates

These are among the most frequently called predicates in any Prolog program.
`ground/1` and `copy_term/2` in particular perform recursive term walks.

## What to move

### From type_checks.py

```python
var/1          # succeeds if argument is unbound Var
nonvar/1       # succeeds if argument is NOT an unbound Var
integer/1      # type check
float_/1       # type check
number/1       # integer or float
atom/1         # zero-arity term or string
compound/1     # compound term
callable_/1    # atom or compound
is_list/1      # proper list check (walks entire list)
is_chars/1     # list of single-char strings
ground/1       # no unbound Vars anywhere (recursive walk)
must_be/2      # type assertion with error
can_be/2       # type compatibility check
```

### From inspection.py

```python
arg/3              # extract N-th argument from compound
functor/3          # decompose/construct compound (functor + arity)
copy_term/2        # deep copy with fresh Vars (recursive)
term_variables/2   # collect all unbound Vars (recursive)
numbervars/3       # number all Vars in a term
unpack/2           # convert term to [functor | args] list
```

### From builtins/_helpers.py (shared helpers)

```python
_is_ground(term)       # recursive groundness check
_functor_name(term)    # extract functor string from any term type
_arity(term)           # compute arity for any term type
_nth_arg(term, n)      # get n-th argument from any term type
_args_list(term)       # get all arguments as list
_is_compound(term)     # compound check
```

## Implementation approach

Most of these are simple type-dispatch functions:
- Check `deref(arg)` type with `PyLong_Check`, `PyFloat_Check`, `Var_Check`, etc.
- Return `True`/`False` (or the result of `unify` for bidirectional predicates)

The recursive ones (`ground/1`, `copy_term/2`, `term_variables/2`) walk term
structures.  Same recursive C pattern as `_deref_walk` and `_normalize_for_key`.

**Recommendation:** Add to `_variables.c` (most natural home since they operate
on Var/term types already defined there) or create a new `_term_ops.c`.

## Gotchas

1. **`copy_term/2` must allocate fresh Vars** for each unbound Var in the
   original and maintain a mapping (old Var → new Var).  Use a PyDict for the
   mapping.  Must also copy attributed variables with their attributes.

2. **`functor/3` is bidirectional**:
   - `functor(f(a,b), F, A)` → F=f, A=2 (decompose)
   - `functor(T, f, 2)` → T=f(_,_) (construct)
   The construct mode requires creating a term instance dynamically.

3. **`ground/1` calls `_is_ground` from `_helpers.py`** which is the same
   recursive walk as `_deref_walk` but returns bool instead of copying.
   See `C_predicate_helpers.md` for the `_is_ground` implementation.

4. **`is_list/1` walks the entire list** to verify it's a proper list
   (ends with `[]`, not an unbound Var or other term).  Must handle SegList.

5. **`term_variables/2` must return Vars in left-to-right order** (ISO
   requirement).  Use a list + set for dedup while preserving order.

## Overlaps

- `C_predicate_helpers.md` — covers `_is_ground`, `_functor_name`, `_arity`,
  `_nth_arg`, `_args_list`, `is_term_instance`, `term_field_names`.  These are
  shared helpers used by both type_checks.py and inspection.py.  Do
  `C_predicate_helpers.md` first, then this todo can call those C functions.

## How to verify

```bash
python -m pytest tests/ -k "type_check or inspection or ground or copy_term or functor" -x -q
python -m pytest tests/conformity/ -x -q
python -m pytest tests/ --ignore=tests/test_trealla_backend.py -x -q
```

Expected: Indirect speedup.  Programs that heavily use `ground/1`,
`copy_term/2`, or `term_variables/2` will see improvement.
