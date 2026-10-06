"""Tests for clausal.modules.py.spacy — spaCy NLP predicates.

Tests skip gracefully when spaCy or en_core_web_sm is not installed.

Two test layers:

1. Unit tests — direct Python calls to the predicate dispatch functions,
   testing the adapter layer and data conversion helpers.

2. Fixture integration — loads tests/fixtures/spacy_basic.seam and runs
   each ``test/1`` clause via ``call("test", name, module=mod)``.
"""

from __future__ import annotations

import os
import threading

import pytest

try:
    import spacy as _spacy_check  # noqa: F811
    import spacy
    try:
        _spacy_check.load("en_core_web_sm")
        _SPACY_OK = True
    except OSError:
        _SPACY_OK = False
        _SKIP_REASON = "en_core_web_sm not installed — run: python -m spacy download en_core_web_sm"
    else:
        _SKIP_REASON = ""
except Exception:
    _SPACY_OK = False
    _SKIP_REASON = "spaCy not importable (missing or incompatible with Python version)"

if not _SPACY_OK:
    pytest.skip(_SKIP_REASON, allow_module_level=True)

from clausal.logic.solve import call
from clausal.logic.variables import Var, Trail, deref
from clausal.import_hook import _load_module
from clausal.modules.py.spacy import (
    _MODELS,
    _LOCK,
    _get_model,
    _token_to_dict,
    _ent_to_dict,
    _chunk_to_dict,
    load_model,
    unload_model,
    current_model,
    process,
    token,
    token_text,
    token_list,
    pos,
    tag,
    lemma,
    dep,
    head,
    shape,
    is_alpha,
    is_stop,
    entity,
    entity_list,
    sentence,
    sentence_list,
    similarity,
    noun_chunk,
)
from clausal._suffixes import SEAM_SUFFIX
from clausal.logic.cells import chars


# ── Shared test sentence ──────────────────────────────────────────────────────

_TEXT = "Apple is looking at buying U.K. startup for $1 billion."
_ALIAS = "_test_spacy_"


@pytest.fixture(autouse=True, scope="module")
def _load_test_model():
    """Load en_core_web_sm once for the whole test module."""
    nlp = spacy.load("en_core_web_sm")
    with _LOCK:
        _MODELS[_ALIAS] = nlp
    yield
    with _LOCK:
        _MODELS.pop(_ALIAS, None)


@pytest.fixture
def doc():
    """Return a processed spaCy Doc for _TEXT."""
    nlp = _get_model(_ALIAS)
    return nlp(_TEXT)


@pytest.fixture
def trail():
    return Trail()


# ── Helper: run a simple-mode generator and collect solutions ─────────────────

def _solutions_simple(gen_fn, *args, trail):
    """Run a simple-mode generator, return number of solutions."""
    t = trail
    return list(gen_fn(*args, t, None))


def _first_solution_trampoline(pred, *args, trail):
    """Invoke a trampoline predicate and return the first (parent, val) yield."""
    sentinel = object()
    results = []
    gen = pred(sentinel, *args, trail)
    for item in gen:
        parent, val = item
        if val is not None:
            from clausal.logic.trampoline import DONE
            if val is DONE:
                break
        results.append(item)
    return results


# ══════════════════════════════════════════════════════════════════════════════
# Unit tests: helpers
# ══════════════════════════════════════════════════════════════════════════════


class TestTokenToDict:
    def test_keys(self, doc):
        # nv
        d = _token_to_dict(doc[0])
        assert set(d) == {"text", "lemma", "pos", "tag", "dep", "head_text",
                          "head_i", "i", "is_alpha", "is_stop", "shape"}

    def test_apple_text(self, doc):
        # nv
        d = _token_to_dict(doc[0])
        assert d["text"] == chars("Apple")

    def test_index(self, doc):
        # nv
        d = _token_to_dict(doc[0])
        assert d["i"] == 0

    def test_is_alpha_true(self, doc):
        # nv
        d = _token_to_dict(doc[0])
        assert d["is_alpha"] is True

    def test_pos_propn(self, doc):
        # nv
        d = _token_to_dict(doc[0])
        assert d["pos"] == "PROPN"


class TestEntToDict:
    def test_keys(self, doc):
        # nv
        ents = list(doc.ents)
        assert ents, "Expected at least one entity in test sentence"
        d = _ent_to_dict(ents[0])
        assert set(d) == {"text", "label", "start", "end", "start_char", "end_char"}

    def test_apple_org(self, doc):
        # nv
        org_ents = [_ent_to_dict(e) for e in doc.ents if e.label_ == "ORG"]
        assert any(e["text"] == chars("Apple") for e in org_ents)


