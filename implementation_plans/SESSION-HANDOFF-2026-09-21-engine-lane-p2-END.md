# Engine lane handoff — 2026-09-21 END, P2: THE BLOCKER IS CLOSED

Branch `feat/predmeta-p2-head-cells-2026-09-19` in **/workspace/clausal**.
Tip `27a4f8c4`, 0 behind `main` (`bd774c46`). Still nothing in C — verified:
`git diff main...HEAD -- '*.c' '*.h' '*.pyx' '*.pxd' setup.py pyproject.toml`
is EMPTY, so the copied-`.so` rooms are sound by construction and the
"clean-base A/B with its own build" worry from the previous handoff does not
apply to the C layer.

Rooms: `/tmp/claude-1000/-workspace-clausal-bug-fix/823f67d2-.../scratchpad/
{kwwt,mainnow}`, 12 `.so` each (sets verified identical), venv symlinked.

**These handoffs are COMMITTED ON THE BRANCH.** They are not in
`/workspace/clausal-bug-fix`, which is a different clone that does not carry
it — if you cannot find one, check out the branch or read it from git.

## The one blocker is done

`todo/aliased-assertz-loses-the-owner-under-cells-2026-09-20.md` is CLOSED.
Two commits: `e3f4a9bc` (the change) and `27a4f8c4` (the roborev round).

**The blocking question — "may a module declare `-dynamic` on a name it
imports?" — was a FALSE knot, and it is answered by measurement, not by a
ruling.** It already may, and the working non-aliased sibling relies on it.

`gate_dyn_user.clausal` declares BOTH `-dynamic(gd_p/1)` and an import of
`gd_p`, and its test has always passed, because ONE DIRECTIVE HAS TWO EFFECTS:

* the import **wins the name binding** — measured,
  `user.__dict__["gd_p"] is owner.gd_p` — so the shadow class the declaration
  mints is simply overwritten, and
* the **mark** stays on the importer's database, which is what keeps
  `compiler_v2` step 7 ("lock non-dynamic predicates") from locking the shared
  row. That loop walks `module_dict.values()`, and an imported class's `_row`
  is the OWNER's row, so an importer really can lock somebody else's
  predicate.

"Ignore the local `-dynamic`" and "the local `-dynamic` permits the write" are
therefore not in contradiction: they are these two different effects, and only
the second is load-bearing. Route (iii) failed last session because it removed
the second. Nothing ever needed the first removed.

### The change

> **A `-dynamic(f/N)` declaration in a module that imports a predicate whose
> own name is `f` at arity N NAMES THAT IMPORT.** The canonical spelling binds
> to the imported class, exactly as it already does when the import is not
> aliased — unless this module has clauses of its own under the name, which is
> a genuine clash the local definition wins (`Database.adopt_row`'s rule,
> applied to the binding).

`compiler_v2._imported_class_by_canonical_name` is `_imported_class(origins,
functor)` — which ALREADY sees through an alias, because
`_import_from_origins` indexes under `bound.__name__` too — plus an arity
check and `_belongs_elsewhere`. Everything downstream then runs the proven
non-aliased path.

Channel 4 was a separate, smaller defect and is fixed in the same commits: the
refusal came from `_check_cell_head_permission`, which fires BEFORE the gate
(pre-P2 an instance head skipped it entirely, which is why the gate used to
speak). It now asks `write_refusal` first when the row belongs to another
database — `row.db is not db`, NOT `home is not db`, because `_home_db`
answers `db` whenever there is no class while an ADOPTED key still resolves to
the exporter's row.

### Gates

* **House: 146 failed, 16737 passed, 50 skipped, 38 xfailed. Extraction
  146 = summary 146 on BOTH arms. NEW 0 / GONE 0 vs main `bd774c46`.**
  (+6 passed vs the pre-change arm: the 2 new tests and the 4 parametrized
  fixture sweeps that pick up the new `.clausal` file.)
* `tests/shared_rows/` green, including
  `test_an_aliased_import_does_NOT_plant_the_exporter_s_spelling` — no row is
  planted under the exporter's spelling. That invariant is about a module that
  never wrote the name; `gate_alias_user` writes it, in its `-dynamic`.
* **Both `xfail(strict=True)` markers are REMOVED and both tests pass.**
* Blast radius, censused: **1** engine-tree file (the fixture) and **0** of
  235,663 corpus `.clausal`/`.seam` files declare `-dynamic` on a name they
  import under an alias.
* Both new tests mutation-checked: each fails when its branch is removed.

## WHAT IS LEFT BEFORE THIS BRANCH LANDS

**One thing, and it is another lane's run.**

* **The corpus ANSWER-SET axis.** Ask the downstream downstream lane to run the downstream
  answer-set answer-set checks on the frozen tip `27a4f8c4`. **Landing waits for
  it**, as the atoms flip's did. Not started. Run the units-DECLARING domain alone first — it holds the one
  unexplained reading, so it is the cheapest early warning.

Not blocking, but worth knowing:

* `todo/task-5-c-arms-are-all-still-live-2026-09-20.md` — Task 5 step 2 stays
  blocked; not one of the 17 C arms is dead, and it re-sequences after the P4
  head channel.
* `todo/packages-are-not-gated-and-are-broken-on-main-2026-09-21.md` — 402
  package tests already fail on MAIN with nothing gating them.

## Rules this branch paid for, now four

1. **A type question must ANSWER, not raise.**
2. **A constructor flip silently re-points every test fixture that used the
   constructor**, and the fixture keeps passing under its old name.
3. **A NEW-0 is evidence only if the run printed a summary AND the thing under
   test actually imported.**
4. **A "contradiction" between two load-bearing behaviours is usually two
   EFFECTS of one directive, not two rules.** Four implementation routes were
   tried and backed out against this one before anybody measured which of the
   two effects each route was actually removing. Measure the working sibling
   before ruling on the broken one.
