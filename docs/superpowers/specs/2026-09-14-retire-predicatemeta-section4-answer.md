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

---

# RULED 2026-09-14: dates and decimals are TERMS, and the refusal stays

The operator's ruling on R3, and it removes the exception rather than accommodating it:

    a date     ('date', 2026, 9, 14)
    a decimal  ('decimal', "10.01")     digits as a STRING, so exactness survives

**Keep the error that is raised today when a Python object is put through.** No Python objects
cross into term position.

## Why this is the clean answer and not a compromise

R3 left an open decision because `datetime.date`, `Decimal` and `Quantity` looked like a value
vocabulary that needed an exception to "no Python objects in terms" — they are Python objects, and
closing the runtime route would have taken them with it. Encoding them as ordinary functor-first
terms means **there is no second class of value at all**: no declared vocabulary to maintain, no
per-type carve-out in the marshal rule, and one sentence covers everything —

> a term is marshal-clean data, and a Python object is not a term.

Both encodings are marshal-clean (`str` + `int` inside a `tuple`), verified by the same
`marshal.dumps` probe that showed `Decimal`, `datetime.date` and an opaque object are not.

## It settles the two measured inconsistencies by DELETION

    datetime.date passes the compile route while FAILING marshal
        -> moot: a date is no longer a Python object, so it never takes that route
    Decimal is refused on the compile route while the engine treats it as first-class
        -> no longer a gap; the refusal IS the rule

## The consequence to schedule, not to assume

With dates and decimals encoded as terms, **nothing legitimate is left on the runtime object route**
(pre-bind a Python object to a Var, pass the Var — measured working today, identity preserved). The
refusal can therefore be made UNIFORM across both routes.

That is a separate change with its own blast radius and it is NOT part of this ruling: existing
engine and corpus code may lean on the runtime route, and that population is unmeasured. Sequence
it after the encodings land, and gate it on a corpus answer-set run — money and dates are live
corpus vocabulary (`decimal-currency`, the minor-units work, the date/3 predicates), so this is
the one step in the representation change that touches values the corpus computes with.

## Open, and small

* `Quantity` — a unit-carrying value — was not named in the ruling. It is the same shape of
  question as `Decimal` and probably the same answer (`('quantity', <magnitude term>, <unit>)`),
  but it is not ruled and should not be assumed.
* Whether `('decimal', "10.01")` is the WRITTEN surface or only the internal encoding. The corpus
  writes money literals; if the encoding is also the surface, that is a corpus migration.

---

# Python tuples as DATA, and a correction to the marshal rule

Asked: what does an actual Python tuple passed in become? **The mechanism already exists** —
`clausal/logic/cells.py`. Slot 0 of a cell is either a `str` (a compound functor) or the `tuple`
TYPE OBJECT itself (`TUPLE_TAG`), which marks plain tuple DATA:

    foo(1, 2)   compound     ('foo', 1, 2)             slot 0 is a str
    foo         atom         ('foo',)                  slot 0 is a str
    (1, 2)      tuple DATA   (<class 'tuple'>, 1, 2)   slot 0 is the tuple TYPE

Tagging with the type object rather than a reserved string is the load-bearing choice, and
`cells.py` gives the reason: a data tuple's own slot 0 could be anything — an int, a str, another
tuple — so no string tag is collision-free. A type object cannot appear as a user value.

Measured, not read off the docstring:

    is_cell(('foo', 1))          True       is_cell((1, 2))        False   a raw pair is not a cell
    is_cell((tuple, 1, 2))       True       is_cell((Var(), 1))    False   deprecated

    ('foo',1,2) vs (tuple,1,2)   False      the two shapes do not unify -- correct
    (tuple,1,X) vs (tuple,1,2)   True       X = 2
    (1,2)       vs (tuple,1,2)   False      an untagged pair is opaque data, not tuple-data

Slot 0 must be `str` or `TUPLE_TAG`; nothing else is a cell. A `Var` in functor position is
explicitly deprecated — `(F, 1)` would flip from compound to tuple-data the moment `F` bound to the
`tuple` type, which `cells.py` records as having caused the bridge's one Critical.

## CORRECTION to the ruling's wording

