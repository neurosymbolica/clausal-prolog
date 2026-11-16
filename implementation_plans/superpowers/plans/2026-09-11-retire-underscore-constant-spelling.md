# Retire the `_CONSTANT_` spelling from seam syntax — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** A module constant is spelled with an ordinary lowercase name and retrieved with the
explicit `++name` escape, so that the logic-variable rule has no exceptions left anywhere.

**Architecture:** The `-constants` directive, its groundness gate and its type-preserving
freezing all STAY — only the *spelling* of a constant name and the *retrieval* of its value
change. Names become atom-shaped (lowercase-initial), so the `_is_constant_name` carve-out is
deleted from all five `_is_logic_var_name` copies. Because a lowercase constant name is no
longer lexically distinguishable from an atom, a bare name in term position is now always an
atom, and the value is reached through `++name` — a plain Python module-global lookup that is
measured to work today. A name declared both as a constant and as an atom becomes a load-time
error, because the atom rebinding is measured to clobber the constant silently.

**Tech Stack:** Python 3.13, the Clausal AST transformer (`clausal/templating/term_rewriting.py`),
pytest.

**Spec:** `todo/retire-underscore-constants-for-an-iso-safe-surface-2026-09-10.md`, plus the two
operator rulings recorded in §"Operator rulings" below.

## Global Constraints

- **Surface:** this plan touches **seam syntax only**. The ISO-syntax directives
  `-constant_value/2` and `-constant_value_units/3` are gated on the reader-fed compiler
  (conformance-survey item 4) and are NOT built here.
- **The directive machinery stays.** `-constants`, `$check_constant_ground`, the
  `_Frozen{List,Dict,Set}` freezing in `clausal/logic/constants.py`, `ConstantNotGroundError`
  and `module_constant/3` all survive this plan unchanged in behaviour. Only names and
  retrieval change. (Operator, 2026-09-11: "Defer — retire spelling only".)
- **Upstream naming:** `constant_value/2` is Markus Triska's name for the eventual ISO-side
  predicate and is going to the Scryer meetup in October 2026. Do NOT rename `module_constant/3`
  to it in this plan — that decision belongs to that meeting.
- **Baseline:** the engine suite in this clone at `9a719536` is **144 failed / 15813 passed /
  1 error**, all environmental. The failure NAME SET is at
  `/home/node/.claude/jobs/af5b4bbe/tmp/tip.fail` (144 names). Every gate in this plan is a
  diff of failure NAME SETS against that file, never a comparison of totals, and both sides
  must be asserted non-empty first.
- **Run the suite as:** `cd /workspace/clausal-bug-fix && /workspace/clausal/venv/bin/python -m
  pytest tests -q -p no:randomly --tb=no -rf --continue-on-collection-errors > run.log 2>&1;
  rc=$?` — capture directly, never through a pipe.
- **Probes:** every probe script starts with `sys.path.insert(0, os.getcwd())` then
  `assert clausal.__file__.startswith(os.path.join('/workspace/clausal-bug-fix', ''))`.
  `startswith` with a trailing separator, never `in` — `/workspace/clausal` is a substring of
  `/workspace/clausal-bug-fix/...`.

## Operator rulings this plan implements

1. **Retrieval is `++name`**, the explicit escape (2026-09-10). A bare lowercase name stays an
   atom, so the spelling never lies.
2. **Runtime lookup, not folding at clause construction** (2026-09-10). Constants become
   late-bound.
3. **Retire the spelling only** (2026-09-11). Keep the `-constants` directive machinery and its
   freezing in place, under lowercase names, until `-constant_value/2` exists for ISO syntax.

## Measured facts this plan rests on

All measured on this tree at `9a719536`, not predicted. Re-measure before acting on any of
them — a fact with a shelf life does not survive a handoff.

| fact | how it was measured | result |
| --- | --- | --- |
| `-constants` usage in tracked seam sources | `git grep -l -- "-constants(" -- '*.clausal' '*.seam'` | **1** file: `tests/fixtures/const_functor_importer.seam` |
| `-constants` usage in the sibling trees | `grep -rl` over the three sibling checkouts | **0** real sites (2 `.md` analysis docs only) |
| `++name` over a plain Python module global in a clause body | probe `cp_escape2.clausal`: `big(thing) <- (++max_fine > 4000)` and `small(thing) <- (++max_fine > 6000)` | **works** — 1 answer and 0 answers respectively (positive AND negative control) |
| a declared atom binds a module global | probe `cp_collide.clausal` | `pi` global is `('pi',)` |
| a declared atom CLOBBERS a same-named Python global | probe `cp_clobber.clausal`: `pi = 3.14` at module level plus atom `pi` in `-module` | global ends as `('pi',)`, **silently** — no diagnostic |

