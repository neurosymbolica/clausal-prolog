# Spec §4 answered: what binds at module level

**Date** 2026-09-14 · **Status** ANSWER, for the operator's ruling. Nothing implemented.
Companion to `2026-09-14-retire-predicatemeta-design.md` §4 and to
`tools/predmeta_census/P1_SITES.tsv`.

Everything below is measured on the built tree unless marked *(judgement)*. The probes are
`tools/predmeta_census/` — `import_probe.py`, `export_probe.py`, `sharedrow_probe.py`,
`classonly_probe.py` — each with its controls.

---

## 0. The fact the whole question turns on

**`-import_from` is `getattr`.** `compiler_v2._process_imports` does
`value = getattr(mod, name); module_dict[local] = value`. Measured end to end:

    importer.edge IS exporter.edge              True    the SAME class object
    importer's db row('edge', 2)                None    the importing Database
    importer's db dispatch for edge/2           None      knows NOTHING about it
    importer.edge._row.db is exporter's db      True
    two_hop answers                             [(1, 3)]  -- and it works

    aliased: aliaser.link IS exporter.edge      True
             aliaser.link.__name__              'edge'   the class keeps ITS name
             'edge' bound in aliaser?           False
             aliaser's db row('edge'|'link', 2) None, None

**The importing Database has no representation of an imported predicate at all.** The entire
import relationship exists as one Python object reference in `module_dict`.

So §4 is not "which of three mechanisms do we reroute to". There is nothing to reroute to: the
relationship must be *created* in the Database, because today it does not live there. That also
explains every cross-module oddity the P1 pass found — `_tabled_home_db`, `_te_predicate_nodes`,
`_import_from_origins`' double indexing, `io.py:589`'s *"the class knows its own row; the name
does not"*. They are all the same workaround for the same absence.

---

## 1. Answer to q1 — `-import_from`: **a shared row**, planted in the importer's table

Of the spec's three options (delegation in the Database, a per-module alias table, a shared row),
take **the shared row**, keyed by the IMPORTER's local spelling:

    importer_db._rows[(local_name, arity)] = exporter_db.row(functor, arity)

**Measured feasible today, with controls** (`sharedrow_probe.py`): before planting, the importer's
db returns `None` for the key; after planting, `idb.row('edge', 2)` returns the exporter's row,
its 2 clauses and its dispatch are reachable through the importer, an unplanted key stays `None`,
and `is_defined` still reports on the importer's OWN storage — so P0's row-exists/is-defined
distinction survives intact. `Database.row()` consults `self._rows` first, so this is a key
insert, not new machinery.

Four things fall out, and they are the argument for this option over the other two:

1. **The alias problem disappears.** Today the carrier is an object with an intrinsic name, so
   `alias(edge, link)` binds a class under `link` whose `__name__` is still `edge`, a clause head
   compiles to the CLASS's functor, and `_import_from_origins` has to index under both spellings
   to stop an aliased write clobbering the exporter (its docstring records that as a live bug found
   by review). A key→row map has no intrinsic name: the importer's key IS `link`, and the question
   never arises.
2. **`row.db is not self` becomes the ownership test**, measured working. That is exactly what
   `_belongs_elsewhere(pred_cls, db)` computes today by asking the class, and what the mutation
   gate wants when it is handed `through=pred_cls`.
3. **Every class-only attribute gets a row home**, and one of them is deleted outright:

        _tabled_home_db              DELETED -- a row already knows its own db (row.db)
        _te_predicate_nodes          -> row field; travels because the row is shared
        _index_plans (+_joint,       -> row fields, beside `dispatch_fn` and `backend`,
          +_hierarchical)               which is where the compile that produces them already puts its output
        _registered_at               -> row field (`source` already exists)
        _fields                      -> the signature; arity is in the key, names become metadata

