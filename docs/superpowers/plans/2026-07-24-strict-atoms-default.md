# Strict Atoms by Default — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make undeclared bare atoms a compile-time `NameError` by default (Python-style), with a new `-implicit_atoms` escape hatch, staged so the suite stays green at every commit.

**Architecture:** A pure binary flip (strict vs. implicit, no `warn` state). The current default flag `strict_mode = any(StrictAtomsItem)` in `compiler_v2._process_bare_atom_refs` inverts to `effective_strict = not implicit_mode`. Safety during the transition comes from migration ordering: a new no-op `-implicit_atoms` marker is added to every in-repo `.clausal` file *before* the default flips, so the flip breaks nothing; strictness is then peeled off file-by-file. The REPL pins implicit mode at its single `EmbedTransformer` construction site.

**Tech Stack:** Python 3.13, pytest 9. DSL compiler in `clausal/templating/term_rewriting.py` (AST transform → `module_items`) and `clausal/logic/compiler_v2.py` (`compile_module` consumes `module_items`). Reference design: `docs/superpowers/specs/2026-07-24-strict-atoms-default-design.md`.

## Global Constraints

- **Test command (this clone):** `PYTHONPATH=/workspace/clausal-bug-fix ~/.pyenv/versions/3.13.3/bin/python -m pytest` — the repo venv lacks pytest; always use pyenv 3.13.3.
- **Scope:** Clausal repo only — `clausal/**` and `tests/fixtures/**`. Do **not** touch downstream consumer repos.
- **Directive markers take no arguments** and accept both bare (`-implicit_atoms`) and parenthesised (`-implicit_atoms()`) forms, mirroring `-strict_atoms`.
- **Green suite at every task boundary.** Each task ends with a commit and a passing full suite (or the task's stated scoped subset where noted).
- **`-implicit_atoms` is permanent and NOT deprecated.** Only `-strict_atoms` gets deprecated (Task 4).

---

## File Structure

- `clausal/pythonic_ast/nodes.py` — add `ImplicitAtomsDeclaration` node (mirrors `StrictAtomsDeclaration`).
- `clausal/templating/term_rewriting.py` — directive handler + dispatch + REPL emission in `EmbedTransformer`.
- `clausal/logic/compiler_v2.py` — mutual-exclusion check, the default flip, deprecation warning.
- `clausal/import_hook.py` — pass `implicit_atoms_default=True` at the single REPL/IPython transform site.
- `tools/codemods/add_implicit_atoms.py` — throwaway codemod (Phases 1 & 5).
- `tests/test_strict_atoms_default.py` — new behavior tests.
- `tools/codemods/test_add_implicit_atoms.py` — codemod unit test.
- `docs/directives.md`, `docs/syntax.md`, `docs/builtins.md` — docs.

---

## Task 1: Add the `-implicit_atoms` directive (additive no-op)

While the default is still loose, `-implicit_atoms` is a no-op — which is exactly what makes it safe to introduce and sprinkle everywhere. This task also adds the both-directives mutual-exclusion error.

**Files:**
- Modify: `clausal/pythonic_ast/nodes.py` (add node ~after line 1107; `__all__` line 90)
- Modify: `clausal/templating/term_rewriting.py` (import block ~line 14-22; handler ~after line 3198; dispatch ~line 3055; known-directives message ~line 3061-3064; comment ~line 2760)
- Modify: `clausal/logic/compiler_v2.py` (import block ~line 28-37; `_process_bare_atom_refs` ~line 577)
- Modify: `docs/directives.md` (Atom-Identity Directives section, after the `-strict_atoms` subsection ~line 113)
- Test: `tests/test_strict_atoms_default.py` (new)

**Interfaces:**
- Produces: `clausal.pythonic_ast.nodes.ImplicitAtomsDeclaration` (zero-field `Node`, alias `ImplicitAtomsItem` in importing modules); a `-implicit_atoms` directive that appends `ImplicitAtomsDeclaration()` to `module_items`; a `SyntaxError` when a file carries both `-strict_atoms` and `-implicit_atoms`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_strict_atoms_default.py`:

```python
"""Tests for strict-atoms-by-default (staged binary flip).

See docs/superpowers/specs/2026-07-24-strict-atoms-default-design.md.
Atom names are prefixed ``sad_`` (strict-atoms-default) and unique per
test so the process-wide predicate_builtins dict is not cross-polluted.
"""
from __future__ import annotations

import os
import tempfile

import pytest

import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module, predicate_builtins
from clausal.logic.predicate import PredicateMeta


def _load_inline_clausal(name: str, source: str):
    """Write `source` to a temp .clausal file and load it (avoids the
    conftest .clausal collector that would surface persistent fixtures)."""
    with tempfile.NamedTemporaryFile(
        suffix=".clausal", mode="w", delete=False
    ) as f:
        f.write(source)
        f.flush()
        path = f.name
    try:
        return _load_module(name, path)
    finally:
        os.unlink(path)


def test_implicit_atoms_mints_undeclared_bare_atom():
    """`-implicit_atoms` opts into loose auto-mint: an undeclared bare
    atom is minted into the global dict (today's default behavior)."""
    assert "sad_implicit_red" not in predicate_builtins
    source = (
        "-implicit_atoms\n"
        "\n"
        "ColorImplicit(sad_implicit_red),\n"
    )
    mod = _load_inline_clausal("_sad_implicit_mints", source)
    assert isinstance(predicate_builtins["sad_implicit_red"], PredicateMeta)
    assert mod.sad_implicit_red is predicate_builtins["sad_implicit_red"]


def test_implicit_atoms_parenthesised_form():
    """`-implicit_atoms()` is accepted, same as the bare form."""
    source = (
        "-implicit_atoms()\n"
        "\n"
        "ColorImplicitParen(sad_implicit_paren_blue),\n"
    )
    mod = _load_inline_clausal("_sad_implicit_paren", source)
    assert isinstance(mod.sad_implicit_paren_blue, PredicateMeta)


def test_implicit_atoms_rejects_arguments():
    """`-implicit_atoms(foo)` is a SyntaxError — the marker takes no args."""
    source = "-implicit_atoms(foo)\n\nX(y),\n"
    with pytest.raises(SyntaxError) as exc_info:
        _load_inline_clausal("_sad_implicit_args", source)
    assert "-implicit_atoms takes no arguments" in str(exc_info.value)


def test_strict_and_implicit_mutually_exclusive():
    """A file carrying both directives is a SyntaxError."""
    source = (
        "-strict_atoms\n"
        "-implicit_atoms\n"
        "\n"
        "X(sad_both_atom),\n"
    )
    with pytest.raises(SyntaxError) as exc_info:
        _load_inline_clausal("_sad_both", source)
    msg = str(exc_info.value)
    assert "mutually exclusive" in msg
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=/workspace/clausal-bug-fix ~/.pyenv/versions/3.13.3/bin/python -m pytest tests/test_strict_atoms_default.py -v`
Expected: FAIL — `test_implicit_atoms_rejects_arguments` and `test_strict_and_implicit_mutually_exclusive` fail because `-implicit_atoms` is an unknown directive (`SyntaxError: Unknown directive: -implicit_atoms(...)` — wrong message / wrong trigger), and the mint/paren tests fail on the unknown directive too.

- [ ] **Step 3: Add the `ImplicitAtomsDeclaration` node**

In `clausal/pythonic_ast/nodes.py`, immediately after the `StrictAtomsDeclaration` class (ends line 1107) add:

```python
@node_class
class ImplicitAtomsDeclaration(Node):
    """Module item: ``-implicit_atoms`` directive marker.

    Presence in ``module_items`` opts the file into the *loose* atom
    default: undeclared bare atom references auto-mint into the
    process-wide global dict instead of raising ``NameError``.  It is the
    inverse of ``-strict_atoms`` and the escape hatch that survives the
    strict-by-default flip — the REPL injects it so interactive sessions
    keep auto-minting.

    Takes no arguments — its mere presence is the signal.  A file may not
    carry both ``-implicit_atoms`` and ``-strict_atoms``;
    ``compiler_v2._process_bare_atom_refs`` rejects that with a
    ``SyntaxError``.
    """
    pass
```

In the `__all__` list (line 90), add `"ImplicitAtomsDeclaration"`:

```python
    "BareAtomRefs", "StrictAtomsDeclaration", "ImplicitAtomsDeclaration",
    "OverwritesDeclaration",
```

- [ ] **Step 4: Wire the directive in `term_rewriting.py`**

Add to the node import block (after the `ImportModuleDirective as ImportModuleItem,` line ~15):

```python
    ImplicitAtomsDeclaration as ImplicitAtomsItem,
```

Add the dispatch branch in `_handle_directive`, immediately after the `strict_atoms` branch (line 3055-3056):

```python
        if name == "implicit_atoms":
            return transformer._handle_implicit_atoms_directive(args, expr_stmt)
```

Update the known-directives error message (line 3064) to list the new directive:

```python
            f"-strict_atoms, -implicit_atoms, -overwrites)"
```

Add the handler immediately after `_handle_strict_atoms_directive` (after line 3198):

```python
    def _handle_implicit_atoms_directive(transformer, args, expr_stmt):
        """Process ``-implicit_atoms`` directive.

        Marker directive — no arguments.  Accepts the bare form
        ``-implicit_atoms`` and the parenthesised ``-implicit_atoms()``.
        Emits an ``ImplicitAtomsItem`` module item that opts the file into
        loose (auto-mint) atom resolution — the inverse of ``-strict_atoms``.
        """
        if args:
            raise SyntaxError(
                "-implicit_atoms takes no arguments: use bare "
                "`-implicit_atoms` or `-implicit_atoms()`"
            )
        transformer._module_items.append(ImplicitAtomsItem())
        return replace(Pass(), expr_stmt)
```

Update the bare-directive comment (line 2760-2762) to mention the new form:

```python
            # Bare -directive at module level (no parens, no args).
            # ``-strict_atoms`` and ``-implicit_atoms`` use this form; other
            # directives all take arguments and parse as the Call form above.
```

- [ ] **Step 5: Add mutual-exclusion check in `compiler_v2.py`**

Add to the node import block (after `StrictAtomsDeclaration as StrictAtomsItem,` line 36):

```python
    ImplicitAtomsDeclaration as ImplicitAtomsItem,
```

In `_process_bare_atom_refs`, replace the existing `strict_mode` assignment (lines 577-579):

```python
    strict_mode = any(
        isinstance(item, StrictAtomsItem) for item in module_items
    )
```

with:

```python
    strict_mode = any(
        isinstance(item, StrictAtomsItem) for item in module_items
    )
    implicit_mode = any(
        isinstance(item, ImplicitAtomsItem) for item in module_items
    )
    if strict_mode and implicit_mode:
        raise SyntaxError(
            f"{module_name}: -strict_atoms and -implicit_atoms are mutually "
            f"exclusive; a file may carry at most one"
        )
```

Leave the rest of the function unchanged — it still branches on `strict_mode`, so the effective default remains loose in this task.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `PYTHONPATH=/workspace/clausal-bug-fix ~/.pyenv/versions/3.13.3/bin/python -m pytest tests/test_strict_atoms_default.py -v`
Expected: PASS (4 passed).

- [ ] **Step 7: Run the full suite to confirm no regression**

Run: `PYTHONPATH=/workspace/clausal-bug-fix ~/.pyenv/versions/3.13.3/bin/python -m pytest -q`
Expected: PASS (same pass count as before, plus the 4 new tests).

- [ ] **Step 8: Document `-implicit_atoms`**

In `docs/directives.md`, after the `-strict_atoms` subsection (before the `-overwrites` subsection at line 115), add:

```markdown
### -implicit_atoms

**Problem**: Strict atom resolution is the default (a typo in a bare atom is a
compile-time `NameError`). Some files — prototypes, exploratory scripts, and
code that deliberately relies on Prolog-style ceremony-free tag atoms — want the
looser behavior back.

`-implicit_atoms` is a **file-level opt-in marker** that takes no arguments (bare
`-implicit_atoms` or `-implicit_atoms()`). With it present, an undeclared bare
atom reference is auto-minted into the process-wide global atom dict instead of
raising. It is the exact inverse of [`-strict_atoms`](#-strict_atoms); a file may
not carry both (doing so is a compile error).

The REPL uses this mode implicitly so interactive queries keep auto-minting.
```

- [ ] **Step 9: Commit**

```bash
git add clausal/pythonic_ast/nodes.py clausal/templating/term_rewriting.py clausal/logic/compiler_v2.py docs/directives.md tests/test_strict_atoms_default.py
git commit -m "feat(atoms): add -implicit_atoms directive (no-op escape hatch)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Pin the REPL to implicit mode (additive)

The REPL/IPython path constructs a fresh `EmbedTransformer` per cell at exactly one site. Give `EmbedTransformer` an `implicit_atoms_default` flag; the REPL passes `True`. While the default is still loose this is a no-op, but it must land *before* the Task 4 flip so interactive sessions never break.

**Files:**
- Modify: `clausal/templating/term_rewriting.py` (`EmbedTransformer.__init__` line 2447; `visit_Module` line 2637-2647)
- Modify: `clausal/import_hook.py` (`_FreshEmbedTransformer.visit` line 859)
- Test: `tests/test_strict_atoms_default.py` (append)

**Interfaces:**
- Consumes: `ImplicitAtomsItem` (`ImplicitAtomsDeclaration`) and `StrictAtomsItem` from Task 1.
- Produces: `EmbedTransformer(implicit_atoms_default: bool = False)`; when `True`, `visit_Module` appends an `ImplicitAtomsDeclaration` to `_module_items` unless the file already carries `-strict_atoms`/`-implicit_atoms`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_strict_atoms_default.py`:

```python
import ast

from clausal.templating.term_rewriting import EmbedTransformer
from clausal.pythonic_ast.nodes import ImplicitAtomsDeclaration


def test_repl_transformer_injects_implicit_atoms():
    """A transformer in REPL mode seeds an ImplicitAtomsDeclaration so
    interactive cells auto-mint even under the strict file default."""
    tree = ast.parse("Color(sad_repl_undeclared),\n")
    t = EmbedTransformer(implicit_atoms_default=True)
    t.visit(tree)
    assert any(
        isinstance(it, ImplicitAtomsDeclaration) for it in t._module_items
    )


def test_file_transformer_does_not_inject_implicit_atoms():
    """The default (file) transformer does NOT seed implicit mode."""
    tree = ast.parse("Color(sad_file_undeclared),\n")
    t = EmbedTransformer()
    t.visit(tree)
    assert not any(
        isinstance(it, ImplicitAtomsDeclaration) for it in t._module_items
    )


def test_repl_transformer_respects_explicit_strict():
    """REPL mode must not override an explicit -strict_atoms in the cell."""
    tree = ast.parse("-strict_atoms\nColor(sad_repl_strict),\n")
    t = EmbedTransformer(implicit_atoms_default=True)
    t.visit(tree)
    assert not any(
        isinstance(it, ImplicitAtomsDeclaration) for it in t._module_items
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=/workspace/clausal-bug-fix ~/.pyenv/versions/3.13.3/bin/python -m pytest tests/test_strict_atoms_default.py -k repl_transformer -v`
Expected: FAIL — `EmbedTransformer.__init__() got an unexpected keyword argument 'implicit_atoms_default'`.

- [ ] **Step 3: Add the constructor flag**

In `clausal/templating/term_rewriting.py`, change `EmbedTransformer.__init__` (line 2447):

```python
    def __init__(transformer, source_lines=None):
```

to:

```python
    def __init__(transformer, source_lines=None, implicit_atoms_default=False):
```

and, inside the body (after `transformer._module_items: list = []` line 2457), add:

```python
        # When True (set by the REPL/IPython transform site), the file
        # defaults to loose auto-mint: visit_Module seeds an
        # ImplicitAtomsDeclaration unless the cell states its own mode.
        transformer._implicit_atoms_default = implicit_atoms_default
```

- [ ] **Step 4: Seed the marker in `visit_Module`**

In `visit_Module` (lines 2645-2647), after the existing `BareAtomRefs` emission block:

```python
        if transformer._bare_atom_refs:
            transformer._module_items.append(
                BareAtomRefsItem(names=frozenset(transformer._bare_atom_refs))
            )
```

add:

```python
        if transformer._implicit_atoms_default and not any(
            isinstance(it, (StrictAtomsItem, ImplicitAtomsItem))
            for it in transformer._module_items
        ):
            transformer._module_items.append(ImplicitAtomsItem())
```

(`StrictAtomsItem` is already imported at line 21; `ImplicitAtomsItem` was added in Task 1.)

- [ ] **Step 5: Run the transformer tests to verify they pass**

Run: `PYTHONPATH=/workspace/clausal-bug-fix ~/.pyenv/versions/3.13.3/bin/python -m pytest tests/test_strict_atoms_default.py -k repl_transformer -v`
Expected: PASS (2 passed — `injects` and `respects_explicit_strict`; `does_not_inject` is under a different `-k` but run the whole file next).

- [ ] **Step 6: Wire the REPL construction site**

In `clausal/import_hook.py`, `_FreshEmbedTransformer.visit` (line 859), change:

```python
            tree = EmbedTransformer().visit(tree)
```

to:

```python
            tree = EmbedTransformer(implicit_atoms_default=True).visit(tree)
```

- [ ] **Step 7: Run the full new-tests file to confirm**

Run: `PYTHONPATH=/workspace/clausal-bug-fix ~/.pyenv/versions/3.13.3/bin/python -m pytest tests/test_strict_atoms_default.py -v`
Expected: PASS (all tests including the 3 transformer tests).

- [ ] **Step 8: Run the full suite**

Run: `PYTHONPATH=/workspace/clausal-bug-fix ~/.pyenv/versions/3.13.3/bin/python -m pytest -q`
Expected: PASS, no regressions.

- [ ] **Step 9: Commit**

```bash
git add clausal/templating/term_rewriting.py clausal/import_hook.py tests/test_strict_atoms_default.py
git commit -m "feat(repl): pin interactive cells to implicit atom mode

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Codemod — arm every in-repo file with `-implicit_atoms`

Add `-implicit_atoms` to every `clausal/**` and `tests/fixtures/**` `.clausal` file that does not already carry `-strict_atoms` (or `-implicit_atoms`). This is a no-op while the default is loose, and it is what lets Task 4's flip break nothing. The `conftest.py` `.clausal` collector loads every fixture, so an unarmed fixture would fail collection after the flip — hence fixtures are in scope.

**Files:**
- Create: `tools/codemods/add_implicit_atoms.py`
- Create: `tools/codemods/test_add_implicit_atoms.py`
- Modify (mechanical): `clausal/**/*.clausal`, `tests/fixtures/**/*.clausal`

**Interfaces:**
- Produces: `add_implicit_atoms(path: str) -> bool` — inserts the directive into one file, returns `True` if the file was modified, `False` if skipped (already has a strict/implicit marker). Idempotent.

- [ ] **Step 1: Write the failing codemod unit test**

Create `tools/codemods/test_add_implicit_atoms.py`:

```python
"""Unit test for the add_implicit_atoms codemod (Task 3)."""
from __future__ import annotations

import importlib.util
import os

_SPEC = importlib.util.spec_from_file_location(
    "add_implicit_atoms",
    os.path.join(os.path.dirname(__file__), "add_implicit_atoms.py"),
)
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)
add_implicit_atoms = _MOD.add_implicit_atoms


def test_inserts_before_first_code_line(tmp_path):
    f = tmp_path / "a.clausal"
    f.write_text("# a comment\n\nColor(red),\n")
    changed = add_implicit_atoms(str(f))
    assert changed is True
    lines = f.read_text().splitlines()
    # Directive goes before the first non-comment, non-blank line.
    assert "-implicit_atoms" in lines
    assert lines.index("-implicit_atoms") < lines.index("Color(red),")
    # Leading comment is preserved above the directive.
    assert lines[0] == "# a comment"


def test_skips_file_with_strict_atoms(tmp_path):
    f = tmp_path / "b.clausal"
    original = "-strict_atoms\n\nColor(red),\n"
    f.write_text(original)
    changed = add_implicit_atoms(str(f))
    assert changed is False
    assert f.read_text() == original


def test_idempotent(tmp_path):
    f = tmp_path / "c.clausal"
    f.write_text("Color(red),\n")
    assert add_implicit_atoms(str(f)) is True
    assert add_implicit_atoms(str(f)) is False
    assert f.read_text().count("-implicit_atoms") == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTHONPATH=/workspace/clausal-bug-fix ~/.pyenv/versions/3.13.3/bin/python -m pytest tools/codemods/test_add_implicit_atoms.py -v`
Expected: FAIL — `add_implicit_atoms.py` does not exist.

- [ ] **Step 3: Write the codemod**

Create `tools/codemods/add_implicit_atoms.py`:

```python
"""Codemod: add ``-implicit_atoms`` to .clausal files lacking an atom-mode
marker. Throwaway migration tool for the strict-atoms-by-default flip
(Task 3 / Phase 1 of the plan). Idempotent; skips files that already carry
``-strict_atoms`` or ``-implicit_atoms``.

Usage:
    python tools/codemods/add_implicit_atoms.py clausal tests/fixtures
"""
from __future__ import annotations

import re
import sys

_MARKER_RE = re.compile(r"^\s*-\s*(strict_atoms|implicit_atoms)\b")


def add_implicit_atoms(path: str) -> bool:
    """Insert ``-implicit_atoms`` before the first non-comment, non-blank
    line of *path*. Returns True if modified, False if skipped."""
    with open(path, "r") as fh:
        lines = fh.readlines()

    if any(_MARKER_RE.match(line) for line in lines):
        return False

    insert_at = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "" or stripped.startswith("#"):
            continue
        insert_at = i
        break
    else:
        # File is all comments/blank — append at end.
        insert_at = len(lines)

    lines.insert(insert_at, "-implicit_atoms\n")
    with open(path, "w") as fh:
        fh.writelines(lines)
    return True


def _walk(roots: list[str]) -> int:
    import os
    changed = 0
    for root in roots:
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                if name.endswith(".clausal"):
                    if add_implicit_atoms(os.path.join(dirpath, name)):
                        changed += 1
    return changed


if __name__ == "__main__":
    roots = sys.argv[1:] or ["clausal", "tests/fixtures"]
    n = _walk(roots)
    print(f"add_implicit_atoms: modified {n} file(s)")
```

- [ ] **Step 4: Run the codemod unit test to verify it passes**

Run: `PYTHONPATH=/workspace/clausal-bug-fix ~/.pyenv/versions/3.13.3/bin/python -m pytest tools/codemods/test_add_implicit_atoms.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Run the codemod across the repo**

Run:
```bash
cd /workspace/clausal-bug-fix
~/.pyenv/versions/3.13.3/bin/python tools/codemods/add_implicit_atoms.py clausal tests/fixtures
```
Expected: prints `add_implicit_atoms: modified N file(s)`.

- [ ] **Step 6: Run the full suite (Phase 2 checkpoint)**

Run: `PYTHONPATH=/workspace/clausal-bug-fix ~/.pyenv/versions/3.13.3/bin/python -m pytest -q`
Expected: PASS. Behavior is unchanged (the marker is a no-op under the loose default), so any failure indicates a file where the insertion landed in a syntactically wrong place — inspect that file's first lines and fix the codemod's insertion point, re-run Step 5 (idempotent), re-run this step.

Note: any fixture that asserted the *loose default without a directive* still passes because loose is still the default here; those become meaningful only after Task 4.

- [ ] **Step 7: Commit**

```bash
git add tools/codemods/add_implicit_atoms.py tools/codemods/test_add_implicit_atoms.py
git add clausal tests/fixtures
git commit -m "chore(atoms): arm all in-repo .clausal files with -implicit_atoms

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Flip the default to strict + deprecate `-strict_atoms`

Now that every in-repo file is armed, invert the resolution default: neither directive ⇒ strict. `-strict_atoms` becomes redundant and emits a once-per-process deprecation notice.

**Files:**
- Modify: `clausal/logic/compiler_v2.py` (warning class + guard near line 40; `_process_bare_atom_refs` loop ~line 577-603)
- Modify: `docs/directives.md` (`-strict_atoms` subsection ~line 86)
- Test: `tests/test_strict_atoms_default.py` (append)

**Interfaces:**
- Consumes: `strict_mode` / `implicit_mode` locals from Task 1.
- Produces: `ClausalStrictAtomsDeprecationWarning(DeprecationWarning)`; module-global `_strict_atoms_deprecation_emitted`; the new default (undeclared bare atom ⇒ `NameError` unless `-implicit_atoms`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_strict_atoms_default.py`:

```python
import warnings

import clausal.logic.compiler_v2 as _compiler_v2
from clausal.logic.compiler_v2 import ClausalStrictAtomsDeprecationWarning


def test_undeclared_bare_atom_raises_by_default():
    """With no directive, an undeclared bare atom is a NameError."""
    assert "sad_default_red" not in predicate_builtins
    source = "ColorDefault(sad_default_red),\n"
    with pytest.raises(NameError) as exc_info:
        _load_inline_clausal("_sad_default_strict", source)
    msg = str(exc_info.value)
    assert "sad_default_red" in msg
    assert "-module" in msg and "-private" in msg
    assert "sad_default_red" not in predicate_builtins


def test_implicit_atoms_still_mints_after_flip():
    """`-implicit_atoms` remains the loose escape hatch after the flip."""
    source = "-implicit_atoms\nColorStill(sad_still_green),\n"
    mod = _load_inline_clausal("_sad_still_mints", source)
    assert isinstance(mod.sad_still_green, PredicateMeta)


def test_strict_atoms_deprecation_warns_once_per_process():
    """`-strict_atoms` still enforces strict, and emits the deprecation
    warning at most once per process."""
    _compiler_v2._strict_atoms_deprecation_emitted = False  # reset guard
    src = "-strict_atoms\n-module(m, [ok])\nUse(ok),\n"
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _load_inline_clausal("_sad_dep_1", src)
        _load_inline_clausal("_sad_dep_2", src)
    dep = [
        w for w in caught
        if issubclass(w.category, ClausalStrictAtomsDeprecationWarning)
    ]
    assert len(dep) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=/workspace/clausal-bug-fix ~/.pyenv/versions/3.13.3/bin/python -m pytest tests/test_strict_atoms_default.py -k "default or deprecation or still_mints" -v`
Expected: FAIL — `test_undeclared_bare_atom_raises_by_default` fails (atom is minted, no NameError); import of `ClausalStrictAtomsDeprecationWarning` fails.

- [ ] **Step 3: Add the warning class and guard**

In `clausal/logic/compiler_v2.py`, near the other warning classes (after `ClausalAtomShadowingWarning` around line 40-58), add:

```python
_strict_atoms_deprecation_emitted = False


class ClausalStrictAtomsDeprecationWarning(DeprecationWarning):
    """``-strict_atoms`` is redundant now that strict resolution is the
    default. The directive still works but can be deleted."""


def _warn_strict_atoms_deprecated() -> None:
    """Emit the ``-strict_atoms`` deprecation notice at most once per
    process. Guarded by a module global rather than the warnings-filter
    dedup so it is exactly-once regardless of the consumer's filters."""
    global _strict_atoms_deprecation_emitted
    if _strict_atoms_deprecation_emitted:
        return
    _strict_atoms_deprecation_emitted = True
    import warnings
    warnings.warn(
        "-strict_atoms is redundant: strict atom resolution is now the "
        "default. The directive still works but can be deleted. "
        "(Shown once per process.)",
        ClausalStrictAtomsDeprecationWarning,
        stacklevel=2,
    )
```

- [ ] **Step 4: Flip the default in `_process_bare_atom_refs`**

Keep the Task 1 mutual-exclusion `if` exactly as it is. Insert the two new statements (`effective_strict` derivation + deprecation emission) directly after that `if` block, so the region reads in full:

```python
    if strict_mode and implicit_mode:                       # unchanged (Task 1)
        raise SyntaxError(
            f"{module_name}: -strict_atoms and -implicit_atoms are mutually "
            f"exclusive; a file may carry at most one"
        )
    # ── NEW in this task ──────────────────────────────────────────────
    # Strict is the default (Python-style): undeclared bare atoms raise
    # unless the file opts into loose auto-mint via -implicit_atoms.
    effective_strict = not implicit_mode
    if strict_mode:
        _warn_strict_atoms_deprecated()
```

Then, in the minting loop, change the branch condition from `strict_mode` to `effective_strict` (line ~592):

```python
            if effective_strict:
                undeclared.append(name)
                continue
```

Leave the `undeclared` collection and the closing `raise NameError(...)` (lines ~600-603) unchanged.

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `PYTHONPATH=/workspace/clausal-bug-fix ~/.pyenv/versions/3.13.3/bin/python -m pytest tests/test_strict_atoms_default.py -v`
Expected: PASS (all tests in the file).

- [ ] **Step 6: Run the full suite**

Run: `PYTHONPATH=/workspace/clausal-bug-fix ~/.pyenv/versions/3.13.3/bin/python -m pytest -q`
Expected: PASS — every in-repo file was armed in Task 3, so nothing regresses. If a test that constructs `.clausal` source inline (not via a fixture file) now fails with a strict `NameError`, that test relied on the old loose default; add `-implicit_atoms` to its inline source. List any such tests in the commit message.

- [ ] **Step 7: Update the `-strict_atoms` docs**

In `docs/directives.md`, at the top of the `-strict_atoms` subsection (line 86), add a deprecation banner:

```markdown
### -strict_atoms

> **Deprecated (still supported).** Strict atom resolution is now the default,
> so this directive is redundant and can be deleted. It still forces strict mode
> where present; loading a file that uses it emits a one-per-process
> `ClausalStrictAtomsDeprecationWarning`. To opt a file *out* of strict, use
> [`-implicit_atoms`](#-implicit_atoms).
```

- [ ] **Step 8: Commit**

```bash
git add clausal/logic/compiler_v2.py docs/directives.md tests/test_strict_atoms_default.py
git commit -m "feat(atoms)!: strict atoms are the default; deprecate -strict_atoms

BREAKING CHANGE: undeclared bare atoms now raise NameError unless the file
carries -implicit_atoms. -strict_atoms is redundant and deprecated.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Pilot strictness on a small file set

Remove `-implicit_atoms` from a small, high-value set of files so they become strict, and fix the fallout (real typos surface here). This validates the migration ergonomics before the full sweep.

**Files:**
- Modify (remove directive): 2-3 chosen `clausal/**/*.clausal` files
- Modify (fix fallout): those files' `-module`/`-private`/`-import_from` declarations as needed

**Interfaces:** none (source-only migration).

- [ ] **Step 1: List candidate files and pick the pilot set**

Run:
```bash
cd /workspace/clausal-bug-fix
git grep -l "^-implicit_atoms" -- 'clausal/**/*.clausal'
```
Pick 2-3 rule-bearing stdlib files (smaller files with a clear set of atoms). Record the chosen paths.

- [ ] **Step 2: Remove the directive from each pilot file**

For each chosen file, delete its `-implicit_atoms` line (edit the file directly; do not use the codemod, which only adds).

- [ ] **Step 3: Run the suite to surface fallout**

Run: `PYTHONPATH=/workspace/clausal-bug-fix ~/.pyenv/versions/3.13.3/bin/python -m pytest -q`
Expected: either PASS (the file was already atom-clean) or a `NameError` naming an undeclared atom in a pilot file.

- [ ] **Step 4: Fix each reported atom**

For every atom in the `NameError`, apply the correct fix per the diagnostic:
- a genuine typo → correct the spelling;
- a legitimate module-local tag → add it to `-module(<name>, [..., tag])` or `-private([tag])`;
- a shared tag owned elsewhere → add `-import_from(<owner>, [tag])`.

Re-run Step 3 until green. Record any genuine typos found (that is the payoff evidence).

- [ ] **Step 5: Commit**

```bash
git add clausal
git commit -m "refactor(atoms): pilot strict mode on <N> stdlib files

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Sweep `-implicit_atoms` from files where strict is fine + finish docs

Remove `-implicit_atoms` from every file that can be strict, leaving it only where loose is genuinely wanted (prototypes, files with intentional dynamic-atom patterns). Finalize the remaining docs.

**Files:**
- Modify (remove directive): remaining `clausal/**` and `tests/fixtures/**` `.clausal` files where strict passes
- Modify: `docs/syntax.md` (atoms callout ~line 101), `docs/builtins.md` (`global_atom/2` cross-ref ~line 549)

**Interfaces:** none (source + docs).

- [ ] **Step 1: Remove the directive repo-wide (trial)**

Run:
```bash
cd /workspace/clausal-bug-fix
grep -rlE "^-implicit_atoms" clausal tests/fixtures | while read f; do
  sed -i '/^-implicit_atoms$/d' "$f"
done
```

- [ ] **Step 2: Run the suite to find files that genuinely need loose mode**

Run: `PYTHONPATH=/workspace/clausal-bug-fix ~/.pyenv/versions/3.13.3/bin/python -m pytest -q`
Expected: some `NameError`s. For each failing file, decide:
- **fixable** → add the proper `-module`/`-private`/`-import_from` declaration (preferred);
- **genuinely loose** (dynamic/asserted atoms, prototype fixtures, fixtures that specifically test the loose default) → restore its `-implicit_atoms` line.

Iterate until green. Keep a short list of the files where `-implicit_atoms` was intentionally restored.

- [ ] **Step 3: Confirm the full suite is green**

Run: `PYTHONPATH=/workspace/clausal-bug-fix ~/.pyenv/versions/3.13.3/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 4: Update `docs/syntax.md`**

Replace the atoms opt-out callout (line 101) so strict is described as the default:

```markdown
    Atoms resolve strictly by default: an undeclared bare atom is a compile-time
    `NameError`, matching Python's treatment of undefined names. Files that want
    Prolog-style ceremony-free tag atoms opt out with
    [`-implicit_atoms`](directives.md#-implicit_atoms).
```

- [ ] **Step 5: Update `docs/builtins.md`**

At the `global_atom/2` reference (line 549), adjust the framing so it points at the strict default rather than `-strict_atoms`:

```markdown
`global_atom/2` is the reflection escape hatch for reaching a global atom by
name when a module-local declaration or an import shadows it — and the sanctioned
way for a strict-default file to obtain a global atom it does not list. See
[`-implicit_atoms`](directives.md#-implicit_atoms) for the file-level opt-out.
```

- [ ] **Step 6: Run the full suite one final time**

Run: `PYTHONPATH=/workspace/clausal-bug-fix ~/.pyenv/versions/3.13.3/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add clausal tests/fixtures docs/syntax.md docs/builtins.md
git commit -m "refactor(atoms): sweep -implicit_atoms; finalize strict-default docs

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review Notes

- **Spec coverage:** end-state runtime model → Tasks 1 & 4; five migration phases → Tasks 1-2 (Phase 1), 3 (Phases 1-2), 4 (Phase 3), 5 (Phase 4), 6 (Phase 5); REPL → Task 2; deprecation notice → Task 4; testing → tests in Tasks 1-4; touch points → all covered. The spec's "both directives → error" decision is Task 1 Step 5.
- **Ordering deviation from the spec's phase numbers (intentional):** the REPL plumbing (Task 2) lands *before* the flip (Task 4) so interactive sessions never break at the flip commit; both are Phase 3 in the spec.
- **Deferred decisions resolved:** codemod home = `tools/codemods/`; Phase 4 pilot set = chosen at Task 5 Step 1 from `git grep`.
- **Type consistency:** `ImplicitAtomsDeclaration`/alias `ImplicitAtomsItem`, `_process_bare_atom_refs`, `effective_strict`, `_warn_strict_atoms_deprecated`, `_strict_atoms_deprecation_emitted`, `ClausalStrictAtomsDeprecationWarning` used consistently across tasks.
