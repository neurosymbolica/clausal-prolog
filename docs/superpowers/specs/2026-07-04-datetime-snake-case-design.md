# `py.datetime` predicates → snake_case, Python-faithful names

**Date:** 2026-07-04
**Status:** Design approved, pre-implementation
**Module:** `clausal/modules/py/datetime.py` (module name `datetime`, imported as `py.datetime`)

## Motivation

The `py.datetime` predicates are currently minted in TitleCase (`Date`, `DaysBetween`,
`ParseDate`, …). The local student models that generate Clausal (Qwen3.6-27B dense and its
7B predecessor) produce snake_case far more reliably than TitleCase: snake_case is what
Python's `datetime` module and SWI-Prolog's date library use, and it is what the models were
pre-trained on. Every TitleCase date predicate is extra surface the model must learn. This is
the single most-generated API family in the temporal domains, so the payoff is high.

This design renames the whole surface to snake_case, following **Python `datetime`
conventions** as the primary guide (SWI naming was considered only insofar as it helps
SWI-Prolog-trained models, but Python wins where they disagree). It also folds format/parse
into one bidirectional relation and adds timestamp + ISO-8601 conveniences.

## Scope

**In scope:**
- Rename every exported predicate in `clausal/modules/py/datetime.py` (both the module
  attribute and the `ModulePredicate(...)` `_name` string) to snake_case.
- Two new predicates: `datetime_string/3` (replaces `FormatDate` + `ParseDate`) and
  `timestamp/2`.
- Two ISO-8601 helper predicates: `datetime_string_iso/2`, `date_string_iso/2`.
- Update the module docstring.
- Sweep the in-repo consumers so nothing breaks: `tests/test_date_time.py`,
  `tests/test_transitive_py_module_import.py`, the doc-signature fixtures under
  `tests/fixtures/docs/` (`date_time_sigs.txt`, `date_time_sig_tests.seam`), and
  `docs/date_time.md` (plus incidental mentions in other docs).

**Out of scope (separate TODOs / repos):**
- A downstream helper-library rename (a helper predicate → `profile_get`, …) — sibling request, its own TODO.
- `date-max-min-ordinal-apis.md` — new ordinal/max/min date APIs.
- A downstream rulebase corpus sweep and its scaffolding templates — those live in **separate
  repos** not present here, so they are not swept by this change.

## Key decisions

1. **Flag-day rename, no aliases.** Only snake_case names exist; TitleCase names are removed
   outright. The name a rulebase imports binds to the Python module *attribute*
   (`-import_from(py.datetime, [date])` compiles to `from py.datetime import date`), so a
   removed TitleCase name yields an `ImportError`. Acceptable because this repo's only
   consumers are tests and docs, which we update in the same change; external rulebases are
   swept in their own repo separately.

2. **Python-faithful spelling wins over mechanical snake_case.** Python spells two of these as
   single words, so they are *not* underscored:
   - `DateTime` → **`datetime`** (class `datetime.datetime`), not `date_time`.
   - `TimeDelta` → **`timedelta`** (class `datetime.timedelta`), not `time_delta`.

3. **`weekday/2`, 0=Mon..6=Sun.** Matches Python's `datetime.weekday()`. (SWI's
   `day_of_the_week/2` is 1=Mon..7=Sun; we do not adopt it — same name + different numbers
   would be a trap, and Python is the priority.)

4. **`datetime_string/3` — one bidirectional relation replaces format + parse.** Fits the
   module's established bidirectional pattern (`date/4`, `time/4`, `datetime/7`, `timedelta/3`,
   `date_of/2`). FORMAT is the trailing argument so the two principal terms `(DATETIME, STRING)`
   mirror the predicate name and are shared as a prefix with the ISO helpers.

5. **ISO helpers use `.isoformat()` / `.fromisoformat()`**, not a fixed strftime pattern —
   `fromisoformat` (Python 3.11+, we run 3.13) is the complete ISO parser (fractional seconds,
   offsets, `Z`, space separator).

## Rename mapping (old → new)

| current | new | note |
|---|---|---|
| `Now` | `now` | `datetime.now()` |
| `NowUTC` | `now_utc` | no Python snake-name; kept descriptive |
| `Today` | `today` | `date.today()` |
| `Date` | `date` | class `datetime.date` |
| `Time` | `time` | class `datetime.time` |
| `DateTime` | `datetime` | class `datetime.datetime` (one word) |
| `TimeDelta` | `timedelta` | class `datetime.timedelta` (one word) |
| `DateAdd` | `date_add` | Clausal relational helper |
| `DateSub` | `date_sub` | |
| `DateDiff` | `date_diff` | |
| `DateBetween` | `date_between` | nondeterministic date range |
| `DaysBetween` | `days_between` | integer day count |
| `DateOf` | `date_of` | `datetime.date()`; `date` taken by the constructor |
| `FormatDate` | *removed* | folded into `datetime_string/3` |
| `ParseDate` | *removed* | folded into `datetime_string/3` |
| `DayOfWeek` | `weekday` | Python `datetime.weekday()`, 0=Mon..6=Sun |

## New predicates

