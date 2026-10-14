# Star splices give different readings for one term; seam == on cyclic lists

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
