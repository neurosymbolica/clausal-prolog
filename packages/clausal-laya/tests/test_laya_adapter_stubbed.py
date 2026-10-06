"""The laya adapter's own logic, against a fake ``laya.Router``.

Runs WITHOUT laya, torch or a checkpoint (``*_stubbed.py``, see
packages/conftest.py): the local backend builds its ``laya.Router`` lazily,
so a ``_LayaBackend`` given a fake router answers, through the real backend
path (``Router.predict_batch``), in laya's own payload shape (``laya/agent.py``: ``{"answers": {qid: {"type", <type>,
"probabilities", "confidence", "answer_confidence", "action"}}}``) and
records exactly what the adapter asked.
"""

from __future__ import annotations

import pytest

from clausal.logic.cells import chars
from clausal.logic.exceptions import LogicException
from clausal.logic.variables import Trail, Var, deref
from clausal.modules.py import laya as pylaya
from clausal.terms import DictTerm


class FakeRouter:
    """Answers every question from fixed probabilities, in laya's shape."""

    def __init__(self):
        self.calls = []
        self.batches = []

    def predict_batch(self, requests):
        """``Router.predict_batch``: one result per request, in order."""
        self.batches.append(len(requests))
        return [self.predict(r["state"], r["questions"],
                             **{k: v for k, v in r.items()
                                if k not in ("state", "questions")})
                for r in requests]

    def predict(self, state, questions, **kwargs):
        self.calls.append((state, questions, kwargs))
        answers = {}
        for qid, q in questions.items():
            if q["type"] not in ("choice", "score", "noul"):
                raise ValueError(f"question {qid!r}: unknown type {q['type']!r}")
            if q["type"] == "choice":
                crit = q["criteria"]
                keys = list(crit) if isinstance(crit, dict) else list(crit)
                if len(set(keys)) != len(keys):
                    raise ValueError(f"question {qid!r}: a label repeats")
                # The LAST label is the most probable, then the others in order.
                probs = [0.1] * len(keys)
                probs[-1] = 1.0 - 0.1 * (len(keys) - 1)
                answers[qid] = {
                    "type": "choice", "choice": keys[-1],
                    "probabilities": dict(zip(keys, probs)),
                    "confidence": 0.5, "answer_confidence": probs[-1],
                    "action": {"act_probability": 0.9},
                }
            elif q["type"] == "score":
                n = len(q["criteria"])
                probs = {str(i): (0.7 if i == 1 else 0.3 / (n - 1)) for i in range(n)}
                answers[qid] = {
                    "type": "score", "score": 1.0,
                    "legend": {str(i): c for i, c in enumerate(q["criteria"])},
                    "probabilities": probs,
                    "confidence": 0.4, "answer_confidence": 0.7,
                    "action": {"act_probability": 0.9},
                }
            else:
                answers[qid] = {
                    "type": "noul", "noul": 0.8, "confidence": 0.8,
                    "answer_confidence": 0.8, "action": {"act_probability": 0.9},
                }
        if kwargs.get("min_confidence"):
            for a in answers.values():
                if a["answer_confidence"] < kwargs["min_confidence"]:
                    a["low_confidence"] = True
        return {"model": "fake", "answers": answers, "usage": {},
                "routing": {"model": "english"}}


@pytest.fixture
def router(monkeypatch):
    fake = FakeRouter()
    monkeypatch.setattr(pylaya, "_backend", pylaya._LayaBackend(router=fake))
    monkeypatch.setattr(pylaya, "_defaults", {})
    return fake


def solutions(fn, *args):
    """Every solution of a simple-mode adapter fn, as the dereferenced args."""
    trail = Trail()
    out = []
    for _ in fn(*args, trail, None):
        out.append(tuple(deref(a) for a in args))
    return out


# ── choice ───────────────────────────────────────────────────────────────

def test_choice_4_answers_the_label_term_the_caller_wrote(router):
    label = Var()
    [sol] = solutions(pylaya._choice_4, "billed twice", "Which team?",
                      ["technical", chars("billing")], label)
    assert sol[3] == chars("billing")          # a string label comes back a string
    state, questions, _ = router.calls[0]
    assert state == "billed twice"
    assert questions == {"q": {"type": "choice", "instructions": "Which team?",
                               "criteria": ["technical", "billing"]}}


