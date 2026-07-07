# fix(A06-F012): zcompare — order var binding propagates nothing; X≡X not inferred

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/06-clpfd/findings.md A06-F012
**Tests:** tests/audit_2026_07_05/test_06_clpfd.py::TestZcompare (2 xfail — flip to pass)

## Bug (sound, but propagation missing)

1. `zcompare(O, X, Y)` attaches ZcompareConstraint only to X and Y
   (clpfd.py:2719-2730). Binding O afterwards (`O is '<'`) fires no hook —
   X/Y domains untouched until some X/Y event re-runs the propagator. SWI
   narrows immediately. Labeling stays sound (final grounding re-checks).
2. `zcompare(O, X, X)` (aliased operands) leaves O unbound — the var-order
   branch (clpfd.py:2561-2570) requires both singletons; identity implies '='.

## Fix direction

1. Attach a wake-up to the order var too: O is bound to a STRING, so the FD
   attr is wrong; either use a dedicated lightweight attr hook key (like
   dif's) that re-runs the constraint, or wrap O in a one-shot coroutining
   hook. Mind A04-D001 (boolean hook protocol) — the re-run is semidet,
   which is fine here.
2. In propagate's var-order branch: `if x is y: return unify(order, '=', trail)`.

## Acceptance

- Both xfails pass; the four zcompare guards (ground directions, determined
  by binding, soundness after labeling) stay green.
