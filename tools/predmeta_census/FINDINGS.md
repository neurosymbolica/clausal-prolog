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

## CORRECTION to the P0 verdicts — A=26, C=8 (was 30/4)

Reading the ENCLOSING FUNCTIONS of the category-A sites reclassified four of them, and there is a
mechanical rule behind it that the census now enforces:

    isinstance(x, type) and isinstance(x, PredicateMeta)   ->  x IS a class, i.e. a bare
                                                               predicate-class used AS AN ATOM.
                                                               Category C.
    isinstance(x, PredicateMeta) on a name lookup          ->  membership. Category A.

Mis-verdicted A before the rule existed: `arg_index.py:180`, `arg_index.py:378`,
`terms_to_ast.py:110`, `head_match.py:846`. `arg_index.py:378` returns `(a.__name__, 0)` under a
comment reading "PredicateMeta atom" — it is indexing a class AS a zero-arity atom.

**Rerouting those four to a Database membership query would have turned an ATOM test into a
PREDICATE test.** They belong with the declared-atom decision, not with P1.

**What this says about the census's value.** P0 classified from the LINE; reading the enclosing
function changed the verdict for 4 of 83 (~5%). The enumeration and the exit criterion are the
durable parts; a line-level verdict is a hypothesis until the function around it is read. The rule
above is now mechanical, so this particular mistake cannot recur.

## P1 design: how the 26 A sites reach a Database

Measured across all 26:

    17  reach a dict (module_dict / namespace / env)  -> db via module_dict["$module"].db
     6  have db in scope already
     8  NEITHER

**So 23 of 26 need no signature change** — the Database is reachable through the module dict they
already hold. That settles the question the prerequisite note left open: **do NOT thread `db`
through signatures, and do NOT add a functor-only query.** Reach it where it already is.

The 8 without either need individual treatment and are listed here so they are not discovered one
at a time:

    import_diagnostics.py:201   io.py:589   io.py:735   predicate.py:1425
    terms_to_ast.py:1245        _lower_goalop_shared.py:129   inspection.py:317
    term_rewriting.py:4236

Two of those are suspect as category A at all: `term_rewriting.py:4236` is inside the EMITTED
guard (arguably category D), and `predicate.py:1425` is in `_dispatch_at`, which is part of the
layer being deleted rather than a caller of it. **Re-read those two before rerouting them.**

## Arity, the question that turned out not to be the obstacle

The prerequisite note flagged arity as P1's real design work. Measured, it is not: the obstacle was
reaching a Database at all, and that is solved for 23 of 26. Arity remains a per-site detail —
present at most sites, and where absent the site is usually resolving an import spec that carries
`name/arity` anyway.

## CORRECTION: "23 of 26 are mechanical" is TOO OPTIMISTIC

Reaching a Database is solved for 23 of 26. **That is necessary and not sufficient**, and two
sites read in detail show the A category decomposes further:

**1. Some are SIMPLIFICATIONS, not reroutes — better than expected.**
`compiler_v2.py:233` passes `pred_cls` into `_load_gate(db, functor, arity, author, kind,
pred_cls, origins, module_name, module_dict)` — which **already receives `db`, `functor` AND
`arity`**. The class is redundant information the gate could derive itself. So this site's fix is
to stop passing it, not to reroute a test. Check the gate's use of it for the
import-redefinition DIAGNOSTIC first: that is what `pred_cls` is there for.

**2. Some need the functor-only query the design note said we would not need.**
`compiler_v2.py:1717`: `not isinstance(module_dict.get(entry), PredicateMeta) and entry not in
_module_constants(module_dict)` -> then bind `entry` as an ATOM. `entry` comes from a declaration
list and **has no arity** — the question is "is this name a predicate at ANY arity?"
`db.row(functor, arity)` cannot answer that.

**3. And that same site is really blocked on spec §4, not on P1.** It asks whether a
module-level NAME is bound to a predicate. Under the new design a predicate may not bind a
module-level name at all — that is exactly §4's open question ("what binds at module level?"). So
its logic changes with §4's answer, not with a reroute.

### Revised P1 shape

    26 category-A sites
      -> reroute to db.row(f, a) is not None        the straightforward ones
      -> SIMPLIFY: stop passing a redundant class   where db+functor+arity already flow
      -> needs a functor-only membership query      where no arity exists (declaration lists)
      -> BLOCKED on spec §4                         where the question is about module binding

**The per-site split is not yet done.** It needs one pass reading each of the 26 in its enclosing
function — the same discipline that corrected 4 of 83 P0 verdicts, applied to the 26. Do that
before editing anything: the sites look alike at line level and are not alike.

**And add a functor-only membership query to Database** (`has_any_arity(functor)`), since the
declaration-list sites cannot be served without one. That reverses the design note's "do not add
a functor-only query", which was concluded from the 23-of-26 reachability figure before any site
was read in full.

---

# P1 PER-SITE PASS — all category-A sites read in their enclosing functions

