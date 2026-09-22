# TODO: structural head-arg normalization doesn't recurse into LIST elements

**Opened 2026-06-25** from real-world exercise (an external authoring harness's
formalization library). Direct
follow-on to `compound-head-literal-output-mode.md` (RESOLVED 2026-06-23): that fix
binds **top-level** structural head args in output mode, but the normalization does
not recurse into **list elements**, so a compound nested in a head list whose inner
variable is bound in the **body** silently keeps a decoupled (non-ground) variable.

## Symptom

`ground/1` is false (and `==` fails) for a head-list compound's inner var after the
body binds it. Downstream this is severe: in a downstream helper library it caused its
own 6-arity dispatcher predicate to thread an unbound STATUS into clause-dispatched
marks, producing a 3^N solution explosion (see that library's own history, 2026-06-24,
where the workaround was to build the term in the body).

## Repro

`todo/head_list_compound_repro.clausal` (run with `python -m clausal.testing`).
Minimal failing case:

```clausal
-private([item2(S)])
prov(K, V) <- (K is "x", V is "met")

# inner var S of item2(S) is shared with the body goal prov("x", S):
ev_plain([item2(S)]) <- (prov("x", S))
Test("ground") <- (ev_plain([item2(S)]), ground(S), S == "met")   # FAILS: S non-ground
```

## What distinguishes broken from working (narrowed)

| Head shape | Inner var bound by | Result |
|---|---|---|
| Bare compound `c(S)` | body goal | **OK** (fixed 2026-06-23) |
| List-nested `[c(S)]` | head-to-head unify (caller supplies it) | OK |
| **List-nested `[c(S)]`** | **a body goal** (plain or `call_goal`) | **BROKEN** |

So the trigger is specifically: a structural literal **inside a list pattern** in
the head, whose inner var also occurs in the body. The list/cons elements aren't
being hoisted+unified the way top-level head args now are.

## Likely site / fix

`_normalize_structural_head_args` in `clausal/logic/database.py` (and/or the
`MatchClass` lowering in `clausal/logic/compiler/head_match.py`). The 2026-06-23 fix
hoists each *top-level* structural head arg to a fresh Var + prepended `Unify`. It
needs to **recurse into list literals (cons cells) and other nested compounds**,
hoisting nested structural sub-terms so their inner vars unify with the clause's
shared body variables. Option C from `compound-head-literal-output-mode.md` (route
the whole clause through fact-style lowering when any head arg contains a structural
literal, at any depth) would cover this uniformly.

## Done when

- All 3 cases in `todo/head_list_compound_repro.clausal` PASS.
- Regression test covering list-nested AND deeper-nested (e.g. `[c(d(S))]`) head
  compounds with body-bound inner vars, both modes.
- Re-running the downstream helper library's own test suite still passes
  with its body-construction workaround removed (i.e. the workaround becomes
  optional) — a good external regression.
