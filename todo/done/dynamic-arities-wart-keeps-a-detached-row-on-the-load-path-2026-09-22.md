# The `_dynamic_arities` wart is the LAST detached row on the load path

Found 2026-09-22 while removing the detached row from the load path so W2 can
proceed. **It is the only source left**, and it is a DOCUMENTED wart with its
own spec section, not an oversight — which is why it is filed rather than
fixed.

## Where we got to

Detached rows minted over 56 real fixture loads:

    before                       18 mints / 8 names
    after step 7 narrowed        12 mints / 5 names   (443b2e3b)
    after the clause-existence
      read stopped minting        6 mints / 2 names   (compiler_v2 ~2013)
    after term_expansion binds
      its row before compiling    2 mints / 1 name    (term_expansion.py)

The remaining 2 are `fnm_verdict` from **`compiler_v2.py:361`**, step 4a.

## The wart, in its own words

    # THE WART (P1 spec 2026-09-17 §2): ``_dynamic_arities`` is a per-NAME
    # set living on the CLASS's OWN row, which is the row of the class's own
    # arity — not of ``arity``, the arity being declared.  That row cannot be
    # named through ``db`` here: for a clause-less ``-dynamic`` declaration
    # the class is still on its DETACHED row at this point (measured
    # 2026-09-17), so ``db.row(...)`` reaches a different object, and a
    # row-side membership test would skip the stamp altogether.  So the class
    # stays for both the test and the write; the set does not move.
    # ``_bind_row`` carries the set onto the real row.

So the mint is deliberate: the class is the only reachable carrier for the set
until `_bind_row` migrates it.

**I checked whether the premise had gone stale** — the comment is dated
2026-09-17 (commit `0f169e93`) and the P4 prerequisite "every declaration
creates its Database row" landed 2026-09-18, which would have made
`db.row(...)` answer. It does not help: the wart is a KEYING mismatch, not an
existence one. The set is per-NAME but stored on a row keyed
`(functor, arity-of-the-class)`, and `arity` here is the arity being
*declared*. A row that exists is still the wrong row.

## What fixing it means

Re-key `_dynamic_arities` so it is addressable per NAME rather than per row —
i.e. move it off the row into a `(functor -> set[int])` map on the Database.
That is P1 spec §2's own subject, so it should be taken with that spec open,
and it is a behaviour-bearing change to declaration handling rather than a
representation tidy-up.

## Why it matters for W2

`todo/w2-facade-retirement-has-no-path-for-a-detached-row-2026-09-22.md` is
blocked on "can a facade read find `_row is None`". After the four changes
above the answer on the load path is "only here". Once this is re-keyed, the
remaining users of the detached row are `make_predicate` classes minted
outside a load — which is a smaller and much more tractable question than the
one W2 started with.

---

## 2026-09-22, later — QUANTIFIED, and the fix is a DESIGN CHOICE

Full-suite census (all 16,950 tests, `_detached_row` instrumented and each
mint attributed to the frame that triggered the FACADE READ):

    detached mints TOTAL        314   (was 897 before this session's commits)
      compiler_v2.py:361        207   <- THIS WART
      test / out-of-engine      100   (tests calling make_predicate; not ours)
      compiler_v2.py:493          4
      compiler_v2.py:1118         2
      specialization.py:106       1

**207 of the 214 engine-side mints are this one site.** The remaining three
engine sites are 7 mints between them. `specialization.py`'s three
`make_predicate` calls and `builtins/_registry.py`'s two contribute nothing —
they bind. So this is THE blocker, not one of several.

## The population is tiny; the semantics are not

Real code touching `_dynamic_arities` (the other 17 hits are comments):

    compiler_v2.py:361-363   the WRITE (this wart)
    predicate.py:1066-1082   the property pair (the facade)
    predicate.py:1431        the ONE reader, inside `_declared_arity`
    predicate.py:578         a name-list entry
    tests/                   30 sites

## Why the obvious fix is WRONG, and this is the bit to decide

`Database._dynamic` already holds `(functor, arity)` pairs, so the per-name set
looks derivable:

    declared = {a for (f, a) in db._dynamic if f == cls.__name__}

**That changes behaviour for IMPORTS.** `compiler_v2.py:339` records the
current semantics as deliberate:

    # ON AN IMPORTED CLASS THIS WRITES THE OWNER'S ROW (roborev job 78,
    # finding 5) [...] the declared-arity set is a property of the PREDICATE,
    # not of the module that mentioned it, and ``_refuse_call_at`` reads it
    # through the same shared class.

Today the set lives on the row, and an `-import_from` SHARES the class, so an
importer sees the OWNER's declarations. A db-derived set would read the
IMPORTER's Database, which does not carry the owner's `-dynamic` marks — so a
declared-but-clause-free imported predicate would stop being refused at the
wrong arity. Silent, and only visible in a diagnostic.

**THE CHOICE:**

* **(A) Keep it on the row, name the row properly.** At step 4a reach the
  CLASS's OWN row — `db.row(functor, len(stamped._fields), create=True)` —
  rather than `db.row(functor, arity)` with the DECLARED arity. Keeps the
  shared-class import semantics exactly. The snag: for a clause-less
  `-dynamic` the class is not bound yet, so `create=True` mints a row that
  `_bind_row` may later not be the one the class settles on, and the set could
  end up stranded on an orphan row. Needs the bind ordering worked out.
* **(B) Move it to the Database as a per-NAME map** (`functor -> set[int]`),
  and make an importer consult the OWNER's Database. That needs a way to get
  from an imported class to its owning db, which is `cls._row.db` — available
  once bound, absent before, which is the same ordering problem from the other
  side.
* **(C) Leave the wart.** It is 207 detached rows per suite run and one
  documented comment; nothing is WRONG today. W2 then proceeds on the basis
  that a facade read can still find `_row is None` on exactly this path, and
  each W2 call site is checked against it individually.

Engine-lane does not recommend one: (A) and (B) both hinge on bind ordering,
which is P1 spec §2's subject, and (C) trades a known cost for not touching
declaration semantics. **This wants the operator, with that spec open.**

Also worth noting for whoever takes it: `_declared_arity` reads `cls._clauses`
as its FIRST line, which is itself a facade read and mints for a row-less
class. Whatever fix lands should cover that read too.

---

## CLOSED 2026-09-22 — option (D), operator-approved, commit `ae51facc`

Not (A), (B) or (C): a fourth option this note had missed. `_declared_arity`
derives the set from `cls._row._db._dynamic` and the step-4a stamp is deleted.

**The import objection above was MY error.** I wrote that a db-derived set
"would read the IMPORTER's Database". It reads whatever db the ROW belongs to,
and for an `-import_from` the shared class's `_row` IS the exporter's row — so
deriving via the row lands on the OWNER's Database, exactly where the stamped
set lived. The objection only applies to deriving from the *compiling*
module's db, which is not what (D) does.

**Detached rows on the load path: 0**, over 56 fixture loads (18 at the start
of the branch). House gate NEW 0 / GONE 0.

Cost: five test sites that assigned `_dynamic_arities` by hand. One failed;
the other four would have gone VACUOUS, since they assert only that
`_refuse_call_at` declines — which a declaration that never took also
satisfies. All five now declare through a helper that marks the Database and
binds the row, with a positive control in the helper.
