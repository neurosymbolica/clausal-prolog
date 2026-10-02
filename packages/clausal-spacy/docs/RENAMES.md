# Predicate renames (2026-10-02)

Breaking: these predicate names were TitleCase (Python class-style),
which the engine's TitleCase lint rejects in functor position --
Clausal code could not call them by name. They are renamed to
lower_snake_case, matching clausal-jax / clausal-torch convention.
Acronyms collapse to one lowercase word (e.g. `FFT` -> `fft`,
`KMeans` -> `k_means`).

| Old (TitleCase) | New (lower_snake_case) |
|---|---|
| `CurrentModel` | `current_model` |
| `Dep` | `dep` |
| `Entity` | `entity` |
| `EntityList` | `entity_list` |
| `Head` | `head` |
| `IsAlpha` | `is_alpha` |
| `IsStop` | `is_stop` |
| `Lemma` | `lemma` |
| `LoadModel` | `load_model` |
| `NounChunk` | `noun_chunk` |
| `Pos` | `pos` |
| `Process` | `process` |
| `Sentence` | `sentence` |
| `SentenceList` | `sentence_list` |
| `Shape` | `shape` |
| `Similarity` | `similarity` |
| `Tag` | `tag` |
| `Token` | `token` |
| `TokenList` | `token_list` |
| `TokenText` | `token_text` |
| `UnloadModel` | `unload_model` |
