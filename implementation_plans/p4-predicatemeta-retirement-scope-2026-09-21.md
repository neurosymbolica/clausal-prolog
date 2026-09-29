# P4 — retiring `PredicateMeta`: a scope, measured 2026-09-21

**Status: SCOPE ONLY. Nothing here is a plan of record, and one workstream
(W1) has to run before the rest can be sized honestly.**

Measured against `main` at the time of writing, not recalled.

## Where P4 starts from

| | |
|---|---|
| `PredicateMeta` | 374 refs / 46 files; **31** methods and properties |
| `Compound` | 361 refs / 53 files |
| `KWTerm` | 118 refs / 26 files |
| P1 (rows keyed `(functor, arity)`, shared rows) | LANDED |
| P4 prerequisites | LANDED (every declaration creates its row; a row is minted only for a declared functor a directive names; 0-arity-as-value is the atom) |
| P2 (terms are tuples) | BUILT, HELD — 73 commits, not merged |

**P2 does not reduce the class count.** Its own exit numbers are live term
INSTANCES 534 -> 0 and `PredicateMeta` CLASSES 574 -> 574, unchanged by
design. P4 is where the class itself goes, and P2 landing changes none of the
numbers in the table above.

## The surface, split by what it actually is

Of the 31 members:

* **19 are THIN READ-THROUGHS onto `_row`** — the getter/setter pairs for
  `_clauses`, `_dispatch_fn`, `_lazy_recompile`, `_signature`, `_locked`,
  `_dynamic_arities`, `_index_plans`, `_clauses_source`. P1 already moved the
  STATE to the row; these are facades over it. They die when their callers
  read the row instead, and that is mechanical.
* **~12 carry real logic** — `__call__`, `__new__`, `_bind_row`,
  `_get_dispatch`, `_refuse_call_at`, `_declared_arity`, `_clause_arity`,
  `_gated`, `_detached_row`. Each needs a home: the row, or a module-level
  function keyed by `(functor, arity)`.

In-tree read sites, the ones that set the volume:

    193  ._clauses          61  ._dispatch_fn      39  ._functor
    185  ._get_dispatch     57  ._locked           33  ._index_plans
     63  ._assertz          47  ._arity            25  .__call__

`_clausal_head` — listed in the P2 announcement as a P4 item — is **already
gone** from `predicate.py`; only a test name still mentions it. Verify before
budgeting for it.

## W1 — MEASURE THE CLIFF. Blocking, and cheap right now.

The §4 spec lists under "Not established":

> downstream code's object-shaped predicate access — the one unmeasured number in
> this document, and the one that decides whether q3 is a **migration or a
> flag day**

**That number is still unmeasured, and P2 has since produced evidence about
its magnitude.** `solve(m.pred(X))` — one Python-API access pattern through a
module attribute — broke every downstream check, was invisible to the whole
in-repo suite AND to all 12 packages, and cost a day plus two compiler
features to unblock. It was a single instance of exactly the class W1 is
supposed to count.

So: **do not size W2-W5 before W1 reports.** The honest reading of P2 is that
the in-repo suite cannot see this population at all.

Cheap NOW because the downstream harness migration is about to touch every
body anyway — the same pass that rewrites goal sites can count object-shaped
accesses. Ask for it as part of that work, not after it.

## W2 — retire the 19 facades

Mechanical, high volume, low risk: point callers at `db.row(functor, arity)`.
Biggest single lever on the 374 refs. Gated by the house suite, which CAN see
this one because it is in-tree. Expect it to be the bulk of the diff and the
least of the risk.

## W3 — `_get_dispatch`: the frozen external protocol

**The hard one, and it is hard for a reason the in-repo suite cannot show.**

* 185 in-tree read sites;
* **27 files under `packages/` implement it** out of tree;
* the signature is FROZEN, the protocol is duck-typed, and **the in-repo suite
  stays green when you break it.**

"Delete the layer" is not available. This needs a compatibility shim, a
deprecation window, and a gate that actually runs the out-of-tree
implementors — which is a gate that does not exist today. Budget the gate as
part of the work, not as a precondition someone else supplies.

## W4 — rehome the ~12 logic-bearing members

`__call__` is the interesting one: P2 already changed what it BUILDS (a cell),
so P4 only has to move where it lives. `_bind_row`, `_refuse_call_at` and
`_declared_arity` are row-shaped and should follow the state P1 moved.
`__new__` and `_gated` are the class-identity pieces and go last.

## W5 — the C arms (tail, not a prerequisite)

Task 5 step 2 is BLOCKED and explicitly re-sequenced to AFTER the P4 head
channel: an instrumented build showed **not one of the 17 C arms is dead**,
and the engine still feeds the instance arms from two call sites. So the C
deletions are a P4 tail. Do not plan them as a P2 or early-P4 item.

## W6 — `Compound` / `KWTerm` (ruled, unscoped, independent)

Ruled unnecessary 2026-09-14 — the tuple strictly dominates: `(F, 1)` vs
`('f', 1)` binds `F`, while `Compound(G, (1,))` vs `Compound('f', (1,))`
FAILS. But no phase has retired it, it is not in P2's scope, and it is not
`PredicateMeta`. 361 + 118 refs. Treat as a separate programme that happens to
share a motivation, and do not let it ride along inside P4 unscoped.

## Ordering

    W1  measure the cliff        <- BLOCKING; fold into the harness migration
    W2  retire the 19 facades    <- bulk of the diff, lowest risk
    W3  _get_dispatch + a gate   <- longest pole; needs an out-of-tree gate built
    W4  rehome the ~12
    W5  C arms
    W6  Compound/KWTerm          <- separate programme

W2 can start before W1 reports — it is in-tree only and the house suite sees
it. W3 and W4 cannot be sized without W1.

## Risks, in the order they are likely to bite

1. **The unmeasured cliff (W1).** P2 is the precedent: invisible to every
   in-repo gate, discovered by a downstream lane, one access pattern, one day
   lost. There is no reason to think P4's version is smaller.
2. **W3's gate does not exist.** 27 out-of-tree implementors and a suite that
   goes green on breakage is the definition of a control that cannot fail in
   the direction that matters.
3. **Class count is untouched by P2**, so anyone reading "P2 landed" as
   progress toward removal will be wrong by 574 classes.
4. **Scope leak from W6.** `Compound` is a different object with its own
   ruling; folding it in hides both.
