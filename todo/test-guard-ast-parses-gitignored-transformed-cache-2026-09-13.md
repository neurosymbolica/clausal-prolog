# A test guard `ast.parse`s the gitignored `__transformed__` cache and fails

**Filed 2026-09-13 by engine-lane.** Found while verifying a landing on canonical, NOT by looking
for it. Pre-existing; nothing to do with the landing that surfaced it.

## What happens

`tests/test_atoms_as_cells_flip.py::test_the_zero_field_class_test_is_named_is_zero_field_class`
fails on canonical with a SyntaxError that names no file:

    File "<unknown>", line 18
      $define_predicate(
      ^
    SyntaxError: invalid syntax

`_class_test_offenders` (tests/test_atoms_as_cells_flip.py:1244) walks `root.rglob("*.py")` and
`ast.parse`s every hit. Two of those hits are not Python:

    tests/clausal_modules/__transformed__/family.py
    tests/fixtures/__transformed__/edge_graph.py

They are Clausal **dump_source output** carrying a `.py` extension — `$define_predicate(`,
`$module`, `position=(16, 19, 20, 1)`. `__transformed__/` is a generated cache and is **gitignored
at .gitignore:7**.

## Why it is worth a todo rather than a shrug

**The failure depends on whether a gitignored cache happens to be POPULATED**, so it appears and
disappears per tree with no commit explaining either. Measured:

    canonical            2 __transformed__ dirs present   -> guard FAILS
    clone (bug-fix)      0 __transformed__ dirs at all    -> guard PASSES

**The engine lane runs its suite in the CLONE. So this defect is structurally invisible to the
instrument the lane actually uses**, and it showed up only because a landing was verified in the
canonical tree as well. That is the general hazard: a guard whose result depends on build residue
reports on the residue, not on the code.

## The fix

Skip the generated cache in the walk — it is already named in `.gitignore`, so the
exclusion exists, it just is not honoured here:

    for path in sorted(root.rglob("*.py")):
        if "__transformed__" in path.parts:
            continue

Prefer that over a try/except around `ast.parse`: **swallowing a SyntaxError would also swallow a
genuinely unparseable test file**, which is a thing this guard should still fail on. Skip what is
known not to be Python; keep failing on everything else.

## NOT APPLIED, deliberately, and this is the reason

Two peer lanes are mid-measurement against the engine suite right now — iso-export-lane has just
taken an export baseline and the harness lane is running a full 82-domain sweep. **Changing the
engine-suite failure SET while they are measuring against it is a second variable moving inside a
measurement of the first** — exactly the trap iso-export-lane avoided today by disabling their own
change for their arm. Apply this when no one is measuring, and announce the failure-set delta (-1
on canonical, 0 on the clone) when it lands.

## Related, found in the same diff and also pre-existing

`tests/test_transitive_py_module_import.py` fails 2 on canonical for an unrelated reason: the test
writes a fixture containing `Test("direct date_time import")`, and the TitleCase lint (which RAISES
since 2026-09-10) now rejects it at load. On the clone both tests SKIP -- "no project venv
interpreter with an installed clausal distribution found" -- so this is invisible there too, by the
same mechanism. Belongs with `todo/packages-fixtures-still-titlecase-2026-09-10.md` and the
`Test/1` retirement.
