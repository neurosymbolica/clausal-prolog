# `_deref_params` in sklearn silently drops DictTerm

`clausal/modules/py/sklearn.py`, `_deref_params` (line ~431)

```python
def _deref_params(params):
    """Deep-deref a params dict."""
    params = deref(params)
    if isinstance(params, dict):
        return {str(deref(k)): deref(v) for k, v in params.items()}
    return {}
```

When params is a `DictTerm` (from a Clausal dict literal like `{"C": 2.0}`),
`isinstance(params, dict)` is false, so it silently returns `{}`.

`_param_3` was fixed to check `isinstance(params, (dict, DictTerm))`, but
`_deref_params` — which is used by other predicates — has the same bug. Any
predicate that routes through `_deref_params` with a Clausal dict literal will
get an empty dict.

Fix: add `DictTerm` to the isinstance check in `_deref_params`, or use duck
typing since both `dict` and `DictTerm` support `.items()`.
