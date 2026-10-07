# clausal-laya — wrapper plan and record (2026-10-06)

Written to [EXTERNAL_WRAPPER_CHECKLIST.md](../EXTERNAL_WRAPPER_CHECKLIST.md).
Phase 1 is implemented: `packages/clausal-laya/` (adapter
`clausal/modules/py/laya.py`, docs `docs/laya.md`, tests).

## 1. Core abstraction

laya (`pip install laya`, 0.3.28) is a non-autoregressive "System 1"
decision engine. Its unit of work is a **decision**: a state (a text) and a
dict of typed questions, answered in one forward pass with calibrated
probabilities. A `laya.Router` routes each text to a checkpoint (`english`,
`multilingual`, `typed-decisions`, or one the caller registers), downloading
it from the Hugging Face Hub on first use. Three question types (`QTYPES`):

| Type | Criteria | Answer |
|---|---|---|
| `choice` | labels (list) or label → description (dict) | `choice`, `probabilities` per label |
| `score` | ordered level descriptions | `score` (expected level), `probabilities` per level |
| `noul` | none | `noul` = P(yes) |

Each answer also carries `confidence`, `answer_confidence` (calibrated,
comparable across types), `action` diagnostics, and `low_confidence` when a
`min_confidence` gate flags it.

The wrapper models one lifecycle: a process-wide router built lazily; every
predicate is one forward pass.

## 2. Bijective map

None. Inference is one-way (text → answers). The relational value is
**enumeration**: a probability distribution over options becomes a
nondeterministic predicate (`choice/5`, `score/5`) whose solutions are the
options, most probable first, each with its probability.

## 3–4. Purity and tiers

For a fixed checkpoint, inference is a function of its inputs: every
predicate is **pure** and safe to backtrack over. Tier 1 (pure), with a
cached heavyweight resource (the router) behind it. Downloading the
checkpoint is a first-use side effect laya owns.

## 5. Scope

**In (phase 1):** `choice/4,5`, `noul/3`, `score/4,5` (one question each, the
common case and the one that composes with logic); `predict/3,4` (several
questions in one forward pass, laya's own question dicts, options `model`,
`lang`, `max_len`, `min_confidence`).

**Out:** hooks (`on_predict_start`/`end`), the HTTP and MCP servers, ONNX and
TileLang backends, LangChain/LlamaIndex/CrewAI integrations, fine-tuning
(`laya-train`), evaluation (`laya-evals`) — tools around the model, not
decisions; reachable with `++` where needed.

**Deferred:**
- `predict_tournament` for `choice` questions with more labels than the
  option budget (16).
- `predict_long` and the shortlist API.
- Schema-driven `decide` (JSON schema / pydantic models).
- A `library(laya)` facade for Clausal Prolog: no extension package ships
  facades yet (`todo/package-adapters-need-library-facades-2026-10-01.md`);
  `.clausal` code reaches laya through a `python_bridges` `.seam` module.

## 5b. `++` escapes

None in typical use: labels are the caller's own terms (answers unify with
them), probabilities are floats, answers are dicts read with `dict_get/3`.

## 5c. Quantities, 5d. registries

No quantities (probabilities are dimensionless). No registry: the checkpoint
names are laya's, passed as option values.

## 6. Term language

