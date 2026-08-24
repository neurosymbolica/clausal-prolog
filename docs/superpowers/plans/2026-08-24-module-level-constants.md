# Module-Level Constants + Singleton Lint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Declared, compile-time-ground module constants spelled `_PI_` (one leading + one trailing underscore), plus a default-on singleton-variable lint with `_UNUSED`-suffix exemption.

**Architecture:** A new lexical class (`_X_`) is carved out of the logic-variable namespace across all five duplicated `_is_logic_var_name` copies. Constants are declared in a `-constants(...)` directive that lowers to module-level assignments guarded by a groundness check, so references are plain `Name` loads whose values are embedded into clause terms at module-exec time (observationally "folded": indexing sees the value, no `Var` is ever involved). The singleton lint counts per-clause variable occurrences in the per-clause `TermTransformer` and warns at clause build.

**Tech Stack:** Pure in-repo Python; `clausal/templating/term_rewriting.py` is the center of gravity. Tests are pytest.

**Spec:** `implementation_plans/module-level-constants.md` (decisions record: `todo/done/module-level-constants-open-questions.md`)

## Global Constraints

- Run tests with `/workspace/clausal/venv/bin/python -m pytest ...` **from the repo root** (`/workspace/clausal-bug-fix` or the worktree copy) — cwd wins over install. Chunk large runs; do not run the whole suite in one process.
- The clone is shared: **never `git add -A`**; stage explicit paths only.
- Suite verification is by **diffing failure sets**, not counts (the clone has ~1 known pre-existing failure).
- Commit messages must not reference private downstream consumers of this repo.
- Work on branch `feat/constants-and-singleton-lint` (create from `main`; use a worktree via superpowers:using-git-worktrees).
- Constant-shape rule (used everywhere; copy verbatim): length ≥ 3, `id[0] == "_"`, `id[-1] == "_"`, `id[1] != "_"`, `id[-2] != "_"`, and `not id[1].isdigit()`.
- Match surrounding comment density and the `transformer`-as-self convention in `term_rewriting.py`.

---

### Task 1: Rename compiler-minted trailing-underscore variable names

The DCG rewriter mints `_dcg{N}_` (`term_rewriting.py:2370`, `:2410`, and the `head(_dcg0_, _dcg1_)` head args near the `>>` rule handling) and the EDCG expander mints `_edcg_{acc}_in{suffix}_` / `_edcg_{acc}_out{suffix}_` / `_edcg_{pass}_` (`term_rewriting.py:2500-2507`). All are constant-shaped under the new rule and must lose the trailing underscore BEFORE the classifier changes, or every DCG/EDCG rule breaks.

**Files:**
- Modify: `clausal/templating/term_rewriting.py:2370,2410,2500-2507` (and the DCG head-arg mint site — grep `_dcg0_`)
- Modify: `tests/fixtures/edcg_counter.clausal` (hand-written `_edcg_*_` names mirror the minted convention)
- Modify: `tests/test_lint_cons_bar_head.py` (references `_dcg` spellings — grep before editing)
- Test: existing `tests/test_dcg.py` and the EDCG tests (grep `edcg` under `tests/`)

**Interfaces:**
- Consumes: nothing.
- Produces: minted hidden-variable names `_dcg{N}`, `_edcg_{acc}_in{suffix}`, `_edcg_{acc}_out{suffix}`, `_edcg_{pass}` — no trailing underscore. Task 2's classifier change relies on no compiler-minted name being constant-shaped.

- [ ] **Step 1: Locate every trailing-underscore mint and reference**

Run: `grep -n '_dcg[0-9{]\|_edcg_' clausal/templating/term_rewriting.py tests/test_lint_cons_bar_head.py; grep -rn '_edcg_\|_dcg0_' tests/fixtures/ docs/`
Record the full list; every hit gets edited in this task.

- [ ] **Step 2: Drop the trailing underscore at the mint sites**

```python
# term_rewriting.py:2502 (and :2507, and the _dcg mints)
    return f"_edcg_{acc_name}_in{suffix}", f"_edcg_{acc_name}_out{suffix}"
...
    return f"_edcg_{pass_name}"
...
            mid = f"_dcg{counter}"
...
            fresh = f"_dcg{counter}"
```
Update `tests/fixtures/edcg_counter.clausal` identically (the fixture interoperates with the minted names — they must stay in sync) and any doc mention found in Step 1.

- [ ] **Step 3: Run the DCG/EDCG/lint tests**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_dcg.py tests/test_lint_cons_bar_head.py $(grep -rl edcg tests --include='test_*.py' | tr '\n' ' ') -q`
Expected: same failure set as before the edit (baseline it first on the unmodified tree).

- [ ] **Step 4: Commit**

```bash
git add clausal/templating/term_rewriting.py tests/fixtures/edcg_counter.clausal tests/test_lint_cons_bar_head.py
git commit -m "dcg/edcg: drop trailing underscore from minted hidden-variable names

Prepares the _X_ lexical class for constants (see
implementation_plans/module-level-constants.md): no compiler-minted
name may be constant-shaped."
```

---

### Task 2: The lexical re-carve — `_is_constant_name` + exclusion in all five classifier copies

**Files:**
- Modify: `clausal/templating/term_rewriting.py:417` (`_is_logic_var_name`; add `_is_constant_name` above it)
- Modify: `clausal/templating/desugar.py:57`
- Modify: `clausal/logic/goal_expansion.py:203`
- Modify: `clausal/tools/clausal_to_prolog.py:311`
- Modify: `clausal/logic/predicate.py:60-67`
- Modify: `tests/fixtures/callsite_joint_lib.clausal`, `tests/fixtures/secondary_dispatch_tro.clausal` (`_JOINT_COVERAGE_` → `_JOINT_COVERAGE`)
- Create: `tests/test_var_classifier_conformance.py`

**Interfaces:**
- Consumes: Task 1 (no minted constant-shaped names remain).
- Produces: `_is_constant_name(identifier: str) -> bool` in `term_rewriting` (public within the module; Tasks 4-7 call it). `_is_logic_var_name` returns `False` for constant-shaped names in all five copies.

- [ ] **Step 1: Write the conformance test (fails on the unmodified tree)**

```python
"""All five _is_logic_var_name copies must agree — and none may claim _X_.

The classifier is deliberately duplicated (predicate.py stays free of
templating imports; desugar stays free of engine imports). This test is the
lockstep guard: a corpus of spellings must classify identically everywhere,
and constant-shaped names (_PI_) must be variables NOWHERE.

Known, deliberate divergences pinned at the bottom: clausal_to_prolog treats
bare `_` as a variable; desugar does not exclude dunders or `_`.
"""
import pytest

