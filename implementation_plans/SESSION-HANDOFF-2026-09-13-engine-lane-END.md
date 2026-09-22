# Engine lane handoff — 2026-09-12/13 END

## State

    canonical main   d4f833a1    everything below; verified by OBSERVATION in that tree
    clone main       d4f833a1    identical
    box                          UNTOUCHED all session — still on the old vocabulary

## What is on canonical

| | |
| --- | --- |
| ratio units | `percent`, `basis_point` — dimensionless scaled units from a `RATIO_UNITS` authority |
| the units-import fix | the scale lint no longer drags `units` into every load |
| decimal strings | `-constant_number_units(fee, "292.00", usd)` keeps the scale a float literal loses |
| constants lexical scope | `/3` compiles to `module_constant_units(<owner>, …)`; imports and `owner.name` resolve; bound-undefined raises |
| exporter option 3 | constants CROSS, as a per-dialect capability; magnitudes converted to base |
| both preludes | Scryer and Trealla, each verified by RUNNING the exporter's own output |
| optional rational decimals | `decimal_repr="rational"` → `1_550_00/100`; default `float` keeps output byte-identical |

Axes measured on `4fc411ac` (the constants-scope tip): engine suite 144/16312/1 with failure AND
skip sets identical; export bytes 0 across 1560 files raw and normalised; domain answers 82
unchanged; **transform bytes 931 files, 919 identical, 0 different, 12 errored-under-both reported
separately**. The later commits (option 3, preludes, rational) have the engine suite only —
144/16341/1, both sets identical — because no corpus file declares a constant, so nothing reaches
the changed code.

## Open, in rough priority

1. **The later landings have no export-bytes or domain arm.** Expected vacuous (no corpus file
   declares a constant) but unmeasured. iso-export-lane and the harness lane both know the
   pattern; ask rather than assume.
2. **Adopting `decimal_repr="rational"` for the roster** is a separate decision from promoting the
   capability. It changes every constant-declaring file, so it needs its own export-bytes run.
3. **box** — still the only tree on the old vocabulary, all session.
4. **`swi` dialect UNTESTED** — it points at the Scryer-shaped prelude because SWI has
   `prolog_load_context/2`, but there is no `swipl` here. Reasoning, not measurement.
5. **SICStus `r/2`** (`155000r100`) unimplemented: no SICStus here, and `3r2` is a syntax error in
   both systems that are.
6. `<downstream-domain>` can migrate to ratio units now that the exporter carries them — corpus-lane
   owns that, 21 pairs across 9 domains.

## Things that will cost the next person time if not known

**Scryer and Trealla are LOCAL**, at `/workspace/scryer-prolog/target/release/scryer-prolog` and
`/workspace/trealla-prolog/tpl` — NOT on box, whatever older notes say. Found by reading how
`tests/iso/conftest.py` locates the oracle.

**`constant(name)`, not `++name`**, reaches a constant's value — and `constant()` errors at LOAD
for an undefined name where `++` defers to runtime. `++` remains correct for Python interop.

**`++` is SURFACE SYNTAX and the transformer is already inside it.** Never synthesise `++expr` to
be re-visited; build at the level you are at (`node_ast` for terms, `_build_py_thunk_ast` for a
late read). The escape is matched on the SOURCE shape, so a manufactured one is read as a term.

**A builtin never receives the calling module** (`_get_dispatch` is frozen, ~22 out-of-tree
implementors). The compiler does know it, and already hands `$module` to `$register_constant_units`
— so module-scoping is done by compile-time insertion, not by filtering at query time.

**Trealla's `prolog_load_context(module, M)` inside `user:term_expansion` reports the module the
HOOK is defined in**, not the file being loaded. Hence its prelude is module-LESS and loaded with
`ensure_loaded`; Scryer refuses `ensure_loaded/1` as a directive and takes `use_module`. That
divergence is why there are two preludes.

**Only the UNEVALUATED `/` term keeps a decimal's scale.** `is 155000/100` gives `1550.0`;
`155000 rdiv 100` gives `1550`. Both lose it.

## Method lessons, in order of how much they cost

**The dominant failure: an instrument whose own execution is part of what it measures.** Six
instances this session, each reporting cleanly while doing nothing:

1. a waiter counting `pytest tests/` whose own cmdline contains that string — spun for 3 HOURS
2. `-rf -rs`: pytest's `-r` is STORE, so `-rs` REPLACED `-rf` and a run reporting 145 failures
   extracted ZERO failure names. Write `-rfs`. **The `-rs` was added to fix skip-blindness found
   hours earlier — the hardening disabled the arm it was meant to sit beside.**
