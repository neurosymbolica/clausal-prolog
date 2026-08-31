# The lazy stub reinstalls itself, so `sys.meta_path` can accumulate duplicates

**Severity:** low — no known misbehaviour today. Filed because it is the
remaining half of a fault that already cost a whole suite once, and because the
cheap guard against it no longer exists after the recursion fix.

## Symptom

`_LazyHookFinder` (`clausal/_lazy_hook.py`) reinstalls itself when `clausal` is
cleared from `sys.modules`. A caller that sweeps `sys.modules` repeatedly can
therefore leave more than one stub instance on `sys.meta_path`.

Observed while fixing
`todo/done/lazy-hook-find-spec-infinite-recursion.md` (merged as `ea317aae`):
`auto/tests/test_check_certificate.py` deletes every `clausal*` entry from
`sys.modules`, and because the stub lives on `sys.meta_path` it survives the
sweep and reinstalls.

## Why it matters even though nothing is broken

The recursion fix guards re-entry with an in-flight name set held on a
`threading.local`, **per stub instance**. Two stub instances therefore have two
independent guards. The recursion that fix prevents is a single instance
re-entering itself; whether two instances can bounce a name between them has not
been tested. The original fix chose the in-flight guard over "consult only the
later `sys.meta_path` finders" partly *because* the alternative would not
survive a second stub instance — so duplicate stubs are known to be the shape
this design is least sure about.

Duplicates also make every failed import walk the stub twice, and make
`sys.meta_path` grow without bound under a test suite that sweeps in a loop.

## What to do

1. Make installation idempotent: before inserting, check whether an instance of
   this class is already on `sys.meta_path` and reuse it. Prefer identity of the
   class over `isinstance`, so a subclass is not silently reused.
2. Add a test that sweeps `sys.modules` of `clausal*` N times and asserts the
   stub count on `sys.meta_path` stays at 1.
3. With idempotent installation in place, check whether two instances *could*
   have recursed through each other — if they could have, say so in the commit,
   because that reframes the severity of the merged fix.

## See also

- `todo/done/lazy-hook-find-spec-infinite-recursion.md` — the recursion itself,
  fixed; its "Left undone" section is where this was first recorded
