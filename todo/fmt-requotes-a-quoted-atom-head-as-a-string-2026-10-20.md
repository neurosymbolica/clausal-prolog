# clausal-fmt rewrites a quoted-atom head as a string, changing the program

Filed 2026-10-20, found by the full-suite gate when clausal/stdlib/reif.seam
(the runtime `if_/3`) joined the files the formatter's comment-anchor test reads.

## What / Repro

In the seam, `'f'` is an atom and `"f"` is a string. The formatter does not
keep the distinction for a quoted clause head:

```python
from clausal.fmt import format_source
format_source("-private([f(_)])\n'f'(X) <- (X is 1)\n")
# '-private([f(_)])\n\n"f"(X) <- (\n    X is 1\n)\n'
```

On `clausal/stdlib/reif.seam`, `'if_'(IF, THEN, ELSE) <- (...)` becomes
`"if_"(IF, THEN, ELSE) <- (...)`; loading the formatted file breaks
library(reif) (48 reif tests fail).

`clausal.fmt.verify.ast_equivalent(src, out)` answers True for that pair,
because both quote styles are the same Python `Constant`; the formatter's own
safety check cannot see the change.

## Expected

The formatter keeps the source's quote style wherever the seam gives quotes a
meaning (atom vs string), at least for a clause head and for any position the
seam compiler reads as an atom, and `ast_equivalent` compares quote style
there (from token positions or the source span), so a meaning change is
refused rather than written.

## Status

Open. `tests/fmt/test_corpus.py::_KNOWN_ANCHOR_DRIFT` xfails reif.seam with a
pointer here; remove that entry when this is fixed.