def test_choice_5_enumerates_most_probable_first(router):
    sols = solutions(pylaya._choice_5, "t", "i", ["a", "b", "c"], Var(), Var())
    assert [(s[3], s[4]) for s in sols] == [("c", pytest.approx(0.8)),
                                            ("a", 0.1), ("b", 0.1)]


def test_choice_5_with_the_label_bound_gives_its_probability(router):
    p = Var()
    [sol] = solutions(pylaya._choice_5, "t", "i", ["a", "b"], "a", p)
    assert sol[4] == pytest.approx(0.1)
    assert solutions(pylaya._choice_5, "t", "i", ["a", "b"], "zzz", Var()) == []


def test_choice_takes_a_dict_of_label_descriptions(router):
    labels = DictTerm({"billing": chars("invoices, refunds"),
                       "technical": chars("bugs, outages")})
    [sol] = solutions(pylaya._choice_4, "t", "i", labels, Var())
    assert sol[3] == "technical"
    assert router.calls[0][1]["q"]["criteria"] == {
        "billing": "invoices, refunds", "technical": "bugs, outages"}


def test_numeric_labels(router):
    [sol] = solutions(pylaya._choice_4, "t", "i", [1, 2, 3], Var())
    assert sol[3] == 3


# ── noul, score ──────────────────────────────────────────────────────────

def test_noul_is_the_probability_of_yes(router):
    [sol] = solutions(pylaya._noul_3, chars("I will cancel"), "Churn?", Var())
    assert sol[2] == pytest.approx(0.8)
    assert router.calls[0][1]["q"] == {"type": "noul", "instructions": "Churn?"}


def test_score_4_is_the_expected_level(router):
    [sol] = solutions(pylaya._score_4, "t", "How urgent?",
                      ["not urgent", "soon", "blocking"], Var())
    assert sol[3] == 1.0
    assert router.calls[0][1]["q"]["criteria"] == ["not urgent", "soon", "blocking"]


def test_score_5_enumerates_levels_most_probable_first(router):
    sols = solutions(pylaya._score_5, "t", "i", ["low", "mid", "high"], Var(), Var())
    assert [s[3] for s in sols] == [1, 0, 2]
    assert sols[0][4] == pytest.approx(0.7)


# ── predict ──────────────────────────────────────────────────────────────

def test_predict_answers_by_the_callers_question_ids(router):
    questions = DictTerm({
        chars("department"): DictTerm({
            chars("type"): chars("choice"),
            chars("instructions"): chars("Which department?"),
            chars("criteria"): ["billing", chars("other")]}),
        "churn": DictTerm({"type": "noul", "instructions": chars("Leaving?")}),
    })
    answers = Var()
    [sol] = solutions(pylaya._predict_3, "t", questions, answers)
    got = sol[2]
    dept = got[chars("department")]
    assert dept["type"] == "choice" and dept["choice"] == chars("other")
    assert dept["probabilities"] == {"billing": pytest.approx(0.1),
                                     chars("other"): pytest.approx(0.9)}
    assert "action" not in dept
    assert got["churn"] == {"type": "noul", "noul": 0.8, "confidence": 0.8,
                            "answer_confidence": 0.8}
    asked = router.calls[0][1]
    assert asked["department"] == {"type": "choice", "instructions": "Which department?",
                                   "criteria": ["billing", "other"]}


def test_predict_4_passes_the_options(router):
    questions = DictTerm({"u": DictTerm({"type": "noul", "instructions": "x"})})
    options = DictTerm({"model": "multilingual", chars("max_len"): 8192,
                        "min_confidence": 0.9, "ignored": 1})
    [sol] = solutions(pylaya._predict_4, "t", questions, options, Var())
    assert router.calls[0][2] == {"model": "multilingual", "max_len": 8192,
                                  "min_confidence": 0.9}
    assert sol[3]["u"]["low_confidence"] is True