from clausal.templating.term_rewriting import (
    _is_logic_var_name as tr_var, _is_constant_name)
from clausal.templating.desugar import _is_logic_var_name as ds_var
from clausal.logic.goal_expansion import _is_logic_var_name as ge_var
from clausal.logic.predicate import _is_logic_var_name as pr_var
from clausal.tools.clausal_to_prolog import _is_logic_var_name as cp_var

ALL = [tr_var, ds_var, ge_var, pr_var, cp_var]

# (spelling, is_variable) — spellings where all five copies must agree.
CORPUS = [
    ("X", True), ("FOO", True), ("MAX_OF", True), ("N1", True),
    ("_x", True), ("_head", True), ("_名前", True),
    ("PI_", True), ("FOO_", True),          # trailing-only: still a variable
    ("foo", False), ("Foo", False), ("in_", False), ("名前", False),
    # The new constant class: variables NOWHERE.
    ("_PI_", False), ("_pi_", False), ("_MAX_RETRIES_", False),
    ("_a_b_", False), ("_円周率_", False),
]

@pytest.mark.parametrize("spelling,expected", CORPUS)
def test_all_copies_agree(spelling, expected):
    got = [(fn.__module__, fn(spelling)) for fn in ALL]
    assert all(v == expected for _, v in got), got

CONSTANT_SHAPE = [
    ("_PI_", True), ("_a_b_", True), ("_円周率_", True),
    ("_", False), ("__", False), ("___", False),
    ("_X__", False), ("__X_", False),        # exactly one underscore each end
    ("_1_", False),                          # interior must not start with a digit
    ("PI_", False), ("_PI", False), ("PI", False),
]

@pytest.mark.parametrize("spelling,expected", CONSTANT_SHAPE)
def test_constant_shape(spelling, expected):
    assert _is_constant_name(spelling) == expected

def test_pinned_divergences():
    # clausal_to_prolog: bare `_` is a variable there (translation context).
    assert cp_var("_") is True and tr_var("_") is False
    # desugar: no dunder exclusion (sugar-recognition context).
    assert ds_var("__x") is True and tr_var("__x") is False

def test_corpus_has_no_constant_shaped_variables():
    """Census guard: no .clausal file may use a _X_-shaped name until the
    constants feature gives it meaning (and after that, only declared ones)."""
    import pathlib, re
    root = pathlib.Path(__file__).resolve().parent.parent
    pat = re.compile(r"(?<![A-Za-z0-9_])_[^\W\d_][\w]*?[^\W_]_(?![A-Za-z0-9_])")
    offenders = []
    for p in root.rglob("*.clausal"):
        if ".claude" in p.parts:
            continue
        for m in pat.finditer(p.read_text()):
            offenders.append((str(p), m.group(0)))
    assert offenders == [], offenders
```

- [ ] **Step 2: Run it to verify it fails**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_var_classifier_conformance.py -q`
Expected: FAIL — `_is_constant_name` unimportable, `_PI_` classified as a variable, census guard hits the two `_JOINT_COVERAGE_` fixtures.

- [ ] **Step 3: Implement `_is_constant_name` and the exclusion**

In `term_rewriting.py`, above `_is_logic_var_name`:

```python
def _is_constant_name(identifier: str) -> bool:
    """True for the module-constant lexical class: exactly one leading and
    one trailing underscore with a non-digit-initial interior (``_PI_``,
    ``_MAX_RETRIES_``, ``_円周率_``).

    Carved OUT of the logic-variable namespace — every ``_is_logic_var_name``
    copy excludes this shape (pinned by test_var_classifier_conformance).
    ``_1_`` is rejected: a constant named ``1`` invites confusion with the
    literal. See implementation_plans/module-level-constants.md.
    """
    return (
        len(identifier) >= 3
        and identifier[0] == "_" and identifier[-1] == "_"
        and identifier[1] != "_" and identifier[-2] != "_"
        and not identifier[1].isdigit()
    )
```

In `_is_logic_var_name` (term_rewriting copy), after the `startswith("__")` check:

```python
    if _is_constant_name(identifier):
        return False
```

Mirror both into the other four copies **preserving each copy's local quirks** (clausal_to_prolog keeps `_` → True; desugar keeps its shorter form — add the constant exclusion as the first check there since it has no dunder branch). Each mirror keeps its existing "kept local, no import" docstring sentence and gains one line noting the conformance test.

- [ ] **Step 4: Rename the two fixture variables**

`_JOINT_COVERAGE_` → `_JOINT_COVERAGE` in `tests/fixtures/callsite_joint_lib.clausal` and `tests/fixtures/secondary_dispatch_tro.clausal` (every occurrence; it stays a variable — leading underscore).

- [ ] **Step 5: Run conformance + neighbors**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_var_classifier_conformance.py tests/test_var_shaped_predicate_name.py tests/test_dcg.py -q` then the fixture consumers: `grep -rl 'callsite_joint_lib\|secondary_dispatch_tro' tests --include='test_*.py'` and run those files.
Expected: PASS (modulo the pre-existing baseline failure set).

- [ ] **Step 6: Commit**

```bash
git add clausal/templating/term_rewriting.py clausal/templating/desugar.py clausal/logic/goal_expansion.py clausal/tools/clausal_to_prolog.py clausal/logic/predicate.py tests/test_var_classifier_conformance.py tests/fixtures/callsite_joint_lib.clausal tests/fixtures/secondary_dispatch_tro.clausal
git commit -m "lexical: carve the _X_ constant class out of the variable namespace

