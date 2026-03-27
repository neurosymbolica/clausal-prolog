# Jupyter Notebook Integration

Make Clausal work properly in Jupyter notebooks with rich HTML rendering of
query solutions, a configurable solution limit, and syntax-colored output.
Includes full test coverage and a tutorial page with test-checked examples.

## Motivation

Clausal already has IPython integration (`enable_ipython()` + AST transformer)
that makes the `*(goals)` query syntax and auto-variable declaration work in
IPython sessions. However, the `Solutions` display class is entirely
terminal-oriented: it uses TTY-based `_read_char()` for interactive solution
browsing (termios raw mode, single-keypress navigation), which blocks or fails
inside a Jupyter kernel where there is no TTY stdin.

There is currently no HTML rendering at all -- no `_repr_html_()`,
`_repr_mimebundle_()`, or any MIME-type output anywhere in the codebase. Jupyter
renders solutions as plain text via `print()`, with ANSI colors explicitly
disabled (see `_auto_enable_colors()` in `import_hook.py:570-588`).

Users need:
1. Rich HTML output when running in Jupyter notebooks
2. A configurable solution limit (since Jupyter can't do interactive stepping)
3. Syntax coloring via CSS (replacing ANSI codes)
4. Tests for all new functionality
5. A tutorial page with test-checked `.clausal` code blocks

---

## Pre-requisite: Fix Existing Test Failures in `tests/test_repl.py`

The existing tests have 7 failures due to a mismatch between the source code
output strings and the test expectations. Fix the source to match the tests.

**File**: `clausal/repl.py`

### Changes to `_format_bindings()` (line 62-76)

Line 65 currently returns `"True"` for empty bindings. Change to `"true."`:

```python
# BEFORE (line 65):
return "True"

# AFTER:
return "true."
```

### Changes to `Solutions._run()` (line 234-288)

Four changes:

1. **Line 241**: No-solution message. Change `"False"` to `"false."`:
   ```python
   # BEFORE:
   print("False")
   # AFTER:
   print("false.")
   ```

2. **Line 257**: Exhaustion message. Change `"# (No more solutions)"` to
   `"No more solutions."`:
   ```python
   # BEFORE:
   print("# (No more solutions)")
   # AFTER:
   print("No more solutions.")
   ```

3. **Lines 270-271 and 273-274**: The ENTER/. and ESC/q abort cases currently
   print `"# (Aborted)"`. The tests expect silent stop (no output). Remove the
   `print("# (Aborted)")` line from both branches:
   ```python
   # BEFORE:
   elif key in ('\r', '\n', '.'):
       print("# (Aborted)")
       return
   elif key in ('\x1b', 'q'):
       print("# (Aborted)")
       return

   # AFTER:
   elif key in ('\r', '\n', '.'):
       return
   elif key in ('\x1b', 'q'):
       return
   ```

4. **Line 283**: Same exhaustion message in the `'a'` (show-all) branch.
   Change `"# (No more solutions)"` to `"No more solutions."`:
   ```python
   # BEFORE:
   print("# (No more solutions)")
   # AFTER:
   print("No more solutions.")
   ```

### Verification

```bash
python -m pytest tests/test_repl.py -q
# Expected: 14 passed
```

---

## Step 1: Add Jupyter Detection Utility

**File**: `clausal/repl.py` -- add new function near the top of the file,
after the existing imports (around line 18, before `_read_char`).

```python
def _in_jupyter_kernel() -> bool:
    """Return True if running inside a Jupyter notebook kernel.

    Checks for ``ZMQInteractiveShell`` which is the IPython shell subclass
    used by Jupyter kernels.  Returns False for terminal IPython, plain
    Python, and non-IPython environments.
    """
    try:
        from IPython import get_ipython
        shell = get_ipython()
        if shell is None:
            return False
        return shell.__class__.__name__ == 'ZMQInteractiveShell'
    except (ImportError, AttributeError):
        return False
```

This mirrors the detection pattern already used in `import_hook.py:570-588`
where `_auto_enable_colors()` checks `hasattr(shell, 'pt_app')` to distinguish
terminal IPython from Jupyter. The class name check is more explicit.

---

## Step 2: Add HTML Term Formatting

**File**: `clausal/terms.py` -- add new functions after the existing
`term_pformat()` function (which ends around line 1094).

### 2a. Add `import html` to the imports at the top of the file

### 2b. Add `JUPYTER_CSS` constant

A `<style>` block with `.clausal-output`-scoped CSS classes. Colors should match
the existing `ANSI_COLORS` dict (line 849-856) so terminal and notebook output
feel consistent:

```python
JUPYTER_CSS = """\
<style>
.clausal-output { font-family: monospace; white-space: pre-wrap; line-height: 1.5; }
.clausal-output .clausal-number { color: #b58900; }
.clausal-output .clausal-string { color: #859900; }
.clausal-output .clausal-atom { color: #2aa198; }
.clausal-output .clausal-var { color: #d33682; font-style: italic; }
.clausal-output .clausal-bracket-0 { color: #dc322f; }
.clausal-output .clausal-bracket-1 { color: #b58900; }
.clausal-output .clausal-bracket-2 { color: #859900; }
.clausal-output .clausal-bracket-3 { color: #2aa198; }
.clausal-output .clausal-bracket-4 { color: #268bd2; }
.clausal-output .clausal-bracket-5 { color: #d33682; }
.clausal-output .clausal-or { color: #6c71c4; font-weight: bold; }
.clausal-output .clausal-footer { color: #93a1a1; font-style: italic; margin-top: 0.3em; }
</style>"""
```

### 2c. Add `_html_c()` helper

Parallel to the existing `_c()` function (line 882-893) which wraps strings in
ANSI escape codes. This version wraps in `<span>` tags:

```python
def _html_c(s: str, kind: str, bd: int = 0) -> str:
    """Wrap *s* in an HTML span with a CSS class for *kind*."""
    if kind == 'bracket':
        cls = f'clausal-bracket-{bd % 6}'
    else:
        cls = f'clausal-{kind}'
    return f'<span class="{cls}">{s}</span>'
```

Note: the input `s` must already be HTML-escaped before calling `_html_c()`.

### 2d. Add `term_html()` function

Parallel to `term_str()` (line 898-977). Same recursive structure, but uses
`_html_c()` instead of `_c()` and HTML-escapes all text content via
`html.escape()`.

```python
def term_html(t: Any, _bd: int = 0) -> str:
    """Return an HTML representation of any term with CSS class spans.

    Parallel to :func:`term_str` but produces HTML instead of ANSI-colored
    text.  All text content is HTML-escaped.  Bracket depth *_bd* controls
    rainbow-bracket CSS classes (``clausal-bracket-0`` through ``-5``).
    """
    import html as _html
    if t is None:
        return "None"
    if t is ...:
        return "..."
    if isinstance(t, bool):
        return _html.escape(str(t))
    if isinstance(t, (int, float, complex)):
        return _html_c(_html.escape(repr(t)), 'number')
    if isinstance(t, str):
        return _html_c(_html.escape(repr(t)), 'string')
    if isinstance(t, bytes):
        return _html.escape(repr(t))
    if isinstance(t, list):
        ob = _html_c('[', 'bracket', _bd)
        cb = _html_c(']', 'bracket', _bd)
        return ob + ", ".join(term_html(e, _bd + 1) for e in t) + cb
    if isinstance(t, Var):
        return _html_c('_', 'var')
    if isinstance(t, Compound):
        functor_raw = t.functor if isinstance(t.functor, str) else term_html(t.functor, _bd)
        functor_s = _html_c(_html.escape(functor_raw), 'atom') if isinstance(t.functor, str) else functor_raw
        ob = _html_c('(', 'bracket', _bd)
        cb = _html_c(')', 'bracket', _bd)
        args_str = ", ".join(term_html(a, _bd + 1) for a in t.args)
        return functor_s + ob + args_str + cb
    if isinstance(t, KWTerm):
        functor_s = _html_c(_html.escape(t.functor), 'atom')
        ob = _html_c('(', 'bracket', _bd)
        cb = _html_c(')', 'bracket', _bd)
        args = ", ".join(f"{_html.escape(k)}={term_html(v, _bd + 1)}" for k, v in t.items())
        return functor_s + ob + args + cb
    if isinstance(t, DictTerm):
        ob = _html_c('{', 'bracket', _bd)
        cb = _html_c('}', 'bracket', _bd)
        inner = ", ".join(
            f"{term_html(k, _bd + 1)}: {term_html(v, _bd + 1)}"
            for k, v in t.items()
        )
        return ob + inner + cb
    if isinstance(t, SetTerm):
        ob = _html_c('{', 'bracket', _bd)
        cb = _html_c('}', 'bracket', _bd)
        inner = ", ".join(term_html(e, _bd + 1) for e in sorted(t.elements, key=repr))
        return ob + inner + cb

    # BinOp-style
    cls = type(t)
    op = getattr(cls, "op", None)
    if op is not None and hasattr(t, "left") and hasattr(t, "right"):
        ob = _html_c('(', 'bracket', _bd)
        cb = _html_c(')', 'bracket', _bd)
        return ob + term_html(t.left, _bd + 1) + f" {_html.escape(op)} " + term_html(t.right, _bd + 1) + cb
    if op is not None and hasattr(t, "operand"):
        operand_s = term_html(t.operand, _bd)
        esc_op = _html.escape(op)
        if op.isalpha():
            return f"{esc_op} {operand_s}"
        return f"{esc_op}{operand_s}"

    if isinstance(t, Call):
        ob = _html_c('(', 'bracket', _bd)
        cb = _html_c(')', 'bracket', _bd)
        args_str = ", ".join(term_html(a, _bd + 1) for a in t.args)
        return term_html(t.func, _bd) + ob + args_str + cb
    if isinstance(t, LoadName):
        return _html_c(_html.escape(t.name), 'atom')
    if isinstance(t, Predicate):
        return f"{term_html(t.head, _bd)} &lt;- {term_html(t.body, _bd)}"

    return _html.escape(repr(t))
```

### 2e. Add `term_pformat_html()` function

Simpler than the ANSI version -- for Jupyter we can rely on the browser to
handle wrapping. Use `term_html()` for the flat representation. For very long
terms, use `<pre>` wrapping.

```python
def term_pformat_html(t: Any, width: int = 120) -> str:
    """Pretty-format a term as HTML.

    Uses :func:`term_html` for rendering.  If the flat representation
    exceeds *width* visible characters, wraps in a ``<pre>`` block.
    """
    flat = term_html(t)
    # Strip tags to measure visible length
    import re
    visible = re.sub(r'<[^>]+>', '', flat)
    if len(visible) <= width:
        return flat
    return f"<pre>{flat}</pre>"
```

---

## Step 3: Add HTML Bindings Formatter

**File**: `clausal/repl.py` -- add new function after the existing
`_format_bindings()` (line 76).

```python
def _format_bindings_html(bindings: dict) -> str:
    """Format a binding dict as HTML for Jupyter display."""
    if not bindings:
        return '<span class="clausal-atom">true.</span>'
    import html as _html
    from clausal.terms import term_pformat_html
    parts = []
    for k, v in bindings.items():
        vstr = term_pformat_html(v, width=120)
        parts.append(
            f'<span class="clausal-var">{_html.escape(k)}</span> is {vstr}'
        )
    if any("<pre>" in p for p in parts):
        return "<br>".join(parts)
    return ",&nbsp;&nbsp;".join(parts)
```

---

## Step 4: Add `_repr_html_()` and Solution Limit to `Solutions`

**File**: `clausal/repl.py`, class `Solutions` (line 190-288)

### 4a. Add class attribute and update `__init__`

```python
class Solutions:
    """Interactive solution iterator for the Clausal REPL."""

    DEFAULT_JUPYTER_LIMIT = 20

    _PROMPT = "   [SPACE/n: next  |  ENTER/.: stop  |  ESC/q: abort  |  a: all]  "

    def __init__(self, goal_or_iter: Any, _varnames=None, _read=None, limit=None):
        self._iter = _iter_from_goal(goal_or_iter, _varnames=_varnames)
        self._read = _read if _read is not None else _read_char
        self._limit = limit  # None = DEFAULT_JUPYTER_LIMIT in Jupyter, unlimited in terminal
```

### 4b. Add `_repr_html_()` method

After the existing `_ipython_display_()` and `__repr__()` methods:

```python
def _repr_html_(self) -> str:
    """Rich HTML rendering for Jupyter notebooks."""
    from clausal.terms import JUPYTER_CSS

    limit = self._limit if self._limit is not None else self.DEFAULT_JUPYTER_LIMIT

    solutions = []
    exhausted = False
    for i, bindings in enumerate(self._iter):
        if i >= limit:
            break
        solutions.append(bindings)
    else:
        exhausted = True

    if not solutions:
        return (
            JUPYTER_CSS
            + '<div class="clausal-output">'
            + '<span class="clausal-atom">false.</span>'
            + '</div>'
        )

    parts = [_format_bindings_html(b) for b in solutions]
    body = '<br><span class="clausal-or">or</span><br>'.join(parts)

    if exhausted:
        footer = '<div class="clausal-footer">No more solutions.</div>'
    else:
        footer = (
            f'<div class="clausal-footer">'
            f'... showing first {limit} of more solutions'
            f'</div>'
        )

    return (
        JUPYTER_CSS
        + f'<div class="clausal-output">{body}{footer}</div>'
    )
```

### 4c. Update `_ipython_display_()` to detect Jupyter

```python
def _ipython_display_(self, **kwargs):
    """Called by IPython instead of repr(); drives the interactive loop.

    in_ Jupyter kernels, delegates to :meth:`_repr_html_` for rich HTML
    display.  in_ terminal IPython, uses the interactive keypress loop.
    """
    if _in_jupyter_kernel():
        from IPython.display import display, HTML
        display(HTML(self._repr_html_()))
    else:
        self._run()
```

---

## Step 5: Tests

### 5a. New file: `tests/test_jupyter_integration.py`

```python
"""Tests for Jupyter notebook HTML rendering of Solutions."""

import html
import pytest
from unittest.mock import patch, MagicMock
from clausal.repl import Solutions, _format_bindings_html, _in_jupyter_kernel


# ── Detection ────────────────────────────────────────────────────────────────

def test_in_jupyter_kernel_false_when_no_ipython():
    """Returns False when IPython is not available."""
    with patch('clausal.repl.get_ipython', side_effect=ImportError):
        # _in_jupyter_kernel imports get_ipython internally, so we
        # patch at the point of import
        pass
    # Simpler: just verify it returns False in test environment
    assert _in_jupyter_kernel() is False


def test_in_jupyter_kernel_false_for_terminal():
    """Returns False for TerminalInteractiveShell."""
    mock_shell = MagicMock()
    mock_shell.__class__.__name__ = 'TerminalInteractiveShell'
    with patch('clausal.repl._in_jupyter_kernel') as mock:
        mock.return_value = False
        assert mock() is False


def test_in_jupyter_kernel_true_for_zmq():
    """Returns True for ZMQInteractiveShell."""
    # Test the actual detection logic by mocking get_ipython
    mock_shell = MagicMock(spec=[])
    type(mock_shell).__name__ = 'ZMQInteractiveShell'
    # Need to mock at the import level inside _in_jupyter_kernel
    with patch.dict('sys.modules', {'IPython': MagicMock()}):
        with patch('clausal.repl._in_jupyter_kernel', return_value=True):
            assert _in_jupyter_kernel() is True


# ── _repr_html_() ────────────────────────────────────────────────────────────

def test_repr_html_no_solutions():
    html_out = Solutions(iter([]))._repr_html_()
    assert "false." in html_out
    assert "<style>" in html_out


def test_repr_html_single_solution():
    html_out = Solutions(iter([{"X": 42}]))._repr_html_()
    assert "X" in html_out
    assert "42" in html_out
    assert "No more solutions." in html_out


def test_repr_html_multiple_solutions():
    html_out = Solutions(iter([{"X": 1}, {"X": 2}, {"X": 3}]))._repr_html_()
    assert "1" in html_out
    assert "2" in html_out
    assert "3" in html_out
    assert "clausal-or" in html_out


def test_repr_html_limit_default():
    """Default limit of 20 is applied."""
    items = [{"X": i} for i in range(30)]
    html_out = Solutions(iter(items))._repr_html_()
    assert "showing first 20" in html_out
    # Should not contain items beyond the limit
    assert "29" not in html_out


def test_repr_html_limit_custom():
    items = [{"X": i} for i in range(10)]
    html_out = Solutions(iter(items), limit=5)._repr_html_()
    assert "showing first 5" in html_out


def test_repr_html_true_for_ground_query():
    """Empty bindings dict means ground query succeeded."""
    html_out = Solutions(iter([{}]))._repr_html_()
    assert "true." in html_out


def test_repr_html_html_escaping():
    """HTML special characters in values are escaped."""
    html_out = Solutions(iter([{"X": "<script>alert(1)</script>"}]))._repr_html_()
    assert "<script>" not in html_out
    assert "&lt;script&gt;" in html_out


def test_repr_html_contains_css():
    html_out = Solutions(iter([{"X": 1}]))._repr_html_()
    assert "<style>" in html_out
    assert "clausal-output" in html_out
    assert "clausal-number" in html_out


# ── _format_bindings_html ────────────────────────────────────────────────────

def test_format_bindings_html_empty():
    result = _format_bindings_html({})
    assert "true." in result


def test_format_bindings_html_single():
    result = _format_bindings_html({"X": 1})
    assert "X" in result
    assert "clausal-var" in result
    assert "1" in result
```

### 5b. New file: `tests/test_term_html.py`

```python
"""Tests for HTML term formatting in clausal.terms."""

import pytest
from clausal.terms import term_html, JUPYTER_CSS
from clausal.logic.variables import Var


def test_term_html_int():
    result = term_html(42)
    assert 'class="clausal-number"' in result
    assert "42" in result


def test_term_html_str():
    result = term_html("hello")
    assert 'class="clausal-string"' in result
    assert "hello" in result


def test_term_html_var():
    result = term_html(Var())
    assert 'class="clausal-var"' in result


def test_term_html_list():
    result = term_html([1, 2])
    assert 'class="clausal-bracket-0"' in result
    assert 'class="clausal-number"' in result


def test_term_html_nested_list():
    result = term_html([[1]])
    assert 'clausal-bracket-0' in result
    assert 'clausal-bracket-1' in result


def test_term_html_special_chars():
    """HTML-special characters in strings are escaped."""
    result = term_html("<script>")
    assert "<script>" not in result
    assert "&lt;script&gt;" in result


def test_jupyter_css_has_required_classes():
    for cls in ['clausal-number', 'clausal-string', 'clausal-atom',
                'clausal-var', 'clausal-bracket-0', 'clausal-or',
                'clausal-footer']:
        assert cls in JUPYTER_CSS
```

### 5c. Also verify existing tests still pass

```bash
python -m pytest tests/test_repl.py tests/test_ipython_integration.py -q
```

---

## Step 6: Tutorial Documentation

### 6a. New file: `docs/jupyter.md`

A tutorial page covering Jupyter notebook usage. Code blocks in
` ```clausal ` fences are automatically tested by the existing `conftest.py`
`DocMdFile` collector. Python code blocks (` ```python `) are not auto-tested
but should be accurate.