class TestChunkToDict:
    def test_keys(self, doc):
        # nv
        chunks = list(doc.noun_chunks)
        assert chunks, "Expected at least one noun chunk"
        d = _chunk_to_dict(chunks[0])
        assert set(d) == {"text", "root_text", "root_dep", "root_head_text"}

    def test_apple_chunk(self, doc):
        # nv
        chunks = [_chunk_to_dict(c) for c in doc.noun_chunks]
        assert any(c["text"] == chars("Apple") for c in chunks)


# ══════════════════════════════════════════════════════════════════════════════
# Unit tests: model registry
# ══════════════════════════════════════════════════════════════════════════════


class TestModelRegistry:
    def test_get_known_model(self):
        # nv
        nlp = _get_model(_ALIAS)
        assert nlp is not None

    def test_get_unknown_raises(self):
        # nv
        with pytest.raises(ValueError, match="No spaCy model"):
            _get_model("__no_such_model__")

    def test_load_model_1(self, trail):
        # nv
        alias = "_test_load1_"
        with _LOCK:
            _MODELS.pop(alias, None)
        # load_model/1 uses name as alias
        results = list(_solutions_simple(_load_model_1_raw, "en_core_web_sm", trail=trail))
        assert len(results) == 1
        # Clean up
        with _LOCK:
            _MODELS.pop("en_core_web_sm", None)

    def test_load_model_2(self, trail):
        # nv
        alias = "_test_load2_"
        with _LOCK:
            _MODELS.pop(alias, None)
        from clausal.modules.py.spacy import _load_model_2
        results = list(_load_model_2("en_core_web_sm", alias, trail, None))
        assert len(results) == 1
        with _LOCK:
            assert alias in _MODELS
            _MODELS.pop(alias)

    def test_load_model_2_idempotent(self, trail):
        # nv
        alias = "_test_idem_"
        from clausal.modules.py.spacy import _load_model_2
        with _LOCK:
            _MODELS.pop(alias, None)
        list(_load_model_2("en_core_web_sm", alias, trail, None))
        list(_load_model_2("en_core_web_sm", alias, trail, None))
        with _LOCK:
            assert alias in _MODELS
            _MODELS.pop(alias)

    def test_unload_model(self, trail):
        # nv
        alias = "_test_unload_"
        nlp = spacy.load("en_core_web_sm")
        with _LOCK:
            _MODELS[alias] = nlp
        from clausal.modules.py.spacy import _unload_model_1
        results = list(_unload_model_1(alias, trail, None))
        assert len(results) == 1
        with _LOCK:
            assert alias not in _MODELS

    def test_unload_nonexistent_fails(self, trail):
        # nv
        from clausal.modules.py.spacy import _unload_model_1
        results = list(_unload_model_1("__missing__", trail, None))
        assert results == []

    def test_current_model_enumerate(self, trail):
        # nv
        result_var = Var()
        results = []
        sentinel = object()
        from clausal.modules.py.spacy import _current_model_1
        from clausal.logic.trampoline import DONE
        for parent, val in _current_model_1(sentinel, sentinel, sentinel, sentinel, result_var, trail):
            if val is DONE:
                break
            results.append(deref(result_var))
        assert _ALIAS in results

    def test_current_model_check_known(self, trail):
        # nv
        sentinel = object()
        from clausal.modules.py.spacy import _current_model_1
        from clausal.logic.trampoline import DONE
        found = False
        for parent, val in _current_model_1(sentinel, sentinel, sentinel, sentinel, _ALIAS, trail):
            if val is DONE:
                break
            found = True
        assert found

    def test_current_model_check_unknown(self, trail):
        # nv
        sentinel = object()
        from clausal.modules.py.spacy import _current_model_1
        from clausal.logic.trampoline import DONE
        found = False
        for parent, val in _current_model_1(sentinel, sentinel, sentinel, sentinel, "__no__", trail):
            if val is DONE:
                break
            found = True
        assert not found


# helper used in test_load_model_1
def _load_model_1_raw(name, trail, k):
    from clausal.modules.py.spacy import _load_model_1
    yield from _load_model_1(name, trail, k)


# ══════════════════════════════════════════════════════════════════════════════
# Unit tests: document processing
# ══════════════════════════════════════════════════════════════════════════════


class TestProcess:
    def test_process_returns_doc(self, trail):
        # nv
        from clausal.modules.py.spacy import _process_3
        result = Var()
        results = list(_process_3(_ALIAS, _TEXT, result, trail, None))
        assert len(results) == 1
        processed = deref(result)
        assert len(processed) > 0

    def test_process_unknown_alias(self, trail):
        # nv
        from clausal.modules.py.spacy import _process_3
        result = Var()
        with pytest.raises(ValueError):
            list(_process_3("__bad__", _TEXT, result, trail, None))


