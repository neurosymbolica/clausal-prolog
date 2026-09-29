# Engine lane handoff — 2026-09-13 (second session of the day) END

Continues `SESSION-HANDOFF-2026-09-13-engine-lane-END.md`. Short session: one landing, two
measurement arms closed by peers, one operator ruling obtained.

## State

    canonical main   c71810ec    was 750e6ae1 -- plain ff, 4 commits
    clone main       c71810ec    identical
    box                          STILL UNTOUCHED, still on the old vocabulary

## What changed

**The minor-unit float defect is now ON canonical.** `b7e6feeb` had been sitting on the clone only,
so canonical was serving a known defect: `155000 aud_cent` is `Decimal('1550.00')`, exactly 1550,
and the emitter wrote a Prolog FLOAT.

Verified by OBSERVATION, in this order, before and after:

    before   fixed tests vs canonical's engine    4 failed / 123 passed
    after    same probe, same tree                127 passed
    hashes   engine file, canonical == clone      e2163a64...

The probe was the clone's two fixed test files copied to a job dir and run with cwd in the target
tree, which is how you test one tree's code against another tree's expectations.

## Both missing measurement arms are CLOSED, and both peers beat my reasoning

**A downstream user — export bytes: `cc008788` vs `c71810ec`, every exported file, raw 0, normalised 0**,
141 errors under both. Wider than the five unmeasured commits, so a zero covers them. They
**disabled their own in-flight change (`be454bb`) for the arm**, which is the discipline: a second
variable moving inside a measurement of the first answers neither question. Their recorder read
"engine 25 commits behind" before the run — an instrument that reports what it is ACTUALLY
measuring.

**A downstream checker — the domain axis is vacuous in the STRICT sense.** My argument was "no corpus
file declares a constant". Theirs was better and they said so: **that is a claim about DOWNSTREAM CODE;
reachability is decided by the IMPORT GRAPH.** They measured it — atexit hook on `sys.modules` over
a real scored domain (crr_lcr, 33/33): CHANGED modules imported NONE, any `clausal.tools.*` at all
NONE; 0 of N harnesses and 0 rulebases reference the exporter. **My reasoned version is retired,
not kept alongside.**

## THE RULING — non-integer arithmetic surface, DIRECT

**`{...}` in goal position is a SET OF CONSTRAINTS; calling the goal solves them. Fractional
arithmetic goes to CLP(Q) through it. The `arithmetic(...)` / `z3.`-precedent alternative is
CLOSED.**

Obtained by asking the operator directly, both candidates side by side. This was the right move and
the pattern is worth more than the answer: **two second-hand accounts of the SAME operator, minutes
apart, describing DIFFERENT surfaces.** a downstream user had `{...}` relayed; this lane had
`arithmetic(...)` raised. Neither lane should pick between two second-hand accounts of one person.

**He priced both costs before ruling, so neither reopens it:** it re-purposes the set literal, and
**CLP(Q) is in NEITHER ladder engine** (Scryer `existence_error`; Trealla warns and provides
nothing, `{}/1` missing; only the branch build at `/workspace/scryer-prolog-clpq` has it). The
availability gate is an implementation problem, not grounds to reopen.

Relayed to a downstream user marked DIRECT so they need not ask again.
`todo/non-integer-arithmetic-surface-and-export-2026-09-13.md` updated in place.

## The census that sizes the remaining risk (a downstream user's, and it is the best artefact of the day)

    924  VAR == <rhs> sites in corpus source
    886  plain, no division
     20  integer division //      safe under clpz
     18  TRUE division /
           6  divisor IS a unit   -> removed by the divisor-fold fix
          12  GENUINE arithmetic  -> would SILENTLY STOP FIRING under a blind #=

`OVERHEADS #= OVERHEADS_TOTAL / 4` fails whenever the total is not divisible by four. No error, no
answer — and **for a legal rulebase "no answer" is indistinguishable from "the rule correctly did
not apply"**, which is worse than a wrong number. **Convert those twelve LAST.**

## Corrected a stale memory of this lane's own

`ratio-units-status` asserted the exporter REFUSES ratio units, so `<downstream-domain>` stayed
blocked. **False as of option 3.** Checked by RUNNING it, not by reading:

    _unit_factor(['percent'])      -> Decimal('0.01')
    _unit_factor(['basis_point'])  -> Decimal('0.0001')
    _unit_factor(['nonesuch_xyz']) -> None          (the refusal that should remain, remains)