4. **`globals_env.py:550`'s objection changes shape** *(judgement)*. Its docstring refuses
   `db.row(name, arity)` because "a same-named predicate in the compiling module's own Database is
   a different predicate". Under a planted import, the importer's db is by construction the
   authority on what the local name means. The conflict does not vanish — a module that imports
   `p/2` and also defines its own `p/2` is still a conflict — but it moves from *two answers at
   every lookup* to *one decision at load time*, which is where it belongs. **This site should be
   re-read after q1 lands rather than rewritten on the strength of this paragraph.**

Rejected: *delegation* (a `parent` pointer on Database) makes every lookup a chain walk and gives
the alias no place to live. A *per-module alias table* is a second store keyed the same way as
`_rows`, i.e. the thing `PredRow`'s own docstring says not to build.

## 2. Answer to q2 — export lists: record the `(functor, arity)` set, keep it ADVISORY

**Measured: the `-module` export list is not enforced today.** A name that is `-private` and absent
from the export list is still importable by `-import_from`, and answers
(`export_probe.py`). It cannot be enforced while import is `getattr`, because `getattr` bypasses
every list the compiler holds.

So converting exports to a `(functor, arity)` set is not a translation of an enforced thing. Record
the set on the Module, change nothing about enforcement in this work, and note that enforcement
becomes *possible* for the first time — the plant step in q1 is the natural chokepoint. **Whether
to enforce is a separate ruling and should not ride along with the representation change**, because
it would turn a silent success into a load error across an unmeasured corpus.

## 3. Answer to q3 — a bare `m.some_pred` from Python: the compatibility cliff

Measured in the engine's own tests, three access shapes:

    330 occurrences / 35 files   name + arity  (_call_collect("edge", 1, x, module=lm),
                                                db.is_dynamic("color", 2), ...)
    169 occurrences / 18 files   module_dict subscript  md["edge"]
     40 occurrences / 23 files   getattr(mod, "edge")

**The dominant in-tree idiom is already name+arity**, which is the shape the new design wants; the
object-shaped access is 209 occurrences. *The corpus side is NOT measured and is the real risk.*

From Python the class does exactly two things: it is **called as a goal**, and it is **called as a
term constructor** (`owner.public_pred(1)` → `public_pred(arg_0=1)`, which unifies).

Recommendation *(judgement)*: **bind the atom `('some_pred',)`, and provide ONE generic callable
handle for the seam** — not a per-predicate class. A single `PredicateRef(db, functor)` costs
nothing per predicate (the ~3.4 MB fixed cost was ~484 generated classes, not one), keeps
`m.p(1)` and `for _ in m.p(X)` working, and is what the seam is *for* now that §0.6 repositions it
as the adaptor layer.

This is a refinement of the spec's own answer, not a contradiction of it. The spec asked what a
generic `Predicate` type would do once terms are tuples and answered "nothing" — correct about its
role as a *facade over state*, which is the layer being removed. As the *module-level binding* it
has one job left, and §4 q3 is the evidence that the job exists.

**And binding the atom resolves two P1 sites by removing their question.** `compiler_v2.py:1717`
asks "does a predicate already own this module-level NAME?" before binding the atom into the same
slot; `1756` is its sibling. If a predicate never binds the name, the name always holds the atom
and the don't-clobber guard is deleted rather than rewritten. **Those two sites therefore do not
need `Database.has_any_arity(functor)`** — which was the query they were the motivation for.

## 4. Answer to q4 — the type test

Answered by P0 and the P1 per-site pass, not here. 431 references classified; category A is 50
sites, of which 14 are not A at all; dispositions in `tools/predmeta_census/P1_SITES.tsv`, checked
by `check_p1.py`. The one substantive addition: five category-G sites hoist `type(x)` into a local,
so the separation of "is this a predicate" from "is this a term" must be done on the DATAFLOW, not
on the line.

---

## 5. What this changes about sequencing

    q1 (shared row) is a PREREQUISITE, not a parallel task.