# ══════════════════════════════════════════════════════════════════════════════
# Unit tests: token predicates
# ══════════════════════════════════════════════════════════════════════════════


class TestTokenPredicates:
    def test_token_2_yields_multiple(self, doc, trail):
        # nv
        from clausal.modules.py.spacy import _token_2
        tok_var = Var()
        sentinel = object()
        from clausal.logic.trampoline import DONE
        count = 0
        for parent, val in _token_2(sentinel, sentinel, sentinel, sentinel, doc, tok_var, trail):
            if val is DONE:
                break
            count += 1
        assert count == len(doc)

    def test_token_2_first_is_apple(self, doc, trail):
        # nv
        from clausal.modules.py.spacy import _token_2
        tok_var = Var()
        sentinel = object()
        from clausal.logic.trampoline import DONE
        first = None
        for parent, val in _token_2(sentinel, sentinel, sentinel, sentinel, doc, tok_var, trail):
            if val is DONE:
                break
            first = deref(tok_var)
            break
        assert first is not None
        assert first["text"] == chars("Apple")

    def test_token_3_by_index(self, doc, trail):
        # nv
        from clausal.modules.py.spacy import _token_3
        tok_var = Var()
        sentinel = object()
        from clausal.logic.trampoline import DONE
        result = None
        for parent, val in _token_3(sentinel, sentinel, sentinel, sentinel, doc, 0, tok_var, trail):
            if val is DONE:
                break
            result = deref(tok_var)
            break
        assert result is not None
        assert result["text"] == chars("Apple")

    def test_token_3_out_of_range(self, doc, trail):
        # nv
        from clausal.modules.py.spacy import _token_3
        tok_var = Var()
        sentinel = object()
        from clausal.logic.trampoline import DONE
        found = False
        for parent, val in _token_3(sentinel, sentinel, sentinel, sentinel, doc, 9999, tok_var, trail):
            if val is DONE:
                break
            found = True
        assert not found

    def test_token_3_iterate_with_index(self, doc, trail):
        # nv
        from clausal.modules.py.spacy import _token_3
        idx_var = Var()
        tok_var = Var()
        sentinel = object()
        from clausal.logic.trampoline import DONE
        pairs = []
        for parent, val in _token_3(sentinel, sentinel, sentinel, sentinel, doc, idx_var, tok_var, trail):
            if val is DONE:
                break
            pairs.append((deref(idx_var), deref(tok_var)["text"]))
            trail.undo(trail.mark())
        assert len(pairs) == len(doc)
        assert pairs[0] == (0, chars("Apple"))

    def test_token_text(self, doc, trail):
        # nv
        from clausal.modules.py.spacy import _token_text_2
        tok = _token_to_dict(doc[0])
        result = Var()
        results = list(_token_text_2(tok, result, trail, None))
        assert len(results) == 1
        assert deref(result) == chars("Apple")   # token text: a STRING

    def test_token_list(self, doc, trail):
        # nv
        from clausal.modules.py.spacy import _token_list_2
        result = Var()
        results = list(_token_list_2(doc, result, trail, None))
        assert len(results) == 1
        lst = deref(result)
        assert isinstance(lst, list)
        assert len(lst) == len(doc)
        assert lst[0]["text"] == chars("Apple")


# ══════════════════════════════════════════════════════════════════════════════
# Unit tests: annotation predicates
# ══════════════════════════════════════════════════════════════════════════════


