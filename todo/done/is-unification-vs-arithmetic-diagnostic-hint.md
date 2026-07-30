# When `X is <arith expr>` later fails to unify with a number, say that `is` did not evaluate

**Filed:** 2026-07-30, from the local-formalizer study (Qwen3.6-27B authoring EU domains).
**Type:** diagnostics / DX. NOT a correctness bug — `is/2` behaves exactly as specified.

## The confusion, and why it is worth engine support

`is/2` is unification. `R is 5000 * 2` binds `R` to the term `Mult(5000, 2)`, and
nothing is wrong with that. `==` evaluates both sides, so `R == 5000 * 2` binds `R`
to `10000`. Verified for every operator (add, sub, mult, floordiv, truediv, mod, pow).

The problem is that `is` is spelled exactly like Prolog's *arithmetic evaluation*
operator, so a model — or a person — carrying Prolog habits writes `is` and gets a
silently unevaluated term. The failure then surfaces far from its cause:

```
test_public_interface.clausal:69 :: effective_ownership computes correct value
  goal 5 of 5 failed:
    eu.aml.amlr_bo_chain.effective_ownership(HOLDINGS, PERSON, ENTITY, 2500)
  the predicate DID have a solution, which did not unify (argument 4 differs):
    (argument 4 was actually: (2500 + 0))
```

or, one call later:

```
LogicException: Uncaught logic exception:
  error(type_error(number, FloorDiv(left=Mult(left=5000, right=5000), right=10000)),
        'sum_list/2')
```

The diagnostics are already good — the second one even prints the unevaluated node.
Neither, though, connects the symptom to the cause: an `is` that was expected to
evaluate. Every reader has to already know the `is`/`==` distinction to decode it.

## Requested

Where an unevaluated arithmetic node reaches a place that needs a number, add one line
naming the likely cause. Two sites, in priority order:

1. **`type_error(number, <ArithNode>)`** — the node type is already in hand, so the
   check is local:
   ```
   error(type_error(number, FloorDiv(...)), 'sum_list/2')
     note: that argument is an UNEVALUATED arithmetic term. `is` unifies, it does not
           evaluate — write `X == <expr>` to evaluate and bind, not `X is <expr>`.
   ```

2. **Unification failure where one side is an arith node and the other a number** —
   the "did not unify (argument N differs)" path already renders the node, so it can
   append the same note.

## Why this shape of fix pays

This project has repeatedly measured that a diagnostic naming its subject gets fixed on
the next attempt, while one that does not burns the remaining budget and blocks the run.
The `-module` arity diagnostic and the export-list-on-import-failure diagnostic are the
precedents: both converted multi-attempt dead ends into one-attempt fixes. This is the
same trade — the engine already holds the fact, it just is not saying it.

## Scope note / non-request

I am NOT asking for `is` to evaluate arithmetic. That would break the term-building
semantics the corpus depends on (`gold eu/aml/amlr_bo_chain` uses
`C == PCT * SUB / 10000` deliberately). Only the diagnostic is requested.

Separately and for the record: `=:=` is not accepted (`invalid syntax`). If Prolog
source compatibility is ever a goal that is worth knowing, but it is not a request here.

## Reproduction

```clausal
-module(ops, [z(N)])
z(0),
Test("is does not evaluate") <- ( R is 5000 * 2, R == 10000 )
```
```
bindings at failure: R = Mult(None, 5000, 2)
```
and for the `sum_list` path:
```clausal
Test("term reaches a numeric builtin") <- ( R is 10000 // 4, sum_list([R], S), S == 2500 )
```

---

## Done — 2026-07-30, both sites

Both requested sites carry the note. `is/2` is untouched.

### Verdict: sane, at both sites

The question was whether this can be done without a global "was this term built
by `is`?" flag. It can, because neither site needs one. What both sites need is
the weaker, purely structural fact *this is an arithmetic operator term and a
number was required here* — and each already holds both halves of it:

* Site 1's culprit is the second argument of the `type_error` term the exception
  already carries; `LogicException.term` is it.
* Site 2's `_report_nearest` has the computed value **and** the goal's
  over-constrained argument in local variables one line apart
  (`clausal/testing.py`, `value` from `_first_binding` and `args[i]`).

Nothing has to be threaded, recorded at bind time, or inferred.

### The note

```
  ../../tmp/isrepro/suml.clausal:5 :: term reaches a numeric builtin — Uncaught …
    goal 2 of 3 raised:
      sum_list([R], S)
      LogicException: Uncaught logic exception: Compound(functor='error', args=…
      note: `10000 // 4` is an unevaluated arithmetic term, not a number. `is`
            unifies without evaluating: `X is <expr>` binds X to the term,
            `X == <expr>` binds X to its value
```
```
    the predicate DID have a solution, which did not unify (argument 1 differs):
      eff(Add(None, 2500, 0))
    note: argument 1 pairs an unevaluated arithmetic term (`2500 + 0`) with a
          number. `is` unifies without evaluating: …
