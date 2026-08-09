# `-private` atoms are importable, which the atoms spec says they are not

STATUS: DONE (2026-07-30). Decided **Option 1 — change the spec, keep the
behaviour**. `-private` means "not part of my documented surface", not
"unreachable": Python's leading underscore, not C++ `private`. The tree now
says so in one place (`docs/directives.md` § `-private`) and everywhere else
points at it. Behaviour is unchanged and now pinned by a test.

The todo's leaning was Option 1 and the evidence agreed, but for a stronger
reason than the todo gave. The todo argued "downstream relies on it, and
anonymous modules have no alternative". The first is true but weak (a one-day-old
workaround is cheap to change) and **the second is simply false** — see below.
The real reason is that Clausal has no visibility enforcement anywhere, so the
spec's whole "Importable" column was aspirational, not just the `-private` row.

## Evidence

Measured in the worktree at `31a1ab79`, not asserted.

**1. Is the permissive behaviour deliberate or accidental? — Both, and the
deliberate half is decisive.**

The *mechanism* is an omission: `_handle_import_from_directive`
(`clausal/templating/term_rewriting.py`) lowers `-import_from(M, [n])` to a
plain Python `from M import n`. Nothing on the import path consults anything
about `M`'s declarations. There is no code that "allows a private atom
through", because there is no code that could stop one — visibility is not a
concept the import path has.

The *intent*, however, is recorded and it is the permissive one. Three places,
all predating this todo:

- `_handle_private_directive`'s docstring: `-private` "has the same compilation
  effect as `-module` exports ... but **communicates** that these names are not
  part of the module's public API."
- `docs/import.md`'s Prolog-comparison table already advertised
  *"No export lists. Everything is public"* as a Clausal **advantage** over
  Prolog's module system.
- `docs/directives.md`'s `-import_from` note already said an atom import is
  meaningful when the source listed it "in its `-module` / `-private`" — i.e.
  the user-facing import docs already documented private atoms as importable.

So the contradiction was internal to `GLOBAL_ATOMS_DEFAULT.md` and
`docs/predicates.md`; the rest of the tree already described the shipped rule.

**2. The `Importable` column is unenforced in *every* row, not just `-private`.**

This is what settles it. Probes:

- A predicate in **neither** `-module` nor `-private` — the spec's
  "unmentioned → module-local, implicitly private → not importable" row — is
  importable by name from another module and binds the owner's class.
- The same atom listed in **both** `-module` and `-private` loads clean with no
  error and no warning, contrary to "the compiler rejects this with a hard
  error". The first listing processed wins; the second is a no-op.
  A downstream helper library lists eight names in both, deliberately.

Enforcing the `-private` row alone would therefore police one row of a
three-row table whose other rows are equally unenforced, and would still not
deliver encapsulation: anything not mentioned at all stays importable. It would
buy the ceremony of access control without the property.

**3. Who relies on it? — 33 sites, 6 of them load-bearing, plus in-repo tests.**

Resolved sweep of `-import_from` in `.clausal` across three downstream repos
(a consumer, a rulebase corpus, and an external authoring harness),
`packages/` and `tests/` (3572 import sites):

| | count |
|---|---|
| import sites naming something the target declares `-private` | **33** |
| ...where the name is declared **only** private (not also exported) | **6** |
| ...of those, the imported name is a bare **atom** | **2** |

The 6 are a downstream helper library's own tests importing `delta` from a
second helper module (×2, the kit is vendored into a second downstream repo as
well), and a tax-credit domain's `test_public_interface` importing four private
citation atoms (`us_code_ref_1_a/_1_c/_1_d`, `us_code_ref_3301`) from `constants` and
`computation`. None of these are workarounds; they are how those libraries are
written.

