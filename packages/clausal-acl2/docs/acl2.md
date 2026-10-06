# acl2 — the ACL2 theorem prover from Clausal

[ACL2](https://www.cs.utexas.edu/~moore/acl2/) is a theorem prover for an
applicative subset of Common Lisp. The `acl2` module talks to a real ACL2
through the [ACL2 Bridge](https://www.cs.utexas.edu/~moore/acl2/manuals/current/manual/?topic=CENTAUR____BRIDGE)
(`books/centaur/bridge`), and Lisp forms and results cross as **Clausal
terms**: an ACL2 term is a Prolog compound.

```seam
--8<-- "tests/fixtures/docs/acl2_sigs.txt:import"
```

---

## Terms

Clausal's compound terms are functor-first tuples, which is what Lisp forms
are. Each ACL2 object has exactly one term:

| ACL2 | Clausal term |
|------|--------------|
| `FOO` (ACL2 package), `NIL`, `T` | the atoms `foo`, `nil`, `t` |
| `:FOO` | the atom `':foo'` |
| `PKG::FOO` | the atom `'pkg::foo'` |
| `|foo|` (a name with lowercase letters) | the atom `'|foo|'` |
| integer, rational | integer, rational |
| `#C(a b)` | `'$complex'(a, b)` |
| string | string |
| `#\a` | `'$char'(a)` |
| `(f a b ...)`, symbol head, 2+ items | the compound `f(a, b, ...)` |
| any other proper list: `(f)`, `(1 2)` | `'()'(...)`, the engine's tuple-data term |
| `(a . b)` | `'$cons'(a, b)` |

So `(implies (true-listp x) (equal (rev (rev x)) x))` is the term
`implies('true-listp'(x), equal(rev(rev(x)), x))`. A Clausal list `[a, b]`
crosses out as the Lisp list `(A B)` too; it comes back as the canonical term.

In the seam, ACL2 names used as data must be declared (`-private([...])`) like
any functor, and a name that is a Python keyword -- `if`, `and`, `or`, `not`
-- cannot be written as a functor at all. Write those forms as ACL2 text and
parse them with `acl2_text/2`.

---

## Evaluating: `acl2/2,3`, `acl2_mv/2`

```
--8<-- "tests/fixtures/docs/acl2_sigs.txt:acl2_sig"
```

`acl2/2` evaluates a form and answers its first value; `acl2/3` also answers
what ACL2 printed, as a string; `acl2_mv/2` answers every value as a list.

```seam
--8<-- "tests/fixtures/docs/acl2_examples.seam:evaluate"
```

---

## Proving: `event/1,2`, `thm/1,2`

```
--8<-- "tests/fixtures/docs/acl2_sigs.txt:event_sig"
```

`event/1` submits an event -- `defun`, `defthm`, `in-theory`, ... -- through
`ld`, in ACL2's main thread; it fails if ACL2 rejects the event. `thm/1`
proves a term and fails if ACL2 cannot. The `/2` forms also answer ACL2's
output (the proof, or why it failed). Events change the ACL2 session, as they
do at its prompt.

```seam
--8<-- "tests/fixtures/docs/acl2_examples.seam:prove"
```

---

## Text: `acl2_text/2`

```
--8<-- "tests/fixtures/docs/acl2_sigs.txt:text_sig"
```

A term and its ACL2 text, either way: with `Text` bound it parses it,
otherwise it prints `Term`. No bridge is needed.

---

## Which ACL2: `use_acl2/1`

```
--8<-- "tests/fixtures/docs/acl2_sigs.txt:use_sig"
```

| Option | Meaning |
|--------|---------|
| `socket` | a Unix socket where a bridge is running, `(bridge::start "<path>")` |
| `host`, `port` | a TCP bridge, `(bridge::start <port>)` (default port 55432) |
| `command` | start this ACL2 executable here (default `acl2`) |
| `timeout` | seconds to wait on a connection |
| `startup_timeout` | seconds to wait for a started ACL2's bridge (default 300) |

With no `use_acl2/1`, the first call starts `acl2` from PATH, loads
`centaur/bridge/top` (the books must be certified; on SBCL the bridge also
needs the Quicklisp libraries its book names) and serves the bridge on a
private Unix socket. Read the bridge's
[security notes](https://www.cs.utexas.edu/~moore/acl2/manuals/current/manual/?topic=BRIDGE____SECURITY)
before serving it on TCP.

---

## Errors

| Problem | Error |
|---------|-------|
| an unbound part of a form | `instantiation_error` |
| a term with no ACL2 object (a dict, a float) | `type_error(acl2_term, Culprit)` |
| no bridge answers | `existence_error(acl2_bridge, Where)` |
| ACL2 signals an error evaluating a form | `error(acl2_error(Message), Context)` |
| text that is not ACL2 syntax (`acl2_text/2`) | `syntax_error(acl2_text)` |
