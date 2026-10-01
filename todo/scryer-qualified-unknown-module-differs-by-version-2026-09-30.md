# Scryer's answer for a qualified call into an UNLOADED module differs by version

**Filed:** 2026-09-30, engine lane. **Ruled for now:** Clausal KEEPS existence_error for
`zz:assertz(foo(1))` when no module zz is loaded.

Measured:

    scryer-prolog cargo 0.10.0 (operator's)   -g "zz:assertz(foo(1))."
        -> error(existence_error(procedure,zz:assertz/1),assertz/1)
    /workspace/scryer-prolog-clpq (9acba77a, upstream master + CLP(Q)), -g
        zz:assertz(foo(1)), zz:foo(X)  -> ok(1)
        zz:atom_length(abc, N)         -> ok(3)

Clausal today: zz:atom_length(abc, N) answers 3 (like master); zz:assertz raises (like 0.10.0).
Open: which Scryer is the reference (release vs master), then make the two cases consistent.

**2026-09-30:** the operator asked Markus Triska, who did not know and suggested asking
Ulrich Neumerkel (ISO); the operator sees him in a few weeks. A bisect agent is finding the
Scryer commit that changed it (report: engine-lane scratchpad `scryer-bisect-report.md`);
bring that commit + the old/new table to the question. Until then Clausal KEEPS the error.

**RULED 2026-09-30 (operator, final):** Clausal KEEPS existence_error for a database builtin
called through an unknown module ("it's my Prolog after all"). The Neumerkel question is
now informational, not blocking. Still open: `zz:atom_length(abc, N)` answers 3 today;
decide whether pure builtins through an unknown module should raise too, for consistency.

**CORRECTION 2026-09-30 (bisect):** NOT a version difference. v0.10.0 (crates.io + source),
upstream 3e2f3ecf and our 9acba77a all agree. The split is COMPILE-TIME vs RUN-TIME
qualification in Scryer: a literal `zz:assertz(..)` inside a compiled clause/goal body
creates module zz (load_state.rs get_qualified_clause_type -> add_dynamically_generated_module)
and builtins ignore the qualifier; a goal reached at run time (bare `-g Goal` runs as
catch(user:Goal,...), or `G = zz:.., call(G)`) raises existence_error(procedure, zz:F/N).
Upstream issue #2826 (open since Feb 2025): "Module qualifications are resolved at compile-time,
and variable module qualifications are just ignored". So Scryer is not a reliable reference
here; Clausal's ruling (error) stands. Full report: engine-lane scratchpad scryer-bisect-report.md.
