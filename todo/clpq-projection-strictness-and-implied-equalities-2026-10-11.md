# CLP(Q) answers: strictness through projection, and implied equalities

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
