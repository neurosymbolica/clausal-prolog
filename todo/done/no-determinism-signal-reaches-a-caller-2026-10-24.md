# No determinism signal reaches a caller: a top-level cannot tell an answer is the last

**Status: FIXED 2026-10-24 (commits 22a7e853, 45481f41, 4324fe09).** Option 2
(producer-side FINAL plus frame forwarding) was taken whole, not staged:
`solve_with_last` / `call_with_last` report `last`; builtins and compiled
clauses emit FINAL; a tail call's FINAL holds only through frames that set
`StepGenerator.tail_final` (the drive core's `final_holds`); a woken-goal
drain or a catcher-resumed step makes an answer plain; retired roots are
undone by their drivers. Pinned in tests/test_solve_with_last.py,
tests/iso/test_last_answer_scryer.py, tests/test_solve_with_last_property.py
and tests/test_trampoline_parity.py. The remaining conservative cases
(catch/3, if-then-else with an else, setup_call_cleanup/3, tabled calls)
are in todo/final-answer-not-known-through-catch-ite-else-and-cleanup-2026-10-24.md.

Filed 2026-10-24, found while building an interactive top-level. Not a
correctness bug: every answer is right. Severity: cosmetic at a top-level,
plus one redundant protocol hop per semi-deterministic call everywhere.

## What / Repro

A caller learns that a goal has no more answers only by asking for the next
one and getting failure. So a top-level prints an answer, waits for `;`, runs
the goal again, and only then prints `false.`:

```
?- member(X, [a,b,c]).          ?- X = 1.
X = a ;                         X = 1 ;
X = b ;                         false.
X = c ;
false.
```

Scryer and Trealla end with a full stop on a deterministic last answer, and
never ask:

```
?- member(X, [a,b,c]).          ?- X = 1.
   X = a                           X = 1.
;  X = b
;  X = c.
```

`clausal/repl.py` (`Solutions._run`) gets the `.` today by computing the next
answer before printing the current one. That works for `X = 1`, but it runs
the goal one step further than the user asked. On `repeat, write(x)`, on a
slow next answer, or on a side effect in the next branch, the user sees work
done before they type `;`. A top-level that asks first can't use it.

## What exists

The protocol half is in place; no producer uses it.

- **`FINAL`**: the third yield sentinel, beside `None` (a solution, there
  may be more) and `DONE` (no more answers). `yield (proceed, FINAL)` means
  "here is a solution, and I am retiring". Defined in
  `clausal/logic/_trampoline_py.py` (the `DONE / FINAL sentinels` block,
  about line 100) and `clausal/logic/runtime/_trampoline.c` (`g_FINAL`).
- **Root retirement**: `StepGenerator.retired` (Python slot, and the C
  `retired` field with its getter and setter). When the drive core sees
  `(None, FINAL)` at the root, it sets `root.retired`. After that a pull
  answers exhaustion without resuming the generator (`_drive_until_yield`,
  `solutions`), or raises a protocol error for `trampoline()`.
  `tests/test_trampoline_parity.py` keeps the C and Python versions in step.
- **Nothing emits it.** There are no `FINAL` yields in
  `clausal/logic/compiler/`, `clausal/logic/builtins/` or the C builtins.
  Compiled frames, `_simple_to_trampoline` (`builtins/_registry.py`) and
  `solve.py`'s `_drive_trampoline` never test for it either.
  `_drive_trampoline` yields the trail per answer, and has no way to say
  "this was the last".
- **The design**: `implementation_plans/compiler/todo/commit_yield_determinism.md`
  (the "commit" variant: what it means, where it comes from, how it is
  encoded) and `implementation_plans/compiler/CONTINUATION_TCO_PLAN.md` §3.4,
  §5.2, §6 Phase 4 and §10 (status: Phase 4 stopped after the sentinel and
  root-driver handling; the analysis and the lowering that would emit
  `yield (_proceed, FINAL)` are not written). Those documents describe the
  saved hop. They do not describe what a caller is told, which is what this
  todo adds.

## What the plans do not cover

### (a) How a conjunction's answer becomes FINAL at the root

A leaf's `FINAL` says nothing about the goals before it. In
`member(X, [a,b]), Y = 1`, the unification `Y = 1` is deterministic every
time, but the answer `X = a` is not the last: `member/2` still has `b`. The
rule:

> An answer is FINAL at the root only if every producer still on its fail
> chain has retired: each earlier goal in every enclosing conjunction answered
> FINAL, and no clause alternative, disjunct or catch frame still has a
> choice point.

Under the split-continuation protocol this check has a concrete form, and
TCO causes a specific hazard:

- **At a normal call site** the callee yields to its own frame, which sees
  `FINAL` as the value it was sent. That frame forwards `FINAL` upward only
  if it has no alternatives of its own: all its earlier subgoals were final,
  it is in its last candidate clause (indexing included), and it is not
  inside an open disjunct. Otherwise it forwards a plain `None`.
- **At a TCO site** `proceed` skips the caller's frame. So a tail callee
  that yields `FINAL` reaches the caller's caller, or the root, without
  passing the frame that holds the earlier choice points. Today that frame
  would retire the root and silently lose answers. A TCO site therefore has
  to do one of two things: pass the callee a flag saying "your FINAL is
  valid only if I am final too" (the caller knows this when it makes the
  call: it is final up to here exactly when its earlier goals were final),
  or downgrade `FINAL` to `None` on that path. The first keeps TCO's
  benefit. The second is simpler.
