# spaCy NLP Module

The `spacy` module exposes spaCy's NLP pipeline as Clausal predicates. It provides model management, tokenisation, linguistic annotations, named-entity recognition, sentence segmentation, noun chunks, and vector similarity — all accessible from `.clausal` files via a relational interface.

**Requires:** `pip install spacy` and at least one downloaded spaCy model (e.g. `python -m spacy download en_core_web_sm`).

```clausal
-import_from(spacy, [load_model, process, token, lemma, entity])

nouns(DOC, TOK) <- (
    load_model("en_core_web_sm", "nlp"),
    process("nlp", DOC, DOC_OBJ),
    token(DOC_OBJ, TOK),
    pos(TOK, "NOUN")
)
```

---

## Import

```clausal
-import_from(spacy, [
    load_model, unload_model, current_model,
    process,
    token, token_text, token_list,
    pos, tag, lemma, dep, head, shape, is_alpha, is_stop,
    entity, entity_list,
    sentence, sentence_list,
    similarity,
    noun_chunk
])
```

---

## Layer 1 — Model management

Models are loaded once and kept in a module-level registry under string aliases. All registry access is [thread-safe](free_threading.md).

### `load_model/1`

```clausal
--8<-- "tests/fixtures/docs/spacy_sigs.txt:load_model_1_sig"
```

Load a spaCy model by name; the model name is used as the alias. Idempotent — if the alias is already loaded, succeeds immediately.

```clausal
--8<-- "tests/fixtures/docs/spacy_sigs.txt:load_model_1_ex"
```

### `load_model/2`

```clausal
--8<-- "tests/fixtures/docs/spacy_sigs.txt:load_model_2_sig"
```

Load `Name` under a custom `Alias`. Useful for loading the same model under multiple names or for shorter identifiers.

```clausal
--8<-- "tests/fixtures/docs/spacy_sigs.txt:load_model_2_ex"
```

### `unload_model/1`

```clausal
--8<-- "tests/fixtures/docs/spacy_sigs.txt:unload_model_sig"
```

Remove the model from the registry. **Fails** if the alias is not registered.

### `current_model/1`

```clausal
--8<-- "tests/fixtures/docs/spacy_sigs.txt:current_model_sig"
```

when `Alias` is unbound, **nondeterministically enumerates** all registered aliases. when ground, succeeds if that alias is currently loaded.

```clausal
list_models(A) <- current_model(A)
```

---

## Layer 2 — Document processing

### `process/3`

```clausal
--8<-- "tests/fixtures/docs/spacy_sigs.txt:process_sig"
```

Run `Text` through the model registered as `Alias` and unify `Doc` with the resulting spaCy `Doc` object. The Doc object is an opaque handle passed to all downstream predicates.

```clausal
setup(DOC) <- (
    load_model("en_core_web_sm", "nlp"),
    process("nlp", "The quick brown fox jumps.", DOC)
)
```

---

## Layer 3 — Tokens

A token is represented as a plain Python dict with (atom) keys. Text the
document holds is free-form and comes back as a **string**
(`"Apple"`, the term `('$chars', 'Apple')`); linguistic labels are names
and come back as **atoms** (`'PROPN'`, `look`) -- ruled 2026-10-04:

| Key | Type | Description |
|-----|------|-------------|
| `text` | string | Surface form |
| `lemma` | atom | Lemmatised form |
| `pos` | atom | Coarse POS tag (Universal Dependencies) |
| `tag` | atom | Fine-grained POS tag |
| `dep` | atom | Dependency label |
| `head_text` | string | Surface form of the syntactic head |
| `head_i` | int | Index of the syntactic head token |
| `i` | int | token index within the document |
| `is_alpha` | bool | True if the token consists of alphabetic characters |
| `is_stop` | bool | True if the token is a stop word |
| `shape` | atom | Orthographic shape (e.g. `'Xxxxx'`, `dd`) |

### `token/2`

```clausal
--8<-- "tests/fixtures/docs/spacy_sigs.txt:token_2_sig"
```

**Nondeterministic.** Yields one solution per token in `Doc`, binding `Tok` to the token dict.

```clausal
all_tokens(DOC, TOK) <- token(DOC, TOK)
```

### `token/3`

```clausal
--8<-- "tests/fixtures/docs/spacy_sigs.txt:token_3_sig"
```

when `Index` is ground, retrieves the token at that position (fails if out of range). when `Index` is unbound, iterates all tokens and binds `Index` to each token's position.

```clausal
first_token(DOC, TOK) <- token(DOC, 0, TOK)
indexed_tokens(DOC, I, TOK) <- token(DOC, I, TOK)
```

### `token_text/2`

```clausal
--8<-- "tests/fixtures/docs/spacy_sigs.txt:token_text_sig"
```

Unify `Text` with the surface form of a token dict, a string. Equivalent to `T is ++Tok["text"]` but more readable.

