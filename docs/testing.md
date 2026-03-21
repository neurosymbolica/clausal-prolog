# Testing

Clausal has two kinds of tests: Python-level pytest tests in `tests/`, and inline `test/1` clauses in `.clausal` files.

## Inline `test/1` clauses

Any `.clausal` file can include test clauses of the form:

```clausal
test("description") <- goal1, goal2, ...
```

A test passes if its body succeeds (produces at least one solution). Tests live alongside the predicates they exercise:

```clausal
fib(0, 0),
fib(1, 1),
fib(N, F) <- (
    N > 1,
    N1 := N - 1,
    N2 := N - 2,
    fib(N1, F1),
    fib(N2, F2),
    F := F1 + F2
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

The `conftest.py` at the project root registers a pytest plugin that automatically collects `.clausal` files. Each `test/1` clause appears as an individual pytest item:

```bash
python -m pytest clausal/examples/fibonacci.clausal -v
```

Output looks like:

```clausal
clausal/examples/fibonacci.clausal::fib(0) = 0 PASSED
clausal/examples/fibonacci.clausal::fib(5) = 5 PASSED
```

This means `.clausal` tests and Python tests can run together in one `pytest` invocation.

## Running Python tests

```bash
python -m pytest tests/ -q
```

Note: `tests/test_continuation_search.py` requires `greenlet` and is skipped if not installed.

## Writing good `test/1` clauses

- Each test should be a single rule with a descriptive string as the argument.
- Test bodies can use any predicates defined in the module, plus builtins like `append`, `member`, etc.
- Use `==` for CLP(FD) arithmetic equality on computed results: `test("check") <- (some_pred(X), X == expected)`. For ground integers this behaves like equality; for Vars it posts a CLP(FD) constraint.
- Use `equivalent(X, Y)` for structural equality (the old `==` behavior) when comparing non-integer terms.
- Use `:=` for arithmetic: `test("arith") <- (N := 2 + 3, N == 5)`.

---

*See also: [Examples](examples.md) — for real test predicates used in example programs.*
