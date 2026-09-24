# Engine-lane handoff, 2026-09-24 — P4 / PredicateMeta retirement

Canonical main: **`d8543fbf`**. Box/GitLab NOT pushed. Gate throughout:
146 failed / ~16892 passed, NEW 0 / GONE 0. Package gate 105 = 105 (in-room)
/ 110 (canonical — a different package environment; re-baseline per tree).

## Landed this session

W4b-0 (the W4a inbox, incl. a C rebuild + rename-swap), the `-dynamic`
arm-3 gap, W4b-1 (term shape), W4b-2a (`qualify_mangled_goal` + the ruled
error shape), W4b-2b (the era-agnostic resolver + 7 sites), F2b (12 sites),
`through=`, the F1 re-audit (+2 sites), F7.

## OPERATOR RULINGS MADE 2026-09-24 — implement these, do not re-ask

1. **Error shape (DONE, landed).** Both unresolvable-mangled-goal cases raise
   `existence_error(procedure, Name/Arity)` as a `LogicException`, culprit
   DEMANGLED, module/not-loaded distinction in the message only.

2. **`call/N` must RAISE, not fail silently.** Today `call(H)` on an
   unresolvable handle returns no answers where `solve(H)` raises:

       solve(handle) -> LogicException existence_error(procedure, ...)
       call(handle)  -> []            # higher_order.py returns None -> failure

   Ruled: raise. The operator noted this project avoids committed choice and
   would use `if_/3`; a `call_t/N` wrapper is OUT OF SCOPE and does not change
   the ruling. NOT YET IMPLEMENTED — `clausal/logic/builtins/higher_order.py`,
   around the `qualify_mangled_goal` re-entry (~line 156): when the goal does
   not qualify and names nothing callable, raise rather than return `None`.

3. **F4 — the diagnostic arity reader returns a SET.** `_arity_of`
   (`predicate_diagnostics.py:190`) feeds the "did you mean:" near-miss pool
   in the predicate-not-found message. It should answer the SET of arities
   (`arities_for`-shaped), empty meaning "not a predicate here" — the role
   `None` plays now. Several arities are several suggestions, not ambiguity.
   **Fixes a live bug for free:** both call sites (lines ~252, ~280) guard
   with `if arity:`, so a `p/0` is falsy and NEVER reaches the pool.
   CAUTION: `arities_for` is lossy — it misses `mark_predicate_export`
   entries and `-import_from` adopted rows. Use it knowing that, or use
   `Database.is_predicate_name` / `declared_kind`.

4. **F8 — KEEP the cross-copy diagnostic; do not migrate or delete it.**
   `describe_term_identity_mismatch` only appends explanatory text to an error
   already being raised (one caller, `database.py:1635`), for the case where
   two copies of the package are live and a foreign instance arrives. It is
   tested (`tests/test_second_package_copy_term_identity.py`). At W4b-3 its
   first line (`isinstance(cls, PredicateMeta)`) has nothing to test and its
   second is already a NAME comparison against `"PredicateMeta"` — so it
   survives as a pure name-based check. A two-line rewrite, not a migration.

5. **two-out-paths — the boundary is WHEREVER A VALUE REACHES PYTHON.**
   Measured, and the todo's claim is correct: no single test works on both
   paths.

       term space (solve+deref): atom = plain str, string = ('$chars', ..)
       export space (--)       : atom = atoms.atom, string = plain str
       isinstance(v, str)  separates atom/string in TERM space only
       isinstance(v, atom) separates atom/string in EXPORT space only

   Ruled: tag at every Python boundary, so `isinstance(v, atom)` is the one
   rule. **IMPLEMENTATION CAVEAT FROM THE CONTROLLER: it must be a NEW
   exporting reader, NOT a change to `deref`.** `deref` is engine-internal and
   on hot paths; tagging there pushes export types back into the engine.
   Bonus argument for doing it: term space currently hands Python the raw
   mangled spelling (`'hide_owner\x1fhide_secret'`, control character and
   all). An export boundary is the place to normalise that; today there is
   none. Closes
   `todo/two-out-paths-disagree-about-atom-tagging-2026-09-22.md` and
   unparks `todo/seam-handle-form-for-hold-and-call-sites-parked-2026-09-22.md`.