The last row is why Task 3 exists, and it is also a pre-existing defect in its own right (see
"Filed separately" at the end).

## File Structure

| file | responsibility in this plan |
| --- | --- |
| `clausal/templating/term_rewriting.py` | the directive handler, the `visit_Name` folding branch, the three directive-list shape gates, the `-import_from` constant branch, and the canonical `_is_constant_name` |
| `clausal/templating/desugar.py` | one `_is_logic_var_name` copy + its `_is_constant_name` |
| `clausal/logic/goal_expansion.py` | one copy |
| `clausal/logic/predicate.py` | one copy |
| `clausal/tools/clausal_to_prolog.py` | one copy, plus a use of the engine's `_is_constant_name` at :2532 |
| `clausal/tools/prolog_to_clausal.py` | `_is_constant_name_shape`, used only to choose a diagnostic half |
| `tests/test_constants.py` | the directive's own suite — the bulk of the migration |
| `tests/test_var_classifier_conformance.py` | the lockstep gate on the five copies |
| `tests/fixtures/const_functor_importer.seam` | the one tracked seam fixture |
| `docs/syntax.md`, `docs/directives.md`, `docs/builtins.md`, `docs/for_prolog_programmers.md` | the human-readable surface |

---

### Task 1: `-constants` takes lowercase names and refuses the old spelling

**Files:**
- Modify: `clausal/templating/term_rewriting.py:7470-7563` (`_handle_constants_directive`)
- Test: `tests/test_constants.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `_is_constant_declaration_name(identifier: str) -> bool` in
  `clausal/templating/term_rewriting.py` — True for a lowercase-initial Python identifier, the
  same lexical class an atom occupies. Tasks 3, 4 and 5 rely on this name and signature.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_constants.py`:

```python
def test_lowercase_constant_name_is_accepted(tmp_path):
    """A constant is spelled like an atom now: lowercase, no underscores."""
    mod = _load(tmp_path, "c_lower", "-constants(max_fine = 5000)\n")
    assert mod.max_fine == 5000


def test_underscored_constant_spelling_is_refused(tmp_path):
    """The retired spelling fails loudly, and the message says what to write."""
    with pytest.raises(SyntaxError) as excinfo:
        _load(tmp_path, "c_old", "-constants(_MAX_FINE_ = 5000)\n")
    message = str(excinfo.value)
    assert "_MAX_FINE_" in message
    assert "max_fine" in message, "the message must offer the new spelling"


def test_capital_initial_constant_name_is_refused(tmp_path):
    """A capital initial is a logic variable everywhere now, with no
    exceptions -- so it cannot name a constant either."""
    with pytest.raises(SyntaxError, match="lowercase"):
        _load(tmp_path, "c_caps", "-constants(MaxFine = 5000)\n")
```

`_load` is the existing helper in that file; check its exact name and signature before writing
these — if it is spelled differently, use the file's own convention rather than introducing one.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_constants.py -k "lowercase or underscored or capital_initial" -v`
Expected: FAIL. The first two fail because `_is_constant_name` still gates the directive
(`'max_fine' is not a constant name`); the third fails because `MaxFine` is refused with the
old message, which does not contain "lowercase".

- [ ] **Step 3: Implement**

Add next to `_is_constant_name` in `clausal/templating/term_rewriting.py`:

```python
def _is_constant_declaration_name(identifier: str) -> bool:
    """True for a name a ``-constants`` declaration may bind.

    Since 2026-09-11 a constant is spelled like an atom -- a lowercase-initial
    identifier -- so that the logic-variable rule (underscore-led or
    capital-initial) has no exceptions left.  The value is reached with the
    explicit ``++name`` escape, never by a bare load; see
    ``_handle_constants_directive``.
    """
    return identifier.isidentifier() and identifier[:1].islower()
```

Then in `_handle_constants_directive`, replace the name check:

```python
            ident = kw.arg
            if ident is None or not _is_constant_declaration_name(ident):
                if ident is not None and _is_constant_name(ident):
                    raise SyntaxError(
                        f"-constants: `{ident}` uses the retired constant "
                        f"spelling; constants are lowercase names now, and "
                        f"the value is reached with the ++ escape. Write "
                        f"`-constants({ident.strip('_').lower()} = ...)` and "
                        f"`++{ident.strip('_').lower()}` at every use site.")
                raise SyntaxError(
                    f"-constants: {ident!r} is not a constant name — a "
                    f"constant is spelled like an atom: a lowercase-initial "
                    f"identifier, e.g. -constants(max_fine = 5000)")
```

and update the usage error and the docstring in the same method to the new spelling
(`-constants(pi = 3.14159, max_retries = 3)`).

The `_UNUSED` warning below it indexes `ident[1:-1]`, which assumed the underscores. Change it
to `ident.endswith("_UNUSED")` and keep the warning otherwise as it is.

Keep `_is_constant_name` itself for now — Task 1 uses it only to recognise the retired spelling
for the migration message. Task 6 deletes it.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_constants.py -k "lowercase or underscored or capital_initial" -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add clausal/templating/term_rewriting.py tests/test_constants.py
git commit -m "feat(constants): a constant is spelled like an atom"
```

---

### Task 2: a bare name never folds — retrieval is `++name`

**Files:**
- Modify: `clausal/templating/term_rewriting.py:2853-2862` (the constants branch of `visit_Name`)
- Modify: `clausal/templating/term_rewriting.py:501` (`_raise_undeclared_constant`) and its three
  call sites at `:1678`, `:2859`, `:7636`
- Test: `tests/test_constants.py`

**Interfaces:**
- Consumes: `_is_constant_declaration_name` from Task 1.
- Produces: nothing new. After this task `transformer._constants` records declared names for
  Tasks 3 and 5 but no longer steers `visit_Name`.

- [ ] **Step 1: Write the failing test**

```python
def test_constant_is_reached_through_the_escape(tmp_path):
    """The whole point of the lowercase spelling: ++name retrieves, a bare
    name is an atom.  Both halves asserted, so the test cannot pass by the
    value simply being absent."""
    source = (
        "-module(c_escape, [big/1, small/1, thing])\n"
        "-constants(max_fine = 5000)\n"
        "\n"
        "big(thing) <- (++max_fine > 4000)\n"
        "small(thing) <- (++max_fine > 6000)\n"
    )
    mod = _load(tmp_path, "c_escape", source)
    assert len(list(mod.big(mod.thing))) == 1
    assert len(list(mod.small(mod.thing))) == 0
```

- [ ] **Step 2: Run it to verify it fails**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_constants.py -k escape -v`
Expected: FAIL — before Task 1 lands this is a name error from the directive; after Task 1 it
should already PASS, because `++name` over a module global is measured to work. **If it passes,
say so and keep it** — it is then a characterisation test that pins the retrieval path, and the
red step for this task is the second test below instead.

- [ ] **Step 3: Write the test that is actually red**

```python
def test_bare_constant_name_is_an_atom_not_the_value(tmp_path):
    """Folding is gone: a bare name in term position is an atom, so an
    undeclared one is the ordinary strict-atoms error rather than the old
    undeclared-constant one."""
    source = (
        "-module(c_bare, [holds/1])\n"
        "-constants(max_fine = 5000)\n"
        "\n"
        "holds(max_fine)\n"
    )
    with pytest.raises((NameError, SyntaxError)) as excinfo:
        _load(tmp_path, "c_bare", source)
    assert "max_fine" in str(excinfo.value)
```

Run it. Expected: FAIL — today the declared-constant branch in `visit_Name` folds `max_fine` to
`5000` and the module loads clean.

- [ ] **Step 4: Implement**

In `visit_Name` (around `:2853`), delete both the folding branch and the shape diagnostic:

```python
        if identifier in transformer.constants:
            return replace(Name(id=identifier, ctx=load), name)
        if _is_constant_name(identifier):
            _raise_undeclared_constant(
                identifier, name, transformer._source_lines,
                transformer._filename)
```

Both lines go. A declared constant name now falls through to the ordinary atom path, which is
what makes Task 3's collision check necessary.

Then delete `_raise_undeclared_constant` and its remaining call sites at `:1678` and `:7636`.
Read each site before deleting: `:7636` is inside `_transform_constant_rhs` (a constant RHS
naming another constant), and that path must keep working — a constant RHS may still reference
an EARLIER declared constant by bare name, because a `-constants` RHS is not a clause term. Keep
that reference resolving through `transformer._constants`; only the shape-based diagnostic goes.

