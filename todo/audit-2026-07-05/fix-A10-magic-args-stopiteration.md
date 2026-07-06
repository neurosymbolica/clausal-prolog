# fix(A10-F014): templating _detect_magic_args raises raw StopIteration for kwonly __args__

**Problem.** `clausal/templating/parser.py:85-88`: `all_args` includes
posonly/kwonly parameters, but the index lookup
`next(i for i, a in enumerate(arguments.args) …)` scans only `arguments.args`,
and the default is read from `arguments.defaults`. A template with
`def inner(*, __args__={FN})` passes the presence check, then `next()` raises
a bare `StopIteration` (kwonly defaults live in `kw_defaults`).

**Repro/test.** test_10_rewriting_import.py::test_F014_magic_args_kwonly_clean_error (xfail).

**Fix.** Either support kwonly placement (look up the default in
`kw_defaults[idx]`) or reject it explicitly:
`raise TemplateCompileError(f"{_MAGIC_ARGS} must be a positional parameter")`.
Same audit for posonly placement (`def inner(__args__={FN}, /)`).
