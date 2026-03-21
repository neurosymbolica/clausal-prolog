# spaCy NLP Module

The `spacy_module` standard library module exposes spaCy's NLP pipeline as Clausal predicates. It provides model management, tokenisation, linguistic annotations, named-entity recognition, sentence segmentation, noun chunks, and vector similarity — all accessible from `.clausal` files via a relational interface.

**Requires:** `pip install spacy` and at least one downloaded spaCy model (e.g. `python -m spacy download en_core_web_sm`).

```clausal
-import_from(spacy_module, [LoadModel, Process, Token, Lemma, Entity])

Nouns(DOC, TOK) <- (
    LoadModel("en_core_web_sm", "nlp") and
    Process("nlp", DOC, DOC_OBJ) and
    Token(DOC_OBJ, TOK) and
    Pos(TOK, "NOUN")
)
```

Or via the `py.spacy` alias:

```clausal
-import_from(py.spacy, [LoadModel, Process, Entity, EntityList])
```

---

## Import

```clausal
-import_from(spacy_module, [
    LoadModel, UnloadModel, CurrentModel,
    Process,
    Token, TokenText, TokenList,
    Pos, Tag, Lemma, Dep, Head, Shape, IsAlpha, IsStop,
    Entity, EntityList,
    Sentence, SentenceList,
    Similarity,
    NounChunk
])
```

---

## Layer 1 — Model management

Models are loaded once and kept in a module-level registry under string aliases. All registry access is thread-safe.

### `LoadModel/1`

```clausal
LoadModel(+Name)
```

Load a spaCy model by name; the model name is used as the alias. Idempotent — if the alias is already loaded, succeeds immediately.

```clausal
LoadModel("en_core_web_sm")
```

### `LoadModel/2`

```clausal
LoadModel(+Name, +Alias)
```

Load `Name` under a custom `Alias`. Useful for loading the same model under multiple names or for shorter identifiers.

```clausal
LoadModel("en_core_web_sm", "en")
LoadModel("en_core_web_lg", "en_lg")
```

### `UnloadModel/1`

```clausal
UnloadModel(+Alias)
```

Remove the model from the registry. **Fails** if the alias is not registered.

### `CurrentModel/1`

```clausal
CurrentModel(?Alias)
```

When `Alias` is unbound, **nondeterministically enumerates** all registered aliases. When ground, succeeds if that alias is currently loaded.

```clausal
ListModels(A) <- CurrentModel(A)
```

---

## Layer 2 — Document processing

### `Process/3`

```clausal
Process(+Alias, +Text, -Doc)
```

Run `Text` through the model registered as `Alias` and unify `Doc` with the resulting spaCy `Doc` object. The Doc object is an opaque handle passed to all downstream predicates.

```clausal
setup(DOC) <- (
    LoadModel("en_core_web_sm", "nlp") and
    Process("nlp", "The quick brown fox jumps.", DOC)
)
```

---

## Layer 3 — Tokens

A token is represented as a plain Python dict with keys:

| Key | Type | Description |
|-----|------|-------------|
| `text` | str | Surface form |
| `lemma` | str | Lemmatised form |
| `pos` | str | Coarse POS tag (Universal Dependencies) |
| `tag` | str | Fine-grained POS tag |
| `dep` | str | Dependency label |
| `head_text` | str | Surface form of the syntactic head |
| `head_i` | int | Index of the syntactic head token |
| `i` | int | Token index within the document |
| `is_alpha` | bool | True if the token consists of alphabetic characters |
| `is_stop` | bool | True if the token is a stop word |
| `shape` | str | Orthographic shape (e.g. `"Xxxxx"`, `"dd"`) |

### `Token/2`

```clausal
Token(+Doc, -Tok)
```

**Nondeterministic.** Yields one solution per token in `Doc`, binding `Tok` to the token dict.

```clausal
AllTokens(DOC, TOK) <- Token(DOC, TOK)
```

### `Token/3`

```clausal
Token(+Doc, ?Index, -Tok)
```

When `Index` is ground, retrieves the token at that position (fails if out of range). When `Index` is unbound, iterates all tokens and binds `Index` to each token's position.

```clausal
FirstToken(DOC, TOK) <- Token(DOC, 0, TOK)
IndexedTokens(DOC, I, TOK) <- Token(DOC, I, TOK)
```

### `TokenText/2`

```clausal
TokenText(+Tok, ?Text)
```