All five _is_logic_var_name copies exclude one-underscore-each-end
spellings, locked by a conformance test plus a corpus census guard."
```

---

### Task 3: Singleton lint — `ClausalSingletonWarning`, `_UNUSED` exemption, inverse lint, `-allow_singletons`

**Files:**
- Modify: `clausal/templating/term_rewriting.py` — `TermTransformer.__init__` (:961-984), `visit_Name` (:1441), lambda sub-transformer (:1356), `_build_py_thunk_ast` (:892), `_build_fact_statements` (:3367), the arrow-clause build (~:3793), `EmbedTransformer.__init__` (:3001), `_handle_directive` (:3890)
- Test: `tests/test_singleton_lint.py` (create)

**Interfaces:**
- Consumes: Task 2 (`_X_` names never reach the variable path, so the lint never fires on constants).
- Produces: `ClausalSingletonWarning(UserWarning)` in `term_rewriting` (import target for tests); `TermTransformer.var_occurrences: Counter`; `EmbedTransformer._warn_singletons(term_transformer, expr_stmt)`; directive `-allow_singletons` setting `EmbedTransformer._allow_singletons = True`.

- [ ] **Step 1: Write the failing tests**

```python
"""Singleton lint: a named variable occurring once per clause warns.

Exemptions: bare `_`; names suffixed `_UNUSED` (sole canonical spelling —
`_unused` is NOT exempt); files carrying -allow_singletons. Inverse lint: a
_UNUSED-suffixed name occurring MORE than once warns the other way.
"""
import warnings
import textwrap
import pytest

from clausal.import_hook import _load_module
from clausal.templating.term_rewriting import ClausalSingletonWarning


def _load(tmp_path, name, text):
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(text).lstrip())
    return _load_module(f"tsl_{name}", str(path))


def _singleton_warnings(recorder):
    return [w for w in recorder if issubclass(w.category, ClausalSingletonWarning)]


def test_singleton_warns_all_caps(tmp_path):
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        _load(tmp_path, "a", "p(X, Y) <- (X == 1)\n")
    msgs = [str(w.message) for w in _singleton_warnings(rec)]
    assert any("Y" in m and "singleton" in m.lower() for m in msgs)


def test_singleton_warns_underscore_style(tmp_path):
    """_x is a first-class variable style, so it is linted too (unlike
    Prolog's _X convention — see the spec's Triska-gotcha rationale)."""
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        _load(tmp_path, "b", "p(_x, _y) <- (_x == 1)\n")
    msgs = [str(w.message) for w in _singleton_warnings(rec)]
    assert any("_y" in m for m in msgs)


def test_unused_suffix_exempts(tmp_path):
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        _load(tmp_path, "c", "p(X, Y_UNUSED) <- (X == 1)\n")
    assert _singleton_warnings(rec) == []


def test_lowercase_unused_is_not_exempt(tmp_path):
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        _load(tmp_path, "d", "p(X, _y_unused) <- (X == 1)\n")
    assert len(_singleton_warnings(rec)) == 1


def test_join_variable_does_not_warn(tmp_path):
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        _load(tmp_path, "e", "p(X) <- (q(X, N), r(N))\n"
                             "q(A, B) <- (B == A)\n"
                             "r(_n) <- (_n == 1)\n")
    assert _singleton_warnings(rec) == []


def test_inverse_lint_marked_unused_but_used(tmp_path):
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        _load(tmp_path, "f", "p(X_UNUSED) <- (X_UNUSED == 1)\n")
    msgs = [str(w.message) for w in _singleton_warnings(rec)]
    assert any("more than once" in m for m in msgs)


def test_allow_singletons_directive_silences(tmp_path):
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        _load(tmp_path, "g", "-allow_singletons\n"
                             "p(X, Y) <- (X == 1)\n")
    assert _singleton_warnings(rec) == []


def test_fstring_use_counts_as_occurrence(tmp_path):
    """Variables reaching a PyThunk (f-string / ++) are occurrences."""
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        _load(tmp_path, "h", 'show(X) <- ++print(X)\n')
    assert _singleton_warnings(rec) == []
```

Note: `-allow_singletons` is written bare (no parens). Check how `-implicit_atoms` arrives at `_handle_directive` — if bare directives come through a different path (a bare `-name` is `USub(Name)`, not `USub(Call)`), mirror `-implicit_atoms`' spelling exactly, parens and all, in both the test and Step 3.

- [ ] **Step 2: Run to verify failure**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_singleton_lint.py -q`
Expected: FAIL — `ClausalSingletonWarning` unimportable.

- [ ] **Step 3: Implement**

(a) Warning class next to `ClausalLintWarning` (:783):

```python
class ClausalSingletonWarning(ClausalLintWarning):
    """A named logic variable occurring exactly once in its clause.

    Suppress per-variable with the ``_UNUSED`` suffix, per-file with
    ``-allow_singletons``. The suffix is the sole canonical spelling —
    case-based exemptions are blind for caseless scripts, which the
    ``isupper()`` rule forces into leading-underscore variables.
    """
```

(b) `TermTransformer.__init__`: add `transformer.var_occurrences = Counter()` (import `Counter` at module top). In `visit_Name`, first line of the `_is_logic_var_name(identifier)` branch: `transformer.var_occurrences[identifier] += 1`.

(c) Lambda sub-transformer (:1356 area): after `lambda_transformer.seen_vars = transformer.seen_vars.copy()`, add `lambda_transformer.var_occurrences = transformer.var_occurrences` (shared object — occurrences inside lambdas count toward the clause).

(d) `_build_py_thunk_ast` (:892): for each logic-var name it collects into the thunk's parameter list, bump `transformer.var_occurrences[name] += 1` once (an f-string/`++` use is an occurrence; exact multiplicity within one thunk is not needed).

(e) `EmbedTransformer.__init__`: `transformer._allow_singletons = False`. New method:

