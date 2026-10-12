# The translator cannot load an improper list literal of ~185+ elements (2026-10-13)

```prolog
big(L) :- L = [1,2,3, ... ,199|foo].
```

Under the default translator, `clausal big.pl` fails to load: "MemoryError: Parser stack
overflowed - Python source too complex to parse". Since a7081c45, the translator emits an
improper list as nested `('.', H, ('.', H2, ...))` seam tuples, one nesting level per element.
Python's parser gives up at about 185-199 levels. Before a7081c45 it emitted `[1, ..., *foo]`,
which loaded but read the tail as an element (a wrong term).

The native front end loads 250 and fails at 500 (RecursionError in `iso_l3_directives._show`;
see the translator improper-tail todo, item 2).

Fix: a flat seam/compiler term form for "these elements, then this tail", e.g. a runtime builder
the compiler emits as one call over an element list. It needs a new compiler term form, so it
was kept out of the front-end fix.
