# W4b-2d — the class-USING sites: a lane handoff

**For:** a dedicated instance owning W4b-2d.
**From:** engine-lane, 2026-09-23. Canonical main `a5466fa2`.
**Status of everything below:** measured this session unless marked INFERENCE.

---

## 1. Why this is its own lane

W4b-2 is migrating 49 sites off `isinstance(x, PredicateMeta)` before a flip
that makes a predicate's module attribute a mangled atom instead of a class.
The working premise was **migrate the sites, then flip** — W1's standing
"a migration, not a flag day" ruling.

Measured by doing it: **that premise only half-holds.** Of the 49, seven
migrated. The rest split into sites that need a different accessor (F2b, 13
rows — mine, in progress) and, crucially, **13 sites that do not merely TEST
the binding: they USE THE CLASS OBJECT.**

For those the order **inverts**. They cannot migrate ahead of the flip,
because there is nothing yet to migrate *to* — they need the flip to supply a
replacement for "the class object" first. That is a design problem, not a
migration, and it is this lane's job.

## 2. What already landed (do not redo)

| commit | what |
|---|---|
| `a6296ba4` | the era-agnostic resolver + 7 migrations |
| `8157b2de` | `qualify_mangled_goal` tests Clausal-ness, not `sys.modules` |
| `a5466fa2` | design doc for F2b and a sizing pass over the hard families |
| `b547c24b` | `field_names_for` narrowed to field NAMES; declaredness is `db.declared_kind` |
| `4f5a1bd7` | W4b-0, the W4a inbox (dead `_clausal_new` gates, `c_term_field_names`) |

**The resolver, which you consume** (`clausal/logic/predicate.py`):

    resolve_predicate_row(binding, *, arity) -> PredRow | None
    is_declared_predicate(binding, *, arity) -> bool

Era-agnostic: a class binding and a mangled-atom binding for the same
predicate return the **same row object**. `arity` is keyword-only and
required — there is no inference path, deliberately. Validity is
`_db_for_module_name(...)`, never `sys.modules`.

**What the resolver cannot serve, and why you exist:** it returns a *row*.
Every site below needs the *class*, or something that can stand in for one.

## 3. The three sub-problems, with their mechanisms

### 3a. `through=` — the sharpest, ~7 of the 13

`Database.mutate` and `Database.refusal_for` take `through=`. Internally,
`database.py:793`:

    other = getattr(through, "_row", None)

A `PredRow` has no `._row`. So handing one to `through=` does not raise —
**it silently resolves to nothing**, and the mutation gate becomes a no-op
that fails open on exactly the writes it exists to police. That is the worst
available failure shape and no test would see it.

Sites: rows 28 (`compiler_v2.py:899` `_refuse_foreign_writes`), 29
(`compiler_v2.py:932` `_imported_class`), and their neighbours.

**Design question:** what does `through=` accept post-flip? A row? A
`(functor, arity)` key? Whatever you choose, the *silent* failure must
become loud first — fix the `getattr` to refuse an unexpected shape before
anything starts passing it new ones.

### 3b. `_install` — and a LEAD worth checking first

`compiler/predicate.py:2185`. Its docstring (line 1736) says it "Also
installs on the PredicateMeta class (and `db.set_dispatch()`)". Reading it:
line 2246 calls `db.set_dispatch(functor, arity, fn, lazy_recompile=...)`
and line 2276 sets `row.dispatch_fn = fn`.

**So it may already write everything the row needs, and the class write may
be redundant.** If so, rows 53-56 collapse from a design problem to a
deletion. INFERENCE — I did not verify that the class write has no reader.
**Check this before designing anything**, because it is the cheapest
possible outcome and it would remove four of the thirteen.

### 3c. `analyze_mi` / `call` / `specialize_mi`

These take the class because they need something *callable*, or need class
identity, not row state. Rows 32, 33 and neighbours. Least explored; expect
this to be where a genuine new abstraction is needed.

### 3d. The five arity-less move-outs

Rows 4, 25, 27, 29, 60 had no independently-known call-site arity. Row 60
(`builtins/io.py:594`) is the instructive one: the captured class is read
later by `_indicator_row` against the *requested* indicator arity, which may
legitimately differ from the class's own. Resolving to a row early would mean
guessing which arity matters. These may resolve themselves once 3a-3c settle.