```python
    def _warn_singletons(transformer, term_transformer, expr_stmt):
        """Clause-end singleton check (see ClausalSingletonWarning)."""
        if transformer._allow_singletons:
            return
        import warnings  # noqa: PLC0415
        lineno = getattr(expr_stmt, "lineno", None)
        where = transformer._site(lineno) if lineno else "unknown site"
        for ident, count in term_transformer.var_occurrences.items():
            if ident.endswith("_UNUSED"):
                if count > 1:
                    warnings.warn(
                        f"{where}: variable `{ident}` is marked _UNUSED but "
                        f"occurs more than once in its clause",
                        ClausalSingletonWarning, stacklevel=2)
            elif count == 1:
                warnings.warn(
                    f"{where}: singleton variable `{ident}` — a variable "
                    f"occurring once binds nothing. Misspelling? Rename to "
                    f"`{ident}_UNUSED` (or `_`) if deliberate, or add "
                    f"-allow_singletons to the file",
                    ClausalSingletonWarning, stacklevel=2)
```

Call it at the end of `_build_fact_statements` and at the end of the arrow-clause build block (~:3830, after `define_stmt` is assembled), passing the clause's `term_transformer`. The `with --{}` block form (:4894) is a term-list builder, not a clause — no call there.

(f) `-allow_singletons` in `_handle_directive`, mirroring `-implicit_atoms`' plumbing (:4112): set the flag, return `replace(Pass(), expr_stmt)`, and add it to the known-directives list in the unknown-directive error message.

- [ ] **Step 4: Run the new tests, then the transformer neighborhood**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_singleton_lint.py tests/test_term_rewriting.py tests/test_dcg.py tests/test_lambdas.py -q`
Expected: new tests PASS; neighborhood failure set unchanged. DCG/EDCG note: minted `_dcg{N}`/`_edcg_*` hidden variables thread through head and body, so they occur ≥2 times and must not warn — if a DCG test warns, the mint is being counted once somewhere; fix the count, not the test.

- [ ] **Step 5: Commit**

```bash
git add clausal/templating/term_rewriting.py tests/test_singleton_lint.py
git commit -m "lint: singleton variables warn by default; _UNUSED suffix exempts

Per-clause occurrence counting in TermTransformer; inverse lint for
_UNUSED names used more than once; -allow_singletons opts a file out."
```

---

### Task 4: Corpus singleton cleanup

439 singleton occurrences across 102 files light up after Task 3. Rename each singleton occurrence `NAME` → `NAME_UNUSED` **per-occurrence** (never file-global — the same spelling may be a real join variable in a neighboring clause).

**Files:**
- Create: `scripts/rename_singletons.py` (committed — it documents how the sweep was made)
- Modify: ~102 `.clausal` files under `tests/`, `packages/`, `repro-arg1-scratch/`, `clausal/stdlib/`

**Interfaces:**
- Consumes: Task 3 (the lint defines what counts).
- Produces: a corpus that loads warning-free.

- [ ] **Step 1: Write the sweep script**

```python
"""Rename per-clause singleton variable occurrences to NAME_UNUSED.

.clausal files are Python-parseable; each top-level statement is one clause.
Edits are applied per exact (lineno, col_offset) occurrence, bottom-up so
earlier spans stay valid. Directives (-name(...) => USub statements) are
skipped. Names already suffixed _UNUSED, bare `_`, and non-variable names
are left alone.
"""
import ast, pathlib, sys
from collections import Counter


def is_var(name):
    if name == "_" or name.startswith("__"):
        return False
    if (len(name) >= 3 and name[0] == "_" and name[-1] == "_"
            and name[1] != "_" and name[-2] != "_" and not name[1].isdigit()):
        return False  # constant-shaped: not a variable
    return name.startswith("_") or name.isupper()


def singleton_sites(tree):
    for stmt in tree.body:
        if (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.UnaryOp)
                and isinstance(stmt.value.op, ast.USub)):
            continue
        names = [n for n in ast.walk(stmt)
                 if isinstance(n, ast.Name) and is_var(n.id)]
        counts = Counter(n.id for n in names)
        for n in names:
            if counts[n.id] == 1 and not n.id.endswith("_UNUSED"):
                yield n


def rewrite(path):
    src = path.read_text()
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    sites = sorted(singleton_sites(tree),
                   key=lambda n: (n.lineno, n.col_offset), reverse=True)
    for n in sites:
        ln = n.lineno - 1
        col = n.col_offset
        assert lines[ln][col:col + len(n.id)] == n.id, (path, n.lineno, n.id)
        lines[ln] = (lines[ln][:col] + n.id + "_UNUSED"
                     + lines[ln][col + len(n.id):])
    if sites:
        path.write_text("".join(lines))
    return len(sites)


if __name__ == "__main__":
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    total = 0
    for p in sorted(root.rglob("*.clausal")):
        if ".claude" in p.parts:
            continue
        total += rewrite(p)
    print(f"renamed {total} occurrences")
```

- [ ] **Step 2: Baseline the failure set, run the sweep, diff**

```bash
/workspace/clausal/venv/bin/python -m pytest tests -q 2>&1 | tail -3 > /tmp/before.txt   # plus the packages/ suites actually affected
/workspace/clausal/venv/bin/python scripts/rename_singletons.py .
git diff --stat | tail -5
```
Eyeball a sample of the diff: every change must be exactly `NAME` → `NAME_UNUSED` at a single-occurrence site. Multi-line clause statements: the script asserts the exact span before editing, so a mismatch aborts loudly rather than corrupting.

- [ ] **Step 3: Re-run affected suites; failure set must be unchanged; singleton warnings ~zero**

Run the same chunked suites; also `grep`-load a few of the heaviest-hit fixtures and confirm no `ClausalSingletonWarning` remains (a handful of legitimate stragglers may earn a hand-placed `-allow_singletons` — e.g. generated-looking fixtures — record each in the commit message).

- [ ] **Step 4: Commit**

```bash
git add scripts/rename_singletons.py
git add <the swept .clausal paths — from git status, explicitly; never -A>
git commit -m "corpus: rename singleton variable occurrences to NAME_UNUSED

