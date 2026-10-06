"""clausal.modules.py.laya — System One decision predicates for Clausal.

`laya <https://pypi.org/project/laya/>`_ is a non-autoregressive "System 1"
decision engine: given a text and a set of typed questions, one forward pass
answers all of them with calibrated probabilities.  This module makes those
answers relations -- a neural predicate whose solutions carry probabilities::

    -import_from(py.laya, [choice, noul, score, predict, predict_batch])

The same protocol -- a state plus typed questions (``choice``, ``score``,
``noul``) answered with probabilities -- is served three ways, so the
predicates run on a swappable BACKEND (``use_backend/1,2``):

- ``laya`` (the default): the open laya model in this process, through
  ``laya.Router.predict_batch``, the layer that groups requests by
  checkpoint and question set and shares forward passes
  (``Agent.predict_batch``); below it, calibration would have to be
  re-implemented.  Needs ``laya`` (and torch); the checkpoint downloads from
  the Hugging Face Hub on first use.
- ``laya_serve``: a ``laya-serve`` HTTP server (``/v1/systemone/batch``).
- ``typesafe``: TypeSafe's hosted Jev model through ``typesafe-sdk``
  (``pip install "clausal-laya[typesafe]"``; ``TYPESAFE_API_KEY``).

Predicates
----------
- ``choice(Text, Instructions, Labels, Label)``      -- the most probable label
- ``choice(Text, Instructions, Labels, Label, P)``   -- every label with its
  probability, most probable first (nondeterministic); with ``Label`` bound,
  that label's probability
- ``noul(Text, Instructions, P)``                    -- P(yes)
- ``score(Text, Instructions, Levels, Score)``       -- the expected level
- ``score(Text, Instructions, Levels, Level, P)``    -- every 0-based level
  with its probability, most probable first (nondeterministic)
- ``predict(Text, Questions, [Options,] Answers)``   -- several questions in
  one forward pass
- ``predict_batch(Texts, Questions, [Options,] AnswersList)`` -- the same
  questions over many texts, sharing forward passes
- ``use_backend(Name)``, ``use_backend(Name, Options)``, ``backend(Name)``
  -- choose / query the process-wide backend and its default options
- ``register_model(Name, Source)``  -- serve a checkpoint (a fine-tune) under
  ``Name`` beside the built-ins (local ``laya`` backend)
- ``finetune(Data, Base, OutputDir, Options, Summary)`` -- fine-tune ``Base``
  on ``Data`` (rows, or a JSONL/CSV path), calibrate, save to ``OutputDir``

Options (``predict/4``, ``predict_batch/4``, ``use_backend/2``): ``model``,
``lang``, ``max_len``, ``head_max_len``, ``min_confidence``; a call's options
override the backend's.  ``typesafe`` takes ``model`` only.

Terms
-----
``Text``/``Instructions`` are text (an atom or a string).  ``Labels`` is a
non-empty list of labels or a dict ``Label -> Description``; answers name a
label by the TERM the caller wrote.  ``Levels`` is a non-empty list.  An
answer (``predict``) is a dict with atom keys: ``type``, the answer under the
type's name (label term, expected level, P(yes)), ``probabilities`` (label ->
P or level -> P), ``confidence`` and ``answer_confidence`` when the backend
reports them, and ``low_confidence`` when ``min_confidence`` flagged it.

Purity
------
For a fixed checkpoint, answering is a function of its inputs: the decision
predicates are pure and safe to backtrack over.  ``use_backend``,
``register_model`` and ``finetune`` change process state or write files:
call them at the program's boundary, not under backtracking.

Errors (RULED 2026-10-02: raise, never fail)
--------------------------------------------
``instantiation_error``; ``type_error(text|list|dict|laya_label, C)``;
``domain_error(non_empty_list, [])``; ``domain_error(laya_question, C)`` for
a question the backend refuses; ``domain_error(laya_backend, Name)`` for an
unknown backend; ``domain_error(laya_option, Name)`` for an option the
backend does not take; ``permission_error(modify, laya_model, Name)`` for
``register_model`` off the local backend; ``domain_error(laya_train_config,
C)`` for a training option laya refuses.
"""

from __future__ import annotations

import json as _json
import os as _os
import tempfile as _tempfile
import threading as _threading

from clausal.logic.exceptions import (
    LogicException, domain_error, permission_error, type_error,
)
from clausal.logic.to_python import to_python
from clausal.logic.variables import deref, is_var, unify
from clausal.modules.py import (
    ModulePredicate, _import_stdlib, expect_type, has_option, option,
    raise_domain_error, require_text, simple_to_trampoline, text_result,
    to_text,
)

# The per-call controls laya's Router, Agent and laya-serve all take
# (laya/integrations/_controls.py: PREDICT_CONTROLS + DECISION_CONTROLS).
_CONTROLS = ("model", "lang", "max_len", "head_max_len", "min_confidence")


