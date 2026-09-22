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
