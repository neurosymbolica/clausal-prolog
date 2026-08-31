# `get/3` rejects a plain dict that `P[K]` subscript accepts — silently

**RESOLVED 2026-08-31** on `fix/get3-plain-dict-profile-api` — option 1: the
profile API (`get/3`, `get/4`, `tri_get/3`, `delete/3` in
`clausal/logic/builtins/dict_set.py`) now accepts `(DictTerm, dict)` wherever
it accepted only `DictTerm`, matching `_subscript` and the plain-dict
acceptance `DictTerm.__unify__`/`structural_eq` already had. Option 3 was
rejected because `get/3`'s documented contract is "never throws"; option 1
removes the trap instead of converting it to an error, and genuine non-dicts
still fail softly. Tests: `TestProfileAPIPlainDict` in
`tests/test_dict_set_builtins.py` (a "pop" family member named below does not
exist; the family is the four predicates above). The "Not addressed here"
sweep is parked as [[dictterm-only-builtins-sweep]].

**Found:** 2026-08-14, while building a Python client that calls domain formalizations
generically.
**Severity:** the asymmetry converts a wrong argument type into a **wrong answer**, not an
error. That is what makes it worth fixing rather than documenting.

## The two dict-access forms disagree

`clausal/logic/runtime/dict_ops.py:51-56` — `_subscript`, i.e. `V is P[K]`, accepts **both**:

```python
if isinstance(obj, DictTerm):
    data = obj.data
elif isinstance(obj, dict):
    data = obj
else:
    raise LogicException(type_error("dict", obj, _SUBSCRIPT_CTX))
```

`clausal/logic/builtins/dict_set.py:353` — `get/3` accepts **only** `DictTerm`:

```python
if (not is_var(key_val) and _is_hashable(key_val)
        and isinstance(d_val, DictTerm) and key_val in d_val):
```

and its docstring commits to failing softly:

> A non-ground key or non-dict object fails (soft: this predicate never throws — use
> `V is P[K]` for the strict, throwing read).

So for a plain Python dict, subscript reads **succeed** and `get/3` **fails silently**.
Both are documented behaviours in isolation; together they are a trap.

## Why that is worse than either behaviour alone

A caller passing a plain dict gets a **partly working** profile. The reads that use
subscript return correct values, so the clause looks healthy — while every `get/3` guard
silently fails, so guarded clauses never fire and their `not get(...)` counterparts do.

Observed in a dated-lookup rule of this shape — a guarded clause and its `not`-guarded
fallback, where the guard is a `get/3` and the reads around it are subscripts:

```prolog
applicable_rate(PROFILE, RATE) <- (
    get(PROFILE, as_of_date, AS_OF_DATE),     % never fired with a plain dict
    CATEGORY is PROFILE[category_key],        % worked fine, masking the problem
    ...
    dated_rate(CATEGORY, TIER, AS_OF_DATE, RATE)
)

applicable_rate(PROFILE, RATE) <- (
    not get(PROFILE, as_of_date, _),          % always fired instead
    ...
    current_rate(CATEGORY, TIER, RATE)
)
```

Result: the date-aware clause was skipped and the **date-blind** one ran, so a record
dated years earlier was assessed against *today's* values. No error, no warning, a
plausible-looking verdict with the wrong number — and where such a rule gates a
compliance decision, that is a false finding against a real subject.

It took three debugging rounds to locate, precisely because the subscript reads kept
working.

## Reproduction

```python
from clausal.terms import DictTerm
# In a generated query script, pass the profile two ways:
#   {'k': v}            -> get/3 fails, subscript succeeds
#   DictTerm({'k': v})  -> both succeed
```

The client-side fix was to always construct a `DictTerm`. That is correct and it is what
source-level `{...}` literals compile to — but nothing told us, and nothing failed loudly.

## Options

1. **Make `get/3` (and the `get/4`, `pop`, `del` family at `dict_set.py:97,109,122,143`)
   accept a plain `dict`**, matching `_subscript`. Most consistent; the two access forms
   stop disagreeing about what a dict is.
2. **Make `_subscript` reject a plain `dict`** with `type_error(dict, obj)`. Also
   consistent, and loud — but it may break existing callers that rely on the leniency.
3. **Keep the asymmetry, make it loud:** have `get/3` throw `type_error(dict, obj)` for a
   non-`DictTerm` *dict-like* argument while still failing softly for genuine non-dicts.
   Preserves the documented soft-read contract for the case it was written for, and closes
   the silent-degradation path.

Option 1 or 3 seems right; option 2 has the widest blast radius. The important property is
that **a plain dict must not be silently half-accepted**.

## Not addressed here

Whether other builtins make the same `DictTerm`-only assumption while their `is/2`
counterparts do not. Worth a sweep — this pattern would be invisible in exactly the same
way anywhere it recurs.