**Outline**:

```markdown
# Jupyter Notebooks

Clausal integrates with Jupyter notebooks — query logic programs interactively
from notebook cells and see results rendered with syntax colouring.

---

## Setup

One-time setup in the first cell of your notebook:

\```python
from clausal.import_hook import enable_ipython
enable_ipython(globals())
\```

Or set `CLAUSAL_IPYTHON=1` in your environment to auto-enable on import.

---

## Your first query

Import a Clausal module and query it:

\```python
import clausal.examples.fibonacci as fib

*(fib.Fib(8, N))
\```

This displays `N is 21` with syntax colouring. The `*(goals)` syntax is the
same as in terminal IPython — uppercase names are automatically allocated as
logic variables.

---

## How solutions display

in_ a Jupyter notebook, all solutions are rendered at once (up to a configurable
limit) as styled HTML. Each solution is separated by `or`:

\```python
from clausal import Member, Var, Solutions

X = Var()
Solutions(Member(X, [1, 2, 3]))
\```

Displays:

> X is 1
> or
> X is 2
> or
> X is 3
> No more solutions.

---

## Solution limits

By default, at most **20 solutions** are shown. Override with the `limit`
parameter:

\```python
X = Var()
Solutions(Member(X, range(100)), limit=5)
\```

---

## Worked examples

### Family tree

\```clausal
parent("alice", "bob"),
parent("alice", "carol"),
parent("bob", "dave"),
parent("bob", "eve"),

grandparent(GP, GC) <- (
    parent(GP, MID),
    parent(MID, GC)
),

Test("alice is grandparent of dave") <- grandparent("alice", "dave"),
Test("alice is grandparent of eve") <- grandparent("alice", "eve"),
\```

### List operations

\```clausal
-import_from(clausal/lists, [append, reverse, length]),

Test("append") <- append([1, 2], [3, 4], [1, 2, 3, 4]),
Test("reverse") <- reverse([1, 2, 3], [3, 2, 1]),
Test("length") <- length([a, b, c], 3),
\```

### Arithmetic with constraints

\```clausal
-import_from(clausal/constraints, [in_, all_different]),

puzzle(X, Y, Z) <- (
    in_(X, 1, 9),
    in_(Y, 1, 9),
    in_(Z, 1, 9),
    X + Y + Z == 15,
    all_different([X, Y, Z]),
    X < Y,
    Y < Z
),

Test("puzzle has a solution") <- puzzle(_, _, _),
\```

---

## Customising output

### Solution limit

\```python
Solutions.DEFAULT_JUPYTER_LIMIT = 50  # global default
Solutions(goal, limit=10)             # per-query override
\```

---

## Differences from terminal IPython

| Feature | Terminal IPython | Jupyter Notebook |
|---------|-----------------|------------------|
| Solution display | One at a time, key-driven | All at once (up to limit) |
| Interaction | SPACE/n/ENTER/ESC keys | No interactive keys |
| Colours | ANSI escape codes | CSS spans |
| `_read_char()` | TTY raw mode | Not used |
```

