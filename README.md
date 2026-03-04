# clausal

A Prolog-style logic programming DSL embedded in Python, built on a simplified AST and a generator-based trampoline.

## Modules

- **`clausal.simple_ast`** — Simplified Python AST with context-split nodes (no `Load`/`Store` context fields; separate `LoadName`/`StoreName` etc. types).
- **`clausal.conversion`** — Converts CPython `ast` trees into `simple_ast` nodes.
- **`clausal.term_rewriting`** — `TermTransformer` and `EmbedTransformer`: DSL syntax (`--expr`, `head<-body`, trailing-comma facts, `with the_following`) rewritten to `simple_ast` constructors.
- **`clausal.template_compiler`** — `@{}`-decorated function templates that expand to AST-building functions.
- **`clausal.trampoline`** — Generator-based trampoline with `Step`/`trampoline()` for stack-safe recursive computations.
- **`clausal.continuation_search`** — `Search`: greenlet-based iterator for continuation-passing search functions.
- **`clausal.import_hook`** — Import hook for `# predicates` modules; `enable_ipython()` for interactive use.
- **`clausal.simple_ast_node`** — `@node_class` decorator that generates `visit_children`, `transform_children`, and `__call__` via AST.

## Installation

```bash
pip install clausal
```

## Quick start

```python
import ast
from clausal import simple_ast

tree = ast.parse("x = 1 + 2")
simple = simple_ast.simplify(tree)
print(simple_ast.dump(simple))
```

### Embedding DSL terms

```python
from clausal.import_hook import enable_ipython
enable_ipython(globals())   # in IPython / Jupyter

result = --(x + y)   # produces simple_ast.Add node
```

### Prolog-style predicates

```python
# predicates          ← first line activates the import hook
parent(tom, bob)<-True,
parent(bob, ann)<-True,
```

## Requirements

- Python ≥ 3.14
- [greenlet](https://pypi.org/project/greenlet/) (for `clausal.continuation_search`)

## License

MIT
