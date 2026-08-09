# No differential checker between the prover's front end and the engine's

**Filed:** 2026-07-30, splitting the one unstarted idea out of
`todo/done/smt-prover-front-end-seam.md` before archiving it as a decision
record.

The decision recorded there stands and is implemented: the SMT prover keeps its
own front end deliberately, and the only thing shared with the engine is the
narrow surface-desugar pass (`clausal/templating/desugar.py`, consumed by the
engine at `clausal/templating/term_rewriting.py:636` and by the prover's own
front end, maintained by a downstream consumer, at its `ir.py`). Do **not**
reopen that as "duplicated parsing to be unified" — see the archived file for
why.

The consequence the decision accepts is that the two front ends can drift, and
nothing currently detects drift. The unbuilt idea: a checker that parses the same
`.clausal` file both ways and compares *shape* — clause count, per-clause head
functor/arity, goal count and goal functors — failing on any divergence.

Note what does **not** already cover this:
the downstream consumer's own translate-differential test is a *semantic*
engine-vs-SMT differential (same answers), not a front-end shape comparison. A
clause the prover silently fails to parse at all can pass a semantics
differential by vacuity, which is exactly the failure mode a shape check would
catch.
