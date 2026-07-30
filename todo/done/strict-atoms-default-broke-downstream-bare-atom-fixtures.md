STATUS: DONE (2026-07-30). Swept, counted, decided: **small count, fix each
site; no new migration note**. Ground truth was load-testing every tracked
`.clausal` file through `clausal.import_hook._load_module` and keeping only the
failures whose message is `strict_atoms: undeclared atom(s) ...`, not a regex
guess. **7 of 1115 tracked files fail**, 0.6%:

| consumer | tracked `.clausal` | strict-atoms load failures |
|---|---|---|
| `clausify-executor-train` | 44 | **5** (all under `kit/`) |
| `clausify-domains` | 713 | **2** |
| `clausify/kit` | 31 | 0 |
| `clausal packages/` | 103 | 0 |
| `clausal tests/` | 224 | 0 (confirmed, not assumed) |

Plus 3 fixture groups embedded in Python string literals in
`clausify-executor-train/auto/tests/`, breaking 6 tests.

The count settles the todo's open question the other way from how it was framed.
The premise was that "the default landed without a sweep of out-of-tree
consumers"; in fact the in-repo corpus *was* swept during the original migration
(`4e1892a0` armed every in-repo `.clausal` with `-implicit_atoms`, `bec94e2d`
finalized it), so the only exposure was ever out-of-tree — and out of tree it is
0.6%, not the broad breakage a deprecation window would be for. A migration note
also already existed in substance: `docs/strict-atoms-migration.md` (`297e506f`),
covering both migration paths, the shipped codemod, and clausify-domains. Writing
a second one would have duplicated it. It was **extended**, not replaced, with the
one thing this sweep learned that it did not already say (below).

Fixed: `clausify-executor-train` branch `fix/strict-atoms-fixtures`, commit
`5b886ea` — 8 fixtures. Suite 9 failed/982 passed -> 3 failed/988 passed, no new
failures; the 3 remaining are unrelated (manifest `independence` validation, and
a G6 gate postdating its expected set). The three `query_requirements` fixtures
this todo names were **already fixed** in that repo by `0fb1171` before this
sweep began, so the recorded "3 failed, 7 passed" was stale by the time it was
acted on — the same staleness this todo complains about, one iteration later.

Deliberately left alone: the **2 `clausify-domains` files**
(`au/firb/eval/scoring/harness.clausal`, undeclared FIRB profile keys; and
`eu/data_protection/gdpr_chapter_v_transfers/tests/test_planning.clausal`, an
`adequacy_decision_in_force` dict key). That repo was in scope for the sweep but
not for edits, and neither file is breaking a suite that was being run here.
Also left alone: 69 further failures under `clausify-executor-train/_reruns/`,
which is **gitignored** scratch output from past training runs — frozen
artifacts, not source, which is why the tables above count tracked files only.

Method note for whoever repeats this. Load-testing is only honest if the file
actually reaches the atom check, and most of them did not on the first pass:
`-import_from` resolves against `sys.path`, so with the wrong search path 442/528
train files and 612/767 domain files died on `ModuleNotFoundError` *before*
compiling a single clause — a sweep that would have reported a clean 0 for the
wrong reason. Fixed by putting each file's own directory and the sibling library
roots on the path, then re-running the leftovers with unresolvable imports
stubbed out (a `sys.meta_path` finder minting any requested name) so the
remainder could not hide a strict failure behind an import failure. The
`packages/` residual is genuine and unresolvable here: those files need jax,
torch, opencv, sympy, sklearn and scipy, none installed — they were cleared under
stubbed imports instead.

Also worth recording, because it cost time in the fixing and is now in the
migration guide: **`-private` is the wrong fix whenever two files must agree on
an atom.** Auto-minting made every undeclared `red` one global class; `-private`
in two files mints two, and atoms unify by identity, so the load error is
replaced by a query that silently has no solution. Two of the three embedded
fixture groups needed `-import_from` (or an export) rather than `-private` for
exactly this reason, and choosing `-private` would have left the suite green and
the fixture meaningless. The compiler cannot warn about it — two modules each
declaring a private atom is what `-private` is for. Added to
`docs/strict-atoms-migration.md` under Path B. Incidentally confirmed:
`-private` atoms *are* importable, which
`implementation_plans/atoms_refactor/GLOBAL_ATOMS_DEFAULT.md` says they should
not be. Not changed — the permissive behaviour is what keeps identity correct
here — but it is a real spec/implementation divergence and is filed as
`todo/private-atoms-are-importable-contra-spec.md`.

No engine change, as the todo predicted: strict atoms did exactly what they were
built to do, and the diagnostic named every declaration route each time.

---

# Strict-atoms-by-default broke downstream bare-atom fixtures

**Found:** 2026-07-30, while accounting for the four failures reported in
[[functor-identity-leaks-across-modules-in-one-process]]. Three of them turned
out to be this, not that.

**Severity:** low for the engine (behaving as designed), but it is unmeasured
migration fallout in at least one out-of-tree consumer, and it *masked* an
unrelated engine bug for a day by firing first.

## What

Strict atom resolution became the default (merged to canonical main 2026-07-29).
A rulebase that references a bare atom without declaring it now raises

    NameError: strict_atoms: undeclared atoms 'art_1', 'art_2', 'met', 'req_a',
    'req_b' in gate_q_1

`/workspace/clausify-executor-train`'s `auto/tests/test_gate_query.py` has three
fixtures that do exactly that, e.g.

    _RB_REQ_FIXTURE = """-import_from(formalize_lib, [attribute, profile_get, unmet])
    requirement(req_a, PROFILE, met, art_1) <- profile_get(PROFILE, "flag", "true")
    ...

`req_a`, `met`, `art_1`, `req_b`, `art_2` are undeclared, so
`test_query_requirements_returns_frozenset`,
`test_query_requirements_unmet_profile` and
`test_query_requirements_key_name_collides_with_predicate` now fail — against
canonical `/workspace/clausal` as well as any branch, and in isolation. The fix
there is a one-line `-private([req_a, req_b, met, art_1, art_2])` per fixture.

## Why it is worth a todo here rather than only there

Two things:

1. **The default landed without a sweep of out-of-tree consumers.** These three
   are the ones that happened to be in front of me; nobody has checked the rest
   of `clausify-executor-train`, the `domains/` corpus, or `packages/`. If the
   count is large, that argues for a migration note or a deprecation window
   rather than N separate one-line fixes.

2. **It cost a day of misattribution.** The `NameError` fires during
   `compile_module`, before the clause heads exist, so in the reported run it was
   hidden behind an unrelated `TypeError` from `head_key` — and all four failures
   got written up as one mechanism. The recorded claim that
   "`pytest auto/tests/test_gate_query.py -q` -> 4 passed in isolation" was
   already stale when it was written.

## Action

* Sweep the known consumers for undeclared bare atoms and count them, before
  deciding between "fix each fixture" and "publish a migration note".
* Not an engine change: strict atoms are doing what they were built to do, and
  the diagnostic already lists every one of the five declaration routes.