Script-swept (scripts/rename_singletons.py), per-occurrence, verified by
failure-set diff."
```

---

### Task 5: `-constants` directive, groundness check, and reference resolution

**Files:**
- Create: `clausal/logic/constants.py`
- Modify: `clausal/templating/term_rewriting.py` — `_handle_directive` (:3890), new `_handle_constants_directive`, `EmbedTransformer.__init__`, `_make_term_transformer` (:3352), `TermTransformer.__init__` + `visit_Name` (:1441), `-module`/`-private` handlers (:3964, :4033)
- Modify: `clausal/import_hook.py` — every `module_dict["$define_predicate"] = ...` site (:147, :493; grep for others) gains `module_dict["$check_constant_ground"] = check_constant_ground`
- Test: `tests/test_constants.py` (create)

**Interfaces:**
- Consumes: Task 2 (`_is_constant_name`).
- Produces: `clausal.logic.constants.check_constant_ground(name: str, value) -> value` (raises `ConstantNotGroundError(ValueError)`); `TermTransformer` constructor param `constants: frozenset[str]`; `EmbedTransformer._constants: set[str]` (Task 6 adds imported names to it). v1 RHS grammar: scalar literals, previously declared constants, declared atoms, arithmetic BinOp/UnaryOp over those, and `++(expr)` (double-UAdd) escapes. List/dict/set RHS → SyntaxError (structured constants deferred; the message says so).

- [ ] **Step 1: Write the failing tests**

```python
"""-constants: declared, ground at module load, folded into clause terms."""
import textwrap
import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


def _load(tmp_path, name, text):
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(text).lstrip())
    return _load_module(f"tc_{name}", str(path))


def _values(module, goal_name, *args):
    v = Var()
    return [deref(v) for _ in call(goal_name, *args, v,
                                   module=module.__dict__["$module"])]


def test_scalar_constant_in_arithmetic(tmp_path):
    m = _load(tmp_path, "a", """
        -constants(_PI_ = 3.14159)
        area(R, A) <- (A is ++(_PI_ * R * R))
    """)
    [a] = _values(m, "area", 2.0)
    assert abs(a - 3.14159 * 4.0) < 1e-9


def test_constant_as_plain_argument(tmp_path):
    m = _load(tmp_path, "b", """
        -constants(_MAX_ = 3)
        limit(_MAX_),
        got(X) <- limit(X)
    """)
    assert _values(m, "got") == [] or True  # shape sanity below is the real check
    v = Var()
    results = [deref(v) for _ in call("limit", v, module=m.__dict__["$module"])]
    assert results == [3]


def test_constant_from_prior_constant_and_arithmetic(tmp_path):
    m = _load(tmp_path, "c", """
        -constants(_BASE_ = 10, _LIMIT_ = _BASE_ * 4 + 2)
        lim(_LIMIT_),
    """)
    v = Var()
    assert [deref(v) for _ in call("lim", v, module=m.__dict__["$module"])] == [42]


def test_plusplus_rhs(tmp_path):
    m = _load(tmp_path, "d", """
        -constants(_PI_ = ++__import__('math').pi)
        pi(_PI_),
    """)
    import math
    v = Var()
    assert [deref(v) for _ in call("pi", v, module=m.__dict__["$module"])] == [math.pi]


def test_undeclared_constant_reference_is_syntax_error(tmp_path):
    with pytest.raises(SyntaxError, match="_PI_"):
        _load(tmp_path, "e", "area(R, A) <- (A is ++(_PI_ * R))\n")


def test_unground_rhs_raises_at_load(tmp_path):
    from clausal.logic.constants import ConstantNotGroundError
    with pytest.raises(ConstantNotGroundError):
        _load(tmp_path, "f", """
            -constants(_V_ = ++__import__('clausal.logic.variables',
                                           fromlist=['Var']).Var())
            p(_V_),
        """)


def test_structured_rhs_rejected_for_now(tmp_path):
    with pytest.raises(SyntaxError, match="structured"):
        _load(tmp_path, "g", "-constants(_L_ = [1, 2, 3])\np(X) <- (X == 1)\n")


def test_module_export_list_rejects_constant_names(tmp_path):
    with pytest.raises(SyntaxError, match="-constants"):
        _load(tmp_path, "h", "-module(h, [_PI_])\n-constants(_PI_ = 3.14)\n")


def test_non_constant_shaped_declaration_rejected(tmp_path):
    with pytest.raises(SyntaxError, match="constant name"):
        _load(tmp_path, "i", "-constants(PI = 3.14)\np(X) <- (X == 1)\n")
```

- [ ] **Step 2: Run to verify failure**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_constants.py -q`
Expected: FAIL — unknown directive `-constants` (the dispatch error message lists known directives).

- [ ] **Step 3: Runtime helper**

`clausal/logic/constants.py`:

```python
"""Load-time support for -constants declarations.

A constant is a module global bound to a ground value before any clause
statement executes; clause construction embeds the value, so downstream
(indexing, solve, translation) never sees a name. This module supplies the
groundness gate the lowered assignment routes through.
"""
from clausal.logic.variables import Var


class ConstantNotGroundError(ValueError):
    """A -constants RHS produced a value containing an unbound variable."""


def _contains_var(value) -> bool:
    if isinstance(value, Var):
        return True
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_contains_var(v) for v in value)
    if isinstance(value, dict):
        return any(_contains_var(k) or _contains_var(v)
                   for k, v in value.items())
    args = getattr(value, "args", None)
    if args is not None:
        return any(_contains_var(a) for a in args)
    return False


def check_constant_ground(name: str, value):
    """Gate a -constants binding: return *value* iff it is ground."""
    if _contains_var(value):
        raise ConstantNotGroundError(
            f"-constants: `{name}` must be fully ground at load time; "
            f"got a value containing an unbound variable: {value!r}")
    return value
```

