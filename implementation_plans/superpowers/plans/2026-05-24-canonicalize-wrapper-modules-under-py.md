# Canonicalize wrapper modules under `clausal.modules.py.*`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move every Python-library wrapper module (torch, sympy, jax, opencv, scipy_*, sklearn, spacy, yaml) from its current top-level location at `clausal/modules/<name>.py` (in each extension package) into the canonical subpackage `clausal/modules/py/<name>.py`, and remove the legacy `_mod.py` compat shims in core. Net effect: bare names like `torch` and `sympy` no longer collide with real PyPI packages in the runtime import hook.

**Architecture:** The clausal project documents `clausal.modules.py.*` as the canonical home for Python-library wrappers (see `clausal/modules/__init__.py` docstring). Stdlib wrappers (csv, uuid, re, ...) already live there. Third-party wrappers (torch, sympy, jax, ...) were never migrated — they shipped at top level when extracted into extension packages in commit `621abc7`. This plan completes that migration and removes the compat shims at the top level. The result is that `ModulesFinder` (the runtime meta-path hook) no longer has any bare wrapper names to intercept, so user `.py` code that does `import torch` reaches real torch. `.clausal` files use compile-time `_IMPORT_ALIASES` to map bare names to the new `clausal.modules.py.*` paths, so their behavior is unchanged.

**Tech Stack:** Python 3.13, setuptools (PEP 420 namespace-package contributions across multiple wheels), pytest.

---

## Background — the bug this fixes

Reproduce on `main` (after installing core clausal and any extension with a wrapper whose filename matches a real PyPI package):

```sh
python -c "import clausal; import torch.nn as nn"
```

Result: `RecursionError: maximum recursion depth exceeded`.

**Why:** `clausal/import_hook.py` installs `ModulesFinder`, a meta-path finder that redirects bare imports to `clausal.modules.<name>` if such a wrapper exists. After `import clausal`, an `import torch` from `.py` code is hijacked: `sys.modules["torch"]` becomes `clausal.modules.torch` (a 1300-line single-file wrapper, NOT a package). When code later does `import torch.nn`, Python can't find `torch.nn` as a submodule (the wrapper has no `__path__`), so it falls back to `getattr(torch_wrapper, "nn")`. The wrapper's `__getattr__` lazily initializes a dtype cache via `_export_dtypes()`, which calls `_ensure_torch()` → `_import_stdlib("torch")` → `importlib.import_module("torch")`. But `sys.modules["torch"]` is already aliased to the wrapper, so `_import_stdlib` returns the wrapper itself — a self-reference. The dtype cache initializer then does `t.float16` where `t IS clausal.modules.torch`, re-entering `__getattr__`, infinitely.

The cleanest fix is to remove the collision: rename `clausal/modules/torch.py` to `clausal/modules/py/torch.py`. After that, `ModulesFinder.find_spec("torch", ...)` looks up `clausal.modules.torch`, doesn't find it, returns `None`, and Python's normal import machinery delivers real torch. `.clausal` files compile bare `torch` references to `clausal.modules.py.torch` via `_IMPORT_ALIASES` — unchanged user-facing behavior.

This same collision risk exists for `sympy`, `jax`, `yaml` (filenames match PyPI package names). It does NOT currently fire for `opencv` (filename is `opencv.py`, not `cv2.py`) or `sklearn` (already in `_PASSTHROUGH`), but moving everything together prevents future regressions and removes the per-name exception-list maintenance burden.

---

## File structure

**Files being moved (one move per file, all source files keep their content unchanged):**

```
packages/clausal-torch/clausal/modules/torch.py                  → packages/clausal-torch/clausal/modules/py/torch.py
packages/clausal-torch/clausal/modules/torch_nn.py               → packages/clausal-torch/clausal/modules/py/torch_nn.py
packages/clausal-torch/clausal/modules/torch_data.py             → packages/clausal-torch/clausal/modules/py/torch_data.py
packages/clausal-torch/clausal/modules/torch_functional.py       → packages/clausal-torch/clausal/modules/py/torch_functional.py
packages/clausal-torch/clausal/modules/torch_distributions.py    → packages/clausal-torch/clausal/modules/py/torch_distributions.py

packages/clausal-sympy/clausal/modules/sympy.py                  → packages/clausal-sympy/clausal/modules/py/sympy.py

packages/clausal-jax/clausal/modules/jax.py                      → packages/clausal-jax/clausal/modules/py/jax.py
packages/clausal-jax/clausal/modules/jax_random.py               → packages/clausal-jax/clausal/modules/py/jax_random.py
packages/clausal-jax/clausal/modules/jax_nn.py                   → packages/clausal-jax/clausal/modules/py/jax_nn.py
packages/clausal-jax/clausal/modules/jax_transforms.py           → packages/clausal-jax/clausal/modules/py/jax_transforms.py
packages/clausal-jax/clausal/modules/jax_scipy.py                → packages/clausal-jax/clausal/modules/py/jax_scipy.py
packages/clausal-jax/clausal/modules/jax_sharding.py             → packages/clausal-jax/clausal/modules/py/jax_sharding.py
packages/clausal-jax/clausal/modules/jax_tree.py                 → packages/clausal-jax/clausal/modules/py/jax_tree.py
packages/clausal-jax/clausal/modules/jax_optax.py                → packages/clausal-jax/clausal/modules/py/jax_optax.py
packages/clausal-jax/clausal/modules/jax_equinox.py              → packages/clausal-jax/clausal/modules/py/jax_equinox.py
packages/clausal-jax/clausal/modules/jax_flax.py                 → packages/clausal-jax/clausal/modules/py/jax_flax.py

packages/clausal-opencv/clausal/modules/_opencv_handles.py       → packages/clausal-opencv/clausal/modules/py/_opencv_handles.py
packages/clausal-opencv/clausal/modules/opencv.py                → packages/clausal-opencv/clausal/modules/py/opencv.py
packages/clausal-opencv/clausal/modules/opencv_calib3d.py        → packages/clausal-opencv/clausal/modules/py/opencv_calib3d.py
packages/clausal-opencv/clausal/modules/opencv_color.py          → packages/clausal-opencv/clausal/modules/py/opencv_color.py
packages/clausal-opencv/clausal/modules/opencv_contours.py       → packages/clausal-opencv/clausal/modules/py/opencv_contours.py
packages/clausal-opencv/clausal/modules/opencv_draw.py           → packages/clausal-opencv/clausal/modules/py/opencv_draw.py
packages/clausal-opencv/clausal/modules/opencv_features.py       → packages/clausal-opencv/clausal/modules/py/opencv_features.py
packages/clausal-opencv/clausal/modules/opencv_imgproc.py        → packages/clausal-opencv/clausal/modules/py/opencv_imgproc.py
packages/clausal-opencv/clausal/modules/opencv_objdetect.py      → packages/clausal-opencv/clausal/modules/py/opencv_objdetect.py
packages/clausal-opencv/clausal/modules/opencv_video.py          → packages/clausal-opencv/clausal/modules/py/opencv_video.py

packages/clausal-scipy/clausal/modules/_scipy_relations.py       → packages/clausal-scipy/clausal/modules/py/_scipy_relations.py
packages/clausal-scipy/clausal/modules/_scipy_units.py           → packages/clausal-scipy/clausal/modules/py/_scipy_units.py
packages/clausal-scipy/clausal/modules/scipy_cluster.py          → packages/clausal-scipy/clausal/modules/py/scipy_cluster.py
packages/clausal-scipy/clausal/modules/scipy_constants.py        → packages/clausal-scipy/clausal/modules/py/scipy_constants.py
packages/clausal-scipy/clausal/modules/scipy_differentiate.py    → packages/clausal-scipy/clausal/modules/py/scipy_differentiate.py
packages/clausal-scipy/clausal/modules/scipy_fft.py              → packages/clausal-scipy/clausal/modules/py/scipy_fft.py
packages/clausal-scipy/clausal/modules/scipy_integrate.py        → packages/clausal-scipy/clausal/modules/py/scipy_integrate.py
packages/clausal-scipy/clausal/modules/scipy_interpolate.py      → packages/clausal-scipy/clausal/modules/py/scipy_interpolate.py
packages/clausal-scipy/clausal/modules/scipy_linalg.py           → packages/clausal-scipy/clausal/modules/py/scipy_linalg.py
packages/clausal-scipy/clausal/modules/scipy_ndimage.py          → packages/clausal-scipy/clausal/modules/py/scipy_ndimage.py
packages/clausal-scipy/clausal/modules/scipy_optimize.py         → packages/clausal-scipy/clausal/modules/py/scipy_optimize.py
packages/clausal-scipy/clausal/modules/scipy_signal.py           → packages/clausal-scipy/clausal/modules/py/scipy_signal.py
packages/clausal-scipy/clausal/modules/scipy_sparse.py           → packages/clausal-scipy/clausal/modules/py/scipy_sparse.py
packages/clausal-scipy/clausal/modules/scipy_spatial.py          → packages/clausal-scipy/clausal/modules/py/scipy_spatial.py
packages/clausal-scipy/clausal/modules/scipy_special.py          → packages/clausal-scipy/clausal/modules/py/scipy_special.py
packages/clausal-scipy/clausal/modules/scipy_stats.py            → packages/clausal-scipy/clausal/modules/py/scipy_stats.py

packages/clausal-sklearn/clausal/modules/sklearn.py              → packages/clausal-sklearn/clausal/modules/py/sklearn.py
packages/clausal-spacy/clausal/modules/spacy.py                  → packages/clausal-spacy/clausal/modules/py/spacy.py
packages/clausal-yaml/clausal/modules/yaml.py                    → packages/clausal-yaml/clausal/modules/py/yaml.py
```

