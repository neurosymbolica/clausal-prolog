# A head variable spelled like a Python keyword (`IN`, `IS`) crashes the load

Found 2026-09-25 while measuring the q() retirement premise (unrelated to it).

```clausal
p(IN) <- (IN is 1)
```

loads as `SyntaxError: invalid syntax (<string>, line 1)` -- no file, no line.
The traceback ends in `clausal/logic/predicate.py` `_make_init`, which
`exec`s a generated

```python
def __init__(self, in=_MISSING, ...):
```

i.e. the predicate's FIELD names are taken from the first head's variable
names, lowercased, and `in` / `is` are Python keywords. Same for
`p(X, IN)` and `p(IS)`; any ALL_CAPS variable whose lowercase is a keyword
(`IF`, `FOR`, `AND`, `NOT`, `CLASS`, `RETURN`, ...) should hit it.

Remedy candidates: mangle a keyword field name (`in_`) in `_make_init`, or
stop deriving field names from head variables at all (the keyword-argument
term spelling that needed them was retired 2026-09-19). At minimum the error
should name the clause.