Adjust `_contains_var` to the real term API if `.args` is wrong — check how `terms.py:587 is_ground` walks and prefer delegating to it for term objects.

- [ ] **Step 4: Directive handler + lowering**

In `_handle_directive`, before the unknown-directive raise: `if name == "constants": return transformer._handle_constants_directive(args, expr_stmt)` and add `-constants` to the known-directives message. Handler:

```python
    def _handle_constants_directive(transformer, args, expr_stmt):
        """Process ``-constants(_PI_ = 3.14159, _MAX_ = _PI_ * 2)``.

        Declarations arrive as keyword arguments on the directive call. Each
        lowers to ``<name> = $check_constant_ground('<name>', <rhs>)`` at
        module level, so the value is bound (and gated for groundness) before
        any clause statement executes; references are plain Name loads and the
        value lands inside clause terms — folding, without a Var anywhere.
        See implementation_plans/module-level-constants.md.
        """
        call_node = expr_stmt.value.operand  # the Call under the USub
        if args or not call_node.keywords:
            raise SyntaxError(
                "-constants takes name = value pairs: "
                "-constants(_PI_ = 3.14159, _MAX_ = 3)")
        statements = []
        for kw in call_node.keywords:
            ident = kw.arg
            if ident is None or not _is_constant_name(ident):
                raise SyntaxError(
                    f"-constants: {ident!r} is not a constant name — "
                    f"constants spell with exactly one leading and one "
                    f"trailing underscore, e.g. _PI_")
            if ident in transformer._constants:
                raise SyntaxError(
                    f"-constants: `{ident}` is already bound (earlier "
                    f"-constants or an import)")
            if ident[1:-1].endswith("_UNUSED"):
                # Decided edge (todo/done/module-level-constants-open-
                # questions.md #3): legal, but visually collides with the
                # singleton-suppression suffix.
                import warnings  # noqa: PLC0415
                warnings.warn(
                    f"-constants: `{ident}` ends in _UNUSED, which reads as "
                    f"the unused-variable marker; consider another name",
                    ClausalLintWarning, stacklevel=2)
            rhs = transformer._transform_constant_rhs(kw.value, ident)
            transformer._constants.add(ident)
            assign = replace(
                Assign(
                    targets=[replace(Name(id=ident, ctx=store), kw.value)],
                    value=replace(
                        Call(
                            func=replace(
                                Name(id="$check_constant_ground", ctx=load),
                                kw.value),
                            args=[replace(Constant(value=ident), kw.value),
                                  rhs],
                            keywords=[],
                        ), kw.value),
                ), expr_stmt)
            fix_missing_locations(assign)
            statements.append(assign)
        return statements if len(statements) > 1 else statements[0]
```

RHS validator/transformer (plain Python AST out — evaluated at module exec):

```python
    def _transform_constant_rhs(transformer, node, ident):
        """Validate and return the Python AST for a -constants RHS.

        v1 grammar: scalar Constant, previously declared constant, declared
        atom, unary/binary arithmetic over those, and a ``++`` escape
        (adjacent double UAdd) whose operand is emitted verbatim as Python.
        Structured literals (list/dict/set/tuple) are deferred — the
        Clausal-term vs Python-value question is not yet decided for them.
        """
        if isinstance(node, Constant):
            return node
        if isinstance(node, Name):
            if node.id in transformer._constants or node.id in transformer._atoms:
                return node
            raise SyntaxError(
                f"-constants: `{ident}` RHS references `{node.id}`, which is "
                f"neither a previously declared constant nor a declared atom")
        if (isinstance(node, UnaryOp) and isinstance(node.op, UAdd)
                and isinstance(node.operand, UnaryOp)
                and isinstance(node.operand.op, UAdd)):
            return node.operand.operand  # ++expr: raw Python, load-time eval
        if isinstance(node, UnaryOp):
            return replace(UnaryOp(op=node.op, operand=transformer.
                           _transform_constant_rhs(node.operand, ident)), node)
        if isinstance(node, BinOp):
            return replace(BinOp(
                left=transformer._transform_constant_rhs(node.left, ident),
                op=node.op,
                right=transformer._transform_constant_rhs(node.right, ident),
            ), node)
        if isinstance(node, (List, Tuple, Set, Dict)):
            raise SyntaxError(
                f"-constants: structured constant RHS not yet supported for "
                f"`{ident}` — use a scalar or a ++() escape")
        raise SyntaxError(
            f"-constants: unsupported RHS for `{ident}`: {unparse(node)}")
```

Match the actual node-class names used in this file (it aliases Python ast classes — check the imports at the top; `UAdd` may need adding to them).

- [ ] **Step 5: Reference resolution + strict error + export-list rejection**

(a) `EmbedTransformer.__init__`: `transformer._constants: set[str] = set()`. `_make_term_transformer` passes `constants=frozenset(transformer._constants)`; `TermTransformer.__init__` stores `transformer.constants = constants` (new keyword param, default `frozenset()`).

(b) `visit_Name` (:1449), immediately after the truth-alias block:

```python
        # Declared or imported constant: a module global holding a ground
        # value, bound before any clause statement executes. A plain Name
        # load embeds the value in the clause term — indexing sees the
        # literal, no Var is involved.
        if identifier in transformer.constants:
            return replace(Name(id=identifier, ctx=load), name)
        if _is_constant_name(identifier):
            raise SyntaxError(
                f"`{identifier}` is a constant name (one leading and one "
                f"trailing underscore) but nothing declares it. Declare "
                f"-constants({identifier} = <ground value>) before this "
                f"clause, or import it: -import_from(mod, [{identifier}])")
```

(c) `-module` (:3995 Name branch) and `-private` handlers: before treating a bare `Name` as an atom, `if _is_constant_name(export.id): raise SyntaxError(f"-module cannot list constant `{export.id}`: constants are public module globals — declare with -constants and import with -import_from; no export listing is needed")` (same for `-private`).

(d) `import_hook.py`: add `from clausal.logic.constants import check_constant_ground` and `module_dict["$check_constant_ground"] = check_constant_ground` beside **every** `$define_predicate` injection (grep — there are at least the :147 dummy, :493 REPL, and the main-path sites).

