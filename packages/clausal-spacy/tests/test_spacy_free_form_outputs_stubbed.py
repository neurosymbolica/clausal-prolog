"""Text a spaCy document holds is a STRING; linguistic labels stay ATOMS.

Ruled 2026-10-04 (adapters are their own entry point, strings spec 9.4):
token ``text`` and ``head_text``, entity and chunk ``text``, a chunk's
``root_text`` / ``root_head_text``, ``token_text/2``, ``head/2``,
``sentence/2`` and ``sentence_list/2`` are free-form text, the string
``('$chars', s)``.  ``lemma`` (ruled an atom), ``pos``, ``tag``, ``dep``,
an entity ``label``, a chunk ``root_dep`` and a token's ``shape`` (ruled
an atom the same day) stay atoms (plain ``str``).

Runs WITHOUT spaCy (``*_stubbed.py``, see packages/conftest.py): a fake
``spacy`` module (``_get_spacy``) whose ``load`` returns a pipeline that
annotates the package's test sentence the way en_core_web_sm does, as far
as the tests look.  The same fake runs the package's two ``.seam``
fixtures, which compare text with strings and labels with atoms.
"""

from __future__ import annotations

import os
import re
import types

import pytest

from clausal._suffixes import SEAM_SUFFIX
from clausal.import_hook import _load_module
from clausal.logic.cells import chars, is_chars
from clausal.logic.solve import call
from clausal.logic.trampoline import DONE
from clausal.logic.variables import Trail, Var, deref
from clausal.modules.py import spacy as pyspacy

_TEXT = "Apple is looking at buying U.K. startup for $1 billion."

#             text       lemma     pos      tag    dep       head  shape   stop
_TOKENS = [("Apple",   "Apple",  "PROPN", "NNP", "nsubj",    2, "Xxxxx", False),
           ("is",      "be",     "AUX",   "VBZ", "aux",      2, "xx",    True),
           ("looking", "look",   "VERB",  "VBG", "ROOT",     2, "xxxx",  False),
           ("at",      "at",     "ADP",   "IN",  "prep",     2, "xx",    True),
           ("buying",  "buy",    "VERB",  "VBG", "pcomp",    3, "xxxx",  False),
           ("U.K.",    "U.K.",   "PROPN", "NNP", "compound", 6, "X.X.",  False),
           ("startup", "startup", "NOUN", "NN",  "dobj",     4, "xxxx",  False),
           ("for",     "for",    "ADP",   "IN",  "prep",     4, "xxx",   True),
           ("$",       "$",      "SYM",   "$",   "quantmod", 10, "$",    False),
           ("1",       "1",      "NUM",   "CD",  "compound", 10, "d",    False),
           ("billion", "billion", "NUM",  "CD",  "pobj",     7, "xxxx",  False),
           (".",       ".",      "PUNCT", ".",   "punct",    2, ".",     False)]


class _Tok:
    def __init__(self, doc, i, row):
        self.doc, self.i = doc, i
        (self.text, self.lemma_, self.pos_, self.tag_, self.dep_,
         self._head, self.shape_, self.is_stop) = row
        self.is_alpha = self.text.isalpha()

    @property
    def head(self):
        return self.doc[self._head]


class _Span:
    def __init__(self, doc, start, end, label=""):
        self.doc, self.start, self.end, self.label_ = doc, start, end, label
        toks = doc._toks[start:end]
        self.text = " ".join(t.text for t in toks).replace("$ 1", "$1")
        self.start_char = _TEXT.find(self.text)
        self.end_char = self.start_char + len(self.text)

    @property
    def root(self):
        return self.doc[self.end - 1]


class _Doc:
    def __init__(self, text):
        self.text = text
        self._toks = [_Tok(self, i, row) for i, row in enumerate(_TOKENS)]

    def __iter__(self):
        return iter(self._toks)

    def __len__(self):
        return len(self._toks)

    def __getitem__(self, i):
        return self._toks[i]

    @property
    def ents(self):
        return [_Span(self, 0, 1, "ORG"), _Span(self, 5, 6, "GPE"),
                _Span(self, 8, 11, "MONEY")]

    @property
    def sents(self):
        return [types.SimpleNamespace(text=self.text)]

    @property
    def noun_chunks(self):
        return [_Span(self, 0, 1), _Span(self, 5, 7)]

    def similarity(self, other):
        return 0.5


@pytest.fixture
def fake_spacy(monkeypatch):
    fake = types.SimpleNamespace(load=lambda name: _Doc)
    monkeypatch.setattr(pyspacy, "_get_spacy", lambda: fake)
    monkeypatch.setattr(pyspacy, "_MODELS", {})
    return fake


@pytest.fixture
def doc():
    return _Doc(_TEXT)


def _simple(fn, *args):
    out = Var()
    assert len(list(fn(*args, out, Trail(), None))) == 1
    return deref(out)


