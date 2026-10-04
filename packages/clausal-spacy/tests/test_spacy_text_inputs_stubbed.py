"""Text arguments accept a STRING as well as an atom (spec §9.4, "text in").

``process/3`` text, ``similarity/4`` texts, ``entity/3`` label and the
model name/alias of ``load_model/1,2``, ``unload_model/1``,
``current_model/1`` were read with ``str(deref(x))``, so a string -- the
chars carrier ``('$chars', s)`` -- reached spaCy as the repr
``"('$chars', 's')"``.

Runs WITHOUT spaCy (``*_stubbed.py``, see packages/conftest.py): the
adapter imports spaCy lazily, so a fake ``nlp`` callable registered under
an alias and a fake ``spacy.load`` record exactly the ``str`` the adapter
hands the library.
"""

from __future__ import annotations

import types

import pytest

from clausal.logic.cells import chars
from clausal.logic.exceptions import LogicException
from clausal.logic.variables import Trail, Var, deref
from clausal.modules.py import spacy as pyspacy


class _Ent:
    def __init__(self, label):
        self.text, self.label_ = "Ada", label
        self.start, self.end, self.start_char, self.end_char = 0, 1, 0, 3


class _Doc:
    def __init__(self, text):
        self.text = text
        self.ents = [_Ent("PERSON"), _Ent("ORG")]

    def similarity(self, other):
        return 1.0 if self.text == other.text else 0.0


class _Nlp:
    def __init__(self):
        self.seen = []

    def __call__(self, text):
        self.seen.append(text)
        return _Doc(text)


@pytest.fixture
def nlp(monkeypatch):
    fake = _Nlp()
    monkeypatch.setattr(pyspacy, "_MODELS", {"m": fake})
    return fake


def _simple(fn, *args):
    return list(fn(*args, Trail(), None))


def _nondet(fn, *args):
    proceed, fail = object(), object()
    return [s for s in fn(None, proceed, fail, None, *args, Trail())
            if s[0] is proceed]


@pytest.mark.parametrize("text", [chars("Ada Lovelace"), "Ada Lovelace"])
@pytest.mark.parametrize("alias", [chars("m"), "m"])
def test_process_hands_spacy_the_text(nlp, text, alias):
    d = Var()
    assert len(_simple(pyspacy._process_3, alias, text, d)) == 1
    assert nlp.seen == ["Ada Lovelace"]


def test_process_of_a_compound_is_a_type_error(nlp):
    with pytest.raises(LogicException) as info:
        _simple(pyspacy._process_3, "m", ("f", 1), Var())
    assert info.value.term[1][:2] == ("type_error", "text")
    assert nlp.seen == []


@pytest.mark.parametrize("label", [chars("ORG"), "ORG"])
def test_entity_label_may_be_a_string(nlp, label):
    doc = _Doc("x")
    e = Var()
    assert len(_nondet(pyspacy._entity_3, doc, label, e)) == 1


def test_similarity_hands_spacy_the_texts(nlp):
    s = Var()
    assert len(_simple(pyspacy._similarity_4, chars("m"),
                       chars("a b"), "a b", s)) == 1
    assert nlp.seen == ["a b", "a b"] and deref(s) == 1.0


def test_load_model_name_and_alias_may_be_strings(monkeypatch):
    loaded = []
    fake_spacy = types.SimpleNamespace(load=lambda n: loaded.append(n) or _Nlp())
    monkeypatch.setattr(pyspacy, "_get_spacy", lambda: fake_spacy)
    monkeypatch.setattr(pyspacy, "_MODELS", {})
    _simple(pyspacy._load_model_1, chars("en_core_web_sm"))
    _simple(pyspacy._load_model_2, chars("en_core_web_md"), chars("md"))
    assert loaded == ["en_core_web_sm", "en_core_web_md"]
    assert sorted(pyspacy._MODELS) == ["en_core_web_sm", "md"]
    assert len(_nondet(pyspacy._current_model_1, chars("md"))) == 1
    assert len(_simple(pyspacy._unload_model_1, chars("md"))) == 1
    assert sorted(pyspacy._MODELS) == ["en_core_web_sm"]
