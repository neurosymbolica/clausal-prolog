# fix(A04-F007): abandoned/crashed leader leaves table "evaluating" — later queries silently partial

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/04-runtime-tabling/findings.md` A04-F007
**Tests:** `tests/audit_2026_07_05/test_04_runtime_tabling.py::TestF007PoisonedEvaluatingTables` (2 xfail — flip to pass; 1 mechanism guard to flip)

## Bug

`make_tabled_wrapper_trampoline`'s leader path (`tabling.py:489-558`)
has `try/finally: pop_leader()` — but nothing removes or repairs the
`table_store` entry when the leader exits abnormally:

- **Abandonment** — `once(path(1,Y))` (or breaking out of any solve loop)
  closes the generator chain; GeneratorExit unwinds; entry stays
  `"evaluating"` with partial answers. Every later `path(1,Y)` takes the
  CONSUMER path with no live leader: yields the partial cached answers,
  suspends, gets converted to DONE → silently `[2]` instead of `[2,3,4]`
  (plus a spurious unbound answer — A04-F008). `once/1` over tabled goals
  is corpus-idiomatic; this poisons the module for its lifetime.
- **Exception** — a body error (e.g. ZeroDivisionError from `:=`)
  propagates; entry stays `"evaluating"`; re-query silently returns the
  pre-crash partial set instead of re-raising or recomputing.

Same structural gap in `make_tabled_wrapper_simple` (`:383-406`) — its
`finally` also only pops the leader.

## Fix direction

In the leader's cleanup distinguish normal completion from abnormal exit:

```python
try:
    ...drive + completion...
except BaseException:        # GeneratorExit, LogicException, Python errors
    table_store.pop(store_key, None)   # or entry.status = "aborted"
    raise
finally:
    pop_leader()
```

Popping the entry gives at-least-recompute-next-time semantics (correct,
cheap). Suspended consumers registered on the dying entry must also be
closed/awoken with DONE so their callers don't hang on a dropped entry.
Note `once()` deliberately abandons — the entry-pop must happen in the
tabled wrapper (GeneratorExit reaches it), not in `solve`.

## Acceptance

- `once(path(1,Y))` then full query → `[2,3,4]`.
- Exception fixture: second query raises ZeroDivisionError again (fresh
  recompute), not silent partial.
- Mechanism guard flips: no `"evaluating"` entries survive an abandoned
  `once()` (update `test_poisoned_entry_status_mechanism`, which pins the
  current poisoned state).
- Existing tabling tests green; a leader that completes normally is
  unaffected.
