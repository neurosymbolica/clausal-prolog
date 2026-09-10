# Testing

Clausal has two kinds of tests: Python-level pytest tests in `tests/`, and inline `test/1` clauses in `.clausal` files.

## Inline `test/1` clauses

Any `.clausal` file (see [Syntax](syntax.md)) can include test clauses of the form:

```clausal
--8<-- "tests/fixtures/docs/misc_phase7_sigs.txt:test_syntax"
```

A test passes if its body succeeds (produces at least one solution). Tests live alongside the predicates they exercise:

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
# Run all .clausal files under a directory
python -m clausal.testing clausal/examples/

# Run a single file
python -m clausal.testing clausal/examples/fibonacci.clausal

# Verbose output (shows individual PASS/FAIL)
python -m clausal.testing -v clausal/examples/
```

The exit code is 0 if all tests pass, 1 otherwise.

## Running `.clausal` tests via pytest

The `conftest.py` at the project root registers a pytest plugin that automatically collects `.clausal` files. The [import hook](import.md) handles loading and compilation. Each `test/1` clause appears as an individual pytest item:

```bash
python -m pytest clausal/examples/fibonacci.clausal -v
```

Output looks like:

```clausal
--8<-- "tests/fixtures/docs/misc_phase7_sigs.txt:test_output"
```

This means `.clausal` tests and Python tests can run together in one `pytest` invocation. Imported Prolog `.pl` files with `test/1` clauses can also be tested — the spelling is preserved across the translation (a Prolog `test/1` clause stays `test/1`, as every predicate name does), so nothing about the imported file is deprecated. See [Importing Prolog](importing_prolog.md).

## Running Python tests

```bash
python -m pytest tests/ -q
```

Note: `tests/test_continuation_search.py` requires `greenlet` and is skipped if not installed.

## Writing good `test/1` clauses

- Each test should be a single rule with a descriptive string as the argument.
- Test bodies can use any predicates defined in the module, plus [builtins](predicates.md) like `append`, `Member`, etc.
- Use `==` for [CLP(ℤ)](constraints.md) arithmetic equality on computed results: `test("check") <- (SomePred(X), X == expected)`. For ground integers this behaves like equality; for Vars it posts a CLP(ℤ) constraint.
- Use `structural_eq(X, Y)` for structural equality (Prolog `==/2`) when comparing non-integer terms.
- Use `==` for [arithmetic](arithmetic.md): `test("arith") <- (N == 2 + 3, N == 5)`.

---

*See also: [Examples](examples.md) — for real test predicates used in example programs.*
