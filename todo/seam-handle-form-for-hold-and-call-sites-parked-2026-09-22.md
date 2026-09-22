# The `--handle(X)` form for hold-and-call sites — PARKED (operator, 2026-09-22)

**Ruling:** for W4, the downstream hold-and-call sites (31 sites in 5
bodies) migrate by writing the RAW goal tuples — `("name", args...)` solved
with `module=` explicit, the all-solve convention those bodies already use;
after W4 a kept attribute read `m.pred` is the module-qualified atom and
`(m.pred, args...)` resolves with no `module=`. The `--handle(X)` wrapping
form is NOT used for them for now. This todo is the place to look at it
again.

**What exists, built and gated, NOT landed:**
`feat/seam-local-handle-2026-09-22` at 7d843d35 (house NEW 0 / GONE 0,
package NEW 0 / GONE 0, roborev 83 closed):

* the seam reads a functor name that is a Python LOCAL (function local,
  parameter, lambda parameter, comprehension target) by its VALUE, instead
  of resolving names against module globals only (which raised NameError,
  or under `-implicit_functors` silently built a cell named after the
  VARIABLE);
* a HANDLE CARRIES ITS MODULE: a class-built handle cell is
  `(":", <the class's module>, (name, args...))`; a mangled-atom handle says
  the same in one spelling; goal position builds the goal through the seam
  builder so it runs in the handle's module, not the host's;
* `seam.dotted()` read `.value` off a `LoadAttr` whose base field is
  `.object` — `--m.pred(X)` in a hosted `.clausal` module crashed; FIXED on
  that branch (todo/seam-dotted-base-fails-in-a-hosted-module-2026-09-22.md
  stays open on main until something lands it — that fix is worth landing
  on its own if the rest stays parked);
* the measured constraint (the downstream lane, on 7d843d35): a `--` cell
  handed to `solve()` keeps plain-`str` atoms; the ITERABLE/test form of a
  seam is goal position and EXPORTS (`atom`-tagged) — so if the form is
  ever adopted the rule is **wrap the call, never the iterable**, until
  `todo/two-out-paths-disagree-about-atom-tagging-2026-09-22.md` is ruled.

**Why parked, in the operator's words:** "for now, for W4, just write the
raw tuples". The raw form needs no engine change, touches no boundary, and
is already the bodies' convention.

**When to look again:** after W4 proper (the head channel, the class,
handles minted with the IMPORT name), when the two-out-paths question has
a ruling — the seam form is the ergonomic one and the branch carries the
work. Rebase it then; the review notes are in its commit messages.
