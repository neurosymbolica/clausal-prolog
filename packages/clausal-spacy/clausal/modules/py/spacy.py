"""clausal.modules.py.spacy — spaCy NLP predicates for Clausal.

Provides load_model, unload_model, current_model, process, token, token_text,
token_list, pos, tag, lemma, dep, head, shape, is_alpha, is_stop, entity,
entity_list, sentence, sentence_list, similarity, noun_chunk as importable
predicate objects for use in .clausal files via::

    -import_from(spacy, [load_model, process, token, entity, ...])

Layers
------
1. **Model management** — load_model/1,2, unload_model/1, current_model/1
2. **Document processing** — process/3
3. **Tokens** — token/2,3, token_text/2, token_list/2
4. **Annotations** — pos/2, tag/2, lemma/2, dep/2, head/2, shape/2,
   is_alpha/1, is_stop/1
5. **NER** — entity/2,3, entity_list/2
6. **Sentences** — sentence/2, sentence_list/2
7. **Similarity** — similarity/4
8. **Noun chunks** — noun_chunk/2
"""

from __future__ import annotations

import threading as _threading
from typing import Any, Callable

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.trampoline import DONE


def _get_spacy():
    """Lazy spaCy import — defers the import until first use."""
    try:
        import spacy as _spacy
        return _spacy
    except Exception as exc:
        raise ImportError(
            "spaCy is required for clausal.modules.py.spacy. "
            "Install it with: pip install spacy"
        ) from exc


# ── Model registry ────────────────────────────────────────────────────────

_MODELS: dict[str, spacy.language.Language] = {}
_LOCK = _threading.Lock()


def _get_model(alias: str) -> spacy.language.Language:
    """Look up a loaded model by alias; raise if not found."""
    alias = str(alias)
    nlp = _MODELS.get(alias)
    if nlp is None:
        raise ValueError(f"No spaCy model with alias {alias!r}")
    return nlp


# ── Dispatch adapter ──────────────────────────────────────────────────────

class _SpacyPredicate:
    """Adapter with ``_get_dispatch()`` for a spaCy predicate.

    Supports multi-arity dispatch (e.g. load_model/1 + load_model/2).
    """

    __slots__ = ("_name", "_dispatch_fns")

    def __init__(self, name: str) -> None:
        self._name = name
        self._dispatch_fns: dict[int, Callable] = {}

    def _register(self, arity: int, fn: Callable) -> None:
        self._dispatch_fns[arity] = fn

    def _get_dispatch(self) -> Callable:
        if len(self._dispatch_fns) == 1:
            return next(iter(self._dispatch_fns.values()))
        return self._multi_dispatch

    def _multi_dispatch(self, this_generator, _proceed, _fail, _catcher, *args):
        arity = len(args) - 1  # exclude trail
        fn = self._dispatch_fns.get(arity)
        if fn is None:
            yield (_fail, DONE)
            return
        yield from fn(this_generator, _proceed, _fail, _catcher, *args)

    def __repr__(self) -> str:
        arities = sorted(self._dispatch_fns)
        return f"spacy.{self._name}/{arities}"


# ── Simple-mode wrapper ──────────────────────────────────────────────────

def _simple_to_trampoline(simple_fn):
    """Wrap a simple-mode fn(*args, trail, k) → trampoline protocol."""
    def trampoline_fn(this_generator, _proceed, _fail, _catcher, *args):
        for _ in simple_fn(*args, None):
            yield (_proceed, None)
        yield (_fail, DONE)
    return trampoline_fn


# ── Helpers: spaCy objects → dicts ────────────────────────────────────────

def _token_to_dict(tok) -> dict:
    """Convert a spaCy token to a plain dict."""
    return {
        "text": tok.text,
        "lemma": tok.lemma_,
        "pos": tok.pos_,
        "tag": tok.tag_,
        "dep": tok.dep_,
        "head_text": tok.head.text,
        "head_i": tok.head.i,
        "i": tok.i,
        "is_alpha": tok.is_alpha,
        "is_stop": tok.is_stop,
        "shape": tok.shape_,
    }


def _ent_to_dict(ent) -> dict:
    """Convert a spaCy span (entity) to a plain dict."""
    return {
        "text": ent.text,
        "label": ent.label_,
        "start": ent.start,
        "end": ent.end,
        "start_char": ent.start_char,
        "end_char": ent.end_char,
    }


def _chunk_to_dict(chunk) -> dict:
    """Convert a spaCy noun chunk span to a plain dict."""
    return {
        "text": chunk.text,
        "root_text": chunk.root.text,
        "root_dep": chunk.root.dep_,
        "root_head_text": chunk.root.head.text,
    }


# ── Layer 1: Model management ────────────────────────────────────────────

def _load_model_1(name, trail, k):
    """load_model/1: load a spaCy model, alias defaults to name."""
    name = deref(name)
    name_str = str(name)
    with _LOCK:
        if name_str not in _MODELS:
            nlp = _get_spacy().load(name_str)
            _MODELS[name_str] = nlp
    yield None


