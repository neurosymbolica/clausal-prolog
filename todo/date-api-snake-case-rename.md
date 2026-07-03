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
2. Update `docs/clausal-cheatsheet.md` §3 (Dates) + `kit/scaffolding/temporal-skeleton.md` +
   `kit/scaffolding/*` to show snake_case (`date(YEAR,MONTH,DAY,OBJ)`, `days_between(A,B,N)`, …).
3. Then sweep `clausify-domains` rulebases from the TitleCase names to snake_case (mechanical
   `-import_from(date_time, [...])` + call-site rename; the corpus temporal domains are
   posted-workers, de-minimis, gdpr-arts33-34, both schengens, temporal-skeleton).
4. Finally drop the TitleCase aliases.

## Related
- `todo/date-max-min-ordinal-apis.md` (clean ordinal/max/min date APIs — do together, all snake_case).
- Sibling request: spell out + snake_case the `formalize_lib` helpers (`prof_get`→`profile_get`,
  `prof_has`→`profile_has`, `attr`→`attribute`) — see that lib's todo. Same rationale (less for the
  local models to learn; closer to Prolog).