# ── Backends ─────────────────────────────────────────────────────────────
#
# A backend answers a list of requests -- ``{"state", "questions", **controls}``
# -- with one ``answers`` dict (question id -> laya-shaped answer) per request,
# in order.  laya's own payload shape (laya/agent.py) is the common format.

class _LayaBackend:
    """The open model in this process, through ``Router.predict_batch``."""

    name = "laya"
    controls = _CONTROLS

    def __init__(self, router=None):
        self._router = router
        self._lock = _threading.Lock()

    def router(self):
        if self._router is None:
            with self._lock:
                if self._router is None:
                    self._router = _import_stdlib("laya").Router()
        return self._router

    def answer(self, requests):
        return [r["answers"] for r in self.router().predict_batch(requests)]


class _ServeBackend:
    """A ``laya-serve`` node: requests sharing questions and controls go in
    one ``/v1/systemone/batch`` POST, as the server batches them itself."""

    name = "laya_serve"
    controls = _CONTROLS

    def __init__(self, url, api_key=None, timeout=60.0):
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _post(self, body):
        import urllib.error  # noqa: PLC0415
        import urllib.request  # noqa: PLC0415
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(
            self.url + "/v1/systemone/batch", method="POST", headers=headers,
            data=_json.dumps(body).encode("utf-8"))
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return _json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code in (400, 422):
                raise ValueError(f"laya-serve refused the request: {detail}") from exc
            raise RuntimeError(f"laya-serve error {exc.code}: {detail}") from exc

    def answer(self, requests):
        groups = {}
        for i, req in enumerate(requests):
            controls = {k: v for k, v in req.items() if k not in ("state", "questions")}
            key = _json.dumps([req["questions"], controls], sort_keys=True, default=str)
            groups.setdefault(key, (req["questions"], controls, []))[2].append(i)
        out = [None] * len(requests)
        for questions, controls, indices in groups.values():
            body = dict(controls, questions=questions,
                        states=[requests[i]["state"] for i in indices])
            for i, result in zip(indices, self._post(body)["results"]):
                out[i] = result["answers"]
        return out


class _TypeSafeBackend:
    """TypeSafe's hosted Jev model, through ``typesafe_sdk.TypeSafeClient``."""

    name = "typesafe"
    controls = ("model",)

    def __init__(self, client=None, **client_kwargs):
        self._client = client
        self._client_kwargs = client_kwargs
        self._lock = _threading.Lock()

    def client(self):
        if self._client is None:
            with self._lock:
                if self._client is None:
                    sdk = _import_stdlib("typesafe_sdk")
                    self._client = sdk.TypeSafeClient(**self._client_kwargs)
        return self._client

    @staticmethod
    def _question(sdk, q):
        kind, ins = q.get("type"), q.get("instructions")
        crit = q.get("criteria")
        if kind == "choice":
            if isinstance(crit, list):
                crit = {str(label): None for label in crit}
            return sdk.Choice(instructions=ins, criteria={str(k): v for k, v in crit.items()})
        if kind == "score":
            return sdk.Score(instructions=ins, criteria=crit)
        if kind == "noul":
            return sdk.Noul(instructions=ins)
        raise ValueError(f"unknown question type {kind!r}")

    def answer(self, requests):
        sdk = _import_stdlib("typesafe_sdk")
        client = self.client()
        out = []
        for req in requests:
            questions = {qid: self._question(sdk, q) for qid, q in req["questions"].items()}
            kwargs = {"model": req["model"]} if "model" in req else {}
            try:
                resp = client.system_one(state=req["state"], questions=questions, **kwargs)
            except (getattr(sdk, "TypeSafeBadRequestError", ()),
                    getattr(sdk, "TypeSafeUnprocessableEntityError", ())) as exc:
                raise ValueError(str(exc)) from exc
            out.append({qid: a.model_dump() for qid, a in resp.answers.items()})
        return out


_BACKENDS = {"laya": _LayaBackend, "laya_serve": _ServeBackend,
             "typesafe": _TypeSafeBackend}
_backend = _LayaBackend()
_defaults: dict = {}
_backend_lock = _threading.Lock()


def _set_backend(backend, defaults=None):
    """Install *backend* (and its default controls) process-wide."""
    global _backend, _defaults
    with _backend_lock:
        _backend, _defaults = backend, dict(defaults or {})


# ── Argument conversion ──────────────────────────────────────────────────

def _is_dict(v) -> bool:
    from clausal.terms import DictTerm  # noqa: PLC0415
    return isinstance(v, (dict, DictTerm))