The dates-and-decimals ruling above is recorded as "**a term is marshal-clean data**". Measured,
that is too strong:

    marshal.dumps(('foo', 1, 2))    clean
    marshal.dumps((tuple, 1, 2))    ValueError -- the type object cannot be marshalled

So a tuple-DATA term is not marshal-clean, and the rule as written would outlaw a shape the design
depends on. The design is nevertheless consistent, because the tag never becomes a bytecode
constant: emitted code names it as the DOTTED VALUE PATTERN `$cells.TUPLE_TAG`
(`cells.CELLS_NAMESPACE_KEY`, used by `compiler/predicate.py:403` and `list_dispatch.py:111`), a
runtime name lookup. The bytecode stays clean; the runtime value carries the type object.

**The accurate rule:**

> A term that is a COMPILE-TIME CONSTANT must be marshal-clean. Tuple-data is constructed by name,
> not folded into `co_consts`.

Which leaves the dates-and-decimals ruling intact and better founded: `('date', 2026, 9, 14)` and
`('decimal', "10.01")` are marshal-clean *and* fold, so they need no `$cells`-style indirection,
while an opaque Python object has neither property and stays refused.

---

# The tuple-DATA tag: `(tuple, …)` vs `('', …)` vs `((), …)` vs a reserved str

Proposed: replace the `tuple`-type tag with `('', 1, 2)`, then `((), 1, 2)` — both to make
tuple-data marshal-clean so the `$cells.TUPLE_TAG` indirection can go.

**The benefit is real and larger than marshalling.** A marshal-clean tag folds into `co_consts`,
which deletes the mechanism that exists ONLY because the current tag cannot be marshalled: the
`$cells` namespace injection, the dotted value pattern (`compiler/predicate.py:403`,
`globals_env.py:379`, `list_dispatch.py:111`). With a `str` tag the slot-0 rule also collapses from
`type(s0) is str or s0 is TUPLE_TAG` to "slot 0 is a `str`" — one check on the hot recognition path.

    marshal.dumps((tuple, 1, 2))      ValueError
    marshal.dumps(('', 1, 2))         clean
    marshal.dumps(((), 1, 2))         clean
    marshal.dumps(('$tuple', 1, 2))   clean

## Why BOTH empty spellings fail, and it is the same reason

**Measured: `unify((), '')` is True, though `() == ''` is False.** The engine already treats the
empty tuple, the empty string and `[]` as ONE term — nil:

    unify((), '')    True        unify((), [])   True        unify('', [])   True

so the two proposals are the same proposal as far as the engine is concerned:

    ((), 1, 2)  vs  ('', 1, 2)        unify -> True

and the empty data tuple collides with the empty atom under either:

    ((),)       vs  ('',)            unify -> True     <- must be False for a tag to work

Controls confirm the equivalence is specific, not a unify that says True to everything:
`('a',)` vs `('b',)` False, `((),)` vs `(1,)` False.

**So the tuple-tag question is DOWNSTREAM of the nil/empty-atom ruling**, whichever empty spelling
is chosen. That ruling is already pending in
`todo/source-empty-string-dict-key-is-an-atom-not-nil-2026-09-07.md`, which notes ISO has `''` as
an atom distinct from `[]` so both readings are defensible, and asks for the same kind of ruling
`'[]'` got. `atoms.NIL_KEY` is `()`; `atoms.mint('[]')` is the empty list.

## The option that works without a ruling

A reserved `str` that is not a writable atom spelling. This tree already reserves `$`-prefixed
names for engine-internal bindings (`$module`, `$cells`, `$Var`), and they are not valid source
identifiers. Measured:

    ('$tuple',)      vs ('',)     False        ('$tuple',) vs ((),)    False
    ('$tuple',)      vs ('[]',)   False        marshal-clean, and a str in slot 0
                                               so it is already a cell today

* keeps the empty data tuple as `('$tuple',)`, unambiguous
* gives the one-branch slot-0 rule, the same win `''` would give
* costs one reserved spelling, and loses the elegance of "a tuple is a compound with no functor"
* **does not touch ISO fidelity** — `''` stays available as the ISO empty atom

