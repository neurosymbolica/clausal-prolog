# P0 census findings — PredicateMeta retirement

Instrument: `census.py`. Exit criterion: **zero unclassified**, because a site classified wrong is
a silent behaviour change.

## P0 IS COMPLETE — 0 still to read

    431 references, 50 files.  STILL TO READ: 0.

Positive-controlled rather than asserted: removing a single verdict from the table makes the
checker report 1, restoring it reports 0. A zero is the easiest number to produce by accident.

    mechanically classified   240  PROSE 128 + COMMENT 112
                               40  F-annotation
                               24  A-predicate-test (by variable name)
                                9  C-zerofield
                                5  B-term-construction
                                4  E-import
                                3  D-declaration
    human-read, 2 whole files  78  specialization.py 32 + _variables.c 41 (+5 auto)
    human-read, site by site   83  A=30 C=4 D=5 G=8 H=2 P=34

## THE TAXONOMY, final — SEVEN categories

The spec assumed two. The first census pass found five. Reading every site found seven.

    A  PREDICATE TEST     30  "is this NAME a predicate here?"  -> Database membership test
    G  TERM TEST           8  `isinstance(type(x), PredicateMeta)` -- a DIFFERENT question,
                              "is x a term INSTANCE". The functor-first-tuple path already
                              answers it natively.
    C  ATOM WIDENING       4  a zero-field class admitted as an atom VALUE
    D  DECLARATION         5  the class statement, registration, __all__, emitted AST
    H  FOREIGN IDENTITY    2  compares against ANOTHER copy of the engine's PredicateMeta
    P  PROSE              34  read, non-behavioural
    F/E/B                 49  annotations, imports, construction-by-name

**G is the category that matters most and the one the spec missed entirely.** `isinstance(x,
PredicateMeta)` asks "is x a predicate CLASS"; `isinstance(type(x), PredicateMeta)` asks "is x a
term INSTANCE". They share a spelling and mean opposite things -- the same one-stem-two-questions
trap that produced `is_atom` -> `is_zero_field_class`. Eight sites ask the second question, in
`solve.py` (6), `head_match.py`, `term_expansion.py` and `predicate.py`. **Any rewrite that treats
these as category A silently changes what the engine considers a callable goal.**

**H is the only category needing a genuinely new design.** `predicate.py:1701-1703` compares
against a FOREIGN `PredicateMeta` (`foreign.__name__ != PredicateMeta.__name__`) to detect a
double-loaded engine -- it depends on class-object identity ACROSS module copies, which is exactly
what a tuple cannot carry. It needs a replacement mechanism, not a deletion. Two sites.

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

## FINAL VERDICT: the removal is MECHANICAL, with two named exceptions

Every one of the 431 references is accounted for. **No site blocks the removal.** In particular
the two candidates for blocking it do not:

* `specialization.py` needs only name + arity + row, all of which `Database.row()` provides
* `_variables.c` is **already polymorphic** over term representations (PredicateMeta instance,
  then a `__dataclass_fields__` fallback), so removing one is in-pattern

**The two exceptions, both small and both now identified rather than latent:**

1. **Category G, 8 sites** — the term test. Must be rewritten as a tuple test, NOT folded into the
   predicate test. Mistaking them changes what counts as a callable goal.
2. **Category H, 2 sites** — the foreign-engine-identity diagnostic. Needs a new mechanism; class
   identity across module copies has no tuple equivalent.

**And one decision the plan must now make explicitly:** category C's 4 sites admit a zero-field
class as an atom VALUE, which `predicate.py:1617` documents as deliberate (a zero-arity class is a
"declared atom"). Declared atoms need a tuple spelling and a migration path before the class can
go.

P1 of the spec — routing straight to `Database.row()` — is now unblocked and its work queue is the
30 category-A sites.

---

# Spec P1 prerequisite — WHICH Database call replaces the isinstance test

Settled before touching any of the 30 category-A sites, because the obvious answer is wrong.

    db.is_defined(functor, arity)        "any clause has been asserted"    STRICTER -- WRONG
    db.row(functor, arity) is not None   "a row exists for it"             EQUIVALENT -- USE THIS

Measured:

    predicate                        isinstance  is_defined  row is not None  is_dynamic
    has_clauses/1                    True        True        True             False
    declared_empty/1 (dynamic, no    True        FALSE       True             True
      clauses)

`compiler_v2.py:958` deliberately *"Creates empty PredicateMeta classes (no clauses, no
dispatch)"*, so `isinstance` is True for declared-but-empty predicates. **Rerouting to
`is_defined` would have silently un-declared every dynamic-but-unasserted predicate** — across 30
sites, found only by a behaviour change downstream.

`row(create=False)` also correctly returns None for an unknown predicate, so the test does not
answer True for everything the moment it is asked.

Pinned by `tests/predmeta_p1/test_membership_equivalence.py`, including a negative control that
fails if `is_defined` ever changes meaning.

## And a wrong turn worth recording

The module's Database is reached through **`module_dict["$module"].db`**. Reaching for it instead
via any predicate's `_row.db` yields a DIFFERENT Database, which reports `is_defined=False` even
for a predicate that demonstrably has clauses. The first measurement here did exactly that and
produced a self-contradictory table — a predicate with a clause reporting undefined. **That the
table contradicted itself is the only reason the wrong db was noticed**; had both rows read
False-but-plausible it would have been recorded as a finding about the engine.

## P1's mechanical rule, and the part that is not mechanical

    isinstance(module_dict.get(functor), PredicateMeta)  ->  db.row(functor, arity) is not None

**The obstacle is arity.** Several category-A sites have a functor in hand but no arity — the
isinstance test needed none. Those sites need either the arity threaded to them or a
functor-only membership query on Database (which does not exist yet: every accessor is keyed
`(functor, arity)`). That is the real design work in P1, and it should be decided once rather than
per site.
