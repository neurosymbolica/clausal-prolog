# P0 census findings — PredicateMeta retirement

Instrument: `census.py`. Exit criterion: **zero unclassified**, because a site classified wrong is
a silent behaviour change.

## State

    431 references, 50 files
      93  comments
     163  auto-classified
     268  MUST BE READ   <-- the work queue

Concentrated: `_variables.c` 41, `predicate.py` 32, `specialization.py` 32, `compiler_v2.py` 16,
`solve.py` 14, `term_rewriting.py` 14.

## The taxonomy is FIVE categories, not the spec's two

    A  PREDICATE TEST        "is this name a predicate here?"      -> Database membership test
    B  TERM CONSTRUCTION     resolve name -> class -> CALL it      -> build a functor-first tuple
    C  ZERO-FIELD-CLASS      `... and not term._fields`            -> the LEGACY ATOM shape
    D  DECLARATION           metaclass= / $PredicateMeta in AST    -> deleted with the guard
    E  IMPORT                follows its users

**Category C is a finding.** `inspection.py:51,140` and `testing.py:1662` still convert a
zero-field predicate class into an `Atom`. So THE FLIP did not fully eliminate zero-field classes
as an atom representation — they still occur and are still treated as atoms on some paths. Any
plan that assumes "atoms are tuples, full stop" is wrong on these paths and needs to say what
happens to them.

## FILE COMPLETE: `specialization.py` — NO class-identity dependency

The file flagged in the spec as most likely to hold an assumption beyond routing. It does not.
Its 32 references reduce to ~14 behavioural lines:

    pred_cls._fields      6   arity, and field names that become positional indices
    pred_cls.__name__     6   the functor string
    pred_cls._clauses     2   -> db.row(functor, arity).clauses
    pred_cls._row         1   ALREADY the row
    pred_cls._ensure_clauses / _bind_row / _assertz   1 each, row operations
    pred_cls(**head_fields)   4 sites (513, 586, 693, 1039) -- TERM CONSTRUCTION

**There is no `type(x) is pred_cls`, no identity comparison, and no reliance on the class object
beyond name/arity/row.** Everything it needs is `(functor, arity)` plus the row, both of which
`Database.row(functor, arity)` already provides.

Remaining work in this file: 4 construction sites become tuple construction, and the
`(functor, fields)` pairs become `(functor, arity)`. That is a signature change, not a redesign.

**Why this matters more than one file:** `specialization.py` was the worst case by reference count
and by suspicion. Its dependencies turning out to be name + arity + row is the strongest evidence
so far that the removal is mechanical rather than architectural.

## Not yet read

`_variables.c` (41) is the one that could still change the verdict — it is the C core's
unify/deref/compare special-casing, and it is the only place that could hold a representation
assumption the Python side cannot express. **Read it before believing the removal is mechanical.**
