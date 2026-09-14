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

**Category C — CORRECTED.** I first recorded this as an undiscovered gap: that THE FLIP had not
fully eliminated zero-field classes as an atom representation. **That overstated it.** The tree has
already separated the two questions and documented the union, at `predicate.py:1617`:

> *"Two different questions share the stem `is_atom` in this tree, and this is the union of them:
> `clausal.logic.atoms.is_atom` is the TERM test — exactly the 1-tuple whose slot 0 is a `str`.
> `predicate.is_zero_field_class` is the CLASS test."*

So a zero-arity `PredicateMeta` class is a **declared atom** by design, and `is_atom_value` admits
it deliberately. `inspection.py:51,140` and `testing.py:1662` are honouring that, not leaking.

What survives of the finding: the plan must still say **what happens to declared atoms** when the
class goes — they need a tuple spelling and a migration. But the tree is not confused about it, and
I should not have implied it was.

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

## FILE COMPLETE: `_variables.c` — does NOT block the removal

The 41 references, read. They do not hold a blocking assumption, for one decisive reason:

**The C is ALREADY polymorphic over term representations.** `c_is_term_instance` (2190) tests for a
`PredicateMeta` instance *and then falls back* to a `__dataclass_fields__` probe — so two term
representations are already supported, with the fallback documented in the source. Adding or
removing one is in-pattern, not architectural.

Everything else is one of four routine shapes behind a single cached type pointer
(`PredicateMeta_type`, set by `_register_predicate_meta`, 2115-2139):

    "is this a term instance?"    2204        -> the term test, already polymorphic
    "is this a predicate CLASS?"  2344, 2540, 2984, 3351
                                              -> used for ground-ness and no-variables
                                                 shortcuts: "PredicateMeta classes are always
                                                 ground -- they're types, not terms" (2341)
    field names                   2278-2301   -> `_fields`, with a py_term_field_names fallback
    reconstruction                3133, 3151  -> copy fields, rebuild via the fast constructor

The `PredicateMeta_type == NULL` guards are **defensive, not a degradation path** — the comment at
2195 says registration happens at import from `predicate.py` before any caller can reach it, and
returning 0 is "rather than silently misclassifying". So do not read them as evidence the C can
already run without the metaclass.

**One piece of genuinely stale C.** `py_is_atom` (2305) implements the LEGACY meaning — "a
`PredicateMeta` class with zero fields" — and is exported from the extension (3755) but **not
re-exported by `clausal/logic/variables/__init__.py`**, so it is unreachable through the package
surface. `atoms.is_atom` is the live term test and is pure Python over tuples. Three modules do
import from `._variables` directly (`predicate.py:1584`, `builtins/inspection.py:197`,
`builtins/_helpers.py:291`), so confirm none of them pulls `is_atom` before deleting it.

## Verdict after two files

Both of the files most likely to block this — `specialization.py` by suspicion,
`_variables.c` by being the C core — are **mechanical**. The removal looks like a large
refactor rather than a redesign. 195 sites remain unread, so this is a strong indication and not
a conclusion.