- `Text`, `Instructions`: text (atom or string).
- `Labels`: a list of labels, or a dict label → description; a label is an
  atom, a string or a number. Answers return the label **term the caller
  wrote** (the adapter keys laya by the label's text and maps back).
- `Levels`: a list of level descriptions; a level in an answer is its 0-based
  index.
- `Answers` (`predict`): dict question id (the caller's term) → answer dict
  with atom keys `type`, `choice`/`score`/`noul`, `probabilities`,
  `confidence`, `answer_confidence`, `low_confidence`; laya's `action`
  diagnostics are dropped.

## 7. Predicate catalogue

| Predicate | Modes | Det | Description |
|---|---|---|---|
| `choice(+Text, +Instr, +Labels, ?Label)` | | det | most probable label |
| `choice(+Text, +Instr, +Labels, ?Label, ?P)` | | nondet | every label with P, most probable first |
| `noul(+Text, +Instr, ?P)` | | det | P(yes) |
| `score(+Text, +Instr, +Levels, ?Score)` | | det | expected level (float) |
| `score(+Text, +Instr, +Levels, ?Level, ?P)` | | nondet | every level with P, most probable first |
| `predict(+Text, +Questions, ?Answers)` | | det | several questions, one pass |
| `predict(+Text, +Questions, +Options, ?Answers)` | | det | with options |

Errors raise (ruled 2026-10-02): `instantiation_error`,
`type_error(text|list|dict|laya_label, C)`,
`domain_error(non_empty_list|laya_question, C)`.

## 9. Showcase

`packages/clausal-laya/tests/fixtures/docs/laya_examples.seam` (route a
ticket by the model's choice, keep every team at least 20% likely, escalate on
a churn threat, several questions in one pass) — the examples in
`docs/laya.md`.

## 10. Tests

- `tests/test_laya_adapter_stubbed.py` — the adapter against a fake router in
  laya's payload shape: label mapping, ranking, options, errors, and the seam
  surface (`tests/fixtures/laya_stubbed.seam`, run through `run_file`). Runs
  without laya, torch or a checkpoint.
- `tests/fixtures/laya_basic.seam`, `tests/fixtures/docs/laya_examples.seam` —
  the real model; `tests/conftest.py` skips them, naming the error, when the
  checkpoint cannot load.
- `tests/test_laya_doc_integrity.py` — the docs' snippet references.

## Phase 2 (2026-10-06): backends, batching, fine-tuning

**Which API layer.** laya's layers, top down: `Router.predict` /
`Router.predict_batch` (language routing, checkpoint load/evict) ->
`Agent.system_one` / `Agent.predict_batch` (tokenising, option rendering,
temperature and histogram calibration -- ~2,000 lines of `agent.py`) ->
`DecisionModel` (the torch `nn.Module`, raw logits).  laya's own
integrations (LangChain, LlamaIndex, CrewAI, MCP) all end at
`runner.predict(state, questions)` or a POST to `laya-serve`
(`laya/integrations/_controls.py`); none goes to torch.  Calling
`DecisionModel` directly would mean re-implementing the calibration the
probabilities rest on.  The adapter therefore uses `Router.predict_batch` for
everything: it groups requests by checkpoint and question set and runs
`Agent.predict_batch`, sharing forward passes -- the most efficient public
layer, and a stable one (documented, used by laya-serve itself).  A single
question is a batch of one.

**Backends.** The protocol -- state + typed questions (`choice`, `score`,
`noul`) -> answers with probabilities -- is TypeSafe's "System One"; laya is
an open model of it, and TypeSafe's hosted Jev serves it through
`typesafe-sdk` (`TypeSafeClient.system_one`, answer models with the same
fields; `NoulAnswer` carries no confidence).  So the predicates run on a
process-wide backend, `use_backend/1,2`: `laya` (in-process
`Router.predict_batch`), `laya_serve` (`/v1/systemone/batch`, one POST per
question set), `typesafe` (one `system_one` call per text; `model` is its
only control).  A backend's options become per-call defaults.

**Batching.** `predict_batch/3,4` exposes the batch path: the same questions
over many texts.

**Fine-tuning.** `finetune/5` wraps `laya.train.finetune` (train, fit
temperatures, save): rows (`{state, questions, expected}`, the
laya-train JSONL schema) or a JSONL/CSV path; `TrainConfig` fields as
options; the base resolved by `resolve_checkpoint_dir` (built-in names, Hub
ids, directories).  `register_model/2` is `Router.register`, so the result
answers under `{"model": Name}`.  Rows can be built from facts: symbolic
labels supervising the neural predicate.  Tier 4 (IO), like `use_backend`.

**Tests.** The stubbed tests now drive the real `_LayaBackend` with a fake
`Router.predict_batch`; `laya_serve` against a real local HTTP server;
`typesafe` through the real SDK over an `httpx2.MockTransport` (skipped
without the SDK); `finetune` against a stand-in `laya.train` (training needs a
real checkpoint).

## Issues

- **Jev not run against the real service either**: no `TYPESAFE_API_KEY`
  here.  The SDK round trip is tested over a mocked transport, with the
  response shape from the SDK's own models (`ChoiceAnswer`, `NoulAnswer`,
  `ScoreAnswer`).
- **`finetune/5` not run end to end**: it needs a downloadable base
  checkpoint and real training time.  Its argument handling (rows to JSONL,
  `TrainConfig`, device, the summary) is tested against a stand-in.
- **Not run against the real model here.** The development sandbox could not
  reach huggingface.co, so the real-model fixtures were verified only against
  fake routers: one in laya's payload shape (everything but the two
  README-specific assertions passes), and one that favours the first label
  (all pass). Their only model-dependent claims are laya's own README example
  (a double-billing complaint routes to `billing` and is a churn threat).
  First thing to check on a machine with Hub access:
  `python -m pytest packages/clausal-laya`.
- **Two hand-synced alias tables.** The bare name `laya` had to be added to
  both `_IMPORT_ALIASES` (`clausal/templating/term_rewriting.py`) and
  `_MODULE_ALIASES` (`clausal/logic/compiler_v2.py`); with only the first, the
  import compiled to `clausal.modules.py.laya` but the compiler resolved
  `laya` to the Python library. No test checks the two tables agree.
- **The released engine (1.0.0) has no `laya` alias**, so a bare
  `-import_from(laya, ...)` there imports the Python library. The package's
  docs and tests therefore use `-import_from(py.laya, ...)`, which works on
  every engine from 1.0; found by running the tests against the built wheel
  as `packages-release.yml` does, where `uv` resolved `clausal>=1.0` to the
  PyPI release.
- `dict_get/3` takes the key FIRST (`dict_get(Key, Dict, Value)`); the first
  draft of the fixtures had it reversed.
