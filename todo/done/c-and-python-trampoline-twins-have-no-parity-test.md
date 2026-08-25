# The C trampoline and its pure-Python twin are kept in sync by comment only

**Filed:** 2026-08-26, from the `catch/3` review (`883cdf08`).
**Status: DONE 2026-08-26** — see docs/superpowers/specs/2026-08-26-one-drive-loop-design.md
and the commits it names.

## Closing note

`f2f348c5` added `tests/test_trampoline_parity.py`, a single module running a
32-case behavioural corpus against both the C extension and the pure-Python
twin (`ffd406b2` extracted the twin into `clausal/logic/_trampoline_py.py`).
The corpus found and fixed exactly the one pre-existing divergence: a
returning inner generator raised the marked engine-protocol `RuntimeError` on
the C side but surfaced a bare `StopIteration` on the Python side, recorded in
Task 4's report. Mutation-checked in both directions — deleting a routing
branch from either implementation reds the module — satisfying both
acceptance criteria.

## The situation

`logic/trampoline.py` imports the C extension and falls back to pure-Python
definitions of `trampoline`, `solutions` and `_drive_until_yield` on
`ImportError`. In any built tree the C extension always wins, so **the Python
fallbacks are never executed by the suite**. Their correctness is maintained by
a `KEEP IN SYNC with …` comment on each side and by whoever edits one
remembering the other.

The routing fix had to edit both. The C half was verified by the whole suite;
the Python half was verified by reading it, plus one manual meta-path-blocker
run that is not a test.

This is the same shape as the twins already flagged elsewhere in the tree
(`is_routable_exception` ↔ `_is_routable`, `is_pep479_stopiteration_wrapper` ↔
the inline `__cause__` check), and it is only going to grow if
[[one-drive-loop-not-six]] lands as a C refactor.

## What a fix looks like

A parity harness that runs a shared behavioural corpus against **both**
implementations in one session: block `clausal.logic.runtime._trampoline` in
`sys.modules`, reload `logic.trampoline`, and re-run the same cases. The
obstacle is that compiled predicates capture `StepGenerator` in their globals
table at compile time (`logic/compiler/predicate.py:746`), so a fixture
compiled against the C type will not simply re-drive under the Python one —
the harness has to force recompilation too, or drive hand-built
`StepGenerator` chains rather than compiled predicates.

Cheaper interim: mark the Python fallbacks as untested in their docstrings so
the next reader does not assume suite coverage they do not have.

## Acceptance

- One test module exercises both implementations over the same cases.
- Deleting a routing branch from EITHER implementation reds that module.

Related: [[one-drive-loop-not-six]]
