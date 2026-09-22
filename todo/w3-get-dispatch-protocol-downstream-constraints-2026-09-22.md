# W3 (`_get_dispatch`) — the downstream constraints, collected before it starts

Filed 2026-09-22 by engine-lane while closing W2. W3 of the PredicateMeta
retirement (`implementation_plans/p4-predicatemeta-retirement-scope-2026-09-21.md`)
is "the frozen external protocol": 185 in-tree read sites, 11 out-of-tree
implementors in 3 packages (provenance 1, scipy 9, spacy 1). This note is what
the other lanes said when asked, verbatim in substance, so W3 does not start
from a guess.

## The gate now exists: `tools/w3_package_gate.sh`

Own venv, packages re-installed editable from the room under test on every
run, engine from the room by cwd. Baseline at 34a6dc79: **105 failed / 1566
passed**, W2 tip identical (NEW 0 / GONE 0). The 105 are pre-existing and
three-fold: spacy fixtures fail without spacy installed (not skipped), scipy
units/dims tests, provenance fixtures. Someone should triage them, but not W3.

## Downstream census (asked 2026-09-22, all three lanes answered)

* **the downstream lane**: the downstream bodies, 0 `_get_dispatch` calls,
  0 retired-facade reads (both attribute syntax and `getattr` by string).
  **31 sites in 5 bodies hold a predicate CLASS as a value** — 14 call
  arguments, 10 in `(name, handle)` tables, 4 in lambda bodies, 3 in tuples in
  comprehensions; five downstream bodies (10/8/6/4/3). None reads state; they hold the class and later
  CALL it. That is W3/W4's cliff: whatever replaces the class must be
  callable in those positions. A census guard with a ratchet (absence of the
  retired names, COUNT of `_get_dispatch` and handle-as-value) was requested.
* **the corpus lane**: the downstream trees, 0 hits. One STRING-KEYED dependency:
  `a downstream gate module` classifies a module-shadow collision by matching the
  rendered AttributeError text `' has no attribute '_get_dispatch'` from
  `_dispatch_at`'s probe of a non-PredicateMeta object (17 archived
  occurrences). The discrimination rests on CPython's wording (apostrophe vs
  `object` before " has") — fragile TODAY, independent of W3. Contract agreed:
  W3 raises a NAMED exception whose class name appears in the rendered text
  (their gate matches captured stderr, it cannot catch a type); at the W3
  commit, send them the verbatim first line, and say whether the old
  AttributeError path is still reachable for any input. They hold the downstream gate module
  unchanged until then.
* **the export lane**: 0 facade reads, 0 `_get_dispatch` callers. The same
  the downstream gate module diagnostic (~983–1038) is text-coupled and fails OPEN. **One live
  classification site**: `a downstream classification site`
  `isinstance(obj, PredicateMeta) and getattr(obj, "_fields", None) != ()`
  decides declared-predicate vs atom — a behaviour change there is a wrong
  ANSWER, not a lost hint. `a downstream helper` reads
  `type(t).__match_args__`. `the downstream corpus tree` NOT grepped (held by
  the corpus lane for a batch) — ask when the hold lifts.

## What W3 must therefore preserve or announce

1. Predicate classes handed around as values and called later (31 sites).
2. `isinstance(x, PredicateMeta)` + `_fields` as the declared-vs-atom test
   (a downstream classification site) — or an announced replacement predicate.
3. A stable TOKEN in the rendered error when a dotted goal resolves to a
   module: the exception's class name. Send text before landing.
4. In-tree: `_dispatch_at` on any non-PredicateMeta object (the probe the
   gates key on); the 11 implementors' signature is frozen and duck-typed.

## Not yet done

* triage of the 105 baseline reds in the package suites;
* the W3 design itself (shim + deprecation window + which exception class).

## Addendum (the export lane, later the same day): a third coupling shape

`a downstream test` compares
`type(t).__name__ == "PredicateMeta"` — the class NAME as a STRING. Neither
an attribute sweep nor an `isinstance` sweep finds it, and it fails the
opposite way: a behaviour change leaves it silently passing, a RENAME breaks
it with nothing for a grep to find. One site, in tests, so it is not a count
change — it is a rule for the SWEEP: any wave that renames `PredicateMeta`
(W4, when the class goes) must also grep for the quoted string
`'PredicateMeta'` / `"PredicateMeta"` across every lane's trees, and that
query returns nothing today from the patterns used above. Their repo-wide
grep confirmed W2's zero; `an untracked snapshot` is an untracked snapshot
duplicating live hits, not additional sites.

## Addendum 2 — the corpus is swept; the census is COMPLETE

the export lane, after the hold on the downstream corpus tree lifted: W2
facades 0 files (positive control first), `_get_dispatch` 0 call sites,
`PredicateMeta` 1 file and it is a comment
(one downstream file, in a comment). Final
across downstream helper library, exporter, translators and corpus: 1 live classification site
(a downstream classification site), 1 text-coupled diagnostic (the downstream gate module), 0 callers, plus the
name-string test listed for the sweep. Nothing outstanding for the census.
