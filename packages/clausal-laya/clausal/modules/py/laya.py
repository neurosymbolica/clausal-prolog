"""clausal.modules.py.laya — laya decision predicates for Clausal.

`laya <https://pypi.org/project/laya/>`_ is a non-autoregressive "System 1"
decision engine: given a text and a set of typed questions, one forward pass
answers all of them with calibrated probabilities.  This module makes those
answers relations -- a neural predicate whose solutions carry probabilities::

    -import_from(py.laya, [choice, noul, score, predict])

Predicates
----------
- ``choice(Text, Instructions, Labels, Label)``      -- the most probable label
- ``choice(Text, Instructions, Labels, Label, P)``   -- every label with its
  probability, most probable first (nondeterministic); with ``Label`` bound,
  that label's probability
- ``noul(Text, Instructions, P)``                    -- the probability the
  answer is yes
- ``score(Text, Instructions, Levels, Score)``       -- the expected level, a
  float between 0 and ``len(Levels) - 1``
- ``score(Text, Instructions, Levels, Level, P)``    -- every 0-based level
  with its probability, most probable first (nondeterministic)
- ``predict(Text, Questions, Answers)`` and
  ``predict(Text, Questions, Options, Answers)``     -- several questions in
  one forward pass, written as laya writes them; ``Options`` holds ``model``,
  ``lang``, ``max_len`` and ``min_confidence``

Terms
-----
``Text`` and ``Instructions`` are text: an atom or a string.  ``Labels`` is a
non-empty list of labels or a dict ``Label -> Description``; a label is an
atom, a string or a number, and answers name a label by the TERM the caller
wrote, so ``choice(T, I, [billing, technical], billing)`` unifies as written.
``Levels`` is a non-empty list of level descriptions, index 0 first.

``Answers`` (``predict``) is a dict ``QuestionId -> Answer``, keyed by the
caller's own question ids.  An answer is a dict with atom keys:
``type`` (``choice``, ``score`` or ``noul``), the answer itself under the
same name as the type (a label term, an expected level, or P(yes)),
``probabilities`` (label -> P, or level -> P; not for ``noul``),
``confidence``, ``answer_confidence`` (calibrated, comparable across types)
and, when ``min_confidence`` flagged it, ``low_confidence``.

Purity
------
For a fixed checkpoint, inference is a function of its inputs, so every
predicate is pure and safe to backtrack over.  The checkpoint is downloaded
from the Hugging Face Hub on first use (laya's own behaviour) and kept by one
process-wide ``laya.Router``.

Errors (RULED 2026-10-02: raise, never fail)
--------------------------------------------
- unbound ``Text``/``Instructions``/``Labels``/``Questions`` ->
  ``instantiation_error``; ``Text``/``Instructions`` not text ->
  ``type_error(text, Culprit)``;
- ``Labels``/``Levels`` not a list (or dict) -> ``type_error(list, Culprit)``,
  an empty one -> ``domain_error(non_empty_list, [])``, a label that is not an
  atom, string or number -> ``type_error(laya_label, Culprit)``;
- ``Questions``/``Options`` not a dict -> ``type_error(dict, Culprit)``;
- a question laya refuses (a duplicate label, an unknown type, ...) ->
  ``domain_error(laya_question, Questions)``.
"""

from __future__ import annotations

import threading as _threading

from clausal.logic.exceptions import LogicException, domain_error, type_error
from clausal.logic.to_python import to_python
from clausal.logic.variables import deref, is_var, unify
from clausal.modules.py import (
    ModulePredicate, expect_type, has_option, option, raise_domain_error,
    require_text, simple_to_trampoline, to_text,
)


# ── The router: one per process, built on first use ──────────────────────

_router = None
_router_lock = _threading.Lock()


def _get_router():
    """The process-wide ``laya.Router``.  laya (and torch) are imported here,
    on first use, so this module imports without them (``*_stubbed.py``)."""
    global _router
    if _router is None:
        with _router_lock:
            if _router is None:
                from clausal.modules.py import _import_stdlib  # noqa: PLC0415
                _router = _import_stdlib("laya").Router()
    return _router


