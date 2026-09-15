# Engine lane handoff — 2026-09-15 END

## State: NOTHING LANDED

    canonical main                        42160eb5   untouched
    clone main                            067de86d   untouched
    feat/clpq-c-port-2026-09-13           11 commits PARKED, clean
    feat/iso-l3-lowering-2026-09-14       37 commits ACTIVE, clean, head 6092e701

Four changes built and gated this session, all on the branch. Every gate is a failure-SET diff
against a same-tree baseline at `7ad86154`, not a count:

    baseline                     144 failed, 16287 passed
    §4 q1 shared-row plant       144 failed, 16299 passed    NEW 0  GONE 0
    ('()', 1, 2) tuple tag       144 failed, 16304 passed    NEW 0  GONE 0
    date compile route closed    144 failed, 16310 passed    NEW 0  GONE 0
    py.datetime speaks terms     144 failed, 16316 passed    NEW 0  GONE 0

The instrument is `tools/predmeta_census/` + `/home/node/.claude/jobs/*/tmp/failure_diff.py`
(six controls, each watched going red). **Rebuild it if the job dir is gone** — it strips ANSI,
refuses to compare unless BOTH runs reached their summary, and aborts if either extraction is
empty. All three guards earned their place this session.

---

# 1. What was ruled, and by whom

The operator ruled interactively through the session. These are settled; do not re-open:

* **Functor-first tuples are THE representation.** Atom 1-tuples discriminate atoms from strings
  in argument position. `PredicateMeta` goes — Prolog needs immutable compounds, only vars change.
* **`Compound` is not needed.** MEASURED: the tuple strictly dominates — `(F,1)` vs `('f',1)`
  binds F, while `Compound(G,(1,))` vs `Compound('f',(1,))` FAILS ("deref-only floor").
* **A module-level predicate name becomes the ATOM.** No predicate objects out into Python; the
  `--goal(...)` seam is already the calling convention and already speaks tuples.
* **Tuple-DATA tag is `('()', 1, 2)`** — a reserved quoted atom, third member of the family with
  `'[]'` and `'{}'`.
* **Dates/datetimes normalise**: `('date', Y, M, D)` etc. Python date classes are not needed any
  more; internally the engine may call back to Python, but the seam does not.
