# `terms_to_goalop` crashes on an attributed variable in goal position

**Error:** `terms_to_goalop: goal shape not yet supported (AttVar): AttVar(_0)`

A CLP(ℤ)-constrained variable (produced by `==`) used **as a goal** (bare, in goal position) makes the
clause compiler raise an internal `terms_to_goalop` error at load time instead of either evaluating it
or giving a clean "not a callable goal" diagnostic.

## Minimal repro (4 lines — fails at `<load>`)
```clausal
go(R) <- (
    X == 5,
    R == X - 2,
    R                 % <- R is a CLP attributed var, used here as a bare goal
)
Test("attvar in goal position") <- (go(R), R == 3)
```
```
$ python -m clausal.testing attvar_min.clausal
  ...::<load> — terms_to_goalop: goal shape not yet supported (AttVar): AttVar(_0)
```

## Where it came from (real case)
A generated schengen rulebase ended a clause with a bare bound variable as its final goal:
```clausal
decide_schengen(REF_DATE, STAYS) <- (
    ..., REM == LIMIT - USED,
    If(REM >= 0, RESULT is "allowed", RESULT is "not_allowed"),
    RESULT                      % <- bare var in goal position -> AttVar crash at load
)
```
The rest of the rulebase is correct (its `days_used`/`days_remaining` logic scores 26/26 against the
oracle); this one construct blocks the whole public-interface test file from loading.

## Why fix it
- It surfaces from machine-generated rulebases, where "a variable accidentally in goal position" is a
  common mistake. The current message is an internal-shape crash, not a user-actionable error.
- **Minimum fix:** turn it into a clear, located error — e.g. *"`R` is not a callable goal (got an
  attributed/bound non-callable in goal position) in clause `go/1`"* — so the author can find it.
- **Consider:** whether an attributed var in goal position should be supported at all, or always rejected
  cleanly at compile time.

## Repro artifacts (on the box)
`/root/clausal-train/data/attvar_repro/`: `attvar_min.clausal` (the 4-line repro) and
`attvar_artifact.tgz` (the full generated schengen rulebase + tests that triggered it).

Found via the 30B schengen formalization baseline (see clausify `formalization-program-state` /
`.superpowers/sdd/progress.md`).