**Files being deleted (core compat shims):**

```
clausal/modules/csv_mod.py
clausal/modules/files_mod.py
clausal/modules/hash_mod.py
clausal/modules/hmac_mod.py
clausal/modules/http_mod.py
clausal/modules/json_mod.py
clausal/modules/os_mod.py
clausal/modules/pbkdf2_mod.py
clausal/modules/process_mod.py
clausal/modules/random_mod.py
clausal/modules/tcp_mod.py
clausal/modules/url_mod.py
clausal/modules/uuid_mod.py
clausal/modules/date_time.py
clausal/modules/regex.py
clausal/modules/log.py
```

**Files being modified:**

```
clausal/modules/__init__.py                          # update docstring, keep __path__ extension
clausal/modules/py/__init__.py                       # add __path__ extension so extension wheels merge in
clausal/import_hook.py                               # update ModulesFinder._MODULES_PKG → "clausal.modules.py", drop _ALIASES["uuid"]
clausal/logic/compiler_v2.py                         # update _MODULE_ALIASES entries to point at py.*
clausal/templating/term_rewriting.py                 # update _IMPORT_ALIASES entries to point at py.*
```

**Files explicitly NOT being moved:**

- `clausal/modules/graphs.py`, `clausal/modules/imperial.py`, `clausal/modules/prolog.py`, `clausal/modules/sqlite.py`, `clausal/modules/units.py`, `clausal/modules/log.py`, `clausal/modules/date_time.py`, `clausal/modules/regex.py` — verify in Phase 2 whether these are real modules with content OR compat shims; only delete the latter (the ones whose body is `from clausal.modules.py.X import *`).
- `packages/clausal-provenance/clausal/modules/provenance/*` — this is a subpackage (`clausal.modules.provenance.*`), not a wrapper at the bare-name level. `provenance` is not a PyPI package name, so no collision. Leave alone.
- `clausal-trealla`, `clausal-scryer`, `clausal-gprolog` — these don't have wrappers under `clausal/modules/`; they expose different APIs. Leave alone.

---

## Phase 0 — Setup and baseline

### Task 0.1: Branch off main

**Files:** none (git only)

- [ ] **Step 1: Confirm clean working tree**

  Run: `git status -s`
  Expected: empty output, or only untracked files unrelated to this plan.

- [ ] **Step 2: Create branch from main**

  ```sh
  git fetch origin
  git checkout -b refactor/canonicalize-modules-py origin/main
  ```

- [ ] **Step 3: Verify branch**

  Run: `git branch --show-current && git log --oneline -1`
  Expected: `refactor/canonicalize-modules-py` and HEAD matches `origin/main`.

### Task 0.2: Install everything editable

**Files:** none

- [ ] **Step 1: Create venv**

  ```sh
  python3.13 -m venv .venv
  source .venv/bin/activate
  pip install --upgrade pip
  ```

- [ ] **Step 2: Install core editable**

  ```sh
  pip install -e .
  ```

- [ ] **Step 3: Install each extension editable**

  ```sh
  pip install -e packages/clausal-torch
  pip install -e packages/clausal-sympy
  pip install -e packages/clausal-jax
  pip install -e packages/clausal-opencv
  pip install -e packages/clausal-scipy
  pip install -e packages/clausal-sklearn
  pip install -e packages/clausal-spacy
  pip install -e packages/clausal-yaml
  ```

  Note: opencv requires `opencv-python-headless` first if you're on Linux without libGL: `pip install opencv-python-headless`.

  If any extension fails to install because a heavy dependency (torch, jax, opencv) can't build in the container, skip that extension and note it for Phase 1 — the corresponding Phase 1 sub-task can be done without running the tests, just verifying imports.

- [ ] **Step 4: Verify the bug reproduces**

  Run: `python -c "import clausal; import torch.nn as nn"`
  Expected: `RecursionError: maximum recursion depth exceeded`.

  If this does NOT reproduce, STOP — something in the environment is different from the analysis. Re-read the Background section, gather diagnostic info, and confirm with the human before proceeding.

### Task 0.3: Establish test baseline

**Files:** none

- [ ] **Step 1: Run core tests**

  ```sh
  pytest tests/ -x --timeout=30 2>&1 | tail -20
  ```

  Record the pass/fail counts. Any test that fails on `main` is pre-existing and not introduced by this plan — keep the list to compare against later.

- [ ] **Step 2: Run each extension's tests**

  ```sh
  for pkg in packages/clausal-{torch,sympy,jax,opencv,scipy,sklearn,spacy,yaml}; do
    echo "=== $pkg ==="
    pytest "$pkg/tests" -x --timeout=30 2>&1 | tail -5
  done
  ```

  Record baseline pass/fail per package.

- [ ] **Step 3: Commit nothing yet — just save the baseline**

  Save the captured output to a scratch file (e.g., `/tmp/baseline-test-output.txt`). Do not commit this file. It's a reference for spotting regressions.

### Task 0.4: Add `__path__` extension to `clausal/modules/py/__init__.py`

**Why:** When extension wheels install `clausal/modules/py/<name>.py` into site-packages alongside the core wheel's `clausal/modules/py/__init__.py`, Python's regular-package machinery only sees the core's directory by default. The core `clausal/modules/__init__.py` extends `__path__` to merge extension contributions; the `py/` subpackage needs the same.

**Files:**
- Modify: `clausal/modules/py/__init__.py` (append a block at the very end, before `__all__` if present)

- [ ] **Step 1: Read the existing file**

  Run: `head -30 clausal/modules/py/__init__.py`
  Note where the module docstring ends and where you'll insert the `__path__` extension. Insert it AFTER the docstring and `from __future__ import annotations`, but BEFORE any other code. Match the pattern from `clausal/modules/__init__.py`.