Unify `Text` with the surface form of a token dict. Equivalent to `T is ++Tok["text"]` but more readable.

```clausal
IsApple(TOK) <- TokenText(TOK, "Apple")
```

### `TokenList/2`

```clausal
TokenList(+Doc, -Tokens)
```

Unify `Tokens` with a list of all token dicts in the document. Deterministic.

```clausal
Toks(DOC, TOKENS) <- TokenList(DOC, TOKENS)
```

---

## Layer 4 — Linguistic annotations

All annotation predicates take a token dict as their first argument and unify the second argument with the annotation value.

### `Pos/2`

```clausal
Pos(+Tok, ?Tag)
```

Coarse-grained Universal Dependencies POS tag: `"NOUN"`, `"VERB"`, `"PROPN"`, `"ADJ"`, etc.

!!! note "Why `Pos` not `POS`?"
    `POS` is all-uppercase, which the term transformer would interpret as a logic variable. The predicate is therefore named `Pos`.

### `Tag/2`

```clausal
Tag(+Tok, ?FineTag)
```

Fine-grained POS tag specific to the language model (e.g. `"NNS"`, `"VBZ"` for English Penn Treebank).

### `Lemma/2`

```clausal
Lemma(+Tok, ?Lem)
```

Lemmatised form of the token (e.g. `"run"` for `"running"`).

### `Dep/2`

```clausal
Dep(+Tok, ?Label)
```

Dependency relation to the syntactic head: `"nsubj"`, `"dobj"`, `"ROOT"`, etc.

### `Head/2`

```clausal
Head(+Tok, ?HeadText)
```

Surface form of the syntactic head token.

### `Shape/2`

```clausal
Shape(+Tok, ?Shp)
```

Orthographic shape string: `"Xxxxx"` for `"Apple"`, `"dd"` for `"42"`, etc.

### `IsAlpha/1`

```clausal
IsAlpha(+Tok)
```

**Succeeds** if the token consists entirely of alphabetic characters. **Fails** otherwise.

### `IsStop/1`

```clausal
IsStop(+Tok)
```

**Succeeds** if the token is a stop word in the model's language. **Fails** otherwise.

---

## Layer 5 — Named entity recognition

An entity is a dict with keys: `text`, `label`, `start`, `end`, `start_char`, `end_char`.

### `Entity/2`

```clausal
Entity(+Doc, -Ent)
```

**Nondeterministic.** Yields one solution per entity in the document.

```clausal
Orgs(DOC, ENT) <- (Entity(DOC, ENT) and T is ++ENT["label"] and T == "ORG")
```

### `Entity/3`

```clausal
Entity(+Doc, +Label, -Ent)
```

Filtered iteration — only yields entities whose label matches `Label`.

```clausal
People(DOC, ENT) <- Entity(DOC, "PERSON", ENT)
Orgs(DOC, ENT) <- Entity(DOC, "ORG", ENT)
```

### `EntityList/2`

```clausal
EntityList(+Doc, -Ents)
```

Unify `Ents` with a list of all entity dicts. Deterministic.

---

## Layer 6 — Sentences

Sentences are plain strings (the `.text` of each spaCy `Span`).

### `Sentence/2`

```clausal
Sentence(+Doc, -Sent)
```

**Nondeterministic.** Yields one solution per sentence.

### `SentenceList/2`

```clausal
SentenceList(+Doc, -Sents)
```

Unify `Sents` with a list of all sentence strings. Deterministic.

!!! note
    Sentence segmentation requires the `senter` or `sentencizer` component in the model pipeline. It is enabled by default in `en_core_web_sm` and other standard models.

---

## Layer 7 — Similarity

### `Similarity/4`

```clausal
Similarity(+Alias, +Text1, +Text2, -Score)
```

Process both texts through the model and unify `Score` with their cosine similarity as a float in `[0.0, 1.0]`.

```clausal
Close(T1, T2) <- (
    Similarity("en", T1, T2, S) and S > 0.8
)
```

!!! note
    Similarity requires word vectors in the model. Use `en_core_web_md` or `en_core_web_lg` instead of `_sm` for meaningful scores.

---

## Layer 8 — Noun chunks

A noun chunk is a dict with keys: `text`, `root_text`, `root_dep`, `root_head_text`.

### `NounChunk/2`

```clausal
NounChunk(+Doc, -Chunk)
```

**Nondeterministic.** Yields one solution per noun chunk.

