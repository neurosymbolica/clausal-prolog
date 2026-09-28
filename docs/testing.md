# Testing

Clausal has two kinds of tests: Python-level pytest tests in `tests/`, and inline `test/1` clauses in `.clausal` files (and in Prolog `.pl` files, through the [Prolog importer](importing_prolog.md)).

## Inline `test/1` clauses

Any `.clausal` file (see [Syntax](syntax.md)) can include test clauses of the form:

```clausal
--8<-- "tests/fixtures/docs/misc_phase7_sigs.txt:test_syntax"
```

A test passes if its body succeeds (produces at least one solution); a body that raises fails the test and reports the error. The head is `test/1`, lowercase like every predicate name: the old `Test/1` spelling is now a load-time error (TitleCase names have no role in Clausal), and the runner names the rename. Tests live alongside the predicates they exercise:

```clausal
fib(0, 0),
fib(1, 1),
fib(N, F) <- (
    N > 1,
    N1 == N - 1,
    N2 == N - 2,
    fib(N1, F1),
    fib(N2, F2),
    F == F1 + F2
)

test("fib(5) = 5") <- fib(5, 5)
test("fib(7) = 13") <- (fib(7, F), F == 13)
```

## Running `.clausal` tests standalone

Use `clausal.testing` as a command-line tool:

```bash
# Run all .clausal, .seam and .pl files under a directory
python -m clausal.testing clausal/examples/

# Run a single file
python -m clausal.testing clausal/examples/fibonacci.clausal

# Verbose output (shows individual PASS/FAIL and every skipped file)
python -m clausal.testing -v clausal/examples/
```

Exit codes:

| Code | Meaning |
|---|---|
| 0 | every collected test passed |
| 1 | a test failed, or a file failed to load (for a `.pl` file, to translate) |
| 2 | usage error: a path does not exist, or names a file that is not `.clausal`, `.seam` or `.pl` |
| 5 | no tests collected (the same number as pytest's "no tests collected") |

A file that fails to load is reported as one failing `<load>` item, with the load error and its source line.

**An empty run fails.** A directory with no test files, or whose files hold no `test/1` clauses, exits 5, as does a single file with no `test/1` clauses: a mistyped root or a renamed extension must not read as a green run. Pass `--allow-empty` when an empty directory is genuinely expected; the run then exits 0. `--strict` (alias `--fail-on-empty`) used to opt in to failing on an empty run; that is now the default, so the flag is accepted for compatibility and changes nothing (it cannot be combined with `--allow-empty`). An empty run used to exit 1 under `--strict`; it now exits 5 either way.

**Skipped files are reported.** A directory scan names the files it collected nothing from, with the reason: `unsupported suffix` (a `README.md`, a `.py` helper), `no test/1 clauses` (a module of helpers), `no-collect marker` (see below) or `ignored by conftest.py`. The last is a file a `conftest.py` at or below the scanned directory excludes through `collect_ignore` or `collect_ignore_glob`, so the CLI and the pytest plugin skip the same files. The CLI reads those two names only when they are assigned a literal list; it never runs the conftest. As in pytest, a file you name on the command line is run even if a conftest list covers it. Up to 5 are listed in full; a longer list is one count line, and `-v` lists every file. Files under hidden directories and `__pycache__` are not reported.

```text
1 file(s) skipped (unsupported suffix: 1):
  docs/README.md  (unsupported suffix)
no test files (.clausal, .seam or .pl) found
0 tests [NO TESTS] (exit 5; pass --allow-empty to accept an empty run)
```

### Prolog `.pl` test files

A `.pl` file is a test file too. It is loaded through the same experimental [Prolog importer](importing_prolog.md) a `-import_from` of a `.pl` file uses, and its `test/1` clauses are the tests:

```prolog
double(X, Y) :- Y is X * 2.

test('double of two is four') :- double(2, 4).
test('append works') :- append([1], [2], [1, 2]).
```

A `.pl` file the translator rejects (a syntax error, or a construct it cannot translate, such as a cut) is a failing `<load>` item carrying the translator error -- never a skipped file. The translator keeps no source map, so a failing `.pl` test is reported without a line number, and its goals are shown in their Clausal translation.

## Running `.clausal` tests via pytest

The `conftest.py` at the project root registers a pytest plugin that automatically collects `.clausal` files (and their `.seam` alias), Prolog `.pl` files (through the Prolog importer; a file that does not translate is one failing `<load>` item), and also every ```` ```clausal ```` block in `docs/*.md` that contains a `test/1` clause. The [import hook](import.md) handles loading and compilation. Each `test/1` clause appears as an individual pytest item:

```bash
python -m pytest clausal/examples/fibonacci.clausal -v
```

Output looks like:

```clausal
--8<-- "tests/fixtures/docs/misc_phase7_sigs.txt:test_output"
```

This means `.clausal` tests and Python tests can run together in one `pytest` invocation. A test-data file that is *meant* not to be collected (a fixture that fails to load on purpose, Prolog source that is data rather than tests) carries the line `# clausal: no-collect` within its first 30 lines -- `% clausal: no-collect` in a `.pl` file. Both runners honour it: the plugin does not collect the file, and `python -m clausal.testing` reports it as skipped. Prolog `.pl` files with `test/1` clauses are collected and run like `.clausal` files -- the spelling is preserved across the translation (a Prolog `test/1` clause stays `test/1`, as every predicate name does), so nothing about the imported file is deprecated. See [Importing Prolog](importing_prolog.md).

## Running Python tests

```bash
python -m pytest tests/ -q
```

Note: `tests/test_continuation_search.py` requires `greenlet` and is skipped if not installed.

## Writing good `test/1` clauses

- Each test should be a single rule with a descriptive string as the argument.
- Test bodies can use any predicates defined in the module, plus [builtins](predicates.md) like `append`, `in_`, `member`, etc.
- Use `==` for [CLP(ℤ)](constraints.md) arithmetic equality on computed results: `test("check") <- (some_pred(X), X == 13)`. For ground numbers this behaves like equality; for Vars it posts a constraint (see [Arithmetic](arithmetic.md) for what `/` means there).
- Use `X is TERM` to unify with a non-numeric expected answer: `test("colour") <- (colour_of(apple, C), C is red)`.
- Use `structural_eq(X, Y)` for structural equality (Prolog `==/2`) when comparing non-integer terms.
- Use `==` for [arithmetic](arithmetic.md): `test("arith") <- (N == 2 + 3, N == 5)`.

---

*See also: [Examples](examples.md) — for real test predicates used in example programs.*