- [ ] **Step 2: Add the `__path__` extension**

  Insert this block in `clausal/modules/py/__init__.py` immediately after the module docstring and `from __future__ import annotations` line, before any other imports:

  ```python
  # Extend __path__ so that separately-installed wrapper distributions
  # (e.g. clausal-torch) that place files under clausal/modules/py/ in
  # site-packages are discoverable alongside the core source tree.
  import os as _os, site as _site
  for _sp in _site.getsitepackages():
      _candidate = _os.path.join(_sp, "clausal", "modules", "py")
      if _os.path.isdir(_candidate) and _candidate not in __path__:
          __path__.append(_candidate)
  del _os, _site
  ```

  (The `del` keeps these names out of the public namespace.)

- [ ] **Step 3: Smoke test the change**

  Run: `python -c "import clausal.modules.py; print(clausal.modules.py.__path__)"`
  Expected: prints a list with at least the source tree's `clausal/modules/py` path. (After Phase 1 it will include more entries.)

  Note: `py` is a soft keyword in some contexts; if the above syntax errors out (it shouldn't in Python 3.13), use `import importlib; m = importlib.import_module('clausal.modules.py'); print(m.__path__)`.

- [ ] **Step 4: Run core tests to confirm no regression**

  ```sh
  pytest tests/ -x --timeout=30 2>&1 | tail -10
  ```

  Expected: same pass/fail as baseline.

- [ ] **Step 5: Commit**

  ```sh
  git add clausal/modules/py/__init__.py
  git commit -m "refactor(modules): extend clausal.modules.py.__path__ for extension wheels

  Prepares clausal.modules.py to receive wrapper files from separately
  installed extension distributions (clausal-torch, clausal-sympy, etc.)
  by extending __path__ to include site-packages locations, matching
  the pattern already in clausal/modules/__init__.py."
  ```

---

## Phase 1 — Move extension wrappers (one package per commit)

For each sub-task in this phase, the work pattern is the same: move files, update aliases, run tests, commit. The pattern is spelled out in full for Task 1.1 (clausal-torch); subsequent tasks reference back to it with the specific list of files and alias entries.

### Task 1.1: Move clausal-torch wrappers

**Files:**

- Move: 5 files from `packages/clausal-torch/clausal/modules/` to `packages/clausal-torch/clausal/modules/py/`:
  - `torch.py`, `torch_nn.py`, `torch_data.py`, `torch_functional.py`, `torch_distributions.py`
- Modify: `clausal/templating/term_rewriting.py` (`_IMPORT_ALIASES`, around line 1255)
- Modify: `clausal/logic/compiler_v2.py` (`_MODULE_ALIASES`, around line 196)

- [ ] **Step 1: Create the destination directory**

  ```sh
  mkdir -p packages/clausal-torch/clausal/modules/py
  ```

  Do NOT create an `__init__.py` in this directory. Per `packages/clausal-torch/pyproject.toml`, this is a namespace-package contribution; `__init__.py` is owned by the core distribution.

- [ ] **Step 2: Move the files**

  ```sh
  git mv packages/clausal-torch/clausal/modules/torch.py               packages/clausal-torch/clausal/modules/py/torch.py
  git mv packages/clausal-torch/clausal/modules/torch_nn.py            packages/clausal-torch/clausal/modules/py/torch_nn.py
  git mv packages/clausal-torch/clausal/modules/torch_data.py          packages/clausal-torch/clausal/modules/py/torch_data.py
  git mv packages/clausal-torch/clausal/modules/torch_functional.py    packages/clausal-torch/clausal/modules/py/torch_functional.py
  git mv packages/clausal-torch/clausal/modules/torch_distributions.py packages/clausal-torch/clausal/modules/py/torch_distributions.py
  ```

  Do not modify the file contents — internal imports already use `from clausal.modules.py._helpers import ...`, which still works after the move.

- [ ] **Step 3: Update `_IMPORT_ALIASES` in `clausal/templating/term_rewriting.py`**

  Locate the dict starting around line 1255. Change these five entries:

  ```python
  # Before:
  "torch": "torch",
  "torch_nn": "torch_nn",
  "torch_data": "torch_data",
  "torch_functional": "torch_functional",
  "torch_distributions": "torch_distributions",

  # After:
  "torch": "py.torch",
  "torch_nn": "py.torch_nn",
  "torch_data": "py.torch_data",
  "torch_functional": "py.torch_functional",
  "torch_distributions": "py.torch_distributions",
  ```

- [ ] **Step 4: Update `_MODULE_ALIASES` in `clausal/logic/compiler_v2.py`**

  Locate the dict around line 196. Apply the SAME five edits as Step 3.

- [ ] **Step 5: Reinstall clausal-torch so editable install picks up the new path**

  Editable installs don't always handle file moves cleanly. Force a refresh:

  ```sh
  pip install -e packages/clausal-torch --force-reinstall --no-deps
  ```

- [ ] **Step 6: Verify imports resolve**

  ```sh
  python -c "from clausal.modules.py import torch; print(torch.__file__)"
  python -c "from clausal.modules.py import torch_nn; print(torch_nn.__file__)"
  ```

  Expected: both print paths ending in `packages/clausal-torch/clausal/modules/py/torch.py` (or similar).

- [ ] **Step 7: Verify old location no longer resolves**

  ```sh
  python -c "from clausal.modules import torch" 2>&1 | tail -3
  ```

  Expected: `ModuleNotFoundError: No module named 'clausal.modules.torch'` (or similar). This is the WHOLE POINT — the wrapper is no longer at a bare-name-colliding path.

- [ ] **Step 8: Run clausal-torch tests**

  ```sh
  pytest packages/clausal-torch/tests -x --timeout=30 2>&1 | tail -10
  ```

  Expected: same pass count as baseline. If a test fails because a `.clausal` test fixture uses `-import_from(torch, ...)` and the compiler isn't routing it correctly, recheck Steps 3 and 4 — both alias dicts must be updated.

- [ ] **Step 9: Verify the bug fix on torch specifically**

  ```sh
  python -c "import clausal; import torch; import torch.nn as nn; print('real torch:', torch.__file__); print('real nn:', nn.__file__)"
  ```

  Expected: BOTH lines print paths under `site-packages/torch/`, NOT under `clausal/modules/`. No recursion error.

- [ ] **Step 10: Commit**

  ```sh
  git add -A
  git commit -m "refactor(clausal-torch): move wrappers under clausal.modules.py

  Moves torch, torch_nn, torch_data, torch_functional, torch_distributions
  from clausal/modules/ to clausal/modules/py/ in the clausal-torch
  package, and updates _IMPORT_ALIASES / _MODULE_ALIASES to point at the
  new locations.

  Fixes recursion when user .py code does \`import torch\` after
  \`import clausal\`: previously the runtime ModulesFinder aliased
  sys.modules['torch'] to the clausal wrapper, and the wrapper's
  __getattr__ infinitely recursed when accessing torch submodules.
  After this change, clausal.modules.torch no longer exists, so the
  finder returns None and Python falls through to real torch."
  ```

### Task 1.2: Move clausal-sympy wrappers

**Files:**
- Move: `packages/clausal-sympy/clausal/modules/sympy.py` → `packages/clausal-sympy/clausal/modules/py/sympy.py`
- Modify: `clausal/templating/term_rewriting.py` (one entry in `_IMPORT_ALIASES`)
- Modify: `clausal/logic/compiler_v2.py` (one entry in `_MODULE_ALIASES`)
- Update: `clausal/modules/__init__.py` docstring (line that says `sympy → clausal.modules.sympy` — change to `py.sympy`)

Follow the same step pattern as Task 1.1.

- [ ] **Step 1:** `mkdir -p packages/clausal-sympy/clausal/modules/py`

- [ ] **Step 2:**
  ```sh
  git mv packages/clausal-sympy/clausal/modules/sympy.py packages/clausal-sympy/clausal/modules/py/sympy.py
  ```

- [ ] **Step 3: Update `_IMPORT_ALIASES`**

  In `clausal/templating/term_rewriting.py`, change `"sympy": "sympy",` to `"sympy": "py.sympy",`.

- [ ] **Step 4: Update `_MODULE_ALIASES`**

  In `clausal/logic/compiler_v2.py`, change `"sympy": "sympy",` to `"sympy": "py.sympy",`.

- [ ] **Step 5: Update docstring in `clausal/modules/__init__.py`**

  In the docstring's "Legacy aliases" section, change the line:
  ```
  - ``sympy``       → ``clausal.modules.sympy`` (extracted: clausal-sympy package)
  ```
  to:
  ```
  - ``sympy``       → ``clausal.modules.py.sympy`` (extracted: clausal-sympy package)
  ```

- [ ] **Step 6: Reinstall**
  ```sh
  pip install -e packages/clausal-sympy --force-reinstall --no-deps
  ```

- [ ] **Step 7: Verify imports**
  ```sh
  python -c "from clausal.modules.py import sympy; print(sympy.__file__)"
  python -c "import clausal; import sympy; print('real sympy:', sympy.__file__)"
  ```
  Expected: clausal wrapper at `packages/clausal-sympy/.../py/sympy.py`; real sympy at `site-packages/sympy/__init__.py`.

- [ ] **Step 8: Run tests**
  ```sh
  pytest packages/clausal-sympy/tests -x --timeout=30 2>&1 | tail -10
  ```

- [ ] **Step 9: Commit**
  ```sh
  git add -A
  git commit -m "refactor(clausal-sympy): move wrapper under clausal.modules.py

  Same migration as clausal-torch — moves sympy.py from clausal/modules/
  to clausal/modules/py/ to eliminate bare-name collision with real PyPI
  sympy. Updates alias tables and the legacy-aliases docstring in
  clausal/modules/__init__.py."
  ```

### Task 1.3: Move clausal-jax wrappers

**Files:**
- Move: 10 files (jax, jax_random, jax_nn, jax_transforms, jax_scipy, jax_sharding, jax_tree, jax_optax, jax_equinox, jax_flax) from `packages/clausal-jax/clausal/modules/` to `packages/clausal-jax/clausal/modules/py/`.
- Modify: `clausal/templating/term_rewriting.py` (10 entries in `_IMPORT_ALIASES`)
- Modify: `clausal/logic/compiler_v2.py` (10 entries in `_MODULE_ALIASES`)

Same step pattern as Task 1.1.

- [ ] **Step 1:** `mkdir -p packages/clausal-jax/clausal/modules/py`

- [ ] **Step 2: Move files**
  ```sh
  for f in jax.py jax_random.py jax_nn.py jax_transforms.py jax_scipy.py jax_sharding.py jax_tree.py jax_optax.py jax_equinox.py jax_flax.py; do
      git mv "packages/clausal-jax/clausal/modules/$f" "packages/clausal-jax/clausal/modules/py/$f"
  done
  ```

- [ ] **Step 3: Update both alias dicts**

  In `clausal/templating/term_rewriting.py` AND `clausal/logic/compiler_v2.py`, change all 10 jax entries from `"jax_X": "jax_X"` to `"jax_X": "py.jax_X"` (and `"jax": "jax"` → `"jax": "py.jax"`).

- [ ] **Step 4: Reinstall**
  ```sh
  pip install -e packages/clausal-jax --force-reinstall --no-deps
  ```

- [ ] **Step 5: Verify imports**
  ```sh
  python -c "from clausal.modules.py import jax, jax_nn, jax_optax; print(jax.__file__, jax_nn.__file__, jax_optax.__file__)"
  python -c "import clausal; import jax; print('real jax:', jax.__file__)"
  ```

- [ ] **Step 6: Run tests**
  ```sh
  pytest packages/clausal-jax/tests -x --timeout=30 2>&1 | tail -10
  ```

- [ ] **Step 7: Commit**
  ```sh
  git add -A
  git commit -m "refactor(clausal-jax): move wrappers under clausal.modules.py

  Moves jax + 9 submodule wrappers (jax_random, jax_nn, jax_transforms,
  jax_scipy, jax_sharding, jax_tree, jax_optax, jax_equinox, jax_flax)
  from clausal/modules/ to clausal/modules/py/. Updates _IMPORT_ALIASES
  and _MODULE_ALIASES."
  ```

### Task 1.4: Move clausal-opencv wrappers

**Files:**
- Move: 10 files (`opencv.py`, `opencv_calib3d.py`, `opencv_color.py`, `opencv_contours.py`, `opencv_draw.py`, `opencv_features.py`, `opencv_imgproc.py`, `opencv_objdetect.py`, `opencv_video.py`, `_opencv_handles.py`) under `py/`.
- Modify: `clausal/templating/term_rewriting.py` — these names are NOT currently in `_IMPORT_ALIASES`. ADD entries `"opencv": "py.opencv"`, `"opencv_calib3d": "py.opencv_calib3d"`, etc. for every moved file (10 entries total). Same for `_MODULE_ALIASES`.

  **Reason:** `opencv` doesn't currently collide with a real PyPI name (PyPI ships as `cv2`, not `opencv`), so the project didn't need a compile-time alias. After the move, `.clausal` files using `-import_from(opencv, [...])` would compile to bare `from opencv import ...` and fail because there's no real `opencv` package and the runtime fallback in `ModulesFinder` is being retired in Phase 3. Adding the aliases now keeps `.clausal` working.

- [ ] **Step 1:** `mkdir -p packages/clausal-opencv/clausal/modules/py`

- [ ] **Step 2: Move files**
  ```sh
  for f in _opencv_handles.py opencv.py opencv_calib3d.py opencv_color.py opencv_contours.py opencv_draw.py opencv_features.py opencv_imgproc.py opencv_objdetect.py opencv_video.py; do
      git mv "packages/clausal-opencv/clausal/modules/$f" "packages/clausal-opencv/clausal/modules/py/$f"
  done
  ```

- [ ] **Step 3: Add alias entries**

  Add to `_IMPORT_ALIASES` in `clausal/templating/term_rewriting.py`:
  ```python
  "opencv": "py.opencv",
  "opencv_calib3d": "py.opencv_calib3d",
  "opencv_color": "py.opencv_color",
  "opencv_contours": "py.opencv_contours",
  "opencv_draw": "py.opencv_draw",
  "opencv_features": "py.opencv_features",
  "opencv_imgproc": "py.opencv_imgproc",
  "opencv_objdetect": "py.opencv_objdetect",
  "opencv_video": "py.opencv_video",
  ```
  (Do NOT add `_opencv_handles` — leading underscore means it's a private helper, never imported via `-import_from`.)

  Add identical 9 entries to `_MODULE_ALIASES` in `clausal/logic/compiler_v2.py`.

- [ ] **Step 4: Reinstall**
  ```sh
  pip install -e packages/clausal-opencv --force-reinstall --no-deps
  ```

- [ ] **Step 5: Verify imports**
  ```sh
  python -c "from clausal.modules.py import opencv, opencv_imgproc; print(opencv.__file__, opencv_imgproc.__file__)"
  ```

- [ ] **Step 6: Run tests**
  ```sh
  pytest packages/clausal-opencv/tests -x --timeout=30 2>&1 | tail -10
  ```

- [ ] **Step 7: Commit**
  ```sh
  git add -A
  git commit -m "refactor(clausal-opencv): move wrappers under clausal.modules.py

  Moves 9 opencv wrapper modules plus the _opencv_handles private helper
  from clausal/modules/ to clausal/modules/py/. Adds compile-time alias
  entries in _IMPORT_ALIASES and _MODULE_ALIASES so .clausal files using
  -import_from(opencv, ...) continue to resolve after the runtime
  ModulesFinder fallback is retired in a later commit."
  ```

### Task 1.5: Move clausal-scipy wrappers

**Files:**
- Move: 15 wrapper files (`scipy_cluster.py`, `scipy_constants.py`, `scipy_differentiate.py`, `scipy_fft.py`, `scipy_integrate.py`, `scipy_interpolate.py`, `scipy_linalg.py`, `scipy_ndimage.py`, `scipy_optimize.py`, `scipy_signal.py`, `scipy_sparse.py`, `scipy_spatial.py`, `scipy_special.py`, `scipy_stats.py`) plus 2 private helpers (`_scipy_relations.py`, `_scipy_units.py`) under `py/`.
- Modify: both alias dicts — the scipy entries already exist; change values from `"scipy_X": "scipy_X"` to `"scipy_X": "py.scipy_X"` for all 14 scipy_* entries.

Same step pattern as Task 1.1.

- [ ] **Step 1:** `mkdir -p packages/clausal-scipy/clausal/modules/py`

- [ ] **Step 2:**
  ```sh
  for f in _scipy_relations.py _scipy_units.py scipy_cluster.py scipy_constants.py scipy_differentiate.py scipy_fft.py scipy_integrate.py scipy_interpolate.py scipy_linalg.py scipy_ndimage.py scipy_optimize.py scipy_signal.py scipy_sparse.py scipy_spatial.py scipy_special.py scipy_stats.py; do
      git mv "packages/clausal-scipy/clausal/modules/$f" "packages/clausal-scipy/clausal/modules/py/$f"
  done
  ```

- [ ] **Step 3: Update alias entries**

  In both `_IMPORT_ALIASES` and `_MODULE_ALIASES`, change all 14 `scipy_*` entries from `"scipy_X": "scipy_X"` to `"scipy_X": "py.scipy_X"`.

- [ ] **Step 4: Reinstall**
  ```sh
  pip install -e packages/clausal-scipy --force-reinstall --no-deps
  ```

- [ ] **Step 5: Verify**
  ```sh
  python -c "from clausal.modules.py import scipy_linalg, scipy_stats; print(scipy_linalg.__file__)"
  ```

- [ ] **Step 6: Run tests**
  ```sh
  pytest packages/clausal-scipy/tests -x --timeout=30 2>&1 | tail -10
  ```

- [ ] **Step 7: Commit**
  ```sh
  git add -A
  git commit -m "refactor(clausal-scipy): move wrappers under clausal.modules.py

  Moves 14 scipy_* wrapper modules plus 2 private helper modules
  from clausal/modules/ to clausal/modules/py/. Updates _IMPORT_ALIASES
  and _MODULE_ALIASES."
  ```

### Task 1.6: Move clausal-sklearn wrapper

**Files:**
- Move: `packages/clausal-sklearn/clausal/modules/sklearn.py` → `packages/clausal-sklearn/clausal/modules/py/sklearn.py`
- Modify: both alias dicts — change `"sklearn": "sklearn"` to `"sklearn": "py.sklearn"`.
- Modify: `clausal/import_hook.py` — sklearn is currently in `_PASSTHROUGH`. After the move, `clausal.modules.sklearn` no longer exists, so `ModulesFinder` would return None for it anyway. The PASSTHROUGH entry becomes redundant but harmless. Leave it for now; it'll be removed in Phase 3 when ModulesFinder is simplified.

- [ ] **Step 1:** `mkdir -p packages/clausal-sklearn/clausal/modules/py`

- [ ] **Step 2:**
  ```sh
  git mv packages/clausal-sklearn/clausal/modules/sklearn.py packages/clausal-sklearn/clausal/modules/py/sklearn.py
  ```

- [ ] **Step 3: Update alias entries**

  Change `"sklearn": "sklearn"` to `"sklearn": "py.sklearn"` in both dicts.

- [ ] **Step 4: Reinstall**
  ```sh
  pip install -e packages/clausal-sklearn --force-reinstall --no-deps
  ```

- [ ] **Step 5: Verify**
  ```sh
  python -c "from clausal.modules.py import sklearn as wrapper; print(wrapper.__file__)"
  python -c "import clausal; import sklearn; print('real sklearn:', sklearn.__file__)"
  ```

- [ ] **Step 6: Run tests**
  ```sh
  pytest packages/clausal-sklearn/tests -x --timeout=30 2>&1 | tail -10
  ```

- [ ] **Step 7: Commit**
  ```sh
  git add -A
  git commit -m "refactor(clausal-sklearn): move wrapper under clausal.modules.py"
  ```

### Task 1.7: Move clausal-spacy wrapper

**Files:**
- Move: `packages/clausal-spacy/clausal/modules/spacy.py` → `packages/clausal-spacy/clausal/modules/py/spacy.py`
- Modify: both alias dicts — change `"spacy": "spacy"` to `"spacy": "py.spacy"`.

- [ ] **Step 1:** `mkdir -p packages/clausal-spacy/clausal/modules/py`

- [ ] **Step 2:**
  ```sh
  git mv packages/clausal-spacy/clausal/modules/spacy.py packages/clausal-spacy/clausal/modules/py/spacy.py
  ```

- [ ] **Step 3: Update alias entries** — change `"spacy": "spacy"` to `"spacy": "py.spacy"` in both dicts.

- [ ] **Step 4: Reinstall**
  ```sh
  pip install -e packages/clausal-spacy --force-reinstall --no-deps
  ```

- [ ] **Step 5: Verify**
  ```sh
  python -c "from clausal.modules.py import spacy as wrapper; print(wrapper.__file__)"
  ```

- [ ] **Step 6: Run tests**
  ```sh
  pytest packages/clausal-spacy/tests -x --timeout=30 2>&1 | tail -10
  ```

- [ ] **Step 7: Commit**
  ```sh
  git add -A
  git commit -m "refactor(clausal-spacy): move wrapper under clausal.modules.py"
  ```

### Task 1.8: Move clausal-yaml wrapper

**Files:**
- Move: `packages/clausal-yaml/clausal/modules/yaml.py` → `packages/clausal-yaml/clausal/modules/py/yaml.py`
- Modify: both alias dicts — change `"yaml": "yaml"` to `"yaml": "py.yaml"`.

- [ ] **Step 1:** `mkdir -p packages/clausal-yaml/clausal/modules/py`

- [ ] **Step 2:**
  ```sh
  git mv packages/clausal-yaml/clausal/modules/yaml.py packages/clausal-yaml/clausal/modules/py/yaml.py
  ```

- [ ] **Step 3: Update alias entries** — change `"yaml": "yaml"` to `"yaml": "py.yaml"` in both dicts.

- [ ] **Step 4: Reinstall**
  ```sh
  pip install -e packages/clausal-yaml --force-reinstall --no-deps
  ```

- [ ] **Step 5: Verify**
  ```sh
  python -c "from clausal.modules.py import yaml as wrapper; print(wrapper.__file__)"
  python -c "import clausal; import yaml; print('real yaml:', yaml.__file__)"
  ```

- [ ] **Step 6: Run tests**
  ```sh
  pytest packages/clausal-yaml/tests -x --timeout=30 2>&1 | tail -10
  ```

- [ ] **Step 7: Commit**
  ```sh
  git add -A
  git commit -m "refactor(clausal-yaml): move wrapper under clausal.modules.py"
  ```

### Task 1.9: Run full suite to check for cross-package regressions

**Files:** none

- [ ] **Step 1: Run all extension tests**

  ```sh
  for pkg in packages/clausal-{torch,sympy,jax,opencv,scipy,sklearn,spacy,yaml,provenance,trealla,scryer,gprolog}; do
    echo "=== $pkg ==="
    pytest "$pkg/tests" -x --timeout=30 2>&1 | tail -3
  done
  ```

  Expected: same pass count as baseline for each. If any package regresses, the offending Phase 1 sub-task missed an alias update — fix and amend the relevant commit (or add a follow-up commit).

- [ ] **Step 2: Run core tests**
  ```sh
  pytest tests/ -x --timeout=30 2>&1 | tail -10
  ```
  Expected: same as baseline.

- [ ] **Step 3: No commit needed** — this is a verification gate. If everything passes, proceed to Phase 2.

---

## Phase 2 — Remove core compat shims

These are the 2-line `from clausal.modules.py.X import *` files at the top level of core. They exist for backward compatibility from an older refactor. With Phase 1 done, the architectural rationale ("everything wrapper-shaped lives under `py/`") is complete, and these legacy shims are pure noise.

### Task 2.1: Inventory the shims

**Files:** none (read-only investigation)

- [ ] **Step 1: List candidates**

  ```sh
  for f in clausal/modules/csv_mod.py clausal/modules/files_mod.py clausal/modules/hash_mod.py clausal/modules/hmac_mod.py clausal/modules/http_mod.py clausal/modules/json_mod.py clausal/modules/os_mod.py clausal/modules/pbkdf2_mod.py clausal/modules/process_mod.py clausal/modules/random_mod.py clausal/modules/tcp_mod.py clausal/modules/url_mod.py clausal/modules/uuid_mod.py clausal/modules/date_time.py clausal/modules/regex.py clausal/modules/log.py clausal/modules/sqlite.py clausal/modules/imperial.py clausal/modules/units.py clausal/modules/graphs.py clausal/modules/prolog.py; do
    if [ -f "$f" ]; then
      echo "=== $f ==="
      head -3 "$f"
    fi
  done
  ```

- [ ] **Step 2: Classify**

  For each file, decide:
  - **SHIM (delete in Task 2.2):** body is a single `from clausal.modules.py.X import *` line (or equivalent). The "Backward compatibility" comment may or may not be present.
  - **CANONICAL (keep):** has real code that doesn't just re-export from `py/`. These stay where they are; they're not part of this refactor.

  Record the classification. Example expected result (based on inspection prior to this plan):
  - Shims: `csv_mod.py`, `files_mod.py`, `hash_mod.py`, `hmac_mod.py`, `http_mod.py`, `json_mod.py`, `os_mod.py`, `pbkdf2_mod.py`, `process_mod.py`, `random_mod.py`, `tcp_mod.py`, `url_mod.py`, `uuid_mod.py`, `date_time.py`, `regex.py`, `log.py`.
  - Possibly canonical (verify in Step 2): `sqlite.py`, `imperial.py`, `units.py`, `graphs.py`, `prolog.py`.

### Task 2.2: Add compile-time aliases for stdlib bare names

**Why:** After deleting `regex.py`, `.clausal` files that use `-import_from(regex, ...)` would compile to bare `from regex import ...`. With no `clausal.modules.regex` available, the runtime fallback would fail to find it, and Python would either succeed by finding the `regex` PyPI package (wrong wrapper!) or fail with `ModuleNotFoundError`. We add compile-time aliases so the compiler emits `from clausal.modules.py.re import ...` directly.

**Files:**
- Modify: `clausal/templating/term_rewriting.py` (`_IMPORT_ALIASES`)
- Modify: `clausal/logic/compiler_v2.py` (`_MODULE_ALIASES`)

- [ ] **Step 1: Add stdlib alias entries**

  In both dicts, add (or update) entries for each shim being removed in Task 2.3, mapping the bare name to the canonical `py.<X>` location. Use this list as a starting point and add/skip based on the classification from Task 2.1:

  ```python
  "regex": "py.re",
  "log": "py.logging",
  "date_time": "py.datetime",
  "csv_mod": "py.csv",
  "files_mod": "py.files",
  "hash_mod": "py.hash",
  "hmac_mod": "py.hmac",
  "http_mod": "py.http",
  "json_mod": "py.json",
  "os_mod": "py.os",
  "pbkdf2_mod": "py.pbkdf2",
  "process_mod": "py.process",
  "random_mod": "py.random",
  "tcp_mod": "py.tcp",
  "url_mod": "py.url",
  "uuid_mod": "py.uuid",
  ```

  Note: `_ALIASES["uuid"] = "uuid_mod"` in `clausal/import_hook.py:ModulesFinder._ALIASES` will be removed in Phase 3 since `uuid_mod` no longer exists. For now, also add `"uuid": "py.uuid"` to both compile-time dicts so the runtime fallback isn't needed.

- [ ] **Step 2: Confirm no test fixture uses an alias not in the table**

  ```sh
  grep -rhE "^-import_from\([a-z_]+" --include="*.clausal" tests/ packages/*/tests/ 2>/dev/null | sed 's/^-import_from(\([a-z_]*\).*/\1/' | sort -u
  ```

  Compare the output with the alias keys you have. Any name that appears in `.clausal` source but isn't in `_IMPORT_ALIASES` and doesn't match a real Python package (like `numpy`) needs investigation before proceeding.

### Task 2.3: Delete the shims

**Files:** delete files identified as shims in Task 2.1.

- [ ] **Step 1: Delete identified shims**

  ```sh
  # Use the actual list from Task 2.1 — example assuming the prior-inspection list holds:
  git rm clausal/modules/csv_mod.py
  git rm clausal/modules/files_mod.py
  git rm clausal/modules/hash_mod.py
  git rm clausal/modules/hmac_mod.py
  git rm clausal/modules/http_mod.py
  git rm clausal/modules/json_mod.py
  git rm clausal/modules/os_mod.py
  git rm clausal/modules/pbkdf2_mod.py
  git rm clausal/modules/process_mod.py
  git rm clausal/modules/random_mod.py
  git rm clausal/modules/tcp_mod.py
  git rm clausal/modules/url_mod.py
  git rm clausal/modules/uuid_mod.py
  git rm clausal/modules/date_time.py
  git rm clausal/modules/regex.py
  git rm clausal/modules/log.py
  ```

- [ ] **Step 2: Update the docstring in `clausal/modules/__init__.py`**

  Remove the entire "Legacy aliases (backward compatibility shims — re-export from ``py.*``):" block from the docstring (lines ~30-46 in the file). The legacy aliases no longer exist as files; their bare names are now resolved via compile-time `_IMPORT_ALIASES` directly to `py.*`.

- [ ] **Step 3: Run core tests**

  ```sh
  pytest tests/ -x --timeout=30 2>&1 | tail -20
  ```

  Expected: same pass count as baseline. Watch especially for tests in `tests/fixtures/docs/regex_sig_tests.clausal`, `date_time_sig_tests.clausal`, `builtins_sig_tests.clausal`, `term_expansion_sig_tests.clausal` — these were identified in pre-plan inspection as using legacy bare names.

  If a `.clausal` test fixture fails because a bare name isn't being resolved, Task 2.2 missed an alias entry. Add it, re-run, then proceed.

- [ ] **Step 4: Commit**

  ```sh
  git add -A
  git commit -m "refactor(modules): remove legacy compat shims at clausal/modules/ top level

  Deletes the 2-line backward-compat shims (csv_mod.py, uuid_mod.py,
  regex.py, log.py, date_time.py, etc.) that re-exported from
  clausal/modules/py/. Adds compile-time alias entries in _IMPORT_ALIASES
  and _MODULE_ALIASES so .clausal files using the bare legacy names
  (e.g. -import_from(regex, [Match])) continue to compile correctly,
  directly emitting clausal.modules.py.re references.

  Also strips the now-stale 'Legacy aliases' block from the
  clausal/modules/__init__.py docstring."
  ```

---

## Phase 3 — Simplify ModulesFinder

After Phases 1 and 2, `clausal.modules` no longer has wrapper modules at the bare-name level. The `ModulesFinder` meta-path hook still intercepts every bare import and checks for `clausal.modules.<name>` — but those lookups now all return `None` (the wrappers are at `clausal.modules.py.<name>` instead). The hook becomes mostly dead code. Two viable approaches:

- **(A) Retarget:** Change `_MODULES_PKG = "clausal.modules.py"`. The hook still exists for `.clausal` runtime fallback for unaliased bare names, but now looks them up under `py/`. Side effect: stdlib names like `random` would be intercepted (since `clausal.modules.py.random` exists), breaking user `.py` code that imports `random`.

- **(B) Retire the bare-name redirect entirely:** Strip the bare-name redirect logic from `ModulesFinder.find_spec`. Keep the `py.X` dotted-name redirect (lines 535-557 of import_hook.py) since that handles pytest's `py` shim collision, which is a separate concern. Rely on `_IMPORT_ALIASES` being comprehensive at compile time.

This plan picks **(B)** because it's safer (no chance of intercepting user-level stdlib imports) and matches the project's documented direction ("compile-time alias approach resolves these at compile time"). The cost is that any `.clausal` file that uses `-import_from(<unaliased_bare_name>, ...)` will fail to compile unless an entry is added to `_IMPORT_ALIASES` first — a one-line change per new module, made explicit at the point of definition.

### Task 3.1: Strip the bare-name redirect from ModulesFinder

**Files:**
- Modify: `clausal/import_hook.py` — `ModulesFinder.find_spec` method (around lines 528-584)

- [ ] **Step 1: Read the existing class**

  Run: `sed -n '497,590p' clausal/import_hook.py`

  Note the structure: there are two redirect blocks in `find_spec`:
  1. `py.X` dotted-name redirect (lines ~535-557) — KEEP, handles pytest collision.
  2. Bare-name redirect (lines ~558-584) — REMOVE.

  Also note `_ALIASES` (around line 511, `{"uuid": "uuid_mod"}`) — REMOVE since `uuid_mod` is gone after Phase 2.

  Also note `_PASSTHROUGH` (around line 520, `frozenset({"sklearn"})`) — REMOVE the `sklearn` entry; after Phase 1.6, `clausal.modules.sklearn` no longer exists, so the explicit passthrough is no longer needed.

- [ ] **Step 2: Apply the edits**

  In `clausal/import_hook.py`:

  - Delete the `_ALIASES` class attribute on `ModulesFinder` (replace with `_ALIASES: dict[str, str] = {}` if other code references it, or remove entirely if not). Run `grep -rn "_ALIASES" clausal/` to check usage; if no other reference, delete the attribute.
  - Empty the `_PASSTHROUGH` frozenset: `_PASSTHROUGH: frozenset[str] = frozenset()`.
  - In `find_spec`, after the `py.X` dotted-name block (the one ending around line 557 with `return new_spec`), the body should `return None`. Delete everything from `# Only redirect top-level names...` through the end of `find_spec` (the bare-name redirect block, ~558-584). Keep only the `py.X` dotted block; if `fullname` doesn't match it, return `None`.

- [ ] **Step 3: Verify no other code in clausal references `ModulesFinder._ALIASES` or `_PASSTHROUGH`**

  ```sh
  grep -rn "_ALIASES\b\|_PASSTHROUGH\b" clausal/ packages/*/clausal/ --include="*.py" 2>&1 | grep -v test
  ```

  Expected: at most the definitions and any imports that we'll be fixing. Investigate hits.

- [ ] **Step 4: Verify `_import_stdlib` in `clausal/modules/py/__init__.py` still works**

  `_import_stdlib` references `ModulesFinder._resolving`. That attribute still exists (it's not part of the changes). Just confirm:

  ```sh
  grep -n "_resolving" clausal/import_hook.py
  ```

  Expected: `_resolving` is still defined as a class attribute and still used in the `py.X` block.

- [ ] **Step 5: Run full test suite**

  ```sh
  pytest tests/ -x --timeout=30 2>&1 | tail -20
  for pkg in packages/clausal-{torch,sympy,jax,opencv,scipy,sklearn,spacy,yaml,provenance,trealla,scryer,gprolog}; do
    echo "=== $pkg ==="
    pytest "$pkg/tests" -x --timeout=30 2>&1 | tail -3
  done
  ```

  Expected: same pass count everywhere as baseline.

  If any `.clausal` test fails with `ModuleNotFoundError`, it's using a bare name not in `_IMPORT_ALIASES`. Add the alias, re-run.

- [ ] **Step 6: Commit**

  ```sh
  git add -A
  git commit -m "refactor(import_hook): retire ModulesFinder bare-name redirect

  After moving all wrapper modules under clausal.modules.py.* and making
  _IMPORT_ALIASES / _MODULE_ALIASES comprehensive at compile time, the
  runtime ModulesFinder no longer needs to intercept bare imports. This
  removes the bare-name redirect block and the now-empty _ALIASES /
  _PASSTHROUGH escape hatches. The 'py.X' dotted redirect (which handles
  the pytest 'py' shim collision) is retained.

  User .py code can now \`import torch\`, \`import sympy\`, etc., and
  reach the real PyPI packages with no surprise interception."
  ```

### Task 3.2: Update the `clausal/modules/__init__.py` docstring to reflect new architecture

**Files:**
- Modify: `clausal/modules/__init__.py` (docstring only)

- [ ] **Step 1: Rewrite the opening paragraph**

  Replace the current "This package acts as the top-level search path..." paragraph and the entire "Canonical modules" / "Legacy aliases" lists with a concise statement of the new architecture. Example replacement:

  ```python
  """clausal.modules — Python library wrappers for Clausal.

  Wrappers for Python stdlib and third-party packages all live in the
  ``py`` subpackage (``clausal.modules.py.<name>``). For example::

      -import_from(py.uuid, [UUIDv4, UUIDStr])
      -import_from(py.torch, [tensor, zeros, randn])
      -import_from(py.sympy, [Simplify, Solve])

  ``.clausal`` files may also use the bare names (``-import_from(torch, ...)``,
  ``-import_from(sympy, ...)``); the compiler rewrites these to the
  canonical ``py.<name>`` paths via ``_IMPORT_ALIASES`` in
  ``clausal/templating/term_rewriting.py``.

  Extension distributions (clausal-torch, clausal-sympy, clausal-jax,
  clausal-opencv, clausal-scipy, clausal-sklearn, clausal-spacy,
  clausal-yaml) install their wrappers into ``clausal/modules/py/`` via
  PEP 420 namespace-package contributions; this package's ``__path__``
  is extended below to discover them.
  """
  ```

  Keep the `__path__` extension code unchanged.

- [ ] **Step 2: Update `clausal/modules/py/__init__.py` docstring similarly**

  Remove the bullet list of "legacy names" — there are no legacy names anymore.

- [ ] **Step 3: Run a quick sanity check**

  ```sh
  python -c "import clausal.modules; help(clausal.modules)" 2>&1 | head -30
  ```

  Expected: prints the rewritten docstring.

- [ ] **Step 4: Commit**

  ```sh
  git add clausal/modules/__init__.py clausal/modules/py/__init__.py
  git commit -m "docs(modules): rewrite package docstrings to reflect canonical py/ layout"
  ```

---

## Phase 4 — End-to-end verification

### Task 4.1: Reproduce the original OCR-sudoku bug repro and confirm it's fixed

**Files:** none (verification only)

- [ ] **Step 1: From a clean Python invocation, run the minimal repro**

  ```sh
  python -c "import clausal; import torch; print('torch:', torch.__file__); import torch.nn as nn; print('nn:', nn.__file__)"
  ```

  Expected (success):
  ```
  torch: /.../site-packages/torch/__init__.py
  nn: /.../site-packages/torch/nn/__init__.py
  ```

  No `RecursionError`. Both modules resolve to the real torch package, not to anything in `clausal/modules/`.

- [ ] **Step 2: Verify sympy, jax, yaml are also fine**

  ```sh
  python -c "import clausal; import sympy; print('sympy:', sympy.__file__)"
  python -c "import clausal; import jax; print('jax:', jax.__file__)"
  python -c "import clausal; import yaml; print('yaml:', yaml.__file__)"
  ```

  Expected: all three print real site-packages paths.

- [ ] **Step 3: Verify the wrappers themselves are still reachable via qualified path**

  ```sh
  python -c "from clausal.modules.py import torch as wt; print('torch wrapper:', wt.__file__)"
  python -c "from clausal.modules.py import sympy as ws; print('sympy wrapper:', ws.__file__)"
  ```

  Expected: paths under `packages/clausal-torch/clausal/modules/py/torch.py` and similar.

- [ ] **Step 4: Run the example suite**

  ```sh
  pytest tests/ packages/*/tests -x --timeout=60 2>&1 | tail -30
  ```

  Expected: same pass count as the Phase 0 baseline. Differences here vs. baseline indicate a regression and must be tracked down before declaring victory.

### Task 4.2: Smoke-test the original OCR-sudoku notebook path

**This task is OPTIONAL** — it requires the `clausal-sudoku-ocr` package, which is NOT on this branch. Skip if it's not available in the container. If you have access to a working tree where it IS present, do this verification:

- [ ] **Step 1: Install the sudoku-ocr package**

  ```sh
  pip install opencv-python-headless
  pip install -e packages/clausal-sudoku-ocr
  ```

- [ ] **Step 2: Import the modules that originally crashed**

  ```sh
  python -c "from clausal.examples.sudoku_ocr import classifier, vision, fixtures, symbolic; print('all imports OK')"
  ```

  Expected: `all imports OK`, no recursion error.

- [ ] **Step 3: No commit needed** — this is verification.

### Task 4.3: Final summary commit (optional)

If any docstrings, comments, or README sections still reference the old layout, sweep them up here.

- [ ] **Step 1: Grep for outdated references**

  ```sh
  grep -rln "clausal\.modules\.\(torch\|sympy\|jax\|yaml\|opencv\|sklearn\|spacy\|scipy_\)" docs/ README.md packages/*/README.md 2>/dev/null
  ```

  Expected: ideally no hits. If hits exist, update them to use `clausal.modules.py.X`.

- [ ] **Step 2: Commit any cleanup**

  ```sh
  git add -A
  git commit -m "docs: update references to canonical clausal.modules.py.* paths"
  ```

  If there's nothing to commit, skip.

---

## Appendix A — Quick-reference alias update table

For every entry in `_IMPORT_ALIASES` (`clausal/templating/term_rewriting.py:1255`) and `_MODULE_ALIASES` (`clausal/logic/compiler_v2.py:196`):

| Bare name | Old value | New value | Phase |
|---|---|---|---|
| `uuid` | `"uuid_mod"` | `"py.uuid"` | 2 |
| `yaml` | `"yaml"` | `"py.yaml"` | 1.8 |
| `spacy` | `"spacy"` | `"py.spacy"` | 1.7 |
| `sympy` | `"sympy"` | `"py.sympy"` | 1.2 |
| `sklearn` | `"sklearn"` | `"py.sklearn"` | 1.6 |
| `torch` | `"torch"` | `"py.torch"` | 1.1 |
| `torch_nn` | `"torch_nn"` | `"py.torch_nn"` | 1.1 |
| `torch_data` | `"torch_data"` | `"py.torch_data"` | 1.1 |
| `torch_functional` | `"torch_functional"` | `"py.torch_functional"` | 1.1 |
| `torch_distributions` | `"torch_distributions"` | `"py.torch_distributions"` | 1.1 |
| `jax` | `"jax"` | `"py.jax"` | 1.3 |
| `jax_random` | `"jax_random"` | `"py.jax_random"` | 1.3 |
| `jax_nn` | `"jax_nn"` | `"py.jax_nn"` | 1.3 |
| `jax_transforms` | `"jax_transforms"` | `"py.jax_transforms"` | 1.3 |
| `jax_scipy` | `"jax_scipy"` | `"py.jax_scipy"` | 1.3 |
| `jax_sharding` | `"jax_sharding"` | `"py.jax_sharding"` | 1.3 |
| `jax_tree` | `"jax_tree"` | `"py.jax_tree"` | 1.3 |
| `jax_optax` | `"jax_optax"` | `"py.jax_optax"` | 1.3 |
| `jax_equinox` | `"jax_equinox"` | `"py.jax_equinox"` | 1.3 |
| `jax_flax` | `"jax_flax"` | `"py.jax_flax"` | 1.3 |
| `scipy_cluster` through `scipy_stats` (14 names) | `"scipy_X"` | `"py.scipy_X"` | 1.5 |

**New entries added in Phase 1.4 (opencv was not previously aliased):**

| Bare name | New value |
|---|---|
| `opencv` | `"py.opencv"` |
| `opencv_calib3d` | `"py.opencv_calib3d"` |
| `opencv_color` | `"py.opencv_color"` |
| `opencv_contours` | `"py.opencv_contours"` |
| `opencv_draw` | `"py.opencv_draw"` |
| `opencv_features` | `"py.opencv_features"` |
| `opencv_imgproc` | `"py.opencv_imgproc"` |
| `opencv_objdetect` | `"py.opencv_objdetect"` |
| `opencv_video` | `"py.opencv_video"` |

**New entries added in Phase 2.2 (legacy stdlib bare names):**

| Bare name | New value |
|---|---|
| `regex` | `"py.re"` |
| `log` | `"py.logging"` |
| `date_time` | `"py.datetime"` |
| `csv_mod` | `"py.csv"` |
| `files_mod` | `"py.files"` |
| `hash_mod` | `"py.hash"` |
| `hmac_mod` | `"py.hmac"` |
| `http_mod` | `"py.http"` |
| `json_mod` | `"py.json"` |
| `os_mod` | `"py.os"` |
| `pbkdf2_mod` | `"py.pbkdf2"` |
| `process_mod` | `"py.process"` |
| `random_mod` | `"py.random"` |
| `tcp_mod` | `"py.tcp"` |
| `url_mod` | `"py.url"` |
| `uuid_mod` | `"py.uuid"` |

---

## Appendix B — Things to watch out for

- **Editable install staleness.** After `git mv`, pip's editable install may still resolve the old path until you re-run `pip install -e <pkg> --force-reinstall --no-deps`. If imports look wrong after a move, reinstall before debugging.
- **`__pycache__` directories.** Stale `.pyc` files at the old locations can occasionally confuse imports. If something is mysteriously not picking up the new layout, `find . -name __pycache__ -type d -exec rm -rf {} +` (or git-clean) and re-run.
- **`.egg-info` directories.** `pip install -e` writes a `<pkg>.egg-info/` next to the source tree. After moves, the SOURCES.txt inside may reference old paths; this is cosmetic but can be regenerated by reinstalling.
- **`.clausal` import resolution.** A `.clausal` file that does `-import_from(foo, [Bar])` compiles to bytecode that imports `clausal.modules.py.foo` ONLY if `foo` is in `_IMPORT_ALIASES`. If you add a new wrapper, add the alias entry in the same commit.
- **`provenance/` is a real subpackage.** Don't try to move `clausal-provenance` modules under `py/`. The `provenance` namespace contains a multi-level hierarchy (semirings, bridges, builtins) — leaving it alone is correct.
- **Don't skip the reinstall step in Phase 1.** Each Phase 1 sub-task ends with `pip install -e ... --force-reinstall --no-deps` for a reason. Without this, the very next step's imports may resolve against the old layout and confuse you.

---

## Self-review checklist (perform before claiming the plan is ready)

- [x] Every spec requirement (bug class fixed, top-level wrappers moved, compat shims removed, ModulesFinder simplified, docs updated) has a corresponding task.
- [x] No "TBD", "TODO", or "add appropriate error handling" placeholders.
- [x] Every file move is paired with an alias-table update in the same commit.
- [x] Every task has an explicit verification step before its commit step.
- [x] Method/attribute names (`_IMPORT_ALIASES`, `_MODULE_ALIASES`, `_ALIASES`, `_PASSTHROUGH`, `_resolving`, `_MODULES_PKG`) are consistent across all tasks that reference them.
- [x] Branch creation comes first; commits chunk along package boundaries; verification is per-package then global.
- [x] Phase 4 verifies the original blocker (the torch.nn recursion) is fixed.