- [ ] **Step 6: Run the tests; iterate**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_constants.py tests/test_var_classifier_conformance.py -q`
Expected: PASS. The census guard from Task 2 will now hit the new test fixtures only if it scans `tmp_path` — it scans the repo tree, so no conflict. If `test_constant_as_plain_argument` fails on the fact form (`limit(_MAX_),`), the trailing-comma fact path builds heads through `_build_fact_statements` — confirm the head args run through the same `TermTransformer` (they do: :3391) so the constants branch applies.

- [ ] **Step 7: fmt round-trip sanity**

Run the formatter over a `-constants` fixture (see `clausal/fmt` docs/tests for the entry point) and confirm the directive round-trips unchanged — fmt is AST-based and directives are generic USub-Call statements, so this should need no fmt change; if it does, fix within this task.

- [ ] **Step 8: Commit**

```bash
git add clausal/logic/constants.py clausal/templating/term_rewriting.py clausal/import_hook.py tests/test_constants.py
git commit -m "constants: -constants directive — declared, ground at load, folded

Scalar v1: literals, prior constants, declared atoms, arithmetic, and
++() escapes, gated by $check_constant_ground; references are plain
Name loads so clause terms embed the value. Structured RHS deferred."
```

---

### Task 6: Importing constants — `-import_from`, alias form, qualified access

**Files:**
- Modify: `clausal/templating/term_rewriting.py` — `_handle_import_from_directive` (:4198, both the direct-Name branch :4223 and the alias branch :4245), `visit_Attribute` (:1521)
- Test: extend `tests/test_constants.py`

**Interfaces:**
- Consumes: Task 5 (`EmbedTransformer._constants`, `TermTransformer.constants`).
- Produces: `-import_from(m, [_PI_])` and `alias(_PI_, _TAU_)` bind the owner's value as an importer global; `m._PI_` after `-import_module(m)` resolves as a module attribute.

- [ ] **Step 1: Write the failing tests (append to tests/test_constants.py)**

```python
def test_import_constant_direct(tmp_path):
    _load(tmp_path, "own1", "-constants(_PI_ = 3.14159)\npi(_PI_),\n")
    m = _load(tmp_path, "use1", """
        -import_from(tc_own1, [_PI_])
        twopi(X) <- (X is ++(_PI_ * 2))
    """)
    v = Var()
    [x] = [deref(v) for _ in call("twopi", v, module=m.__dict__["$module"])]
    assert abs(x - 6.28318) < 1e-4


def test_import_constant_alias(tmp_path):
    _load(tmp_path, "own2", "-constants(_PI_ = 3.14159)\n")
    m = _load(tmp_path, "use2", """
        -import_from(tc_own2, [alias(_PI_, _MYPI_)])
        p(_MYPI_),
    """)
    v = Var()
    assert [deref(v) for _ in call("p", v, module=m.__dict__["$module"])] == [3.14159]


def test_import_constant_alias_shape_mismatch_rejected(tmp_path):
    _load(tmp_path, "own3", "-constants(_PI_ = 3.14159)\n")
    with pytest.raises(SyntaxError, match="constant"):
        _load(tmp_path, "use3", "-import_from(tc_own3, [alias(_PI_, Pi)])\n")


def test_qualified_constant_access(tmp_path):
    _load(tmp_path, "own4", "-constants(_PI_ = 3.14159)\n")
    m = _load(tmp_path, "use4", """
        -import_module(tc_own4)
        p(X) <- (X is ++(tc_own4._PI_ + 0))
    """)
    v = Var()
    assert [deref(v) for _ in call("p", v, module=m.__dict__["$module"])] == \
        [3.14159]
```

The qualified test goes through `++` deliberately — `++` evaluates arbitrary Python against module globals, and `-import_module` puts the module object there, so it must pass once the import lands. A follow-on assertion with bare-term qualified access (`p(tc_own4._PI_),`) is attempted in Step 3 and kept only if the attribute path supports it without contortions; otherwise raise a clear SyntaxError pointing at `-import_from` (record the choice in the test).

- [ ] **Step 2: Run to verify failure**

Expected: the direct import currently succeeds *lexically* (post-re-carve `_PI_` passes the var-shape check) but binds via `_import_remap`/LoadName — the use site then misresolves. Observe the actual failure mode before Step 3.

- [ ] **Step 3: Implement**

In `_handle_import_from_directive` direct-Name branch (:4223): before the var-shape check,

```python
                if _is_constant_name(local_name):
                    # Imported constant: the ImportFrom below binds the
                    # owner's ground value as a module global; use sites
                    # resolve through the constants branch of visit_Name,
                    # not the predicate remap.
                    if local_name in transformer._constants:
                        raise SyntaxError(
                            f"-import_from: `{local_name}` is already bound "
                            f"by an earlier -constants or import in this "
                            f"file; use alias({local_name}, _OTHER_)")
                    transformer._constants.add(local_name)
                    aliases.append(alias(name=local_name))
                    import_names.append(local_name)   # match the accumulation shape
                    continue
```

(Adapt to the loop's actual accumulation flow — `import_names` is built after the loop from `aliases`; if so, only the `aliases.append` + `continue` is needed.) Alias branch (:4245): if `_is_constant_name(orig_name)` or `_is_constant_name(local_name)`, require **both** to be constant-shaped (else `SyntaxError: constant imports must alias to a constant name (alias(_PI_, _MYPI_))`), then `transformer._constants.add(local_name)`, `aliases.append(alias(name=orig_name, asname=local_name))`, and skip the remap/`_imported_functors` bookkeeping.

For qualified access: in `visit_Attribute` (:1521), where the dotted chain bottoms out in a non-variable base that is not a dict-read candidate, if the **final** attribute is constant-shaped, emit the attribute chain as plain Python (`return transformer.generic_visit-style passthrough` — mirror however qualified predicate references in term position are emitted in this file; if no such passthrough exists, keep the `++` route as the supported spelling and raise `SyntaxError("qualified constant access in term position is not supported; -import_from it or use ++(mod._X_)")` with a test pinning the message).

- [ ] **Step 4: Run and commit**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_constants.py tests/audit_2026_07_05/test_10_rewriting_import.py tests/test_var_shaped_predicate_name.py -q`
Expected: PASS; A10-F017 tests still pass (predicate aliases remain rejected — only constant-shaped names take the new path).