class TestAnnotationPredicates:
    @pytest.fixture
    def apple_tok(self, doc):
        return _token_to_dict(doc[0])  # "Apple"

    @pytest.fixture
    def looking_tok(self, doc):
        return _token_to_dict(doc[2])  # "looking"

    def test_pos(self, apple_tok, trail):
        # nv
        from clausal.modules.py.spacy import _pos_2
        result = Var()
        results = list(_pos_2(apple_tok, result, trail, None))
        assert len(results) == 1
        assert deref(result) == "PROPN"

    def test_lemma(self, looking_tok, trail):
        # nv
        from clausal.modules.py.spacy import _lemma_2
        result = Var()
        results = list(_lemma_2(looking_tok, result, trail, None))
        assert len(results) == 1
        assert deref(result) == "look"

    def test_dep(self, apple_tok, trail):
        # nv
        from clausal.modules.py.spacy import _dep_2
        result = Var()
        results = list(_dep_2(apple_tok, result, trail, None))
        assert len(results) == 1
        assert isinstance(deref(result), str)

    def test_head(self, apple_tok, trail):
        # nv
        from clausal.modules.py.spacy import _head_2
        result = Var()
        results = list(_head_2(apple_tok, result, trail, None))
        assert len(results) == 1
        # Free-form text is a STRING (the chars carrier), not an atom: see
        # test_spacy_free_form_outputs_stubbed.py.  "Apple" heads to "looking".
        assert deref(result) == chars("looking")

    def test_shape(self, apple_tok, trail):
        # nv
        from clausal.modules.py.spacy import _shape_2
        result = Var()
        results = list(_shape_2(apple_tok, result, trail, None))
        assert len(results) == 1
        assert deref(result) == "Xxxxx"

    def test_is_alpha_true(self, apple_tok, trail):
        # nv
        from clausal.modules.py.spacy import _is_alpha_1
        results = list(_is_alpha_1(apple_tok, trail, None))
        assert len(results) == 1

    def test_is_alpha_false_for_punctuation(self, doc, trail):
        # nv
        from clausal.modules.py.spacy import _is_alpha_1
        # Find the "$" or "." token
        punct_tok = None
        for tok in doc:
            if not tok.is_alpha:
                punct_tok = _token_to_dict(tok)
                break
        assert punct_tok is not None
        results = list(_is_alpha_1(punct_tok, trail, None))
        assert results == []

    def test_is_stop(self, doc, trail):
        # nv
        from clausal.modules.py.spacy import _is_stop_1
        # "is" should be a stop word
        for tok in doc:
            if tok.is_stop:
                d = _token_to_dict(tok)
                results = list(_is_stop_1(d, trail, None))
                assert len(results) == 1
                return
        pytest.skip("No stop words found in test sentence")


# ══════════════════════════════════════════════════════════════════════════════
# Unit tests: NER predicates
# ══════════════════════════════════════════════════════════════════════════════


class TestNERPredicates:
    def test_entity_2_yields_entities(self, doc, trail):
        # nv
        from clausal.modules.py.spacy import _entity_2
        ent_var = Var()
        sentinel = object()
        from clausal.logic.trampoline import DONE
        entities = []
        for parent, val in _entity_2(sentinel, sentinel, sentinel, sentinel, doc, ent_var, trail):
            if val is DONE:
                break
            entities.append(deref(ent_var))
        assert len(entities) == len(doc.ents)
        assert any(e["text"] == chars("Apple") for e in entities)

    def test_entity_3_filter_by_label(self, doc, trail):
        # nv
        from clausal.modules.py.spacy import _entity_3
        ent_var = Var()
        sentinel = object()
        from clausal.logic.trampoline import DONE
        org_ents = []
        for parent, val in _entity_3(sentinel, sentinel, sentinel, sentinel, doc, "ORG", ent_var, trail):
            if val is DONE:
                break
            org_ents.append(deref(ent_var))
        assert any(e["text"] == chars("Apple") for e in org_ents)
        assert all(e["label"] == "ORG" for e in org_ents)

    def test_entity_3_unknown_label_empty(self, doc, trail):
        # nv
        from clausal.modules.py.spacy import _entity_3
        ent_var = Var()
        sentinel = object()
        from clausal.logic.trampoline import DONE
        found = False
        for parent, val in _entity_3(sentinel, sentinel, sentinel, sentinel, doc, "NONEXISTENT_LABEL", ent_var, trail):
            if val is DONE:
                break
            found = True
        assert not found

    def test_entity_list(self, doc, trail):
        # nv
        from clausal.modules.py.spacy import _entity_list_2
        result = Var()
        results = list(_entity_list_2(doc, result, trail, None))
        assert len(results) == 1
        lst = deref(result)
        assert isinstance(lst, list)
        assert any(e["text"] == chars("Apple") for e in lst)


# ══════════════════════════════════════════════════════════════════════════════
# Unit tests: sentence predicates
# ══════════════════════════════════════════════════════════════════════════════


class TestSentencePredicates:
    def test_sentence_2_yields_sentences(self, doc, trail):
        # nv
        from clausal.modules.py.spacy import _sentence_2
        sent_var = Var()
        sentinel = object()
        from clausal.logic.trampoline import DONE
        sents = []
        for parent, val in _sentence_2(sentinel, sentinel, sentinel, sentinel, doc, sent_var, trail):
            if val is DONE:
                break
            sents.append(deref(sent_var))
        assert len(sents) > 0
        assert sents[0] == chars(_TEXT)   # a sentence: a STRING

    def test_sentence_list(self, doc, trail):
        # nv
        from clausal.modules.py.spacy import _sentence_list_2
        result = Var()
        results = list(_sentence_list_2(doc, result, trail, None))
        assert len(results) == 1
        lst = deref(result)
        assert isinstance(lst, list)
        assert lst[0] == chars(_TEXT)


