# The exporter's LOSSY channel is write-only — every discarded unit is silent

**Found 2026-09-11** while adding the constant literal-fold.

`clausal_to_prolog` has two channels for information about a translation:

    _add_warning(...)  -> emitted into the .pl as a WARNING comment, and makes
                          strict mode raise
    _add_lossy(...)    -> appended to self._lossy / self._all_lossy ... and read
                          by NOBODY

`git grep all_lossy` outside `clausal_to_prolog.py` returns nothing. `self._lossy`
is cleared per statement in `convert_module` and never rendered. So a lowering that
SUCCEEDED but dropped information reports that fact to no one.

## What is currently silent

The documented case is units. `_convert_call` discards the unit from an inline
quantity literal and records it:

    self._add_lossy(f"unit discarded: {func.value}({unit.id}) -> {func.value}")

So `cost(days(90), 0(euro), hassle(high))` exports with the currency gone and nothing
says so. In a corpus of legal and financial domains that is the wrong default: the
number survives, its dimension does not, and the resulting `.pl` looks clean.

## What was done about it, and what was not

The constant literal-fold (`671a697e`) emits its own `LOSSY:` comment for
`-constant_value_units`, because a constant's unit is declared far from its use and
would otherwise vanish without trace. **That is a local fix, not the general one.**
The inline-literal case still goes only to `_add_lossy`.

## The decision to make

Rendering every `_add_lossy` as a comment in `convert_module` is a three-line change
and would make the whole channel visible at once. It is not done here because it
changes the emitted text of every file that discards a unit, which will move golden
outputs (`tests/test_prolog_golden.py`) and wants its own diff to review. Options:

1. **Render them as comments**, like warnings but non-fatal. Most useful, moves goldens.
2. **Expose them on the API** (a `lossy` field on the translation result) so callers
   and the CLI can report them without changing the file. No golden churn.
3. **Both** — comment in the file, field on the result.

Prefer 3 if the golden churn is acceptable; 2 is the no-risk half and could land first.

## Check before doing it

Confirm the channel is still write-only — this is a fact with a shelf life, and the
whole point is that nothing today would notice if it changed. `git grep all_lossy`
plus a check that `convert_module` still clears `_lossy` without rendering it.