- [ ] **Step 5: Run both tests to verify they pass**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_constants.py -v`
Expected: the two new tests PASS. Other tests in the file will fail — they still use the retired
spelling and are migrated in Task 7. Note which ones, so Task 7 can be checked against the list.

- [ ] **Step 6: Commit**

```bash
git add clausal/templating/term_rewriting.py tests/test_constants.py
git commit -m "feat(constants): the value is reached through ++, never by a bare load"
```

---

### Task 3: a name cannot be both a constant and an atom

**Files:**
- Modify: `clausal/templating/term_rewriting.py` — `visit_Module` (around `:6277`), at the point
  where the module body has been walked and both `transformer._constants` and
  `transformer._atoms` are complete
- Test: `tests/test_constants.py`

**Interfaces:**
- Consumes: `transformer._constants` (Task 1) and `transformer._atoms`.
- Produces: nothing later tasks call.

**Why this task exists:** measured above — a declared atom rebinds the module global to `('pi',)`
AFTER the module body runs, silently overwriting a same-named constant. Before this plan the two
namespaces could not collide because their shapes were disjoint. Now they can, so the collision
has to be refused rather than resolved.

- [ ] **Step 1: Write the failing tests — BOTH declaration orders**

```python
def test_a_name_cannot_be_both_constant_and_atom(tmp_path):
    source = (
        "-module(c_clash, [likes/2, a, pi])\n"
        "-constants(pi = 3.14)\n"
        "\n"
        "likes(a, pi)\n"
    )
    with pytest.raises(SyntaxError) as excinfo:
        _load(tmp_path, "c_clash", source)
    message = str(excinfo.value)
    assert "pi" in message
    assert "constant" in message and "atom" in message


def test_the_collision_is_refused_in_the_other_order_too(tmp_path):
    """-constants before -module, and -constants after: the check must be
    order-independent, so it runs once the whole module has been walked."""
    source = (
        "-constants(pi = 3.14)\n"
        "-module(c_clash2, [likes/2, a, pi])\n"
        "\n"
        "likes(a, pi)\n"
    )
    with pytest.raises(SyntaxError, match="pi"):
        _load(tmp_path, "c_clash2", source)


def test_distinct_names_do_not_collide(tmp_path):
    """The negative control: without it a check that refuses EVERYTHING
    passes both tests above."""
    source = (
        "-module(c_noclash, [likes/2, a, pi])\n"
        "-constants(max_fine = 5000)\n"
        "\n"
        "likes(a, pi)\n"
    )
    mod = _load(tmp_path, "c_noclash", source)
    assert mod.max_fine == 5000
```

- [ ] **Step 2: Run them to verify the first two fail and the third passes**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_constants.py -k "collision or both_constant or noclash" -v`
Expected: two FAIL (the module loads, no SyntaxError), one PASS.

- [ ] **Step 3: Implement**

In `visit_Module`, after `transformer.generic_visit(module)` returns and before the result is
handed back:

```python
        clashes = sorted(transformer._constants & transformer._atoms)
        if clashes:
            names = ", ".join(f"`{n}`" for n in clashes)
            raise SyntaxError(
                f"-constants: {names} is declared both as a constant and as "
                f"an atom. A constant is a module global and an atom rebinds "
                f"the same global to itself, so the atom would silently win. "
                f"Rename one of them.")
```

Check the exact attribute spellings first: the transformer exposes `_constants` (a set) and
`_atoms` (a set) — confirm both are sets and both are populated by this point, and if either is
a list, compare accordingly rather than changing its type.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_constants.py -k "collision or both_constant or noclash" -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add clausal/templating/term_rewriting.py tests/test_constants.py
git commit -m "feat(constants): a name is a constant or an atom, never both"
```

---

### Task 4: delete the three directive-list shape gates

**Files:**
- Modify: `clausal/templating/term_rewriting.py:7081` (`-module`), `:7195` (`-private`),
  `:7319` (`-hide`)
- Test: `tests/test_constants.py`

**Interfaces:**
- Consumes: Task 3's collision check, which now produces the error these gates used to produce.
- Produces: nothing.

Each of the three tested `_is_constant_name(...)` on a listed name to give a constant-specific
message. A lowercase constant name is no longer distinguishable by shape, so all three branches
go: a listed name is simply an atom, and Task 3 catches the real error with a better message.

**One behaviour is deliberately dropped:** `-private` used to accept a constant listing as
documentation ("implementation detail"). There is no lexical way to keep that, so listing a
constant in `-private` now makes it an atom and Task 3 refuses the module. Say this in the commit
message.

- [ ] **Step 1: Write the test that pins the replacement behaviour**

```python
def test_module_listing_a_constant_name_is_the_collision_error(tmp_path):
    """The old -module-specific message is gone; the collision check gives
    the accurate one instead."""
    source = (
        "-module(c_export, [max_fine])\n"
        "-constants(max_fine = 5000)\n"
    )
    with pytest.raises(SyntaxError) as excinfo:
        _load(tmp_path, "c_export", source)
    assert "constant" in str(excinfo.value) and "atom" in str(excinfo.value)
