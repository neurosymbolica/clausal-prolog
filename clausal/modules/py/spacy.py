"""clausal.modules.py.spacy — spaCy predicates under the ``py.spacy`` name.

Re-exports everything from :mod:`clausal.modules.spacy_module` so that
``.clausal`` files can use the familiar name::

    -import_from(py.spacy, [LoadModel, Process, Token, Entity])
"""

from clausal.modules.spacy_module import (  # noqa: F401
    LoadModel,
    UnloadModel,
    CurrentModel,
    Process,
    Token,
    TokenText,
    TokenList,
    Pos,
    Tag,
    Lemma,
    Dep,
    Head,
    Shape,
    IsAlpha,
    IsStop,
    Entity,
    EntityList,
    Sentence,
    SentenceList,
    Similarity,
    NounChunk,
)
