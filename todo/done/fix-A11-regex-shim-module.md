# fix(A11-F001): clausal/regex.py shim imports nonexistent clausal.modules.regex

`clausal/regex.py` is `from clausal.modules.regex import *` — that module does
not exist; the implementation is `clausal/modules/py/re.py` (clausal-source
name "regex" resolves via `_IMPORT_ALIASES["regex"]="py.re"`,
templating/term_rewriting.py:1327). Any Python caller following the shim gets
ModuleNotFoundError.

**Fix**: re-export from `clausal.modules.py.re` (and fix the docstring), or
delete the shim if nothing imports it (grep first).

**Test**: test_11_modules_interop.py::test_F001_regex_shim_importable (xfail).
