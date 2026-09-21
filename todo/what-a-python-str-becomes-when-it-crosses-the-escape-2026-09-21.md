# What does a Python `str` become when it crosses `++`?

**Status: OPEN, needs an operator ruling. Blocks the class-3 cleanup
downstream, and decides whether that is an audit of ~249 sites or a
one-line semantic change plus a much smaller one.**

Found 2026-09-21 while scoping the downstream fallout of the atoms-as-str
flip. Measured on main, not argued.

## The incoherence

Under `-double_quotes(chars)`, in one module, the same literal:

    a(X) <- (X is "text in source")        -> ('$chars', 'text in source')   a STRING
    b(X) <- (X is ++("text from python"))  -> 'text from python'             an ATOM

**The two sides of the escape disagree about what text is.** And it is not
only literals — anything Python hands across arrives the same way:

    r(X) <- (X is ++(os.sep))   -> '/'   is_atom TRUE, is_chars False

## Why it matters beyond tidiness

Post-flip an atom IS a `str`. So a value that crossed `++` is, by the engine's
own test, **indistinguishable from an atom the program declared**:

    is_atom('text from python')  -> True
    is_chars('text from python') -> False

A downstream reader asking `isinstance(v, str)` — or `is_atom(v)` — therefore
cannot learn whether it is holding a declared atom or text that came from
Python. That is not a downstream bug; the engine made them the same object.

This is the root of what the downstream lane classified as its hardest
category: a test that silently changed which question it answers, with no
score able to reveal it.

## The options

* **(a) It stays an ATOM (today).** Nothing to do in the engine. Cost: the
  conflation above is permanent, the two sides of the escape keep disagreeing,
  and every downstream `isinstance(v, str)` over an answer needs a human READ
  to recover the author's intent — an upper bound of ~249 sites across 62
  domains, and no instrument can narrow it, because the distinction does not
  exist in the data.
* **(b) It becomes a STRING (the `$chars` carrier).** The two sides of the
  escape agree, and the distinction is restored — a site that meant "string"
  gets one. This is the coherent reading of the flip's own rule ("an atom is a
  str, a string is the carrier"), applied to the boundary as well as to source.
  Cost: a breaking change with its own downstream migration, and every
  deliberate `++` -> atom crossing has to be respelled `++(mint(...))`.
* **(c) It is REFUSED at the boundary.** The author must say which they mean:
  `++(mint(x))` or `++(chars(x))`. Loudest, no silent conversion in either
  direction, and the only option that cannot produce a wrong answer. Costs the
  most at the call sites and would want a deprecation window.

## The second ruling, which (a) does not escape

**Which space is the harness boundary in?** A downstream body comparing an
engine answer to its own reference has to decide where the representation
stops. Some already say "IN TERM SPACE" in as many words; others compare
against plain-`str` references and meet a `('$chars', …)` key. That is the
second failure class the lane found — a string reaching `sorted`/`set`/dict-key
code as a 2-tuple.

The engine's part is to say what the canonical boundary conversion IS, and to
provide it, rather than leaving each body to write its own. Note that any
conversion to Python text is LOSSY under (a) — atom and string both become
`str` — which is an argument for (b) or (c) independent of the escape.

## Not to be confused with

The **1-tuple atom test** (a downstream helper that still tests the pre-flip
shape). That one is mechanical, measured, and being fixed; it is not a ruling
and it is not this.

## What I would want before ruling

The ~249 is a PROXY — enclosing functions that touch an answer — not dataflow,
and it over-counts. Under (b) or (c) a large part of it becomes mechanical
rather than a read. So the honest sequence is: rule the boundary first, then
re-count, rather than sizing the audit against today's semantics and then
changing them.
