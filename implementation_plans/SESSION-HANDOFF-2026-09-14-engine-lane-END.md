# Engine lane handoff — 2026-09-14 END

## State: NOTHING LANDED

    canonical main                        42160eb5   untouched all session
    clone main                            067de86d   untouched all session
    feat/clpq-c-port-2026-09-13           11 commits  PARKED, clean
    feat/iso-l3-lowering-2026-09-14       10 commits  ACTIVE, clean

Both branches have clean working trees. Everything below is on a branch, by the operator's
"feature branch only, land nothing" instruction.

---

# 1. CLP(Q) C port — PARKED

Its own handoff is authoritative: `implementation_plans/SESSION-HANDOFF-2026-09-14-clpq-port.md`
on `feat/clpq-c-port-2026-09-13`. Summary only here.

**The operator's top priority was answered: the attributed-variable seam IS reproducible.**
Clausal's hook is SWI-shaped (fires AFTER binding, one per key, accept/reject, no `Later` list),
which looked fatal and is not — **Holzbaur's hooks never test X's binding state, only Y's**, and
Clausal's `bound_to` IS Y. `Later` maps to inline execution because hook re-entrancy works. One
deviation: `put_attr` raises on a bound var, so `put_atts(X, forward(Y))` is impossible — but
`forward` is Holzbaur's hand-rolled deref chain and `deref` provides it natively.

`arith_q` is ported to C over GMP and agrees with Holzbaur **20/20** on a live Scryer differential.
Stage-0 instruments all exist and are green. **`clausal/logic/clpq_c/BUILD.sh` is load-bearing** —
the `.so` is gitignored, so it is the only record of the build.

**To resume:** rebuild via BUILD.sh, confirm the three instruments green, then `store.pl` — and
the first decision there is already made and recorded: port `delete_factor_hom/4` from the
**SICStus** form (`compare/3`), not the Scryer workaround (`nf_ordering/3`), which dodges a Scryer
defect that has no cause in C and which the source comment says is slower.

---

# 2. ISO L3 front end — P1 DONE

