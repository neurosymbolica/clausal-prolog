# `.clausal` bytecode cache is keyed on SOURCE mtime — an engine upgrade does not invalidate it

**Found by corpus-lane 2026-09-11** while verifying a landing; the cause and the user-facing
consequence were reproduced here before filing.

## The defect

A `.clausal` file is compiled by the ENGINE's transformer and the result cached as ordinary
Python bytecode. The cache is validated the way CPython validates any `.pyc`: against the
SOURCE file's mtime and size. Nothing in the key mentions the engine.

`clausal/import_hook.py:232` states the mechanism from the other side: *"If the code came from
.pyc cache, source_to_code didn't run."* `source_to_code` is where the transformer runs.

**So the compiled output of a compiler is cached under a key that does not include the
compiler.**

## Reproduction

    # cold: transformer runs, pc.cpython-313.pyc written
    # warm (new process, source untouched): transformer does NOT run
    # after `find clausal -name '*.py' -exec touch {} +`  -- i.e. an engine upgrade:
    #   transformer STILL does not run

Measured by spying on `import_hook._parse_clausal_source`. All three results as stated.

## Why this is user-facing, not just a testing nuisance

Upgrade the engine and every unchanged `.clausal` file keeps running the compilation produced
by whatever engine last saw it — silently, with no warning and no error. Today alone that
would mean the constants respelling, the TitleCase rules and the seam-collector fix all
appearing not to take effect on an untouched corpus, which is indistinguishable from the
landing having failed.

It also quietly invalidates re-measurement across lanes: "re-run your census on the new sha"
tests the new engine only if the caches were cold. corpus-lane found 457 `.pyc` files written
"today" across 25 engine commits — same day, different engines.

## The narrower reading, which is also true

A load census is INSENSITIVE to this: stale bytecode loads perfectly well. So a census that
came back green was never evidence about a transformer change either way. The instruments that
carried those results were the behavioural ones — probes, oracles, harness bodies. Worth
remembering when choosing what to ask a lane for.

## Fix options

1. **Put an engine fingerprint in the cache filename.** Override `cache_from_source` for the
   clausal loader so the `.pyc` is named with a hash of the engine version (or of the
   transformer sources). An engine change then yields a different filename and a cold compile;
   stale files linger harmlessly until cleaned. Standard mechanism, no change to validation
   logic.
2. **Refuse the cache when the engine differs.** Override `path_stats`/`get_code` to compare a
   recorded engine fingerprint and fall through to source when it differs. More code, same
   effect, and it can report WHY it recompiled.
3. **Disable the cache for `.clausal`.** Correct and simple; costs transformer time on every
   import of every file, which for a large corpus is the wrong trade.

(1) is the recommendation.

**Blast radius, which is why this is not being done unasked:** it changes module loading for
every `.clausal` file. Every file recompiles once on the first run after the change, and a bug
in the key means either nothing caches (slow) or the wrong thing loads (silent, and worse than
today). It wants its own landing, its own gate, and a measured import-time comparison before
and after.

## Immediate mitigation, no code change

Anyone re-measuring after an engine landing should clear caches first:

    find <tree> -name __pycache__ -type d -exec rm -rf {} +

and any request to another lane to re-measure should say so explicitly.