```

Site 1 also renders the culprit in surface syntax (`10000 // 4`), because the
opaque `FloorDiv(left=…, right=…)` repr on the line above is half the confusion.

### Truthfulness

The note never says an `is` was written — it cannot know that, and a `Mult` node
can be built by a clause head, by `unify/2`, or by CLP. It states one fact and
one language rule:

* fact: this value is an arithmetic operator term where a number was required
  (site 1) / on one side of an argument whose other side is a number (site 2);
* rule: `X is <expr>` binds the term, `X == <expr>` binds the value.

Both stay true whoever built the term, in the same way as
`"the segment 'b' did not resolve, so neither can 'a.b.c'"`.

### False positives: none in the corpus

Scanned all 769 `.clausal` files in `/workspace/clausify-domains` plus 47 in
`/workspace/clausify/kit` with `ast.parse` (`.clausal` is Python-parseable — `<-`
is `<` then unary minus), counting `Compare` nodes whose op is `Is`/`Eq` and
whose comparator is an arithmetic `BinOp`:

* `X == <arith>`: **331** occurrences. The idiom.
* `X is <arith>`: **1**, and it is not arithmetic — `DAYS is ++DELTA.days`
  (`clausify/kit/deadline_lib.clausal:112`), where `++` is the Python-interop
  marker. Hence `UnaryPlus` is deliberately **not** in the flagged set.
* Structural use of arithmetic terms — a clause head matching `Add(A, B)`,
  symbolic differentiation, expression simplification, `#=` constraint posting,
  a meta-interpreter over expressions: **zero occurrences**. `BinOp.__unify__`
  supports it and the corpus does not use it.
* 10 files fail to parse at all, every one of them
  `_dpo/*.student27b.clausal` — the local-formalizer output this todo came from.

`eu/aml/amlr_bo_chain/computation.clausal:25,31` uses `==`, as the scope note
said; its results reach `sum_list` as numbers, so the note cannot fire there.

Site 2's requirement that a *number* sit opposite the operator term is what
keeps it off the one legitimate pattern that does exist: a clause building
`DA + DB` to unify against another operator term never has a number on the
other side.

### Cost: failure paths only

Site 1's check is in `LogicException.__str__`, not `__init__` — `__init__` is
byte-identical to before, so constructing a LogicException (these terms are
`throw`/`catch` control flow, so construction is not rare) costs exactly what it
did. A caught exception whose message nobody renders pays nothing.

Site 2's check is two `isinstance` tests in `_report_nearest`, reached only from
`diagnose_failure`, which `run_test` calls under `if diagnose and not
result.passed` (`clausal/testing.py:259`).

### Reach, and what was deliberately left alone

`type_error("number", …)` has exactly three raise sites — `sum_list/2`
(`clausal/logic/builtins/lists.py:641`) and `number_chars/2` / `number_codes/2`
(`chars.py:633,685`) — so site 1's reach is narrow by construction, not by
choice. Probed the neighbours:

* `max_list`/`min_list` on a one-element list return the arithmetic term itself
  and raise nothing; on a mixed list they raise `type_error(orderable, <the
  whole list>)`, whose culprit is a list, not a node. Recursing into a culprit
  to find a node inside it was not done: it would have to guess which element
  the author meant.
* `type_error("evaluable", …)` (`clpfd.py:1593,1604`) explicitly lets
  arithmetic terms through, so it can never carry one — hence it is not in
  `_NUMERIC_EXPECTATIONS` (`number`, `integer`).
* Site 2 fires on a *top-level* argument only, which is the shape both reported
  failures had. An arithmetic node nested inside a compound (`verdict(_, 2500 +
  0, _)`) is not named; finding it would need a walker, and naming the wrong
  subterm is worse than naming none.

`=:=` is confirmed rejected — `Test("arith eq") <- ( R =:= 5 )` gives
`invalid syntax` with a caret under the `=:=`. Recorded, not requested, not done.

### Files

`clausal/logic/exceptions.py` (`ARITH_OPERATOR_TERMS`, `IS_VS_EQ_HINT`,
`is_arith_operator_term`, `render_arith_operator_term`,
`arith_in_numeric_position_hint`, `LogicException.__str__`),
`clausal/testing.py` (`_arith_vs_number_note`, `_is_number`, one call in
`_report_nearest`), `tests/test_is_vs_eval_diagnostic.py` (10 tests: 4 that
assert the note, 5 negative controls — non-arithmetic culprit, non-numeric
expectation, unhashable expectation, compound near miss, number-vs-number near
miss — and one pinning `.term` unchanged, since `catch/3` matches on it).

Red-green verified by `git stash push -- clausal/`: `4 failed, 6 passed`, the
four failures being exactly the four that assert the note. Restored: `10 passed`.
Full suite `2 failed, 10673 passed, 136 skipped, 44 xfailed` — the two being the
known `test_no_raw_untested_blocks` (28 violations, list unchanged) and the
`test_F026_multi_star_splits_bounded_for_moderate_input` timing flake, which
fails identically with `clausal/` stashed.
