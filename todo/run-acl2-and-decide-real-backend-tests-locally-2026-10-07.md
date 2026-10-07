# Run the ACL2 and decide tests against the real backends

Filed 2026-10-07. The operator will run these locally: the cloud sandbox the
packages were built in has no `acl2` and cannot reach the Hugging Face Hub, so
every test that needs a real backend skipped there, naming the reason. The
`*_stubbed.py` tests (fake bridge, fake router) and the doc-integrity tests
always run and passed.

| Package | Passed in the sandbox | Skipped there | Needs |
|---|---|---|---|
| `packages/clausal-acl2` | 62 | 9 | a running ACL2 Bridge |
| `packages/clausal-decide` | 35 | 13 | laya's checkpoint from the Hugging Face Hub (backend `laya`) |

Run each package's tests in a session of its own, separate from `tests/`
(packages/AGENTS.md). One combined run of both packages in the sandbox crashed
once inside a native extension (numpy was loaded) and passed on the rerun,
and one run of `clausal-decide` on its own gave 1 error in place of a skip
(35 passed, 12 skipped, 1 error) and did not recur in five reruns. Both were
with the Hugging Face Hub blocked. If either happens to you, note the
traceback here.

## Setup

```bash
pip install -e .                                   # the engine, from this checkout
pip install -e packages/clausal-acl2
pip install -e 'packages/clausal-decide[typesafe]' # laya (brings torch) + typesafe-sdk
```

Install the engine from the checkout first: installing a package can pull the
PyPI `clausal` over an editable install (seen 2026-10-06; reinstall with
`pip install --no-deps -e .` if it happens).

## ACL2

The real tests are the `.seam` fixtures under
`packages/clausal-acl2/tests/fixtures/` (`tests/conftest.py`). They use, in
order:

1. the bridge named by `CLAUSAL_ACL2_SOCKET`, a Unix socket of an ACL2 already
   running the bridge:
   ```lisp
   (include-book "centaur/bridge/top" :dir :system)
   (bridge::start "/tmp/acl2-bridge")
   ```
   then `export CLAUSAL_ACL2_SOCKET=/tmp/acl2-bridge`;
2. otherwise `acl2` on PATH, which the adapter starts itself. That needs the
   ACL2 books with `centaur/bridge` certified.

```bash
python -m pytest packages/clausal-acl2 -q -rs
```

Expect 71 passed, 0 skipped. `-rs` prints each skip's reason; a skip naming
"ACL2 bridge not available" means the bridge could not be reached.

## decide (formerly clausal-laya)

The package was renamed from `clausal-laya` to `clausal-decide` (PR #31):
the module is `py.decide`; the backend names `laya`, `laya_serve` and
`typesafe` are unchanged. The real tests are the `.seam` fixtures under
`packages/clausal-decide/tests/fixtures/` (`tests/conftest.py`). On first use
laya downloads its checkpoint from the Hugging Face Hub; the conftest probes
by loading the `english` model.

```bash
python -m pytest packages/clausal-decide -q -rs
```

Expect 48 passed, 0 skipped (the 13 model tests now run). If the model's
probabilities differ from the doc examples' expectations, the test names the
predicate and the values: report those. The examples come from laya's own
README, so a difference may be a laya version change rather than an adapter
bug.

## Not covered by any automated test

These need credentials or long runs. Try them by hand if you can:

- **Jev for real.** The `typesafe` backend's test drives the real SDK over a
  mock transport. With a key:
  ```bash
  export TYPESAFE_API_KEY=...
  ```
  then in a `.seam` or the REPL: `use_backend(typesafe)`, then a
  `choice/4` or `noul/3` call from `packages/clausal-decide/docs/decide.md`.
- **`finetune/5` end to end.** Its test uses a stand-in `laya.train`. A real
  run needs a base checkpoint, a few labelled rows and training time; then
  `register_model/2` and a `choice/4` against the new name.
- **`laya-serve`.** Tested against a local HTTP stand-in; a real
  `laya-serve` with `use_backend(laya_serve, [url(...)])` is a quick check.

## Done when

Both packages pass with no skips (or the remaining skips are understood and
noted here), and any Jev/fine-tuning/laya-serve results are recorded. Then
move this file to `todo/done/` with a status line.
