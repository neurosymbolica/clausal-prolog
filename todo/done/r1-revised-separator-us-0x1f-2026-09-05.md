# R1-revised: switch the -hide mangling separator from U+E000 to US (0x1F)

Proposed by the author 2026-09-05 during P3-2 close-out; assessed and
recommended for ratification. FIRST post-merge follow-up — the change is
cheap only while no mangled atom has persisted anywhere (pickles, DBs,
fixtures outside tests/).

## Why (assessment recorded at proposal time)

- R1's anti-NUL rationale does not apply to 0x1F: US is an ordinary byte to
  every C twin (no C-string termination hazard).
- CPython storage, the strongest argument: one U+E000 forces the WHOLE
  mangled atom into UCS-2 (2 bytes/char) and off the compact-ASCII
  comparison/hash fast paths; 0x1F keeps ASCII module/name atoms in
  Latin-1 storage. Halves mangled-atom memory, not just the separator.
- Byte-clean interop: travels in-band to non-Unicode Prologs (GNU Prolog);
  §1b's structural (module, name) codec at foreign boundaries becomes an
  option rather than a necessity on some paths — update §1b's wording.
- Counterpoints accepted as a wash: collision profile shifts from
  PUA-in-data (icon fonts) to US-in-data (delimited-record pipelines) —
  both remain the documented out-of-warranty forgery class; debugger
  visibility worsens (invisible control char) — mitigated by writer
  demangling being the display path.

## Change surface (verified 2026-09-05, post-P3-2 branch)

- clausal/logic/atoms.py (HIDDEN_SEP constant — the single definition)
- clausal/tools/toklex/specs/clausal.toklex.pl (reserved class U+E000 → 0x1F)
- clausal/reflection.py, clausal/templating/term_rewriting.py (consume the
  constant — verify no hardcoded literal)
- tests/test_hide_directive.py, tests/toklex/test_clausal_dialect.py
- docs/directives.md; spec §1b + the P3-1 R1 ruling text (record as
  R1-revised, user-ratified <date>)
- Reader rejection rule unchanged in shape: refuse the separator inside any
  atom token, quoted or not.

## Gate

Covering: test_hide_directive + toklex dialect suite; full-suite name-diff
empty (mangling is display+identity internal; no semantics change).

## Resolution (2026-09-05)

Implemented on branch `feat/r1-sep-0x1f`: `HIDDEN_SEP` in
`clausal/logic/atoms.py` flipped from U+E000 to `"\x1f"` (US); the toklex
`reserved` class, `docs/directives.md`, and the covering tests
(`tests/test_hide_directive.py`, `tests/toklex/test_clausal_dialect.py`)
updated in lockstep. `reflection.py` and `term_rewriting.py` already
consumed the constant (no hardcoded literal in the former; a doc-comment
literal fixed in the latter). Full-suite name-diff empty vs. main.
