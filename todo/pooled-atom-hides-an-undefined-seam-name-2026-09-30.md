# A pooled atom hides an undefined name in a seam module (order-dependent)

Found 2026-09-30 while gating native-reader slice 3. Reproduced on f01790d2,
which has no slice 3 code.

Module dicts are seeded from the process-wide atom pool (`predicate_builtins`).
After ANY earlier module declares an atom `cite` (a seam `-private([cite])`, a
translated or native `.pl` that uses it), a later seam module that uses `cite`
without declaring or importing it no longer gets `NameError: name 'cite' is not
defined`:

- in a goal, `cite(X)` fails at load with `'str' object is not callable`
- as data, `{k: cite(a)}` raises `existence_error(procedure, cite/1)`

The sibling-export diagnostic is then lost.

Repro on base:

    printf -- "-private([cite])\nk(cite),\n" > /tmp/leak/leakcite.seam
    PYTHONPATH=.:/tmp/leak python -c "import clausal.import_hook, leakcite, pytest; \
      pytest.main(['-q', 'tests/test_undefined_name_sibling_diagnostic.py', \
                   'tests/test_catch_trampolined.py'])"
    # 6 failed; all pass when leakcite is not imported first

The strict-atom checks already guard this "leaked pool atom" shape for bare atoms and
dict keys (`compiler_v2._process_bare_atom_refs`, `import_hook._make_intern_atom`).
The call-position and functor-position resolution does not.

Since slice 3, a native `.pl` declares every atom it uses, as the translator already
did, so more spellings reach the pool. The slice-2 D11 test was renamed off `cite`
because of this. The engine fix belongs with the P3-1 leaked-pool guards.
