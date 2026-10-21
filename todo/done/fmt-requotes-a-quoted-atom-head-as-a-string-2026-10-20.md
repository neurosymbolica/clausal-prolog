# clausal-fmt rewrites a quoted atom as a string, changing the program

**Status: FIXED 2026-10-20 (commit 2ec866c7).** The emitter writes every string literal back as the source spelled it (a spelling ledger captured next to the arrow ledger, `CommentTable.literals`), and `ast_equivalent` compares the quote character of every string literal from the source, so a requoting result is refused. Pinned in `tests/fmt/test_emit.py::test_a_quoted_atom_head_functor_stays_an_atom`, `tests/fmt/test_emit.py::test_a_quoted_atom_body_goal_stays_an_atom`, `tests/fmt/test_verify.py::test_a_requoting_formatter_is_refused` and, for every `.seam` in the repository, `tests/fmt/test_corpus.py::test_fmt_keeps_the_compiled_module`.

Filed 2026-10-20, found by the full-suite gate when clausal/stdlib/reif.seam
(the runtime `if_/3`) joined the files the formatter's comment-anchor test reads.

## What / Repro

In the seam, `'f'` is an atom and `"f"` is a string. The formatter does not
keep the distinction for a quoted functor, in a clause head or in a body goal:

```python
from clausal.fmt import format_source
format_source("-private([f(_)])\n'f'(X) <- (X is 1)\n")
# '-private([f(_)])\n\n"f"(X) <- (\n    X is 1\n)\n'
```

The same for a quoted body goal (2026-10-20, on 6f44ffc2 and 02f451f1):

```python
format_source("-private([p(_), a])\np(X) <- ('=='(X, a))\n")
# '... p(X) <- (\n    "=="(X, a)\n)\n'
format_source("-private([p(_)])\np(L) <- ('=..'(L, [f, 1]))\n")
# '... p(L) <- (\n    "=.."(L, [f, 1])\n)\n'
```

On `clausal/stdlib/reif.seam`, `'if_'(IF, THEN, ELSE) <- (...)` becomes
`"if_"(IF, THEN, ELSE) <- (...)`; loading the formatted file breaks
library(reif) (48 reif tests fail).

`clausal.fmt.verify.ast_equivalent(src, out)` answers True for that pair,
because both quote styles are the same Python `Constant`; the formatter's own
safety check cannot see the change.

## Exposure

Quoted-atom calls are how the seam spells operator-named predicates
(`'=='`, `'=..'`, `'if_'`), so the defect reaches real code: a count on
2026-10-20 found 16 such calls in a downstream kit's `.seam` libraries and 97
in a downstream rulebase collection (mostly tests). Any tool that formats
those files in place would silently change what they mean. One downstream
pipeline phase does run the formatter in place over a run's `.seam` domain
tree; it is dormant while new runs write `.clausal`.

## Expected

The formatter keeps the source's quote style wherever the seam gives quotes a
meaning (atom vs string): every quoted functor, head or body, and any other
position the seam compiler reads as an atom, and `ast_equivalent` compares quote style
there (from token positions or the source span), so a meaning change is
refused rather than written.

## Status

Fixed; see the status line at the top. The reif.seam entry in
`tests/fmt/test_corpus.py::_KNOWN_ANCHOR_DRIFT` is gone and that case passes.