```

- [ ] **Step 2: Run it**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_constants.py -k module_listing -v`
Expected: PASS already, because `max_fine` is not constant-SHAPED so the old gate never fires
and Task 3's check does. Keep it — it pins that the replacement path is the one giving the error.
If it FAILS, stop and read why before deleting anything.

- [ ] **Step 3: Delete the three branches**

Remove the `_is_constant_name` branch and its `raise`/`continue` body at each of `:7081`,
`:7195` and `:7319`. In `-private`, also remove the now-unused `private_constants` list and any
downstream reference to it — grep for it before deleting, and if it feeds a ModuleAST field,
remove the field's population rather than leaving it always-empty.

- [ ] **Step 4: Run the constants and declarations suites**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_constants.py tests/test_module_constant_reflection.py -q`
Expected: no NEW failures beyond the retired-spelling ones Task 7 migrates.

- [ ] **Step 5: Commit**

```bash
git add clausal/templating/term_rewriting.py tests/test_constants.py
git commit -m "refactor(constants): a listed name is an atom; the shape gates go"
```

---

### Task 5: `-import_from` imports a constant as an ordinary name

**Files:**
- Modify: `clausal/templating/term_rewriting.py:7940-7960` (the bare-Name constant branch) and
  `:8004-8020` (the `alias(...)` constant branch)
- Test: `tests/test_constants.py`, `tests/fixtures/const_functor_importer.seam`

**Interfaces:**
- Consumes: `_is_constant_declaration_name` (Task 1).
- Produces: nothing.

Today an imported constant is recognised by SHAPE and given a distinct path: it is added to
`transformer._constants` and emitted as a plain `alias`, with no `_import_remap` /
`_imported_functors` bookkeeping, so its use site resolves through the (now-deleted) folding
branch. With lowercase names the importer cannot tell a constant from an atom or a predicate in
another module, so the distinct path cannot be kept.

**Decision:** an imported name takes the ordinary imported-name path. The `ImportFrom` binds the
owner's module global here, so `++name` retrieves the value exactly as it does for a locally
declared constant — which is the measured mechanism from the facts table. The cost: importing a
constant and then CALLING it (`max_fine(X)`) now fails at runtime rather than at load time.
That is the same failure an imported atom already gives.

- [ ] **Step 1: Write the failing test**

```python
def test_an_imported_constant_is_reached_through_the_escape(tmp_path):
    owner = (
        "-module(c_owner, [])\n"
        "-constants(max_fine = 5000)\n"
    )
    user = (
        "-module(c_user, [big/1, thing])\n"
        "-import_from(c_owner, [max_fine])\n"
        "\n"
        "big(thing) <- (++max_fine > 4000)\n"
    )
    _write(tmp_path, "c_owner", owner)
    mod = _load(tmp_path, "c_user", user)
    assert len(list(mod.big(mod.thing))) == 1
```

Use whatever two-module helper `tests/test_constants.py` already has for the importer fixture —
`tests/fixtures/const_functor_importer.seam` exists for exactly this shape, so follow it
rather than inventing a new helper.

- [ ] **Step 2: Run it to verify it fails**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_constants.py -k imported_constant -v`
Expected: FAIL — `max_fine` is not constant-shaped, so it takes the functor path and the alias
is registered as an imported functor; the `++` escape may still resolve, in which case read the
error carefully before assuming the test is wrong.

- [ ] **Step 3: Implement**