Not counted in the 33 because they live in Python string literals: an external
authoring harness's own `auto/tests/test_gate_test_profiles.py`, whose fixtures
import `requirement`, `req_bool`, `flag`, `count` from a private-only list —
the fixtures fixed yesterday under the downstream bare-atom-fixture fix
(relocated to that harness's own repo).

**4. What breaks in-repo under enforcement? — 8 items.**

Measured by actually implementing a minimal Option-2 check and running the
suite: `1 failed, 10684 passed` → `9 failed, 10680 passed`. The new failures
were the whole `tests/test_functor_reexport.py` suite (4 tests) plus its two
fixture loads, and the new pin plus its fixture. `test_functor_reexport` is a
real in-repo regression suite for the `kit → queries → downstream` re-export
chain; it depends on importing a `-private` functor.

**5. The anonymous-module premise is false — Option 2 was NOT blocked by it.**

The todo said an anonymous fixture module has "no stable module name to export
under", making the `-private` import its only identity-preserving route. This
is wrong. `-module(name, [...])`'s first argument is a **free-form label**: it
is never checked against the file name and is not what `-import_from` resolves
(that uses the Python module path). A file `gen_a1b2c3.clausal` declaring
`-module(mismatched_name, [shared_tag, Fact(X)])` loads fine and
`-import_from(gen_a1b2c3, [Fact, shared_tag])` binds its classes. So any
generated or `tmp_path` fixture can carry an export list, and Option 2 owed no
alternative. It is rejected on the merits in point 2, not on this.

**6. What `-private` actually buys** (established, so the docs could state it
truthfully): module-local identity distinct from the global atom and from every
other module's declaration; satisfaction of the strict-atoms resolver so a bare
reference compiles; shadowing (it is resolution step 1 inside the declaring
module, ahead of `-module`, imports and the global); signature pre-registration
of arity/field names for `P(A, B)` entries; and the advisory statement of
intent. Not unreachability.

## Options rejected

**Option 2, enforce.** Rejected on point 2: it polices one row of a table whose
other rows are equally unenforced, so it cannot deliver encapsulation (an
undeclared name stays importable) — it would add ceremony and break 8 in-repo
items and 6+ downstream call sites for a guarantee it cannot make. Notably
*not* rejected for the reason the todo expected; point 5 disproves that.

**Option 3, warn.** Rejected because it would fire on deliberate, correct,
shipped library code — the kit's `delta` re-export and the tax-credit domain's citation
atoms are not mistakes. The brief required that a warning "cannot fire on the
legitimate anonymous-fixture pattern"; since that pattern *is* the `-private`
import (`test_gate_test_profiles`), the warning has no way to tell the two
apart. Silencing it would need a fresh escape-hatch directive for a rule the
language has never enforced.

## What changed

Documentation only; no behaviour change.

- `implementation_plans/atoms_refactor/GLOBAL_ATOMS_DEFAULT.md` — both tables
  (`Importable` → `Declared surface`), the "shadow the world inside my walls"
  prose in resolution rule 3, rule 4's account of what an atom import binds,
  the `-private` entry under "Changes to existing directives", the stale
  "compiler rejects this with a hard error" claim, and a new
  **"Visibility is advisory"** section recording this decision.
- `docs/directives.md` § `-private` — the canonical statement: a warning box
  saying the marker is not a barrier, and an info box listing the five things
  `-private` does buy. Everything else links here.
- `docs/predicates.md` § Private Predicates — removed "they are not exposed for
  import" and "this prevents accidental coupling", which were the flattest
  false statements in the docs.
- `docs/strict-atoms-migration.md` — the Path B advice now says explicitly that
  a file with no `-module` export list does not need one invented for it.
- `docs/import.md` — the "Export list maintenance" row now names `-private` as
  a surface declaration rather than a barrier.
- `docs/syntax.md` — dropped the bare "(public)"/"(private)" parenthetical.

## Pinned

`tests/test_global_atoms_default.py::test_private_names_are_importable_and_share_identity`,
with fixtures `tests/fixtures/private_import_{owner,consumer}.clausal`. It
asserts the import succeeds, that both modules hold the *same* class for the
private atom and the private predicate, that the class is module-local rather
than the global atom, that the query actually solves, and that **no warning is
emitted** — so an Option-3 implementation fails it too, not just an Option-2
one.

Verified against a deliberately broken build: a minimal Option-2 enforcement
was added to `compiler_v2._process_declarations`, the pin failed with
`ImportError: cannot import private name 'PrivImpHelper' from
'tests.fixtures.private_import_owner'`, and the enforcement was then reverted
(`git checkout HEAD -- clausal/`, confirmed by grepping for the added symbol).

## Not to be confused with

The identity trap itself (declaring the same atom `-private` in two files that
must agree, producing a silently unsatisfiable query) is *correct* behaviour and
is documented under Path B in `docs/strict-atoms-migration.md`. This todo was
only about whether the import should have been allowed.

## Left open

Whether the compiler *should* reject the same name in both `-module` and
`-private` is a separate design question, deliberately not decided here — the
docs now describe what happens rather than claiming an error that does not
exist. Filed as `todo/module-private-overlap-is-accepted-silently.md`.
