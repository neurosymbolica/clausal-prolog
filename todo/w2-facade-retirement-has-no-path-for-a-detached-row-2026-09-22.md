# W2 cannot "point callers at `db.row(functor, arity)`" — the detached row has no such key

Raised 2026-09-22 by engine-lane while scoping W2 of the P4 retirement
(`implementation_plans/p4-predicatemeta-retirement-scope-2026-09-21.md`).
**W2 should not start until this is ruled.** Measured on
`feat/predmeta-w2-facades-2026-09-22` (= the P2-on-main integration, b45171ab).

## What W2 says

> **W2 — retire the 19 facades.** Mechanical, high volume, low risk: point
> callers at `db.row(functor, arity)`. Biggest single lever on the 374 refs.
> Expect it to be the bulk of the diff and the least of the risk.

## Why the prescribed substitution is not available

All **21** facade bodies in `predicate.py` are the same shape:

    return (cls._row or cls._detached_row()).clauses

`cls._row` is initialised to `None` (predicate.py:812) and is only filled by
`_bind_row` when the class is compiled into a module. The `or` arm is therefore
not incidental — it is the **compatibility mode**, and its own docstring says
so:

> A ``PredicateMeta`` minted outside a ``.clausal`` load has no Database to be
> a row OF, and must still behave like a predicate [...] It gets a ``PredRow``
> over a **private single-predicate Database nobody else can reach**.

That last clause is the problem. A caller holding only `(functor, arity)` and a
`db` **cannot reach a detached row by construction** — it lives on a private
Database that is not the one the caller has. So for any class whose `_row` is
None, `db.row(functor, arity)` does not return that state and there is no key
that would. The substitution is unavailable, not merely inconvenient.

Which leaves three options at each of the 76 engine call sites, none mechanical:

1. **Drop the fallback.** `cls._row.clauses` raises `AttributeError` on None
   for every class minted outside a load. Silent until the first such class.
2. **Duplicate the fallback 76 times.** `(cls._row or cls._detached_row())`
   inlined at every site — which keeps the class on the path anyway, so it buys
   a lower reference count and no structural progress.
3. **Retire the detached mode FIRST**, so `_row` is never None. That is a
   decision about `make_predicate` and class-minted predicates — i.e. W4-shaped
   (the class-shaped helpers) — so W2 would depend on W4, reversing the plan's
   stated ordering.

Note the laziness is also load-bearing and for two stated reasons: `database.py`
imports `predicate.py`, so eager minting would need a module-level cycle; and a
pure term/data class never pays for a row it never touches.

## The size, re-measured — W2 is much smaller than the plan implies, engine-side

The plan's per-attribute figures are WHOLE-TREE counts, not engine counts:

    ._clauses sites      clausal/  46    tests/  137    packages/  4   = 187
                         (the plan quotes 193 for this attribute)

Engine-only sites for the eight facade families, excluding `predicate.py`:

    _clauses 35   _dispatch_fn 18   _lazy_recompile 9   _signature 6
    _locked 2     _dynamic_arities 3   _index_plans 3   _clauses_source 0
    TOTAL 76 sites, and 56 of them are in THREE files:
      database.py 27, compiler_v2.py 15, builtins/_registry.py 14

So the engine half is 76 sites in ~11 files, and the three biggest files
already hold a Database, so the row IS reachable there. **The bulk of the 374
reference count is test code** (137 of 187 for `_clauses` alone) — mechanical,
and gated directly by the house suite.

## What is actually being asked

Does the detached row survive P4?

* **If NO** — retire it first, then `_row` is never None, the 21 facades become
  true one-line read-throughs, and W2 is genuinely mechanical. But it must be
  sequenced BEFORE W2, and it needs an answer for `make_predicate`, which the
  spec already lists for deletion among the class-shaped helpers.
* **If YES** — W2's mechanism needs restating. The honest version is "point
  callers at the ROW, obtained from the class", which keeps the class on the
  path and makes W2 a reference-count exercise rather than a structural one.
  Worth doing, but not worth calling the biggest lever.

## Related, already filed

* `todo/detached-row-bind-refusal-is-not-atomic-2026-09-06.md`
* `todo/done/bind-row-does-not-migrate-index-plans-from-a-detached-row-2026-09-17.md`

Both are defects in the detached-row/bind-row seam, which is evidence the mode
is subtle enough to be worth retiring rather than spreading to 76 call sites.
