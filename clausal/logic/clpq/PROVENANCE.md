# Provenance of the CLP(Q) port

## Source

The port translates clp(q,r) version 1.3.3:

> (c) Copyright 1992,1993,1994,1995 Austrian Research Institute for
> Artificial Intelligence (OFAI), Schottengasse 3, A-1010 Vienna, Austria.
> Author: Christian Holzbaur.

The files are the `.pl` files of the SICStus Prolog 4.10.1 distribution,
`library/clpq/*.pl`, all dated 2018-11-08:

`arith.pl`, `arith_q.pl`, `bb.pl`, `bv.pl`, `class.pl`, `compenv.pl`,
`dump.pl`, `fourmotz.pl`, `geler.pl`, `ineq.pl`, `itf3.pl`, `nf.pl`,
`nfq.pl`, `ordering.pl`, `project.pl`, `redund.pl`, `store.pl`.

Notes on those files:

- `class.pl`, `fourmotz.pl`, `ineq.pl` and `redund.pl` carry a
  "version 1.3.2" banner; the rest say 1.3.3.  They ship together as one
  release and are treated as 1.3.3.
- `compenv.pl` is marked obsolete by SICStus (`%% [PM] 4.1.3 obsolete code`,
  then `end_of_file.`) and carries a Swedish Institute of Computer Science
  copyright, not OFAI's.  It is not ported (DEVIATIONS.md, D2).

Every ported module starts with the header given in the plan's global
constraints, naming the 1.3.3 file it comes from.

## The operator's decision (2026-10-12)

The operator decided to port 1.3.3 directly and faithfully. The reasons:

- **The copyright holder cannot be reached.**  Christian Holzbaur
  could not be reached after repeated attempts, so no licence could be
  asked for.
- **The operator accepts the licence risk** of publishing a translation of
  the 1.3.3 source.
- **A clean-room rewrite was rejected** for its correctness risk.  The
  solver's invariants (bound types, active bounds, strictness, the
  back-substitution order) are subtle.  A rewrite from a description would
  lose behaviour that a line-by-line translation keeps and that its tests
  can check.

## What is not used

- **SWI-Prolog's `clpqr`** (a rework of the same code) is not used in any
  form: not read, not run, not compared against.
- **Claude-written notes are excluded.**  They may be wrong and are not a
  source for the port:
  - `library/clpq/clpq-algorithm.md` and the `library/clpq/.claude/`
    directory in the SICStus tree;
  - the `.md` notes in `/workspace/claude_sicstus_clpq/` (`ANALYSIS.md`,
    `possible_improvements_from_python_clpq.md`,
    `scryer_3295_findings.md`).

  A claim taken from them counts only once checked against the `.pl` source
  or a test.

## Supporting material that is used

- **The runnable oracle**: `/workspace/scryer-prolog-clpq/src/lib/clpq.pl`,
  a mechanical translation of 1.3.3 into one Scryer Prolog module.  It is
  run to get expected answers; its code is not the port's source.
- **The examples**: `/workspace/claude_sicstus_clpq/test_examples_clpq.pl`
  inlines the 1.3.3 example programs.  It is outside `library/clpq`, so
  the licence acceptance for the 1.3.3 sources does not cover it, and it
  is never copied into this repository.  `tests/clpq_port/test_examples.py`
  reads it from that path, and skips where it is absent.  It runs the
  file's cut-free example predicates (mg and the Monash mortgage, simplex
  1 to 9, eliminat, laplace, fib, SEND+MORE=MONEY, option) under the port
  and on the oracle, and checks the values the file documents.  The file's
  own driver (`->`) and its cut-using examples cannot load in cut-free
  Clausal and are not run; the rest of its examples are not run either
  (the test's docstring lists them).
- **The reading copy**: `tools/clpq_reference/rename.py` with
  `tools/clpq_reference/rename_map.tsv` rewrites the 1.3.3 files (and the
  Scryer copy) with the full-word names of `NAMES.md`.  The output lives
  outside the repository, in `/workspace/clpq-reference/`, and is never
  committed.
