# `_date_4` is NOT dead — it implements `ymd_date/4`. Coverage ported; deletion blocked.

**Raised:** 2026-09-01, from the `date/3` migration (`spike/date3`, `c1929462`).
**Revised:** 2026-09-01, after measuring. Half of it is done; the other half
rested on a premise that is false, and the correction is the point.

## What this todo originally said, and why it was wrong

> `_date_4` — the Python function — was left in place, **unregistered**, and
> marked in-source as dead.

It is not unregistered. `clausal/modules/py/datetime.py:805`:

    ymd_date = ModulePredicate("ymd_date", module="datetime")
    ymd_date._register(4, simple_to_trampoline(_date_4))

`ymd_date/4` is the transitional alias added by `ff7c125a` — the SAME
components↔object relation, under a name that does not collide with the
incoming arity-3 `date` TERM. `_date_4` is its live implementation. Deleting it
would break every caller:

    clausify/kit          61 sites in  9 files
    clausify-domains      26 sites in 11 files
    clausal itself         4 sites

The registration comment already states the real condition — **"DELETE when it
has no callers"** — and it has 91. The two facts (`date/4` retired, `_date_4`
retained) were run together into "unregistered and dead"; only the first is true.

## DONE: the coverage half

The concern that motivated this todo was real — the 13 `_date_4` sites cover
semantics `date/3` must honour too. Measured against `date/3` today, it already
honours all of them:

    date(2024, 2, 29)     -> datetime.date(2024, 2, 29)     leap accepted
    date(2025, 2, 29)     -> LogicException domain_error     leap rejected
    date(2020.9, 1, 5)    -> LogicException type_error       float not truncated (F015)
    date(2020, 1.9, 5)    -> LogicException type_error

but `tests/test_date_term.py` did not PIN all of them. Rejection of 2025-02-29
and of a float YEAR were already covered; leap-day ACCEPTANCE and a float in the
MONTH/DAY slots were not — so a constructor that rejected every 29 February, or
truncated a fractional month, would have passed. Now covered (12 -> 15 tests).

Nothing was deleted to make room: `ymd_date/4`'s own tests still exercise
`_date_4` directly, which is correct, because it is still a live predicate.

Also pinned while there: `date(2020, True, 5) == date(2020, 1, 5)`. `bool`
subclasses `int`, so this follows `datetime.date` exactly — but the corpus's gold
harnesses take the OPPOSITE view and exclude bool explicitly
(`isinstance(x, int) and not isinstance(x, bool)`). The two disagree. Recorded as
a pinned behaviour so that making `date/3` stricter is a decision someone takes,
rather than a divergence found later. **This is the one open question here.**

## DONE 2026-09-01 — `_date_4` and `ymd_date/4` are deleted

The blocker recorded here earlier was real and was resolved by an operator
ruling rather than by code: **bad dates should fail fast and loudly.**

`ymd_date/4` FAILED on a calendrically-invalid triple where the `date/3` TERM
RAISES, and `kit/rolling_window`'s E-malformed tests required the failure. That
looked like it needed a construct-or-fail primitive to preserve. It did not —
the behaviour being preserved was a SILENT one, and explicitly out of contract:
`max_stay.clausal` §6.3 / DIFFERENTIAL E2 classed a malformed history item as
unreachable within the declared `raw_input_contract`. So the ruling was to let
it raise, and update the out-of-contract tests to say so.

### What was done

| phase | what | commits |
|---|---|---|
| 1 | 82 ground-literal sites | clausify `156ef73`, domains `4e7160d3`, train `d8ed0e7` |
| 2a | 6 computed-component sites (sara_irc_tax, irc_s121) | domains `dcb7d62d` |
| 2b | 3 transitional compat clauses | clausify `35521d6`, train `21a991b` |
| 2c | rolling_window + its tests; schengen E2 re-pinned | this change |
| 3 | `_date_4` and the `ymd_date/4` registration deleted | this change |

`day_of/2` now constructs through `date/3`, so an invalid endpoint raises
`error(domain_error("date", date(2024, 2, 30)), 'date/3')` and the raise
survives `findall`. The three E-malformed tests assert that, catching the
STRUCTURED ISO ball rather than substring-matching: `sub_atom/5` raises
`type_error(atom, ...)` on a compound, and matching the shape also asserts WHICH
error, so an unrelated failure cannot pass them by accident.

### Coverage, and what did NOT port

The 13 `_date_4` call sites are gone. What they pinned lives in
`tests/test_date_term.py` and is stronger: `date/3` RAISES where `_date_4`
failed silently, and the float test now covers the month and day slots where
the audit version checked only the year. One semantic deliberately did NOT
port: `_date_4` decomposed a `datetime.datetime`; `date/3` rejects one
(`test_a_datetime_is_not_a_date`). That is the Liskov ruling, not a regression.

`test_py_interop_type_notes` kept its `_timedelta_3` half — `date/3` has no
equivalent hazard, because an unbound component yields a `_DatePattern` for
unification rather than calling the stdlib constructor at all.

### Acceptance

Full clausal suite, failure set compared BY NAME as this todo required:

    baseline  143 failed, 12308 passed, 50 skipped, 37 xfailed
    after     143 failed, 12294 passed, 50 skipped, 37 xfailed
    diff      IDENTICAL — 0 new, 0 fixed

Collection is -14 items, every one of them a deleted `_date_4`/`ymd_date` test
and nothing else (full collect-only set diffed, no other item moved).
`143 + 12294 + 50 + 37 = 12524` = collected, so every item is accounted for.

Corpus: schengen_90_180_max_stay 81/81, schengen_90_180 27/27,
working_time_average 3639/3639, posted_workers 32/32, de_minimis 39/39 —
all unchanged. Kit suites at baseline except test_rolling_window 35 -> 36
(two E-malformed tests became three).

The `++` error-bridge todo is no longer a dependency of this one; it was routed
to `/workspace/clausal-bug-fix/todo/` and stands on its own merits.
