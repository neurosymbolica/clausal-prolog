# Engine lane handoff — 2026-09-20, P2 Task 6: slices A+B done, C next

Branch `feat/predmeta-p2-head-cells-2026-09-19` in **/workspace/clausal**.
Nothing on main. Main `bd774c46` at every gate today.

**THE BRANCH IS GREEN — NEW 0 / GONE 1 vs main.** Stop and re-gate before
trusting anything below; the GONE is the load-sensitive C17 perf test that
has been GONE on every gate of this branch (passes 3/3 in isolation, both
rooms). xfail 37->40 is the three deliberately parked tests.

Rooms, both faithful and reusable:
`/tmp/claude-1000/-workspace-clausal-bug-fix/823f67d2-.../scratchpad/{kwwt,mainnow}`
(12 `.so`, venv symlink). C is identical main<->branch so no rebuild dance.

## Where Task 6 is

    bridge (`instances=True`)   15 -> 2    reflection 9 DONE, term_expansion 4 DONE
                                           clpb 2 REMAIN  <- slice C
    structural exit             79 + 76    UNMOVED, and that is correct

**The structural counts do not move until slice C.** Every cell arm added so
far sits BESIDE an instance arm; the arms can only be DELETED once nothing
produces instances. Slice C is what makes that true, and Task 5 (17 C
`PredicateMeta_type` arms) unblocks after it.

## Slice C — sized, and it needs NO operator ruling

corpus-lane swept `.clausal` AND `.seam` (931 files), the kit (43), the sealed
`eval/` trees (256), then every file of every type with no filter: **ZERO**
references to `BoolEq`/`BoolImpl` in any spelling. Engine-internal. Their
framing, better than mine: the retirement therefore cannot break a corpus file
by removing the `$`-twin TitleCase exemption.

Surface, measured: 8 engine files mention them, 6 test files, **22 structural
read sites**. The one place to read FIRST is `clpb.py`'s `_expr_to_bdd`, which
is BDD engine logic and already does

    if functor == 'BoolEq' and left is not _MISSING and right is not _MISSING:

— functor-based already, but with a `getattr(..., _MISSING)` guard, which is
**the exact fail-open shape** that produced six defects in slice A: against a
cell the getattr answers the sentinel, the arm does not fire, and nothing
raises. `clpz3.py` has the same `functor == 'BoolEq'` shape.

## READ THIS BEFORE TOUCHING A WALKER

One pattern produced six of slice A's defects: **a read that answers a DEFAULT
instead of failing.** `getattr(cell, "field", <default>)` returns the default,
the caller proceeds with a wrong-but-plausible value, and NOTHING raises. The
six: `_extract_init_final`, `_reified_clause`, `_atomize_declared_atoms`,
`_flatten_reified`, `_reified_children`, `_reified_findall_body_goal`.

Its mirror, four times: **a generic `isinstance(x, tuple)` branch catching
cells AHEAD of the specific branch.** In the renderer that made `++(X + 1)`
emit as raw `Escape(...)`, which then refuses to re-reify because the raw form
is TitleCase. When you add a cell arm, ask what ELSE already matches a tuple
and WHERE it sits.

Third: **`is_v` must not RAISE.** `compound_cell_shape` refuses the reserved
1-tuple `('x',)`; a type TEST has to answer, not propagate — a predicate that
raises cannot sit in a dispatch chain.

## Two tools that found bugs a grep could not

* **Scope-aware import check.** "Imported anywhere in this file" is NOT "in
  scope here" — `clausal/testing.py` imports `clausal.reflection` PER
  FUNCTION. Walk each FunctionDef; compare its own local ImportFrom names ∪
  module-level names against what it uses. It found three functions whose
  `NameError` was being swallowed by the repo's own
  `except BaseException: continue`, silently disabling the whole descent
  diagnostic.
* **Bracket-balancing receiver rewriter.** A regex character class cannot span
  `vfield(out, "goals")[0].args[0]`; a `[\w\[\]\.]*` receiver silently rewrote
  8 of 48 lines and reported success. Balance brackets leftwards. Parse each
  file before writing it.

Both live in this session's scratchpad; both are ~40 lines and worth
re-deriving rather than hunting for.

## Instrumenting, three rules paid for today

1. **In a `capsys` test a debug print goes into the CAPTURE.** "No output"
   then reads as "not called". Write the instrument to a FILE.
2. **Instrument on a COMMITTED base** — removing nine inserted blocks broke an
   `except` whose entire body was the instrumentation; the clean undo is
   `git checkout HEAD -- <file>` plus re-applying the real edits.
3. **Probe the branch actually taken before theorising about it.** Three
   hypotheses died to one four-line instrument that printed WHY a fallback
   fired.

## After slice C

* **The aliased-`assertz` adoption change** — RULED 2026-09-20, option (a)
  adoption wins: `-import_from` makes `db.row(name, arity)` in the importer BE
  the exporter's row; a local `-dynamic` on an imported name is an error or is
  ignored. Todo:
  `todo/aliased-assertz-loses-the-owner-under-cells-2026-09-20.md`. **The two
  `xfail(strict=True)` markers in tests/test_mutation_gate.py come OFF with
  it** — strict, so they fail loudly if not. Channel 4's wrong refusal message
  is fixed by the same move.
* Task 5 (C arms), then Task 7 (packages, 17 source files), 8, 9.
* Still parked, needs no action yet:
  `todo/two-copy-diagnostic-after-the-cell-flip-2026-09-20.md`.

## One correction to carry

The exporter `==`->`#=` flip is **already on main** — a62853e2, reverted
9faeaae1, then RE-LANDED by `6f1274ad` (`Revert "Revert ..."`), with §1(b)
shipped in 20c6dabb. `272e2a3f` is a duplicate of a62853e2 and is NOT in main.
I reported it as an open blocker from stale memory. **"Was it reverted?" is not
"is it in main?" — run `git merge-base --is-ancestor <sha> main`.**