10 of the 50 P1 sites are waiting on it; it deletes `_tabled_home_db`; it gives the other
class-only state a home; and it is what makes `db.row(functor, arity)` a correct answer to "what
does this name mean here" — which is the premise P1's whole reroute rests on. **Doing P1's reroutes
first would be rerouting onto a Database that does not yet know about imports**, i.e. onto the
exact gap `io.py:589` documents as a fixed bug.

Revised order:

    1. q1: plant shared rows at import; `row.db is not self` replaces `_belongs_elsewhere`.
       Gate: the aliased-import clobber tests, and an answer-set run over a corpus domain.
    2. q3: bind the atom + one generic PredicateRef; migrate the 209 in-tree object-shaped
       accesses. MEASURE THE CORPUS FIRST -- this is the only step with an unmeasured blast radius.
    3. P1's 19 actionable sites, now that db.row means what the reroute assumes.
    4. q2: record export sets. No enforcement.
    5. P2+ as the spec has them.

## 6. Not established

* the corpus's object-shaped predicate access (§3) — the one unmeasured number in this document,
  and the one that decides whether q3 is a migration or a flag day
* whether any module both imports and locally defines the same `(functor, arity)`, which is the
  conflict q1 moves to load time
* what a shared row does to `Database.mutate`'s blast radius and to `abolish_table` — the gate
  gets *better* information, but its policy was written against `through=pred_cls`
* `predicate.py:1425` — the `_get_dispatch` funnel is a duck-typed protocol with out-of-tree
  implementors and a frozen signature. Deleting the layer breaks an external contract; it is not
  in the spec's "not established" list and should be.

---

# REVISION, after the operator's direction of 2026-09-14

The operator settled the representation question directly: **functor-first tuples are the main
representation** (S-expressions), **atom 1-tuples discriminate atoms from strings in argument
position** and match real atoms in shape, `PredicateMeta` goes because "Prolog needs immutable
compounds — the only things that change are vars", and tuples are immutable with CPython fast
paths. Three consequences below are measured, and one of them **retracts a recommendation I made
above**.

## R1. q3's "generic callable handle" is RETRACTED — the seam already speaks tuples

I recommended binding the atom *plus one generic callable handle*, reasoning that Python still
needs to call and construct. **Measured wrong**: the goal-position seam already does both, in the
target representation, with no module-level predicate object anywhere.

From `tests/test_goal_position_seam.py`, running today:

    goal = ("decide", ("large",), ("verdict", S, IDS))       # functor-first; atoms are 1-tuples
    once_bind(goal, mod.__dict__) is True
    export(S) == ("prohibited",)  and  export(IDS) == [("r1",)]
    list(each(goal, (S, IDS), mod.__dict__)) ==
        [(("prohibited",), [("r1",)]), (("prohibited",), [("r2",)])]

and `once_bind` resolves through `module_globals["$module"]` — the LogicModule and its db — not
through a module-level binding. `if --goal(X):` and `for a, b in --goal(A, B):` lower to exactly
this, exporting the answers as ordinary Python locals.

**So the calling convention is `--`, not `m.some_pred`.** The module-level name should be the atom
`('some_pred',)` and nothing else, which is the spec's original position; my counter-proposal was
reasoning from the 209 in-tree object-shaped accesses without checking what the seam had already
replaced them with. Those 209 are a MIGRATION to an existing idiom, not evidence that a handle is
needed.

## R2. `Compound` is not needed, and the tuple STRICTLY DOMINATES it

`clausal/terms.py:97` — a dataclass of `functor: str | Var`, `args: tuple`, `_position`. The
operator's read ("a generic class that contains a compound term, but that's what our
functor-first-tuples are now") is right. The one capability that could have justified keeping it —
a VARIABLE in functor position — measured the other way:

    (F, 1)            vs ('f', 1)             unify -> True,  F bound to 'f'
    Compound(G, (1,)) vs Compound('f', (1,))  unify -> FALSE, G left unbound

