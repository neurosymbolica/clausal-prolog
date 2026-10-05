# A plain cell's READ reaches another module's predicate, but its WRITE is refused

Found 2026-09-25 on fix/preflip-small-arms-2026-09-25 (task 7, small arms),
while pinning ruling (a), "a cell built from a handle is always plain".
Parked; nothing here is fixed.

**The filename is misleading.** I first saw this in a host that had dotted
goals, and suspected them.  Bisecting the host showed the dotted goals play
no part.  The trigger is a PYTHON-HELD predicate handle bound anywhere in the
host's module dict.

## Repro (both eras, main ae1a456d + the branch)

```
# sa_tlib.seam
-module(sa_tlib, [dfact/1])
-dynamic(dfact/1)
dfact(0),

# host
-module(sa_th, [run(G)])
-import_module(sa_tlib)
from clausal.logic.atoms import mangle
h = mangle('sa_tlib', 'dfact')        # <- this line alone is the trigger
run(G) <- call(G)
```

```python
call("run", ("dfact", X), module=host_lm)          # -> X = 0 (the OWNER's clause)
call("assertz", ("dfact", 5), module=host_lm)      # -> existence_error(procedure, dfact/1)
host.__dict__.get("dfact")                         # -> None; no row, no adopted row
```

What the host binds (the probe bisected the host body):

| host body | `call(("dfact", X))` | `assertz(("dfact", 5))` |
|---|---|---|
| nothing extra | existence_error | existence_error |
| `goal_d(X) <- sa_tlib.dfact(X)` (dotted goal) | existence_error | existence_error |
| `cell_d(C) <- same(C, sa_tlib.dfact(1))` (dotted term) | existence_error | existence_error |
| `get_d(X) <- call(sa_tlib.dfact(X))` | existence_error | existence_error |
| `h = mangle('sa_tlib', 'dfact')` only | **[0]** | existence_error |

## Cause

`predicate._import_index` indexes EVERY module-dict value that is a foreign
predicate binding (a class, or a mangled handle, whose owner db is not this
one) as an import, under the owner's plain name:

```python
for k, v in md.items():
    ...
    if not (isinstance(v, PredicateMeta)
            or (type(v) is str and _is_mangled_fast(v))):
        continue
    if not is_declared_predicate_name(v, db=db):
        continue
    owner = _binding_owner_db(v, db)
    if owner is None or owner is db:
        continue
    by_owner.setdefault(_binding_own_name(v), []).append((k, v))
```

`localize_owner_functor` (the round-6 aliased-import remap, reached from
`higher_order._resolve_named_goal`, which call/N uses) takes an unbound
`dfact` to be the owner's name for the "alias" `h`.  It dispatches the owner's
`dfact/1`:

```
_call_goal_n -> _resolve_named_goal -> localize_owner_functor(db, "dfact", 1)
  -> _UnqualifiedName(db, "h", 'sa_tlib\x1fdfact').dispatch_at(1)
  -> _dispatch_at -> sa_tlib's db.get_dispatch("dfact", 1)
```

The write doors ask `database_ops._find_pred_cls(functor, ...)`, which reads
only `module_dict[functor]`, so they never see `h`.

## Why it matters

* Reads and writes of the SAME plain cell disagree about which predicate it
  names.
* A Python variable that holds a handle, for example to build goals from Python
  or to call `--h(X)`, silently becomes an import alias for every meta-call of
  the plain name in that module.  An `-import_from(m, [alias(p, h)])` is the
  only thing that should do that.

## Options

1. `_import_index` counts only bindings that an `-import_from` recorded
   (`compiler_v2._import_from_origins` / the adopted rows), not every foreign
   value in the dict.
2. Make the write doors use the same index (reads and writes agree, but a
   Python-held handle still acts as an alias).

Option 1 matches ISO: a module's namespace is what it imports, not what its
Python variables hold.
