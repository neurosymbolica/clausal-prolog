# fix(A10-F018): .pyc cache survives clausal transformer upgrades (unconfirmed-impact)

**Problem.** `.pyc` validation for `.clausal`/`.pl` modules is source
(mtime,size) + CPython magic only (`_ClausalSourceLoader.path_stats`,
documented in docs/caching.md). The cached bytecode is the OUTPUT of
EmbedTransformer — upgrading clausal (new transformer semantics, e.g. any fix
from this audit wave) leaves stale transformed bytecode live until the
user's source file happens to change. `clausal/tools/clear_pycache.py` exists
as a manual escape hatch, which suggests the footgun is known.

**Status.** unconfirmed (needs two clausal versions to demonstrate); logged
from code+doc inspection. Design question A10-D005 resolved-from-docs: the
mtime/size scheme is as documented — this todo is the cheap hardening.

**Fix.** Fold a transformer-version constant into cache validity — e.g.
`CLAUSAL_BYTECODE_TAG = <int>` bumped on transformer changes, XORed into the
reported `mtime` (or added to `size`) in `path_stats`, or switch to
`source_to_code`-level hash invalidation. One-line change; add a release-notes
checklist item to bump the tag.