### `datetime_string(DATETIME, STRING, FORMAT)` — bidirectional format/parse

Replaces `FormatDate/3` and `ParseDate/3`. Reads declaratively: "DATETIME rendered under the
strftime FORMAT is STRING."

Mode logic (deref all three first):
- FORMAT must be a ground string in every mode → fail otherwise.
- **Format** (DATETIME is a `date`/`time`/`datetime`, i.e. has `.strftime`):
  `S = DATETIME.strftime(FORMAT)`, unify with STRING. If STRING already bound, this is a
  **check**. (Matches current `_format_date_3`, which accepts anything with `strftime`.)
- **Parse** (DATETIME unbound, STRING a ground string):
  `DATETIME = datetime.strptime(STRING, FORMAT)`.
- Both DATETIME and STRING unbound → fail.

Inherent asymmetry to document: `strftime` works on `date`/`time`/`datetime`, but `strptime`
always yields a `datetime`. So round-tripping a `date` → string → back gives a **midnight
`datetime`**, not a `date`; likewise a FORMAT that omits fields parses to defaults (midnight).
Standard Python behavior.

Arity 3, `simple_to_trampoline` wrapper, same shape as the other simple predicates.

### `timestamp(DATETIME, STAMP)` — bidirectional datetime ↔ POSIX epoch

- **Forward** (DATETIME is a `datetime`): `STAMP = DATETIME.timestamp()` (float epoch seconds).
  If STAMP bound → check. (`date` has no `.timestamp()`, so forward requires a `datetime`.)
- **Inverse** (DATETIME unbound, STAMP a real number): `DATETIME = datetime.fromtimestamp(STAMP)`.
- Otherwise fail.

Mirrors Python `datetime.timestamp()` / `datetime.fromtimestamp()`; same bidirectional shape as
`date_of/2`.

### `datetime_string_iso(DATETIME, STRING)` — bidirectional ISO-8601 datetime

- **Forward** (DATETIME is a `datetime`): `STRING = DATETIME.isoformat()`.
- **Inverse** (DATETIME unbound, STRING a ground string): `DATETIME = datetime.fromisoformat(STRING)`.
- Otherwise fail.

### `date_string_iso(DATE, STRING)` — bidirectional ISO-8601 date

- **Forward** (DATE is a `date` and *not* a `datetime`, guarded like `_date_4`):
  `STRING = DATE.isoformat()` → `"YYYY-MM-DD"`.
- **Inverse** (DATE unbound, STRING a ground string): `DATE = date.fromisoformat(STRING)`.
- Otherwise fail.

## Final API surface

| predicate | arity | notes |
|---|---|---|
| `now`, `now_utc`, `today` | 1 | current date/time |
| `date`, `time` | 4 | bidirectional construct/decompose |
| `datetime` | 7 | bidirectional (Y,Mo,D,H,Mi,S,Obj) |
| `timedelta` | 3 | bidirectional (Days,Seconds,Obj) |
| `date_add`, `date_sub`, `date_diff` | 3 | date/timedelta arithmetic |
| `date_between` | 3 | nondeterministic date range |
| `days_between` | 3 | integer day count |
| `date_of` | 2 | bidirectional datetime ↔ date |
| `weekday` | 2 | 0=Mon..6=Sun |
| `datetime_string` | 3 | **new** — bidirectional format/parse |
| `timestamp` | 2 | **new** — bidirectional datetime ↔ epoch |
| `datetime_string_iso` | 2 | **new** — bidirectional ISO datetime |
| `date_string_iso` | 2 | **new** — bidirectional ISO date |

## Consumer sweep

- `tests/test_date_time.py` — rename all predicate references; add tests for the four new
  predicates (both directions, check mode, and the date→midnight-datetime round-trip caveat).
- `tests/test_transitive_py_module_import.py` — update any TitleCase datetime references.
- `tests/fixtures/docs/date_time_sigs.txt`, `tests/fixtures/docs/date_time_sig_tests.seam` —
  regenerate/rewrite to the new signatures (these back the doc-signature tests).
- `docs/date_time.md` — rewrite examples and the predicate reference to the new names; document
  `datetime_string`, `timestamp`, and the ISO helpers, including the round-trip asymmetry.
- Incidental mentions in `docs/regex.md`, `docs/compiler.md`, `docs/builtins.md`,
  `docs/python_integration.md`, `docs/architecture.md`, `docs/index.md`, `docs/packages.md` —
  update any TitleCase datetime names encountered.

## Testing

- Every renamed predicate keeps its existing behavior; existing tests port over by name change.
- New predicates get direct tests: forward, inverse, check mode, and failure modes (unbound
  FORMAT, both-unbound, wrong types).
- Run the full `tests/test_date_time.py` and the doc-signature tests to confirm the sweep is
  complete (per the memory note: pyenv 3.13.3 + `PYTHONPATH` to this clone, venv lacks pytest).

## Non-goals

- No deprecation-alias mechanism (flag-day per decision 1).
- No microsecond component added to `datetime/7` (kept arity 7; separate consideration).
- No timezone-aware constructors beyond the existing `now_utc`.