## 4. Operational rules — each of these cost someone a session

* **A worktree per lane.** `/workspace/clausal` is shared with other
  instances. Never `git checkout` a branch there; `git worktree add` your own
  room. Symlink `venv -> /workspace/clausal/venv` and copy the `.so` files in.
* **Never `git add -A`, never `git stash`.** Both sweep up other lanes'
  in-progress work. Stage explicit paths. `git branch --show-current` before
  every commit.
* **Verify the engine before trusting any number:**
  `./venv/bin/python -c "import clausal; assert clausal.__file__.startswith('<room>')"`.
  Run pytest FROM the room. A *script file* puts its own directory on
  `sys.path` and you will silently test a different engine — this happened to
  me today.
* **GATES ARE THE SCARCE RESOURCE, NOT AGENTS.** Measured: two concurrent
  full suites turned a 166s run into **949s**, and killed another at 89% of
  the way through, yielding an **empty extracted set** that would have read as
  "0 failures" without a non-empty assertion. Always assert your extracted set
  is non-empty before comparing. Serialise suite runs.
* **Two tests are load-sensitive timing assertions**:
  `test_F026_multi_star_splits_bounded_for_moderate_input` and
  `TestSortDedupCost::test_many_distinct_strings_sort_in_linear_time`. The raw
  function timed 12.37 / 12.45 / 11.48s against a 3.0s threshold under load,
  and **fails on main too**. Attribute by running the same test on main under
  the same load before ever calling it a regression.
* **The gate:** `pytest tests -q -rfE -p no:cacheprovider
  --continue-on-collection-errors --ignore=tests/test_clportools.py`, extract
  `FAILED|ERROR` node ids, `comm` against a baseline you regenerated yourself.
  Baseline on `a5466fa2` is **146 failed / 16836 passed**. Do not trust that
  number — regenerate it.
* **A failure-set gate cannot see a removed passing test.** If you retire
  tests, diff the **collected node ids**, not the failure set.
* **No C is involved in W4b-2d.** If that changes, build in a same-sha
  worktree and rename-swap (`cp` then `mv` inside the destination directory);
  never `build_ext --inplace` on a tree long-lived processes have imported.

## 5. Coordination with engine-lane (me)

I am continuing with **F2b (13 rows)** and then F5/F9 in this session, in my
own worktrees. We will not collide on files — your sites are the class-USING
ones, mine are the name-as-atom coercion — but **we will collide on the
suite**. Agree a cadence, or ping before a full run.

I hold the operator relationship for the rulings in §6; if you need one
answered, route it through me rather than asking separately, so we do not
put the same question twice.

## 6. Open rulings you may depend on

1. **The error shape** for an unresolvable mangled goal —
   `existence_error(procedure, Name/Arity)` for both cases is proposed, under
   review. Affects `qualify_mangled_goal`'s second half, not your sites
   directly.
2. **F4** — a diagnostic wanting "the arity" of a name declared at several
   arities. Under review.
3. **F7** — `_dispatch_at`'s arity-aware arm when `PredicateMeta` goes. This
   one **does** touch you: it is the same "the class was the thing that
   answered" problem in the dispatch funnel. Under review.

## 7. Done looks like

Every one of the 13 class-USING sites either migrated, or explicitly deferred
to W4b-3 with a stated reason and a named replacement. `through=`'s silent
failure made loud. The `_install` lead resolved either way. Gate NEW 0 /
GONE 0 against a baseline you regenerated. And the 49-row tracking document
(`implementation_plans/w4b1-site-classification-2026-09-22.md`) updated —
note it is already stale on row F10, which landed in `ca4e49dd`.

## 8. Reading order

1. `implementation_plans/w4b2-open-questions-2026-09-23.md` — families, and
   the controller corrections at the end.
2. `implementation_plans/w4b2-f2b-and-hard-families-2026-09-23.md` — sizing.
3. `implementation_plans/w4b1-site-classification-2026-09-22.md` — the rows.
4. `.superpowers/sdd/w4b2b-resolver-report.md` — the per-row move-out table
   with reasons. **This is your worklist.**
5. `implementation_plans/w4b-class-retirement-scope-2026-09-22.md` — where
   W4b-2d sits in the whole retirement.
