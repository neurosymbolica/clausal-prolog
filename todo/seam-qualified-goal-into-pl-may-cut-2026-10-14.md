# A goal relayed through `.seam` into a `.pl` module may cut there, including one a `.clausal` module built: ruling wanted

**Status: OPEN, a question for Mike.** Found while pinning the D59 boundary in Task 6 of the `.pl` cut series (2026-10-14), and widened by the Task 6 review. The coordinator ruled it is not a blocker for the series: the relay predates the series, the cut runs inside `.pl` code, and the sandbox refuses the route. Today's behaviour is pinned, not blessed.

## What happens

A `.seam` module may call a `.pl` module; D59 refuses only the direct `.clausal` → `.pl` edge. The edge gate checks the IMMEDIATE caller, and a `.seam` frame is ungated in normal mode (`dialect_edge.py`: "the programmer's responsibility"). `M:G` converts G against M's db (`call_body.cut_allowed`), so when M is a `.pl` module, a cut or if-then-else in G runs there, local to that call (ISO 7.8.3). It cannot prune the caller's choice points; its power is that of `once/1`.

### 1. From `.seam` directly

Here `cg1(G) <- call(G)` is in a seam module, and `plcut` is a `.pl` module with `p(1). p(2). p(3).`:

    cg1(plcut:(p(X), !))           % 1 answer: the body is converted against plcut's db and cuts
    cg1(plcut:cutter((p(X), !)))   % 1 answer: cutter(X) :- call(X), !.  a .pl predicate calling its argument
    cg1((plcut:p(X), !))           % existence_error(procedure, !/0): the seam's own body
    cg1(plcut:(p(X), seamcut:!))   % 3 answers: a cut qualified to the seam module is true

### 2. From `.clausal`, relayed through any `.seam` meta-call (review Gap 1)

No user seam code is needed: the shipped `library(reif)` `cond_t/3` (`clausal/stdlib/reif.seam`) calls its goal argument. `pls.pl` here is cut-FREE (`p(1). p(2). p(3).`):

```prolog
% cls.clausal
:- use_module(library(reif)).
r_cond_t(L)     :- G = (p(X), !),             findall(X, cond_t(=(true), pls:G, _), L).
r_cond_t_ite(L) :- G = (p(X) -> true ; true), findall(X, cond_t(=(true), pls:G, _), L).
r_cond_t_ctl(L) :-                            findall(X, cond_t(=(true), pls:p(X), _), L).
% a user seam relay, seams.seam:  cg1(G) <- call(G),
r_seam_relay(L) :- G = (p(X), !), M = seams, findall(X, call(M:cg1, pls:G), L).
```

| Engine | r_cond_t | r_cond_t_ite | r_cond_t_ctl | r_seam_relay |
|---|---|---|---|---|
| this series, normal | `[1]` (the `.clausal`-built cut ran) | `[1]` (commit ran) | `[1,2,3]` (D59 edge crossed) | `[1]` |
| this series, sandbox | `permission_error(access, prolog_module, pls)` | same | same | same |
| canonical main ebf205fb (pre-series), normal | `existence_error(!/0)` | `existence_error(->/2)` | `[1,2,3]` | — |

So the `.clausal` → seam → `.pl` crossing is older than this series (the ctl column on main). This series is what makes it a CUT route.

**Pins:**
- normal mode: `tests/iso_l3/test_l3_cut_boundary.py::test_clausal_relays_a_cut_into_pl_through_a_seam_meta_call` and `::test_seam_qualifying_into_a_pl_module_runs_as_that_module`;
- sandbox: `tests/test_sandbox.py::test_the_sandbox_refuses_the_clausal_seam_pl_relay`.

It is NOT true that nothing leaks into `.clausal`. A `.clausal` program can observe committed-choice answers for a body it built itself, by handing it through a seam meta-argument. That is at odds with D59 ("Clausal Prolog may never call a `.pl` module ... strict for closures too").

## The questions for Mike

1. Should normal-mode `.seam` relay `.clausal`-built goals into `.pl` at all, and should the shipped `library(reif)` do so?
2. If not, which mechanism?
   - **(a)** A goal or closure that a `.clausal` caller passes through a seam meta-argument keeps the ORIGINATING caller's gate: its meta_predicate context, so `pls:G` built in `.clausal` is refused wherever it is finally called.
   - **(b)** A seam frame called from `.clausal` is itself gated, as it is in the sandbox (`sandbox.gated_caller`).
3. For a `.seam` caller's own goals: should `M:Body` with a control-construct Body be gated by the caller's surface, so that `cg1(plcut:(p(X), !))` is `existence_error(procedure, !/0)`?
   - **Against:** `plcut:cutter(G)` and `plcut:call(G)` give the same reach through any `.pl` predicate that calls its argument, so closing only `:`/2 would not close the reach.
   - **For:** "`.seam` stays cut-free on every path" read literally.

**Where a fix would go:**
- (a) in the meta-argument qualification (`meta_predicate.qualify_args`) and the edge gate;
- (b) in `dialect_edge.refuse_edge`'s caller test;
- question 3 in the qualified-goal resolution.

None of them is in `cut_allowed`.