3. `pkill -f` with a pattern matching nothing, reporting success
4. `kill $var` on a newline list — zsh does NOT word-split an unquoted `$var`. Already in the
   notes; walked into anyway. Use `pgrep … | xargs -r kill`, then verify by re-enumerating
   **filtered on process AGE** — a process older than the command inspecting it cannot be it.
5. probes written with `++name`, which still resolves — so they passed for the wrong reason
6. a prelude test asserting `mod(` appeared rather than the module NAME: it passed under a
   hardcoded wrong module, which is the one thing it existed to catch. Strengthening it
   immediately surfaced a real Trealla defect that would have broken every exported file.

**Two peer rules better than mine:**
* the harness lane: **a control that exercises one AXIS says nothing about the other.** Their
  differ's identity run printed "919 identical, 0 different" — also what a differ stuck on
  "identical" prints.
* iso-export-lane: **a measured skip is about a CHANGE, not a claim about a TREE.** Their export
  claim went stale across 56 commits.

**Baselines are cost-bound, not absolute**: carry the COMMAND where re-measuring is cheap, the
NUMBER AND ITS TREE where it is expensive. Each of us had generalised our own end of the curve.

**A transform-time change should not be promoted until the transform-time question is asked** —
promotion destroys the cheap `dump_source` comparison. Learned by promoting without it, then
materialising the old tree in a job dir so the differ could still run.

**Seven tests pinned the old exporter refusal across FOUR files**, and the failure-set diff found
the last in a file nobody would have grepped. All CONVERTED, not deleted: each keeps its coverage
and changes its expectation, because the hazard it guarded is still the hazard.

**An assertion that fails on a correct result is the right way round for an assertion to be
wrong.** Looking for the string `"1550.00"` and getting `1550.0` is how the export scale loss was
found at all.

## Corrections made to this lane's own notes

* Scryer/Trealla are local, not on box
* `constant(name)` not `++name`
* "never trust a written-down baseline" is BOUNDED to where regenerating is cheap

---

# ADDENDUM: a defect in the promoted work, found by a peer

**Clone `b7e6feeb` carries a fix that canonical (`750e6ae1`) does not.** Narrow — only minor-unit
constants at use sites, and no corpus file declares one yet — but it IS on canonical.

`155000 aud_cent` is `Decimal('1550.00')`, which equals 1550 EXACTLY, and the emitter wrote
`1550.00` — a Prolog FLOAT. The unscaled path stayed integer, so only SCALING lost exactness:
the fold converted exact cents into binary floating point, which is the hazard the operator ruled
against when rejecting dimensionless constants, reached by another route. Reported by
iso-export-lane; fixed at the use-site substitution.

**Two things about it worth more than the fix.**

**The test I wrote for that path asserted `pay(1550.00)` — it encoded the defect as the
expectation**, and three others did the same. So no amount of running my own suite would have
found it. A test written alongside the code it tests inherits the code's assumptions; only
someone reading the OUTPUT found this.

**The first fix was wrong in an instructive way.** Integralising inside the shared scaler broke
the DECLARATION, because a declaration wants the SCALE (`1_550_00/100`) and a use site wants the
exact INTEGER. They want opposite things and the shared helper had folded them together.

## Residual, and it may bear on the `#=` ruling

A genuinely fractional fold (`15505 aud_cent` -> `155.05`) is still a float. There is no exact
form to convert to at a use site — and **CLP(Z) is integer-only**, so under the operator's `#=`
ruling `V #= 155.05` is not a clpz goal at all. **Fractional money cannot be expressed as the
constraint the ruling calls for.** iso-export-lane's design question, flagged before their `#=`
conversion meets a fractional amount.

## Also open from iso-export-lane's report (theirs, not this lane's)

* `==` / `=:=` should be `#=`, with `clpz` not `clpfd` — operator's ruling, and their measurement
  shows **Clausal's `==` IS a CLP(Z) constraint** (`10 == X + 4` binds X to 6, backward)
* the fold does not reach through a divisor: `constant(cap) / aud_cent` leaves `aud_cent`, which
  is not an evaluable functor in either engine. 65 single-goal corpus clauses are this shape.
  Pre-existing, not from these landings.
* `_CLPFD_CANONICAL` at `clausal_to_prolog.py:2123` is the policy the ruling overturns — update
  the comment rather than delete it, so a later reader sees it was chosen, not forgotten.
