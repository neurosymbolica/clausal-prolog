# RESOLVED: `CLAUSAL_BYTECODE_TAG` is manual, and it went 55 transformer commits stale

**Fixed 2026-09-11 at `a9989b7a`** — the tag is now derived from a content fingerprint of
`templating/`, `pythonic_ast/` and `logic/compiler*`, XORed with the hand tag (kept as the
lever for runtime changes a source fingerprint cannot see). Lazy and memoised: 9.7 ms on the
first `.clausal` compile in a process, 0.06 µs after, and nothing at all for a process that
loads no Clausal source. Verified end to end in subprocesses and on both machines — the box
(x86_64) computes the same fingerprint as the dev tree (aarch64), which is the path-relative
content-hash design working across architectures.

The tag was also bumped 12 -> 13 to close the accumulated gap.

Kept below for the reasoning, and because the WRONG first diagnosis is the instructive part.

---


**2026-09-11.** This file previously claimed the `.clausal` bytecode cache "ignores the engine
version". **That was wrong and the correction is the point of the file.** The cache has an
explicit engine-version knob and has had one since `b5dff16b`. The defect is that nothing
turns it.

## What actually exists

`clausal/import_hook.py`, `_ClausalSourceLoader.path_stats`:

    return {"mtime": (st.st_mtime_ns ^ CLAUSAL_BYTECODE_TAG) & 0xFFFFFFFF,
            "size": st.st_size}

The tag is XORed into the mtime importlib validates against, so bumping it invalidates every
cached `.pyc` even when sources are untouched — and it needs no clearing step, no directory
walk and no file deletion: a stale entry simply misses and is overwritten on recompile. That
is exactly the "check a fingerprint and invalidate" design, already built and already correct.

Its history is carefully documented too — eleven bumps, each naming the compilation change
that makes a stale `.pyc` wrong (the atom pivot, atoms-as-cells, the nil-atom flip, ...).

## The defect

**It is manual.** Between the 11→12 bump (`b4875ba9`, 2026-09-07) and 2026-09-11, **55 commits
touched `clausal/templating/term_rewriting.py`** and none bumped the tag. At least one changes
emitted code: `7a4d7407`, where a seam stopped collecting names through a `++` escape. A stale
tag-12 `.pyc` still emits the walrus and still raises the `UnboundLocalError` that fix removes.

So the discipline is sound and unfollowed, which is worse than absent: the mechanism's
existence is why nobody looked for the problem.

Bumped to 13 on 2026-09-11 to close the accumulated gap. **That is a patch, not the fix.**

## The fix: derive the tag instead of typing it

Compute a fingerprint of the compilation-relevant engine sources at import-hook wiring-in and
use it as the tag. One walk at startup; everything downstream is unchanged, because the tag
already flows into `path_stats`.

The design tension, which is presumably why it was manual: fingerprinting **all** of
`clausal/**/*.py` invalidates every cache on any engine edit, including a docstring — painful
in a development tree where the engine changes hourly. Narrow it to what actually decides
emitted code:

    clausal/templating/         the transformer
    clausal/logic/compiler*     the clause compiler
    clausal/pythonic_ast/       the node definitions

and hash `(path, size, mtime_ns)` for those, not file contents, to keep startup cheap. Measure
the added import time before and after; if it is material, cache the fingerprint itself keyed
on the engine directory's own mtime.

Keep the manual tag as an override — a hand bump is still the right tool when a RUNTIME change
(not a compilation change) makes old bytecode wrong, which a source fingerprint would not catch.

## Why a load census could not have caught this

Stale bytecode loads perfectly well. A census that reports "74 of the roster's domains load clean" is
insensitive to the whole class, in either direction. The instruments that detect it are
behavioural — probes, oracles, answer comparisons. That is about instrument SELECTION, not
hygiene, and it applies to what a lane is ASKED for as much as to how they run it.

## Immediate mitigation for anyone measuring today

    find <tree> -name __pycache__ -type d -exec rm -rf {} +

and say so explicitly when asking another lane to re-measure after an engine landing.