```bash
git add clausal/templating/term_rewriting.py tests/test_constants.py
git commit -m "constants: -import_from and alias() import constants by value binding

Constant-shaped names bypass the predicate remap: the lowered
ImportFrom binds the owner's ground value; visit_Name resolves as a
local constant. Alias form requires constant-to-constant."
```

---

### Task 7: Prolog translators

**Files:**
- Modify: `clausal/tools/prolog_dialect.py:143` (`prolog_var_to_clausal`)
- Modify: `clausal/tools/clausal_to_prolog.py` (directive handling — find where `-module`/`-import_from` directives are consumed or skipped)
- Test: `tests/test_prolog_to_clausal_var_names.py` (create; or extend the existing translator test file — `grep -rl prolog_var_to_clausal tests`)

**Interfaces:**
- Consumes: Task 2 (constant shape definition).
- Produces: inbound Prolog variables never map to constant-shaped spellings; outbound translation of a `-constants` file raises `NotImplementedError` with a pointer message (v1 scope).

- [ ] **Step 1: Write the failing tests**

```python
"""Inbound Prolog variables must never land on the _X_ constant class."""
from clausal.tools.prolog_dialect import prolog_var_to_clausal


def test_trailing_underscore_prolog_var_is_not_constant_shaped():
    # Prolog `_PI_` is a variable; naive lowering gives `_pi_`, which is
    # Clausal's constant class. The trailing underscore must be stripped.
    got = prolog_var_to_clausal("_PI_")
    assert not (len(got) >= 3 and got[0] == "_" and got[-1] == "_"
                and got[1] != "_" and got[-2] != "_")


def test_titlecase_trailing_underscore():
    got = prolog_var_to_clausal("Foo_")
    assert got == "_foo"
```

- [ ] **Step 2: Verify failure, then fix**

In `prolog_var_to_clausal`, before returning the leading-underscore forms:

```python
    if name.startswith("_"):
        candidate = "_" + name[1:].lower()
    elif len(name) == 1 and name.isupper():
        return name
    else:
        candidate = "_" + name.lower()
    # Clausal reserves one-underscore-each-end spellings for constants;
    # a translated VARIABLE must never land on that class.
    while len(candidate) > 1 and candidate.endswith("_"):
        candidate = candidate[:-1]
    return candidate if candidate != "_" else "_v"
```

The per-clause `_var_name` disambiguator (`prolog_to_clausal.py:251`) already resolves any collisions this stripping introduces.

- [ ] **Step 3: Outbound guard**

In `clausal_to_prolog`'s directive handling, on encountering a `-constants` directive: `raise NotImplementedError("clausal_to_prolog: -constants files are not translatable yet — Prolog has no constants; inlining is tracked in implementation_plans/module-level-constants.md")`. Add a small test asserting the message.

- [ ] **Step 4: Run translator tests + commit**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_prolog_to_clausal_var_names.py $(grep -rl 'clausal_to_prolog\|prolog_to_clausal' tests --include='test_*.py' | tr '\n' ' ') -q`

```bash
git add clausal/tools/prolog_dialect.py clausal/tools/clausal_to_prolog.py tests/test_prolog_to_clausal_var_names.py
git commit -m "translators: keep inbound Prolog variables off the constant class

prolog_var_to_clausal strips trailing underscores; clausal_to_prolog
refuses -constants files explicitly rather than mistranslating."
```

---

### Task 8: Documentation + full-suite verification

**Files:**
- Modify: `docs/syntax.md` (Logic variables section: the constant class, the `_UNUSED` convention; new Constants subsection with the `area == _PI_ * R**2` motivating example)
- Modify: `docs/directives.md` (`-constants`, `-allow_singletons`, updated known-directives list)
- Modify: `docs/for_prolog_programmers.md` (variables table row: singleton warnings + `_UNUSED` vs Prolog's `_Var`; constants have no Prolog equivalent)
- Modify: `implementation_plans/module-level-constants.md` (Status → IMPLEMENTED, date, deviations list — at minimum: v1 scalar-only RHS, qualified-access outcome from Task 6, translators' NotImplementedError)

**Interfaces:** consumes everything; produces the documented surface.

- [ ] **Step 1: Write the docs** — each section shows one runnable example in the house `--8<--`/fixture style where the neighboring sections use it, otherwise plain fenced blocks. Cover: the lexical rule (verbatim from Global Constraints), declaration, `++` RHS caveat (machine-dependent values are legal — say so), import (direct/alias/qualified-as-implemented), `_UNUSED` (canonical spelling, inverse lint), `-allow_singletons`, and the `_1_`/`_X_UNUSED_` edges.

- [ ] **Step 2: Doc snippet check** — `clausal/tools/doc_snippet_check.py` exists; run it if docs here participate (`grep -rn "syntax.md\|directives.md" clausal/tools/doc_snippet_check.py` to confirm scope).

- [ ] **Step 3: Full chunked suite; diff the failure set against the pre-branch baseline** — `tests/` in 3-4 chunks, then `packages/clausal-scipy/tests` and any other packages suites touched by Task 4. The failure set must equal the baseline exactly.

- [ ] **Step 4: Commit**

```bash
git add docs/syntax.md docs/directives.md docs/for_prolog_programmers.md implementation_plans/module-level-constants.md
git commit -m "docs: constants (_X_), singleton lint, -allow_singletons"
```

---

## Post-plan

After all tasks: superpowers:requesting-code-review against the branch, then superpowers:finishing-a-development-branch. The roborev reviewer (`/workspace/roborev/roborev`) is available for a semantic pass — it catches reasoning errors a green suite can't.