# ══════════════════════════════════════════════════════════════════════════════
# Unit tests: similarity
# ══════════════════════════════════════════════════════════════════════════════


class TestSimilarity:
    def test_identical_texts(self, trail):
        # nv
        from clausal.modules.py.spacy import _similarity_4
        score = Var()
        results = list(_similarity_4(_ALIAS, "dog", "dog", score, trail, None))
        assert len(results) == 1
        s = deref(score)
        assert isinstance(s, float)
        assert s == pytest.approx(1.0, abs=1e-6)

    def test_score_is_float(self, trail):
        # nv
        from clausal.modules.py.spacy import _similarity_4
        score = Var()
        results = list(_similarity_4(_ALIAS, "cat", "dog", score, trail, None))
        assert len(results) == 1
        s = deref(score)
        assert isinstance(s, float)
        assert 0.0 <= s <= 1.0


# ══════════════════════════════════════════════════════════════════════════════
# Unit tests: noun chunk predicates
# ══════════════════════════════════════════════════════════════════════════════


class TestNounChunks:
    def test_noun_chunk_2_yields_chunks(self, doc, trail):
        # nv
        from clausal.modules.py.spacy import _noun_chunk_2
        chunk_var = Var()
        sentinel = object()
        from clausal.logic.trampoline import DONE
        chunks = []
        for parent, val in _noun_chunk_2(sentinel, sentinel, sentinel, sentinel, doc, chunk_var, trail):
            if val is DONE:
                break
            chunks.append(deref(chunk_var))
        assert len(chunks) == len(list(doc.noun_chunks))
        assert any(c["text"] == chars("Apple") for c in chunks)

    def test_noun_chunk_has_keys(self, doc, trail):
        # nv
        from clausal.modules.py.spacy import _noun_chunk_2
        chunk_var = Var()
        sentinel = object()
        from clausal.logic.trampoline import DONE
        for parent, val in _noun_chunk_2(sentinel, sentinel, sentinel, sentinel, doc, chunk_var, trail):
            if val is DONE:
                break
            c = deref(chunk_var)
            assert set(c) == {"text", "root_text", "root_dep", "root_head_text"}
            break


# ══════════════════════════════════════════════════════════════════════════════
# Unit tests: predicate adapter (_SpacyPredicate)
# ══════════════════════════════════════════════════════════════════════════════


class TestSpacyPredicateAdapter:
    def test_single_arity_dispatch_direct(self):
        """Single-arity predicate returns its fn directly."""
        # nv
        disp = unload_model._get_dispatch()
        assert callable(disp)

    def test_multi_arity_dispatch_is_multi(self):
        """Multi-arity predicate returns _multi_dispatch."""
        # nv
        disp = load_model._get_dispatch()
        assert callable(disp)

    def test_repr(self):
        # nv
        assert "load_model" in repr(load_model)

    def test_multi_dispatch_wrong_arity_fails(self, trail):
        """Multi-dispatch returns DONE for unrecognised arity."""
        # nv
        from clausal.logic.trampoline import DONE
        sentinel = object()
        results = list(load_model._multi_dispatch(sentinel, sentinel, sentinel, sentinel, trail))
        # arity 0 (just trail) not registered — should yield DONE immediately
        last = results[-1]
        assert last[1] is DONE


# ══════════════════════════════════════════════════════════════════════════════
# Fixture integration: tests/fixtures/spacy_basic.seam
# ══════════════════════════════════════════════════════════════════════════════

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(name):
    path = os.path.join(_FIXTURE_DIR, f"{name}{SEAM_SUFFIX}")
    mod = _load_module(name, path)
    return mod.__dict__["$module"]


def _succeeds(functor, *args, module):
    for _ in call(functor, *args, module=module):
        return True
    return False


class TestSpacyBasicFixture:
    """Run Test/1 predicates from tests/fixtures/spacy_basic.seam."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("spacy_basic")

    @pytest.mark.parametrize("name", [
        "load model",
        "load model idempotent",
        "current model",
        "token iteration",
        "token by index",
        "token list",
        "pos tag",
        "lemma",
        "dep label",
        "shape",
        "is alpha",
        "entity iteration",
        "entity by label",
        "entity list",
        "sentence iteration",
        "sentence list",
        "noun chunk",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("test", chars(name), module=self.mod)   # test names are strings
