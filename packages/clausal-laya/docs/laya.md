# laya — calibrated decisions as relations

[laya](https://pypi.org/project/laya/) is a non-autoregressive "System 1"
decision engine. Given a text and a set of typed questions, one forward pass
answers all of them with calibrated probabilities, in 100+ languages. The
`laya` module makes those answers **relations**: a neural predicate whose
solutions carry probabilities, which ordinary logic can then filter, rank and
combine.

```seam
--8<-- "tests/fixtures/docs/laya_sigs.txt:import"
```

With this engine release or later, the bare name works too:
`-import_from(laya, [...])`. (A bare `laya` is otherwise the Python library
itself.)

The predicates run on a swappable [backend](#backends): the open laya model
in this process (the default), a `laya-serve` server, or TypeSafe's hosted
Jev model, which answers the same typed questions.

---

## Question types

laya answers three kinds of question, and each has a predicate:

| Type | Predicate | Answer |
|------|-----------|--------|
| `choice` | `choice/4,5` | one label of a set, with a probability per label |
| `noul` | `noul/3` | the probability that the answer is yes |
| `score` | `score/4,5` | a level on an ordered scale, with a probability per level |

`Text` and `Instructions` are text: an atom or a string. Labels are atoms,
strings or numbers, and an answer names a label by the **term you wrote**, so
it unifies with your own atoms.

---

## `choice/4`, `choice/5`

```
--8<-- "tests/fixtures/docs/laya_sigs.txt:choice_sig"
```

`Labels` is a non-empty list of labels, or a dict from label to a description
the model reads. `choice/4` answers the most probable label. `choice/5`
enumerates every label with its probability, most probable first; with
`Label` bound it gives that label's probability.

```seam
--8<-- "tests/fixtures/docs/laya_examples.seam:route"
```

---

## `noul/3`

```
--8<-- "tests/fixtures/docs/laya_sigs.txt:noul_sig"
```

`P` is the probability that the answer to the yes/no question is yes.

```seam
--8<-- "tests/fixtures/docs/laya_examples.seam:escalate"
```

---

## `score/4`, `score/5`

```
--8<-- "tests/fixtures/docs/laya_sigs.txt:score_sig"
```

`Levels` is a non-empty list of level descriptions, lowest first. `score/4`
answers the expected level, a float from `0` to `len(Levels) - 1`. `score/5`
enumerates every 0-based level with its probability, most probable first.

```seam
--8<-- "tests/fixtures/docs/laya_examples.seam:urgency"
```

---

## `predict/3`, `predict/4`

```
--8<-- "tests/fixtures/docs/laya_sigs.txt:predict_sig"
```

Several questions in **one** forward pass. `Questions` is a dict from a
question id to a question written as laya writes one: `type`, `instructions`
and, for `choice` and `score`, `criteria`. `Answers` is a dict from your
question ids to answer dicts with these keys:

| Key | Value |
|-----|-------|
| `type` | `choice`, `score` or `noul` |
| `choice` / `score` / `noul` | the answer: your label term, the expected level, or P(yes) |
| `probabilities` | label → P (`choice`) or level → P (`score`) |
| `confidence` | laya's per-type confidence |
| `answer_confidence` | the calibrated confidence, comparable across types |
| `low_confidence` | present (`True`) when `min_confidence` flagged the answer |

`Options` may hold `model` (`english`, `multilingual`, `typed-decisions` or a
checkpoint you registered with laya), `lang`, `max_len` (up to `8192` for long
documents with the multilingual checkpoint) and `min_confidence`. Read answers
with `dict_get/3`.

```seam
--8<-- "tests/fixtures/docs/laya_examples.seam:predict"
```

---

## `predict_batch/3`, `predict_batch/4`

```
--8<-- "tests/fixtures/docs/laya_sigs.txt:predict_batch_sig"
```

The same `Questions` over a list of texts, answered together: the local
backend groups them into shared forward passes (laya's `predict_batch`), and
`laya_serve` sends one request. `AnswersList` holds one `Answers` dict per
text, in order. Prefer it to `findall` over `predict/3` when there are many
texts.

```seam
--8<-- "tests/fixtures/docs/laya_examples.seam:predict_batch"
```

---

## Backends

```
--8<-- "tests/fixtures/docs/laya_sigs.txt:backend_sig"
```

| Name | Answers with | Options |
|------|--------------|---------|
| `laya` (default) | the open model in this process, through `laya.Router.predict_batch`; the checkpoint downloads from the Hugging Face Hub on first use | the call options below |
| `laya_serve` | a `laya-serve` HTTP server (`/v1/systemone/batch`) | `url` (required), `api_key`, `timeout`, and the call options |
| `typesafe` | TypeSafe's hosted Jev model, through `typesafe-sdk` (`pip install "clausal-laya[typesafe]"`, `TYPESAFE_API_KEY`) | `api_key`, `base_url`, `timeout`, `model` |

The call options -- `model`, `lang`, `max_len`, `head_max_len`,
`min_confidence` -- given to `use_backend/2` become the defaults for every
call; a `predict/4` or `predict_batch/4` call's own options override them.
`typesafe` takes `model` only. `backend/1` names the backend in use. The
backend is process-wide state: choose it once, when the program starts.

```seam
-private([laya_serve])

use_server(URL) <- use_backend(laya_serve, {"url": URL, "model": "multilingual"})
```

---

## Fine-tuning

```
--8<-- "tests/fixtures/docs/laya_sigs.txt:finetune_sig"
```

`finetune/5` runs laya's own fine-tuning (`laya.train.finetune`): it trains
`Base` (a built-in name such as `english`, a Hub repo id, or a checkpoint
directory) on `Data`, fits the calibration temperatures, and saves the
checkpoint to `OutputDir`. `Data` is a list of rows -- dicts with `state`,
`questions` and `expected` (question id -> the right answer) -- or the path of
a JSONL or CSV file in laya-train's formats. `Options` takes laya's
`TrainConfig` fields (`epochs`, `micro_batch`, `encoder_lr`, ...) and `device`.
`Summary` is a dict: `train_items`, `calibration_items`, `epoch_loss`,
`temperature`, `output_dir`.

`register_model/2` serves a checkpoint under a name, beside the built-ins, so
`{"model": Name}` selects it. Training labels can come from the program's own
facts: symbolic knowledge supervising the neural predicate.

```seam
-private([billing, technical, other])

labelled(TEXT, TEAM) <- (in_([TEXT, TEAM], [["Charged twice", billing],
                                             ["The site is down", technical]]))

row(ROW) <- (
    labelled(TEXT, TEAM),
    ROW is {"state": TEXT,
            "questions": {"team": {"type": "choice",
                                   "instructions": "Which team handles this?",
                                   "criteria": [billing, technical, other]}},
            "expected": {"team": TEAM}}
)

retrain(DIR) <- (
    findall(ROW, row(ROW), ROWS),
    finetune(ROWS, "english", DIR, {"epochs": 2}, _),
    register_model("tickets", DIR)
)
```

Fine-tuning needs the local `laya` backend's dependencies (torch) and a
checkpoint to start from; `register_model/2` works on the `laya` backend only.

---

## Errors

The predicates raise ISO errors rather than fail:

| Problem | Error |
|---------|-------|
| `Text`, `Instructions`, `Labels` or `Questions` unbound | `instantiation_error` |
| `Text` or `Instructions` not text | `type_error(text, Culprit)` |
| `Labels`/`Levels` not a list (or dict) | `type_error(list, Culprit)` |
| an empty `Labels`/`Levels` | `domain_error(non_empty_list, [])` |
| a label that is not an atom, string or number | `type_error(laya_label, Culprit)` |
| `Questions` or `Options` not a dict | `type_error(dict, Culprit)` |
| a question the backend refuses (a repeated label, an unknown type) | `domain_error(laya_question, Culprit)` |
| an unknown backend | `domain_error(laya_backend, Name)` |
| an option the backend does not take, or `laya_serve` without a `url` | `domain_error(laya_option, Name)` |
| `register_model/2` off the local backend | `permission_error(modify, laya_model, Name)` |
| a training option laya refuses | `domain_error(laya_train_config, Options)` |
| training data laya cannot use | `domain_error(laya_training_data, Data)` |

A checkpoint that cannot be downloaded raises the Python error laya raises,
catchable with `catch/3`.

---

## Purity

For a fixed checkpoint, inference is a function of its inputs, so the
decision predicates (`choice`, `noul`, `score`, `predict`, `predict_batch`)
are pure and safe to backtrack over: `choice/5` and `score/5` enumerate on
backtracking, and nothing is mutated. `use_backend/1,2`, `register_model/2`
and `finetune/5` change process state or write files; call them at the
program's boundary, not under backtracking.
