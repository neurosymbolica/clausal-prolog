# Python seam: classes as functors + instance ingestion (design, parked)

**Status:** DESIGN PARKED 2026-09-04 (user proposal during P3-2 ruling review;
assessed same day). Supersedes §5a's TermProxy sketch as the intended seam
answer. NOT part of P3-2 — implement as its own plan after P3-2 (preferred:
while the dispatch funnel is warm) or after P3-3; no dependency either way.

**Origin:** With R6 revised (data-functor classes stop being minted), cells
leave the engine as `("point", 1, 2)` — reconstruction into Python objects
by NAME would need a class the engine no longer owns. The user's proposal:
let PYTHON-owned classes participate directly.

## The proposal (user, 2026-09-04)

1. **Python classes as functors.** Clausal code may import a Python class;
   a term built naming that class constructs a cell with the CLASS OBJECT
   in slot 0: `(PointCls, 1, 2)`. Code using this is deliberately
   Python-aware — accepted and desirable when needed.
2. **Instance ingestion.** A Python class instance passed into the engine
   is accepted and matched against clause heads; the proposal allows
   matching "after the tuple versions have been tried", with conversion to
   the tuple form on demand (lazy).
3. **Tuple convention.** An actual `tuple` supplied from Python is read as
   Python speaking the Clausal representation (it IS a cell). Post-P3-2
   this is simply the discipline — no extra rule needed.
4. **Monotonicity options** for ingested instances: (a) convert to a cell
   at match time — a snapshot copy, so later mutation cannot affect
   reasoning (docs must state copies are reasoned over); (b) pass through
   as-is, Python owns mutation consequences; (c) per-predicate flag.
5. **OWA unaffected**: arity comes from the instance/class itself; only
   the Python side has the arity limitation, which it already owns.
6. **Motivation:** frictionless Prolog↔Python — ideally the object that
   goes in is the identity object that comes out (modulo copying).

## Assessment (recorded 2026-09-04)

- **Needs a tag-domain ruling (candidate R10).** §1b contracted slot 0 to
  `{str} ∪ {TUPLE_TAG}` and recorded "the tag domain contracts, never
  extends". This proposal reopens it to `{str} ∪ {TUPLE_TAG} ∪ {type
  objects}`. It does NOT resurrect the §1b deref/instability costs that
  justified deprecating Var functors: a class is never a Var (no deref
  added back) and cannot bind into `TUPLE_TAG` (category stays stable).
  Recognition ordering: test `slot0 is TUPLE_TAG` BEFORE
  `isinstance(slot0, type)` — TUPLE_TAG is itself a type.
- **Unification/identity**: class-functor cells unify by slot-0 identity —
  module-safe by construction (Python import scoping), the deliberate
  counterpoint to global-by-spelling str functors. Ties off the
  name-collision concern for Python-owned data: Python data keeps Python
  scoping; pure-Clausal data stays global by spelling.
- **Field protocol: use `__match_args__`**, not a naming convention — it is
  Python's own match/case field contract, dataclasses populate it
  automatically, and it is what the engine's compiled patterns already
  speak. Conversion: `(type(x), *(getattr(x, f) for f in
  type(x).__match_args__))`. Classes without `__match_args__` are not
  ingestible (clear error), only opaque args.
- **Convert at dispatch entry, not per clause arm.** Dual match arms per
  clause (tuple then instance) double codegen and raise the ordering
  question; normalizing registered-class instances to cells ONCE at the
  dispatch funnel entry subsumes "lazy on-demand conversion", costs one
  isinstance sweep per call, and first-arg indexing sees cells for free
  (no key-function changes beyond P3-2's slot-0 branch generalized to
  hashable class tags).
- **Copy semantics: snapshot-at-entry is the default** (proposal option a).
  Pass-through would embed mutable state in terms — tabling keys, index
  buckets and the trail assume immutability — engine-hostile as a default;
  if ever offered, per-predicate explicit opt-in (option c) and clearly
  documented. Docs MUST state: Clausal reasons over a copy taken at call
  time; mutation after entry is invisible to the derivation.
- **Identity out — honest limit.** "Same object out" holds only for values
  passed through unconverted and never rebuilt (walk/copy rebuilds break
  identity for every representation today). What class-as-functor actually
  buys is trivial RECONSTRUCTION: `slot0(*args)`. Python code needing
  identity should pass the object as an opaque term ARGUMENT (already
  supported — never destructured, never copied into a new shell).
- **Serialization**: class-functor cells are NOT process-portable (the
  class must import on the other side) — the exact hazard global str
  functors eliminated. Acceptable because opt-in and Python-aware by
  definition; the Scryer codec / pickling docs must say so.
- **Writer**: render `ClassName(arg1, arg2)` (module-qualified under a
  verbosity style?) — decide with the plan.
- **Egress sugar** (cell → Python object by name) deliberately NOT
  proposed: reconstruction by spelling would need a global class registry
  — the seam stays explicit (Python destructures cells, or uses
  class-functor cells whose slot 0 reconstructs).

## Interactions

- `clausal-provenance` (packages/): its `getattr(mod, name)(**kwargs)`
  reconstruction breaks for data functors at P3-2 (attribute is a str);
  THIS phase is where it migrates (to cells or to class-functor cells).
- P3-3: `call/N` over cells + qualified goals — class-functor cells in
  goal position should be ruled there (probably: not goals; goals are
  str-functor/atom only).
- `_get_dispatch` frozen protocol: dispatch-entry normalization happens
  INSIDE our funnel before clause matching; the protocol surface is
  untouched — verify when planning.

## Open sub-decisions for the implementation plan

1. R10 ratification text (tag domain reopening).
2. Registration: are ALL classes with `__match_args__` ingestible, or only
   explicitly registered/imported-into-the-module ones? (Lean: explicit —
   an `-import` of the class into the Clausal module is the registration.)
3. Snapshot depth: shallow (args as-is, nested instances converted lazily
   when they themselves hit a dispatch) vs deep at entry. Lean: shallow.
4. Per-predicate pass-through flag: offer now or never? Lean: defer.
5. Timing: after P3-2 (funnel warm) vs after P3-3 (state relocation
   landed). User to call.
