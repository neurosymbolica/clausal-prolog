# Phase N-4 — Rule-weight learning *(research ticket)*

**Status: parked.** Not scheduled. This file exists to record the
shape of the open question so a future scope conversation has
something to start from.

---

## The question

Each alternative clause of a predicate gets a learnable scalar
weight. A call's "forward pass" becomes a weighted sum (or softmax)
over the contributions of each alternative. Gradients on the loss
flow through the weights, so training discovers which alternatives
matter. This is the idea DeepProbLog and Scallop both implement,
in different ways.

The Clausal-local question is: **how does this interact with
`PredicateMeta._get_dispatch`?** Specifically:
- Does soft choice replace the hard dispatch function, or wrap it?
- What is the unit being differentiated — a scalar weight per
  clause, or a parameterised function of the query term?
- How do we keep the machinery invisible to predicates that don't
  opt in, so the 99% of code that doesn't want soft choice pays
  nothing?

---

## What would move it forward

1. **A concrete workload.** Something that actually needs weighted
   alternatives — rule learning from data, a theory-induction
   benchmark, a small semantic-parsing task. Without one, design
   decisions about the dispatch API are guesses.
2. **A read of the DeepProbLog and Scallop papers** filtered for
   *what they chose to parameterise*, not the proof-theory
   arguments. The engineering choice of "where the weight lives"
   is the core Clausal-local question.
3. **A prototype in a branch,** not the main compiler. See how
   invasive the changes to `PredicateMeta._get_dispatch` actually
   have to be before deciding whether this is a small addition or
   a fork of the dispatch path.

---

## Why it's parked

The sketch is explicit: this crosses from engineering into research
(`../NEUROSYMBOLIC_PLATFORM_SKETCH.md:78`). None of the platform's
headline claims — homoiconic architectures, call-pretrained-as-goal,
single-predicate differentiable forward — depend on it. Doing it
speculatively, before a workload demands it, risks committing to
an API shape that doesn't fit the real use case.

Revisit when:
- Someone is trying to use Clausal for ILP or rule induction, *and*
- They can articulate what they want to parameterise and why, *and*
- N-3 has landed (otherwise we have no story for the backward pass
  even inside a single predicate).

---

## Related reading

- DeepProbLog (Manhaeve et al., 2018): probabilistic logic
  programming with neural predicates. Weight semantics is
  probabilistic (clause selection probabilities).
- Scallop (Huang et al., 2021 / 2024): provenance semirings,
  differentiable reasoning over a tagged database. A different
  lens on the same problem.
- `clausal/logic/predicate.py` — the `PredicateMeta` machinery
  any implementation has to slot into.

---

## Issues

_To be populated if/when this phase is unparked._