def _label_key(label, pred, arg=3):
    """The scalar a backend keys a label by: its text, or the number itself."""
    text = to_text(label)
    if text is not None:
        return text
    if isinstance(label, (int, float)) and not isinstance(label, bool):
        return label
    raise LogicException(type_error("laya_label", label, f"{pred}: argument {arg}"))


def _labels(labels, pred):
    """``(criteria, by_key)``: the criteria the backend is given, and its
    key -> the label TERM the caller wrote."""
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


def _options(options, pred, arg, names=_CONTROLS):
    """The controls an options dict names (text values as ``str``)."""
    options = deref(options)
    if not _is_dict(options):
        expect_type(options, dict, pred, arg=arg)
    out = {}
    for name in names:
        if has_option(options, name):
            value = deref(option(options, name))
            text = to_text(value)
            out[name] = text if text is not None else to_python(value)
    return out


def _field(qdef, name):
    for key, value in qdef.items():
        if to_text(deref(key)) == name:
            return value
    return None


def _questions(questions, pred, arg=2):
    """``(asked, qids, label_maps)`` for a Questions dict: what the backend
    is asked, its id -> the caller's id term, and per choice question its
    label key -> label term."""
    questions = deref(questions)
    if not _is_dict(questions):
        expect_type(questions, dict, pred, arg=arg)
    asked, qids, label_maps = {}, {}, {}
    for qid, qdef in questions.items():
        qid = deref(qid)
        name = str(_label_key(qid, pred, arg))
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
    return asked, qids, label_maps


def _ask(requests, pred, culprit, call_options=None):
    """Answer *requests* on the current backend, with its defaults and
    *call_options* applied; a refused question is a domain error."""
    backend, defaults = _backend, _defaults
    controls = dict(defaults, **(call_options or {}))
    for name in controls:
        if name not in backend.controls:
            raise LogicException(domain_error(
                "laya_option", name, f"{pred}: the {backend.name} backend "
                f"takes {', '.join(backend.controls)}"))
    try:
        return backend.answer([dict(controls, **r) for r in requests])
    except (ValueError, TypeError) as exc:
        raise LogicException(domain_error(
            "laya_question", culprit, f"{pred}: {exc}")) from exc


def _one(text, instructions, qtype, criteria, pred):
    """Ask one question about one text; its laya-shaped answer."""
    text = require_text(text, pred, arg=1)
    instructions = require_text(instructions, pred, arg=2)
    question = {"type": qtype, "instructions": instructions}
    if criteria is not None:
        question["criteria"] = criteria
    [answers] = _ask([{"state": text, "questions": {"q": question}}], pred, question)
    return answers["q"]


def _ranked(probabilities):
    """``(key, p)`` pairs, most probable first; ties keep option order."""
    return sorted(probabilities.items(), key=lambda kv: -kv[1])


def _answer_term(answer, by_key):
    """A laya-shaped answer as a term: atom keys, the caller's label terms;
    the action-head diagnostics (``action``) and ``legend`` dropped."""
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
    for name in ("confidence", "answer_confidence"):
        if answer.get(name) is not None:
            out[name] = float(answer[name])
    if answer.get("low_confidence"):
        out["low_confidence"] = True
    return out


# ── choice/4,5, noul/3, score/4,5 ────────────────────────────────────────

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


def _noul_3(text, instructions, p, trail, k):
    answer = _one(text, instructions, "noul", None, "noul/3")
    if unify(p, float(answer["noul"]), trail):
        yield None


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


# ── predict/3,4, predict_batch/3,4 ───────────────────────────────────────

def _answers_term(answers, qids, label_maps):
    return {qids[name]: _answer_term(answer, label_maps.get(name, {}))
            for name, answer in answers.items()}


def _predict_n(text, questions, options, answers, trail, pred):
    text = require_text(text, pred, arg=1)
    asked, qids, label_maps = _questions(questions, pred)
    call = _options(options, pred, 3) if options is not None else {}
    [got] = _ask([{"state": text, "questions": asked}], pred, deref(questions), call)
    if unify(answers, _answers_term(got, qids, label_maps), trail):
        yield None


def _predict_3(text, questions, answers, trail, k):
    yield from _predict_n(text, questions, None, answers, trail, "predict/3")


def _predict_4(text, questions, options, answers, trail, k):
    yield from _predict_n(text, questions, options, answers, trail, "predict/4")


def _batch_n(texts, questions, options, answers_list, trail, pred):
    texts = deref(texts)
    expect_type(texts, list, pred, arg=1)
    states = [require_text(t, pred, arg=1) for t in texts]
    asked, qids, label_maps = _questions(questions, pred)
    call = _options(options, pred, 3) if options is not None else {}
    got = _ask([{"state": s, "questions": asked} for s in states],
               pred, deref(questions), call) if states else []
    out = [_answers_term(a, qids, label_maps) for a in got]
    if unify(answers_list, out, trail):
        yield None


