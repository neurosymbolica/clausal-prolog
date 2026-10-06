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

laya downloads its checkpoint from the Hugging Face Hub on first use and keeps
it in one process-wide router, which picks the English or multilingual
checkpoint for each text.

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
| a question laya refuses (a repeated label, an unknown type) | `domain_error(laya_question, Culprit)` |

A checkpoint that cannot be downloaded raises the Python error laya raises,
catchable with `catch/3`.

---

## Purity

For a fixed checkpoint, inference is a function of its inputs, so every
predicate is pure and safe to backtrack over: `choice/5` and `score/5`
enumerate on backtracking, and nothing is mutated.
