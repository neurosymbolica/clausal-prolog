# Atoms need readable names, and names need the same provenance rules as citations

**Requested:** 2026-08-29, from the law portal (feedback item FB-0012, filed against
`/population/`). Opening the "missing fact" filter dropdown showed:

```
absence_of_competition_not_artificially_narrowed
change_of_supplier_would_cause_technical_incompatibility
contract_type_key
```

A lawyer using the portal to plan a week's work is being asked to read the
formalization's identifiers. The portal now derives English at render time
(`portal/vocabulary.py`: underscores out, sentence case, a short acronym list) so the
dropdown reads `Absence of competition not artificially narrowed`. That is a stopgap in
the wrong repository, and it can only ever produce English.

## What already exists, and what it does not cover

Part C built exactly the right mechanism for **citation** atoms
(`docs/superpowers/specs/2026-07-18-translation-population-design.md`,
`_tools/scaffold_translation.py`, `_tools/check_translation.py`):

- `<domain>/translation/<lang>.clausal`, a nested subpackage per ISO language code.
- One `translation(<atom>, {ref, verbatim})` per citation atom, the atom declared via
  `-import_from(<pkg>.citations, [...])` so it is the SAME atom — that shared identity
  is the join key.
- Purely additive and load-on-demand: never imported by `__init__`, so logic and
  `citations.clausal` stay byte-identical.
- Idempotent scaffolding: "Atoms with an existing populated block keep it byte-for-byte";
  a re-run does not overwrite what a human filled in.
- Anti-hallucination: `verbatim` must be an exact normalized substring of a FETCHED
  target-language EUR-Lex source. Unfetchable → empty + `status: unverified` + a note.
  Never guess.

Every one of those properties is what FB-0012 asks for. The gap is **scope and record
shape**: `translation/2` carries the verbatim TEXT of a cited provision. The atoms the
portal renders are not citations and have no such record:

| atom kind | example | surfaces in the portal as |
|---|---|---|
| profile key / missing fact | `modification_notice_published` | the missing-fact filter, the ledger's fact column, the capture form's questions |
| ground key limb | `art32_2_c` | the ground filter, the capture form's limb chooser |
| engine status token | `incomplete_profile` | the "engine reason" filter, every finding row |
| outcome vocabulary | `non_conformity_indicated` | every finding (deliberately verbatim — see below) |

These are **names of concepts**, not quotations. `{ref, verbatim}` is the wrong shape for
them: there is no provision to quote, and no substring to check against.

## Open questions

**1. Record shape.** A separate `name(<atom>, {...})` in the same `translation/<lang>`
module, or a `name` key added to `translation/2`? A name wants different fields from a
quotation — something like `{name, source, note}` where `source` is one of `derived`
(mechanical from the atom), `human` (a translator checked it), `official` (taken from the
jurisdiction's own published translation of the instrument, with a `ref`). The
anti-hallucination gate for a name is not substring-matching; it is that anything not
`derived` names who or what stands behind it.

**2. Where English is produced.** Two options, and they are not equivalent:

- *Derived at read time by each consumer* — what the portal does today. Zero pipeline
  work, but every consumer re-implements the derivation and they drift. It also cannot
  express a name the derivation gets wrong: `contract_type_key` derives to "Contract type
  key", where the `_key` suffix is a formalization artefact a reader should not see, and
  no mechanical rule can know that without deciding what `_key` means.
- *Materialized once as `translation/en.clausal`* — the pipeline writes the derived name
  as `source: derived`, and a human may correct any entry to `source: human`, which
  re-runs then preserve (the existing idempotence rule already does this). One answer,
  correctable, and every consumer reads rather than derives.

The second looks right, and it is the one that makes the whole thing uniform: English
stops being a special case and becomes the language whose entries happen to start out
`derived`.

**3. Non-English languages.** These cannot be derived at all — deriving Slovene from an
English atom is precisely the guess this whole provenance standard exists to refuse.
They come from a human translator or from the official translation of the instrument in
that jurisdiction, and once checked they must survive re-runs. `scaffold_translation.py`
already implements exactly that rule for citations; whatever carries names needs it too,
and `check_provenance.py`'s coverage report should count named atoms alongside cited
ones.

**4. Fallback.** A consumer asking for `sl` where no `sl` entry exists should get a
defined answer — English, presumably, and visibly marked as untranslated rather than
silently substituted. A page that shows a Slovene UI with a silently English term is
making a claim about the law in Slovene that nobody checked.

**5. What must NOT be renamed.** The portal renders the engine's outcome verbatim on
purpose (`non_conformity_indicated`, with its engaged/advisory scope), and has a test
that fails if a template prettifies it. A name layer must be something a consumer opts
into per vocabulary, never a global display transform — otherwise the first thing it
does is soften the engine's own word.

## Portal side, once this exists

FB-0012 also asks for a language dropdown: persistent across pages, reloading the current
page on change, warning first if any input would be lost. That is portal work and it is
blocked on this — there is nothing to switch to until a second language exists. Worth
noting that the portal's own constraint points the same way as the design above: 12 §3.1
forbids per-domain portal work, so the portal may not hold a table of names. It has to
read them from the corpus.

Filed by the portal work on FB-0011/FB-0012; the derivation being used in the meantime is
`law-portal/portal/vocabulary.py`, which says in its own docstring that it is standing in
for this.
