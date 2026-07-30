# `prof_get`/`prof_has` stragglers still taught to models, and one dead sample

**Filed:** 2026-07-30, splitting the residue out of
`todo/done/formalize-lib-snake-case-rename.md` before archiving it. Cross-repo:
the work is in `/workspace/clausify/kit` and `/workspace/clausify-domains`, filed
here because the parent todo was.

The rename itself is done — `formalize_lib.clausal` exports `profile_get/3`,
`profile_has/2`, `profile_set/3`; aliases were dropped; 81 domain files use
`profile_get`; no `.clausal` in kit or domains calls the old names except the one
below. What was missed is everything that is not code:

- **11 model-facing exemplars** under `/workspace/clausify/kit/exemplars/`
  (`EXEMPLAR_GDPR.yaml`, `EXEMPLAR_SARA_IRC.yaml`, `EXEMPLAR_SNAP.yaml`,
  `EXEMPLAR_TRAFFIC.yaml`, `EXEMPLAR_IRC_S121.yaml`, `EXEMPLAR_CSA.yaml`,
  `EXEMPLAR_PEPPOL.yaml`, `EXEMPLAR_THAI_VISA.yaml`,
  `EXEMPLAR_LEGALBENCH_DIVERSITY.yaml`, plus `README.md`) still show
  `prof_get/3` / `prof_has/2` / `attr(key, value)`. These are prompt material,
  so every generation seeded from them teaches a name that no longer exists —
  the highest-value item here, and the reason the parent todo's own rationale
  (models generate what they were shown) applies in reverse.
- **`/workspace/clausify/kit/scaffolding/coverage_template.yaml`** emits
  `attr(key, value)` profile literals on 5 lines.
- **`/workspace/clausify-domains/_training/samples/eu-dma-art3-gatekeeper/dma_art3_gatekeeper.clausal:57`**
  does `-import_from(formalize_lib, [prof_get, prof_has, attr])` and no longer
  loads at all. Confirmed:

  ```
  1 tests: 0 passed, 1 failed [FAILED]
  cannot import name 'prof_get' from 'formalize_lib'
      -> either add `prof_get` to that -module(...) list and define it there, or
         stop importing it and remove every use.
  ```

  (That message is the `import-error-should-list-module-exports` diagnostic doing
  its job.)

Mechanical: `prof_get` → `profile_get`, `prof_has` → `profile_has`,
`attr(` → `attribute(`. Lint C6 in the kit already enforces the code side going
forward, which is why only non-code carriers drifted.
