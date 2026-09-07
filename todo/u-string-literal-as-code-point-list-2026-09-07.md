# `u"…"` as a compact code-point list — parked idea, 2026-09-07

**Observation (operator).** Clausal inherited Python's `b"…"` literal: `bytes`, denoting the code list `[97, 98]`, unifying element-wise with int lists (the codes model; kept through the strings program, spec §5.1). It is the reason `-double_quotes(codes)` is refused — codes already have a literal — and arguably the chars-vs-codes split in Prolog would never have happened with such a literal.

**Gap.** `bytes` covers codes 0..0xFF only. ISO codes are code points, so `atom_codes('é', C)` cannot answer `bytes`; today it answers a plain Python int list for anything outside Latin-1 — correct as a term, but without the compact representation and the C unification arms bytes enjoy.

**Idea.** A `u"…"` literal (and a matching runtime type) denoting the full code-point list: compact storage (`array('I')` or an int tuple), element-wise unification with int lists via the same arm shape as bytes↔list, `atom_codes/2`/`number_codes/2`/`char_code/2` answering it uniformly, `write_canonical` printing the `'.'/2` form, `is_codes/1` true. Fits the third representation slot the `SegString` protocol leaves open (spec §14.8: `str` = chars, `bytes` = 8-bit codes, `u` = code points).

**Surface.** On the Python surface CPython erases the `u` prefix (`u"x"` is `str`), but the quote map (`clausal/templating/quote_map.py`) already sees the token and strips `bBrRuU` — it can record the prefix and give the literal its own meaning. The future surface parser can define it freely.

**Status.** No use case yet ("it just seems right for completeness"). Park until one appears; do not implement speculatively.