Delete the constant branch at `:7940-7960` (the `if _is_constant_name(local_name):` block,
including its `already bound` SyntaxError and the `transformer._constants.add(local_name)`), and
the `alias(...)` constant branch at `:8004-8020` (the "constant imports must alias to a constant
name" error and everything under it). Both fall through to the ordinary imported-name handling
below them.

- [ ] **Step 4: Run the test to verify it passes**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_constants.py -k imported_constant -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add clausal/templating/term_rewriting.py tests/test_constants.py
git commit -m "feat(constants): an imported constant is an ordinary imported name"
```

---

### Task 6: delete `_is_constant_name` from all five copies

**Files:**
- Modify: `clausal/templating/term_rewriting.py:483` (definition), `:622` (the carve-out in
  `_is_logic_var_name`), and the remaining call sites at `:1535` and `:2858` if Tasks 2–5 have
  not already removed them
- Modify: `clausal/templating/desugar.py:57,80`
- Modify: `clausal/logic/goal_expansion.py:204,228`
- Modify: `clausal/logic/predicate.py:70,94`
- Modify: `clausal/tools/clausal_to_prolog.py:501,526` and the import + use at `:35,2532`
- Modify: `clausal/tools/prolog_to_clausal.py:339,367` (`_is_constant_name_shape`)
- Test: `tests/test_var_classifier_conformance.py`

**Interfaces:**
- Consumes: everything above. This task is the payoff — it is what makes the variable rule
  exception-free.
- Produces: nothing.

**Keep exactly one instance:** Task 1's migration message calls `_is_constant_name` to recognise
the retired spelling. Move that check inline into `_handle_constants_directive` as a private
`_is_retired_constant_spelling`, so the classifier files carry no trace of it, and the one place
that still knows the old shape is the one place that exists to reject it.

- [ ] **Step 1: Update the conformance test first**

`tests/test_var_classifier_conformance.py` currently asserts that constant-shaped names are
variables NOWHERE. Invert those rows: `_PI_` is now an ordinary underscore-led name and
therefore IS a logic variable in all five copies. Update the module docstring, the `CORPUS`
entries for `_PI_`/`_MAX_RETRIES_`/`_1_`, the `NAME_POSITION` row `("_PI_", False)` (it stays
False there — a variable is not a name-position name), the `_is_constant_name` import at `:16`,
`test_constant_shape_is_never_a_variable` (delete it), and the fixture-corpus scan at `:106-124`
and `:133-174` that allowlists files declaring a `-constants` name.

Add the property that replaces the deleted one:

```python
def test_the_variable_rule_has_no_exceptions():
    """The point of retiring _CONSTANT_: underscore-led (but not dunder, not
    bare _) or capital-initial IS the whole rule, in every copy."""
    for spelling in ["_PI_", "_MAX_RETRIES_", "_x", "_1_", "X", "Foo", "FOO"]:
        expected = (spelling not in ("_",)
                    and not spelling.startswith("__")
                    and (spelling.startswith("_") or spelling[:1].isupper()))
        for fn in ALL:
            if fn is ds_var and (spelling == "_" or spelling.startswith("__")):
                continue  # pinned divergence: desugar excludes neither
            assert fn(spelling) == expected, (fn.__module__, spelling)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_var_classifier_conformance.py -v`
Expected: FAIL — `_PI_` is still carved out of every copy, so `tr_var("_PI_")` is False where
the new property expects True.

- [ ] **Step 3: Delete the carve-out from all five copies**

In each of the five files, delete the `_is_constant_name` definition and the two lines

```python
    if _is_constant_name(identifier):
        return False
```

from `_is_logic_var_name`, and update the docstring sentence that mentions the exclusion.
In `clausal/tools/clausal_to_prolog.py` also drop the `_engine_is_constant_name` import at `:35`
and read `:2532` before changing it — it decides something about a prefixed name and needs a
replacement rule, not just a deletion.
In `clausal/tools/prolog_to_clausal.py`, `_is_constant_name_shape` only picks which half of a
diagnostic to print; with `_X_` now a legal Clausal variable, `prolog_var_to_clausal` no longer
rejects it, so delete the helper and the branch that calls it, leaving the dunder half.

- [ ] **Step 4: Run the conformance and translator suites**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_var_classifier_conformance.py tests/test_prolog_to_clausal_var_names.py tests/test_translate*.py -q`
Expected: PASS, except any test still spelling a constant the old way (migrate those here — they
belong to this task, not Task 7, because they are about the classifier).

- [ ] **Step 5: Commit**

```bash
git add clausal/ tests/test_var_classifier_conformance.py tests/test_prolog_to_clausal_var_names.py
git commit -m "refactor(vars): the logic-variable rule has no exceptions left"
```

---

### Task 7: migrate the fixture, the remaining tests, and the docs

**Files:**
- Modify: `tests/fixtures/const_functor_importer.seam`
- Modify: `tests/test_constants.py`, `tests/test_atoms_as_cells_flip.py`,
  `tests/test_ipython_integration.py`, `tests/test_lint_titlecase.py`,
  `tests/test_module_constant_reflection.py`
- Modify: `docs/syntax.md`, `docs/directives.md`, `docs/builtins.md`,
  `docs/for_prolog_programmers.md`
- Modify: `implementation_plans/module-level-constants.md` (a historical record — add a dated
  note at the top rather than rewriting it)

**Interfaces:**
- Consumes: everything above.
- Produces: nothing.

- [ ] **Step 1: Migrate the one tracked seam fixture**

```bash
sed -n '1,40p' tests/fixtures/const_functor_importer.seam
```

Rewrite its `-constants` names to lowercase and every use site from a bare name to `++name`.
Check the importing test still asserts the same values.

- [ ] **Step 2: Migrate the inline test sources**

Every `-constants(_X_ = ...)` in the five Python test files, and every bare use of the declared
name in the same inline source, become `-constants(x = ...)` and `++x`. `module_constant/3`
call sites in `tests/test_module_constant_reflection.py` pass the name as a STRING (`"_PI_"`) —
those become `"pi"`.

Do NOT blanket-`sed`. Two of these files use constant spellings for a different purpose:
`tests/test_lint_titlecase.py:508-530` asserts that a `-constants` RHS refuses a TitleCase
element, and `tests/test_var_classifier_conformance.py` (Task 6) uses `_PI_` as a CLASSIFIER
corpus entry, where it now means "an ordinary variable". Read each hit.

- [ ] **Step 3: Run the whole affected set**

Run:
```bash
/workspace/clausal/venv/bin/python -m pytest tests/test_constants.py \
    tests/test_atoms_as_cells_flip.py tests/test_ipython_integration.py \
    tests/test_lint_titlecase.py tests/test_module_constant_reflection.py \
    tests/test_var_classifier_conformance.py -q
```
Expected: PASS.

- [ ] **Step 4: Migrate the docs**

`docs/syntax.md`'s Constants section, `docs/directives.md`'s `-constants` entry,
`docs/builtins.md`'s `module_constant/3` entry and `docs/for_prolog_programmers.md`. Each must
say three things: the name is lowercase, the value is reached with `++name`, and the value is
late-bound (a runtime lookup, not folded into the clause).

`tests/test_doc_snippet_coverage.py` compiles ```clausal blocks — it is one of the 144 standing
failures, at 38 uncompilable blocks. Check the number does not GROW:

```bash
/workspace/clausal/venv/bin/python -m pytest tests/test_doc_snippet_coverage.py -q 2>&1 | grep -o "Found [0-9]* \`\`\`clausal"
```
Expected: 38 or fewer. If it grows, a migrated doc block is wrong.

- [ ] **Step 5: Commit**

```bash
git add tests/ docs/ implementation_plans/module-level-constants.md
git commit -m "docs+tests: migrate every constant to the lowercase spelling"
```

---

### Task 8: gate the whole thing against the baseline, then land

**Files:** none — this task only measures.

- [ ] **Step 1: Run the full suite on the branch**

```bash
cd /workspace/clausal-bug-fix
/workspace/clausal/venv/bin/python -m pytest tests -q -p no:randomly --tb=no -rf \
    --continue-on-collection-errors > /home/node/.claude/jobs/af5b4bbe/tmp/const-branch.log 2>&1
echo "rc=$?"
```

- [ ] **Step 2: Extract the failure NAME SET and assert it is non-empty**

```bash
cd /home/node/.claude/jobs/af5b4bbe/tmp
sed -E 's/\x1b\[[0-9;]*m//g' const-branch.log > const-branch.clean
tail -2 const-branch.clean | grep -qE "[0-9]+ (passed|failed)" || echo "RUN DID NOT EXECUTE"
grep -E "^(FAILED|ERROR) " const-branch.clean \
    | sed -E 's/^(FAILED|ERROR) //; s/ - .*//' | sort -u > const-branch.fail
wc -l < const-branch.fail        # MUST be non-empty
wc -l < tip.fail                 # the 144-name baseline; MUST be non-empty
```

- [ ] **Step 3: Diff the sets in both directions, and read the INTERSECTION for guard tests**

```bash
comm -13 tip.fail const-branch.fail > const-NEW.txt      # regressions
comm -23 tip.fail const-branch.fail > const-GONE.txt     # fixed
wc -l const-NEW.txt const-GONE.txt
grep -E "corpus|guard" <(comm -12 tip.fail const-branch.fail) || true
```

Expected: `const-NEW.txt` empty. A failure common to BOTH arms lands in neither column — that is
how a previous landing silently covered 1914 fewer cases than it appeared to — so the third
command exists to make any corpus/guard test failing on both sides visible rather than cancelled
out.

- [ ] **Step 4: Confirm the corpora actually ran**

```bash
grep -c "rewrite/test_corpus\|fmt/test_corpus" const-branch.clean
```
If this is 0, the corpora discovered no files in this tree and the diff covers less than it
appears to. The shared clone does collect them; a worktree may not.

- [ ] **Step 5: Report, and get the operator's go before landing**

Do NOT push to canonical or the box without an explicit per-landing go. When asking, state all
three claims separately — engine suite, corpus loads, batch bodies — and name the tree each was
measured on. This plan produces only the first; the other two are measured elsewhere, and
neither is implied by a green engine suite.

---

## Filed separately (do NOT fix in this plan)

**A declared atom silently clobbers a same-named Python module global.** Measured above with
`cp_clobber.clausal`: a module-level `pi = 3.14` ends up as `('pi',)` after
`_process_bare_atom_refs` rebinds it, with no diagnostic. This is pre-existing, is not
capitalisation-related, and is wider than constants — any hosted-Python global whose name
matches a declared atom is affected. Task 3 refuses the specific constant/atom case; the general
case needs its own todo and its own decision (error, or warn, or documented precedence).

## Corrections made while executing this plan

Three of the plan's premises did not survive contact with the code. They are recorded here
rather than edited away, because each was found by a measurement the plan itself called for.

**1. "A bare name is an atom" was wrong, and Task 2 could not deliver it.**
`compiler_v2._process_bare_atom_refs` trusts ANY already-bound module global unconditionally,
so a bare reference to a plain Python `max_fine = 5000` in a seam already yields `5000` with no
`-constants` directive anywhere. Deleting the `visit_Name` branch does not change that. What
actually separates the two spellings is BINDING TIME, and both work: a bare reference folds at
clause construction, `++name` resolves at solve time. Rebinding the global afterwards moves one
answer and not the other. So `++name` is what delivers the late-binding ruling — the reason to
reach for it is not that the bare form is unavailable.

**2. The `visit_Name` branch is NOT redundant, and deleting it was a regression.**
Measured after the fact: the fall-through emits `$LoadName`, whose job is to resolve LATER so
that an atom declared further down the file still works, and which therefore hands back the raw
Python object with no term conversion. `-constants(origin = point(0, 0))` reached the clause as
a `point` INSTANCE instead of `('point', 0, 0)`. Only structured values moved — an int converts
to itself — and the two tests that caught it were green at the baseline. The branch is restored.
The lesson generalises: "this branch is redundant with that one" is a claim about two code
paths, and the way to check it is to unparse both, not to reason about them.

**3. Task 3's rule was too strong. A name CAN be a constant and an atom.**
The operator said so and the measurement agreed: with `-constants(pi = 5000)` and no atom
listing, `pi` is the constant and `'pi'` is the atom, and the quoted form unifies with what
`global_atom("pi", A)` yields. The one combination that cannot work is DECLARING the atom bare
in `-module`/`-private`/`-hide`, because that listing rebinds the module global after the file
has run and silently destroys the constant. Only that is refused.

## Self-review notes

- **Spec coverage:** the spec's "Definition of done" lists `-constant_value(name, value)`
  implemented — that is item (b), gated on the reader-fed compiler, and is deliberately NOT in
  this plan (see Global Constraints). The other four bullets — carve-out gone from all five
  copies, conformance test updated, fixture migrated, a test that the retired spelling fails
  loudly, downstream re-measured and stated — map to Tasks 6, 6, 7, 1 and the facts table.
- **Type consistency:** `_is_constant_declaration_name` is the only new name and is used with
  the same signature in Tasks 1, 3, 4 and 5. `_is_retired_constant_spelling` (Task 6) is the
  renamed remnant of `_is_constant_name` and is private to the directive handler.
- **Known soft spot:** Task 6 Step 3 names `clausal_to_prolog.py:2532` as needing a replacement
  rule rather than a deletion, and the plan does not say what that rule is, because the line's
  purpose could not be established without reading its surrounding function. Read it first; if
  it turns out to need a design decision, park it in a todo rather than guessing.
