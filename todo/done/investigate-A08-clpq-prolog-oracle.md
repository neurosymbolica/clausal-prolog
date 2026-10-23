# investigate(A08, Opus): no Prolog CLP(Q) oracle runnable — differential classes untested

**Status: RESOLVED 2026-10-20 (commits 5bf74404, d6adc770, 232fa1fd).** A CLP(Q) oracle now runs: Scryer built with library(clpq) (tests/_oracles.py `SCRYER`), driven by tests/clpq_oracle.py, which compares answer sets, inf/sup and residual constraints by z3 equivalence. The port of clp(q,r) 1.3.3 (`CLAUSAL_CLPQ=holzbaur`) is checked against it, and the random-store classes below are fuzzed (tests/clpq_port/fuzz/: LP against scipy, projection, strictness against z3, undo with replay). Pinned in tests/clpq_port/test_against_oracle.py and tests/clpq_port/fuzz/test_fuzz_strictness_against_z3.py (216 passed 2026-10-20). Gaps the oracle found are in todo/done/clpq-port-vs-sicstus-manual-23-gaps-2026-10-16.md.

**Context:** A08 audit oracle gap (2026-07-05).

`scryer-prolog` is on PATH but ships no `library(clpq)` (only clpz/clpb);
gprolog is not installed and has no CLP(Q) either; `prolog_backends/` contains
only build scaffolding (a gprolog C extension and a scryer Rust crate), no
CLP(Q) library. SWI (GPL CLP(Q) port) and SICStus (proprietary) are absent.

The A08 findings were confirmed with hand-checkable Fraction arithmetic and
unambiguous unsat systems instead. Differential classes that still lack an
executable reference and should be swept once an oracle (SICStus, SWI, or
CLP(B,Q,R)-capable Scryer build) is available:

1. `dump_q/2` projection format + completeness vs SICStus `dump/3`
   (Fourier–Motzkin result equivalence on random polytopes).
2. `entailed/1` corner semantics (strict, diseq, mixed) vs SICStus.
3. `sup/inf` attainment semantics with strict constraints
   (`{X<5}, sup(X,S)` — S=5 non-attained) and `maximize` failure modes.
4. Coefficient-growth stress (Newton sqrt(2) iterations) — answer equality
   at every step, not just termination.
5. Random linear-system satisfiability fuzz (post k random eq/le/lt over
   n vars; diff sat/unsat + solution point) — would have caught A08-F001/2/3/4
   mechanically.

Suggested harness: generate SICStus/SWI `{...}` goals + matching clpq.py
posts from one seed; compare sat, bindings, sup/inf.