`Compound.__unify__` refuses to bind an unbound functor var on purpose (the "deref-only floor",
A01-F003). The tuple path binds it. So the tuple is not merely equivalent, it is **more
expressive** on the only axis where `Compound` looked richer.

And the fourth-representation tax is real and measurable:

    Compound('f', (1,2)) vs ('f', 1, 2)       unify -> False

**One thing `Compound` carries that a tuple cannot: `_position`** (source span, `compare=False`,
`repr=False`, for diagnostics). That is the only open item in removing it, and it is a diagnostics
question, not a representation one — a side table keyed by id, or positions kept on the clause
rather than the term.

## R3. A NEW GAP: an opaque Python object cannot go directly into a goal

The operator's requirement — "there should be a way to pass Python objects *through* it, if
necessary (ideally not touched)". Measured, with a working control:

    control: ("idpred", 42, W)            -> True, exports 42
    ("idpred", <Payload object>, W)       -> NotImplementedError:
                                             term_to_ast_expr: unsupported term type Payload
    pre-bind to a Var, pass the Var       -> True, exports Payload(42), SAME OBJECT (identity)

So passthrough works, but only by the Var route; the direct route dies in `term_to_ast_expr`.

**The cause is exactly the representation question.** `once_bind` hands the goal to `solve()`,
which LOWERS it to AST — it treats the goal as *source to compile*, and an arbitrary Python object
has no literal AST form. Once the goal is a tuple of DATA resolved against the db rather than a
tree to compile, an opaque object in an argument slot is no more special than an `int`, and route A
works for free. **This is an argument for the tuple representation, and a concrete acceptance test
for it.**

(A first probe of this reported a failure on the Var route too. Its control also failed — the
fixture had not declared the functor — so that reading was void. Recorded because the control is
the only reason it was not filed as a finding.)

---

# The cut barrier and the three suffixes

The operator's ruling, restated: **cut-free forever is a property of `.clausal`, not of the
engine.** `.pl` MAY carry cut and the rest of ISO. Clausal code must not be able to call into code
with cuts — *not even load it*. A cut-free `.pl` file must run unchanged when renamed `.clausal`.
The seam has no cuts and keeps none. The purpose is to guarantee monotonicity, because `.clausal`
is the target of formalisation into ontologies.

Four things follow, and the last one is load-bearing.

**1. `.clausal` and `.pl` must share ONE front end.** "Rename the suffix and it runs" is only true
if both suffixes read through L3. The suffixes then differ by a GATE, not by a grammar — which is
the cheapest possible version of this design and is what L3 already is.

**2. Purity is statically decidable, so it is a gate rather than a judgement** — as plan rev 3
says. The reader sees `!` in a body; no analysis is required.

**3. But purity is a property of the IMPORT CLOSURE, not of a file.** If pure A imports pure B
which imports impure C, A can reach a cut. So the check is transitive, and a module must carry a
purity bit that is the AND of its own text and everything it imports. This is not stated in the
plan and it is where the design gets teeth.

**4. The enforcement point already exists in this document.** §1's answer to q1 plants the
exporter's row into the importer's table at import. **That plant is the chokepoint** — the one
place that sees "module X is taking a dependency on module Y" with both modules resolved. Purity
barrier, export enforcement (§2), and row sharing are three jobs for one hook. Doing q1 first
therefore buys the cut barrier its mechanism, which is a second reason it sequences before P1.

## The ordering constraint, measured

    engine tree, tracked:   .clausal  431      .seam  0      .pl  15

**Zero files have moved to `.seam`.** `.clausal` cannot take on ISO syntax while 431 engine files
(plus the corpus, which the plan puts at 787 and which is not measured here) still hold Python-seam
syntax under that name. The write-side flip to `.seam` is the prerequisite for everything in this
section, and it has not started.

Nothing here blocks L3, which targets `.pl`. It blocks the `.clausal` RECLAMATION, and the cut gate
lives on the far side of it.
