# Retire the per-predicate class: terms are tuples, predicates are Database rows

**Date** 2026-09-14 · **Status** DESIGN, not approved. Nothing started.

**The question that produced this, and the answer.** Asked what a generic `Predicate` type
would do once terms are functor-first tuples. **Nothing.** It would be a third facade over a
store that is already keyed by `(functor, arity)`. The proposal is not "replace the metaclass
with a lighter class" — it is **remove the layer**.

## 1. What exists today, measured

`PredicateMeta` (`clausal/logic/predicate.py:689`) is a metaclass that, per predicate, generates
`__init__`, `__eq__`, `__repr__`, `__unify__`, `__occurs_check__`, `__iter__`,
`__match_args__`, `__slots__` and a fast constructor — each a function with its own code object.

**The state it appears to hold is not its own.** Its docstring: `_clauses`, `_dispatch_fn`,
`_lazy_recompile`, `_signature`, `_locked`, `_clauses_source`, `_dynamic_arities` are
*"READ-THROUGH PROPERTIES onto one `PredRow` held in `cls._row`"*. And `PredRow`
(`database.py:81`) describes itself as *"a THIN READ-THROUGH FACADE over the Database's existing
storage, not a second parallel store."*

`Database` (`database.py:467`) is the actual store, and it is keyed exactly as a Prolog engine
would key it:

    _clauses / _signatures / _dispatch / _lazy_recompile : dict[(str, int), ...]
    _dynamic / _discontiguous / _tabled / _shallow       : set[(str, int)]
    _rows                                                : dict[(str, int), PredRow]
    module_dict                                          : the module dict, held BY the Database

**So the chain is: name -> class -> row -> Database.** Two facades over a dict.

Every consumer goes through the whole chain for routing only. `compiler_v2.py:233,275,283,711`
all do `pred_cls = module_dict.get(functor)`, check `isinstance(pred_cls, PredicateMeta)`, and
then read or write a read-through property. **`db` is already in scope at those sites** — e.g.
`_load_gate(db, functor, arity, ...)` on the very next line.

## 2. The cost, measured 2026-09-14

    per class, shallow                     944 B
    per class, deep (methods + code)       6.2 - 8.2 KB
    classes live after importing ONE
      3-predicate module                   487        <-- ~484 are the engine's own
    => fixed cost before any user code     ~3.4 MB, growing ~7-8 KB per predicate

**And the per-class generation is not a speed feature. It is a speed cost.**

    construct: class instance     809 ns/op        construct: tuple     35 ns/op    23x
    unify:     class instances    678 ns/op        unify:     tuple    145 ns/op   4.7x

The C `do_unify` has a native functor-first-tuple path; the class path detours through the
generated Python-level `__unify__`. Verified that the native path is complete:
`unify(('f',1,X), ('f',1,2))` binds `X = 2` and correctly fails on a mismatch.

(Measured on GROUND construct-and-unify. A real workload has variables and backtracking so the
multipliers will differ — but 23x and 4.7x are too large to be artefacts, and the ~3.4 MB fixed
cost is not workload-dependent at all.)

**One honest counterpoint:** a `__slots__` instance is 48 B against a tuple's 64 B, so per-term
*memory* slightly favours the class. It is swamped by the per-class fixed cost and by the
construct/unify gap.


## 2a. How much goes away — measured 2026-09-14

**Deleted outright, ~1,450-1,650 lines:**

    predicate.py                          1772 lines total
      class PredicateMeta (689-1398)       710   the layer itself
      generated-method factories           ~250  _make_init/_fast_new/_eq/_unify/
        (344-620)                                _occurs_check/_repr/_term_iter,
                                                 _make_instance_state_property
      construction-error machinery         ~178  ClausalTermConstructionError and
        (166-343)                                friends -- they exist because a
                                                 class ctor can be called with wrong
                                                 NAMED fields; tuples cannot be
      class-shaped helpers                 ~150  _dispatch_at, _is_term_instance_py,
        (1399-1530, 1642-1659, 1723-1736)        _is_zero_field_class_py,
                                                 _term_field_names_py,
                                                 term_field_names_of_class,
                                                 _class_origin, make_predicate
      ----                                 ----
      subtotal                            ~1288  ~73% of the file

    database.py PredRow (81-366)           ~286   the MIDDLE facade; goes if routing
                                                  is direct to Database

**Rewritten, not deleted: 435 reference lines across 52 modules**, and they are concentrated —
`predicate.py` 50, `_variables.c` **46**, `specialization.py` 32, `compiler_v2.py` 32,
`solve.py` 23, `term_rewriting.py` 20, `database.py` 16, `terms_to_ast.py` 16. Those eight hold
~235 of the 435; the remaining ~200 are spread over 44 modules.

**`_variables.c`'s 46 references are the unmeasured part of this estimate.** The C core
special-cases predicate instances in its unify/deref/compare paths. Since the native
functor-first-tuple path already exists and is faster, much of that special-casing should be
DELETABLE rather than rewritten — but I have not read those 46 sites, so they are not counted in
the subtotal above. The true deletion figure is likely higher than 1,650, not lower.

**Generated code shrinks too, and this is the invisible half.** Every predicate in every module
currently emits a ~10-line `try/except NameError/class` guard into its transformed AST. The engine's
own stdlib alone accounts for ~484 predicate classes at import, i.e. roughly 4,800 lines of
generated guard before any user code, and every corpus module carries its own share. That is
bytecode, not source, so it does not appear in a line count — but it is why the fixed cost is
~3.4 MB.