## Recommendation

If the nil ruling goes the way the open todo hints (no empty-spelling atom in Clausal), `''` is the
better design and should be taken then. Until that is ruled, a reserved `$`-prefixed tag gets the
marshalling win and the one-branch recognition rule with no ISO cost and no dependency on an open
question. Either way, `(tuple, …)` should go: it is the only candidate that cannot be marshalled.

**Not established:** how many tuple-DATA terms exist in the corpus, i.e. what a re-tagging would
cost to migrate. The engine's own use is small (4 sites, all display tests).

## RECOMMENDED: `('()', 1, 2)` — the two-character spelling `"()"`

Proposed by the operator after `''` and `()` were measured to be the same nil-entangled tag. It
beats both, and it beats `'$tuple'`. Measured:

**1. Not entangled with nil** — the property `''` and `()` both fail:

    ('()',) vs ((),)    False        ('()',) vs ([],)     False
    ('()',) vs ('',)    False        ('()',) vs ('[]',)   False
    ('()',1,2) vs ('()',1,2)  True

So it needs no ruling and does not wait on
`todo/source-empty-string-dict-key-is-an-atom-not-nil-2026-09-07.md`.

**2. It follows an established convention exactly.** `atoms.NIL_SPELLING` is `'[]'`, and
`atoms.mint('[]')` returns the empty list — the engine ALREADY reserves and intercepts a writable
quoted-atom spelling for a structural term. `'()'` spelling a tuple is the same idea, and reads
correctly: `('()', 1, 2)` is the tuple `(1, 2)`.

**3. The "but it is writable as a quoted atom" objection is a FEATURE here.** `'()'(1, 2)` is valid
ISO — a quoted atom may be a functor, and the reader already handles it
(`prolog_parser.py:490`, "a quoted functor like `'foo'(1)`"). So tuple-data gets a portable
spelling with NO new syntax, and a `.pl` file containing one loads in Scryer and Trealla. That
matters for the `.pl` portability goal in a way `'$tuple'` does not: `$` is not an ISO atom
convention.

**4. It is faster, and the operator's reason is the right one** — a Python `str` caches its hash,
so it wins both the recognition test and the dict lookup:

    recognition  one-branch  `type(s0) is str`               0.0205 s / 2M
                 two-branch  `str or s0 is TUPLE_TAG`        0.0428 s / 2M    2.08x
    dict key     str-tagged cell                             0.0335 s / 2M
                 type-tagged cell                            0.0584 s / 2M    1.74x

The one-branch rule is only available to a `str` tag, so this is the same win `''` would have
given, without the collision.

**5. `'()'` is free.** 0 uses in engine Python, 0 `.clausal` files, 0 tests.

**The one cost**, stated plainly: the atom `'()'` stops being available as an ordinary atom. That
is the same trade `'[]'` already makes, and it is why the precedent matters.

**Migration**: the engine's own tuple-DATA use is 4 sites, all display tests. The corpus is
unmeasured — that figure is the only thing between this recommendation and a decision.

### Confirmed against real Prolog (Scryer, plus the operator's SWI 10 session)

    (1,2) == ','(1,2)                  true     <- (1,2) IS the comma-term
    (1,2) == '()'(1,2)                 false
    {1,2} == '{}'(','(1,2))            true     <- the curly precedent, at arity ONE
    {1,2} == '{}'(1,2)      arity 2    false
    {a}   == '{}'(a)                   true

    functor((1,2))      = (,)/2
    functor({1,2})      = {}/1
    functor('()'(1,2))  = ()/2

    writeq('()'(1,2))   ->  '()'(1,2)
    writeq('{}'(a))     ->  {a}

**`(1,2)` in Prolog is ALREADY TAKEN** — it is the comma-term, functor `(,)/2`, i.e. conjunction.
Prolog therefore has no surface syntax available for tuple-data at all, which is exactly why it
needs a reserved functor rather than a bracket form. `'()'(1,2)` failing to unify with `(1,2)` is
the property we want, and SWI 10 and Scryer agree on it.

**`'()'` round-trips**: `writeq` returns it in canonical quoted form in both engines, so a
Clausal-emitted `.pl` carrying tuple-data is readable and re-readable there.

