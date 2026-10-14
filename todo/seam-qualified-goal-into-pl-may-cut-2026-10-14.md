# A `.seam` goal qualified into a `.pl` module may cut there: ruling wanted

**Status: OPEN, a question for the operator. It was found while pinning the D59 boundary (Task 6 of the `.pl` cut series), 2026-10-14. Nothing leaks into `.clausal`.**

## What happens

A `.seam` module may call a `.pl` module; D59 refuses only the `.clausal` → `.pl` edge. Here `cg1(G) <- call(G)` is in a seam module, and `plcut` is a `.pl` module with `p(1). p(2). p(3).`:

    cg1(plcut:(p(X), !))           % 1 answer: the body is converted against plcut's db and cuts
    cg1(plcut:cutter((p(X), !)))   % 1 answer: cutter(X) :- call(X), !.  a .pl predicate calling its argument
    cg1((plcut:p(X), !))           % existence_error(procedure, !/0): the seam's own body
    cg1(plcut:(p(X), seamcut:!))   % 3 answers: a cut qualified to the seam module is true

The engine's rule is that `M:G` runs G as M's goal, so the db that G is converted against is M's (`call_body.cut_allowed`). Every such cut is local to the call (ISO 7.8.3). It cannot prune the seam caller's choice points, but the seam program does observe committed-choice answers for a body it built itself.

Pinned as-is in `tests/iso_l3/test_l3_cut_boundary.py::test_seam_qualifying_into_a_pl_module_runs_as_that_module`.

## The question

Should the CALLER's surface also gate `M:Body` when Body is a control construct, so that `cg1(plcut:(p(X), !))` from a seam module is `existence_error(procedure, !/0)`?

- **Against:**
  - `plcut:cutter(G)` and `plcut:call(G)` give a seam module the same reach through any `.pl` predicate.
  - Closing only the `:`/2 form would not close the reach.
- **For:** "`.seam` stays cut-free on every path" read literally.

If the answer is yes, the fix is in the qualified-goal resolution: it would pass the caller's db to `cut_allowed` for the body conversion. It is not in `cut_allowed` itself.