- **Retired producers never undo.** Producers undo their own bindings when
  they are resumed (`trail.undo(mark)` after each `yield`), and a retired
  producer is never resumed. So whatever goes past it on the way back must
  undo through an enclosing mark. That holds at the root, because `solve`
  owns the trail. For a mid-chain `FINAL` it has to be checked frame by
  frame.
- **Things that delay finality**: a pending-goal drain on the trail (a
  woken attribute goal with several answers; `StepGenerator._drain`) makes
  an answer non-final. So does a tabled call that is not complete. Inside
  `findall/3`, `forall/2`, `\+` and `once/1` the signal is used up by the
  construct itself: `once/1` makes its answer FINAL whatever the inner goal
  said. That is also the cheapest source of FINAL there is.

### (b) Which builtins could emit FINAL dynamically

Scryer and Trealla print `X = c.` for `member(X, [a,b,c])` because the
clause indexing in their WAMs leaves no choice point on the last element.
Here, the builtins that know their last answer are:

| Builtin | Last answer when |
|---|---|
| `member/2` (`in_/2`) | at the last element of a proper list; never on a partial list |
| `between/3` | `X =:= High`; check mode is always final |
| `select/3`, `selectchk/3` | at the last element of a proper list |
| `nth0/3`, `nth1/3` | index bound: always final; enumerating: at the last element |
| `append/3` | first list proper (the split is fixed); when splitting, at the last split |
| `length/2` | list proper, or length bound |
| `clause/2`, `retract/1`, `current_op/3` | at the last matching row of the snapshot |
| `sub_atom/5` | at the last (B, L, A) candidate |
| `repeat/0` | never |
| every semidet builtin (`=/2`, `is/2`, type checks, comparisons, `functor/3`, `arg/3` with N bound, `atom_codes/2`, ...) | always |

The simple-mode adapter `_simple_to_trampoline` cannot emit FINAL: its
generator undoes its bindings before it can learn that it is exhausted. It
needs a variant for semidet builtins (a registration flag saying "at most one
answer") so it can yield `FINAL` instead of `None` and skip the trailing
`DONE` pull.

### (c) A cheap first step for the common top-level cases

Most top-level queries are a single call, or a conjunction of semidet
builtins with at most one nondeterministic goal, last. These steps cover them
without touching compiled-predicate code:

1. **The drive loop tells its caller.** `_drive_trampoline` (or a sibling
   that the top-level uses) reports `sg.retired` along with each answer, for
   example `(trail, is_last)`. No engine change; with no producer emitting
   FINAL, it is always `False`.
2. **Semidet builtins and `once/1` emit FINAL** through the flagged adapter
   from (b). A query made only of semidet goals (`X = 1`, `X is 2 + 3`,
   `atom_length(abc, N)`) then reaches the root as FINAL, provided the
   top-level calls it as a conjunction whose frames forward FINAL under
   rule (a). At first that means only the query's own conjunction frame,
   which the top-level owns. Compiled predicates keep yielding `None`, which
   is always safe.
3. **`member/2` and `between/3` emit FINAL** at their last answer, under the
   same rule. That covers the `X = c.` case.

Compiled user predicates come later, with the structural analysis in
CONTINUATION_TCO_PLAN Phase 4 (last yield of the last clause, after indexing).

## Options

1. **Look-ahead in the top-level** (what `repl.py` does now). No engine
   change. But it runs the goal one step early (side effects, `repeat`,
   cost), so an interactive top-level that waits for `;` can't use it.
2. **Producer-side FINAL plus frame forwarding (rule a).** The real fix, and
   the one the existing sentinel and the root retirement were built for. It
   is a protocol change across compiled frames, both trampolines and the
   TCO sites, so it is large if done all at once.
3. **Staged: step (c) first.** The root reports retirement. Semidet
   builtins, `once/1`, `member/2` and `between/3` emit FINAL. Only frames
   the top-level builds forward it. Compiled predicates come later through
   the Phase 4 analysis.

**Recommendation: option 3.** It reuses the sentinel and root handling that
already exist and covers the common top-level answers (`X = 1.`,
`X = c.` for member, `N = 3.` for atom_length). It is safe by
construction: anything that does not opt in keeps yielding `None`, and the
worst case is the current behaviour. It also leaves the hard parts (TCO
sites, the frame forwarding rule in generated code) to the plan that already
owns them.