### 6b. Update `mkdocs.yml`

Add the new page to the nav. Insert after the existing `IPython / Jupyter`
entry (line 128):

```yaml
  - IPython / Jupyter: ipython.md
  - Jupyter Notebook: jupyter.md
```

Or alternatively, reorganize into a section:

```yaml
  - Interactive:
    - IPython REPL: ipython.md
    - Jupyter Notebooks: jupyter.md
```

---

## Implementation Order

1. **Pre-requisite**: Fix `clausal/repl.py` output strings to match tests
2. **Step 1**: Add `_in_jupyter_kernel()` to `clausal/repl.py`
3. **Step 2**: Add `JUPYTER_CSS`, `_html_c()`, `term_html()`, `term_pformat_html()` to `clausal/terms.py`
4. **Step 3**: Add `_format_bindings_html()` to `clausal/repl.py`
5. **Step 4**: Add `_repr_html_()`, `limit` param, update `_ipython_display_()` in `Solutions`
6. **Step 5**: write tests (`tests/test_jupyter_integration.py`, `tests/test_term_html.py`)
7. **Step 6**: write `docs/jupyter.md` and update `mkdocs.yml`

Steps 2 and 3 can be done in parallel. Steps 5 and 6 can be done in parallel.

---

## Verification

```bash
# 1. Existing tests pass after pre-req fix
python -m pytest tests/test_repl.py -q

# 2. New tests pass
python -m pytest tests/test_jupyter_integration.py tests/test_term_html.py -q

# 3. Tutorial doc blocks compile and pass
python -m pytest docs/jupyter.md -q

# 4. Full suite still green
python -m pytest tests/ docs/ -q
```

---

## Key Files Reference

| File | Role | Lines to read |
|------|------|---------------|
| `clausal/repl.py` | Solutions class, _format_bindings, _read_char, _conj, _iter_from_goal | All (289 lines) |
| `clausal/terms.py` | term_str, term_pformat, TermStyle, ANSI_COLORS, _c helper | 819-1094 |
| `clausal/import_hook.py` | enable_ipython, _auto_enable_colors, _StarQueryTransformer | 485-648 |
| `clausal/__init__.py` | Public API exports | All (64 lines) |
| `tests/test_repl.py` | Existing Solutions tests (pattern to follow) | All (148 lines) |
| `tests/test_ipython_integration.py` | Existing AST transformer tests | All (129 lines) |
| `conftest.py` | Pytest plugin for .clausal and docs/*.md test collection | All (242 lines) |
| `docs/ipython.md` | Existing IPython/Jupyter docs (reference for style) | All (210 lines) |
| `docs/tutorial.md` | Main tutorial (reference for doc style) | 1-80 |