```clausal
is_apple(TOK) <- token_text(TOK, "Apple")
```

### `token_list/2`

```clausal
--8<-- "tests/fixtures/docs/spacy_sigs.txt:token_list_sig"
```

Unify `Tokens` with a list of all token dicts in the document. Deterministic.

```clausal
toks(DOC, TOKENS) <- token_list(DOC, TOKENS)
```

---

## Layer 4 — Linguistic annotations

All annotation predicates take a token dict as their first argument and unify the second argument with the annotation value.

### `pos/2`

```clausal
--8<-- "tests/fixtures/docs/spacy_sigs.txt:pos_sig"
```

Coarse-grained Universal Dependencies POS tag, an atom: `'NOUN'`, `'VERB'`, `'PROPN'`, `'ADJ'`, etc.

!!! note "Why `pos` not `POS`?"
    `POS` is all-uppercase, which the term transformer would interpret as a logic variable. The predicate is therefore named `pos`.

### `tag/2`

```clausal
--8<-- "tests/fixtures/docs/spacy_sigs.txt:tag_sig"
```

Fine-grained POS tag specific to the language model, an atom (e.g. `'NNS'`, `'VBZ'` for English Penn Treebank).

### `lemma/2`

```clausal
--8<-- "tests/fixtures/docs/spacy_sigs.txt:lemma_sig"
```

Lemmatised form of the token, an atom (e.g. `run` for `"running"`): `lemma(TOK, 'run')`.

### `dep/2`

```clausal
--8<-- "tests/fixtures/docs/spacy_sigs.txt:dep_sig"
```

Dependency relation to the syntactic head, an atom: `nsubj`, `dobj`, `'ROOT'`, etc.

### `head/2`

```clausal
--8<-- "tests/fixtures/docs/spacy_sigs.txt:head_sig"
```

Surface form of the syntactic head token, a string.

### `shape/2`

```clausal
--8<-- "tests/fixtures/docs/spacy_sigs.txt:shape_sig"
```

Orthographic shape, an atom: `'Xxxxx'` for `"Apple"`, `dd` for `"42"`, etc.

### `is_alpha/1`

```clausal
--8<-- "tests/fixtures/docs/spacy_sigs.txt:is_alpha_sig"
```

**Succeeds** if the token consists entirely of alphabetic characters. **Fails** otherwise.

### `is_stop/1`

```clausal
--8<-- "tests/fixtures/docs/spacy_sigs.txt:is_stop_sig"
```

**Succeeds** if the token is a stop word in the model's language. **Fails** otherwise.

---

## Layer 5 — Named entity recognition

An entity is a dict with keys: `text` (a string), `label` (an atom, `'ORG'`), `start`, `end`, `start_char`, `end_char`.

### `entity/2`

```clausal
--8<-- "tests/fixtures/docs/spacy_sigs.txt:entity_2_sig"
```

**Nondeterministic.** Yields one solution per entity in the document.

```clausal
orgs(DOC, ENT) <- (entity(DOC, ENT), T is ++ENT["label"], T == 'ORG')
```

### `entity/3`

```clausal
--8<-- "tests/fixtures/docs/spacy_sigs.txt:entity_3_sig"
```

Filtered iteration — only yields entities whose label matches `label`.

```clausal
people(DOC, ENT) <- entity(DOC, "PERSON", ENT)
orgs(DOC, ENT) <- entity(DOC, "ORG", ENT)
```

### `entity_list/2`

```clausal
--8<-- "tests/fixtures/docs/spacy_sigs.txt:entity_list_sig"
```

Unify `Ents` with a list of all entity dicts. Deterministic.

---

## Layer 6 — Sentences

Sentences are strings (the `.text` of each spaCy `span`, as the term `('$chars', s)`).

### `sentence/2`

```clausal
--8<-- "tests/fixtures/docs/spacy_sigs.txt:sentence_sig"
```

**Nondeterministic.** Yields one solution per sentence.

### `sentence_list/2`

```clausal
--8<-- "tests/fixtures/docs/spacy_sigs.txt:sentence_list_sig"
```

Unify `Sents` with a list of all sentence strings. Deterministic.

!!! note
    sentence segmentation requires the `senter` or `sentencizer` component in the model pipeline. It is enabled by default in `en_core_web_sm` and other standard models.

---

## Layer 7 — similarity

### `similarity/4`

```clausal
--8<-- "tests/fixtures/docs/spacy_sigs.txt:similarity_sig"
```

process both texts through the model and unify `Score` with their cosine similarity as a float in `[0.0, 1.0]`.

```clausal
close(T1, T2) <- (
    similarity("en", T1, T2, S),
    S > 0.8
)
```

!!! note
    similarity requires word vectors in the model. Use `en_core_web_md` or `en_core_web_lg` instead of `_sm` for meaningful scores.

