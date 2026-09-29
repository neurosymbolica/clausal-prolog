# Engine lane handoff — 2026-09-12/13: ratio units, constants scope, exporter dialect

## State

    canonical main   4fc411ac    ratio units, the units-import fix, decimal strings,
                                 constants lexical scope -- all four axes clean
    clone main       f396838d    + exporter option 3 (per-dialect constants), NOT promoted
    box                          still on the old vocabulary

## What landed on canonical

| | |
| --- | --- |
| ratio units (`percent`, `basis_point`) | dimensionless scaled units, from a `RATIO_UNITS` authority |
| the units-import defect fix | the lint no longer drags `units` into every load |
| decimal strings | `-constant_number_units(fee, "292.00", usd)` keeps the scale a float literal loses |
| constants lexical scope | `/3` compiles to `module_constant_units(<owner>, …)`; imports and `owner.name` work; bound-undefined raises |

Four axes on `4fc411ac`: engine suite 144/16312/1 with failure AND skip sets identical; export
bytes 0 across every exported file raw and normalised; domain answers all unchanged; **transform bytes 931
files, 919 identical, 0 different, 12 errored-under-both reported separately.**

## Built but NOT promoted: exporter option 3 (`f396838d`)

Constants cross as a **per-dialect capability** — the operator's framing: two sides, so add a
switch rather than pick one side of a trade-off.

    iso              facts      constant_number_units(mod, fee, 5000, euro).
    scryer, trealla  expansion  :- constant_number_units(fee, 5000, euro).
    gprolog          none       refuse

Magnitudes fixed in every dialect: `pay(1550.00)` not `pay(155000)`; `lim(0.0300)` not `lim(300)`.

**Next piece: the `expansion` prelude is unbuilt.** Those dialects emit a directive needing a
`term_expansion/2` prelude, whose packaging `clausal_to_prolog.py` already calls unsolved. The
switch CONFINED that rather than solving it — `iso` needs no prelude, so the roster is unblocked.

## Open for whoever picks this up

* **the expansion prelude** (above) — inline per file, or one library file
* **box** — still the only tree on the old vocabulary
* ratio units do not unblock `<downstream-domain>` by themselves; option 3 is the piece that does,
  once promoted
* the scale lint's three known distortions are unchanged (`docs/currency.md`)
* `todo/constant-number-units-3-answers-across-modules-2026-09-12.md` is CLOSED by `a92a3e74`

## Method notes that earned their place

**The day's dominant failure: an instrument whose own execution is part of what it measures.**
Five instances, each reporting cleanly while doing nothing —

1. a waiter counting `pytest tests/` whose own cmdline contains that string: **spun for 3 hours**
2. `-rf -rs`: pytest's `-r` is STORE, so `-rs` replaced `-rf` and a run reporting 145 failures
   extracted ZERO failure names. Write `-rfs`. **The `-rs` was added to fix skip-blindness found
   hours earlier — the hardening disabled the arm it was meant to sit beside.**
3. `pkill -f` with a pattern that matched nothing, reporting success
4. `kill $var` on a newline-separated list — **zsh does not word-split an unquoted `$var`**, so it
   killed one. Already in this lane's notes; walked into anyway.
5. probes written with `++name` for constants, which still resolves — so they passed for the
   wrong reason and hid the difference. `constant(name)` is the spelling AND it errors at LOAD.

The form that works: `pgrep … | xargs -r kill`, then verify by **re-enumerating filtered on
process AGE** — a process older than the command inspecting it cannot be that command.

**Two rules from peers, both better than what I had:**

* A downstream checker: **a control that exercises one AXIS of an instrument says nothing about the
  other.** Their differ's identity run printed "919 identical, 0 different" — which is also what a
  differ stuck on "identical" prints. They proved the diff axis separately.
* A downstream user: **a measured skip is about a CHANGE; it is not a claim about a TREE.** Their
  export claim went stale across 56 commits. Generalised with them: carry the COMMAND where
  re-measuring is cheap, carry the NUMBER AND ITS TREE where it is expensive. **The choice is set
  by re-measurement cost, not taste** — and each of us had generalised our own end of the curve.

**A transform-time change should not be promoted until the transform-time question is asked**,
because promotion destroys the cheap comparison (`dump_source` over both trees). Learned by
promoting without it and then materialising the old tree in a job dir so the differ could run.

**Seven tests pinned the old exporter refusal, across FOUR files**, and the failure-set diff found
the last in a file nobody would have grepped. All CONVERTED, not deleted: each keeps its coverage
and changes its expectation, because the hazard it guarded is still the hazard.

## Corrections to this lane's own notes, made in-session

* **Scryer and Trealla are LOCAL**, not on box — found by reading how `tests/iso/conftest.py`
  locates the oracle rather than guessing at paths
* **`constant(name)`, not `++name`**, is how a constant's value is reached — and it errors at LOAD
* **"never trust a written-down baseline" is BOUNDED** — right only where regenerating is cheap