def _predict_batch_3(texts, questions, answers_list, trail, k):
    yield from _batch_n(texts, questions, None, answers_list, trail, "predict_batch/3")


def _predict_batch_4(texts, questions, options, answers_list, trail, k):
    yield from _batch_n(texts, questions, options, answers_list, trail,
                        "predict_batch/4")


# ── use_backend/1,2, backend/1 ───────────────────────────────────────────

def _make_backend(name, options, pred):
    if name == "laya":
        return _LayaBackend()
    if name == "laya_serve":
        conn = _options(options, pred, 2, ("url", "api_key", "timeout"))
        if "url" not in conn:
            raise LogicException(domain_error(
                "laya_option", "url", f"{pred}: laya_serve needs a url"))
        return _ServeBackend(conn["url"], conn.get("api_key"),
                             float(conn.get("timeout", 60.0)))
    conn = _options(options, pred, 2, ("api_key", "base_url", "timeout"))
    return _TypeSafeBackend(**conn)


def _use_backend_n(name, options, pred):
    name_term = deref(name)
    text = require_text(name_term, pred, arg=1)
    if text not in _BACKENDS:
        raise LogicException(domain_error(
            "laya_backend", name_term, f"{pred}: one of {', '.join(_BACKENDS)}"))
    if options is None:
        options = {}
    backend = _make_backend(text, options, pred)
    defaults = _options(options, pred, 2, backend.controls) if options else {}
    _set_backend(backend, defaults)
    yield None


def _use_backend_1(name, trail, k):
    yield from _use_backend_n(name, None, "use_backend/1")


def _use_backend_2(name, options, trail, k):
    yield from _use_backend_n(name, options, "use_backend/2")


def _backend_1(name, trail, k):
    if unify(name, _backend.name, trail):
        yield None


# ── register_model/2, finetune/5 ─────────────────────────────────────────

def _register_model_2(name, source, trail, k):
    pred = "register_model/2"
    name_text = require_text(name, pred, arg=1)
    source_text = require_text(source, pred, arg=2)
    backend = _backend
    if not isinstance(backend, _LayaBackend):
        raise LogicException(permission_error(
            "modify", "laya_model", deref(name),
            f"{pred}: only the local laya backend serves registered checkpoints"))
    backend.router().register(name_text, source_text)
    yield None


_TRAIN_DEVICE = "device"


def _finetune_5(data, base, output_dir, options, summary, trail, k):
    pred = "finetune/5"
    out_dir = require_text(output_dir, pred, arg=3)
    base_text = require_text(base, pred, arg=2)
    train = _import_stdlib("laya.train")
    fields = tuple(train.TrainConfig.__dataclass_fields__)
    knobs = _options(options, pred, 4, fields + (_TRAIN_DEVICE,))
    device = knobs.pop(_TRAIN_DEVICE, "auto")
    try:
        config = train.TrainConfig(**knobs)
        config.validate()
    except (TypeError, ValueError) as exc:
        raise LogicException(domain_error(
            "laya_train_config", deref(options), f"{pred}: {exc}")) from exc
    data_term = deref(data)
    path = to_text(data_term)
    tmp = None
    if path is None:
        # Rows: [{state, questions, expected}] -- laya-train's JSONL rows.
        expect_type(data_term, list, pred, arg=1)
        rows = [to_python(row) for row in data_term]
        fd, tmp = _tempfile.mkstemp(suffix=".jsonl", prefix="clausal_laya_")
        with _os.fdopen(fd, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(_json.dumps(row) + "\n")
        path = tmp
    try:
        model_dir = train.resolve_checkpoint_dir(base_text)
        result = train.finetune(path, model_dir, out_dir, config, device=device)
    except ValueError as exc:
        raise LogicException(domain_error(
            "laya_training_data", data_term, f"{pred}: {exc}")) from exc
    finally:
        if tmp is not None:
            _os.unlink(tmp)
    keep = {key: result[key] for key in
            ("train_items", "calibration_items", "epoch_loss", "temperature",
             "output_dir") if key in result}
    if unify(summary, text_result(_json.loads(_json.dumps(keep))), trail):
        yield None


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

predict_batch = ModulePredicate("predict_batch")
predict_batch._register(3, simple_to_trampoline(_predict_batch_3))
predict_batch._register(4, simple_to_trampoline(_predict_batch_4))

use_backend = ModulePredicate("use_backend")
use_backend._register(1, simple_to_trampoline(_use_backend_1))
use_backend._register(2, simple_to_trampoline(_use_backend_2))

backend = ModulePredicate("backend")
backend._register(1, simple_to_trampoline(_backend_1))

register_model = ModulePredicate("register_model")
register_model._register(2, simple_to_trampoline(_register_model_2))

finetune = ModulePredicate("finetune")
finetune._register(5, simple_to_trampoline(_finetune_5))