def _load_model_2(name, alias, trail, k):
    """load_model/2: load a spaCy model under a given alias."""
    name = deref(name)
    alias = deref(alias)
    name_str = str(name)
    alias_str = str(alias)
    with _LOCK:
        if alias_str not in _MODELS:
            nlp = _get_spacy().load(name_str)
            _MODELS[alias_str] = nlp
    yield None


def _unload_model_1(alias, trail, k):
    """unload_model/1: remove a model from the registry."""
    alias = deref(alias)
    alias_str = str(alias)
    with _LOCK:
        nlp = _MODELS.pop(alias_str, None)
    if nlp is None:
        return  # fail — no such model
    yield None


def _current_model_1(this_generator, _proceed, _fail, _catcher, alias, trail):
    """current_model/1: enumerate registered model aliases."""
    alias = deref(alias)
    if not is_var(alias):
        if str(alias) in _MODELS:
            yield (_proceed, None)
        yield (_fail, DONE)
        return
    with _LOCK:
        aliases = list(_MODELS.keys())
    for a in aliases:
        mark = trail.mark()
        if unify(alias, a, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


# ── Layer 2: Document processing ─────────────────────────────────────────

def _process_3(alias, text, doc_var, trail, k):
    """process/3: run text through a model, unify result Doc."""
    alias = deref(alias)
    text = deref(text)
    nlp = _get_model(alias)
    doc = nlp(str(text))
    if unify(doc_var, doc, trail):
        yield None


# ── Layer 3: Tokens ──────────────────────────────────────────────────────

def _token_2(this_generator, _proceed, _fail, _catcher, doc, tok_var, trail):
    """token/2: backtrack over all tokens in a Doc."""
    doc = deref(doc)
    for tok in doc:
        mark = trail.mark()
        d = _token_to_dict(tok)
        if unify(tok_var, d, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


def _token_3(this_generator, _proceed, _fail, _catcher, doc, index, tok_var, trail):
    """token/3: get token by index, or iterate with index."""
    doc = deref(doc)
    index = deref(index)
    if not is_var(index):
        # Specific index
        idx = int(index)
        if 0 <= idx < len(doc):
            mark = trail.mark()
            d = _token_to_dict(doc[idx])
            if unify(tok_var, d, trail):
                yield (_proceed, None)
            trail.undo(mark)
        yield (_fail, DONE)
        return
    # Iterate all with index
    for tok in doc:
        mark = trail.mark()
        d = _token_to_dict(tok)
        if unify(index, tok.i, trail) and unify(tok_var, d, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


def _token_text_2(tok, text_var, trail, k):
    """token_text/2: extract text from a token dict."""
    tok = deref(tok)
    text = tok["text"]
    if unify(text_var, text, trail):
        yield None


def _token_list_2(doc, tokens_var, trail, k):
    """token_list/2: all tokens as a list of dicts."""
    doc = deref(doc)
    tokens = [_token_to_dict(tok) for tok in doc]
    if unify(tokens_var, tokens, trail):
        yield None


# ── Layer 4: Annotations ─────────────────────────────────────────────────

def _pos_2(tok, tag_var, trail, k):
    """pos/2: coarse pos tag from token dict."""
    tok = deref(tok)
    if unify(tag_var, tok["pos"], trail):
        yield None


def _tag_2(tok, tag_var, trail, k):
    """tag/2: fine-grained pos tag from token dict."""
    tok = deref(tok)
    if unify(tag_var, tok["tag"], trail):
        yield None


def _lemma_2(tok, lem_var, trail, k):
    """lemma/2: lemma from token dict."""
    tok = deref(tok)
    if unify(lem_var, tok["lemma"], trail):
        yield None


def _dep_2(tok, label_var, trail, k):
    """dep/2: dependency label from token dict."""
    tok = deref(tok)
    if unify(label_var, tok["dep"], trail):
        yield None


def _head_2(tok, head_var, trail, k):
    """head/2: head text from token dict."""
    tok = deref(tok)
    if unify(head_var, tok["head_text"], trail):
        yield None


def _shape_2(tok, shape_var, trail, k):
    """shape/2: shape from token dict."""
    tok = deref(tok)
    if unify(shape_var, tok["shape"], trail):
        yield None


def _is_alpha_1(tok, trail, k):
    """is_alpha/1: succeed if token is alphabetic."""
    tok = deref(tok)
    if tok["is_alpha"]:
        yield None


def _is_stop_1(tok, trail, k):
    """is_stop/1: succeed if token is a stop word."""
    tok = deref(tok)
    if tok["is_stop"]:
        yield None


# ── Layer 5: NER ─────────────────────────────────────────────────────────

def _entity_2(this_generator, _proceed, _fail, _catcher, doc, ent_var, trail):
    """entity/2: backtrack over all entities in a Doc."""
    doc = deref(doc)
    for ent in doc.ents:
        mark = trail.mark()
        d = _ent_to_dict(ent)
        if unify(ent_var, d, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


def _entity_3(this_generator, _proceed, _fail, _catcher, doc, label, ent_var, trail):
    """entity/3: backtrack over entities filtered by label."""
    doc = deref(doc)
    label = deref(label)
    label_str = str(label)
    for ent in doc.ents:
        if ent.label_ == label_str:
            mark = trail.mark()
            d = _ent_to_dict(ent)
            if unify(ent_var, d, trail):
                yield (_proceed, None)
            trail.undo(mark)
    yield (_fail, DONE)


def _entity_list_2(doc, ents_var, trail, k):
    """entity_list/2: all entities as a list of dicts."""
    doc = deref(doc)
    ents = [_ent_to_dict(ent) for ent in doc.ents]
    if unify(ents_var, ents, trail):
        yield None


# ── Layer 6: Sentences ───────────────────────────────────────────────────

def _sentence_2(this_generator, _proceed, _fail, _catcher, doc, sent_var, trail):
    """sentence/2: backtrack over sentences as strings."""
    doc = deref(doc)
    for sent in doc.sents:
        mark = trail.mark()
        if unify(sent_var, sent.text, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


def _sentence_list_2(doc, sents_var, trail, k):
    """sentence_list/2: all sentences as a list of strings."""
    doc = deref(doc)
    sents = [sent.text for sent in doc.sents]
    if unify(sents_var, sents, trail):
        yield None


# ── Layer 7: similarity ──────────────────────────────────────────────────

def _similarity_4(alias, text1, text2, score_var, trail, k):
    """similarity/4: compute similarity between two texts."""
    alias = deref(alias)
    text1 = deref(text1)
    text2 = deref(text2)
    nlp = _get_model(alias)
    doc1 = nlp(str(text1))
    doc2 = nlp(str(text2))
    score = doc1.similarity(doc2)
    if unify(score_var, score, trail):
        yield None


# ── Layer 8: Noun chunks ────────────────────────────────────────────────

def _noun_chunk_2(this_generator, _proceed, _fail, _catcher, doc, chunk_var, trail):
    """noun_chunk/2: backtrack over noun chunks."""
    doc = deref(doc)
    for chunk in doc.noun_chunks:
        mark = trail.mark()
        d = _chunk_to_dict(chunk)
        if unify(chunk_var, d, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


# ── Build and export predicate objects ───────────────────────────────────

load_model = _SpacyPredicate("load_model")
load_model._register(1, _simple_to_trampoline(_load_model_1))
load_model._register(2, _simple_to_trampoline(_load_model_2))

unload_model = _SpacyPredicate("unload_model")
unload_model._register(1, _simple_to_trampoline(_unload_model_1))

current_model = _SpacyPredicate("current_model")
current_model._register(1, _current_model_1)

process = _SpacyPredicate("process")
process._register(3, _simple_to_trampoline(_process_3))

token = _SpacyPredicate("token")
token._register(2, _token_2)
token._register(3, _token_3)

token_text = _SpacyPredicate("token_text")
token_text._register(2, _simple_to_trampoline(_token_text_2))

token_list = _SpacyPredicate("token_list")
token_list._register(2, _simple_to_trampoline(_token_list_2))

pos = _SpacyPredicate("pos")
pos._register(2, _simple_to_trampoline(_pos_2))

tag = _SpacyPredicate("tag")
tag._register(2, _simple_to_trampoline(_tag_2))

lemma = _SpacyPredicate("lemma")
lemma._register(2, _simple_to_trampoline(_lemma_2))

dep = _SpacyPredicate("dep")
dep._register(2, _simple_to_trampoline(_dep_2))

head = _SpacyPredicate("head")
head._register(2, _simple_to_trampoline(_head_2))

shape = _SpacyPredicate("shape")
shape._register(2, _simple_to_trampoline(_shape_2))

is_alpha = _SpacyPredicate("is_alpha")
is_alpha._register(1, _simple_to_trampoline(_is_alpha_1))

is_stop = _SpacyPredicate("is_stop")
is_stop._register(1, _simple_to_trampoline(_is_stop_1))

entity = _SpacyPredicate("entity")
entity._register(2, _entity_2)
entity._register(3, _entity_3)

entity_list = _SpacyPredicate("entity_list")
entity_list._register(2, _simple_to_trampoline(_entity_list_2))

sentence = _SpacyPredicate("sentence")
sentence._register(2, _sentence_2)

sentence_list = _SpacyPredicate("sentence_list")
sentence_list._register(2, _simple_to_trampoline(_sentence_list_2))

similarity = _SpacyPredicate("similarity")
similarity._register(4, _simple_to_trampoline(_similarity_4))

noun_chunk = _SpacyPredicate("noun_chunk")
noun_chunk._register(2, _noun_chunk_2)