**One asymmetry, in `'()'`'s favour.** `writeq('{}'(a))` prints `{a}` — Prolog has read-back SUGAR
for the curly functor. `'()'` has none, so it always prints canonically: no writer support to add,
and a tuple in a `.pl` file is visually unmistakable from a conjunction.

*(A first reading of `'{}'(1,2) \= {1,2}` as a refutation of the curly precedent was an ARITY
mismatch — `{1,2}` is `'{}'/1` over the comma-term, not `'{}'/2`. Recorded because the shape of the
mistake — testing a precedent at the wrong arity — is easy to repeat.)*

**Not verified**: Trealla. Only Scryer is installed in this environment
(`/workspace/scryer-prolog/target/release/`).

---

# CORPUS SWEEP — both open numbers, measured

`/workspace/clausify-domains` @ `main`: **787 `.clausal`, 88 `.seam`, 263 `.py`** (the `.clausal`
count matches the plan's 787 exactly). Instruments in `tools/predmeta_census/`; every count printed
the size of what it matched, and both controls behaved (a must-match-nothing pattern returned 0, a
must-match-plenty pattern returned 1,692 / 290,641).

## 1. Object-shaped predicate access: ESSENTIALLY ZERO

How the corpus actually invokes a predicate:

    test(...)          in-language, .clausal        5,259  in 295 files
    --pred(...)        the term seam, .seam            57  in  42 files
    ++escape           python back across the seam   165  in  41 files
    call("name", ..., module=mod)   .py                7  in   4 files
    load_clausal_module(...)        .py                4  in   3 files
    ------------------------------------------------------------------
    module attribute / getattr on a predicate           ~0

**The object-shaped count is a measurement artefact, and chasing it down is the finding.** A first
sweep reported 123 object-shaped sites. Read:

* **120 of them are `getattr(_body, 'run')` and `getattr(_body, 'main')`** — 60 each, shim
  boilerplate reaching PYTHON entry points, not predicates. The regex matched any `getattr` with a
  lowercase string.
* **3 were `sections["citation_records"]`** — the alternation `(module_dict|md|ns)\[` matched the
  `ns[` inside `sectio``ns[`.
* `from <domain>.<module> import <pred>`: **0**. `call(mod.pred, …)`: **0**. Attribute calls
  resolve to `re.Match.group`, `pathlib.mkdir` and the `_body.main` shim.

So **spec §4 q3 — a module-level predicate name becomes the atom — costs the corpus nothing.** The
engine's own 209 object-shaped accesses are the whole migration, and the corpus is already on the
idiom the design targets.

Worth noting for the seam's own roadmap: `if --goal:` and `for x in --goal:` are at **0** corpus
sites. The goal-position seam landed 2026-09-08; all 57 corpus seams are TERM position. The
transparent-variable idiom is available and unused.

## 2. Tuple-DATA in the corpus: ZERO

    TUPLE_TAG by name                0 occurrences in 0 files
    $cells namespace                 0 occurrences in 0 files
    is_cell / compound_cell_shape    0 occurrences in 0 files
    matching slot 0 on a type        0 occurrences in 0 files

**Re-tagging tuple-data is compiler-internal and costs the corpus nothing.** Corpus source writes
`(1, 2)` and the compiler applies the tag; nothing in the corpus spells or matches it. The engine's
own use is 4 sites, all display tests.

**That was the one number between the `('()', 1, 2)` recommendation and a decision. It is zero.**

## The caveat, because "no migration sites" is not "no risk"

Those 5,259 `test(...)` and 57 `--pred(...)` invocations all run THROUGH the engine. A
representation change with zero corpus EDIT sites can still move corpus ANSWERS, and site analysis
is a different claim from an answer-set re-run. Both changes still need the oracle gate — ask
harness-batch-lane to re-run the sealed scorers — before promotion.

---

# Scoping the dates-and-decimals ruling — the two halves are NOT alike

Measured before implementing, and they need different decisions.

## Dates: the ruled shape is ALREADY the reality

    date(2026, 9, 14) written in .clausal   exports as   ('date', 2026, 9, 14)   type tuple

Exactly the ruled encoding, in the engine today. And the corpus standardises on it independently:
`_tools/check_date_representation.py` is a RATCHET whose whole job is stopping `[Y, M, D]` integer
lists spreading in place of "the standard `date(Y, M, D)` term", with a per-file baseline holding
**one** remaining violation. So there is no date migration to do.

**But the remaining `datetime.date` route is deliberate machinery, not a leak.**
`terms_to_ast.py:60-72` defines `_VALUE_TERM_CTORS`: `datetime.date`, `datetime.datetime`,
`datetime.time` and `datetime.timedelta` are lowered to CONSTRUCTOR CALLS in the emitted AST
(`date(year, month, day)`), which is why a Python date passes the compile route where a `Decimal`
or an opaque object is refused. Extending the refusal to dates therefore means DELETING a built
feature, not closing a hole — and 9 engine test files reference `datetime.date`.

That is a feature removal and wants an explicit call rather than an inference from "keep that
error".

## Decimals: NOT in the ruled shape, and the change is the bigger one

    10.01 written in .clausal   exports as   10.01   type FLOAT
    3/4                         exports as   Div(left=3, right=4)   a structural operator node

A decimal literal is a Python float today — which is the known scale-loss problem recorded against
the money work (`decimal_repr="float"`, the default, loses scale; `"rational"` keeps it as an
unevaluated `1_550_00/100`).

**Two readings of `('decimal', "10.01")`, and they are materially different work:**

1. **A SEAM-BOUNDARY encoding.** Python hands `('decimal', "10.01")` across the seam instead of a
   `Decimal` object, and the engine keeps refusing the object. Bounded, matches "keep that error
   that was raised if there is an attempt to put these through", and changes nothing about how
   `10.01` in source compiles. Open sub-question: what the engine then DOES with that term — it has
   to be recognised as a number for arithmetic, or it is inert.

2. **The LITERAL representation.** `10.01` in `.clausal` source stops compiling to a float and
   becomes `('decimal', "10.01")`. This fixes the scale loss at its root, and it is the reading
   that makes the encoding load-bearing rather than decorative. It also changes the numeric surface
   and interacts with the 2026-09-13 ruling that **arithmetic IS RATIONAL** (`{...}` the default,
   `#=` the narrow integer case) — a decimal term would have to participate in rational arithmetic,
   and `Quantity` reaches 29 engine modules and 26 test files.

Reading 1 is a day. Reading 2 is the numeric surface. **Not guessed — put to the operator.**

## `Quantity` is still unruled

Named in neither. Same shape of question as `Decimal`, plausibly
`('quantity', <magnitude>, <unit>)`, but units are live corpus vocabulary and it should not be
assumed to follow.

---

# `('()', 1, 2)` LANDED on the branch — gate clean

    baseline  7ad86154   144 failed, 16287 passed
    candidate 28f29c55   144 failed, 16304 passed      NEW 0   GONE 0

The +17 is the new tests (12 shared-row, 5 tuple-tag). Sites changed: `cells.py` (the tag, the
one-branch `_valid_functor_slot`, `is not` -> `!=`), and the data/compound split written down
explicitly in `terms.py` (4 pairs), `reflection.py`, `testing.py`, `builtins/_helpers.py` (2) and
`modules/py/json.py` (3).

## What the gate caught, both worth keeping

**1. The identity sweep I did not do.** I fixed `compound_cell_shape`'s `is not TUPLE_TAG` because
I happened to read it, and did not sweep. Thirteen more sites had the shape, and they are PAIRS in
which the COMPOUND branch runs first:

    if type(t) is tuple and t and type(t[0]) is str:    # compound   <- ran first
    if type(t) is tuple and t and t[0] is TUPLE_TAG:    # tuple-data <- never reached

While the tag was a type object the compound branch excluded it FOR FREE. With a `str` tag it
swallows tuple-data, and every data tuple rendered, serialised and pattern-matched as the compound
`'()'/N`. 19 failures, all one cause.

**The general rule, now twice-learned this session: a property that was FREE under the old
representation has to be written down under the new one.** `_helpers._cell_functor` needed the same
treatment for the same reason, and its docstring now says so.

**2. A missing import that failed OPEN.** `testing.py` used `TUPLE_TAG` without importing it. The
`NameError` was swallowed by the diagnostic path, so near-miss output silently lost the goal name
(`chain_subject(simple)` vanished, leaving only "argument 1 was actually: simple") instead of
crashing. **And the check I wrote to prevent exactly this was worthless**: `spec['name'] in
src.split('def ')[0] or 'import' in src` — the second disjunct is true of every Python file, so it
reported OK for all five modules. Re-verified by asking each MODULE for the attribute
(`getattr(mod, name) == TUPLE_TAG`), which found it immediately.

**3. One flake, correctly identified as such.** `test_F026_multi_star_splits_bounded_for_moderate
_input` is a perf bound; it failed once while two suites ran concurrently, passed 3/3 standalone,
and did not recur on a clean solo gate.

## The indirection this deletes

Three tests existed only to pin `$cells.TUPLE_TAG`, and the reason it existed is sharp: **the tag
was a NAME, and a bare name in a `match` pattern CAPTURES rather than compares.** Rooting it at
`$cells` was the dodge. A string literal cannot capture:

    case [$cells.TUPLE_TAG, _ncap0]:     ->     case ['()', _ncap0]:

with no namespace injection — and the "degrades to a wildcard when `$cells` is absent" failure,
which silently cost a non-ground tuple-data cell its indexing, can no longer happen. Those three
tests are INVERTED to pin that rather than deleted.

---

# rdiv/decimal: the TERM half is free; the arithmetic half collides with a parked branch

Ruled 2026-09-15: rationals are `('rdiv', N, D)` (Scryer's spelling, not SICStus's `r/2`), and
decimals are `('decimal', M, E)` — mantissa and power-of-ten scale.

## Free, measured

Both spellings already work, with NO engine change, because post-FLIP every compound is a cell:

    rdiv(1, 3)        in source ->  ('rdiv', 1, 3)          marshal-clean, compiles
    decimal(1001, 2)  in source ->  ('decimal', 1001, 2)    marshal-clean, compiles

Names confirmed free: `rdiv` and `decimal` have 0 engine-builtin mentions and 0 corpus definitions.

`('decimal', M, E)` is Python's own `Decimal` model — `Decimal.as_tuple()` is
`(sign, digits, exponent)` — so conversion is lossless both ways, the sign rides in the mantissa,
and SCALE survives where `rdiv` alone loses it:

    10.01   -> ('decimal', 1001, 2)          distinct terms,
    10.010  -> ('decimal', 10010, 3)         same rational value

and it is a SUBTYPE of rdiv: `('decimal', M, E)` == `('rdiv', M, 10**E)`, so arithmetic normalises
with one rule rather than gaining a fourth numeric type. **Open detail:** `1E+5` has a POSITIVE
Decimal exponent, so it encodes as `('decimal', 1, -5)` — a negative scale field meaning x10^5.
Allowing it preserves Decimal's model exactly; normalising to `('decimal', 100000, 0)` loses the
`1E+5` / `100000` distinction. Recommended: allow it.

## What is NOT free, and why it should wait

Making the two spellings NUMBERS — recognised by the evaluator and by CLP — is the real work, and
it lands squarely on rational arithmetic. **`feat/clpq-c-port-2026-09-13` has `arith_q` already
ported to C over GMP** (its handoff: "ported to C over GMP and agrees with Holzbaur 20/20 on a live
Scryer differential"). `arith_q` IS the rational arithmetic layer.

So a rational-representation change written now would be written against a Python `arith_q` that a
parked branch is midway through replacing. **Sequence it WITH the CLP(Q) port, not against it** —
otherwise one of the two gets rewritten twice, and the differential oracle that makes the port
trustworthy would be comparing against a moved target.

Also unmeasured, and needed before the arithmetic half: today a non-integral rational has no
observable term form at all — `Fraction` cannot be lowered (`NotImplementedError`, same as
`Decimal`), so nothing in a compiled goal can hold one. What `X` binds to for a non-integral result
is therefore a question about the CLP path specifically, not about the general evaluator.
