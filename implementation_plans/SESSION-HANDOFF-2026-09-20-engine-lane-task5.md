# Engine lane handoff — 2026-09-20c, Task 5: step 1 done, step 2 BLOCKED

Branch `feat/predmeta-p2-head-cells-2026-09-19` in **/workspace/clausal**,
tip `e73d78b0`, 62 ahead of `main` (`bd774c46`), 0 behind. Nothing on main.

**GATE: 146 failed, 16726 passed, 50 skipped, 40 xfailed, pytest exit 1;
extraction 146 = summary 146. NEW 0 / GONE 0 vs main AND vs the slice C tip.**
The +4 passed is exactly the new guard class.

Rooms: `.../823f67d2-.../scratchpad/{kwwt,mainnow}`, 12 `.so` each, venv
symlinked. **C is still identical main<->branch — nothing landed in C.**

## The headline

**Task 5 step 2 cannot be done. Not one of the 17 arms is dead.** The full
record is `todo/task-5-c-arms-are-all-still-live-2026-09-20.md`; the short
version is that the plan's premise ("the cell arms already walk `PyTuple`",
so the instance arms are dead) was written 2026-09-18, before Tasks 3/4/6,
and is false as stated.

    87  c_is_term_instance -> PredicateMeta INSTANCE
295430  c_is_term_instance -> @dataclass            <- Quantity et al, never goes
    63  py_term_field_names -> PredicateMeta arm
    25  c_term_field_names  -> PredicateMeta arm
  2646  py_is_atom          -> PredicateMeta arm    <- a CLASS, not an instance
     6  c_is_ground         -> PyType_Check class arm
     6  c_copy_term         -> PyType_Check class arm
     4  c_collect_vars      -> PyType_Check class arm

Three groups, three different release dates: the dataclass arm is not part of
this retirement at all; the four `PyType_Check` arms answer for a predicate
CLASS and go when the class goes (P4 — the same reason the plan already gives
for keeping `py_register_predicate_meta`); only arms 0/2/3 are instance arms,
and the ENGINE still feeds them from `solve.py:129` and
`list_dispatch.py:371`, with `database.py:1329`/`:1459` and
`database_ops.py:119` latent. `solve.py` spells
`getattr(cls, "_clausal_head", cls)` and every `PredicateMeta` has
`_clausal_head`, so that rebuild yields an instance.

**Re-sequence Task 5 after the P4 head-channel change.**

## What step 1 found

The pins Task 5 step 1 asks for already existed — `_corpus()` in
`tests/test_python_fallbacks.py`, from P3-2 Task 2C, 38 shapes through the
raw C entry points and the Python twins. **Three of its rows had stopped
testing what they are named.** `("instance", Pt(x=X, y=2))`,
`cell_in_instance` and `instance_in_cell` were written when `Pt(...)` built
an instance; Task 3 made the plain call build the CELL. All three became
duplicates of shapes already in downstream code, the C instance arms stopped being
exercised by that file, and NOTHING FAILED.

Fixed to `Pt._clausal_head(...)` with `TestTheCorpusStillCoversInstances`
pinning it, plus the mirror so the guard cannot be satisfied by making
everything an instance. Parity holds for the restored rows.

**The general lesson, and it will bite again in Task 7:** a constructor flip
silently re-points every test fixture that used the constructor. A fixture
named for the old shape keeps passing on the new one. After flipping a
producer, grep the TESTS for its constructor and assert the shape each
fixture claims.

## The instrument, worth re-deriving (~30 lines of C)

Eight counters in `_variables.c`, one per arm, plus a `METH_NOARGS`
accessor; a pytest plugin dumps them at `pytest_sessionfinish` **to a FILE**
(in a capsys test a print goes into the CAPTURE and "no output" reads as "not
called"). Anchor points, all unique strings:

1. `static PyObject *PredicateMeta_type = NULL;` — counters + `ARM(i)` macro
2. `c_is_term_instance`'s `if (r) return 1;` — the PredicateMeta arm
3. its `PyObject_HasAttr(..., str_dataclass_fields)` return — the dataclass arm
4. `py_term_field_names`' and 5. `c_term_field_names`' `if (r) {` arms
6. `py_is_atom`'s `if (!r) Py_RETURN_FALSE;`
7-9. the three `if (PyType_Check(term) && PredicateMeta_type) {` (split on
   that exact line and re-join — there are exactly three)

To identify PRODUCERS rather than counts, have the arm record
`Py_TYPE(obj)->tp_name` into a static `PySet`. That is what turned "87 hits"
into "43 names, all test-minted". For the Python side, a plugin that wraps
`PredicateMeta._clausal_head` and keys a Counter on
`sys._getframe(1)` file:lineno separates ENGINE callers from test callers —
that is what found `solve.py:129`.

**Build it in a throwaway detached worktree, never in a room you gate from**,
and `git worktree remove --force` it after: the instrumented `.so` must never
be the one a gate runs against, and the modified `.c` must never land.

## Two traps paid for today

1. **`venv/bin/python <script.py>` runs against CANONICAL, not your tree.** A
   script file puts its OWN directory on `sys.path[0]`, not the cwd, so
   `import clausal` resolved to `/workspace/clausal`. Use a heredoc on stdin
   (`venv/bin/python - <<'PY'`) from the room, and **assert the room's name is
   in `clausal.__file__`** as the first line of every probe.
2. **A build worktree needs the other eleven `.so` copied in** before it can
   run anything, and `--inplace` rebuilds all twelve anyway. Check
   `/proc/*/map_files` for live importers of the target `.so` first; there
   were none, which is the only reason an in-place build was safe there.

## Next

* **The aliased-`assertz` adoption change** — RULED 2026-09-20, option (a),
  adoption wins. `todo/aliased-assertz-loses-the-owner-under-cells-2026-09-20.md`.
  **The two `xfail(strict=True)` in tests/test_mutation_gate.py come off with
  it.** This is the ruling that gated the branch from landing, and it is now
  the only thing between this branch and a merge.
* **Task 7** (packages, 17 source files) — unblocked, and independent of the
  Task 5 blocker. Carry the fixture lesson above into it.
* Task 8, 9.
* Task 5 step 2: after P4's head channel. Do not attempt before.
