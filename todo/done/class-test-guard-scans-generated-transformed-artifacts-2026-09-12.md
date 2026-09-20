# `test_the_zero_field_class_test_is_named_is_zero_field_class` breaks on generated artifacts

Found 2026-09-12 while measuring the ratio-units promotion on canonical.

The guard walks the AST of **every `*.py` under `clausal/` and `tests/`** to catch the retired
`predicate.is_atom` spelling. It therefore also parses `tests/**/__transformed__/*.py` — the
dumped Python that the transformer writes for debugging — and those are not valid Python:

    tests/fixtures/__transformed__/edge_graph.py:18        invalid syntax
    tests/clausal_modules/__transformed__/family.py:18     invalid syntax

Both are UNTRACKED generated output. So the test's result depends on whether someone has run
something that dumps a transform, which is working-tree state rather than source.

**Measured, not inferred:** the test passes on `cc008788` source in a clean worktree and fails
on `cc008788` in the canonical working tree. Same commit, same `.so`, different on-disk
leftovers.

**Why it matters beyond the one test.** It reports as a SyntaxError with no file attribution in
the pytest summary (`File "<unknown>", line 18`), which is exactly the shape the sync notes warn
about: a parse failure blamed on nothing, in a tree several lanes write to. Anyone diffing a
failure set across two trees will see it appear and disappear for reasons unrelated to their
change.

**Fix**: skip `__transformed__` directories in `_class_test_offenders` (and any other
generated-output directory), or restrict the walk to tracked files. Skipping unparseable files
silently would be the wrong fix — the guard would then go quiet on a real offender it cannot
parse, which is the fail-open shape this repo keeps hitting.

Do NOT "fix" it by deleting the artifacts: they belong to whoever generated them, and the test
would break again the next time anyone dumps a transform.

## CLOSED 2026-09-19 (6090d1d6)

`_class_test_offenders` skips any path with `__transformed__` in its parts.
The guard's own positive control (`test_the_class_test_pin_actually_bites`,
which feeds it a live offender in each of the three spellings) still bites, so
the skip narrowed the walk without blunting it.

Gated in a REPRODUCED room rather than in the canonical working tree: a
worktree plus all twelve `.so`, a `venv` symlink (the sibling test's skipif
uses `abspath`, not `realpath`, so a symlink satisfies it) and a copy of the
two untracked dumps. Baseline arm reproduced all three checkout-only failures
with zero skips — that control is what makes the diff mean anything — then
NEW 0 / GONE 1, this test being the one that went.

**Found twice.** This note is dated 2026-09-12; I rediscovered the same defect
on 2026-09-19 from the failure text, fixed it, and only then read the todo
list. The note had already measured what I re-measured, including the
`File "<unknown>", line 18` no-attribution shape. Read `todo/` before chasing
a suite failure that smells environmental.
