# The clause-free vocabulary idiom moves a CLASS between rows — what is it after the flip?

**Found:** 2026-09-24, fixing F1 row 24 (`compiler_v2` step 4). **Flip design.**

## Today

Step 4's `pred_cls._bind_row(db, functor, arity, authorized=True)` is the one
authorized "steal": module B imports a clause-free exported predicate from
vocabulary module A and supplies its clauses; the shared class is moved off
A's row onto B's, so everything resolving through the class sees B's
clauses. Measured: 7 of 16,123 class arrivals take this path over the house
suite — `impclob_implements`/`_impclob_probe_b` (`impclob_verdict/2`) and
`fnmismatch_use` (`fnm_verdict/2`); tests in
`tests/test_imported_functor_clause_clobber.py` and the fnmismatch fixtures.
(The other 16,116: 8,971 unbound classes, 7,145 already on this row.)

## After the flip

There is no class to move. The binding in B is a mangled atom
`A\x1fverdict`, which `_resolve_mangled_owner` resolves to A's row — which
stays EMPTY, while B's clauses land on B's own row. Unless something
decides otherwise, a vocabulary implementation silently stops answering
through the vocabulary's name.

## Design question (not guessed)

Which row receives the implementer's clauses post-flip — the vocabulary
owner's (write through, like `-dynamic` import asserts land ON THE OWNER),
or B's, with A's name resolving to B's row via adoption? Either way the
existing impclob/fnmismatch tests should go red at the flip if nothing is
done; confirm that before relying on it.