# ── Argument conversion ──────────────────────────────────────────────────

_OPTION_NAMES = ("model", "lang", "max_len", "min_confidence")


def _is_dict(v) -> bool:
    from clausal.terms import DictTerm  # noqa: PLC0415
    return isinstance(v, (dict, DictTerm))


def _label_key(label, pred):
    """The scalar laya keys a label by: its text, or the number itself."""
    text = to_text(label)
    if text is not None:
        return text
    if isinstance(label, (int, float)) and not isinstance(label, bool):
        return label
    raise LogicException(type_error("laya_label", label, f"{pred}: argument 3"))


def _labels(labels, pred):
    """``(criteria, by_key)``: the criteria laya is given, and laya's key ->
    the label TERM the caller wrote."""
    labels = deref(labels)
    if is_var(labels):
        expect_type(labels, list, pred, arg=3)          # instantiation_error
    if _is_dict(labels):
        items = list(labels.items())
        if not items:
            raise_domain_error("non_empty_list", labels, pred, arg=3)
        criteria, by_key = {}, {}
        for label, description in items:
            label = deref(label)
            key = _label_key(label, pred)
            criteria[key] = to_python(description)
            by_key[key] = label
        return criteria, by_key
    expect_type(labels, list, pred, arg=3)
    if not labels:
        raise_domain_error("non_empty_list", labels, pred, arg=3)
    criteria, by_key = [], {}
    for label in labels:
        label = deref(label)
        key = _label_key(label, pred)
        criteria.append(key)
        by_key[key] = label
    return criteria, by_key


def _levels(levels, pred):
    levels = deref(levels)
    expect_type(levels, list, pred, arg=3)
    if not levels:
        raise_domain_error("non_empty_list", levels, pred, arg=3)
    return [to_python(level) for level in levels]


def _options(options, pred):
    """The ``Router.predict`` keyword arguments an options dict names."""
    options = deref(options)
    if not _is_dict(options):
        expect_type(options, dict, pred, arg=3)
    kwargs = {}
    for name in _OPTION_NAMES:
        if has_option(options, name):
            value = deref(option(options, name))
            text = to_text(value)
            kwargs[name] = text if text is not None else to_python(value)
    return kwargs


def _predict(text, questions, pred, culprit, **kwargs):
    """Run one forward pass; laya's refusal of a question is a domain error."""
    try:
        return _get_router().predict(text, questions, **kwargs)
    except (ValueError, TypeError) as exc:
        raise LogicException(domain_error(
            "laya_question", culprit, f"{pred}: {exc}")) from exc


def _one(text, instructions, qtype, criteria, pred):
    """Ask one question; its answer dict as laya returns it."""
    text = require_text(text, pred, arg=1)
    instructions = require_text(instructions, pred, arg=2)
    question = {"type": qtype, "instructions": instructions}
    if criteria is not None:
        question["criteria"] = criteria
    result = _predict(text, {"q": question}, pred, question)
    return result["answers"]["q"]


def _ranked(probabilities):
    """``(key, p)`` pairs, most probable first; ties keep option order."""
    return sorted(probabilities.items(), key=lambda kv: -kv[1])


# ── choice/4, choice/5 ───────────────────────────────────────────────────

def _choice_4(text, instructions, labels, label, trail, k):
    criteria, by_key = _labels(labels, "choice/4")
    answer = _one(text, instructions, "choice", criteria, "choice/4")
    if unify(label, by_key[answer["choice"]], trail):
        yield None


def _choice_5(text, instructions, labels, label, p, trail, k):
    criteria, by_key = _labels(labels, "choice/5")
    answer = _one(text, instructions, "choice", criteria, "choice/5")
    for key, prob in _ranked(answer["probabilities"]):
        mark = trail.mark()
        if unify(label, by_key[key], trail) and unify(p, float(prob), trail):
            yield None
        trail.undo(mark)


# ── noul/3 ───────────────────────────────────────────────────────────────