**What survives in predicate.py** (~480 lines): the source-site/clause-provenance helpers
(`module_source_path`, `record_clause_source`, `_source_site`, `_format_site`), the term
accessors that need REWRITING for tuples rather than deleting (`term_field_values`,
`term_field_dict`), `is_atom_value`, `make_atom`, the identity-mismatch diagnostics, and the
name predicates (`_is_logic_var_name`, `_camel_case`).

**Caveat on the range.** The subtotal is a line census by region, not a dependency analysis. Some
of the ~150 "class-shaped helpers" may have non-class callers that need a replacement rather than
a deletion; §6 P0 is what would find that out.

## 3. What the layer actually provides, and what replaces each part

| role today | replacement |
| --- | --- |
| clause/dispatch state | **already** the `Database`, keyed `(functor, arity)`. No work. |
| routing: name -> row | **`Database.row(functor, arity, create=False)` ALREADY EXISTS** (`database.py:483`) — this is not a new API to design. `db` is already in scope at every call site. |
| "is this name a predicate here?" | a `Database` membership test, not `isinstance(x, PredicateMeta)`. |
| term construction / unification | functor-first tuples, with the existing C path. Faster and no per-predicate cost. |
| Python ergonomics (ctor, `.arg_0`, `__match_args__`) | **not needed.** The seam works both ways: terms go in, and terms that come out are compared against `--/2`-defined term expressions in the Python seam. |

That last row is the one that changes the conclusion from "make it cheaper" to "remove it".

## 4. THE REAL OPEN QUESTION: what binds at module level?

Clause lookup goes by the functor in argument 0 of the tuple, so a predicate needs no
module-level Python object *to be called*. But `module_dict` is the name-resolution environment
for the whole compile (~102 touchpoints in `compiler_v2`), and these still need an answer:

1. **`-import_from(m, [p])`** — with no module-level object to alias, importing `p` must make
   this module's calls to `p/N` resolve to the OTHER module's rows. Delegation in the Database, a
   per-module alias table, or a shared row — pick one and say which.
2. **`-module(m, [p, ...])` export lists** — currently a Python name is exported. With rows, the
   export is a `(functor, arity)` set.
3. **A bare name in Python-facing code.** `m.some_pred` is presently a class. After the change it
   is either absent, or the atom `('some_pred',)`. **This is the compatibility cliff**, and it is
   the one place the seam boundary genuinely notices.
4. **`isinstance(x, PredicateMeta)` as a type test** appears across 52 modules, and the
   references are CONCENTRATED, not spread thin: `specialization.py` alone has 32,
   `_tabling_core.c` 3, `goal_expansion.py` 1. Specialization is therefore the module to read
   first — if anything holds an assumption beyond routing, it is most likely there. Each site is
   asking one of two different questions — "is this a predicate?" or "is this a term?" — and they
   must be separated before they can be rewritten. This is the same
   one-stem-two-questions confusion that produced `predicate.is_atom` ->
   `is_zero_field_class` during THE FLIP.

## 5. Sequencing — do NOT fold this into L3

`implementation_plans/clausal-iso-to-transformed-ast-2026-09-14.md` rests on L3 lowering to the
SAME transformed AST the seam produces, so that everything downstream is shared and unmodified and
the differential harness means something. **If the representation changes at the same time, a
lowering bug and a representation bug are indistinguishable** — the precise failure §8 of that
plan is built to prevent.

So: L3 targets today's AST and proves the front end. Then this change moves BOTH front ends at
once, with L3's own differential harness as one of the controls.

## 6. Phases

* **P0 — separate the two questions.** Census the 52 `PredicateMeta`-referencing modules and
  classify every `isinstance` site as *predicate test* or *term test* (§4.4). Exit: every site
  labelled; no rewriting yet. **This is the risk-bearing phase**, because a mislabelled site is a
  silent behaviour change.
* **P1 — route directly to the Database.** Replace `module_dict.get(functor)` -> class -> row with
  `db.row(functor, arity)` at the compiler sites. No representation change yet; the classes still
  exist. Exit: the class is no longer on the routing path.
* **P2 — terms become tuples in argument position.** The narrow, high-value half: arguments are
  data, the C path already handles them.
* **P3 — goal position.** Goals are compiled with their surrounding bodies, or interpreted; either
  way tuples.
* **P4 — delete the metaclass** and answer §4's module-level binding question.

## 7. Verification

* **A/B the same downstream domain under both representations, comparing ANSWER SETS** — not pass/fail
  counts. A wrongly-lowered clause commonly leaves a domain passing with fewer solutions.
* **Assert which representation ran.** A run that silently used the old path and reported
  "identical" is the failure this exists to catch; it has already happened once in the L3 work,
  caught only because the harness asserted the front end had executed.
* **Memory and speed as exit criteria, not hopes**: report the class count and the fixed cost
  before and after, and re-run the construct/unify benchmark in §2 rather than trusting it.
* **A negative control per phase.**

## 8. Not established

* whether any `isinstance(x, PredicateMeta)` site depends on *class identity* rather than on the
  predicate/term question — §6 P0 exists to find out
* the cost of `__match_args__` loss to any Python code doing structural pattern matching on terms
* whether the tabling, specialization and goal-expansion paths (`_tabling_core.c`,
  `specialization.py`, `goal_expansion.py` all reference `PredicateMeta`) hold assumptions beyond
  routing
* the real-workload multipliers, as against §2's ground-term microbenchmark
