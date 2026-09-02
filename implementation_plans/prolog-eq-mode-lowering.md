# `==` and ordering comparisons: mode- and type-correct ISO lowering

**Status:** DESIGN — no code, no test changes. Written for
`.superpowers/sdd/2026-09-02-iso-export-wave-2` Task 5 (`clausify-executor-train`),
scope-extended by controller ruling to cover date-term ordering (Task 6's §7 concern).

**Problem in one sentence:** `clausal/tools/clausal_to_prolog.py::_convert_compare`
lowers Clausal's comparison operators by **operand shape**, but their meaning depends
on operand **mode** (bound vs unbound) and operand **type** (number vs `date`), so the
exported ISO program either checks a value it can no longer compute or raises on a
term ISO's arithmetic evaluator has never heard of.

Everything below was re-derived in this session against
`/workspace/clausify-domains` (765 published-domain `.clausal` files),
`/workspace/clausal/venv/bin/python -c "from clausal.tools.clausal_to_prolog import
clausal_source_to_prolog"`, the Clausal engine itself, and
`/workspace/scryer-prolog/target/release/scryer-prolog`. Every output block is unedited terminal
output, of one of two kinds, and each block says which:

- **Scryer blocks** show the consulted file and the exact
  `$ printf '…' | scryer-prolog …` invocation, with Scryer's own answers beneath.
  Scryer does not echo a piped query, so the queries live in the `printf` and the
  answers are in query order. Re-running the shown command reproduces the shown lines
  byte for byte — this was checked mechanically for all 6 blocks after the last edit.
- **Engine blocks** are marked "Python driver stdout". They are the unedited stdout of a
  small Python driver calling the predicate once per row against the live Clausal
  engine; the `-> succeeds` / `-> fails` wording is that driver's `print()`, while the
  values and any exception text are the engine's.

Where this document contradicts
`docs/iso-export-pilot-2026-09.md` §5.1 or `.superpowers/.../task-6-report.md` §7, the
divergence is called out explicitly.

---

## 1. The semantic difference

### 1.1 What Clausal's `==` actually is

`==` in Clausal source parses to `nodes.ArithEq`
(`clausal/pythonic_ast/conversion_from_python_ast.py:175`), whose class docstring
(`clausal/pythonic_ast/nodes.py:655-663`) carries a standing guard comment:

> **warning:: Do not rename this to StructuralEq.** `==` in Clausal is *arithmetic*
> equality, not structural equality. True structural equality (Prolog `==/2`) is the
> separate `StructuralEq` node / `structural_eq/2` builtin.

`ArithEq` lowers to `FDCompare(op="eq", ...)`
(`clausal/logic/compiler/terms_to_goalop.py:94, 448-450`) — a CLP(FD/ℤ) **constraint**,
not a test. A constraint over one unbound variable determines it.

`is` in Clausal is `nodes.Unify` — plain unification (`nodes.py:709-711`), which the
translator correctly emits as ISO `=/2` (`_convert_compare`, the `Is` case,
`clausal_to_prolog.py:1179-1187`). Clausal's *eager* arithmetic evaluate-and-bind is
the separate `eval_(EXPR, RESULT)` call (`nodes.py:719-720`,
`terms_to_goalop.py:381-386`), which the translator does emit as ISO `is/2`
(`clausal_to_prolog.py:991-997`).

So the memory-note "Clausal `is/2` means the OPPOSITE of ISO `is/2`" is **confirmed
from source, with a correction to its usual phrasing**: Clausal `is` ≈ ISO `=`, and the
Clausal operator that plays ISO `is/2`'s role is **`==`**, not `eval_` — because
**the corpus calls `eval_` exactly 0 times** (`grep -rn --include='*.clausal' "eval_("`
over `/workspace/clausify-domains`, excluding `_`-prefixed scratch trees: 0 hits) while
it writes `==` in 826 goal positions (§2.1). The `eval_` path in the translator is
dead for this corpus.

### 1.2 Clausal `==`, measured

Run against the live engine (`/workspace/clausal/venv/bin/python`), predicate
`eq(A, B) <- (A == B)` (Python driver stdout — one call per row, printing the outcome and
the dereferenced bindings; the `-> succeeds` / `-> fails` wording is the driver's, the
exception text is the engine's):

```
eq(2500, 2500.0)   ground/ground numeric, diff type  -> succeeds, bindings (2500, 2500.0)
eq(foo, foo)       ground/ground atom equal          -> succeeds, bindings ('foo', 'foo')
eq(foo, bar)       ground/ground atom unequal        -> fails
eq(V, 1257000)     unbound/ground numeric            -> succeeds, bindings (1257000, 1257000)
eq(V, foo)         unbound/ground atom               -> RAISES Uncaught logic exception: Compound(functor='error', args=(Compound(functor='type_error', args=('evaluable', 'foo')), '(==)/2'))
eq(1257000, V)     ground numeric/unbound            -> succeeds, bindings (1257000, 1257000)
eq(V, W)           unbound/unbound                   -> succeeds, bindings (AttVar(_14, attrs={}), AttVar(_15, attrs={}))
```

The `type_error(evaluable, foo)` is raised by `_reject_nonnumeric_eq`
(`clausal/logic/clpfd.py:1694`). So Clausal `==` is: **numeric arithmetic equality that
binds an unbound side, degrading to a ground structural test when both sides are ground
non-numbers, and raising when one side is unbound and the other is a ground non-number.**

### 1.3 The same shapes in ISO, measured

Scryer (`/workspace/scryer-prolog/target/release/scryer-prolog`, `--version` reports
`cargo:0.10.0`). Consulted file `mx2.pl`:

```prolog
seq(A, B) :- A == B.
aeq(A, B) :- A =:= B.
```

```
$ printf 'seq(2500, 2500.0).\nseq(foo, foo).\nseq(foo, bar).\nseq(_, 1257000).\nseq(_, foo).\nseq(_, _).\naeq(2500, 2500.0).\naeq(_, 1257000).\naeq(_, foo).\n' | scryer-prolog mx2.pl
   false.
   true.
   false.
   false.
   false.
   false.
   true.
   error(instantiation_error,(is)/2).
   error(instantiation_error,(is)/2).
```

Answers in query order: `2500 == 2500.0` false; `foo == foo` true; `foo == bar` false;
`V == 1257000` false; `V == foo` false; `V == W` false; `2500 =:= 2500.0` true;
`V =:= 1257000` raises; `V =:= foo` raises.

Side by side, of the 7 Clausal rows, **4 diverge** from the emitted `==` and **2 of the
3 comparable rows diverge** from the emitted `=:=`. Neither ISO operator can bind, so
neither reproduces the two binding rows at all.

### 1.4 Worked example — the `uk/tax` witness, run in Scryer

Source, `/workspace/clausify-domains/uk/tax/income_tax_rates_allowances/liability.clausal`,
lines re-derived by `grep -n` in this session. Three of the four line numbers the Task 5
brief names (133, 169, 217) are confirmed; the fourth, **229, is not a `==` witness** —
`liability.clausal:229` is `total_income in PROFILE`, a membership goal belonging to the
pilot doc's separate §5.2 `in` → `member/2` defect. Seven further `==` goals the triage
doc did not list are included below:

| source line | Clausal text | emitted line | emitted ISO |
|---|---|---|---|
| 133 | `ALLOWANCE == FULL_ALLOWANCE` | 47 | `Allowance == Full_allowance` |
| 148 | `EXCESS == ADJUSTED_NET_INCOME - TAPER_THRESHOLD` | 53 | `Excess =:= Adjusted_net_income - Taper_threshold` |
| 155 | `REMAINING_TWICE == 2 * FULL_ALLOWANCE - EXCESS` | 59 | `Remaining_twice =:= 2 * Full_allowance - Excess` |
| 156 | `ALLOWANCE == (REMAINING_TWICE + 199) // 200 * 100` | 60 | `Allowance =:= div(Remaining_twice + 199, 200) * 100` |
| **163** | `ALLOWANCE == 0` | **66** | `Allowance == 0` |
| 169 | `AFTER_ALLOWANCE == TOTAL_INCOME - ALLOWANCE` | 71 | `After_allowance =:= Total_income - Allowance` |
| 188 | `ABOVE_LIMIT_RAW == TAXABLE - LIMIT` | 81 | `Above_limit_raw =:= Taxable - Limit` |
| 196 | `BAND_WIDTH == HIGHER_RATE_LIMIT - BASIC_RATE_LIMIT` | 88 | `Band_width =:= Higher_rate_limit - Basic_rate_limit` |
| 209 | `BAND_TAX == BAND_AMOUNT * RATE_PERCENT // 100` | 99 | `Band_tax =:= div(Band_amount * Rate_percent, 100)` |
| 217 | `TAX_DUE == BASIC_TAX + HIGHER_TAX + ADDITIONAL_TAX` | 106 | `Tax_due =:= Basic_tax + Higher_tax + Additional_tax` |

*(Emitted line numbers are into the `.pl` text produced by
`clausal_source_to_prolog(open(liability.clausal).read())` with no other arguments.)*

`liability.clausal:163` (`ALLOWANCE == 0` → `Allowance == 0`) is a **witness the triage
doc missed**: a full-taper case where the domain means "the allowance is nil" and the
export emits a structural test that can only ever fail on an unbound `Allowance`.

The two shapes, minimised. File `eq_witness.pl`:

```prolog
taxable(Total, Allow, After) :- After =:= Total - Allow.   % liability.clausal:169 shape
allow(A, F)                  :- A == F.                    % liability.clausal:133 shape
```

```
$ printf 'taxable(1257000, 257000, After).\nallow(A, 1257000).\ntaxable(1257000, 257000, 1000000).\n' | scryer-prolog eq_witness.pl
   error(instantiation_error,(is)/2).
   false.
   true.
```

Answers in query order: computing `After` **raises**; computing `A` **fails**; checking
an `After` the caller already supplied **succeeds**.

The same two predicates written in Clausal and run on the engine (Python driver stdout;
the wording is the driver's, the values are the engine's):

```
CLAUSAL  taxable(1257000, 257000, AFTER) succeeds with AFTER = 1000000
CLAUSAL  allow(A, 1257000)               succeeds with A = 1257000
```

That is the defect in five lines of output: the engine computes `1000000` and
`1257000`; the export raises on one and fails on the other. The third Scryer answer
shows why no gate below G3 can see it — hand the export the answer and it happily
checks it.

### 1.5 A second divergence, for operands that *are* bound

The pilot doc treats this as purely a binding-mode problem. It is not. Even where both
operands are bound — the 429-goal majority of emitted `==` (see §2) — the emitted `==`
is the wrong *operator family*, because Clausal `==` is arithmetic:

Clausal, `chk(X) <- (X == 2500)` (Python driver stdout):

```
CLAUSAL chk(2500.0) -> succeeds
CLAUSAL chk(2500)   -> succeeds
```

ISO, the emitted `chk(X) :- X == 2500.` in file `num2.pl`:

```
$ printf 'chk(2500.0).\nchk(2500).\n' | scryer-prolog num2.pl
   false.
   true.
```

An integer-vs-float mismatch anywhere in a bound comparison silently flips the verdict.
The corpus is pence/cents/basis-points integer arithmetic throughout, so this is latent
today rather than live — but it is latent in 429 goals, and any future `//` → `/` or
percentage-rate change makes it live.

Supporting fact: **the corpus never writes structural equality at all.**
`grep -rn --include='*.clausal' "structural_eq"` over the published domain trees returns
**0 hits**. So all 553 emitted `==` goals and all 273 emitted `=:=` goals originate from
`ArithEq`. Not one of them was ever intended as ISO `==`.

### 1.6 A latent third path (no live corpus instance)

`_convert_compare`'s multi-comparison branch (`clausal_to_prolog.py:1214-1248`) does
**not** consult `_is_arith_operand`; it hard-codes `==` / `\==` for every `Eq` / `NotEq`
link in a chain:

```
q(X, Y, Z) :-            % from  Q(X, Y, Z) <- (X == Y + 1 == Z)
    X == Y + 1,
    Y + 1 == Z.
```

`X == Y + 1` can never succeed for numeric `X` in ISO — `printf '5 == 4 + 1.\n' |
scryer-prolog` prints `   false.` An AST scan of all 765 published `.clausal` files finds **0 chained `Compare`
nodes**, so this is dead code today; any fix must not leave it behind as the one path
that still guesses.

---

## 2. Inventory — which Clausal operators reach which emitted ISO forms

**Method.** Every `.clausal` file under `/workspace/clausify-domains` whose path does not
start with a `_`-prefixed top-level directory (`_dpo`, `_work`, `_training`, `_tools`) —
**765 files, all 765 translating without exception** under
`clausal_source_to_prolog(source)` with default arguments. (The 10 files that raise
`SyntaxError` are all in `_dpo/…student27b.clausal`, i.e. rejected model output, and are
excluded. The pilot doc's census of 692 files uses a different, manifest-driven file set;
this document's numbers are for the 765-file walk described here and are not directly
comparable to it.)

### 2.1 Emitted operator census

"goals" counts **top-level body conjuncts** — exact, but undercounts goals nested inside
`findall/3`, `aggregate_over/3`, `once/1`. "occurrences" counts every appearance in
non-comment, non-directive clause text with the lambda arrow `< -` masked out — a
superset that includes nested goals.

| emitted ISO | goals | files | occurrences | files |
|---|---:|---:|---:|---:|
| `=:=`  | 273 | 88  | 274 | 88  |
| `==`   | 553 | 110 | 577 | 111 |
| `=\=`  | 0   | 0   | 0   | 0   |
| `\==`  | 6   | 4   | 7   | 4   |
| `is`   | 1   | 1   | n/a | n/a |
| `<`    | 110 | 54  | 149 | 63  |
| `=<`   | 89  | 45  | 91  | 45  |
| `>`    | 113 | 63  | 125 | 72  |
| `>=`   | 174 | 67  | 187 | 74  |
| `@<`   | 0   | 0   | 0   | 0   |

(`is` is not given an occurrence count: the substring ` is ` appears inside English
citation-label strings, which the occurrence pass cannot exclude.)

Headline: **826 emitted equality goals (273 `=:=` + 553 `==`), 1 emitted `is/2` goal**,
in a corpus whose sources use `==` to *produce* a value in most of those places.

### 2.2 Source operator → emitted form

Derived from `_convert_compare` (`clausal_to_prolog.py:1146-1249`) and confirmed by
translating one-line probes:

| Clausal source | AST node | engine meaning | emitted ISO | faithful? |
|---|---|---|---|---|
| `X is Y` | `Unify` | unification | `X = Y` | yes |
| `X is not Y` | `DoesNotUnify` | `dif/2` | `dif(X, Y)` | yes |
| `eval_(E, R)` | `Evaluate` | ISO `is/2` | `R is E` | yes (0 corpus uses) |
| `X == Y+1` (either side a `BinOp`/unary) | `ArithEq` | CLP(FD) equality constraint | `X =:= Y+1` | **no** — cannot bind |
| `X == Y` (neither side a `BinOp`) | `ArithEq` | CLP(FD) equality constraint | `X == Y` | **no** — wrong family *and* cannot bind |
| `X != Y+1` | `ArithNeq` | CLP(FD) disequality | `X =\= Y+1` | no (0 corpus uses) |
| `X != Y` | `ArithNeq` | CLP(FD) disequality | `X \== Y` | **no** (6 corpus goals) |
| `X < Y`, `X <= Y`, `X > Y`, `X >= Y` | `Lt/LtE/Gt/GtE` | CLP(FD) or `datetime` ordering | `<`, `=<`, `>`, `>=` | **no when operands are dates** — §6 |
| `structural_eq(X, Y)` | builtin call | ISO `==` | (not routed) | 0 corpus uses |

The whole decision rests on `_is_arith_operand` (`clausal_to_prolog.py:1130-1144`),
which returns `True` for exactly `ast.BinOp` and unary `+`/`-`. It is a **syntactic
shape test standing in for a mode-and-type analysis**, and `docs/prolog_translation.md`
line 109 records the result under the wrong name: "`X == Y` → `X == Y` — Structural
equality". Per `nodes.py:655-663` that label is exactly what the engine forbids.

### 2.3 Mode classification of the emitted equality goals

For every emitted clause, every body goal of shape `Var <op> Rest` on its own line
(799 goals total), classified by where `Var` is first bound:

| emitted | LHS bound by an earlier body goal | LHS appears in the head only (unbound in the compute-the-answer mode) | LHS bound nowhere in the clause (always unbound) |
|---|---:|---:|---:|
| `=:=` | 11 goals / 9 files | **94 goals / 44 files** | **152 goals / 56 files** |
| `==`  | 429 goals / 72 files | **108 goals / 34 files** | **5 goals / 1 file** |

**359 goals across 92 distinct files (71 of them non-test) emit a test where the engine
binds.** The 429 `==` goals in column 1 are the §1.5 latent-divergence population.

Sample rows, verbatim from the pass:

```
=:=  head-arg-only     au/corps_act_disclosure/classification.clausal | N =:= C1 + C2 + C3.
=:=  head-arg-only     eu/aml/amlr_bo_chain/ownership_interest.clausal | C =:= Pct * Sub/10000.
=:=  never bound       au/corps_act_disclosure/substantial_holding.clausal | Delta =:= Current_bps - Previous_bps,
==   bound earlier     au/aml_ctf/tests/test_output_mode.clausal | Tranche == 1.
==   bound earlier     au/aml_ctf/tests/test_output_mode.clausal | Comm == date(2026, 7, 1).
==   head-arg-only     eu/aml/amlr_bo_chain/ownership_interest.clausal | C == Pct.
==   never bound       th/visa/tests/test_negative_controls.clausal | Age == 45,
```

Caveat on "head-arg-only": whether that column is a defect is genuinely mode-dependent.
Called with the output argument bound (which is what a domain's own `test_input_mode`
suites do) those goals behave; called to compute (which is what
`test_output_mode`, the verdict predicates, and every real query do) they do not. The
column is reported separately rather than folded in for that reason.

---

## 3. Lowering options for `==` / `!=`

### Option A — runtime-dispatching companion predicate

Route every `ArithEq` through one exported helper that reproduces §1.2's matrix by
inspecting instantiation at call time. Shape (illustrative only — no code is being
proposed for commit here):

```prolog
clausal_eq(A, B) :- var(A), var(B), !, A = B.
clausal_eq(A, B) :- var(A), !, A is B.
clausal_eq(A, B) :- var(B), !, B is A.
clausal_eq(A, B) :- number(A), number(B), !, A =:= B.
clausal_eq(A, B) :- A == B.
```

- **Correctness:** highest available. Every row of §1.2 is reproduced, including the
  `type_error(evaluable, …)` row — `A is foo` raises `type_error(evaluable, foo/0)`,
  the same error family the engine raises, though not the identical culprit term
  (`foo/0` vs `foo`). Needs no mode analysis, so it cannot be wrong about a mode.
- **Readability:** worst. `Tax_due =:= Basic + Higher + Additional` becomes
  `clausal_eq(Tax_due, Basic + Higher + Additional)`. A published legal ontology that a
  regulator is supposed to read loses its arithmetic to a helper call in **826 places**.
- **Purity:** as written it uses `!`, which the export pipeline forbids (the translator
  already refuses to emit `!` — `clausal_to_prolog.py:976-990`). A cut-free version
  using nested `( … -> … ; … )` is straightforward but not free — `->` has its own
  status in the companion files (`clausal_dates.pl` is documented as `->`-free).
- **New engine tests to pin it:** (i) `clausal_source_to_prolog('Q(X,Y) <- (X == Y+1)')`
  contains `clausal_eq(`; (ii) a Scryer-execution test asserting each of §1.2's 7 rows
  reproduces (this is the test class that does not exist today at all — see §5);
  (iii) a test that no emitted file contains `!`.

### Option B — clause-local left-to-right binding analysis, plus a fallback

Walk each clause's body left to right maintaining the set of variables bound by the head
and by earlier goals — exactly the analysis §2.3 already implements as a measurement —
and choose per goal:

1. LHS is a variable **not** in the bound set, RHS's variables all in it → `LHS is RHS`.
2. Both sides in the bound set, and either side is syntactically arithmetic → `=:=`.
3. Both sides in the bound set, neither arithmetic → `==` (today's behaviour, correct
   only if the operands are never numbers of differing type).
4. Anything else (RHS also unbound; LHS a compound; goal nested inside `findall/3` or
   `once/1` where left-to-right order is not the caller's order) → fall back to Option
   A's helper, or refuse (§ Option C).

- **Correctness:** good but **not sound in general**, and the unsoundness is exactly
  where §2.3's middle column sits. A head argument is "bound" only in some calling
  modes; the analysis has to pick one. Picking "head args are unbound" (the
  compute-the-answer mode) makes rule 1 fire for the 202 head-arg-only goals and turns
  `Allowance == Full_allowance` into `Allowance is Full_allowance` — correct for every
  verdict query and **wrong for a `test_input_mode` suite that passes `Allowance`
  bound**, where `is/2` would then raise instead of checking. Picking the other way
  reproduces today's bug. There is no single static answer; a per-predicate mode
  fixpoint over the whole domain (all files, including test files, which call in the
  other mode) would be needed to do better, and even that is a whole-program analysis
  the translator does not currently perform — `clausal_source_to_prolog` translates
  **one file at a time**.
- **Readability:** best. At least the 246 goals of §2.3's `=:=` row (94 head-arg-only
  + 152 never-bound), where the RHS is syntactically arithmetic, become the obvious
  `Tax_due is Basic + Higher + Additional` — what a Prolog reader expects. Rule 1 also
  fires on the `==` rows whose RHS is a variable bound by an earlier goal
  (`Allowance is Full_allowance`), so 246 is a floor on the readable population, not a
  ceiling.
- **New engine tests to pin it:** (i) `P(X, A, B) <- (X == A + B)` emits `X is A + B`;
  (ii) `P(A, B, X) <- (foo(A, X), X == A + B)` — LHS bound by an earlier goal — emits
  `=:=`, not `is`; (iii) a goal nested in `findall/3` takes the fallback; (iv) each of
  §1.2's 7 rows, executed in Scryer against the emitted text.

### Option C — refuse under strict

Leave permissive mode as-is; in `strict=True`, raise `UntranslatableConstructError` for
any `ArithEq` the translator cannot prove safe (i.e. every case that is not Option B's
rule 2 or rule 3).

- **Correctness:** total, by construction — nothing wrong is emitted.
- **Cost:** the strict-mode ratchet baseline (`clean 648` of 692,
  `docs/iso-export-pilot-2026-09.md` headline) would drop substantially. §2.3's **92
  affected files** are counted over this document's 765-file walk, not over the
  ratchet's 692-file set, so the exact new baseline has to be measured rather than
  subtracted — but it is a drop of the same order, and larger still if the refusal also
  fires wherever the analysis is merely inconclusive. Every domain among §2.3's 71
  non-test files stops being publishable until its source is rewritten to spell the mode
  explicitly (`eval_(EXPR, RESULT)` where it means compute, `==` where it means check).
  That is ~71 corpus edits in a sibling repo, not an engine change.
- **New engine tests to pin it:** (i) `strict=True` raises on `X == A + B` with unbound
  `X`; (ii) `strict=False` still emits and warns; (iii) the raise carries the source
  line and names the offending goal.

---

## 4. Recommendation

**Option B with Option A as its fallback, and Option C behind a separate flag — but
staged, and with the ordering of the stages mattering more than the choice.**

The reasoning:

1. **Nothing can be recommended for adoption until a test exists that would have caught
   this.** §5 shows the engine has four assertions pinning this lowering and **not one
   of them executes the emitted program**; a fix validated by the same kind of assertion
   would be validated by nothing. The first commit under this design must therefore be
   the *harness*: a test that translates a Clausal predicate, runs the emitted `.pl` in
   Scryer, and compares answers against the same predicate run on the Clausal engine.
   §1.2 and §1.3's matrices are that test's first 7 rows, and they are red today.
2. Once the harness exists, **Option B's rules 1 and 2 are unambiguous wins** and cover
   at least 246 of the 359 defective goals (§3, Option B) with output a reader
   recognises. They can land alone.
3. **Rule 1's mode assumption is the one real decision the operator has to make** and it
   should be made explicitly, not implied by a heuristic: is an exported legal ontology
   a *program that computes verdicts* (head args unbound → `is/2`, and the input-mode
   test suites must be exported differently or accepted as red), or a *relation callable
   in any mode* (→ Option A's helper everywhere, and the readability cost is the price)?
   This design cannot decide that; §1's evidence is that the corpus's own domain tests
   exercise both.
4. **Option A is the right fallback, not the right default** — it is the only construct
   that is correct without knowing the mode, so it belongs exactly where the analysis
   gives up, and nowhere else.
5. **Option C should ship as a flag, not as strict-mode's default.** Turning it on
   inside `strict=True` silently re-scores the ratchet, and the ratchet is how the
   pilot measures progress; conflating "this construct has no ISO equivalent" with
   "this construct's mode could not be proven" would make `clean 648` mean two things.

Explicitly **not** recommended: keeping `_is_arith_operand` as the decision procedure in
any form. It answers a question ("is this syntactically arithmetic?") that is not the
question being asked ("what is bound here, and of what type?"), and §1.6's chain path
shows what happens where even that guess is skipped.

---

## 5. What pins this behaviour today

The brief's premise was that **no** engine test pins either behaviour. **Re-derivation
contradicts that, and the correction matters.** Four assertions pin it:

| test | file:line | asserts |
|---|---|---|
| `test_structural_eq` | `tests/test_prolog_emit.py:362-366` | `'Same(X, Y) <- (X == Y)'` emits `X == Y` |
| `test_structural_neq` | `tests/test_prolog_emit.py:368-372` | `'Diff(X, Y) <- (X != Y)'` emits `X \== Y` |
| `test_comparison_operators` | `tests/test_prolog_emit.py:350-354` | `'Check(X, Y) <- (X >= Y)'` emits `X >= Y` |
| `test_lte_becomes_prolog_lte` | `tests/test_prolog_emit.py:356-360` | `'Check(X, Y) <- (X <= Y)'` emits `X =< Y` |

A fifth, `test_F032_arith_eq_roundtrip`
(`tests/audit_2026_07_05/test_11_modules_interop.py:595-599`), asserts
`"=:=" in back or " is " in back` — deliberately disjunctive, so it stays green under
either lowering and pins nothing.

Two things about those four, both verified this session:

- **Every one is a text-shape assertion.** None loads the emitted program, none runs it,
  none checks a binding. So the accurate statement is: *the current emission is pinned;
  the current **behaviour** is pinned by nothing.* Changing the lowering will turn four
  tests red, and those four turning red is not evidence of a regression — it is the
  whole of what they measure.
- **Every one carries a `# nv` marker**, which per `scripts/test_audit/annotate_py.py:1`
  means "needs verification" — an audit backlog marker for tests never human-checked.
  `test_structural_eq`'s *name* asserts a semantics (`structural`) that
  `nodes.py:655-663` explicitly forbids for this operator.

For the date-ordering half (§6), the search is clean: `grep -rn "date_before\|@<\|type_error(evaluable"
tests/ --include='*.py'` returns only `@<` **parser/operator-table** tests
(`tests/test_prolog_fix_review.py:154`,
`tests/audit_2026_07_05/test_11_modules_interop.py:496-500`) and nothing about date
lowering. **No engine test exercises an ordering comparison with date operands, in
emission or in behaviour.** Note the consequence for §6.4 D1: the two ordering tests in
the table above (`test_comparison_operators`, `test_lte_becomes_prolog_lte`) use bare
variables with no type information, so a type-aware lowering that keeps `>=` / `=<` for
numeric and unknown operands leaves them **green** — unlike the `==` fix, the date fix
can land without turning any existing assertion red.

---

## 6. Date-term ordering — the same defect, one type-shape further out

### 6.1 The defect

`_convert_compare`'s `Lt` / `LtE` / `Gt` / `GtE` cases
(`clausal_to_prolog.py:1201-1213`) emit `<` / `=<` / `>` / `>=` unconditionally, with no
operand check at all — not even the `_is_arith_operand` shape guard that `Eq`/`NotEq`
get. Clausal's `date` values are real `datetime.date` objects and are natively orderable;
`clausal/modules/py/datetime.py:43-50` states the contract:

> `date`, `time` and `datetime` values are orderable with the standard comparison
> operators `<`, `>`, `<=`, `>=` … Comparing two values that are not orderable against
> each other (`date` vs `datetime`, naive vs tz-aware `datetime`, `date` vs a number)
> raises a catchable `error(type_error(orderable, Culprit), (<)/2)`.

Confirmed live on the engine (Python driver stdout; the exception text is the engine's):

```
CLAUSAL sif("virtual_asset", date(2026,9,2)) -> succeeds
CLAUSAL sif("real_estate",   date(2026,1,1)) -> fails
CLAUSAL mixed(date(2018,4,3), 42) -> raises LogicException Uncaught logic exception:
    Compound(functor='error', args=(Compound(functor='type_error', args=('orderable', 42)), '(<)/2'))
```

### 6.2 Witness, re-derived and run

`/workspace/clausify-domains/au/aml_ctf/reporting_entity_obligations.clausal:257-259`:

```
service_in_force(CATEGORY, QUERY_DATE) <- (
    status_commencement(CATEGORY, COMMENCEMENT_DATE),
    COMMENCEMENT_DATE <= QUERY_DATE
)
```

`COMMENCEMENT_DATE` is bound by a fact table in the same file (`:112-130`,
`status_commencement("virtual_asset", date(2018, 4, 3))` and 9 siblings). Emitted
(`.pl` lines 37, 145-147):

```prolog
status_commencement("virtual_asset", date(2018, 4, 3)).
%  ... 9 sibling facts elided ...
service_in_force(Category, Query_date) :-
    status_commencement(Category, Commencement_date),
    Commencement_date =< Query_date.
```

In Scryer, on exactly that emitted text (saved as `date_witness.pl`, the two facts above
plus the clause):

```
$ printf 'service_in_force("virtual_asset", date(2026,9,2)).\n' | scryer-prolog date_witness.pl
   error(type_error(evaluable,date/3),(is)/2).
```

Task 6's §7 quoted this witness and this error term; **both reproduce exactly.**

### 6.3 Inventory

Two independent passes over the same 765 files, on the emitted Prolog:

**Pass 1 — data-flow.** A variable is date-typed if it is unified with a `date(…)`
compound, or occupies a date-typed argument of a `date_time` predicate (argument
positions taken from `clausal/modules/py/datetime.py`: `date_add/3` args 1,3;
`date_sub/3` 1,3; `date_diff/3` 1,2; `days_between/3` 1,2; `date_between/3` 1,2,3;
`date_max/3`, `date_min/3` 1,2,3; `weekday/2` 1; `date_of/2` 2; `today/1`, `now/1` 1),
propagated interprocedurally to a fixpoint over head-argument positions.

| emitted | goals | files |
|---|---:|---:|
| `<`  | 5 | 4 |
| `=<` | 2 | 2 |
| `>`  | 1 | 1 |
| `>=` | 3 | 3 |
| **total** | **11** | **7** (6 non-test) |

**Pass 2 — name heuristic** (both operand names mention `date`, no data-flow evidence):
**26 further goals in 10 files, all 10 non-test**.

**Union: 11 non-test files**, in 11 distinct domain directories:

```
au/aml_ctf/reporting_entity_obligations.clausal
au/corps_act_disclosure/classification.clausal
au/firb/notifiability.clausal
au/merger_clearance/threshold.clausal
eu/procurement/common/thresholds.clausal
eu/procurement/contract_termination/contract_termination.clausal
eu/procurement/electronic_auction/electronic_auction.clausal
eu/procurement/exclusion_grounds/exclusion.clausal
eu/procurement/framework_agreements/framework_agreements.clausal
eu/procurement/light_regime/light_regime.clausal
eu/procurement/selection_criteria/selection_criteria.clausal
```

This **corroborates Task 6's "at least 9 non-test files" and raises it to 11** — the
data-flow pass finds `eu/procurement/common/thresholds.clausal`
(`As_of_date >= Period_start`, `As_of_date < Period_end`) which a `*DATE*`-name grep
misses, and drops `au/corps_act_disclosure/deadline.clausal`, whose `Diff >= 0` and
`Diff < 0` compare the **integer** output of `date_diff/3`, not a date. Both figures are
lower bounds: a date reaching a comparison through a generic accumulator variable is
invisible to both passes.

Note the shape difference from §1: date ordering **raises loudly** at G3 rather than
failing silently. It is the less dangerous of the two defects for that reason, and the
cheaper to detect.

### 6.4 Options

**D1 — type-aware lowering to companion predicates.** When both operands are provably
date terms, emit `date_before(A, B)` / `date_not_after(A, B)` / … against
`tools/iso_export/companion/clausal_dates.pl`, which already carries the ordinal
machinery this needs (`to_ordinal/2` at line 116, guarded by a cut-free `valid_date/3`).

- *Correctness:* exact where the type is proven, including the invalid-date case, since
  `to_ordinal/2` already fails rather than raising or succeeding wrongly.
- *Coverage:* the fixpoint above proves 11 of ~37 candidate goals. The other ~26 need
  either a stronger analysis or the source to say so.
- *Cost:* requires a coordinated change in a **different repo** — `clausal_dates.pl`
  would gain 4 exports and `COMPANION_SIGNATURES["date_time"]` would need them added.
  The engine cannot land this alone.
- *Tests to pin it:* `A is date(2020,1,1), B is date(2021,1,1), A < B` emits
  `date_before(A, B)`; a numeric `X < Y` still emits `<`; a mixed/unknown case takes the
  chosen fallback; a Scryer-execution row for each of the 4 operators across a
  year/month/day boundary.

**D2 — map to standard order `@<` / `@=<` / `@>` / `@>=`.** Tempting, because for
ground `date/3` terms with integer components, standard order **is** chronological
order — verified in Scryer, no consulted file needed:

```
$ printf 'date(2018,4,3) @< date(2026,3,31).\ndate(2007,12,12) @< date(2007,2,1).\ndate(2007,2,1) @< date(2007,12,12).\n' | scryer-prolog
   true.
   false.
   true.
```

It is nonetheless the wrong answer, for three separately verified reasons:

```
$ printf 'date(2018,4,3) @< 42.\ndate(2018,4,3) @< date(2018,4,X).\n2 @< 1.5.\n1.5 @< 2.\n' | scryer-prolog
   false.
   false.
   false.
   true.
```

1. **Mixed date/number gives an answer where Clausal raises.** `date(…) @< 42` fails
   (numbers precede compounds in standard order); the engine raises
   `type_error(orderable, 42)`. Turning a raise into a silent `false` is the exact
   failure mode this whole document exists to stop.
2. **Partially instantiated dates compare by variable age, not by calendar.**
   `date(2018,4,3) @< date(2018,4,X)` fails because an unbound `X` precedes `3` in
   standard order. Clausal supports partially-instantiated dates on purpose
   (`_DatePattern`, `clausal/modules/py/datetime.py:115-122`).
3. **`@<` cannot be applied unconditionally**, because it breaks numbers: the last two
   answers show `2 @< 1.5` false and `1.5 @< 2` true, since standard order sorts all
   floats before all integers regardless of value — the opposite of `<` on those
   operands. So D2 still needs the same type analysis D1
   needs, and then buys nothing D1 does not buy more correctly.

**D3 — runtime-dispatching companion `clausal_lt/2` &c.** Mirror the engine at call
time: both numbers → `<`; both `date/3` → compare ordinals; otherwise raise
`type_error(orderable, Culprit)` with context `(<)/2`. Same trade as Option A in §3 —
no analysis needed, exact error reproduction, worst readability, and it would rewrite
**all 486 emitted ordering goals** (110 `<` + 89 `=<` + 113 `>` + 174 `>=`) to carry a
type check that ~475 of them do not need.

**D4 — refuse under strict.** Raise `UntranslatableConstructError` when an ordering
comparison's operands cannot be proven numeric. Same shape as Option C, at a much lower
cost here: 11 non-test files rather than 71, and unlike §3 the defect is loud at
runtime anyway, so refusing at translation time buys mainly *earlier* detection.

### 6.5 Date recommendation

**D1 for the proven cases, D4 for the rest, D3 not at all, D2 never.**

The date half is genuinely easier than the `==` half and should not be bundled with it:
the type lattice is two-valued (number / date) where §3's mode lattice is not; the
failure is loud where §1's is silent; and the affected surface is 11 files rather than
71. D1's coverage gap is real but it fails *safe* — an unproven operand pair goes to D4
and refuses, which is exactly the behaviour the standing fail-fast ruling asks for, and
it never emits a comparison that silently answers.

D2 is listed only because it looks right on the three chronological rows above and is
wrong on three others; it is recorded here so nobody re-derives the tempting half
without the disqualifying half.

The cross-repo dependency (§6.4 D1) means the engine-side commit and the
`clausal_dates.pl` commit have to be sequenced, and the engine one cannot go first
without leaving the export emitting calls to predicates that do not exist.

---

## 7. Summary of what this re-derivation changed

| claim | source | re-derived verdict |
|---|---|---|
| `==` maps by operand shape to `=:=` / `==`, both test-only | pilot §5.1 | **confirmed**, `clausal_to_prolog.py:1130-1144, 1191-1199` |
| `uk/tax` `liability.clausal:133,169,217` witnesses | pilot §5.1 | **confirmed**, plus `:148, 155, 156, 163, 188, 196, 209` |
| `us/tax/irc_s1` is a second instance | pilot §5.1 | **confirmed** — 11 emitted goals, `.pl:103,109,134,138,143,147,151,157,163,180,185` |
| `liability.clausal:163` (`ALLOWANCE == 0`) | — | **new witness**, not in the triage doc |
| the defect is only about binding mode | pilot §5.1 | **narrower than the truth** — §1.5, 429 further goals diverge on numeric type even fully bound |
| Clausal `==` is "evaluate-and-bind" | pilot §5.1 | **imprecise** — it is a CLP(FD) equality constraint with a documented 7-row behaviour (§1.2), including a raise |
| Clausal `is/2` is the opposite of ISO `is/2` | memory note | **confirmed with correction** — Clausal `is` ≈ ISO `=`; the ISO-`is` role is played by `==`, not by `eval_`, which the corpus uses 0 times |
| NO engine test pins either behaviour | brief | **false as stated** — 4 assertions pin the *emission* (§5); none pins the *behaviour*, and all 4 are `# nv`-marked |
| date ordering raises `type_error(evaluable, date/3)` | task-6 §7 | **confirmed**, reproduced in Scryer on the emitted `au/aml_ctf` text |
| "≥9 non-test files" carry date ordering | task-6 §7 | **raised to 11 non-test files / 11 domains**, by data-flow rather than name grep |

---

Awaiting operator review.
