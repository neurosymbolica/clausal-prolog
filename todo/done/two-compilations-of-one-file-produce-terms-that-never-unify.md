# Two compilations of one file produce terms that never unify — silently

**Found:** 2026-08-24, building a Python layer that runs one rule domain and then
hands its result term to a *separate* rulebase for classification.
**Severity:** the mismatch is **not an error**. The pattern match simply yields no
solution, and the two terms *render identically*, so every diagnostic a caller reaches
for agrees they are the same. That is what makes it worth fixing rather than documenting.

## The two loading routes disagree about term identity

```python
from clausal.testing import load_clausal_module
dom = load_clausal_module("/path/to/soledom.clausal")   # compilation A
# elsewhere, a rulebase does:  -import_from(soledom, [sole_verdict, ok])
# which resolves through sys.path/sys.modules            -> compilation B
```

`load_clausal_module` compiles a fresh module (named `_clausal_test_<basename>`). A dotted
`-import_from` of the *same file* goes through the import hook and produces a **second,
independent** compilation. The declared compound `sole_verdict/2` therefore exists twice,
as two distinct classes, and a term built by A's constructor does not unify with a pattern
built from B's.

## Reproduction

`soledom.clausal`:

```prolog
-module(soledom, [sole_verdict(STATUS, NOTE), ok, note1, decide_sole(IN, VERDICT)])

-strict_atoms

decide_sole(IN, VERDICT) <- (
    IN is ok,
    VERDICT is sole_verdict(STATUS=ok, NOTE=note1)
)
```

`comp2.clausal`:

```prolog
-module(comp2, [classify(VERDICT, CLASS), matched])

-import_from(soledom, [sole_verdict, ok])

-strict_atoms

classify(VERDICT, matched) <- (
    VERDICT is sole_verdict(STATUS=ok)
)
```

```python
import sys; sys.path.insert(0, DIR)
dom  = load_clausal_module(DIR + "soledom.clausal")
comp = load_clausal_module(DIR + "comp2.clausal")
v = first_solution("decide_sole", dom.ok, module=dom["$module"])
classify(v, C, module=comp["$module"])
```

Observed:

```
verdict from load_clausal_module : sole_verdict(STATUS=ok, NOTE=note1)
classify() via dotted -import_from: *** ZERO SOLUTIONS — no error ***
same constructor object?  False
```

Changing only the domain's loading route to `importlib.import_module("soledom")` — so both
sides share one `sys.modules` entry — makes the identical rule match:

```
domain via dotted import -> ['matched']
constructor identity      -> True
```

## Why that is worse than an ordinary mismatch

The failure is indistinguishable from "the rule correctly did not apply":

- `term_str` renders both terms identically, so printing them shows no difference.
- The functor name, arity and field names are all equal.
- Nothing raises. A three-valued classifier reading "no solution" as *this rule does not
  apply* silently reclassifies every case.

In the application this was found in, the whole run would come back either
"indeterminate" or, where the affected predicate is a gate, "this rule does not apply
here" for every record. A confident, uniform, wrong answer.

It took a minimal two-file reproduction to see, because the real corpus **hides it**: those
domains re-export their verdict constructors from a dotted submodule, which both
consumers reach through the same `sys.modules` entry. So identity holds by accident of
file layout, and the trap only springs for a domain that defines its constructor in the
file loaded directly.

## Options

1. **Make `load_clausal_module` reuse an existing compilation** when the file is already
   importable on `sys.path` (resolve to the dotted module and return it, rather than
   compiling a parallel copy). Most consistent; one file means one set of declared terms.
2. **Make declared-compound identity structural rather than per-compilation** — unify on
   `(module_path, functor, field names)` instead of class identity. Bigger change, but it
   removes the whole class of problem rather than one route into it.
3. **Make it loud:** when a unification compares two same-named, same-arity declared
   compounds from different compilations of the same source path, raise rather than fail.
   Preserves current semantics for genuinely different types and closes the silent path.
4. **Document only**, and have callers guarantee one universe. This is what the consumer
   now does (an `is`-identity check at batch start), but it puts the burden on every caller
   and only helps the ones who know to look.

Option 1 or 3 seems right. The important property is that **two compilations of one file
must not silently produce mutually unmatchable terms.**

## Not addressed here

Whether the same split affects atoms used as **dict keys** (a plain-atom key from
compilation A used against a clause reading it in compilation B). Expected to behave the
same way, and it would present as `get/3` soft-failing — see
`get3-rejects-a-plain-dict-that-subscript-accepts.md`, which is a different cause with an
identical symptom. Worth checking together.

---

## Resolved 2026-08-23 — option 1, applied to the import route

The general shape of the bug is wider than the reproduction above: it is not
specific to `load_clausal_module`. Any *one* file reachable under *two* dotted
names compiles twice, because CPython's module cache is keyed by dotted name.
That happens with no testing helper in sight whenever a package directory and
its parent are both on `sys.path`:

```prolog
-import_from(soledom, [sole_verdict, ok])       % pkg/ is on sys.path
-import_from(pkg.soledom, [sole_verdict, ok])   % pkg/'s parent is too
```

Both resolve to `pkg/soledom.clausal`; `sole_verdict` then exists as two
classes, and a term from one consumer yields zero solutions against the other's
pattern. Pinned in `tests/test_import_path_canonicalization.py`.

**Fix (`clausal/import_hook.py`):** the finders now deduplicate by resolved
source path. `_MODULES_BY_PATH` maps `realpath(source)` → the dotted name it
was first imported under; `_ExtensionFinder._spec_for` consults it, and a
second name for a file already loaded gets an `_AliasLoader` spec that binds
the existing module instead of compiling a parallel copy. So
`sys.modules["soledom"] is sys.modules["pkg.soledom"]`, and one file means one
set of declared terms.

Details worth knowing:

- The alias is installed from `exec_module`, not `create_module`. A module
  returned from `create_module` gets `_init_module_attrs` applied to it, which
  would overwrite the *canonical* module's `__name__`/`__spec__` with the
  alias's. Swapping `sys.modules[name]` inside `exec_module` — the trick
  `PredicateLoader` already uses — hands importlib the canonical module without
  touching it.
- Keyed by `realpath`, so a symlinked package directory is not a second copy.
- Self-healing: an entry whose module has been evicted from `sys.modules` is
  ignored, and the next load reclaims the path.
- `.pl` modules go through the same finder base, so `PrologLoader` is covered.
- The claim is made after exec and importlib's lock is per name, so two threads
  first-importing two names for one file concurrently can still both compile.
  Unchanged from before; not worth a path-wide lock.

## Deliberately *not* changed: `load_clausal_module`

The testing helper still compiles a private `_clausal_test_<basename>` copy on
every call, and stays out of the path registry — 101 in-repo call sites depend
on each call yielding an independent database. So the original reproduction
(helper on one side, dotted `-import_from` on the other) still produces two
term universes; that is option 4 for this one route, and the hazard is now
stated in the helper's docstring. An embedder that needs one universe across
both routes should reach the file through `importlib`.

Option 3 (raise when two same-named declared compounds from one source path
meet in a unification) was not pursued: `unify` is the C accelerator
(`clausal/logic/variables/_variables.c`), so the check would cost a rebuild and
sit on the hot failure path — and with the import route deduplicated, the only
way to reach it is the helper mix above.

## Still open

The dict-key question under "Not addressed here" is untouched.
