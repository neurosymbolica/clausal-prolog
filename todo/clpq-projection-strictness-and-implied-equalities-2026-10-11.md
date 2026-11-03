# CLP(Q) legacy solver: implied equalities are not found

**Status 2026-11-03: legacy only.**  Under `CLAUSAL_CLPQ=holzbaur` both
gaps are closed: the port gives Scryer's answers through the Python-API
driver (`residual_strings`), the `clausal -g` printer, `dump/3` and
`dump_q`, with no change to the port.  Strictness through projection is
also fixed on legacy (459cd660, "legacy keeps strict bounds in the
simplex": the projection carries `<` through Fourier-Motzkin).  What is
left is implied equalities on legacy:
`{X =< Y, Y =< 3, X >= 3}` and `{X - 2*Y =< 0, Y =< 1, X >= 2}` still
leave X and Y unbound there.  Legacy does find the case where an equation
substitutes into a bound so a variable's own bounds meet
(`{X + Y = 4, X =< 2, Y =< 2}`).  Pinned by
`tests/clpq_port/test_projection_strictness_and_implied_equalities.py`
(15 queries against the Scryer oracle; the legacy implied-equality cases
are `xfail(strict=True)`, so a legacy fix shows as XPASS).  Not fixed on
legacy: it needs an entailment LP per variable after each post, which is
not small, and legacy is to be replaced by the port
(implementation_plans/clpq/2026-11-03-default-solver.md).  Close this when
the port becomes the default.

The original note (2026-10-11, written against legacy) follows.

## CLP(Q) answers: strictness through projection, and implied equalities

Two gaps in how `dump_q/2` and `clausal -g` show the CLP(Q) store.  Both
answers are true, but weaker than Scryer's.

**Strictness is lost when it passes through an eliminated variable.**  A
strict `<` is stored as `=<` plus a disequality.  Projection
(Fourier-Motzkin) carries the `=<`, but a disequality over an eliminated
variable cannot be projected, so it is dropped:

    {X < Y, Y =< 3}  onto X   ->  {X =< 3}      (Scryer: X < 3)

The fix is to give each constraint a strict flag through elimination
(a combination is strict when either source is).  The flag would come from
the bound or slack row the strict post created, not from the stored
disequality.

**Equalities the store implies are not found.**  When the bounds force a
value, the variable stays unbound:

    {X =< Y, Y =< 3, X >= 3}  ->  {X - Y =< 0}, {X >= 3}, {Y =< 3}.
                                   (Scryer: X = 3, Y = 3.)

Only a variable's own bounds meeting (lo == hi) is detected.  A bound
implied through rows is not.  Holzbaur's solver finds these by
detecting implied equalities after each change.

The disequality check (`Tableau._check_diseqs`) has the same gap, but it
already finds it by entailment: an LP for the minimum and maximum of each
disequality's expression.  The same LP per variable would find implied
equalities, at a cost per post.