* **Rationals `('rdiv', N, D)`** (Scryer's spelling, not SICStus `r/2`); **decimals
  `('decimal', M, E)`** — mantissa and power-of-ten scale.
* **Cut-free forever is a property of `.clausal`, not the engine.** `.pl` may carry cut. Purity is
  a property of the IMPORT CLOSURE, not a file.

Design record (published page): https://claude.ai/code/artifact/deb7779b-2aa8-467c-8d92-3c72284ef111
Full spec: `docs/superpowers/specs/2026-09-14-retire-predicatemeta-section4-answer.md`

---

# 2. OPEN — needs the operator

1. **`1E+5` -> `('decimal', 1, -5)`**: allow the negative scale field (Decimal's own model) or
   normalise to `('decimal', 100000, 0)` and lose the `1E+5`/`100000` distinction? Recommended:
   allow.
2. **`Quantity`** was named in no ruling. Same shape of question as `Decimal`, plausibly
   `('quantity', <magnitude>, <unit>)`, but units are live corpus vocabulary. Do not assume.
3. **The oracle gate has NOT been run on any of this.** Engine-green is a different claim from
   corpus-answers-unchanged, and dates and money are live corpus vocabulary. Ask
   harness-batch-lane for the 28 sealed scorers before promoting anything here.
4. **Named-zone narrowing.** A tz-aware datetime now carries its UTC offset in minutes, so a
   `ZoneInfo` reduces to its offset AT THAT INSTANT and DST-crossing arithmetic would differ from
   Python's. Exact for fixed offsets (`timezone.utc`, `now_utc/1`). Revisit if the corpus needs
   DST-correct arithmetic.

---

# 3. NEXT — in order, each already scoped

1. **P1's 19 actionable reroute sites** (`tools/predmeta_census/P1_SITES.tsv`). NOW UNBLOCKED: §4
   q1 landed, so `db.row(functor, arity)` finally means "what does this name mean here". 4 of the
   19 TIGHTEN an arity-blind test (they compute an arity then look up by name alone) — a behaviour
   change needing an answer-set gate. 4 more are one idiom copied four times
   (`compiler/predicate.py` 900/1025/1734/1849): make a helper, not four edits.
   `globals_env.py:550` is marked NO — re-read it now that imports are planted, since its
   objection was that `db.row` could find a different same-named predicate.
2. **`rdiv`/`decimal` as NUMBERS.** The TERM half is free (measured: both already compile and
   marshal, zero engine change). The arithmetic half collides with `feat/clpq-c-port-2026-09-13`,
   which has `arith_q` — the rational arithmetic layer — already ported to C over GMP. **Sequence
   it WITH that port, not against it**, or one of the two gets rewritten twice and the
   differential oracle compares against a moved target.
3. **P2: terms become tuples in argument position.** The narrow, high-value half.

---

# 4. Lessons this session cost something to learn

**The dominant one, and it recurred three times: a property that was FREE under the old
representation has to be WRITTEN DOWN under the new one.**

* `_helpers._cell_functor` excluded tuple-data for free while the tag was a type object; with a
  `str` tag it had to say so, or every data tuple answers as the compound `'()'/N`.
* 13 more sites had the same shape — PAIRS where the COMPOUND branch runs first. I fixed the one
  I happened to read and did not sweep. 19 failures, one cause.
* tz-awareness: my term shape dropped `tzinfo`, and audit F016 — which pins that a naive/aware MIX
  must FAIL cleanly — went green BY ACCIDENT because every value had become naive. **A test that
  asserts a failure is the one that catches this; a test asserting success cannot.**

**A check whose second disjunct is trivially true verifies nothing.** My "does this module import
the name?" check was `name in src.split('def ')[0] or 'import' in src` — true of every Python
file. It reported OK for all five modules while `testing.py` was missing the import, and the
resulting `NameError` was SWALLOWED by the diagnostic path, so near-miss output silently lost the
goal name. Re-verified by asking each MODULE for the attribute.

**An extraction that collapses is worse than one that fails.** `^(FAILED|ERROR) (\S+)` truncated
`.clausal` fixture ids at their first SPACE and collapsed 145 distinct failures into 92 ids. Caught
only because the instrument compared its own count against pytest's summary.

**Second-order breakage is why the whole suite runs.** `test_tagged_terms.py` was never in any edit
list; its fixture does `D is date(2020,1,1)`, which started binding a TERM, while the test still
queried with a Python date. Nothing in the files I touched.

**zsh, three times.** `$var` is not word-split (`pytest $FILES` collected ZERO tests and reported
"2 warnings in 0.00s"); command substitution `$(...)` IS split, which is why the inline form
worked. Backticks inside `git commit -m "..."` are command substitution — a message lost two words.
Use an array, and `-F -` with a quoted heredoc.

See [[instruments-that-fail-open]] — running count is now 12.

---

# ADDENDUM — the oracle gate ran, went red, and the fix is ruled

Written after the handoff above; it supersedes that section's "oracle gate has NOT been run".

## The canary caught what my corpus sweep could not

    branch   eu/procurement/selection_criteria   score = (none), EXIT=1
             NotImplementedError: term_to_ast_expr: unsupported term type date
    canonical, same domain, same minute          341/341, EXIT=0

**My claim "the corpus cost is zero" for dates was wrong, and precisely how matters.** I swept
`/workspace/clausify-domains` (787 .clausal, 88 .seam, 263 .py), found nothing importing
`py.datetime` from code, and reported it as a fact about "the corpus". The SEALED SCORER BODIES are
not in that tree. They construct `datetime.date` and pass it into goals — exactly the path the
change closed. The number was right; the CLAIM generalised across a boundary I had not measured.

harness-batch-lane named it as a shape three lanes have now hit: **the population you measured,
named as the population that matters.** Recorded in [[instruments-that-fail-open]].

## Blast radius, measured and predictable

harness-batch-lane's predictor — "the body imports or constructs a `datetime`" — validated exact on
the observed data (10 predicted failures, 10 observed, 0 missed, 0 false alarms). Corpus-wide:
**23 of 74 domains**. A fix has a number to hit.

**Partial evidence on the other three changes, and it is real rather than absent.** The 8 domains
that scored are all at their recorded numbers, including the large-case ones (`life_cycle_costing`
17464, `espd` 2294, `shortlisting` 2217, `procedure_choice` 4716). So the tuple-tag, ordering and
import changes moved nothing ON THOSE EIGHT. They are untested on the 10 that could not run. Do not
report them as gated.

## The ruling: (b) + the better error

Both lanes initially argued for (a) — engine coerces a Python date at the boundary — on a cost
asymmetry. **Both cost arguments were withdrawn after measuring.** Mine said "82 sealed bodies";
theirs said the same; neither had measured the WORK. By AST across all 82:

    date() constructions   85   across 22 domains    (54 three-scalar, 31 starred triple)
    timedelta()            37   keyword-only
    clock or parse calls    0   ZERO, anywhere in the 82

**Not one date in any sealed body comes from a clock, a parse, or external arithmetic.** That zero
is what decided it: the only thing that would have made coercion NECESSARY is a date arriving with
no component form, and there is none. So (b) loses nothing, and it is the version where "the seam
shouldn't need dates" is literally true rather than "the seam tolerates dates".

## What is done, and what is left

DONE, gated 0-new: `f729d1b9` — the refusal names the fix.

    term_to_ast_expr: a Python date is not a term.
      Write the term instead:  ('date', 2023, 6, 1)
      in .clausal source:      date(2023, 6, 1)

A value with a canonical term encoding gets a suggestion; one without gets the plain refusal, and
that asymmetry is pinned by a test — it IS the distinction the ruling turns on. Shapes come from
`modules.py.datetime`'s own emit table so there is one definition.

LEFT, harness-batch-lane's, gated on the operator's DIRECT word for sealed files:
85 sites to the term form. 31 starred triples are `("date", *v)`; 54 scalar sites are
`("date", y, m, d)`. **The 37 `timedelta()` calls are keyword-only and the term is positional** —
`timedelta(days=1.5)` is `('timedelta', 1, 43200, 0)`, not `('timedelta', 1.5)`. Those want reading,
not a sed.

Then: the 28, then the full 82, with harness-batch-lane saying which of the four changes each
result does and does not cover.

---

# ADDENDUM 2 — the registry, the ++ attempt, and a correction that matters

## Final branch state

    feat/iso-l3-lowering-2026-09-14   head 4bf2fca1   clean
    gate                              144 failed / 16316 passed, NEW 0, GONE 0
    canonical / clone main            untouched. NOTHING LANDED.

## LANDED on the branch, each gated 0-new

    §4 q1 shared-row plant       arities_for / adopt_row / owns; adoption answers
                                 READS only, so a create=True caller never gets
                                 another database's row
    ('()', 1, 2) tuple tag       marshal-clean, ISO-writable, 2.08x recognition,
                                 1.74x as a dict key; completes the '[]' / '{}'
                                 family
    dates are terms              compile route closed; py.datetime produces and
                                 consumes terms via two choke points (its own
                                 deref/unify shadows), computing in Python between
    the error names the fix      "a Python date is not a term. Write the term
                                 instead: ('date', 2023, 6, 1)"
    the conversion REGISTRY      TO_TERM / FROM_TERM, exact-type keys, global, no
                                 overriding, NO generic converter; py.datetime
                                 consumes it rather than holding a second copy

## NOT landed, and why

**`++` auto-conversion: three insertion points, all red, REVERTED.** The obstacle
is a design question — `++` sits where both seam-built and user-returned tuples are
in flight and nothing in the value distinguishes them. Needs a marker on seam
constructions, or a conversion point where only user values appear. Full account in
the spec.

**`rdiv` / `decimal` as NUMBERS.** Term spellings are free and work today. The
arithmetic half belongs WITH the parked CLP(Q) C port, which has `arith_q` already
in C over GMP — writing against the Python one means rewriting twice.

## OPEN for the operator

1. `1E+5` -> `('decimal', 1, -5)`: allow the negative scale field (Decimal's own
   model) or normalise? Recommended: allow.
2. `Quantity` is unruled. Same shape as `Decimal`, but units are live corpus
   vocabulary — do not assume it follows.
3. The date migration on the HARNESS side: ruled (b) + the better error, then
   harness-batch-lane measured the real shape — 85 constructions vs 70 crossings
   in 62 wrappers, and a migration of the constructions produced a SILENT WRONG
   answer (`framework_agreements` 1413/1423). Their kit changes (capability probe,
   recogniser, pass-through) are correct and uncommitted. **The cost basis has
   moved three times; nothing should proceed there without a fresh ruling.**

## §4 q3 RESOLVED (and it reverses the ruling, cheaply)

Take **"absent"**, the spec's other branch, not the atom. A logic module is a plain
Python module, so a PEP 562 `__getattr__` fires on a MISS and resolves the name from
the Database row. Verified: attribute reach, `getattr` by literal AND by variable,
`hasattr`, and `from domain import pred` all keep working. **A miss-only hook serves
every REACH and cannot ENUMERATE** -- that is the entire distinction.

Enumeration count: engine **3** (all already dispositioned "enumerate the db's rows");
sealed bodies **ZERO** (harness-batch-lane, by AST, calibrated 6 positive / 5 negative
before running). Their 164 hits are all one launcher line enumerating the harness's own
PYTHON sibling -- 0 of 82 bodies declare a clause head, 82 of 82 export lists are empty.

**So q3 is one hook plus a `__dir__`, not ~655 site edits.**

CAVEAT, and it is why `__dir__` ships WITH the hook rather than after: the zero rests on
harness bodies declaring no predicates, which is how this batch was built, not a rule
anyone enforces. If one ever does, that re-export line becomes a real enumeration in all
82 launchers at once.

SEQUENCING: the hook cannot fire until names leave `module_dict` (P4). Add both together.

## THE CORRECTION THAT MATTERS MOST

**§4 q3 is not free.** I reported corpus object-shaped predicate access as ~0 and
"the engine's own 209 sites are the whole migration". Measured: corpus `.seam`
harnesses use `m.<predicate>(` ~200 times across 160 names, plus ~101
`getattr(m, <var>)`. **~446 sites in the 82 SEALED BODIES alone** (harness-batch-lane's own count: 296
module-attribute reaches across 245 names, 98 `getattr(m, <var>)`, 52
`getattr(m, 'literal')` -- a shape I did not count), plus the engine's 209.

Four times in one day I generalised a sweep past the file type it covered -- but the
CAUSE is structural, not carelessness, and harness-batch-lane named it: the sealed
bodies are excluded from every other lane's census BY THE SEAL, so "the corpus costs
nothing" is silent about the harnesses BY CONSTRUCTION.

**STANDING PROTOCOL FROM HERE: any sweep whose conclusion would cover the harnesses
goes to harness-batch-lane as a question.** They answer most in one AST pass. See
[[instruments-that-fail-open]] (count 15).

## NEXT, in order

1. **P1's 14 actionable sites** — `tools/predmeta_census/P1_SITES.tsv`, now anchored
   by SNIPPET because line numbers drift (19 of 50 had, while the checker validated
   the canonical tree nobody edits). 4 of the 14 TIGHTEN an arity-blind test.
   `globals_env.py:550` is marked NO — re-read it now imports are planted.
2. **The oracle gate is the instrument that matters**, not the engine suite. It
   caught what a green suite and a corpus sweep both missed. Ask harness-batch-lane.
3. `rdiv`/`decimal` arithmetic, sequenced with the CLP(Q) port.