The step the previous handoff marked "do not skip". Done. The table is
`P1_SITES.tsv`, machine-checked by `check_p1.py` (six controls, each watched
going red). Every claim below is measured.

## The headline: the A population is 50, not 26

    census VERDICTS, A               26   human-read, site by site, at P0
    census "A-predicate-test"        24   classified MECHANICALLY, from the
                                          VARIABLE NAME, and never read
    overlap                           0
    -------------------------------------
    category A, actual               50

P0's own summary contains both numbers — `24 A-predicate-test (by variable
name)` in the mechanical block, `A=30` (later 26) in the human block — and the
final taxonomy carried only the second forward. Every downstream statement of
the work queue ("the 30 category-A sites", "the 26", "23 of 26 are mechanical")
was therefore counting half the population. **`check_p1.py` now computes the
union from the census and fails if the table disagrees, so the two cannot drift
again.**

The mechanical rule was `isinstance\(\s*(pred_cls|pred_obj|cls|mi_cls|owner)\s*,
\s*PredicateMeta` — a regex over the SUBJECT'S NAME. `cls` is in that list, and
`cls = type(x)` is the category-G spelling.

## 14 of the 50 are not category A at all

Reading each site in its enclosing function reclassified 14:

    G  term test          5   the subject is a TYPE, so the question is
                              "is x a term INSTANCE", not "is this NAME a predicate"
    C  class-as-atom      3   (+1 C/G union)
    B  construction       2   the class is CALLED to build a term
    D  emitted code       2   inside a docstring showing the generated guard
    LAYER                 1   part of the machinery being deleted, not a caller

    mis-verdicted, human-read at P0     9 of 26   (34%)
    mis-verdicted, auto by var name     5 of 24   (20%)

**The category-G misses are the ones that matter**, for exactly the reason P0
recorded: treating them as A changes what the engine considers a callable goal.
P0 found eight G sites by their literal spelling `isinstance(type(x),
PredicateMeta)`. Five more hoist the `type()` into a local first:

    database_ops.py:280    own = type(head)   -> isinstance(own, PredicateMeta)
    io.py:735              val = type(val)    -> isinstance(val, PredicateMeta)
    terms_to_ast.py:549    cls = type(term)
    terms_to_ast.py:1133   cls = type(term)
    predicate.py:1500      cls = type(obj)
    predicate.py:1688      cls = type(obj)    (gates the category-H diagnostic)

A sixth, `predicate.py:1524`, splits `isinstance(cls, type)` and the
`PredicateMeta` test into two separate `if` statements, so P0's one-line C rule
could not see it either.

**The lesson generalises P0's own.** P0 concluded that a line-level verdict is a
hypothesis until the enclosing function is read. It is narrower than that: these
verdicts were defeated by a LOCAL VARIABLE one line up. The rule has to be
applied to the DATAFLOW, not to the line — and where it was applied to a
variable NAME instead, one in five verdicts was wrong.

## The P1 mechanical rule has a documented counter-example

    isinstance(module_dict.get(functor), PredicateMeta) -> db.row(functor, arity) is not None

`globals_env.py:550` (`_maybe_cache_dispatch`) is exactly that shape — `obj`
comes from `base_globals.get(target_name)` — and its docstring rules the
rewrite out in advance:

> *"The row is the CLASS's own (``obj._row``), not ``db.row(name, arity)``: the
> call site this key serves resolves to THIS class, so it is this class's row
> whose dispatch may be baked under the key. A same-named predicate in the
> compiling module's own Database is a different predicate, and baking its
> dispatch here would silently redirect the call to it."*

So the rule is not universal, and the exception is not exotic: it is the
ordinary case of two modules owning same-named predicates. One site in 50 is
marked `NO`; the value of the pass is that it was found by reading rather than
by a redirected call in a corpus run.

## The class holds state that the spec says it does not

The spec's argument for removal is that `PredicateMeta`'s state "is not its
own" — read-through onto a `PredRow`. Measured on a real compiled predicate
(`classonly.py` probe, controls included), that is true of nine attributes and
false of six:

    read-through onto the row   _clauses _clauses_source _dispatch_fn
                                _dynamic_arities _lazy_recompile _locked
                                _signature  (+ _arity _functor as properties)

    CLASS-ONLY, no row home     _fields
                                _index_plans
                                _index_plans_joint
                                _index_plans_hierarchical
                                _registered_at
                                _tabled_home_db
                                _te_predicate_nodes   (set only when term
                                                       expansion runs)

`_registered_at` was found by the probe, not at any call site.

**Two of these are cross-module CARRIERS, and that is the load-bearing part.**
`_tabled_home_db` (`database.py:974`) and `_te_predicate_nodes`
(`term_expansion.py:107,160`) are stamped on the class precisely so state
travels across `-import_from`, because the class object is shared between the
exporter and the importer while a row belongs to one Database. `io.py:589`'s
docstring records the same dependency as a fixed bug — *"the class knows its own
row; the name does not"* — and `database_ops.py:280` tests it directly with
`any(v is own for v in module_dict.values())`.

So spec §4 question 1 (`-import_from`: delegation, alias table, or shared row)
is not one open question among four. **It is the question 10 of the 50 sites are
waiting on**, and the index plans plus `_registered_at` need a home before P4
can delete anything.

## Dispositions

    R       11   reroute to db.row(functor, arity) is not None
    R!       4   same, but the site does NOT check arity today, so the reroute
                 TIGHTENS an arity-blind test -- a behaviour change, not a
                 refactor (goal_trampoline 150/265, call_site 85/206: all four
                 compute `arity` and then look up by name alone)
    R-enum   1   rewrite to enumerate the Database's rows
    S        3   simplify: a redundant type test on an already-resolved value
    Q        3   needs functor-only resolution; no arity exists at the site
    X4      10   blocked on spec §4
    X4+Q     3   both
    NO       1   documented in-tree as wrong to reroute
    ---------------------------------------------------------------
    stays A 36     actionable now (R/R!/R-enum/S) 19
    reclassified 14   blocked or needs new API (Q/X4/X4+Q/NO) 17

Four of the R sites are one idiom copied four times
(`compiler/predicate.py:900,1025,1734,1849`): *"resolve pred_cls by name if not
passed"*. They should become one helper, not four edits.

## What this changes about the plan

1. **`Database.has_any_arity(functor)` is still needed** (the Q sites), but the
   declaration-list sites that motivated it — `compiler_v2.py:1717,1756` — are
   ALSO §4-blocked, and 1756 cannot be served by a functor-only query on this
   db at all: an imported re-export's clauses live on the exporter's. Add the
   query for the specialization sites (969, 1004, 1044); do not expect it to
   unblock the declaration lists.
2. **P1 is 19 sites, not 26 or 50**, and 4 of the 19 change behaviour.
3. **Spec §4 should be answered before, not after, P1's remaining half.**
4. **`predicate.py:1425` is the `_get_dispatch` funnel** — a duck-typed protocol
   with out-of-tree implementors and a frozen signature. It is inside the layer
   being deleted, so P4 breaks an external contract. Not in P1's scope, but it
   belongs in the spec's "not established" list and is not there.

## X4 / X4+Q / Q refresh, 2026-09-17 (after adoption landed on canonical 38d3cb32)

The 13 X4/X4+Q rows and 3 Q rows were re-read against what the Database answers TODAY, measured
on a two-module probe (exporter `edge/2`, `-table(path/2)`; importer `-import_from(expmod,
[edge, alias(path, route)])`):

    importer.row('edge', 2)  is exporter.row('edge', 2)      True   (adoption, plain)
    importer.row('route', 2) is exporter.row('path', 2)      True   (adoption, aliased)
    importer.row('path', 2)                                  None   (original name NOT adopted)
    importer.owns('edge', 2) / exporter.owns('edge', 2)      False / True
    importer.arities_for('edge'), ('route')                  set(), set()   <-- GAP: ignores _adopted
    'edge', 'route' in importer.functors()                   True, True
    importer.row('route', 2).db is exporter db               True; its module_dict has $module + __file__
    importer.row('route', 2).db.is_tabled('path', 2)         True   (the class stamp is redundant)
    importer.signature_for('route', 2)                        None   <-- same GAP (row.signature answers)
    alias class .__name__                                    'path'

Dispositions after (column 4 of P1_SITES.tsv; each note starts "REFRESH 2026-09-17"):

    X4 10, X4+Q 3, Q 3   ->   R 8 (+ 3 = 11 R total), P4 8 (+3 = 11), Q 2, X4 0, X4+Q 0

* R (8): import_diagnostics 201 + predicate_diagnostics 194 (`owns` IS the `__module__` filter);
  database.py 1076 (`_tabled_home_db` redundant, readers tabled_naf.py:45 / tabling.py:863 take
  `db.row(f, a).db`); io.py 589 (adoption fixes the docstring's bug; class arm -> fallback);
  term_expansion 107/160 (the shared row carries a `te_predicate_nodes` field -- the field is the
  prerequisite); testing.py 2199 (defining module = `row.db.module_dict`); compiler_v2 1091
  (error path, `functors()`).
* P4 (8): compiler_v2 745/779/812 -- the gate's `through=` leg is the class carrier's residue,
  needed ONLY for an aliased import whose clause head spells the original name (reachable only via
  the class's `__name__`); 1056/1141 -- the specializer's PRODUCT is a class; terms_to_ast 1024 --
  R6 is the binding-shape rule, i.e. the retirement design point itself.
* Q (2): compiler_v2 1814 (imports precede declarations, so adopted names are visible; a LOCAL
  predicate's row at that step is the unmeasured half) and 1853 (blocked on the `arities_for` gap).

The gap is filed: `todo/arities-for-and-signature-for-ignore-adopted-rows-2026-09-17.md` (clone).
