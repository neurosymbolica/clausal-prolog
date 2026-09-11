# Engine lane handoff — 2026-09-11 END

**You are the engine lane AND the coordinator.** Read this file first. The 2026-09-10 END
handoff is now history except for its §5a/§5c/§5e lessons, which still hold.

## 1. State of the world

    clone / canonical / box main   946d7296   (rev-parse x2 + ls-remote, verified after each landing)

Engine suite in the clone at that tip: **144 failed / 15862 passed / 1 error**, all
environmental. That failure NAME SET is identical to the one measured at `9a719536` at the
START of the day — every landing below moved it by zero. The extraction is at
`/home/node/.claude/jobs/af5b4bbe/tmp/tip.fail` (144 names); regenerate rather than trust it.

**Three claims, separately, none implying another** (the standing rule):

| axis | who | measured on | result |
| --- | --- | --- | --- |
| engine suite | me | 946d7296 | 0 new failures vs the 9a719536 baseline |
| corpus loads | corpus-lane | 946d7296 predecessors | 71 asserted clean / 0 defects / 7 not checked, cold AND warm |
| batch bodies | harness-batch-lane | not re-run today | — ask before relying on it |

## 2. What landed today, in order

    375acf8f..e030988b   constants respelled: lowercase names, `_CONSTANT_` retired,
                         the classifier carve-out gone from all five copies
    7e825cdf             Trail_dealloc untracks before clearing weakrefs (SEGFAULT fix)
    25fe9dce             c_make_node owns its borrowed references
    671a697e             exporter folds a declared constant to its literal
    c4c7d6c9             constant_number_units/3 + the directive renamed to match
    6e00bc75             that predicate reports the DECLARED pair
    8b23615f             CLAUSAL_BYTECODE_TAG 12 -> 13
    a9989b7a             the tag is derived from an engine fingerprint (automatic now)
    960edd94             no minor-unit currency, no ratio units — ruled and documented
    946d7296             constant(name) is the retrieval form, replacing ++name

## 3. The surface as it now stands

    -constant_value(name, value)                  declare
    -constant_number_units(name, number, units)   declare, unit kept out of the value
    constant(name)                                RETRIEVE — not ++name
    constant_value(Name, Value)                   query; Name is an ATOM
    constant_number_units(Name, Number, Units)    query; reports what was DECLARED

Rulings behind it, all the operator's, all 2026-09-11:

- **A bare name is the ATOM**, never the value. One name carries both readings.
- **Declaring a constant does NOT declare the atom** — my conservative call, not his. A bare
  `pi` still needs its `-module` listing. Available to relax; not available to tighten later.
- **`constant_number_units/3` reports the DECLARED pair.** `30 day` answers `30, day` while
  `constant_value/2` answers `2592000 second`. They disagree on purpose, because only the
  declared unit lets a gate check that a parameter's unit matches what its NAME claims.
- **No minor-unit currency, ever.** `cent` is ambiguous — euros have cents, dollars have
  cents. Base currency with decimals. Extended to ratios: no `percent`, no `basis_point`.
- **Durations are date arithmetic, not units.** Months vary; business days need holidays.

## 4. The corpus migration — APPROVED and dispatched to corpus-lane

88 parameters / 28 domains / 337 call sites + 5 in eval bodies. 24 keyed parameters stay facts.
Three edits per parameter (atom listing, declaration, each call site). First domain
`eu/banking/crr_leverage_ratio`. Full spec sent to corpus-lane; they own it.

**Do not start corpus work here.** It is theirs, they hold the census and the gates.

## 5. Open, and what they need

- **The `-module` listing relaxation** (§3). If corpus-lane reports it as pure friction across
  88 parameters, put it to the operator. Cheap either way at this point.
- **`_add_lossy` is a write-only channel** — nothing reads `_all_lossy`, so every unit
  discarded on export is silent. `todo/exporter-lossy-channel-is-write-only-2026-09-11.md`
  has three options and the golden-output churn each costs.
- **The `++` operator export** — a non-constant `++` still emits `???`. The prelude packaging
  is unsolved in both Scryer and Trealla (self-applying `term_expansion/2` hangs Trealla; an
  included prelude hangs Trealla and Scryer rejects it positionally).
- **CLP(B) registry keyed on `id(Var)`** — a real design hazard with NO known reproduction.
  `todo/clpb-registry-keyed-on-object-addresses-2026-09-11.md`. Do not treat it as live.

## 6. Three lessons that cost real time today

**"Disabling X makes the crash go away" identifies a TRIGGER, not a cause.** The segfault
looked like CLP(B) for most of a day because CLP(B) is the only code that puts a
`weakref.finalize` on a Trail. `gc.disable()`, neutering the finalizer, skipping any one of
three dict pops, even reverting an unrelated transformer file — all "fixed" it, all real
measurements, all pointing at the wrong thing. The real bug was `Trail_dealloc` clearing
weakrefs while still GC-tracked. For a memory fault, anything that moves allocation or GC
phase masks or unmasks it.

**A load census cannot detect a compiler change.** Stale bytecode loads perfectly. Asking a
lane to "re-measure on the new sha" tests the new engine only if their caches were cold — and
even cold, "does it load" is the wrong instrument for a transformer change. **Name the
instrument you need** (behavioural probe, oracle, answer diff), not just the sha. I asked for
re-measurements the wrong way repeatedly today.

**An instrument that can only report success reports nothing.** Today's crop: a bisect that
used `str.replace` with no assertion and "proved" a change innocent; an awk detector that
matched its own comment; a `git grep` that said 0 downstream where a filesystem walk said 322;
an extraction that silently produced empty output and read as a clean sweep. Every instrument
needs a positive control, and you read the evidence line, not the verdict.

## 7. Lanes

corpus-lane [0dfae0] holds the migration and is the most active. iso-export-lane [e8cdc5],
harness-batch-lane [803e60], law-portal-1a [718243] have not been engaged today — none of
today's landings was flagged to them, which is worth doing if anything here reaches their
trees. The `.so` changed today (`7e825cdf`, `25fe9dce`), so **any lane with a long-lived
process that imported the engine before ~09:00 is running the old extension.**
