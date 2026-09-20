# Engine lane handoff — 2026-09-20, P2 Task 4 sweep (in progress)

Branch `feat/predmeta-p2-head-cells-2026-09-19` in **/workspace/clausal**.
Nothing of this branch is on main. Main is `bd774c46` and moves under you —
three different sessions wrote it in the last two days.

## What is ON MAIN (landed 2026-09-19, gated NEW 0 / GONE 0 against main)

* the keyword-term refusal (`KEYWORD_ARGUMENT_SEVERITY`, 34 source sites + 28
  test pins migrated) — ruled by the operator: disable now, delete in P4;
* `tools/division_census/` — measures which engine divisions come out UNEVEN;
* the checkout/worktree failure-count fix (see ROOMS below).

## THE NUMBER, and how to reproduce it

    414 -> 393 -> 242 -> 207 -> 142 NEW failures vs main, 0 regressions

**ROOMS.** /workspace/clausal reads 147 failures where a worktree reads 144 at
the same sha, from TWO causes pointing opposite ways: the checkout OVER-counts
by 1 (untracked gitignored `tests/**/__transformed__/*.py` dumps that
ast-walking guards choke on — fixed on main) and a worktree UNDER-counts by 2
(`test_transitive_py_module_import` skipif wants `<root>/venv/bin/python`; a
worktree has none, so they SKIP, they do not pass). **A faithful room is:**

    git worktree add --detach <wt> <sha>
    cp all TWELVE .so files in                  # not just _variables
    ln -s /workspace/clausal/venv <wt>/venv     # skipif uses abspath, not realpath
    cp tests/**/__transformed__/*.py in         # only if reproducing the checkout

**Positive control before trusting any diff:** the baseline arm must reproduce
all three checkout-only failures and ZERO skips.

**The run:**

    timeout 900 venv/bin/python -m pytest tests -q -rfE -p no:cacheprovider \
        --continue-on-collection-errors --ignore=tests/test_clportools.py

`-rfE`, never `-rs`: **`-rs` REPLACES the default reportchars**, so the summary
lists skips and NO `FAILED` lines and every extraction silently reads zero.
Always print the extracted count beside the summary line and compare them.

## HOW THE SWEEP IS BEING DONE — read this before continuing

Not down the census in file order. **Failure-driven, ranked by the engine frame
that RAISES**: the census says where the sites are, the tracebacks say which
ones matter. Collect the NEW ids, run just those with `--tb=long` (through a
python driver, NOT the shell — zsh does not word-split `$VAR` and the ids
contain spaces), then:

    grep -oE "^clausal/[a-z_0-9/]+\.py:[0-9]+" tb.txt | sort | uniq -c | sort -rn

One line in `specialization.py` carried 85 failures AND 79 load errors.

## WHAT THE FOUR BATCHES FOUND (commits eb6a59db, 8ec4d372, 693bd739, 3859368f)

Two of the defects were **SILENT** — wrong answers, no error — and both are the
same shape: **a cell is a tuple, so anything that treats a tuple structurally
now swallows a term.**

1. `coroutining._install_when_condition` read `('nonvar', X)` as a
   CONJUNCTION (length 2!), destructuring it into `c1='nonvar', c2=X`. The
   conjunction arm now requires `cond_functor is None`.
2. `for _ in pred(*args)` drove a predicate; now it iterates the TUPLE and
   yields one "solution" per element, every argument unbound. `call(pred, *args)`
   is the surviving form.

**Watch for more of this shape.** Any `isinstance(x, (tuple, list))`,
`len(x) == 2`, or unpacking `a, b = x` in term-handling code is suspect.

Also fixed: `specialization.py:2121` (last `getattr(head, field)`),
`solve._deref_walk_py` calling `_clausal_head` on non-PredicateMeta classes
(`BinOp`), `test_fast_construction`'s 47 classes now built `instances=True`
(the `_clausal_new` fast path is unreachable for a cell and retires in P4),
and ~130 `solve(...)`/helper call sites threaded with an explicit module.

**R-P2-2 in practice:** a cell carries no module and `solve` REFUSES to guess
(module locality). Every `solve(goal)` that relied on inference needs
`solve(goal, module)`. The AST sweep catches `solve(<name>.<pred>(...))`; it
does NOT catch `getattr(m, n)(...)`, dotted module paths, or helpers that take
a goal and have no module of their own. Derive the module from the name the
goal's attribute came off; where that is not derivable the sweep must REPORT,
not guess (one `_run_clausal` call did, and was threaded by hand).

## NEXT, in order

1. **`dcg.py` is `needs-db` and STOPS the sweep there** (marked in
   `P2_SITES.tsv`, commit 3859368f). `phrase/2,3` resolve a nonterminal to a
   CLASS and dispatch at written-arity+2; a cell names the predicate but there
   is no db/module_dict in a plain `_builtin` to resolve it. Making them
   `_db_builtin` is plumbing — an operator-visible decision, not one of the
   three rewrites. **17 `test_dcg` failures wait on it.**
2. Remaining clusters: `test_builtin_classes` 15, `test_predicate_meta` 14,
   `test_hide_directive` 8, `test_control` 7, `test_date_query_args` 6,
   `audit_2026_07_05/test_06_clpfd` 6, then a long tail.
3. **The structural exit is NOT the failure count.** Task 4 exits at
   `is_term_instance(` / `term_field_names(` = 0 in `clausal/` outside
   `predicate.py`. Still **80 + 77**. A dormant site passes today and breaks
   the first time something reaches it.
4. Then Task 5 (17 `PredicateMeta_type` arms in `_variables.c` — C change, so
   the rebuild-and-swap dance) and Task 6 (17 `instances=True` bridge
   declarations: the reflection vocabulary, clpb's BoolEq/BoolImpl, term
   expansion's state). **Those two are what block step C of the head flip**,
   measured: `_clausal_head` still takes 213,713 calls a suite from the bridge.

## THE MISTAKE NOT TO REPEAT

Every gate before 2026-09-20 ran against the Task 3 checkpoint `20b32550` as
baseline — a tree that is RED BY CONSTRUCTION and spins in specialization. Each
"NEW 0" was true and meaningless; the branch was 414 away from main and I
reported it as gated. **Gate against what you intend to merge into, every time,
and re-gate after a rebase.** The existing note that a failure-set diff cannot
see what its baseline contains is only half of it.
