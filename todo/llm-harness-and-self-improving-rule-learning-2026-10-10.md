# An LLM harness on Clausal, and what to build with it

Written to be broken out into separate todos. Nothing here is ruled or
started. Sections H1-H3 are the harness itself; U1-U6 are uses of it; S1
is the self-improving loop.

## Background: DeepClause

`github.com/deepclause/deepclause-sdk` (MIT; read at 1a5338f9, 2026-10-09,
branch `feat/dml-repl` not yet merged there) is a "Prolog-based runtime
for self-modifying agent harnesses":

- TypeScript CLI and SDK around SWI-Prolog compiled to WebAssembly. Its
  language, DML, is SWI Prolog plus LLM predicates (`task/N`, `prompt/N`,
  `exec/2`, `system/1`, `user/1`, `with_tools/2`).
- User code runs under a meta-interpreter (`mi_call/3` in
  `deepclause_mi.pl`) that threads `state{memory, params, gas_remaining}`.
  An LLM call is an `engine_yield(request_agent_loop(...))` that the host
  answers. Conversation memory is in the threaded state, so backtracking
  undoes `system/1` and `user/1`.
- **The harness idea:** a harness is one live module in which skills, tools,
  memory and workflow are all predicates. An authoring agent edits it in
  transactions: `begin_turn`, then `define`/`assert`/`execute`, then
  `end_turn`. A failed turn restores the snapshot, and `rollback` steps back
  one version. A commit replaces whole predicates, and history is queryable
  as `harness_change/5`, `harness_turn/5`, ... `export` writes a plain
  file that another harness loads as its baseline.
- **Judgments** `choose`, `rate`, `verify` (`yes`/`no`/`unknown`) and
  `probability` take explicit state and no memory, and are memoised per run
  so that backtracking reuses an answer instead of re-sampling.

### Overlaps

| DeepClause | Clausal today |
|---|---|
| An LLM call pauses the meta-interpreter | `clausal.aio.asolve` + `async_predicate`: a compiled goal awaits an asyncio LLM SDK directly, no meta-interpreter (experimental, not 1.0 API) |
| Tool scoping, workspace confinement, bwrap/AgentVM for `bash` | `clausal.sandbox.enable()`: built goals reach only whitelisted `.seam` predicates; `seam_audit` decides at load time from the compiler's view |
| `verify` answers `unknown` | Kleene truth values and WFS `undefined`, which carry meaning through a proof |
| Memoised judgments | Tabling, if an answer becomes a tabled fact |
| `listing`/`export` reverse a load-time rewrite | reified-term renderer, `clausal-fmt`, `clausal-rewrite` |
| Agent edits predicates in a live module | `op_node/3`, `replace_subterm/4` exist; no auditor built on them |
| CLP(FD/Q/R) in skills | CLP(Q) is the default arithmetic; CLP(Z), CLP(B), units, Decimal |
| `gas` budget, `call_with_inference_limit/3` | nothing equivalent (gap, see H3) |

### Not a port

DML is SWI-shaped: SWI dicts and `D.x`, `key: value` arguments,
`format(string(S), ...)` with `"..."` as an SWI string, cut, `->`,
`once/1`. Clausal is cut-free ISO with ISO, then Scryer, as the
references, so a DML compatibility layer means building an SWI dialect. Not
recommended. Using Clausal as DeepClause's engine is a poor fit too: the
host is TypeScript/WASM and the interpreter is SWI code.

Cheapest experiment, no Clausal change: a DeepClause skill calls a Clausal
rulebase through `exec(bash(command: "clausal ..."))`.

## H1. LLM calls as async adapters

`task/2`-style predicates as `async_predicate` adapters under `asolve`.
Open: the typed-output shape (a domain, a CLP constraint, or a term
check); where conversation memory lives, if anywhere (DeepClause backtracks
it with the state).

## H2. Living module with transactions

Snapshot, edit predicates, test with goals, commit replace-by-predicate,
rollback, history as facts, export through the formatter. The edited
module loads under sandbox mode, so a committed skill can only reach
whitelisted adapters. Open: where the snapshot lives; whether a commit
must pass a recorded-case gate (S1 needs that).

## H3. Bounding a goal

An inference or step budget per goal (DeepClause has gas and
`call_with_inference_limit/3`). Clausal has none; a harness running
model-written rules needs one. ISO has no standard form; check Scryer's
`call_with_inference_limit/3` first.

## Uses

- **U1. Decisions that explain "what would change the answer."** With an
  input left unbound, CLP(Q) returns a residual condition
  (`{Income >= 31200}`) and an LLM phrases it. The logic stays exact.
  Strongest demo.
- **U2. Policy gate for AI agents.** Each proposed tool call becomes a goal
  against a policy rulebase in sandbox mode. True: allow, keeping the proof as
  the audit record. False: deny. Undefined: escalate to a human. The model
  cannot widen its own permissions. Suggested first build: U2 with U1's
  "allowed if ..." answers.
- **U3. Rulebases drafted from text, one transaction at a time.** A rule is
  committed only if recorded cases still pass. Genuine ambiguity is
  `undefined`, and each one is a precise question for a human. Output exports
  to Scryer.
- **U4. Units- and money-safe extraction.** LLM-extracted figures compute
  under units, currency and exact rationals, so nonsensical combinations
  raise instead of combining silently.
- **U5. Scheduling and planning.** Constraints from plain language to CLP;
  when under-specified, the residual says which question to ask next.
- **U6. Rules that improve under a regression gate.** The agent proposes
  rewrites with `op_node/3`/`replace_subterm/4`; a rewrite lands only if
  every recorded case answers the same.

## S1. Self-improving symbolic learning

The loop: the LLM proposes a rule, rewrite or helper predicate; recorded
cases, constraints and proofs check it; a transaction commits it only on
improvement with no regression; failures come back as feedback. Prior art:
ILP (Progol, Aleph, Metagol's meta-interpretive learning), DreamCoder's
library learning, and neural-proposer/symbolic-checker systems
(AlphaGeometry, FunSearch, the Darwin Goedel Machine).

Every level is clauses: knowledge (rules), skills (a growing helper
library), strategy (which rule to try, which question to ask) and the
harness (prompts, policies, tool scopes). So the system can rewrite how it
improves, not only what it knows.

What Clausal adds:
- Cut-free clauses: "this rewrite kept behaviour" is checkable on recorded
  cases.
- Feedback beyond pass/fail: CLP(Q) residuals locate where a rule fails, and
  WFS `undefined` separates missing knowledge from wrong knowledge.
- Tabling + WFS: self-referential rules give `undefined` instead of
  hanging.
- Sandbox mode keeps the evaluator out of the improver's reach.
- Export to Scryer: confirm an improvement on a second engine, so the loop
  cannot learn to exploit a Clausal bug.

**The checker sets the ceiling.** The easiest way to raise a score is to
weaken the test, so the held-out cases must be outside the system's write
access. Where answers cannot be checked, the loop drifts rather than
improves. The LLM stays the source of new hypotheses.

First experiment: learn a rulebase from a few hundred labelled cases, 30%
held out and unreadable to the learner. Per round, measure held-out
accuracy, rule-set size, and whether the helper library makes later rounds
faster. Success = round-over-round held-out gains with no hand-tuning.