def test_score_answer_in_predict_keys_levels_by_integer(router):
    questions = DictTerm({"u": DictTerm({"type": "score", "instructions": "x",
                                         "criteria": ["a", "b", "c"]})})
    [sol] = solutions(pylaya._predict_3, "t", questions, Var())
    assert sorted(sol[2]["u"]["probabilities"]) == [0, 1, 2]


# ── errors: raise, never fail ────────────────────────────────────────────

def _error(fn, *args):
    with pytest.raises(LogicException) as info:
        solutions(fn, *args)
    return info.value.term


def test_unbound_text_is_an_instantiation_error(router):
    err = _error(pylaya._noul_3, Var(), "i", Var())
    assert err[1] == "instantiation_error"


def test_text_that_is_not_text_is_a_type_error(router):
    err = _error(pylaya._noul_3, ("f", 1), "i", Var())
    assert err[1][:2] == ("type_error", "text")


def test_labels_must_be_a_non_empty_list(router):
    assert _error(pylaya._choice_4, "t", "i", "abc", Var())[1][:2] == ("type_error", "list")
    assert _error(pylaya._choice_4, "t", "i", [], Var())[1][:2] == (
        "domain_error", "non_empty_list")
    assert _error(pylaya._choice_4, "t", "i", [("f", 1)], Var())[1][:2] == (
        "type_error", "laya_label")


def test_a_question_laya_refuses_is_a_domain_error(router):
    questions = DictTerm({"u": DictTerm({"type": "ranking", "instructions": "x"})})
    err = _error(pylaya._predict_3, "t", questions, Var())
    assert err[1][:2] == ("domain_error", "laya_question")
    assert _error(pylaya._choice_4, "t", "i", ["a", chars("a")], Var())[1][:2] == (
        "domain_error", "laya_question")


def test_questions_must_be_a_dict(router):
    assert _error(pylaya._predict_3, "t", ["x"], Var())[1][:2] == ("type_error", "dict")


# ── the seam surface ─────────────────────────────────────────────────────

def test_seam_fixture_against_the_fake_router(router):
    """``-import_from(py.laya, ...)`` resolves, dict literals and atoms reach
    the router, and the answers unify in seam code (findall, dict_get)."""
    from pathlib import Path
    from clausal.testing import run_file
    fixture = Path(__file__).parent / "fixtures" / "laya_stubbed.seam"
    results = run_file(fixture).results
    failed = [(r.name, r.error) for r in results if not r.passed]
    assert results and not failed, failed


def test_bare_name_import_reaches_the_adapter(router, tmp_path):
    """``-import_from(laya, ...)`` means this adapter, not the Python library,
    on an engine whose alias tables carry ``laya`` (after 1.0.0)."""
    from clausal.templating.term_rewriting import _IMPORT_ALIASES
    if "laya" not in _IMPORT_ALIASES:
        pytest.skip("this engine predates the bare `laya` import alias")
    from clausal.testing import run_file
    src = tmp_path / "bare_laya.seam"
    src.write_text(
        "-import_from(laya, [noul])\n\n"
        'test("bare laya") <- (noul("t", "Leaving?", P), P > 0.5)  # nv\n')
    results = run_file(src).results
    assert results and all(r.passed for r in results), [
        (r.name, r.error) for r in results]


# ── predict_batch: many texts, one backend call ──────────────────────────

def test_predict_batch_answers_every_text_in_one_call(router):
    questions = DictTerm({"u": DictTerm({"type": "noul", "instructions": "x"})})
    [sol] = solutions(pylaya._predict_batch_3, ["a", chars("b"), "c"], questions, Var())
    assert [a["u"]["noul"] for a in sol[2]] == [0.8, 0.8, 0.8]
    assert router.batches == [3]
    assert [c[0] for c in router.calls] == ["a", "b", "c"]


def test_predict_batch_of_nothing_is_empty(router):
    questions = DictTerm({"u": DictTerm({"type": "noul", "instructions": "x"})})
    [sol] = solutions(pylaya._predict_batch_3, [], questions, Var())
    assert sol[2] == [] and router.batches == []


# ── backends: choosing one, defaults, options ────────────────────────────