`docs/superpowers/specs/…` n/a; the plan is
`implementation_plans/clausal-iso-to-transformed-ast-2026-09-14.md` (rev 4, operator's).

**P1's exit criterion is met, through the REAL loader.** `PrologLoader.source_to_code` is replaced
by L3 lowering (which plan §3.4 says is the end state), a `.pl` fact module is imported, and its
answers match a `.seam` twin: `[(1,10),(2,20)]` both sides. `clausal/tools/iso_l3.py`,
`tests/iso_l3/`, 4 tests green.

**§8.2's control caught me within minutes of writing it**: the first green run showed identical
answers while L3 had NEVER EXECUTED — a cached `.pyc` served the module. Every test now clears
`__pycache__` and asserts non-empty lowering stats.

## Two corrections to the plan, both measured

* **§3.5 puts `#=` in scope while the plan claims L0/L1/L2 need no change.** Bare `#=` is NOT a
  default operator — it yields a `SyntaxIssue`. It needs `:- op(700, xfx, #=)` in source, or the
  quoted form `'#='(C, A+B)`, which parses with nothing. The claim holds CONDITIONALLY and the
  plan should say which route. Note the convergence: the quoted form is also what the operator's
  `==` ruling chose.
* **§7 puts atoms in P1, but a bare atom needs a declaration, which is a DIRECTIVE, which is P3.**
  P1 was closed with integer-only facts. Atoms are genuinely blocked on P3.

## Decision taken (reversible), plan §6 decision 1

L3 emits positional `arg_0..arg_{n-1}`. Measured: the seam derives field names from the ARGUMENT
EXPRESSION — `positional(A, B)` gives `('a','b')` while `mylen([], 0)` gives `('arg_0','arg_1')` —
which has no stable ISO analogue. A mismatch is unreachable within a module (one file, one suffix,
one front end); across modules the class object travels via import.

**Plan §6 decisions 2, 3, 4 remain OPEN** — 2 and 3 gate the `.clausal` purity gate, 4 gates P2
arithmetic.

---

# 3. Retire PredicateMeta — P0 COMPLETE, P1 designed but NOT started

Spec: `docs/superpowers/specs/2026-09-14-retire-predicatemeta-design.md`.
Census + findings: `tools/predmeta_census/` (`census.py`, `FINDINGS.md`).

## Why this exists

The operator asked what a generic `Predicate` type would do once terms are functor-first tuples.
**Nothing.** `PredicateMeta`'s state is read-through onto a `PredRow`, which is itself "a THIN
READ-THROUGH FACADE over the Database's existing storage". `Database` already keys everything by
`(functor, arity)`. **The chain is name -> class -> row -> Database: two facades over a dict**, and
every compiler consumer walks it for ROUTING ONLY with `db` already in scope nearby.

    per class, deep          6.2-8.2 KB
    classes after importing
      a 3-predicate module   487      (~484 the engine's own) => ~3.4 MB fixed
    construct   class 809 ns/op   vs tuple  35 ns/op   23x
    unify       class 678 ns/op   vs tuple 145 ns/op   4.7x

**The per-class generation is a speed COST, not a feature** — the C `do_unify` has a native
functor-first-tuple path. Honest counterpoint recorded: a `__slots__` instance is 48 B against a
tuple's 64 B, so per-TERM memory slightly favours the class; swamped by the rest.

Sizing: **~1,450-1,650 lines deleted** (predicate.py loses ~1,288 of 1,772; PredRow ~286), **435
reference lines rewritten**, plus ~4,800 lines of generated class-guard that appears in no line
count.

## P0 is COMPLETE and machine-checked

431 references, 50 files, **0 still to read**. Positive-controlled: removing one verdict makes the
checker report 1, restoring reports 0.

**The taxonomy is SEVEN categories** (the spec assumed two, the first pass found five):

    A  PREDICATE TEST     26  "is this NAME a predicate here?"
    G  TERM TEST           8  isinstance(type(x), PredicateMeta) -- A DIFFERENT QUESTION
    C  CLASS-AS-ATOM       8  a bare predicate-class used as an atom VALUE
    D  DECLARATION         5  class stmt, registration, __all__, emitted AST
    H  FOREIGN IDENTITY    2  needs a genuinely new mechanism
    P  PROSE              34
    F/E/B                 49  annotations, imports, construction-by-name

**G is the one the spec missed and the one that would cause a silent bug.**
`isinstance(x, PredicateMeta)` = "is x a predicate CLASS"; `isinstance(type(x), PredicateMeta)` =
"is x a term INSTANCE". Same spelling, opposite meanings. Eight sites ask the second, in `solve.py`
(6), `head_match.py`, `term_expansion.py`, `predicate.py`. Treating them as A **changes what the
engine considers a callable goal.**

**H is the only category needing new design.** `predicate.py:1701-1703` compares against ANOTHER
copy of the engine's `PredicateMeta` to detect a double-loaded engine — class-object identity
ACROSS module copies, which a tuple cannot carry.

**No site blocks the removal.** Both candidates for blocking it are mechanical:
`specialization.py` needs only name + arity + row; `_variables.c` is **already polymorphic** over
term representations (`PredicateMeta` instance, then a `__dataclass_fields__` fallback).

## P1 — designed, NOT started, and my own first two conclusions were wrong

**The call, pinned by tests** (`tests/predmeta_p1/`):

    db.is_defined(f, a)        "any clause asserted"   STRICTER -- WRONG
    db.row(f, a) is not None   "a row exists"          EQUIVALENT -- USE THIS

A declared-but-empty predicate (`-dynamic`, no clauses) is `isinstance`=True, `is_defined`=FALSE,
row-exists=True. `compiler_v2.py:958` creates empty classes deliberately, so `is_defined` would
have **silently un-declared every dynamic-but-unasserted predicate**.

**The access path:** `module_dict["$module"].db`. NOT any predicate's `_row.db` — that yields a
different Database which reports `is_defined=False` for a predicate that has clauses.

**Reachability:** of the 26 A sites, 17 reach a dict, 6 have `db`, 8 neither. So a signature change
is not needed for 23.

**BUT "23 of 26 are mechanical" is TOO OPTIMISTIC — my own correction.** Reading two sites in full
shows four kinds:

    -> reroute to db.row(f, a) is not None       the straightforward ones
    -> SIMPLIFY: stop passing a redundant class  compiler_v2.py:233 -> _load_gate ALREADY
                                                 receives db, functor AND arity
    -> needs a FUNCTOR-ONLY query                compiler_v2.py:1717 asks "a predicate at ANY
                                                 arity?" from a declaration list; row() cannot
    -> BLOCKED on spec §4                        that same site really asks whether a module-level
                                                 NAME binds a predicate

**Recommendation: add `Database.has_any_arity(functor)`.** This reverses my own "do not add a
functor-only query", which I concluded from the reachability figure before reading any site in
full.

## NEXT STEP, and do not skip it

**A per-site pass reading each of the 26 A sites in its enclosing function, before any edit.** The
same discipline corrected 4 of 83 P0 verdicts. **The sites look alike at line level and are not
alike** — that is the single most important sentence in this section.

---

# 4. Relayed operator ruling on `==/2` — AWAITING THE OPERATOR

`todo/seam-operator-disambiguation-ruling-2026-09-14.md` on the CLP(Q) branch.

Relayed via iso-export-lane: the seam language is to be changed so the operators `==/2` overloads
are **disambiguated at the CALL SITE**, via quoted string functors (`'#='(L,R)`). Both reasons for
the overloading have expired — Python has no user-defined operators, and fitting Python operator
semantics matters less because **Clausal will be written by LLMs**.

**Verified here, 5 probes:** `'#='` binds forward AND backward; bare `==` does atom identity AND
arithmetic, both directions. `iso_compare.py:403` shows `'#='(X, foo)` reporting context
`'(==)/2'` — the quoted form ROUTES THROUGH `==` today, so the change is not purely additive.

**THE GAP, and iso-export-lane agreed it is real:** the ruling says how to disambiguate but not
**what bare infix `==` BECOMES** — identity-only, removed, or both-with-optional-migration. Under
the first the 928 sites are a mandatory migration; under the third they are not a migration at all.
iso-export-lane is putting the three dispositions to the operator directly.

**The hard core, already measured in-tree at `iso_compare.py:381-387`:** 1933 corpus call sites,
430,945 executions, **33 sites take TWO arithmetic modes — the same site BINDS on one call and
TESTS on another.** For those, `'=:='` raises instantiation_error on the binding call and `'is'`
is wrong for the testing one: **`#=` is the only spelling valid in every mode.** So those 33 are a
FLOOR on any migration, not a judgement call. This also explains why iso-export-lane's static
classifier failed: `==`'s meaning is a property of runtime instantiation.

**Two scale figures disagree by >2x** — 1933 (runtime, in-file) vs 928 (static, 58 domains). Not
reconciled. **Do not quote either as settled**; the 33 is the figure to lean on.

Adjacent, scope UNKNOWN: `=<` `<` `>` `>=` carry the same overloading (53+ sites, 28 domains). The
operator named `==` specifically, and the ambiguities are NOT symmetric — `==` is
identity-vs-arithmetic, the comparisons are polymorphic-over-types vs arithmetic-only.

---

# 5. Open, needing the operator

1. **What bare infix `==` becomes** (§4 above). Blocks a 928-site migration either way.
2. **Whether `=<`/`<`/`>`/`>=` are in scope** of the same change.
3. **Plan §6 decisions 2, 3, 4** — cut-in-disguise list, replacement idioms, arithmetic spelling.
4. **Spec §4 of the PredicateMeta retirement: what binds at module level?** `-import_from`, export
   lists, bare `m.some_pred`. One P1 site is already blocked on it.
5. **Declared atoms** — a zero-arity class is a declared atom by design (`predicate.py:1617`
   documents the union deliberately). They need a tuple spelling and a migration before the class
   can go.

# 6. Things that will cost the next person time

**Worktrees have no built C extensions, and a worktree's `clausal/` SHADOWS the built tree** if it
reaches `sys.path` first. Symptom: `ModuleNotFoundError: clausal.logic.variables._variables` deep
in a fixture. Both test suites here carry a guard that prefers a built tree and SKIPS loudly.

**Run engine tests from `/workspace/clausal`**, and for tests that live on a branch use
`--import-mode=importlib --noconftest`.

**`arith_eval` takes `/`, not `rdiv`.** `eval_q` has no `rdiv` clause; a first oracle run returned
`fail` for almost everything because of this.

**Citations must quote the source line EXACTLY** — the CLP(Q) traceability checker rejects
paraphrase and elision.

**Backticks inside a double-quoted `git commit -m` are COMMAND SUBSTITUTION in zsh.** One commit
message here silently lost a phrase because zsh tried to execute it. Use `-F -` with a quoted
heredoc for any message containing backticks.

**zsh does not word-split an unquoted `$var`.** Bit me again this session in a `for` loop over a
space-separated site list; use an array.

# 7. Method lessons, in order of what they cost

**The dominant one, and it recurred four times: an instrument that reports success while measuring
nothing.**
* a cached `.pyc` made an L3 differential report "identical" while L3 had never run — caught only
  because the test asserted the front end had executed
* ANSI codes made `grep '^FAILED '` extract ZERO names from 147 failures
* a failure-set diff ran against an UNFINISHED run and reported 147 phantom differences
* `roborev … | tail -60` at capture time DESTROYED findings 1-5 of a review; they had to be
  refetched

**Every extraction must print the SIZE of what it extracted, next to the result.** That single
habit caught three of the four.

**A number and its prose must not drift.** The census said 268 unread while the findings said 195,
because manual verdicts were never fed back. The prose was ahead of the instrument, which is the
wrong way round. The tool now tracks verified files.

**Line-level verdicts are hypotheses.** Reading the enclosing function changed 4 of 83 P0 verdicts
(~5%). Twice in this session a conclusion drawn from a line or a count was reversed by reading the
function or the site in full — including two of my own P1 design conclusions.

**Counting the same thing three ways gave three answers.** `head -10` said 10 registrations and
silently dropped `clpr.py`; `grep -c` said 17 by counting definition lines; the truth was 11. Both
wrong answers looked plausible.

**A positive control that has never been OBSERVED failing is not a control.** Every checker here
was broken deliberately and watched go red before being trusted.