## BLOCKS THE FLIP — fix before W4b-2d lands

`todo/the-lock-loop-stops-selecting-after-the-flip-2026-09-24.md`.
`compiler_v2.py:488` finds static predicates by filtering `module_dict` on
`isinstance(obj, PredicateMeta)`. Measured: 3 selected today, **0 after the
flip**. Nothing gets locked, so every static predicate silently becomes
mutable at runtime. `_lock()` has an exact row equivalent, so migrating the
ACTION looks clean while the SELECTOR stops selecting — the fix must change
what the loop ITERATES, with a positive control that the population is
non-empty.

## Carried forward from F7

**`_dispatch_at` is NOT yet safe for `PredicateMeta`'s deletion.** It still
names the class because raw classes still reach it directly (`solve.py`'s
`call()` Phase 5 and ~7 other sites, unaudited). W4b-3 must convert those
first. This invalidates the earlier assumption that a native predicate always
arrives as a handle.

## F5, F9, F3 — ALL DONE (2026-09-24, after the first version of this handoff)

* **F5** (rows 18, 39) — the coupled pair swapped in ONE commit, with the
  mirroring proved two ways: a code trace, and a test calling both functions
  on the same inputs asserting they agree.
* **F3** (row 9) — **NO CODE CHANGE NEEDED at any of the four callers.** All
  three INFERENCE verdicts in the design doc were turned into verified ones.
  It did surface an undocumented divergence the brief never flagged: in
  `term_to_ast_expr` the baked literal's SPELLING differs across eras (a
  plain name today, a raw mangled string post-flip). That needs a ruling, so
  it was PARKED, not guessed —
  `todo/self-denoting-predicate-atom-spelling-post-flip-mangled-or-plain-2026-09-24.md`.
* **F9** (row 1) — **the design brief was WRONG and would have shipped a
  silent bug.** It said filter on `is_mangled(value)` *instead*; today every
  binding is a class, so that selects NOTHING until the flip and the
  diagnostic quietly goes blank. Filter is `is_declared_predicate_name`
  (era-agnostic), and the task's real deliverable is a POSITIVE CONTROL: two
  tests assert the population is non-empty and check exact pairs, failing
  TODAY if the filter empties. Also measured: `field_names_for` returns
  `None` for ordinary clause-defined predicates in the mangled era, so an
  `arities_for` fallback keeps the `/N` suffix — and `arities_for` is itself
  lossy for bare `name/arity` exports and adopted rows. Fine for a
  diagnostic; NOT fine for a gate.

**The recurring lesson, now three times in one day:** a filter keyed on the
old shape does not fail loudly when the shape changes — it silently selects
nothing. The lock loop, the F9 brief, and the `through=` bug are the same
mistake wearing different clothes. Any migration of a SELECTOR needs a
non-empty positive control; migrating the ACTION is the easy half.

## What is left, in order

1. **The 11 still-blocked sites** — worklist with per-row evidence in
   `.superpowers/sdd/f1-reaudit-report.md`. Not migrations: they need the
   flip to supply a replacement for the class object. `analyze_mi` (32/33)
   has no era-agnostic arm at all; `_find_pred_cls` (58/59) is documented as
   returning a class; row 4 has no arity.
3. **The flip** (W4b-2d) — lane handoff at
   `implementation_plans/W4B2D-LANE-HANDOFF-2026-09-23.md`, already updated
   for `through=` landing.
4. **W4b-3** — the deletion. Needs the `.so` rebuild + rename-swap; procedure
   and traps in memory.

## Working rules this session paid for

* **Gates are the scarce resource, not agents.** Two concurrent full suites
  took one run from 166s to 949s and killed another at 89%. Parallelise
  agents and read-only analysis; SERIALISE suite runs.
* **Strip ANSI before extracting failures.** `grep -E "^(FAILED|ERROR) "`
  matched NOTHING on a run where 146 failed, because pytest coloured the
  lines. An empty extraction means colour OR truncation, never "nothing
  failed". Always assert non-empty.
* **Worktrees live at `/workspace/_<name>`** — the session scratchpad was
  withdrawn mid-session and git then refused those rooms ("dubious
  ownership"); `safe.directory` entries added.
* Implementers keep backgrounding test runs and parking for 20+ minutes.
  Tell them FOREGROUND explicitly, every time.
