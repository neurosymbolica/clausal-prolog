# clausal-acl2

[ACL2](https://www.cs.utexas.edu/~moore/acl2/) theorem prover predicates for [Clausal Prolog](https://github.com/neurosymbolica/clausal-prolog).

Talks to a real ACL2 through its ACL2 Bridge (`books/centaur/bridge`). Lisp
forms and results cross as Clausal terms -- Clausal's functor-first terms are
Lisp forms -- so an ACL2 term is a Prolog compound:

- `acl2/2,3`, `acl2_mv/2` — evaluate a form; its value(s) and output
- `event/1,2` — submit an event (`defun`, `defthm`, ...)
- `thm/1,2` — prove a term
- `acl2_text/2` — a term and its ACL2 text, either way
- `use_acl2/1` — a running bridge, or the ACL2 to start

## Install

```
pip install clausal-acl2
```

No Python dependencies. ACL2 is an external program: `acl2` on PATH (with its
books, including a certified `centaur/bridge`), or a running bridge named with
`use_acl2/1`. Requires Python 3.13 or later.

## Use

Import the predicates into a seam (`.seam`) module. A Clausal Prolog
(`.clausal`) module reaches Python only through the seam: put the imports in a
`.seam` module and list it under `[tool.clausal] python_bridges` in your
project's `pyproject.toml` (see
[Importing Prolog](https://github.com/neurosymbolica/clausal-prolog/blob/main/docs/importing_prolog.md)).

This test, from [`tests/fixtures/docs/acl2_examples.seam`](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-acl2/tests/fixtures/docs/acl2_examples.seam):

```seam
-import_from(py.acl2, [acl2_text, event, thm])
-private([equal(_, _), app(_, _)])

test("define a function, then prove a theorem about it") <- (
    acl2_text(DEFUN, "(defun app (x y) (if (endp x) y (cons (car x) (app (cdr x) y))))"),
    event(DEFUN),
    thm(equal(app(app('x', 'y'), 'z'), app('x', app('y', 'z'))))
)
```

## Documentation

- [acl2 — the ACL2 theorem prover from Clausal](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-acl2/docs/acl2.md)

## License

MIT