def _nondet(fn, *args):
    out, got, s = Var(), [], object()
    for _parent, val in fn(s, s, s, s, *args, out, Trail()):
        if val is DONE:
            break
        got.append(deref(out))
    return got


def test_token_dict_text_is_a_string_labels_atoms(doc):
    d = pyspacy._token_to_dict(doc[0])
    assert d["text"] == chars("Apple") and d["head_text"] == chars("looking")
    for key, want in (("lemma", "Apple"), ("pos", "PROPN"), ("tag", "NNP"),
                      ("dep", "nsubj"), ("shape", "Xxxxx")):
        assert type(d[key]) is str and d[key] == want, key
    assert all(type(k) is str for k in d)


def test_token_text_and_head_are_strings(doc):
    tok = pyspacy._token_to_dict(doc[2])
    assert _simple(pyspacy._token_text_2, tok) == chars("looking")
    assert _simple(pyspacy._head_2, pyspacy._token_to_dict(doc[0])) == chars("looking")
    assert _simple(pyspacy._lemma_2, tok) == "look"     # lemma: an ATOM (ruled)


def test_entity_text_is_a_string_label_an_atom(doc):
    ents = _nondet(pyspacy._entity_2, doc)
    assert [e["text"] for e in ents] == [chars("Apple"), chars("U.K."), chars("$1 billion")]
    assert [e["label"] for e in ents] == ["ORG", "GPE", "MONEY"]
    assert all(type(e["label"]) is str for e in ents)


def test_chunk_texts_are_strings_root_dep_an_atom(doc):
    [c, _] = _nondet(pyspacy._noun_chunk_2, doc)
    assert c["text"] == chars("Apple") and c["root_text"] == chars("Apple")
    assert c["root_head_text"] == chars("looking")
    assert type(c["root_dep"]) is str and c["root_dep"] == "nsubj"


def test_sentences_are_strings(doc):
    assert _nondet(pyspacy._sentence_2, doc) == [chars(_TEXT)]
    assert _simple(pyspacy._sentence_list_2, doc) == [chars(_TEXT)]


_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _fixture_cases():
    for rel in ("spacy_basic", os.path.join("docs", "spacy_sig_tests")):
        src = open(os.path.join(_FIXTURES, rel + SEAM_SUFFIX), encoding="utf-8").read()
        for name in re.findall(r'^test\("([^"]+)"\)', src, re.M):
            yield rel, name


@pytest.mark.parametrize("rel,name", list(_fixture_cases()))
def test_seam_fixtures_under_the_fake(fake_spacy, rel, name):
    mod_name = "spacy_ff_" + os.path.basename(rel)
    mod = _load_module(mod_name, os.path.join(_FIXTURES, rel + SEAM_SUFFIX))
    assert any(True for _ in call("test", chars(name), module=mod.__dict__["$module"])), name


# ── Check mode is STRICT (ruled 2026-10-04) ──────────────────────────────────
#
# A bound result is compared as a TERM: the string "looking" is what
# token_text/2 answers, and the atom 'looking' -- the same spelling -- is a
# different term, so check mode with it FAILS (ISO: a string is no atom).
# Pinned here so neither side can drift into a text-level comparison.

_CHECK_SRC = """\
-import_from(spacy, [load_model, process, token, token_text])

doc_tok(TOK) <- (load_model("en_core_web_sm", "check"), process("check", "Apple is looking at buying U.K. startup for $1 billion.", DOC), token(DOC, 2, TOK))
check_string() <- (doc_tok(TOK), token_text(TOK, "looking"))
check_atom() <- (doc_tok(TOK), token_text(TOK, 'looking'))
"""


@pytest.fixture
def check_module(fake_spacy, tmp_path):
    src = tmp_path / f"spacy_check_probe{SEAM_SUFFIX}"
    src.write_text(_CHECK_SRC, encoding="utf-8")
    return _load_module("spacy_check_probe", str(src)).__dict__["$module"]


def test_check_mode_takes_the_string_not_the_atom(check_module):
    assert any(True for _ in call("check_string", module=check_module))
    assert not any(True for _ in call("check_atom", module=check_module))


# ── shape is an ATOM (ruled 2026-10-04) ──────────────────────────────────────

@pytest.mark.parametrize("i, want", [(0, "Xxxxx"), (5, "X.X."), (9, "d")])
def test_shape_is_an_atom(doc, i, want):
    tok = pyspacy._token_to_dict(doc[i])
    assert type(tok["shape"]) is str and tok["shape"] == want
    got = _simple(pyspacy._shape_2, tok)
    assert type(got) is str and not is_chars(got) and got == want
    # check mode: the atom holds, the string of the same spelling does not
    assert len(list(pyspacy._shape_2(tok, want, Trail(), None))) == 1
    assert list(pyspacy._shape_2(tok, chars(want), Trail(), None)) == []
