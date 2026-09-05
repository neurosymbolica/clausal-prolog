# packages/ Python-side reconstruction of declared data functors breaks post-flip

Found during the P3-2 whole-branch final review. Plan-acknowledged, not a
surprise: `implementation_plans/python-seam-classes-as-functors.md`'s own
"Origin" paragraph names exactly this consequence of R6 ("data-functor
classes stop being minted") — this todo is the concrete, verified inventory
of where it lands in `packages/`, filed so the seam work has a real target
list instead of a general worry.

Imports were verified clean by the final review (74 modules, zero missing
names) — nothing in `packages/` fails to IMPORT. This is a semantic break at
USE time: Python code that used to receive a `PredicateMeta` class for a
declared data functor now receives its interned spelling (a plain `str`),
and code that assumes the former shape breaks when it runs.

## Where it lives

`packages/clausal-provenance` is the concrete instance: 103 `.clausal`
fixtures under `packages/` declare data functors the way
`packages/clausal-provenance/tests/fixtures/provenance_reach.clausal` does
— `Edge(SRC, DST)` exported with no clauses of its own (an EDB relation
supplied as data at query time, not a predicate), and
`packages/clausal-provenance/clausal/modules/provenance/engine.py`
reconstructs term instances from stored tuples via `cls(**kwargs)` at
roughly 10 sites (`_walk_term`, `_renew_term`, `_filter_by_goal`, and their
neighbours).

## Verified break (precise, reproducible mechanism)

Read directly, not inferred: `provenance_reach.clausal` registers `Edge` for
bottom-up evaluation with `bottom_up_(Edge)` at module-load time. The
registration goal
(`packages/clausal-provenance/clausal/modules/provenance/_registration.py`,
`_RegistrationGoal.__call__`) does:

```python
cls = deref(cls)
cls = _resolve_loadname(cls)
if not isinstance(cls, PredicateMeta):
    raise TypeError(
        f"{self._name} expects a PredicateMeta class, got {cls!r}. "
        "Use the bare class name, e.g. `bottom_up_(Path)`."
    )
setattr(cls, self._flag, True)
```

Pre-flip, `Edge` (a declared data functor with no clauses, compiled under
the `-tagged_terms`-off/bridge era) bound a `PredicateMeta` class, so this
resolved fine. Post-flip (R6: "a declared data functor mints no reachable
class any more — the name binds its interned spelling"), the bare reference
`Edge` in `bottom_up_(Edge)` binds the `str` `"Edge"`. The `isinstance`
check fails and raises:

```
TypeError: bottom_up_ expects a PredicateMeta class, got 'Edge'. Use the
bare class name, e.g. `bottom_up_(Path)`.
```

at module load — before any query runs. This is deterministic and
independent of the `~10` `cls(**kwargs)` sites in `engine.py` (those are
downstream of registration and guard with `is_term_instance(term)` first,
so a cell tuple mostly just falls through their earlier
`isinstance(term, tuple)` branch rather than reaching `cls(**...)` — the
registration break above fires first and harder, at load time, for every
fixture that registers a pure-data EDB relation this way).

The other five `.clausal` fixtures under `packages/clausal-provenance/tests/
fixtures/` (`datalog_reach`, `mnist_sum`, `mutual_recursion`,
`negation_aggregate`, `top_k_engine`) declare and register EDB relations the
same way and are expected to hit the identical break; not individually
re-verified here (the mechanism is uniform — this repo's job is the
inventory and the mechanism, not a fixture-by-fixture crash log).

Not independently re-run end-to-end in this session:
`clausal.modules.provenance` is a `packages/`-local namespace package not
installed in the venv this session works from (no `pip install -e
packages/clausal-provenance` was done — installing packages is outside a
fix-or-record wave's scope). The mechanism above was confirmed by direct
source reading, not by executing the failure.

## Why it's not fixed here

- This is the exact seam gap `implementation_plans/python-seam-classes-as-
  functors.md` exists to close (Python classes as functors; instance
  ingestion; the tag-domain ruling R10 it is waiting on) — a real design
  task with an already-parked plan, not a local patch.
- `packages/` is downstream of core (the P3-2 mandate was the engine's
  representation flip); rewriting `packages/clausal-provenance`'s
  reconstruction logic is package-maintainer work that depends on which
  seam shape ships.
- The break is confined to Python-side code that treats a declared data
  functor's name as a class (registration helpers, `cls(**kwargs)`
  reconstruction). Pure `.clausal`-side construction and matching of the
  same functors (e.g. `Path(SRC, DST) <- Edge(SRC, DST)`,
  `solve(boolean, FACTS, Path("a", "b"), R)`) compiles through the ordinary
  cell-emission path and is unaffected — the compiler never "calls" the
  runtime binding for a source-written functor reference, it emits a cell
  literal directly.

## Migration options (from the seam plan)

1. **Build cells directly.** Rewrite `packages/clausal-provenance`'s
   reconstruction and registration code to work with plain tuples
   (`("Edge", "a", "b")`) instead of minting instances — matches the engine
   as it stands today, no core dependency, but every `cls(**kwargs)` site
   and every `bottom_up_`/`pure_`-style registration helper that assumes a
   `PredicateMeta` class needs its own rewrite.
2. **Class-functor cells per the seam design.** Once R10 (the tag-domain
   ruling in `implementation_plans/python-seam-classes-as-functors.md`)
   lands, `packages/clausal-provenance` could import a Python class per
   relation and let a term built naming that class construct a cell with
   the class object in slot 0 (`(EdgeCls, "a", "b")`) — closer to today's
   `cls(**kwargs)` shape (`cls` is a real, addressable class again) and
   lets `bottom_up_`/`pure_` keep `isinstance(cls, PredicateMeta)`-shaped
   checks by swapping the check's target type, not its structure. Blocked
   on that plan shipping.

Either direction is package-maintainer work once one is chosen; this todo's
job is only to make the break, and the choice, visible.