def _noul_3(text, instructions, p, trail, k):
    answer = _one(text, instructions, "noul", None, "noul/3")
    if unify(p, float(answer["noul"]), trail):
        yield None


# ── score/4, score/5 ─────────────────────────────────────────────────────

def _score_4(text, instructions, levels, score, trail, k):
    answer = _one(text, instructions, "score",
                  _levels(levels, "score/4"), "score/4")
    if unify(score, float(answer["score"]), trail):
        yield None


def _score_5(text, instructions, levels, level, p, trail, k):
    answer = _one(text, instructions, "score",
                  _levels(levels, "score/5"), "score/5")
    for key, prob in _ranked(answer["probabilities"]):
        mark = trail.mark()
        if unify(level, int(key), trail) and unify(p, float(prob), trail):
            yield None
        trail.undo(mark)


# ── predict/3, predict/4 ─────────────────────────────────────────────────

def _answer_term(answer, by_key):
    """A laya answer dict as a term: atom keys, the caller's label terms, the
    action-head diagnostics (``action``) dropped."""
    qtype = answer["type"]
    out = {"type": qtype}
    if qtype == "choice":
        out["choice"] = by_key.get(answer["choice"], answer["choice"])
        out["probabilities"] = {by_key.get(key, key): float(prob)
                                for key, prob in answer["probabilities"].items()}
    elif qtype == "score":
        out["score"] = float(answer["score"])
        out["probabilities"] = {int(key): float(prob)
                                for key, prob in answer["probabilities"].items()}
    else:
        out["noul"] = float(answer["noul"])
    out["confidence"] = float(answer["confidence"])
    out["answer_confidence"] = float(answer["answer_confidence"])
    if answer.get("low_confidence"):
        out["low_confidence"] = True
    return out


def _field(qdef, name):
    """The value a question dict holds under the key *name* (an atom or a
    string key), or ``None``."""
    for key, value in qdef.items():
        if to_text(deref(key)) == name:
            return value
    return None


def _predict_n(text, questions, options, answers, trail, pred):
    text = require_text(text, pred, arg=1)
    questions = deref(questions)
    if not _is_dict(questions):
        expect_type(questions, dict, pred, arg=2)
    kwargs = _options(options, pred) if options is not None else {}
    asked, qids, label_maps = {}, {}, {}
    for qid, qdef in questions.items():
        qid = deref(qid)
        name = str(_label_key(qid, pred))
        qids[name] = qid
        qdef = deref(qdef)
        if not _is_dict(qdef):
            raise LogicException(domain_error(
                "laya_question", qdef, f"{pred}: a question is a dict"))
        definition = {}
        for key, value in qdef.items():
            key = deref(key)
            definition[to_text(key) or str(key)] = to_python(value)
        criteria = _field(qdef, "criteria")
        if definition.get("type") == "choice" and criteria is not None:
            definition["criteria"], label_maps[name] = _labels(criteria, pred)
        asked[name] = definition
    result = _predict(text, asked, pred, questions, **kwargs)
    term = {qids[name]: _answer_term(answer, label_maps.get(name, {}))
            for name, answer in result["answers"].items()}
    if unify(answers, term, trail):
        yield None


def _predict_3(text, questions, answers, trail, k):
    yield from _predict_n(text, questions, None, answers, trail, "predict/3")


def _predict_4(text, questions, options, answers, trail, k):
    yield from _predict_n(text, questions, options, answers, trail, "predict/4")


# ── Exports ──────────────────────────────────────────────────────────────

choice = ModulePredicate("choice")
choice._register(4, simple_to_trampoline(_choice_4))
choice._register(5, simple_to_trampoline(_choice_5))

noul = ModulePredicate("noul")
noul._register(3, simple_to_trampoline(_noul_3))

score = ModulePredicate("score")
score._register(4, simple_to_trampoline(_score_4))
score._register(5, simple_to_trampoline(_score_5))

predict = ModulePredicate("predict")
predict._register(3, simple_to_trampoline(_predict_3))
predict._register(4, simple_to_trampoline(_predict_4))