```clausal
Subjects(DOC, CHUNK) <- (
    NounChunk(DOC, CHUNK) and
    D is ++CHUNK["root_dep"] and D == "nsubj"
)
```

---

## Working example

```clausal
-import_from(spacy_module, [LoadModel, Process, Token, Pos, Lemma, Entity, Dep])

# Find all noun subjects in a sentence
NounSubjects(TEXT, LEMMA) <- (
    LoadModel("en_core_web_sm", "nlp") and
    Process("nlp", TEXT, DOC) and
    Token(DOC, TOK) and
    Pos(TOK, "NOUN") and
    Dep(TOK, "nsubj") and
    Lemma(TOK, LEMMA)
)

# Extract all organisation entities
Orgs(TEXT, ORG_TEXT) <- (
    LoadModel("en_core_web_sm", "nlp") and
    Process("nlp", TEXT, DOC) and
    Entity(DOC, "ORG", ENT) and
    ORG_TEXT is ++ENT["text"]
)

# Filter tokens by POS and collect as list
NounLemmas(TEXT, LEMMAS) <- (
    LoadModel("en_core_web_sm", "nlp") and
    Process("nlp", TEXT, DOC) and
    FindAll(L, (Token(DOC, TOK) and Pos(TOK, "NOUN") and Lemma(TOK, L)), LEMMAS)
)
```

---

??? info "Test coverage"

    Tests are in `tests/test_spacy_module.py` (50+ tests, skipped if spaCy is unavailable).

    - **Helpers**: `_token_to_dict`, `_ent_to_dict`, `_chunk_to_dict` key sets and values
    - **Model registry**: load/unload, idempotent load, `CurrentModel` enumerate/check
    - **Process**: returns Doc, error on unknown alias
    - **Token/2,3**: iteration count, first token, by index, out-of-range, iterate with index
    - **TokenText, TokenList**: extraction, list length and contents
    - **Annotation predicates**: Pos (PROPN), Lemma (look), Dep, Shape, IsAlpha, IsStop
    - **NER**: entity iteration, label filter, empty filter, EntityList
    - **Sentences**: Sentence/2 iteration, SentenceList
    - **Similarity**: identical texts (≈1.0), score is float in [0,1]
    - **NounChunk**: chunk count, dict keys
    - **Adapter**: single-arity dispatch, multi-arity dispatch, repr, unknown arity → DONE
    - **py.spacy alias**: re-exports are identical objects
    - **Fixture integration**: `spacy_basic.clausal` (17 Test predicates)

??? abstract "Implementation"

    - **Module:** `clausal/modules/spacy_module.py`
    - **Alias:** `clausal/modules/py/spacy.py`
    - **Adapter class:** `_SpacyPredicate` — same pattern as `_SQLitePredicate` and `_RegexPredicate`
    - **Simple → trampoline**: `_simple_to_trampoline()` wraps deterministic generators
    - **Nondeterministic predicates**: native trampoline protocol with `trail.mark()`/`trail.undo(mark)` per solution
    - **Lazy import**: `import spacy` is deferred to first use via `_get_spacy()` so the module loads cleanly even when spaCy is not installed
    - **Thread-safe registry**: model dict protected by `threading.Lock`
    - **Token representation**: plain Python dicts (not opaque handles) — easy to inspect, log, and use with `++()` interop

??? abstract "Design decisions"

    1. **Doc as opaque handle** — the spaCy `Doc` object is passed directly as a logic term. It can be unified, stored, and passed around, but its internal structure is accessed only via the provided predicates.
    2. **Token as dict** — tokens are converted to plain Python dicts. This makes them easy to access with `++TOK["text"]` and compatible with dict-handling builtins. Dicts are ground (no logic variables inside), so they unify structurally.
    3. **Filtered iteration** — `Entity/3` and similar predicates filter at iteration time rather than via a separate filter predicate, following the pattern of `SQLiteQuery/4` with SQL `WHERE` clauses.
    4. **Model aliases** — models are referenced by string aliases throughout, making predicates composable without carrying model references. The same pattern is used in the SQLite module.
    5. **`Pos` not `POS`** — `POS` is all-uppercase and would be treated as a logic variable by the term transformer. `Pos` (title-case) avoids the collision.
    6. **Lazy spaCy import** — `import spacy` is deferred to first use so that `.clausal` files importing this module compile correctly even when spaCy is not installed. Errors are reported at predicate call time with a clear message.
