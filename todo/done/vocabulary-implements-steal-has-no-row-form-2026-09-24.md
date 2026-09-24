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
Mike: I guess the owner's, if the owner is the one defining it. But is it not possible to move the predicates into their 'B' files?

RULED 2026-09-24 (operator, direct): DROP the idiom. B defining clauses for a
predicate imported from a clause-free vocabulary A is a LOAD ERROR (remedy:
define it in B and export it from B). Move the impclob_*/fnmismatch_*
fixtures. Downstream usage to be checked before landing.

## Resolved (2026-09-24, branch feat/drop-vocabulary-implements-2026-09-24)

The idiom is a LOAD ERROR, per the ruling above.

**Where.** `compiler_v2._refuse_foreign_writes` (step 3d, the dry run before
the write loop) asks, after the gate's existing `refusal_for` has permitted a
key, `_implements_an_imported_declaration`: is the head's `(functor, arity)` an
`-import_from` of a predicate AT THIS ARITY (`is_declared_predicate`,
arity-strict in both eras) from ANOTHER module, with the canonical spelling
not re-bound to a local predicate of this module? If so the load is refused
before anything is written. Because the gate already refused every import of
a predicate the exporter DEFINES (clobber refusal, message unchanged), what
reaches the new check is exactly "imported from a module that does not define
it": a declaration-only export (no row post-flip, a detached private row
today) or a `-dynamic` one with no load clauses (an unowned row). Nothing in
it reads a class: the binding goes through the era-agnostic accessors, and
`tests/test_vocabulary_implements_refused.py` runs it with a class binding
and a mangled handle and gets the same text.

**Message** (`import_diagnostics.describe_imported_declaration_implemented`):

    B defines clauses for p/2, which it -import_from's from A -- but A only
    declares p/2; it does not define it.
      Supplying the clauses for a predicate imported from a module that only
      declares it is not supported: a predicate has exactly one defining
      module, and the module that writes its clauses is that module.
      -> define p/2 in B and export it from B: drop p from the
         -import_from(A, [...]) list and add p/2 to B's -module export list;
         then have the modules that use it import it from B, not from A (and
         remove the declaration from A if nothing else needs it).

**Measured.** Every in-tree `.clausal` file with an `-import_from` (106 under
tests/clausal/examples; 84 load, the rest are deliberate error fixtures or
need a sys.path entry, 5 of those retried and loaded): the idiom condition
fires in exactly 5 fixtures / 5 keys — `impclob_implements` and
`impclob_implements_rival` (`impclob_verdict/2`), `fnmismatch_use`
(`fnm_verdict/2`), `impord_declare_then_import_fact` (`impord_fverdict/2`),
`gate_rival` (`gv_free/1`). Package fixtures: 0 (all 190 of their imports
name Python library modules, not `.clausal` exporters). The F1 "7 arrivals"
counted only moves off a REAL foreign row; the first implementer's move off a
DETACHED row is the idiom too and was not in that count. After the change,
step 4's authorized bind moves a class off a foreign real row 0 times over
the targeted suites (177 arrivals) and the whole population (1,205 arrivals);
positive control with the refusal disabled: 1.

**The steal branch is LEFT.** `authorized=True` is still needed by step 4a
and `specialization._install_specialized`; step 4's own use has no measured
user, but a class reaching `module_dict` by a route other than
`-import_from` is not provably absent, and dropping the flag would turn such
a bind into a silent skip. Comment updated; it goes with the classes at the
flip.

**Found on the way (pre-existing, parked):**
`todo/field-named-export-of-an-imported-dynamic-splits-identity-2026-09-24.md`,
`todo/too-few-positional-args-pad-with-fresh-vars-2026-09-24.md`.
