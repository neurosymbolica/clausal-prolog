# Star splices give different readings for one term; seam == on cyclic lists

**Status: FIXED 2026-10-22 (commits 7c6a4e54, 201c05f2).** I1, I2, M4, M5
and M6: a star bound to a non-list is the improper tail when only emptiness
follows it and `type_error(list, S)` otherwise, in the SegList walk and in
every builder (both twins), whenever the hole was bound; `SegList.__eq__`
decides the bisimulation on cyclic lists (`terms._rational_eq`). M1
(compare/sort on a 500-cell improper list) fixed by `_cons_chain_key`.
Pinned in tests/test_star_splice_readings.py (seam fixtures, walk, builders,
equality fuzz, deep improper lists). What remains of M1-M3 -- assertz of an
IMPROPER list of ~1500 cells, and ==/=/compare/copy_term/findall/ground/writeq
on two distinct CYCLIC lists -- moved to
todo/deep-and-cyclic-terms-overflow-the-recursive-walkers-2026-10-22.md.

Found in the Fable review of the front-end series (a3a62e67..018c18c8). A fix brief is ready; see the star-splice candidate.

**Prior ruling:** a hole bound to a non-list is the IMPROPER TAIL. It is never spliced as characters, and a star element must be a list.

- **I1, Important.** In `SegList._walk_raw`, an EMPTY hole after the improper tail counts as "something follows":
  - `[*A, *B]` with `A = [b|foo]` and `B = []` gives `"bfoo"`, but should give `[b|foo]`;
  - with `B = [x]` it gives `"bfoox"`, but should raise `type_error(list, [b|foo])`;
  - a cons or number tail raises a raw PartialTermError.
- **I2, Important.** `[*A, x]` with `A == foo` reads three ways:
  - `[foo, x]` when A is bound before the build;
  - `type_error(list, foo)` from a SegList;
  - `"foox"` when A is bound after the build.

  The number case behaves the same way. All three must give one reading.
- **M4, a regression in 018c18c8.** The seam `==` (`SegList.__eq__`, the `return w == other` arm) answers FALSE for two identical cyclic lists. Base raised, and Scryer answers yes. A wrong answer is never acceptable.
- **M5.** `[*X, x]` with X cyclic raises RecursionError while formatting the type_error message.
- **M6.** An atom star in a multi-star list is still spliced as text: `[*A, *B]` with `A = foo` and `B = [x]` gives `"foox"`.
- **M1–M3, pre-existing recursion limits:**
  - compare/3, sort/2 and msort/2 raise RecursionError on an improper list of about 500 cells (`_helpers.term_key`);
  - assertz overflows on a list of about 1500 cells (`globals_env._walk_body`);
  - the translator overflows on a 5000-cell `X = Y`;
  - two distinct cyclic lists `X = [a|X], Y = [a|Y]` raise RecursionError under `==`, `=`, compare, copy_term, findall, ground and writeq.