---

## Layer 8 — Noun chunks

A noun chunk is a dict with keys: `text`, `root_text`, `root_head_text` (strings) and `root_dep` (an atom).

### `noun_chunk/2`

```clausal
--8<-- "tests/fixtures/docs/spacy_sigs.txt:noun_chunk_sig"
```

**Nondeterministic.** Yields one solution per noun chunk.

```clausal
subjects(DOC, CHUNK) <- (
    noun_chunk(DOC, CHUNK),
    D is ++CHUNK["root_dep"],
    D == 'nsubj'
)
```

---

## Working example

```clausal
-import_from(spacy, [load_model, process, token, pos, lemma, entity, dep])

# Find all noun subjects in a sentence
noun_subjects(TEXT, LEMMA) <- (
    load_model("en_core_web_sm", "nlp"),
    process("nlp", TEXT, DOC),
    token(DOC, TOK),
    pos(TOK, 'NOUN'),
    dep(TOK, 'nsubj'),
    lemma(TOK, LEMMA)
)

# Extract all organisation entities
orgs(TEXT, ORG_TEXT) <- (
    load_model("en_core_web_sm", "nlp"),
    process("nlp", TEXT, DOC),
    entity(DOC, "ORG", ENT),
    ORG_TEXT is ++ENT["text"]
)

# include tokens by POS and collect as list
noun_lemmas(TEXT, LEMMAS) <- (
    load_model("en_core_web_sm", "nlp"),
    process("nlp", TEXT, DOC),
    findall(L, (token(DOC, TOK), pos(TOK, "NOUN"), lemma(TOK, L)), LEMMAS)
)
```

---

??? info "Test coverage"

    Tests are in `tests/test_spacy_module.py` (50+ tests, skipped if spaCy is unavailable).

    - **Helpers**: `_token_to_dict`, `_ent_to_dict`, `_chunk_to_dict` key sets and values
    - **Model registry**: load/unload, idempotent load, `current_model` enumerate/check
    - **process**: returns Doc, error on unknown alias
    - **token/2,3**: iteration count, first token, by index, out-of-range, iterate with index
    - **token_text, token_list**: extraction, list length and contents
    - **Annotation predicates**: pos (PROPN), lemma (look), dep, shape, is_alpha, is_stop
    - **NER**: entity iteration, label filter, empty filter, entity_list
    - **Sentences**: sentence/2 iteration, sentence_list
    - **similarity**: identical texts (≈1.0), score is float in [0,1]
    - **noun_chunk**: chunk count, dict keys
    - **Adapter**: single-arity dispatch, multi-arity dispatch, repr, unknown arity → DONE
    - **py.spacy alias**: re-exports are identical objects
    - **Fixture integration**: `spacy_basic.seam` (17 Test predicates)

??? abstract "Implementation"

    - **Module:** `clausal/modules/spacy_module.py`
    - **Alias:** `clausal/modules/py/spacy.py`
    - **Adapter class:** `_SpacyPredicate` — same pattern as `_SQLitePredicate` and `_RegexPredicate`
    - **Simple → trampoline**: `_simple_to_trampoline()` wraps deterministic generators
    - **Nondeterministic predicates**: native trampoline protocol with `trail.mark()`/`trail.undo(mark)` per solution
    - **Lazy import**: `import spacy` is deferred to first use via `_get_spacy()` so the module loads cleanly even when spaCy is not installed
    - **Thread-safe registry**: model dict protected by `threading.Lock`
    - **token representation**: plain Python dicts (not opaque handles) — easy to inspect, log, and use with `++()` interop

??? abstract "Design decisions"

    1. **Doc as opaque handle** — the spaCy `Doc` object is passed directly as a logic term. It can be unified, stored, and passed around, but its internal structure is accessed only via the provided predicates.
    2. **token as dict** — tokens are converted to plain Python dicts. This makes them easy to access with `++TOK["text"]` and compatible with dict-handling builtins. Dicts are ground (no logic variables inside), so they unify structurally.
    3. **Filtered iteration** — `entity/3` and similar predicates filter at iteration time rather than via a separate filter predicate, following the pattern of `query/4` with SQL `WHERE` clauses.
    4. **Model aliases** — models are referenced by string aliases throughout, making predicates composable without carrying model references. The same pattern is used in the SQLite module.
    5. **`pos` not `POS`** — `POS` is all-uppercase and would be treated as a logic variable by the term transformer. `pos` (title-case) avoids the collision.
    6. **Lazy spaCy import** — `import spacy` is deferred to first use so that `.clausal` files importing this module compile correctly even when spaCy is not installed. Errors are reported at predicate call time with a clear message.

---

*See also: [Regex](regex.md) — pattern matching in strings · [Python Interop](python_integration.md) — `++()` escape for additional spaCy features.*
