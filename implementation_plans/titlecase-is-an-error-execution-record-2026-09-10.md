# TitleCase in a Clausal position is a load-time error — execution record

**Branch** `feat/titlecase-is-an-error-2026-09-10`, 22 commits on d6d4cea0.
**Landed** clone `main` 2026-09-10. Canonical/box: see the sha line at the end.
**Operator's word** "land when the closing review has no High" — given before the
branch was built, and the condition was met twice over (reviews 37 and 38).

## What changed

`TITLECASE_IDENTIFIER_SEVERITY` flips from `"warn"` to `"error"`: a TitleCase
identifier in a Clausal position no longer loads. The message names the remedy —
a snake_case rename, or `++Name` when the name is a Python class. Import-list
names stay exempt, hosted Python is not read at all, and two deprecation
witnesses stay on the old spelling on purpose so a test can assert the error.

Everything the flip made unloadable was migrated: the engine's hook lookups
(`term_expansion`, `rewrite_clause`, `match_clause`, `memberd_t`), stdlib,
rewrite rules, examples, fixtures, codegen goldens, package fixtures, and the
docs' fenced blocks. `tests/test_titlecase_gate.py` is the permanent gate: it
measures the whole repository with the lint itself rather than a grep, so a
file that imports a TitleCase Python class through its import list reads clean
and one that spells it bare does not.

## Defects found and fixed after the migration was "done"

Four review rounds ran (roborev jobs 35, 36, 37, 38). Every one found something
real; none of the last two found a High. The substantive ones:

1. **The string-callable sugar bypassed the lint entirely.** `visit_Call`
   rewrites `'Foo'(X)` to the name `Foo` AFTER the lint has walked the raw
   tree, so `'Foo'(1),` and `go(X) <- ('Foo'(X))` loaded and failed late — at
   call time with `PredicateNotFoundError`, or at exec with `'str' object is
   not callable`. The lint's walk now reads a string callable as the identifier
   it names.

2. **Closing that opened an ISO hole.** The fix taught the trailing-comma fact
   recogniser to read the sugar as a head by lowering the string Constant to a
   `Name` on the spot, which skipped what `visit_Call` does for the same sugar
   in a body. `"foo"(1),` then LOADED as a fact for foo/1 while `"foo"(X)` in a
   body was still refused per ISO 6.3.3 — the head silently carrying a meaning
   it loses when the `double_quotes` default flips to `chars`. The refusal now
   lives in one function both readings call.

3. **A fact head is not a body goal.** A body goal may name any atom
   (`'foo bar'(X)` compiles and solves), but a fact head is compiled to a
   functor class whose name is emitted as Python source and re-parsed. A
   spelling that is not an identifier, or is a Python keyword, made that source
   unparseable and showed the author CPython's complaint about a line they
   never wrote: `'foo bar'(1),` gave "invalid syntax. Perhaps you forgot a
   comma?" and `'class'(1),` gave "invalid syntax (<unknown>, line 4)" — no
   file, no line, no cause. The head now refuses in its own words.

4. **The translator's variable-shaped-name refusal was one spelling short.** It
   keyed on an initial capital, so `'_foo'(x)` was emitted as `_foo(x)` — which
   `_is_logic_var_name` classifies as a logic variable. Same defect as the
   `'FOO'`/`'X1'` cases it was written to close. The test is now
   `not _is_plain_atom_name` on an identifier, which also drops a dead conjunct.

5. **The renamed-spelling carve-out gave wrong advice.** `Test` is on the
   carve-out list because `Test/1` was the old test-predicate spelling, so a
   file whose own hosted Python defined `class Test:` was told "Rename `Test`
   -> `test`" — a predicate that does not exist. Control: the same file with
   `class Widget:` was correctly told `++Widget`. The carve-out now yields to
   the file's own bindings.

6. **Seven documents still stated the retired PascalCase rule.** The import
   direction stopped PascalCasing predicate names, and that was TRUE on
   d6d4cea0 — measured, not recalled: baseline translates `foo_bar(1).` to
   `FooBar(1),` and this branch to `foo_bar(1),`. Corrected in the two
   translation docs, both backend pages, `testing.md` and the SymPy page. The
   ISO compatibility report was NOT rewritten: it says on its face that it is a
   record dated 2026-03-25, so its table is annotated in the banner instead.

## Verification, and the one instrument that lied by omission

Failure-set diff against a d6d4cea0 baseline in the same tree shape: zero
genuine new failures. Two pre-existing `docs/currency.md` blocks moved three
lines (same blocks, verified by reading both); `test_F026` tripped its 3.0s
bound under load and passes alone at 2.67s, as it has all week; two
`docs/higher_order.md` call cases are FIXED by the branch.

**The blind spot, recorded because it nearly shipped unnoticed.** In both arms
of that comparison `tests/fmt/test_corpus.py::test_the_corpus_is_not_empty`
failed with `assert 0 > 100` — the fmt corpus discovered ZERO files in a
worktree, so all 1914 fmt and rewrite corpus cases were absent from both sides
and cancelled out of the diff. The guard fired honestly in both arms; reading a
name-set diff means the guard's own failure appears in NEITHER the NEW nor the
GONE column, which is exactly where a reader stops looking. Closed by running
the two corpora separately, baseline worktree vs landed clone: 1914 passed on
each side, identical failure sets, zero movement.

Barrier scan over the whole crossing range: 9195 added lines, 0 closed-side
terms, positive control firing. One violation WAS introduced during this
session — a todo I wrote named a closed-side path glob — and was caught by
re-scanning the range after committing rather than by scanning what I had just
typed.

## Sequencing with the other lanes

The export lane's `.seam` rename sweep was mid-flight. Two things came out of
coordinating with it:

- `/workspace/clausal-bug-fix` is not only the shared clone, it is what that
  lane's `test_strict_atoms_readiness` resolves through `CLAUSAL_STRICT_ROOT`.
  So "the clone moving does not affect you" was wrong, and the clone had
  already moved when they asked. A pinned baseline worktree at d6d4cea0 was
  made for them.
- That worktree was handed over unusable: a fresh git worktree has no compiled
  extensions, so importing clausal from it died on `_variables`. Found by
  accident, not by checking the artifact. Built and verified by observation
  (engine path, severity `"warn"`, C extension imports) before re-delivering.

`snake_to_pascal` now has no caller anywhere in the engine and survives only as
a re-export. Held out of this branch at the export lane's request so an
export-surface change does not ride in the same window as their rename; filed
as `todo/remove-dead-snake-to-pascal-export-2026-09-10.md`.

## Next

The operator's sequence continues with TitleCase as a LOGIC VARIABLE in Clausal
positions: widen `_is_logic_var_name` (`term_rewriting.py`, the units sugar and
quasi-quotation follow it), keep the head case an error, and retire the
translator's variable mangling to identity. Plan in
`todo/titlecase-variables-in-clausal-positions-2026-09-10.md`. This branch is
its prerequisite: the error had to be on and the tree green under it first.