def test_backend_defaults_apply_and_call_options_override(router):
    pylaya._set_backend(pylaya._backend, {"model": "multilingual", "max_len": 2048})
    questions = DictTerm({"u": DictTerm({"type": "noul", "instructions": "x"})})
    solutions(pylaya._predict_4, "t", questions, DictTerm({"max_len": 8192}), Var())
    assert router.calls[-1][2] == {"model": "multilingual", "max_len": 8192}


def test_use_backend_and_backend(monkeypatch):
    monkeypatch.setattr(pylaya, "_backend", pylaya._backend)
    monkeypatch.setattr(pylaya, "_defaults", {})
    solutions(pylaya._use_backend_2, "laya_serve",
              DictTerm({"url": chars("http://h:8000/"), "model": "english"}))
    [sol] = solutions(pylaya._backend_1, Var())
    assert sol[0] == "laya_serve"
    assert pylaya._backend.url == "http://h:8000"
    assert pylaya._defaults == {"model": "english"}
    assert _error(pylaya._use_backend_1, "gpt")[1][:2] == ("domain_error", "laya_backend")
    assert _error(pylaya._use_backend_1, "laya_serve")[1][:2] == (
        "domain_error", "laya_option")                     # no url


def test_an_option_the_backend_does_not_take(monkeypatch):
    monkeypatch.setattr(pylaya, "_backend", pylaya._TypeSafeBackend(client=object()))
    monkeypatch.setattr(pylaya, "_defaults", {})
    questions = DictTerm({"u": DictTerm({"type": "noul", "instructions": "x"})})
    err = _error(pylaya._predict_4, "t", questions, DictTerm({"lang": "fr"}), Var())
    assert err[1][:3] == ("domain_error", "laya_option", "lang")


# ── laya_serve: a real HTTP round trip ───────────────────────────────────

@pytest.fixture
def serve(monkeypatch):
    """A local stand-in for laya-serve's /v1/systemone/batch."""
    import http.server
    import json
    import threading

    fake, posts = FakeRouter(), []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            posts.append((self.path, self.headers.get("Authorization"), body))
            controls = {k: v for k, v in body.items() if k not in ("states", "questions")}
            try:
                results = [fake.predict(s, body["questions"], **controls)
                           for s in body["states"]]
                code, payload = 200, {"results": results}
            except ValueError as exc:
                code, payload = 422, {"detail": str(exc)}
            data = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(pylaya, "_backend", pylaya._ServeBackend(
        f"http://127.0.0.1:{server.server_port}", api_key="k"))
    monkeypatch.setattr(pylaya, "_defaults", {})
    yield posts
    server.shutdown()


def test_serve_backend_batches_by_question_set(serve):
    q1 = DictTerm({"u": DictTerm({"type": "noul", "instructions": "x"})})
    [sol] = solutions(pylaya._predict_batch_3, ["a", "b"], q1, Var())
    assert [a["u"]["noul"] for a in sol[2]] == [0.8, 0.8]
    [(path, auth, body)] = serve
    assert path == "/v1/systemone/batch" and auth == "Bearer k"
    assert body["states"] == ["a", "b"]
    [sol] = solutions(pylaya._choice_4, "t", "i", ["a", "b"], Var())
    assert sol[3] == "b"


def test_serve_backend_refusal_is_a_domain_error(serve):
    questions = DictTerm({"u": DictTerm({"type": "ranking", "instructions": "x"})})
    err = _error(pylaya._predict_3, "t", questions, Var())
    assert err[1][:2] == ("domain_error", "laya_question")


# ── typesafe: the real SDK over a mocked transport ───────────────────────