**`<downstream-domain>` is UNBLOCKED** — 21 pairs across several domains, a downstream user's migration, not this
lane's. The memory had stated a REFUSAL as a standing property of a tree and it went stale in ONE
DAY. State the CHANGE; carry the command that re-measures it.

## Method: four more instruments that failed open, in one short session

The count from the previous handoff was six. It is now ten, and every one reported success.

1. **`nohup … &` reported exit code 0 while pytest was still in COLLECTION.** The harness faithfully
   reported the wrapper's exit, not the run's; the log was zero bytes. Twice.
2. **147 failures, ZERO names extracted** — ANSI colour codes in the log. `grep '^FAILED '` matches
   nothing when the line begins with an escape sequence. Caught ONLY because the extraction printed
   its own count as a positive control. Strip with `sed -r 's/\x1B\[[0-9;]*[mK]//g'` first.
3. **A failure-set diff against an UNFINISHED run** — 147 vs 0 "differences", all of them artefacts
   of the other side not having reached its summary. The control that caught it was printing the
   other side's extracted count next to the diff.
4. **A waiter that watched an EMPTY pid and printed DONE instantly**, then a second one that watched
   a pid that had already exited — because **`pgrep -f 'm pytest tests/'` matches the inspecting
   shell's OWN command line**, which contains that string. Already in the notes; walked into twice
   more. The counter-move that works: **filter on process AGE** (`ps -eo pid,etimes` with
   `etimes > 60`) — a process younger than the command inspecting it may BE that command.

The generalisation that keeps earning: **every extraction needs to print the size of what it
extracted, next to the result.** Three of these four were caught by that alone, and the two in the
previous handoff that were NOT caught lacked it.

## Open, in rough priority

1. **box** — unchanged, and now the only tree on the old vocabulary for a second session. Asked;
   the operator said not now, deliberately. It needs the `box` ssh ALIAS, `--force` for the clock
   skew, and verification by observation.
2. **Implement the `{...}` surface.** Engine + surface is this lane's; emission and the `#=`
   conversion are a downstream user's; the float trap binds both. **Emit the RATIO, never the
   decimal** — `{X = 155.05}` gives `2727668446186701 rdiv 17592186044416`, `{X = 15505/100}` gives
   `3101 rdiv 20`.
3. **The CLP(Q) availability gate** now has to be designed around rather than argued about.
4. `swi` dialect still UNTESTED; SICStus `r/2` still unimplemented. Both unchanged, both reasoning
   rather than measurement.
5. Adopting `decimal_repr="rational"` for the roster is still a separate decision from having the
   capability, and still needs its own export-bytes run.
6. `<downstream-domain>` migration — a downstream user's, now genuinely unblocked.

## Numbers, with their trees, because they do not transfer

    canonical c71810ec   engine suite   147 failed / 16278 passed / 50 skipped / 38 xfailed / 1 error
    clone     c71810ec   engine suite   145 failed / 16342 passed / 52 skipped / 38 xfailed / 1 error

**Same sha, different trees, and the counts differ. The failure SET diff explains all of it, and
none of it is the landing:**

    CANONICAL-only  3
      test_atoms_as_cells_flip :: the zero-field-class guard   ast.parse on a gitignored cache
      test_transitive_py_module_import :: direct + transitive  fixture writes TitleCase `Test(`
    CLONE-only      1
      audit_2026_05_25 :: F026 multi-star splits bounded       a PERF test, flaked under my own
                                                               concurrent load

The two `transitive_py_module_import` failures **SKIP on the clone** ("no project venv interpreter
with an installed clausal distribution found"), which is also the 52-vs-50 skip difference. The
zero-field-class guard `ast.parse`s `tests/**/__transformed__/*.py` — Clausal dump_source output
wearing a `.py` extension, in a directory gitignored at `.gitignore:7`. The clone has NO
`__transformed__` directories, so the guard passes there.

**Both canonical-only failures are structurally INVISIBLE to this lane's normal instrument**, which
runs in the clone. Filed as `todo/test-guard-ast-parses-gitignored-transformed-cache-2026-09-13.md`
with the fix, and deliberately NOT applied: two peers are mid-measurement against the engine suite,
and changing its failure set now is the very trap they avoided today.

**Do not compare those two counts to the 144/16343 in the previous handoff** — that was measured in
the CLONE, and a count from one tree says nothing about another. What the landing is actually
cleared by is narrower and stronger: **zero failures anywhere in the exporter / constants /
currency / prelude area**, from a name set whose extraction was positive-controlled, plus the
before/after probe, plus a downstream user's byte zero, plus a downstream checker's import-graph null.
