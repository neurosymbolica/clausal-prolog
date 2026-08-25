# The trampoline drive loop exists six times, and each copy learns fixes separately

**Filed:** 2026-08-26, from the `catch/3` fix (`463291d6`) and its review
follow-up (`883cdf08`).
**Status: DONE 2026-08-26** — see docs/superpowers/specs/2026-08-26-one-drive-loop-design.md
and the commits it names.

## Closing note

Landed as one core per language with stop-condition wrappers:
`08e066a0` (C: `drive_to_root_yield`, constprop'd single copy) and
`213371b8` (Python: `_drive_to_root_yield` + wrappers), with `4224094d`
re-basing `_tramp_call`/`_naf_has_solution` on the shared core. The general-ITE
arm was the seventh, previously-unrouted inline copy — found and fixed by
`35ad41df`, which routes it through `$drive_until_yield` instead of emitting
its own loop. All three acceptance criteria are met: an exception-policy or
protocol change now touches one site per language, no drive loop is emitted
as generated AST, and the audit (spec addendum) is recorded.

## What the two fixes showed

Broadening `catch/3` routing from `LogicException` to every routable exception
had to be applied, by hand, to every one of these:

| copy | where |
|---|---|
| `trampoline_func` | `logic/runtime/_trampoline.c` |
| `solutions_func` | `logic/runtime/_trampoline.c` |
| `drive_until_yield_func` | `logic/runtime/_trampoline.c` |
| `trampoline` / `solutions` / `_drive_until_yield` | `logic/trampoline.py` (pure-Python twins) |
| `_tramp_call` | `logic/runtime/tramp_call.py` |
| the `Negate` mini-trampoline | `logic/compiler/lower_python_trampoline.py`, emitted as **generated AST** |

The first fix reached four of them and **missed two**: `_tramp_call` had never
had routing at all, and the `not` lowering emitted its own loop inline, so a
`catch/3` inside a negated goal was inert. Neither gap was visible from the
others — each was found only by someone writing a test for that specific
driver. `_naf_has_solution` now lifts the `not` loop out of codegen, but that
is five copies, not one.

## Why it keeps happening

A drive loop is three decisions braided together: the *step protocol* (send a
`(gen, value)` pair, interpret `DONE`), the *stop condition* (first solution,
all solutions, one solution, existence), and the *exception policy*. Only the
stop condition actually differs between the copies. The other two are
duplicated, and a change to either has to find all six sites.

The `Negate` case is the sharpest: engine control flow emitted as AST cannot be
grepped for alongside its siblings, and no test of the runtime can reach it.

## Proposal

One parameterised loop — protocol and exception policy in a single place, stop
condition passed in. The C extension is the implementation that actually runs,
so this is a C refactor with the Python twins following (see
[[c-and-python-trampoline-twins-have-no-parity-test]]).

Worth doing as part of it: audit the other lowerings in
`logic/compiler/lower_python_trampoline.py` and `logic/compiler/goal_*.py` for
any further engine control flow emitted as AST rather than called as a runtime
helper. `Negate` was found by accident; nothing says it is the only one.

## Acceptance

- A new exception-policy or protocol change touches one site.
- No drive loop is emitted as generated AST.
- The audit above is recorded, with whatever it finds either fixed or filed.

Related: [[c-and-python-trampoline-twins-have-no-parity-test]]