def test_typesafe_backend_through_the_sdk(monkeypatch):
    sdk = pytest.importorskip("typesafe_sdk")
    httpx = pytest.importorskip("httpx2")
    import json
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append((request.url.path, body))
        return httpx.Response(200, json={
            "model": "jev-latest", "usage": {"input_tokens": 1, "output_tokens": 1},
            "answers": {
                "dept": {"type": "choice", "choice": "billing", "confidence": 0.9,
                         "probabilities": {"billing": 0.9, "other": 0.1}},
                "churn": {"type": "noul", "noul": 0.7},
            }})

    client = sdk.TypeSafeClient(api_key="k", transport=httpx.MockTransport(handler))
    monkeypatch.setattr(pylaya, "_backend", pylaya._TypeSafeBackend(client=client))
    monkeypatch.setattr(pylaya, "_defaults", {"model": "jev-latest"})
    questions = DictTerm({
        "dept": DictTerm({"type": "choice", "instructions": "Which team?",
                          "criteria": ["billing", chars("other")]}),
        "churn": DictTerm({"type": "noul", "instructions": "Leaving?"}),
    })
    [sol] = solutions(pylaya._predict_3, "billed twice", questions, Var())
    assert sol[2]["dept"]["choice"] == "billing"
    assert sol[2]["dept"]["probabilities"] == {"billing": 0.9, chars("other"): 0.1}
    assert sol[2]["churn"] == {"type": "noul", "noul": 0.7}
    [(path, body)] = seen
    assert path == "/v1/systemone" and body["model"] == "jev-latest"
    assert body["questions"]["dept"]["criteria"] == {"billing": None, "other": None}


# ── register_model, finetune ─────────────────────────────────────────────

def test_register_model_on_the_local_backend(router):
    registered = []
    router.register = lambda name, source: registered.append((name, source))
    solutions(pylaya._register_model_2, "tickets", chars("/ckpt/tickets"))
    assert registered == [("tickets", "/ckpt/tickets")]


def test_register_model_needs_the_local_backend(monkeypatch):
    monkeypatch.setattr(pylaya, "_backend", pylaya._ServeBackend("http://h"))
    err = _error(pylaya._register_model_2, "tickets", "/ckpt")
    assert err[1][:3] == ("permission_error", "modify", "laya_model")


@pytest.fixture
def train(monkeypatch):
    """A stand-in for ``laya.train``: records what finetune is handed."""
    import dataclasses
    import json
    import sys
    import types

    @dataclasses.dataclass
    class TrainConfig:
        epochs: int = 4
        max_len: int | None = None

        def validate(self):
            if self.epochs < 1:
                raise ValueError("epochs must be a positive integer")

    calls = []

    def finetune(data, model_dir, output_dir, config, device="auto"):
        with open(data) as fh:
            rows = [json.loads(line) for line in fh]
        calls.append((rows, model_dir, output_dir, config, device))
        return {"train_items": len(rows), "calibration_items": 0,
                "epoch_loss": [0.5], "temperature": [1.0, 1.0, 1.0],
                "output_dir": output_dir, "n_by_bucket": {}}

    mod = types.SimpleNamespace(TrainConfig=TrainConfig, finetune=finetune,
                                resolve_checkpoint_dir=lambda m: f"/hub/{m}")
    monkeypatch.setitem(sys.modules, "laya.train", mod)
    return calls


def test_finetune_writes_rows_and_trains(train):
    rows = [DictTerm({"state": chars("billed twice"),
                      "questions": DictTerm({"dept": DictTerm({
                          "type": "choice", "instructions": "Which team?",
                          "criteria": ["billing", "other"]})}),
                      "expected": DictTerm({"dept": "billing"})})]
    [sol] = solutions(pylaya._finetune_5, rows, "english", chars("/out/ft"),
                      DictTerm({"epochs": 2, "device": "cpu"}), Var())
    [(got, model_dir, out, config, device)] = train
    assert got == [{"state": "billed twice",
                    "questions": {"dept": {"type": "choice", "instructions": "Which team?",
                                           "criteria": ["billing", "other"]}},
                    "expected": {"dept": "billing"}}]
    assert (model_dir, out, config.epochs, device) == ("/hub/english", "/out/ft", 2, "cpu")
    assert sol[4]["train_items"] == 1 and sol[4]["output_dir"] == chars("/out/ft")


def test_finetune_refuses_a_bad_training_option(train):
    err = _error(pylaya._finetune_5, [], "english", "/out", DictTerm({"epochs": 0}), Var())
    assert err[1][:2] == ("domain_error", "laya_train_config")
