# date_time API → snake_case (Python-/Prolog-like) names

**Requested:** 2026-07-02. **Why:** the local student models (Qwen3.6-27B dense, and the 7B
before it) generate snake_case far more reliably than TitleCase/CamelCase — snake_case is what
Python's `datetime` and SWI-Prolog's date library use, and what the models were pre-trained on.
Every TitleCase date predicate is extra surface the local LLM has to learn. Making the date API
snake_case means *less to learn* and *closer to Prolog*. This is the single most-generated API
family in the temporal domains, so the payoff is high.

## What to rename (module `date_time`, `clausal/modules/py/datetime.py`)
Current names are minted through `_DateTimePredicate("<Name>")`. Add snake_case names for the whole
surface. Proposed mapping (snake_case of the current name; adjust if a more Python/SWI-idiomatic
spelling is better — noted in the third column):

| current | snake_case | note |
|---|---|---|
| `Date` | `date` | matches Python `datetime.date(y,m,d)` |
| `DateTime` | `date_time` | |
| `Time` | `time` | |
| `Today` | `today` | |
| `Now` | `now` | |
| `NowUTC` | `now_utc` | |
| `DateAdd` | `date_add` | |
| `DateSub` | `date_sub` | |
| `DateDiff` | `date_diff` | |
| `DateBetween` | `date_between` | enumerates the dates in a range |
| `DaysBetween` | `days_between` | integer day delta (routes via the `_DateTimePredicate` trampoline) |
| `DateOf` | `date_of` | |
| `TimeDelta` | `time_delta` | cf. Python `timedelta` |
| `ParseDate` | `parse_date` | |
| `FormatDate` | `format_date` | |
| `DayOfWeek` | `day_of_week` | |

## Rollout (avoid a flag-day break)
1. **Add the snake_case names as the canonical spelling**; keep the TitleCase names as
   **deprecated aliases** for one release so existing rulebases keep loading.
2. Update the downstream corpus's authoring-conventions doc §3 (Dates) + a downstream library's
   scaffolding docs to show snake_case (`date(YEAR,MONTH,DAY,OBJ)`, `days_between(A,B,N)`, …).
3. Then sweep the downstream rulebase corpus from the TitleCase names to snake_case (mechanical
   `-import_from(date_time, [...])` + call-site rename; the corpus temporal domains include
   several date-window and data-handling rules).
4. Finally drop the TitleCase aliases.

## Related
- `todo/date-max-min-ordinal-apis.md` (clean ordinal/max/min date APIs — do together, all snake_case).
- Sibling request: spell out + snake_case a downstream helper library's helpers (a helper predicate
  → `profile_get`, another helper predicate → `profile_has`, `attr`→`attribute`) — see that lib's
  todo. Same rationale (less for the local models to learn; closer to Prolog).

---

## Closed 2026-07-04 — implemented

Implemented in commits on branch `fix/qualified-atoms-term-position`. Deltas from the original proposal above:

- **Flag-day rename, no deprecated aliases** — only snake_case names exist (the downstream rulebase corpus/library swept separately in its own repo).
- **`datetime` and `timedelta` spelled as single words** (matching Python's class names), not `date_time`/`time_delta`.
- **`DayOfWeek` → `weekday`** (Python `datetime.weekday()`, 0=Mon..6=Sun), not `day_of_week`.
- **`FormatDate` + `ParseDate` folded into one bidirectional `datetime_string(DateTime, String, Format)/3`** (format when the datetime is bound, parse when the string is bound).
- **New predicates added:** `timestamp/2` (datetime ↔ POSIX epoch), `datetime_string_iso/2` and `date_string_iso/2` (ISO-8601 via `isoformat`/`fromisoformat`).

Design + plan: `docs/superpowers/specs/2026-07-04-datetime-snake-case-design.md`, `docs/superpowers/plans/2026-07-04-datetime-snake-case.md`.

Still outstanding (separate TODOs): the downstream rulebase corpus/library rulebase sweep; the sibling helper-library rename; `date-max-min-ordinal-apis.md`.
