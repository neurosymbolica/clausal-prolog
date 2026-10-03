# Changelog

All notable changes to Clausal are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). From 1.0.0 onwards
the project follows [semantic versioning](https://semver.org/) over the
surface described in [docs/public-api.md](docs/public-api.md).

## Unreleased (1.0.0)

This is the first release with a public-API promise. Most of the changes
since 0.4.0 finish three moves:

- Terms are plain Python values: an atom is a `str`, a compound is a tuple
  `(functor, *args)` (a "cell"), and a string is the carrier
  `('$chars', text)`. There is no compound class any more.
- A predicate is a row in its module's database, named by a handle. It is
  no longer a Python class.
- The language moves towards ISO Prolog: the ISO builtin names, ISO error
  terms, and `"…"` as a string by default.

### Breaking

- **Clausal Prolog may not reach a `.pl` module at run time either**
  (the dialect gate, routes 2-7 of the 2026-10-01 one-way ruling; route 1,
  the import, landed earlier). From a `.clausal` clause, a qualified goal
  `M:G` -- written in the clause, or built at run time and run by
  `call/N`, `maplist/N`, `findall/3`, a body term -- `assertz/asserta/
  retract/retractall(M:C)`, `clause(M:H, B)` and `phrase(M:NT, L)` whose
  module `M` (the innermost) is a `.pl` module raise
  `error(permission_error(access, prolog_module, M), Context)`, the term
  route 1 raises; a Python module `M` raises `permission_error(access,
  python_module, M)`. **Strict for closures too:** a `.pl` caller's
  closure handed to a Clausal Prolog `-meta_predicate` arrives as
  `pl_module:G` and is refused when the Clausal Prolog code runs it -- the
  one place the rule bites the allowed direction. `.pl` and `.seam`
  callers are unaffected (`.seam` is the Python boundary), and so is
  Python-side `solve()`. A run-time `M:G` from Clausal Prolog into a `.pl`
  module some other code loaded used to run.
- **Input text an adapter cannot read raises `syntax_error(Kind)`**
  (ruled 2026-10-02) instead of failing the goal or raising a
  `domain_error`. Text that does not PARSE -- `py.json` `parse/2,3` and
  `read_file/2` (`syntax_error(invalid_json)`; a file that is not UTF-8
  `syntax_error(invalid_data)`; both were `domain_error(json_text, S)` /
  `domain_error(json_file, P)`), `py.datetime` `datetime_string/3`,
  `datetime_string_iso/2` (`invalid_datetime`) and `date_string_iso/2`
  (`invalid_date`; were `domain_error(datetime_text | iso_datetime |
  iso_date, S)`), `py.url` `parse/2` and the `py.http` predicates on a URL
  that does not parse (an unclosed IPv6 bracket, a port that is not a
  number: `invalid_url`; was `domain_error(url, U)`), `py.uuid`
  `uuid_str/2`, `uuid_hex/2`, `uuid_urn/2` (`invalid_uuid`; was
  `domain_error(uuid_text | uuid_hex | uuid_urn, S)`). Text that parses but
  names no value -- a 30th of February, a month 13, a port of 99999 --
  keeps its `domain_error`. `py.http`: a response
  body that is not UTF-8 is `error(syntax_error(invalid_data), Name/Arity)`
  -- Scryer's term for bytes that are not UTF-8 on a text stream -- in
  `get/2,3`, `post/3,4`, `json_get/2`, `json_post/3` and `request/3`
  (whatever the status: `request/3` used to read an undecodable error body
  as `""`); a body `json_get/2` or `json_post/3` cannot parse is
  `syntax_error(invalid_json)`. An error status still comes first in the
  body-only predicates. A failed read of an error body now raises the
  network error in `request/3` (it read as `""`). The `clausal-yaml`
  package: text that is not YAML (`Read/2`, `ReadAll/2`, `ReadFile/2`) is
  `syntax_error(invalid_yaml)`; a file-system failure in `ReadFile/2` and
  `WriteFile/2` goes through the shared ISO mapping, as in `py.files`
  (`existence_error(source_sink, Path)`, `permission_error(open,
  source_sink, Path)`, ...); an object YAML cannot represent (`write/2`,
  `WriteAll/2`, `WriteFile/2`) is `type_error(yaml_term, Culprit)`, as in
  `py.json`. A YAML file that is not UTF-8 is
  `syntax_error(invalid_data)`. `WriteFile/2` serialises before it opens
  the file, so a bad term leaves no file. A path must be text, as in
  `py.json` (`instantiation_error` / `type_error(text, P)`; it was `str()`
  of the term), and files are read and written as UTF-8. The package's
  predicates are renamed to lower_snake_case, with no aliases (a TitleCase
  name no longer loads): `Read/2` -> `read/2`, `ReadAll/2` -> `read_all/2`,
  `ReadFile/2` -> `read_file/2`, `WriteAll/2` -> `write_all/2`,
  `WriteFile/2` -> `write_file/2`, `Get/3` -> `get/3`. `read/2` and
  `read_all/2` take text (`instantiation_error` / `type_error(text, X)`
  otherwise; a string was parsed as its Python repr), and `get/3` matches a
  string key written in source.
- **The `clausal-scipy`, `clausal-sklearn`, `clausal-sympy` and `clausal-spacy`
  optional packages rename their TitleCase predicates to lower_snake_case**
  (e.g. `Simplify` -> `simplify`, `KMeans` -> `k_means`, `Erf` -> `erf`).
  These names were registered from Python (`ModulePredicate("Name")` /
  `_pred("Name", ...)` / `_pred_bidir("Name", ...)` / `X._register(...)`),
  so the engine's TitleCase lint never saw them at load time, and Clausal
  code could not call them by name -- a TitleCase name in functor position
  is a load-time error. Acronyms collapse to one lowercase word (`FFT` ->
  `fft`, `SVD` -> `svd`). `sympy.Inf` (arity 1) is removed outright (ruled
  2026-10-02): the module's existing `inf` value (`= sympy.oo`) already
  covers it, and the predicate just unified a result with the same value.
  `sympy.ToSympy` / `sympy.FromSympy` are MERGED into one relation,
  **`sympy_term(Sympy, Term)`** (ruled 2026-10-02; neither old name
  survives and there is no alias): an ISO-`atom_codes/2`-style mode
  switch on which argument is bound, with `instantiation_error` /
  `type_error(sympy_expression, _)` / `type_error(clausal_term, _)` for
  the ill-moded and conversion-failure cases (replacing what used to be
  a silent failure). It is not a true bijection -- SymPy canonicalises on
  construction (`X+X` -> `2*X`), so `Term -> Sympy -> Term` returns an
  equivalent term, not necessarily the same one -- but a Clausal variable
  DOES round-trip exactly across two separate calls, and two distinct
  variables never collapse onto one SymPy symbol; see `docs/sympy.md`.
  Full per-package rename tables are in each package's `docs/RENAMES.md`.

- **A file-system or network failure in a library adapter raises an ISO
  error** (ruled 2026-10-02) instead of failing the goal. The model is ISO
  `open/4` (8.11.5.3 j, k): a path that does not exist (or goes through a
  file) is `error(existence_error(source_sink, Path), Name/Arity)`; a path
  that exists but may not be used -- no permission, a read-only file
  system, a directory where a file is needed (EISDIR) or an existing file
  where a directory is needed (ENOTDIR), a name already taken (EEXIST), a
  directory not empty -- is `permission_error(Action, source_sink, Path)`,
  `Action` being `open` to read, write or list, `modify` to delete or
  rename, `create` to make a directory or temporary file. Too many open
  files is `resource_error(file_descriptors)` (Scryer's term), a full disk
  `resource_error(disk_space)`; any other errno `system_error(E)`, E its
  lower-case symbolic name (`exdev`). Covered: `py.files` `directory_files/2`,
  `directory_entries/2`, `file_size/2`, `file_modification_time/2`,
  `delete_file/1`, `delete_directory/1`, `rename_file/2`, `copy_file/2`,
  `make_directory/1` (an existing path: `permission_error(create, ...)`),
  `make_directory_path/1`, `read_file_to_string/2`, `write_string_to_file/2`,
  `append_string_to_file/2`, `temp_file/1`, `temp_directory/1`; `py.os`
  `change_directory/1`; `py.csv` and `py.json` `read_file/2`,
  `read_records/2`, `write_file/2`; `py.logging` `file_handler/2` and
  `py.sqlite` `connect/2` (both escaped as a raw Python error);
  `reified_file_item/2` on a directory or an unreadable file (a raw Python
  error; a missing file was already `existence_error`). ISO has no network
  error, and Scryer's `socket_client_open/3` and `http_open/3` fail on
  everything but NotFound (`existence_error(source_sink, Host)`) and
  PermissionDenied (`permission_error(open, source_sink, Host)`), so those
  two terms are Scryer's and the rest the engine's own: in `py.tcp`
  (`connect/3`, `listen/3`, `accept/2`, `send/2`, `receive/2,3`) and
  `py.http` (`get/2,3`, `post/3,4`, `request/3`, `json_get/2`,
  `json_post/3`) a host that does not resolve is
  `existence_error(source_sink, Host)` (the URL in `py.http`), another DNS
  failure `system_error(host_lookup_failed)`, a refused, reset or aborted
  connection `system_error(connection_refused | connection_reset |
  connection_aborted)`, `system_error(broken_pipe)`,
  `system_error(host_unreachable | network_unreachable)`, a port in use
  `system_error(address_in_use)`, a timeout `resource_error(timeout)`, a
  TLS failure `system_error(tls_failure)`, a malformed HTTP response
  `system_error(http_protocol_error)`. An HTTP error status raises in the
  predicates that answer a body alone (`get`, `post`, `json_get`,
  `json_post`): 404 and 410 are `existence_error(source_sink, Url)`, 401,
  403 and 407 `permission_error(open, source_sink, Url)`, any other status
  `system_error(http_status(S))`; `request/3` still answers the status as a
  value, as Scryer's `http_open/3` does. In `py.process` a program that does
  not exist is `existence_error(source_sink, Program)`, one that may not be
  executed `permission_error(create, process, Program)` (Scryer's
  `process_create/3` term), a missing `cwd` `existence_error(source_sink,
  Cwd)`; an exit status stays a value (`shell/2`, `process_create/3,4`), and
  `shell/1`, `shell_output/2,3` still fail on a nonzero one. A
  `process_create/4` timeout now SUCCEEDS with `exit_code` the atom
  `timeout` (Scryer's `process_wait/3` status) where it failed. Unchanged,
  because their failure is the answer: `file_exists/1`,
  `directory_exists/1`, `path_exists/1` (now `false` too for a path the
  process may not look at, where an EACCES escaped as a raw Python error),
  `environment_variable/2` for an unset name, `receive/2,3` at end of
  stream, `close/1`. The shared mapping is `raise_os_error` /
  `os_error_term` in `clausal.modules.py`. Wrap a call in `catch/3` where a
  caller wants the old failure.
- **A library adapter given a right-typed value it rejects raises
  `domain_error`** (ruled 2026-10-02) instead of failing the goal with a
  diagnostic note: `error(domain_error(Domain, Culprit), Name/Arity)`, the
  culprit being the term as written, the domain ISO's name where ISO has one
  (`not_less_than_zero`) and the adapter's own otherwise. In `py.*`:
  `hash/3`, `hash_bytes/3`, `sign/4`, `verify/4` with an unknown algorithm
  or `shake_*` → `domain_error(hash_algorithm, A)`; `derive/4,5` with
  iterations or key length <= 0 → `domain_error(positive_integer, N)`;
  (`py.json` malformed text: see the `syntax_error` entry above);
  `time/4` hour 25 → `domain_error(time, time(25, 0, 0))`, `datetime/7`
  month 13 or day 32 → `domain_error(datetime, datetime(...))`,
  `timedelta/3` past ±999999999 days → `domain_error(timedelta, ...)`;
  `ordinal/2` outside 1..3652059 → `domain_error(ordinal, N)`;
  `datetime_string/3` on text that parses but names no datetime →
  `domain_error(datetime_text, S)`, a bad format →
  `domain_error(datetime_format, F)`; `datetime_string_iso/2`,
  `date_string_iso/2` on such text → `domain_error(iso_datetime, S)`,
  `domain_error(iso_date, S)` (text that does not parse:
  `syntax_error`, above); `timestamp/2` out of range or NaN →
  `domain_error(timestamp, X)`; `py.http` `get`, `post`, `request`,
  `json_get`, `json_post` with a URL urllib cannot use (no or unknown
  scheme, no host) → `domain_error(url, U)`, and
  `request/3` with no `url` key → `domain_error(http_request_options,
  Opts)`, a negative timeout → `domain_error(not_less_than_zero, T)`, a
  non-number timeout or non-dict headers → `type_error` (both were ignored);
  `py.url` `parse/2` with a port out of range → `domain_error(url, U)`;
  `uuid_bytes/2`, `uuid_int/2` → `domain_error(uuid_bytes | uuid_int, X)`
  (`uuid_str/2`, `uuid_hex/2`, `uuid_urn/2` on text that is not a UUID:
  `syntax_error`, above); `generate_records/3`
  with a record key the headers lack → `domain_error(csv_record, R)`;
  `sample/3` with a negative size → `domain_error(not_less_than_zero, N)`;
  `maybe/1` outside 0..1 → `domain_error(probability, P)`.
  A plain date mixed with a datetime in `date_max/3`, `date_min/3`,
  `date_diff/3`, `days_between/3`, `date_between/3` is
  `type_error(date, DT)` / `type_error(datetime, D)` on the second argument
  (the first fixes the type; no value of the other type answers); a naive
  mixed with an aware datetime is `domain_error(naive_datetime, DT)` /
  `domain_error(aware_datetime, DT)`. `date_add/3`, `date_sub/3` past years
  1..9999 raise `representation_error(date)`. JSON generation
  (`generate/2`, `pretty_generate/2`, `write_file/2`, `json_post/3`) writes
  a decimal as its exact digits (`0.10` stays `0.10`) and an integral
  rational as its integer -- both used to fail; bytes, a non-integral
  rational or a NaN/infinite decimal is `type_error(json_term, X)` (as a
  compound already was) and a nested unbound variable is
  `instantiation_error`; `write_file/2` (JSON and CSV) checks before it opens
  the file, so a bad term leaves no truncated file. CSV `generate/2`,
  `write_file/2` with an unbound cell and `set_seed/1` with an unbound seed
  are `instantiation_error`, as is `generate_records/3` with an unbound
  record value (it wrote the variable's name); `set_seed/1` with a seed
  that is not a number, text or bytes is `type_error(number, S)`.
  The non-`py` adapters follow the same rules: `graphs` (every predicate
  taking an edge list: an unbound or non-list Edges, an unbound node, start
  or end, and `path_cost/3`'s path; `shortest_path/4` with a negative weight
  is `domain_error(not_less_than_zero, W)`), `currency` (`money/3`,
  `money_precise/3`, `currency_scale/2`, `currency_symbol/2`,
  `currency_start/2`, `currency_end/2`, `currency_code/2` forward,
  `money_round/3`, `money_str/3`, `money_format/4`: `type_error(currency |
  quantity | text, X)`, `domain_error(money | rounding_mode | money_style,
  X)`), `units` (`strip_units/2`, `dimension_of/2`: a bare number is a
  dimensionless quantity -- `dimension_of(42, D)` gives `D = {}` and
  `strip_units(42, V)` gives `V = 42`, where both used to fail -- and
  anything else that is not a quantity is `type_error(quantity, X)`;
  `make_quantity/3`) and
  `reflection` (`reified_item/2`, `reified_clause/2`,
  `reified_file_item/2`: `type_error(text, S)`; a missing file is
  `existence_error(source_sink, Path)`).
  Still a plain failure, because it is a legitimate "no": an empty range,
  a sample larger than its list, no path in a graph, an unknown currency code in
  `currency_code(-C, +Code)`. The diagnostic-note machinery
  (`note_mismatch`, `note_rejected_call`, `collect_type_mismatch_notes`,
  `value_is_ground` in `clausal.modules.py`) is removed: nothing fails
  silently for it to explain. Wrap a call in `catch/3` where a caller wants
  the old failure.
- **A `py.*` wrapper given an argument of the wrong type raises** (ruled
  2026-10-02) instead of failing the goal. `date_add(90, TD, R)` is
  `error(type_error(date, 90), date_add/3)`, `sleep(abc)` is
  `type_error(number, abc)`, a non-text path, URL or command is
  `type_error(text, Culprit)`, and an unbound input the call needs (both
  arguments of a bidirectional conversion, `date_add(D, TD, R)` with `TD`
  unbound, `read_file(P, T)` with `P` unbound) is `instantiation_error`.
  Type names are ISO's where ISO has one (`integer`, `number`, `list`) and
  the wrapper's own otherwise (`text`, `date`, `datetime`, `time`,
  `timedelta`, `uuid`, `dict`, `socket`). This covers every wrapper in
  `clausal.modules.py` (`csv`, `datetime`, `files`, `hash`, `hmac`, `http`,
  `json`, `os`, `pbkdf2`, `process`, `random`, `re`, `tcp`, `url`, `uuid`):
  the shared `expect_type`/`require_text` checks raise, and the wrappers'
  own `is_var -> fail` and `int()`/`float()`-coercion paths go through
  them. Also: a bool is no longer accepted as an integer or a number
  (`true` is an atom); `integer_between/3` no longer truncates a float or
  parses an atom spelled as a digit; `time/4` and `datetime/7` with a float
  component raise `type_error(integer, F)` as `date/3` already did;
  `http:post/3,4` with non-text data raises instead of sending a body-less
  POST; `uuid_v3/3`, `uuid_v5/3` with an unknown namespace alias raise
  `domain_error(uuid_namespace, Ns)`; `timedelta/3` accepts a rational or
  decimal day count (as its float) instead of refusing it. A right-typed
  value the library rejects raises too: see the next entry. Wrap the call
  in `catch/3` where a caller wants the old failure.
- **`.clausal` is now Clausal Prolog; seam source is `.seam`** (the
  extension flip). A `.clausal` file is read as cut-free, ISO-like Prolog
  by the native front end, whatever `CLAUSAL_PL_FRONTEND` says: `!`,
  `->` and `*->` are refused, a module file must end with
  `:- end_module(Name).`, and it may not import a `.pl` module. Seam
  (Python-syntax) source must be named `.seam`; a seam file left as
  `.clausal` now fails to load with a Prolog syntax error. Every seam file
  in this repository (stdlib, examples, rewrite rules, tests, packages) is
  renamed. In one directory `name.seam` beats `name.clausal`, which beats
  `name.pl`, for any importer. `clausal-fmt` and `clausal-rewrite` take
  `.seam` and refuse `.clausal`. The test runner, the doc checks and the
  diagnostics follow; its messages read ".seam, .clausal or .pl".
  **Migrate:** `git mv name.clausal name.seam` for each seam file (MOVE,
  never copy: a stale `name.clausal` beside `name.seam` is now a different,
  Prolog, module), and update any glob or path that names `*.clausal`.
  Bytecode caches need no action (a `.clausal` file has its own cache key).

- **The seam's `if_/3` requires a reifiable condition** (ruled
  2026-10-01), as Scryer's library(reif) does and as the native `.pl` front
  end already did. The condition is a reified comparison (`X is Y`,
  `X is not Y`, `==`, `!=`, `<`, `<=`, `>`, `>=`), a conjunction or
  disjunction of them, or a closure called with the truth value appended:
  `if_(memberd_t(X, Es), ...)` runs `memberd_t(X, Es, T)`,
  `must_be(boolean, T)` and branches on `T`. Every way the closure answers
  is a solution, so `if_(memberd_t(X, [a, b]), R is yes, R is no)` gives
  `a-yes`, `b-yes` and `dif`-constrained `X` with `no`, as Scryer does. A
  plain goal as the condition (`if_(atom(X), ...)`, `if_(p(X), ...)` with no
  `p/2`, `not G`, `X in L`, `once(G)`, `True`) is now a load-time
  `SyntaxError` (`NonReifiableConditionError`) naming the predicate and line
  and the reified form to write. It used to run as a soft cut (every
  solution of the condition, the else branch only when there were none),
  which is not monotone; that lowering, and its tabled-NAF variant, are
  removed. In a DCG or EDCG body the condition must be a `{Goal}` block (a
  terminal, non-terminal or accumulator push as the condition is refused).
  A unification with a partial list (`if_(X is [a, *T], ...)`, and a `.pl`
  `if_(X = [a|T], ...)`) is reif's `=/3` and answers as Scryer does (`y`
  and `n` for an unbound or `[a, b]` `X`).
  To migrate a semidet plain goal G, write
  `(G, Then) or (not G, Else)`, or define the reified `p_t/2`. call/1 of an
  `if_` term follows the same rule.
- **An unknown `library(X)` is refused by the translator `.pl` front end
  too** (ruled 2026-10-01), with the native front end's error:
  `library(X) is not a library the native front end knows (built in: ...;
  mapped: ...; facades: ...)`, a load-time `SyntaxError` naming the line.
  The translator used to read an unknown library name as a module of that
  name, so `library(os)`, `library(math)`, `library(random)` or
  `library(time)` silently imported Python's standard-library module, and
  a list naming only engine builtins (`library(charsio), [atom_chars/2]`)
  was dropped as a no-op. Known libraries -- built in, mapped
  (`clpz`, `clpb`, ...), the `library(...)` facades and `py_*` -- are
  unchanged.

- **A cut inside a meta-called body is refused, never run as `true`.**
  Clausal has no cut. A clause body cannot spell `!`, but a goal built at
  run time could carry one into `call/N`, and `call/1` ran it as `true`:
  `call((p(X), !))` gave every `p` answer where ISO and Scryer give the
  first. The same happened in `findall`, `forall`, `\+`, `once`, `catch`
  and `aggregate_all` bodies, which all reach their goals through `call/1`.
  A `!` that is a leaf inside a body term now raises
  `error(existence_error(procedure, !/0), !/0)`. This is the error `->` and
  `*->` already raise at run time, and the one an ISO system gives for a
  construct it does not provide. The refused placements include `(G, !)`,
  `(!, G)`, `(G ; !)`, `\+ (G, !)` and `findall(X, (p(X), !), L)`. The
  whole body is refused before it runs. Inside a `phrase/2,3` body, `!` is
  now read as ISO's `!, S0 = S` and gets the same refusal. It used to be
  called as the nonterminal `!/2`.

  A cut that is the WHOLE goal of a call is unchanged: `call(!)`, `\+ !`,
  `findall(X, !, L)`, and `call(V)` with `V` bound to `!` all still run it
  as `true`. ISO 7.8.3 makes such a cut local to the call, so it has
  nothing to cut and `true` is the ISO answer.
- **`assertz/1` and `asserta/1` refuse a control construct as a clause
  head**, as ISO 8.9.1.3 and Scryer do. The error is
  `permission_error(modify, static_procedure, PI)`: `assertz(!)` is `!/0`
  and `assertz((a, b))` is `','/2`. `assertz(!)` used to store a fact `!/0`,
  and a later `solve("!")` then succeeded through that fact. `retract/1`
  already refused these heads.

- **Calling a qualified goal whose module argument is unbound or not an
  atom raises Scryer's error** (ruled 2026-10-01). `call(7:foo)` is
  `error(type_error(atom, 7), call/0)` and `call(_:foo)` is
  `error(instantiation_error, call/0)`; both raised
  `existence_error(module, …)`. The context is `call/N` with N = the goal's
  arity plus call/N's extras, as Scryer reports it (`call(7:foo, x)` is
  `call/1`). With an unbound or non-callable goal the whole term is refused:
  `call(7:_)` is `type_error(callable, 7:_)` at `call/1`, and
  `phrase(7:g, L)` is `type_error(callable, 7:g(L, []))` at `call/1`. This
  holds for call/N, findall/3, `\+`, phrase/2,3, `solve`, seam `':'`, and a
  body goal: the native `.pl` front end no longer refuses `M:foo` /
  `7:foo` in a body at load, it calls the term at run time. Asserting into,
  or looking up clauses in, `M:`, a missing OUTER atom module
  (`nosuchmod:m2:G`) and `module=` arguments keep `existence_error(module,
  …)`.
- **Importing an unexported `.pl` predicate in Clausal code is an error**
  (ruled 2026-10-01). A seam `-import_from(m, [p])` (also `[p/N]` and
  `[alias(p, q)]`) or a `.pl` `:- use_module(m, [p/N])` naming a predicate
  that the `.pl` module `m` defines but does not export raises
  `ImportError` with `permission_error(access, private_procedure, p/N)` at
  load time, under both front ends; it silently imported the predicate.
  A `.pl` file with no `module/2` directive exports everything. Scryer
  accepts such a `use_module` silently and imports nothing (the call then
  raises `existence_error(procedure, p/N)`); the error term is provisional.
- **In Python code, `from plmod import name` is `getattr`** (ruled
  2026-10-01: in Python code, Python semantics apply). For an unbound
  atom-shaped name of a module loaded from `.pl` it now gives the atom,
  like `plmod.name`; it raised `ImportError`. A real submodule still
  imports (`from pkg import sub`); an atom-shaped name that is no
  submodule gives the atom (`from pkg import nosuchsub` is `'nosuchsub'`).
  In Clausal code the statement keeps the seam `-import_from` rules.

- **Attribute access on a `.pl` module answers an unbound data name with
  its atom** (ruled 2026-10-01, extending the `.pl` data-import ruling).
  `getattr(mod, 'employment')` / `mod.employment` on a module loaded from
  `.pl` (either front end, a package's `__init__.pl` included), for a name
  the module neither defines as a predicate (any arity) nor binds, is the
  atom `'employment'`; it raised `AttributeError`. Only an atom-shaped name
  is answered (`iso_l3_directives._is_declarable`: a lowercase identifier,
  no keyword, no reserved name), so dunder, private, TitleCase and
  non-identifier names still raise, and an unimported submodule of a `.pl`
  package is not data. `from mod import name`, the engine's own probes and
  `.clausal`/`.seam`/Python modules are unchanged. A near miss of a
  predicate warns once per module and name
  (`ClausalImportedDataNameWarning`). **`getattr`/`hasattr` on a `.pl`
  module no longer signals absence; use `clausal.has_predicate` /
  `clausal.defines_predicate` / `clausal.module_binds`.** A PEP 562 `__getattr__`
  (`pl_data_imports.install_attribute_fallback`) installed when the module
  has loaded.
- **Calling into a module that does not exist is
  `existence_error(procedure, Name/Arity)`** (ruled 2026-09-30; Scryer's
  form). `call(nosuchmod:mp(_))` in `.pl`, `call(':'(nosuchmod, mp(X)))`
  and `':'('nosuchmod', mp(X))` in seam, `solve((":", "nosuchmod", G), m)`
  and `findall`/`call/N`/`phrase` over them raise
  `error(existence_error(procedure, mp/1), mp/1)`; call/N counts its extra
  arguments (`call(nosuchmod:mp, X)` is `mp/1`; `phrase(nosuchmod:g, L)`
  is `g/2`). They raised
  `error(existence_error(module, 'nosuchmod'), call/1)`. The change is in
  the one resolver of qualified goals (`cells.resolve_qualified_goal_cell`),
  for its calling callers only; a non-atom designator (`7:G`), an unbound
  or non-callable goal, a control construct, a missing OUTER module of
  `m1:m2:G`, and `assertz`/`retract`/`clause` into `nosuchmod:` keep
  `existence_error(module, ...)`, as does `end_module/1`'s mismatch error.

- **An unterminated `/*` block comment is a syntax error** (ruled
  2026-09-30; ISO, as Scryer's `syntax_error(incomplete_reduction)`). Both
  toklex lexers used to end an unclosed comment silently at end of input,
  so everything after the `/*` vanished without a trace. Now the lexer
  emits an `unterminated` error token from the outermost opener: the
  reader returns a `resumable=False` `SyntaxIssue` after the items before
  it, `tokenize()` raises `TokenizeError` at the opener, and a `.pl` file
  ending in one fails to load under either front end (the native loader
  names the opener's line).
- **Block comments in `.pl` source do not nest** (ISO, as Scryer). Both
  `.pl` front ends read with `nested_comments=False`
  (`prolog_tokenizer.PL_SOURCE_NESTED_COMMENTS`): `/*` closes at the first
  `*/`, and only end of input before any `*/` is the unterminated error.
  `/* outer /* inner */` followed by clauses now loads, and
  `/* outer /* inner */ still */` is a syntax error (` still */` is code).
  Both used to go the other way. `PrologReader`, `read_module()`,
  `tokenize()` and `parse()` keep a `nested_comments` parameter; their
  default (nesting on) is unchanged.

- **`arg/3` with an unbound `N` raises `instantiation_error`** (ISO 8.5.2.3,
  as Scryer). It used to enumerate the `(N, Arg)` pairs, SWI's extension.
- **The clpz `#` family refuses a non-arithmetic operand.** `'#='`, `'#\='`,
  `'#<'`, `'#>'`, `'#=<'` and `'#>='` raise clpz's
  `domain_error(clpz_expression, Culprit)` for an atom, a string, a list, a
  compound that is not evaluable, or a Python `bool` anywhere in an operand
  (Scryer's clpz treats the atom `true` the same). A ground one used to fail
  (`'#='(1, foo)`), succeed (`'#\='(1, foo)`), raise
  `type_error(orderable, foo)` (`'#<'`), or count a bool as 0/1. Floats are
  unchanged. Infix `==` is unchanged.
- **`number_chars/2` and `number_codes/2` read their text as Scryer does**
  (ISO 8.16.7) and raise `syntax_error(unexpected_end_of_file)` or
  `syntax_error(unexpected_char)` for text that is not a number. They used to
  parse it with Python's `int()`/`float()` and fail, accepting `"1 "`,
  `"+1"`, `"1e5"` and `"inf"` besides; `"0x1A"` and `"0'a"` now read. With
  both arguments bound the text is read (`number_chars(1, ['0', '1'])`
  holds), and a float's text always carries its fraction (`1.0e+22`), so it
  reads back. `atom_number/2` still fails on a non-number, as Scryer's
  library does.
- **A bare `/` in evaluation is Python's true division.** In `eval_/2`,
  `'is'/2` and the ISO comparisons, `7 / 2` is 3.5 and `6 / 2` is 3.0 (a
  float for two integers); a `Fraction` or `Decimal` operand stays exact, as
  in Python. Write `rdiv(7, 2)` for the exact rational 7/2. Inside a
  constraint (`==`, `!=`, `<`, ...) `/` stays rational. See
  [docs/operators.md](docs/operators.md).
- **Bare operators keep Python's meaning; quoted ones follow Scryer.** In
  `.clausal`/`.seam` source, clause bodies and `--` expressions alike,
  `-7 // 2` is -4 and `2 ** 3` is the integer 8. A quoted or runtime-built
  cell follows Scryer and ISO: `'//'(-7, 2)` truncates to -3, `'**'(2, 3)`
  is the float 8.0, `'/'(7, 2)` is 3.5.
- **A zero divisor is ISO's `evaluation_error(zero_divisor)`** in plain
  arithmetic on every spelling (`eval_(1 // 0, X)` raises
  `error(evaluation_error(zero_divisor), (//)/2)`), never a raw Python
  `ZeroDivisionError`. Inside a constraint it **fails** instead, in every
  goal order: `X == 1 // 0` has no solutions, as in Scryer.
- **A non-arithmetic term in an arithmetic constraint** raises Scryer's
  clpz error: `X == foo(1)` raises
  `error(domain_error(clpz_expression, foo(1)), (==)/2)`.
- **Error terms are Scryer's, and are plain cells.** An error is
  `error(Formal, Culprit)`, where `Culprit` is the culprit's predicate
  indicator (`atom_length/2`) or an unbound variable. The explanatory prose
  that used to sit in the second argument is now `LogicException.message`,
  printed after the term. A catcher that matched on the old context text
  must match on the indicator, or on `_`. Read an error term from Python
  with `cell_functor` / `cell_args`.
- **`Compound` and `KWTerm` are gone.** A compound term is always the plain
  cell `(functor, *args)`; see Removed.
- **The dynamic database is declare-first.** `assertz/1` and its kin add
  clauses only to a predicate declared `-dynamic`; asserting into any other
  predicate raises `permission_error(modify, static_procedure, Name/Arity)`.
- **`eval_/2` is stricter.** It now evaluates an operand bound in a
  variable, raises `type_error(evaluable, Name/Arity)` for a compound that
  is not arithmetic, and raises `instantiation_error` for an unbound
  operand. A Python `str` reached through a variable is an atom there and
  raises; write `X is ++(expr)` to evaluate Python.
- **A pair is `Key-Value`, as in Scryer's `library(pairs)`.**
  `pairs_keys_values/3`, `pairs_keys/2`, `pairs_values/2` and
  `group_pairs_by_key/2` take and build `'-'(K, V)` pairs instead of
  `[K, V]` lists (a `[K, V]` element now fails), and follow Scryer's
  definitions in every mode. `group_pairs_by_key/2` groups only ADJACENT
  pairs with identical keys and returns `K-Values` groups: sort first to
  collect every occurrence of a key. See [docs/pairs.md](docs/pairs.md).
  `dict_pairs/2`, `dict_put_pairs/3` and `zip_/3` use the same `'-'(K, V)`
  pairs (a `[K, V]` element now fails).
- **foldl/4 backtracks into every call**, as maplist does (it committed to
  each call's first solution), and maplist, foldl and the `X in L` goal
  enumerate an OPEN list as the ISO prologue's definitions do.
- **`call(Y^G)` is `existence_error(procedure, (^)/2)`**, as in ISO and
  Scryer (it was `type_error(callable, ...)`); bagof/setof still read `^`.
- **`clausal.__all__` is smaller.** `make_predicate` and
  `MakePredicateRetiredError` are gone. `Database`, `Clause`,
  `structural_unify` and `get_builtin_class` are internal and no longer
  listed (they stay attributes of `clausal`). The builtin objects whose names
  are not Python identifiers (`'#='`, `'=..'`, `'@<'`, `is`, …) and the
  dotted solver predicates (`z3.*`, `clpq.*`, `ortools.*`, …) are no longer
  listed either. They stay attributes of `clausal` and callable from
  `.clausal` source; only `from clausal import *` stops binding them.
- **At the 1.0 release, the packages under `packages/` pin an exact Clausal
  minor** (`clausal>=1.0,<1.1`), because some of them use internal helpers.
- **An atom is a Python `str`, and a string is the carrier
  `('$chars', text)`.** Answers, `++` arguments and the converters all follow
  this. The 1-tuple `('x',)` is reserved.
- **`"…"` is a string (a char list) by default**, as in Scryer and Trealla.
  A module that relied on the old atom reading needs `'…'` for its symbols,
  or `-double_quotes(atom)` as a stop-gap.
- **A module attribute for a predicate is the predicate's handle** (a `str`),
  not a callable class. `m.pred(X)` no longer runs anything. Write
  `solve(("pred", X), module=m)`.
- **Predicates defined as Python classes are gone.** `PredicateMeta` and
  `make_predicate` have been deleted, and a Python-made predicate class is
  refused at load. Implement `_get_dispatch()` instead (see the public API).
- **Goal-position `--` seams hand back raw terms** (the "dumb seam"). An
  atom comes back as its `str`, a string as its carrier, a compound as its
  cell. `++` passes values in unconverted. Convert with `to_python` /
  `to_clausal` where you need a Python value.
- **Name classes:** a name with a capital initial is a logic variable, and a
  TitleCase name used as a functor is a load-time error. The SI unit names
  are now lowercase, and the old spellings are warned aliases.
- **Keyword-argument terms** (`point(x=1, y=2)`) are refused at load. Build
  terms positionally.
- **No implicit arity padding:** a term is built at the arity it is written
  with, and a partial keyword-only construction is refused.
- **Constants were respelled** as the `-constant_value(name, value)` family.
  A bare name is the atom, and `constant(name)` retrieves the value.
- **`q(...)` quasi-quotation is retired.** `q` is an ordinary name.
  `ClausalRetiredQuasiQuoteWarning` flags old `term_expansion/4` rules that
  still use it.
- **ISO behaviour at the call boundary:**
    - A direct call to an unknown procedure raises
      `existence_error(procedure, Name/Arity)`.
    - `call/N` runs `findall`, `once`, `catch` and module-qualified cells.
    - A call at a different arity resolves under the name it used.
- **Module rules:**
    - A load may not add clauses to another module's predicate.
    - An imported name that clashes with a local definition is refused.
    - `-import_from` binds the names it lists, not the module.
- **Arithmetic is exact where it can be:** `Decimal` is a number, `+ - *`
  stay exact, `rdiv` and `/` inside a constraint are rational, an integral
  rational is presented as an `int`, and a float mixed with a `Decimal`
  raises.
- **Standard order:** `Quantity` sorts in the number band. `sort/2` no longer
  treats `1`, `1.0` and an equal `Decimal` as duplicates, and it no longer
  crashes on mixed units.
- **`sort/2`, `msort/2` and `compare/3` agree with `term_key`.**
- **The bytecode cache is keyed by an engine fingerprint.** Caches from
  earlier versions are ignored and rebuilt.
- **An empty test run fails.** `python -m clausal.testing` exits 5 ("no
  tests collected", pytest's number) when it collects no `test/1` clause; it
  exited 0. Pass `--allow-empty` when an empty run is expected. `--strict`
  is now the default and changes nothing. See [docs/testing.md](docs/testing.md).

### Added

- **DCG grammar rules in the native `.pl` front end** (and so in Clausal
  Prolog). A `-->` rule used to be refused at load ("DCG is out of
  scope"). It is now translated to the clause ISO 7.14 / Scryer's
  `library(dcgs)` give it -- terminal lists and `"..."` per the
  `double_quotes` flag, nonterminals, `,`, `;`, `|`, `{G}`, `call//N`, a
  variable body, `M:NT` and pushback (`H, PB --> B`) -- and loaded as that
  clause, so `phrase/2,3` (with the rest) answer as Scryer's, and
  nonterminals export and import as `name//N`. `!`, `->` and `{!}` in a
  grammar body are refused with the clause-body refusal (cut-free), and
  `\+` with Scryer's `representation_error(dcg_body)`. `library(dcgs)` is
  a built-in library for both front ends; in the native one it installs
  `op(1105, xfy, '|')`. The transition-construct census counts a grammar
  rule as its translated clause.

- **The seam counts its transition constructs, and a census keeps the count
  from growing** (ruling D13: allowed where they are, no new ones). A seam
  module's loader now has `l3_stats["transition_constructs"]`, the key and
  shape the native `.pl` front end already fills: the goal-position sites
  of `not` (as `\+/1`), `once/1`, `forall/2`, `memberchk/2`,
  `findall(_, G, [])` and `make_quantity/3`. A load with any of them logs
  one INFO line on `clausal.seam_frontend`. `if_/3` is not counted; it is
  library(reif)'s pure conditional and the thing to rewrite to. Each source
  site counts once: the `not` pair that `forall/2` lowers to, a `not` in a
  data position and a construct passed as a `call/N` closure do not count.
  `python -m clausal.tools.transition_census` counts every seam and `.pl`
  file under `clausal/`, `tests/` and `docs/`, prints per-file counts,
  totals and the census size (an empty census is an error, exit 2), and
  exits 1 when a file cannot be read at all, or when any (file, construct)
  count, or a file's count of goals it cannot convert, goes above the committed
  baseline (`clausal/tools/transition_census_baseline.json`; `--update`
  rewrites it). One test runs it against the baseline. Nothing is refused
  at load time.
- **Clausal Prolog may not import ISO Prolog** (ruled 2026-10-01: the
  dependency is one-way; a `.pl` module may import a Clausal Prolog or
  `.seam` module, never the reverse, and there is no opt-in). Under the
  Clausal Prolog surface, a `use_module/1,2` whose target resolves to a
  `.pl` file is refused at load with `permission_error(access,
  prolog_module, M)`: "Clausal Prolog may not import ISO Prolog (.pl),
  which may use cut; convert it to .clausal". The check reads the file the
  finders picked, so a name with a `.seam` or Clausal Prolog twin beside
  its `.pl` is imported as before. Both `.pl` front ends refuse it the same
  way. That surface has no extension until the extension flip, so the
  refusal is inactive today; `.pl` and seam importers are never affected.
  The run-time routes are refused too since the dialect gate (see
  Breaking).
- **`library(...)` facades: Clausal Prolog reaches Python only through
  `.seam` modules** (ruled 2026-10-01). Every engine Python module has a
  generated `.seam` facade under `clausal/library/`, a pure re-export of
  its predicates (same names and arities) and values (units, currencies,
  numbers): `py/<lib>` is `library(<lib>)` (`library(datetime)`,
  `library(json)`, ...) -- or `library(py_<lib>)` where Scryer has a
  library of that name (`py_os`, `py_files`, `py_random`, `py_uuid`,
  `py_csv`, `py_process`; `library(os)` stays an unknown library) --
  `units`/`imperial`/`currency`/`graphs`/`reflection`
  are `library(<m>)`, and each currency jurisdiction is
  `library(countries/<j>)` -- 203 facades, 204 predicate indicators.
  `:- use_module(library(datetime), [date_add/3]).` works from a `.pl`
  under both front ends. A library the front end already knows is never
  shadowed. `python -m clausal.tools.gen_library_facades` regenerates them
  (`--check`, `--census`); `clausal._py_facades.PY_FACADE_LIBS` lists them
  without importing the engine. Under the Clausal Prolog surface, an import
  whose target is a Python module by path (`py/datetime`,
  `clausal/modules/units`, a user `.py`) is refused at load with
  `permission_error(access, python_module, M)` naming the facade, and a
  module name a seam alias resolves (`european_union`, `units`) imports its
  facade. That surface has no extension until the extension flip, so the
  refusal is inactive today; `.pl` and seam files are unchanged. A
  `.clausal`/`.seam`/`.pl` file inside a package may now be named after a
  standard-library module (`clausal/library/datetime.seam`): only a
  top-level name is deferred to the stdlib.

- **`clausal.has_predicate(mod, name, arity=None)`,
  `clausal.defines_predicate(mod, name, arity=None)` and
  `clausal.module_binds(mod, name)`** ask a module about a name without
  going through `getattr`. `has_predicate` answers "is it a predicate I can
  call through the module": True whether the module defines the predicate
  or imports it (a thin facade), False for a data atom; it replaces
  `getattr(mod, name, None) is not None` as a predicate probe.
  `defines_predicate` is True iff the module
  defines, or imports and exports, the predicate `name/arity` (any arity
  when `arity` is `None`; the population of `module_signatures`).
  `module_binds` is True iff `name` is a real attribute of the module (in
  its `__dict__`: defined, imported, declared or auto-declared). Both work
  for `.clausal`/`.seam`, `.pl` under either front end, and package roots.
- **`':'(M, G)` builds a qualified goal term in seam** (ruled 2026-09-30).
  ISO's `:`/2 is now a known functor in `.clausal`/`.seam` source with no
  declaration: `T is ':'(lib, p(X)), call(T)`, `call(':'(lib, p(X)))`,
  `findall(X, ':'(lib, p(X)), L)`, `aggregate_all(count, ':'(lib, p(_)), N)`
  and `':'(lib, p(X))` as a body goal all run `p` in `lib`. The term is the
  one the `.pl` front end reads for `lib:p(X)` (`==` across the two) and
  prints as `lib:p(X)`. The second argument is resolved in `lib`, so the
  caller need not declare `p`: a written `p(...)`, `p()` or bare `p` there
  is the plain term of that name. A predicate `lib` does not define, or a
  module that does not exist, is `existence_error(procedure, p/N)` (see
  below). These used to raise
  `existence_error(procedure, (:)/2)`. A dotted call in data position is
  unchanged (`T is lib.p(1)` is still the plain `p(1)`).
- **`name()` is the atom `name`** (ruled 2026-09-30). A zero-argument call
  written with parentheses is the same goal as the bare name wherever a
  goal is expected: `call(zz())`, `aggregate_all(count, zz(), N)`,
  `maplist`'s closure, and `call(lib.z())` (which runs `z/0` in `lib`).
  These raised a Python `TypeError` about the reserved 1-tuple `('zz',)`.
  In data position `T is zz()` (for a predicate `zz`) and `T is lib.z()`
  bound `T` to that reserved 1-tuple; they now bind the atom. A name bound
  to a Python callable is unchanged: `T is f()`, `T is time.time()` and
  `T is ++f()` still call Python.
- **`--':'(M, G)` builds the qualified goal term from Python** (ruled
  2026-09-30). The `--` term builder gives the same term as seam
  `':'(lib, p(1))` and the `.pl` front end's `lib:p(1)` (`==`), with `p`
  resolved in `lib` (the calling module need not declare it). It raised
  `NameError: 'p' is not a declared or imported functor`. `--foo()` is
  still refused, inside `':'` too ("`foo()` is not a term form").
- **A seam `-import_from` of a data name from a `.pl` module binds the
  atom** (ruled 2026-09-30). `-import_from(M, [cite])` (or
  `alias(cite, c)`) against a `.pl` module that neither defines `cite` as a
  predicate at any arity nor binds it now resolves `cite` to the ATOM
  `cite`: data needs no declaration, and a `.pl` export list holds only
  `name/arity` predicates. It used to raise `ImportError: cannot import
  name 'cite' ... exports: citation/2` unless the `.pl` file happened to
  use `cite(...)` as data itself. Both `.pl` front ends. A name the module
  binds (an exported or defined predicate, a data atom it uses) imports
  as before; a `name/N` entry names a predicate and still fails when there
  is none; `.clausal`/`.seam` and Python targets are unchanged. A name
  within a small edit distance of one of the module's predicates
  (`citaton` for `citation`) still imports as the atom, and warns once
  with `ClausalImportedDataNameWarning` naming the predicate. Such a name
  also builds `cite(...)` at ANY arity in the importer, positionally:
  `--cite(++k)` and a clause's `cite(K)` are `('cite', K)`, `==` the
  rulebase's `cite(k)`. The same holds for a data functor the `.pl` module
  itself uses and the importer imports (`v` of `v(ok, [...])`) when the
  module declares no signature for it, which is the native front end's
  case: it used to build under the translator only.

- **ISO 13211-2 `:- end_module(Name).`, and a "require end_module"
  setting.** A `.pl` module file may end with `end_module/1`; both `.pl`
  front ends check that it names the file's `module/2` module and is the
  last item (only comments after it). A mismatched name, no `module/2`, or
  a duplicate is `error(existence_error(module, Name), end_module/1)`; an
  item after it is `error(permission_error(modify, module, M),
  end_module/1)`. When end_module is REQUIRED, a module file without it
  fails to load (`error(existence_error(directive, end_module(M)),
  load/1)`, naming the file and the module). Required is decided by the
  file's own `:- set_prolog_flag(require_end_module, true|false).`, else
  the process-wide setting (`CLAUSAL_REQUIRE_END_MODULE=1|0`,
  `clausal.end_module.set_require_end_module`, or
  `set_prolog_flag(require_end_module, V)` as a goal; read with
  `current_prolog_flag/2`), else a per-SURFACE default
  (`clausal.end_module.REQUIRE_END_MODULE_DEFAULTS`): `.pl` no, Clausal
  Prolog yes. Seam files are never affected. Scryer refuses the
  directive, so the test oracles drop it before handing a file to Scryer
  (`clausal.end_module.strip_end_module`), and the exporter refuses to
  emit it.

- **`clausal.tools.iso_l3_directives.is_auto_declarable_atom(name)`.**
  The name-level half of the native `.pl` front end's auto-declaration
  rule: True when a declaration can bind the spelling and the engine gives
  it no builtin or evaluable meaning at any arity (arity-blind). The
  per-file half (names the file itself takes: heads, goals, constructors,
  constants, imports, directive specs) is applied at load; a file's result
  is `lower_source(...).context.auto_atoms`. Native front end only.
  `DirectiveContext.auto_declare` now calls it, so there is one rule.

- **`abolish/1` (ISO 8.9.4).** `abolish(Name/Arity)` removes a dynamic
  procedure: its clauses and the procedure itself, so a later call is
  `existence_error(procedure, Name/Arity)` (a procedure emptied by
  `retract/1` fails instead). A static procedure, user-defined or builtin,
  is `permission_error(modify, static_procedure, Name/Arity)`; a procedure
  that does not exist is no error; the indicator's errors are ISO's
  (instantiation, `type_error(predicate_indicator, PI)`, `type_error(atom,
  Name)`, `type_error(integer, Arity)`, `domain_error(not_less_than_zero,
  Arity)`). It was an existence error. The database has a matching
  `Database.abolish(functor, arity)`.

- **clpz's `sum/3` and `global_cardinality/3` on the native `.pl` front
  end.** `sum(Vs, Op, Value)` (Op one of `#=`, `#\=`, `#<`, `#>`, `#=<`,
  `#>=`; Value a clpz expression) and `global_cardinality(Vs, Pairs,
  Options)` with Scryer's options `consistency(value)` and `cost(Cost,
  Matrix)`, answering and raising as Scryer's clpz does. `sum/3` is not a
  global builtin (a global `sum` would shadow Python's `sum` inside a seam
  `++` escape): it resolves only in a `.pl` file that imports
  library(clpz), from `clausal.stdlib.clpz_sum`; a file that defines its
  own `sum/2` still loads.

- **automaton/8** (clpz, Scryer's signature): automaton/3 with counters.
  An arc `arc(From, Label, To, Exprs)` sets each counter to its
  expression, where a variable of `Counters` is that counter's previous
  value and a variable of `Template` the matching part of the current
  element; an arc without `Exprs` leaves the counters. Scryer's own
  library raises `instantiation_error` for every counter expression with a
  variable (its `template_var_path/3` calls `arg/3` with an unbound
  index); Clausal gives the documented relation (the documentation's
  `sequence_inflexions` example answers `N = 3`).
- **append/2, list_max/2 and list_min/2** (Scryer's library(lists)).
  `append(ListOfLists, List)` answers as its two-clause definition does,
  in the same order and with the same non-termination (`append([A,B],
  [1,2])` enumerates the three splits; `append(foo, L)` fails).
  `list_max/2` and `list_min/2` fold with `max/2` / `min/2` through `is/2`
  (`list_max([2, 2.0], M)` is `M = 2.0`; the first element is taken
  unevaluated, so `list_max([1+1], M)` is `M = 1+1`).

- **Native `.pl` front end: meta-predicates, library(reif) and the
  transition constructs.** `findall/4` (the list ends in a given tail, as in
  Scryer), `maplist/4..9` (every answer, like `maplist/2,3`) and `call/9`
  are new builtins, for `.seam` as well. After `:- use_module(library(reif))`
  a `.pl` goal `if_(If_1, Then, Else)` has Scryer's meaning: `If_1` is
  called with one more argument, the truth value (`X = Y` and `dif(X, Y)`
  are reified in place, `(A, B)` and `(A ; B)` unfolded), and an unbound or
  non-boolean truth value raises `instantiation_error` /
  `type_error(boolean, T)`. The rest of Scryer's reif export list is there:
  `(=)/3` and `dif/3` are engine builtins (Scryer's answer orders),
  `tmember/2`, `tmember_t/3` and `cond_t/3` are in `clausal.stdlib.reif`,
  and so are `tfilter/3` and `tpartition/4` with EVERY answer, which a
  `.pl` file importing library(reif) takes instead of the engine's
  committed-choice builtins of the same name. `\+`, `once/1`, `forall/2`,
  `memberchk/2`, the `findall(_, G, [])` backdoor and `make_quantity/3` are
  accepted and counted: `l3_stats["transition_constructs"]` holds the goal
  sites per construct, and a load with any logs one INFO line on the
  `clausal.pl_frontend` logger.

- **Constants, units and dicts on the native `.pl` front end.** A `.pl`
  file declares constants with the seam's directive family in ISO syntax
  (`:- constant_value(max_retries, 3).`, `:- constant_number_units(max_fine,
  5000, euro).`, `constant_number_currency/3` and the `constants_number_*`
  tables), runs through the seam's own handlers, and reads a value with
  `constant(Name)`, folded at compile time as in the seam; an undeclared
  name is a load error naming the `.pl` line. `constant_number_units/3` is
  module-scoped as in the seam. `use_module(european_union, [euro])` imports
  a unit (a bare name on a Python module imports its value). `5*euro` stays
  an ordinary ISO term. `is/2` and the ISO comparisons now accept a quantity
  (`Q is 100 * constant(one_euro)` answers 100 euro) instead of raising
  `type_error(evaluable, ...)`; comparing across units (or with a plain
  number) raises `system_error(units_mismatch)`, as the seam does.
- **`get_strict/3`: the strict dict read as a predicate.**
  `get_strict(Dict, Key, Value)` (get/3's argument order) raises
  `existence_error(dict_key, Key)` on a missing key, with the subscript
  `V is D[K]`'s other errors, where `get/3` fails. It is the strict read ISO
  syntax can spell; from `.seam` it is an ordinary call.
- **Native `.pl` front end: declarations (`CLAUSAL_PL_FRONTEND=native`).**
  A `.pl` file is not strict: every atom and data functor it uses is
  declared for it, so a `.seam` file can `-import_from` those names, and
  each load logs the count as one INFO line on the `clausal.pl_frontend`
  logger (the names at DEBUG). A data functor declared this way has no field
  names, and `assertz` of its term still creates a dynamic procedure. The
  optional `:- constructors([pt(x, y)]).` gives a data functor field names
  (`signature/3`, `unbound_keys/2`). Listed as `pt/2` in `module/2`, it is
  exported as data with those fields. There is no `atoms/1` directive.
  Not declared: a constant's name (`constant(Name)` is a fold, not data), a
  constants table's predicate, an imported name (a Python module's value
  such as `euro` included) and the engine's own names (clpz, clpq). A bare
  entry of a `use_module/2` list imports nothing and is a use of its atom,
  unless the module offers that name as `name/N` (a module/2 export, a
  Python module's predicate): then it is not declared either.
- **A set literal in goal position is a CLP(Q) constraint set.** In
  `.clausal`/`.seam` source, `two(N, Q) <- {Q == N * 2}` and
  `within(X) <- {0 <= X <= 10}` post exact rational constraints: the twin
  of clpq's `{C}` and the short spelling of `clpq.rational((...))`, which
  it lowers to (one goal, identical answers). Elements are comparisons
  (`==`, `!=`, `<`, `<=`, `>`, `>=` or a chain); any other element is a
  load-time error naming it. A set in data position is still a set and
  `{}` is still a dict. The constraint block now runs the units side
  channel, so a `-constant_number_units` constant folded in through
  `constant(Name)` keeps its unit: `{Q == 100 * constant(one_euro)}` gives
  `100 euro` (before, `clpq.rational` refused a Quantity as non-linear).
  See [docs/clpq.md](docs/clpq.md).
- **library(lambda) as builtins: `(\)/1..8`, `(^)/3..10`, `(+\)/2..9`.**
  Ulrich Neumerkel's lambdas (`maplist(\X^Y^(Y is 2*X), Xs, Ys)`,
  `Free+\X^Goal`) run through call/N with Scryer's answers: `\` copies the
  lambda before each call so no binding leaks between calls, `+\` shares the
  variables of its left side, and a parameter no argument reaches raises
  `existence_error(lambda_parameter, _)`. The native `.pl` front end accepts
  `use_module(library(lambda)[, List])` and adds its `op(201, xfx, +\)`.
  The procedures are global, as the list builtins are: unlike Scryer, a
  module that does not import the library can still call them, and
  `call(Y^G, A)` is library(lambda)'s `(^)/3` rather than an
  existence_error.
- **clpz's predicates under Scryer's names: `in/2`, `ins/2`, `labeling/2`,
  and the reified connectives `#<==>`, `#==>`, `#<==`, `#\/`, `#/\`, `#\`.**
  Domains are written `1..3`, `inf..sup`, `1..3 \/ 5..7` or an integer;
  `labeling/2` takes Scryer's options (`leftmost`/`ff`/`ffc`/`min`/`max`,
  `up`/`down`, `step`/`enum`/`bisect`) and answers in Scryer's order; a
  reified comparison or `in/2` keeps its 0/1 variable linked. Errors carry
  Scryer's formal terms (`domain_error(clpz_domain, D)`, ...). They are
  builtins, so they work from `solve()` and, quoted, from the seam; a
  module's own definition of the name answers first. The engine's
  `label/1` is unchanged (first-fail); a native `.pl` file that imports
  library(clpz) gets Scryer's `label/1` (`labeling([], Vs)`).
- **The native `.pl` front end: clpq's `{C}` and ops by import.** After
  `use_module(library(clpq))`, `{C}` is lowered to `clpq.rational(C)`. An import installs the operators Scryer
  installs: `use_module/1` every op the module exports; an import list the
  exported ops it names, plus the exported ops the module also declares
  with a top-level `op/3` (so `use_module(library(clpz), [label/1])` still
  makes `#=` an operator, while `use_module(library(lambda), [(\)/2])` no
  longer makes `+\` one).
- **`member/2` and `memberchk/2` are builtins under their ISO names.** They
  were registered only as `in_/2` and `in_check/2`, so a `.pl` file read by
  the native front end, or a goal handed to `solve()`, found no procedure.
  The same builtins answer both spellings; a module's own or imported
  `member/2` still answers first.
- **Negative tests: `test(Name, fail)`.** plunit's `test/2` with the option
  `fail` passes iff its goal has no solution; a solution fails it and an
  exception is an error, as for `test/1`. The seam spelling is the same term,
  `test("name", fail) <- Goal`, and `.pl` files write it as plunit does. Any
  other option (`throws(E)`, `nondet`, `true(C)`, ...) is a collection error
  naming it (`clausal.testing.TestCollectionError`; one failing `<collect>`
  item for the file), never ignored. As in plunit, `test/2` is reserved: a
  file defining its own `test/2` predicate with other second arguments now
  fails collection (no file in this repository defines one). In a `.pl` file an atom second argument of
  `test/2` stays that atom (`fail`/`false` no longer fold to `False` there),
  in heads, calls and data alike. See [docs/testing.md](docs/testing.md).
- **One name at several arities in one file**, as in ISO: `p(1),` and
  `p(1, 2),` define `p/1` and `p/2`, two unrelated procedures (a DCG
  `s//1` is `s/3`); neither is padded into the other. A bare `p` in a data
  position is still the atom, `p(1, 2)` is the compound at the arity
  written, and a call at an arity that has no clauses is still an
  arity-mismatch error. See [docs/predicates.md](docs/predicates.md).
- **Declared fields per arity.** A name may carry declared fields at
  several arities, each with its own field names, in `-module` and
  `-private` lists and across directives: `-module(lib, [q(X), q(X, Y)])`
  loads. A clause head of a declared name must be at a declared arity
  (write `f/2`, an indicator, to add an arity without fields). A term built
  from Python by field name uses the written arity, else the one declared
  arity its keywords fit, else raises `AmbiguousArityConstructionError`.
  An `-edcg_pred` name keeps one arity.
- **`.pl` files are test files.** `python -m clausal.testing` and the
  pytest plugin load a `.pl` file through the `.pl` importer and run its
  `test/1` clauses; a `.pl` file that fails to translate is a failing
  `<load>` item. A file opts out with a `% clausal: no-collect` comment. A
  directory scan lists the files it skipped, with the reason. See
  [docs/testing.md](docs/testing.md).
- **`-import_from(m, [p/1])` imports one arity of `p`**, as Scryer's
  `use_module(m, [p/1])` does (`s//1` is `s/3`). A bare `p` still imports
  every arity; the forms mix in one list, and `alias(p/1, q)` renames one
  arity. An indicator the exporter lacks is a load-time `ImportError`
  (`existence_error(procedure, p/N)`, with the file, line and the arities
  the module has). A call at an arity that was not imported is refused like
  any missing arity, and the message names the entry to add. A `p/N` entry
  names a predicate, so `clausal.imported_atoms` does not count it. See
  [docs/import.md](docs/import.md#importing-one-arity-namen).
- **A repeated `-import_from` entry is one import.** `[baz, baz]`,
  `[baz/1, baz/1]` and `[baz, baz/1]` load as one entry (the `.pl`
  translator no longer emits `[baz, baz]` for `[baz/1, baz/2]`). Binding ONE
  local name to two different predicates (`[alias(f, x), alias(g, x)]`) is
  now a `SyntaxError`; Python kept the last one silently before.
- **A `.pl` file's `use_module(file, [p/1])` imports `p/1` only**, as in
  Scryer; it imported every arity of `p` before. A `library(...)` list is
  still imported by bare name.
- **`clausal.declared_atoms(module_or_package)`.** The `frozenset` of atom
  names declared in the `-module`/`-private` lists of a module's own files,
  or, for a package, of its `__init__` and its loaded submodules. An
  `-import_from`ed atom is not included, and the answer does not depend on
  import order. See
  [docs/python_integration.md](docs/python_integration.md#listing-the-atoms-a-module-declares-declared_atoms).
- **`clausal.imported_atoms(module_or_package)`.** A `dict` from atom name to
  exporter module name for the atoms a module's own files (or a package's
  `__init__` and loaded submodules) bring in via `-import_from` without
  re-declaring them. It counts only atoms the exporter declares, so imported
  predicates are left out, and it never overlaps `declared_atoms`. A package
  `__init__` with no `-module` list can now list its imported atoms without
  reading internal namespace keys. See
  [docs/python_integration.md](docs/python_integration.md#listing-the-atoms-a-module-imports-imported_atoms).
- **`clausal.module_signatures(module)`.** A `dict` from predicate name to
  the `frozenset` of its arities, for the predicates a module offers to
  `-import_from`. It answers for a Python-backed engine module (`py.datetime`,
  `currency`, `units`, ...), which has no Clausal source to read a signature
  from, as well as for a Clausal module. A module name is spelled and
  resolved as `-import_from` resolves it, and is imported if needed. See
  [docs/public-api.md](docs/public-api.md#13-python-entry-points).
- **A native `.pl` file can import a Python-backed module.**
  `:- use_module(py/datetime, [date_add/3, timedelta/3]).` works under
  `CLAUSAL_PL_FRONTEND=native`: `py/X` is redirected to the engine's
  `py.X` module as `-import_from(py.X, ...)` is, and each `name/N` entry is
  checked against `clausal.module_signatures`. A name the module lacks, or
  an arity it does not register, is a load error that names the `.pl` line
  and lists the predicates the module offers. `use_module(py/datetime)`
  imports every predicate the module has. See
  [docs/importing_prolog.md](docs/importing_prolog.md#importing-a-python-backed-module).
- **CLP(ℝ) `inf/2` and `sup/2`**: the bounds of an expression over real
  variables, read from the store without changing it; they fail when
  unbounded. (They used to reach the CLP(ℚ) solver, which knew nothing of
  a real variable: `in_real(X, 0.0, 10.0), X >= 2.5, inf(X, I)` gave
  `I = 0`.) See [docs/clpr.md](docs/clpr.md).
- **`Module.declare_dynamic(name, arity)`**, the Python spelling of
  `-dynamic(name/arity)`, so a `Module` built from Python can take an
  `assertz`. Idempotent; its errors are ISO `dynamic/1`'s. See
  [docs/database_ops.md](docs/database_ops.md).
- **Prolog flags.** `set_prolog_flag/2` and `current_prolog_flag/2` with the
  ISO flags (`bounded`, `max_integer`, `min_integer`,
  `integer_rounding_function`, `char_conversion`, `debug`, `max_arity`,
  `unknown`, `double_quotes`) and ISO's error terms, and the directive
  `-set_prolog_flag(Flag, Value)`. `double_quotes` is the module's
  `-double_quotes` mode. `unknown` can only be `error`. See
  [docs/flags.md](docs/flags.md).
- **The `assert_creates_dynamic` flag** (module-scoped, default `false`).
  With it `true`, `assertz`/`asserta` of a procedure that does not exist
  creates it as dynamic (ISO 7.5.2(2)), instead of raising
  `permission_error(modify, static_procedure, PI)`. A static predicate, a
  builtin and a declared data functor are still refused. An imported `.pl`
  module starts with it `true`, and `:- set_prolog_flag(F, V).` in a `.pl`
  file now carries across for any flag.

- **`.seam`** as an alias extension for `.clausal` files.
- **Goal-position seams in hosted Python:** `if --g(X):`, `for X in --g(X):`,
  `while --g(X):` and `not --g(...)`, plus comprehensions whose first `for`
  is a seam, and the dotted form `--m.pred(X)`. Conditional (WFS-undefined)
  answers raise `UndefinedAnswer`, and unbound constrained exports raise
  `ResidualConstraints`.
- **Converters exported from `clausal`:** `to_python` (deep, out),
  `to_clausal` (deep, in) and `term_key` (the standard order as a sort key).
- **Cell helpers exported from `clausal`:** `cell_functor`, `cell_args` and
  `make_cell`, to read and build a compound term. `query_wfs` is exported
  from `clausal` too.
- **The rest of ISO's evaluables:** `sign/1`, `+/1`, `rem/2`, `gcd/2`,
  `truncate/1`, `round/1`, `ceiling/1`, `floor/1`, `float/1`,
  `float_integer_part/1`, `float_fractional_part/1`, `sqrt/1`, `sin/1`,
  `cos/1`, `tan/1`, `asin/1`, `acos/1`, `atan/1`, `atan2/2`, `atan/2`,
  `exp/1`, `log/1`, `pi`, `e` and the bitwise `'>>'`, `'<<'`, `'/\\'`,
  `'\\/'`, `'\\'`, `xor`, with Scryer's kinds and errors. See
  [docs/arithmetic.md](docs/arithmetic.md).
- **`foldl/5`, `foldl/6` and `map_list_to_pairs/3`**, as Scryer's
  `library(lists)` and `library(pairs)`.
- **`'^'/2`**, ISO integer power: `'^'(2, 3)` is 8, and a negative
  exponent on an integer base other than 1 is `type_error(float, B)`.
- **`rdiv/2` as an evaluable functor**, the exact rational division:
  `rdiv(7, 2)` is 7/2 and `rdiv(6, 2)` is 3, in every arithmetic context.
- **The evaluable functors are builtins in scope in every module**
  (`+ - * / // div mod ** ^ rdiv` and unary `-`), strict or not, with no
  declaration: `'is'(X, rdiv(7, 2))` and `'//'(A, B)` are written as in
  Prolog. As data they stay ordinary terms.
- **[docs/operators.md](docs/operators.md)**: what each operator spelling
  means bare, quoted, and in the planned Prolog syntax.
- **Arithmetic written as a plain cell evaluates.** `('+', 1, 2)` evaluates
  in `eval_/2`, the arithmetic comparisons, `between/3`, `#=`, `==`/`!=`
  constraints and CLP(Q)/CLP(R), through one closed table of evaluable
  functors.
- **A public API promise:** `docs/public-api.md` lists what semantic
  versioning covers from 1.0.0. A new lint in a minor release may only warn.
- **Error messages print the term the way Scryer does**
  (`error(type_error(atom,1),atom_length/2)`), then the prose.
- **ISO builtins under their ISO names:** `'is'`, `'='`, `'\='`, `'=='`,
  `'\=='`, `'=:='` and the arithmetic comparisons, `'@<'` and its family,
  `compare/3`, `'=..'`, `'#='`, `clause/2`, and `writeq/1` and
  `write_canonical/1`.
- **ISO error terms**, pinned against Scryer, and a `system_error/2` helper.
- **`test/1`** is the test-clause predicate.
- **Units and CLP:** quantities and united variables take part in CLP
  comparisons, `in_domain/3`, and `label/1`. Added the `percent` and
  `basis_point` ratio units. `str(Quantity)` now round-trips.
- **Currency:** the full ISO 4217 vocabulary, including historical
  currencies; minor units such as `cent`; `money/3` and `money_round/3` with
  the other money builtins; and a construction-time precision check.
- **Constants:** lexical scope, `constant_number_units/3`,
  `module_constant_units/4`, and exact decimal strings.
- **Types:** `quantity/1`. `number/1` accepts a quantity, and `sum_list/2`
  sums every numeric kind.
- **Well-founded semantics:** `query_wfs` reports truth values and delays
  for every goal shape. Answers use the strong-Kleene `Undefined` value.
- **Dict dot access** (`P.key`), and `is`-chains (`A is B is C`) for naming
  a term inline.
- **New load-time lints:**
    - `ClausalStringInCatchPatternWarning`: a double-quoted string naming
      the type, domain or kind of an error in a catch pattern
      (`catch(G, error(domain_error("date", _), _), R)`), which never
      matches because the engine's error terms carry atoms. Write `'date'`.
    - `ClausalBooleanSeamWarning`: a seam read as a boolean.
    - `ClausalSeamTextCompareWarning`: a seam answer compared with a
      Python `str` literal.
    - `ClausalAtomExportDefinedAsPredicateWarning`: an exported atom that
      is also a predicate.
    - `ClausalExportArityMismatchWarning`: a `name/N` export entry for an
      arity the module neither defines nor declares, while it has clauses
      for `name` at another arity (`-module(m, [base/9])` over `base/2`
      clauses). The export stays legal; the warning names both arities.
    - `ClausalScaleInNameWarning`, `ClausalCurrencyLiteralWarning`,
      `ClausalTitleCaseIdentifierWarning`, `ClausalKeywordArgumentWarning`.
- **Diagnostics:**
    - Syntax errors show the source line and a caret.
    - Arity mismatches name the arity.
    - Undefined predicates list their candidates.
    - The test runner descends into a failing goal's clauses.

### Changed

- **`module_signatures` lists a `ModulePredicate` subclass that overrides
  `_get_dispatch`.** Such an adapter dispatches without its `_dispatch_fns`
  table, so an empty table no longer hides it: it is listed with the arity
  its dispatch function's parameters give, or an EMPTY set ("a predicate,
  arities unknown") when that takes `*args`. Only an adapter keeping the
  base `_get_dispatch` with nothing registered (a unit or currency
  constant) is still left out. `has_predicate` / `defines_predicate` now
  answer True for these adapters, a native `use_module(py/M, [name/N])`
  accepts them at any arity, and a BARE `name` entry for one is a bare
  predicate atom that imports nothing (it was imported as a value). The
  `_get_dispatch` protocol is unchanged.

- **A gate reads the names Python modules REGISTER as predicates.**
  `tests/test_python_predicate_name_gate.py` imports every module under
  `clausal/modules/` and `packages/*/clausal/modules/` from source (in a
  child process) and checks each name `module_signatures` offers, and
  each predicate adapter's own `_name`, against the engine's
  logic-variable rule: a TitleCase, ALL-CAPS or underscore-led name fails.
  The source lint never saw these (`ModulePredicate("Name")`, `_pred`,
  hand-rolled adapters). A package module whose declared third-party
  dependency is absent is read statically instead; any other import
  failure fails the gate. Run against the tree before the package renames,
  it reports 334 such names.
- **The optional packages' suites run against the checkout, uninstalled.**
  `packages/conftest.py` splices each package's source directories onto
  the engine's namespaces, so `python -m pytest packages` from the
  repository root tests this tree's package code. A package whose required
  dependency is not importable is skipped, naming it; so is a test that
  fails because a declared dependency is absent. The package tests now load
  their seam fixtures under `.seam` (they still named `.clausal`).

- **The `.pl` translator reads which twins hide a `.pl` from the finder
  order.** When a `use_module` names a `.pl` file, its `module/2` export
  list is read only if no twin the import hook loads first sits beside it.
  That set was the literal `(".clausal", ".seam")`; it is now every
  extension `clausal._suffixes.SOURCE_SUFFIXES` lists before `.pl`, read at
  each call. Same answer today; it cannot drift from the hook.

- **The test suite writes seam source under the seam suffix.** A test that
  writes seam (Python-syntax) source to a temporary file, or globs for seam
  files, names the suffix through `tests/_suffix.py` (`SEAM`, which reads
  `clausal._suffixes`: `.seam` before and after the extension flip;
  `seam_glob` and `seam_path` find in-repo seam fixtures under either
  spelling) rather than spelling `.clausal`. Tests that pin today's
  `.clausal` seam alias, the `.clausal`/`.seam` finder priority, or the
  simulated flip to Clausal Prolog keep `.clausal`.

- **Preparation for the extension flip** (`.seam` becomes the only seam
  suffix and `.clausal` the Clausal Prolog surface). Nothing changes for a
  `.clausal` or `.seam` file today; the flip itself is now the edit of the
  two tuples in `clausal/_suffixes.py` plus the rename of seam files.
  - The bytecode cache key is keyed on the file's surface: a Clausal Prolog
    file gets its own key, so a seam `.pyc` is never served for it. Existing
    `.clausal`, `.seam` and `.pl` caches keep their keys.
  - A Clausal Prolog file always loads through the native front end,
    whatever `CLAUSAL_PL_FRONTEND` says. `PrologFinder` and the import
    finder take the Prolog suffixes from the Clausal Prolog tuple then
    `.pl`; the seam group is still asked first. So in one directory
    `name.seam` beats `name.pl`, and after the flip `name.clausal` beats
    `name.pl`, for every importer.
  - `clausal-fmt` and `clausal-rewrite` refuse a file whose extension says
    it is Prolog (`.pl`, or Clausal Prolog), naming the surface, instead of
    feeding it to the seam parser.
  - Diagnostics and CLI help derive their suffix lists from the tuples; a
    message telling you where to put seam code names `.seam` (for example
    the goal-seam `NameError`: "move the code into a .seam file").
  - Seam code blocks in `docs/` are fenced ```` ```seam ````. The doc-snippet
    checks and the docs collector accept ```` ```clausal ```` as an alias
    for now.

- **No export privacy from Python.** Python code reaches a `.pl` module's
  unexported predicates through `getattr`, `mod.name` and
  `from mod import name`, as with any module attribute (this already worked
  under both front ends; now pinned by tests). It is documented as possible
  but **not supported long-term and not advisable**: use exported
  predicates, since unexported access may stop working in a future release.
  No runtime warning.

Where there is a choice, ISO 13211-1 is the reference, and Scryer Prolog
where ISO is silent; SWI-Prolog is not a reference.

- **The Prolog exporter prefers ISO/Scryer spellings.** The default (`iso`)
  dialect writes `all_different` as `all_distinct/1` and `time_goal` as
  `time/1`, Scryer's names; `in_domain` and `divmod_` are unchanged. The
  default CLP(ℤ) library is `clpz` (`Dialect.swi()` keeps `clpfd`). Every
  dialect writes a prefix-operator directive in functional notation
  (`:- discontiguous(p/1).`), which both Scryer and SWI read. See
  [docs/prolog_translation.md](docs/prolog_translation.md).
- **Tests never drive Scryer's toplevel from stdin.** The oracle build hangs
  when its interactive toplevel reads a pipe or `/dev/null`, and when a `-g`
  goal raises with no separate `-g halt` after it. `tests/_oracles.py`
  `run_scryer(program, goals)` now asks each query with `-g` (stdin
  `/dev/null`, a trailing `-g halt`) and prints the answer with the
  toplevel's own printers (`tests/_scryer_toplevel.pl`), so `   X = 1.`,
  `   false.` and `   error(...).` read exactly as before. Every test that
  fed Scryer queries uses it; `tests/test_oracle_paths.py` guards that no
  direct Scryer call reads stdin.
- **`.pl` import renames nothing silently.** The ISO evaluables keep their
  names and ISO meaning (`max`, `min`, `abs`, `sqrt`, ...; `max` used to
  become `max_`, which is not evaluable); `//`, `mod`, `rem`, `div`, `^`,
  `**` and the bit operators cross as the quoted ISO evaluables
  (`'^'(2, -1)` is `type_error(float, 2)`, not `0.5`); `profile_get/3`,
  `atomic/1` and a program's own or imported names cross unchanged.
- **`.pl` import: `use_module` resolves paths as Scryer does.** A quoted or
  unquoted slash path (`sub/helpers`, `'../shared/helpers'`, with or without
  `.pl`) is resolved against the importing file's directory; an unquoted
  one used to become a comment and the import vanished. A spec that names
  no module is a `SyntaxError` naming the directive and its line. The
  built-in libraries (`dif`, `between`, `error`, ...) are explicit no-op
  imports. Every translation error names the `.pl` line.
- **`.pl` import: `set_prolog_flag(double_quotes, Mode)`** governs every
  `"…"` below it: `chars`, `codes` (`[97, 98]`) or `atom`. `codes` used to
  be ignored.
- **`.pl` import: the standard-order comparisons** `@<`, `@>`, `@=<`,
  `@>=` cross as the quoted ISO builtins (they were refused).
- **`.pl` import refuses what it cannot keep.** A query in program text
  (`?- G.`) is refused (it used to become a comment); the atom `undefined`
  is written quoted.
- **`.pl` import: a name clash between modules** is resolved with a
  module-qualified call, `m:p(X)` (which becomes `m.p(X)`). Renaming an
  import with `as` is not accepted, as neither ISO nor Scryer has it. See
  [docs/importing_prolog.md](docs/importing_prolog.md#name-clashes-qualified-calls).

### Deprecated

These keep working, with a warning, through 1.x. They are removed in 2.0.

- **The `clausal.logic.atoms.atom` boundary class.** Constructing one emits
  `ClausalAtomClassDeprecationWarning`. It is a `UserWarning`, so it is shown
  by default, once per call site. Write `'x'`, and test with
  `type(v) is str` or `is_atom(v)`. Known gaps:
    - `isinstance(v, atom)` does **not** warn. It is now `False` for every
      engine value, so filters built on it go silently empty.
    - Unpickling an old instance warns once, at the `pickle.loads` call
      site.
- **`-double_quotes/1`.** It is a temporary per-module ratchet, and it will
  be deleted once no module needs it.
- **TitleCase unit names** (`Metre` for `metre`) **and the old
  physical-constant spellings.** They are warned aliases
  (`ClausalDeprecatedSpellingWarning`).
- **`query()`.** Iterate `solve(...)` and read `Var.value`.

### Experimental

- **Importing `.pl` files** is experimental in 1.0: it goes through a
  translator that is being replaced, and it is outside the semantic
  versioning promise.

### Removed

- `PredicateMeta`, `make_predicate` and `MakePredicateRetiredError`.
- `clausal.terms.Compound` and `clausal.terms.KWTerm`, with
  `compound_as_cell`, `list_to_cons`, `cons_to_list` and the builtin
  `extend/3` (only a keyword term could satisfy it). Keyword-argument terms
  stay a load-time `SyntaxError`.
- The `CLAUSAL_NO_FLIP` environment switch.
- The `:=` walrus form in clause bodies (`X := Expr`), which is now a
  `SyntaxError`. It was never deprecated. Use `eval_(Expr, X)` for eager arithmetic, `==` for arithmetic
  constraints, and `is` for unification.
- `q(...)` quasi-quotation.
- **`Test/1`** test clauses: a TitleCase name is a logic variable, so
  `Test("…") <- …` is a load-time error. Use `test/1`.
- **The `-implicit_atoms` directive**, with its deprecation warning
  (`ClausalImplicitAtomsDeprecationWarning`) and the
  `tools/codemods/add_implicit_atoms.py` codemod. A file that carries it
  does not load: `SyntaxError: -implicit_atoms was removed; declare atoms
  with -private([...]) or quote them`.

### Fixed

- **The date predicates see a date term whose component was bound in the
  body.** `Y = 2025, ordinal(date(Y, 3, 1), N)` answered nothing, with no
  error, in `.pl` (both front ends) and in the seam when the term was built
  before `Y` was bound; a literal date or a head-bound `Y` worked. The
  module's input conversion dereferenced only the outer term, so a
  component that was a bound variable made the term look like a non-date.
  It now walks the term. Every predicate of `py.datetime` /
  `library(datetime)` is affected (`ordinal/2`, `date_add/3`,
  `days_between/3`, `weekday/2`, ...). A date-family term that is still not
  a date where one is required now RAISES instead of failing:
  `instantiation_error` for an unbound component (`ordinal(date(_, 3, 1),
  N)`), `type_error(integer, date(foo, 3, 1))` for an ill-typed one and
  `domain_error(date, date(2025, 2, 30))` for an impossible one, as
  `date/3` already did, and `type_error(date, date(2025, 3))` for the wrong
  number of components. A partial term is an output target where the
  predicate can compute the value: `ordinal(date(Y, M, D), 739311)` binds
  `Y = 2025, M = 3, D = 1`, and a short-form target such as
  `timedelta(3, 0, timedelta(D, S))` or `time(10, 30, 0, time(H, 30, 0))`
  meets the value when its microseconds are zero. A value of another type (`date_add(90, TD,
  R)`) still fails with a diagnostic note, as before.
- **A clause body of any length loads**, on every front end (native `.pl`,
  the translator, seam). Each backtracking goal compiles to a loop around
  the rest of the body, so about 19 such goals (user calls, builtin calls,
  DCG nonterminals, the goals inside a `findall/3` body) went past CPython's
  limit of 20 nested blocks, and the module failed to load with
  `SyntaxError: too many statically nested blocks`. The code generator now
  moves the deep tail of such a body into nested helper generators, which
  share the clause's variables. Shorter bodies compile exactly as before.
  If the generated code still cannot be compiled, the error is a
  `GeneratedCodeError` (a `SyntaxError`) that names the predicate and the
  clause's file and line.

- **`phrase/2,3` with an unbound grammar body raise
  `instantiation_error`**, as ISO and Scryer do: `phrase(_, L)`,
  `phrase(_, L, [])`, and so a variable grammar body (`v(B) --> B.`)
  called with `B` unbound. They used to fail silently.

- **A bare-name import of a `.pl` predicate brings only its exported
  arities** (ruled 2026-10-01). With `:- module(m, [p/1])` and an
  unexported `p/2` also defined, `-import_from(m, [p])` (or
  `alias(p, q)`, or a translator `.pl` `use_module(m, [p])`) imports
  `p/1` alone, as `[p/1]` does: a clause calling `p(X, Y)` through it
  raises `existence_error(procedure, p/2)`, and the importer may define
  its own `p/2`. It used to reach the private `p/2`. Python access is
  unchanged. The native `.pl` front end now does the same for
  `use_module(m, [p])`: it imported nothing for a bare name (D11), so
  `p(X)` through it raised `existence_error(procedure, p/1)`. A name `m`
  does not export still imports nothing and warns as a bare atom.
- **DCG braces `{G}` follow ISO and Scryer.** `phrase({G}, L)`,
  `phrase({G}, L, R)` and a `{G}` inside a phrase body run `G, S0 = S`
  (every answer of G kept, nothing consumed); they raised
  `existence_error(procedure, {}/3)`. A rule whose whole body, or a whole
  disjunct or if-then-else branch, is `{G}` (or `\+ G`) now ties its two
  states together: `e(X) --> {X = 5}.` (and the seam's
  `e(_x) >> ({_x is 5})`) accepted `[a]` and left phrase/3's rest
  unbound. A whole body `{!}` is a local cut, like
  `phrase(!, L)`; a braced cut inside a larger body is refused, as any cut
  inside a meta-called body is.
- **`solve("!")` succeeds once, as `call(!)` does.** A cut that is the
  whole query is local to it and cuts nothing (ISO 7.8.3). `solve` already
  answered `true`, `fail` and `false` by name; `!` (and `M:!`) was looked
  up as a procedure `!/0` and raised `PredicateNotFoundError`.
- **`phrase(!, L)` and `phrase(!, L, R)` answer as ISO and Scryer do.** A
  cut that is the whole grammar body is local to phrase and cuts nothing,
  as in `call(!)`: `phrase(!, [])` succeeds, `phrase(!, [a])` fails, and
  `phrase(!, [a], R)` gives `R = [a]`. It used to be looked up as the
  nonterminal `!//0` and raised `existence_error(procedure, !/2)`. A cut
  inside a larger body (`phrase((a, !), L)`) is still refused.
- **library(reif)'s `=/3` (and `dif/2`) read a partial list.**
  `'='([a, b], [a|L], T)` (the seam's `[a, *L]`) answered only `T = false`;
  it now answers `T = true, L = [b]` and then `T = false` with
  `dif(L, [b])`, as Scryer does, for a partial list against a proper list,
  another partial list, a nested one or a string, and decides `false`
  against a list it cannot match or a non-list. The occurs-checked
  unifier behind `reify_eq` and `dif` (C, with its Python twin) probed a
  partial list through its split-enumerating unify hook, which advanced a
  cached generator: the probe used up the one split and the real
  unification that followed failed. It now pairs a partial list's
  elements itself. A list with a hole that is not its tail (`[*A, x]`)
  still goes through the hook.
- **A clpz inequality with an arithmetic side narrows its variables and
  binds a singleton.** `7*R #=< 1000000` left R in `inf..sup`: the posted
  constraint narrowed only a side that was a bare variable, so an expression
  side was merely checked. The floor-division idiom
  `T #> 0, R*T #=< C*10000, C*10000 - R*T #< T` left R unbound where Scryer
  binds `R = 142857`, and `R - R #< 0` succeeded. A `#=<`, `#<`, `#>=` or
  `#>` with an `+ - *` / negation side (and the seam's bare `<=`, `<`, `>=`,
  `>`) is now linearised: one variable left is narrowed by ceil/floor
  division by its coefficient, several are posted as a bounds-consistent
  scalar product, and a product of two unknowns (`R*T`) gets a times
  propagator, so `R*T #=< 1000000, T = 7` narrows R once T is known.
  `7*R #>= 1000000` gives `142858..sup`, one tighter than Scryer's
  `142857..sup` (7*142857 is 999999). A chain of such posts now propagates
  bounds both ways, as clpz does, and costs more to post.

- **A dotted `lib.p(...)` passed to a builtin meta-caller runs `p` in `lib`.**
  `call(lib.p(X))`, `call(lib.p(1), Y)`, `aggregate_all(count, lib.p(_), N)`,
  `call_goal(lib.p(X))`, `time_goal(lib.p(X))`, `phrase(lib.nt(A), L)` and
  `maplist(lib.p(1), L)` (and `include/3`, `foldl/4` & co.)
  built the plain `p(...)` term and ran it in the CALLING module:
  `existence_error(procedure, p/1)`, a Python `NameError` when `lib` defines
  no `p` at all, or, silently, the caller's own `p`. The argument is now
  the qualified goal `lib:p(...)`, as the same dotted call in goal position,
  inside `findall/3`/`once/1`/`not`/`forall/2`, or in a user
  `-meta_predicate` position already was (Scryer: `call(lib:p(X))`). A dotted
  call used as data (`T is lib.p(1)`) is still the plain `p(1)` cell, so
  `T is lib.p(X), call(T)` still runs `p` in the calling module.

- **A `use_module` sibling of a `.pl` file loaded BY PATH gets its full
  dotted name.** Both `.pl` front ends named a file found beside the
  importer relative to a root climbed one directory per dot of the
  importer's module name, which is wrong when that name is not the file's
  dotted one: `clausal.testing.load_clausal_module('pkg/dom/__init__.pl')`
  (loaded as `_clausal_test___init__`) named its sibling `dom.schema` and
  failed ("no module dom.schema on sys.path" / "No module named 'dom'").
  The climbed root is now used only when it round-trips to the importer's
  own name; otherwise the most specific `sys.path` entry names the
  sibling (`pkg.dom.schema`). The same applies to the undefined-name hint
  that names an exporting sibling, which also named a package
  `__init__`'s sibling one level too high.

- **A test clause whose body is exactly `true`, or a test fact, keeps its
  name and option.** Such a clause is stored like a fact, with its head
  arguments moved into leading unifications, and the test runner read the
  bare head: `test(name) :- true.` was reported as `_0` and run as
  `test(_)`, and `test(name, fail) :- true.` failed collection with
  "unknown test option `'fail'`". The runner now reads the moved arguments
  back. This affected both `.pl` front ends and `.clausal`/`.seam`
  (`test("name") <- True`), and a compound description on any seam test
  clause (`test(case(2)) <- ...`), which was run as `test(_)` and so could
  pass on the strength of another test's clause. A compound description is
  named by its term text, as `writeq/1` writes it (`case(2)`), not the
  Python tuple `('case', 2)`.
- **`findall/4` inside a `findall/3` goal no longer raises "findall/3 not
  found".** When a clause set called both `findall/3` (the compiler special
  form) and `findall/4`, the compiled clause could bind the name to a
  dispatch stand-in fixed at arity 3 and route the `findall/4` goal through
  it. Whether this happened depended on hash order, so it failed only on some
  runs. It affected `.pl` and `.seam` source alike.
- **`{}` in goal position is now a clear load-time error.** In `.seam`
  source `{}` is the empty dict, not an empty constraint set. As a goal it
  used to surface an internal `NotImplementedError` ("goal shape not yet
  supported (DictTerm)"). It now raises `DictGoalError`: "`{}` is an empty
  dict, not a goal in predicate p/1 (line N)". A non-empty set of
  comparisons in goal position is still the CLP(Q) constraint set.
- **`assertz((foo :- X))` with `X` unbound raises the runtime rule refusal.**
  An unbound body is a rule body (ISO converts it to `call(X)`), so it now
  gets `permission_error(assert, rule, foo)` like every other rule assert
  instead of `instantiation_error`. With `X` bound to `true` it still asserts
  the fact `foo`. The same applies to `asserta/1`.

- **An improper list read from a `.pl` file is the ISO cons cell, not a
  list of characters.** The native `.pl` front end read `[b|foo]` as
  `[b,f,o,o]` (the atom's characters spliced in), so `msort([b|foo], L)`
  answered `L = [b,f,o,o]`. A tail that is neither a list nor a variable
  now makes the compound `'.'(H, T)`: `sort/2`, `msort/2`, `keysort/2` and
  `atom_chars/2` raise `type_error(list, [b|foo])`, `is_list/1`, `length/2`
  and `append/3` fail, `member/2` finds the heads, `X = [b|foo], X = [H|T]`
  binds `H = b, T = foo`, and `writeq/1` prints `[b|foo]`, as Scryer does.
  A clause HEAD `[H|T]` does not yet match an improper list.
- **The native `.pl` front end resolves a `use_module` path beside the
  importing file first.** Inside a `.pl` package `pk`, `use_module(sib, ...)`
  now imports `pk.sib` when `pk/sib.pl` (or `.clausal`, `.seam`, `.py`, a
  package) exists, and a slash path `a/b` names `a/b` beside the importer;
  only a path with nothing beside the importer is read as a dotted module on
  `sys.path`. This is Scryer's rule and the translator's. Before, the native
  front end read the path as a top-level module only: a same-named module
  later on `sys.path` answered silently, and without one the import was
  refused.
  In both front ends a plain directory beside the importer (one with no
  `__init__` file) is no module: Scryer opens only the file, and the
  translator used to take such a directory and never fall back to
  `sys.path`.
- **The bytecode cache key includes the source suffix.** A same-directory
  `twin.pl` and `twin.clausal` share one `__pycache__` file; with equal size
  and modification time each was served the other's bytecode. `.pl` and
  `.seam` caches are rebuilt once; `.clausal` caches are unaffected.
- `_load_module` and `_load_prolog_module` accept a `pathlib.Path` on a warm
  bytecode cache too (it raised `TypeError`).
- A non-`str` `sys.path` entry (`None`, `bytes`, an `int`, a `Path`) is
  skipped by the source finder, as CPython's `PathFinder` skips it, instead
  of raising `TypeError` out of every import.
- **clpz global constraints follow Scryer's clpz contract.**
  `global_cardinality(Vs, Pairs)` now requires every element of `Vs` to be
  one of the keys: it counted per key only, so an element free to take an
  off-key value satisfied every count (`X in 0..2,
  global_cardinality([X], [1-0])` labelled X = 0 and 2; clpz has no
  answer). Its counts and elements must be integers or variables (`[1-a]`
  succeeded; now `type_error(integer, a)`), and a repeated key is
  `domain_error(gcc_unique_key_pairs, Pairs)`. `zcompare/3` raises
  `domain_error(order, O)` for a bound Order other than `<`, `=`, `>` (it
  failed) and `type_error(integer, X)` for a non-arithmetic operand.
  `element/3` raises `type_error(integer, I)` for a non-integer index (it
  failed). `scalar_product/4` takes any clpz expression as its fourth
  argument (`Y*Y`, `4/2`), as `#=` does; every compound was refused.
- **`compare/3` checks its Order argument (ISO 8.4.2.3).** An Order that is
  neither a variable nor an atom is `type_error(atom, Order)`; an atom other
  than `<`, `=` and `>` is `domain_error(order, Order)`.  `compare(foo, a, b)`
  used to fail silently.

- **`succ/2` and `numlist/3` raise Scryer's errors instead of failing.**
  `succ(X, Y)` with both unbound is an instantiation error, a non-integer
  argument `type_error(integer, A)` and a negative one
  `domain_error(not_less_than_zero, A)`; `numlist(a, 3, L)` is
  `type_error(integer, a)`.  All of these used to fail silently.
  (`numlist/3` with an unbound bound still fails; Scryer enumerates.)
- **CLP(R) reads a united variable's interval.** The units side channel
  posts a physical quantity's constraint on a shadow variable; `inf/2`,
  `sup/2` and `label_real/1,2` read the user's variable instead, so after
  `clpr.real((X >= constant(one_metre), X <= 2 * constant(one_metre)))`,
  `inf(X, L)` answered `0 metre` (from CLP(Q)) and `sup(X, H)` failed. They
  now read the shadow and answer with the expression's dimension (`1.0
  metre`, `2.0... metre`), the same numbers as the unit-free twin. Money is
  still refused by CLP(R) (`units_unsupported`).

  A clause head list pattern takes the cell apart too: `p([H|T], H, T)`
  called with `[b|foo]` answers `H = b, T = foo`, `[a, b|T]` walks nested
  cells, and a proper pattern such as `[a, b]` matches only a chain that
  ends in `[]` (the head matcher, C and Python, shares the body's code).
- **assertz/1 and asserta/1 no longer recompile the predicate on every
  call.** Each assert recompiled the whole clause list, so filling a
  predicate was quadratic (about 90 s for 250 clauses). An assert now only
  invalidates the compiled code and the next call recompiles it once, as
  retract/1 already does: 250 clauses fill in 0.02 s, 10,000 in 0.5 s (plus
  one compile at the first call). A call between asserts still sees every
  clause asserted before it, and a running call still iterates its snapshot.
- **A module-qualified call to a builtin runs the builtin.** In a `.pl`
  file that also wrote a module name as data (`call(m:G)`,
  `findall(X, m:p(X), L)`), every compiled `m:atom_length(...)`,
  `m:assertz(...)`, `m:retract(...)` in the file raised
  `existence_error(procedure, _)`: the module name was bound as an atom,
  and the compiler walked the atom instead of the module.  In a `.seam`
  module, `m.assertz(...)` reached an internal AST class and raised
  `type_error(callable, _)`.  Both now run the builtin in module m.  As in
  Scryer, `zz:atom_length(abc, R)` answers `R = 3` when no module `zz` is
  loaded (for a builtin that does not touch the database).
- **`clause/2`, `retract/1` and `retractall/1` answer every clause when the
  pattern holds a frozen variable.** A `freeze/2` goal woken while a clause
  head was tested left its bindings behind, so
  `freeze(Y, Y = X), clause(p(Y), true)` found only the first clause, with no
  error.
- **`assertz(M:C)`, `asserta(M:C)`, `retract(M:C)` and `retractall(M:H)` act
  on module M.** Before, the assert stored a clause for `(:)/2` in the
  calling module, where nothing could reach it, and the retracts removed
  nothing and gave no error. An unbound `M` is an `instantiation_error`.
- **`retract/1` raises ISO's errors.** `retract(1)`, `retract("ab")` and
  `retract([a])` raise `type_error(callable, _)`, and a control construct
  (`retract((a, b))`, `retractall(true)`) raises
  `permission_error(modify, static_procedure, _)`, as in Scryer. Before,
  `retract/1` failed and `retractall/1` succeeded. `retract((p(_) :- 1))`
  now fails, as in ISO 8.9.3 and Scryer, instead of raising.
- **`retract/1` no longer recompiles the predicate for each clause it
  removes.** The next call recompiles it, once. A drain of 1,000 clauses
  took over a minute and now takes a few hundredths of a second.
- **`copy_term/2`, `term_variables/2`, `ground/1`, `numbervars/3`,
  `bagof/3`, `setof/3` and `findall/3` see the variables of a partial list
  nested in a term.** The C term walkers treated a partial list (`[A|T]`), a
  partial string or byte string, and a dict term as a leaf below the top
  level: `term_variables(f([A|T]), Vs)` gave `[]`, `copy_term(f([A|T]),
  f([B|U]))` left `A == B`, `ground(f([a|T]))` succeeded, and the free
  variables of a bagof/setof goal and the per-solution copy of findall/3
  missed them too. The walkers now read through these shapes at any depth,
  in C (no slowdown for proper terms), with the Python twins in step. A dict
  term's values are walked the same way (its keys are ground).
  `numbervars/3` numbers every variable except one in the hole of a partial
  list or string (the `T` of `[A|T]`), which it leaves unbound at any depth:
  `[A|'$VAR'(1)]` has no representation and could not be printed (ISO
  numbers it too; this follows the `[a|b]` gap).
- **`copy_term/2` copies `dif/2` constraints.** `dif(A, a), copy_term(A, B),
  B = a` now fails, as in Scryer: the copy carries the constraint, over
  copies of the constraint's other variables. `freeze/2` goals and CLP
  constraints are still not copied (their attribute is a compiled goal or a
  propagator network, not a term); findall/3 and bagof/3 copy no
  attributes, as in Scryer.

- **A `.pl` module in an earlier `sys.path` entry is no longer shadowed by a
  `.clausal` or `.seam` module of the same name in a later one.** The import
  hook now resolves source modules per `sys.path` entry, in path order: the
  first entry that holds the module wins, and the extension priority
  (`.clausal`, `.seam`, then `.pl`) decides only within one entry. Before,
  `.clausal`/`.seam` and `.pl` were found by two finders that each scanned
  the whole path, so a `.pl` package could load a same-named `.clausal`
  sibling from another tree and answer from it without any error.
  `PrologFinder` is no longer installed on `sys.meta_path`; `PredicateFinder`
  finds `.pl` too. The other side of the same rule: a stray `foo.pl` in an
  earlier entry (such as the script directory, `sys.path[0]`) now shadows a
  `foo.clausal` or `foo.seam` in a later one. See
  [docs/importing_prolog.md](docs/importing_prolog.md).

- **A partial list is `instantiation_error` in the clpz globals.**
  `tuples_in/2`, `global_cardinality/2`, `lex_chain/1`, `automaton/3` and
  the other clpz predicates that read a list raised
  `type_error(list, [1|_])` for a partial list; Scryer's `must_be/2` gives
  `instantiation_error`.
- **subtract/3, intersection/3 and union/3 compare elements by `==/2`.**
  Python's `==` made `1` and `1.0` (and `f(1)` and `f(1.0)`) one element:
  `subtract([1, 2, 1.0], [1.0], D)` gave `[2]`, now `[1, 2]`.
- **CLP(Q) accepts quantities.** `{Q = 100 * constant(one_euro)}` in a
  `.pl` file, `clpq.rational(Q == 100 * constant(one_euro))`, `in_q/3` with
  quantity bounds, `entailed/1` and the objectives of `maximize/2`,
  `minimize/2`, `sup/2`, `inf/2` and `bb_inf/3` go through the units side
  channel the CLP(FD) comparators already use: dimensions are inferred and
  checked first (a disagreement is `system_error(units_mismatch)`), the
  tableau solves on exact magnitudes in the base unit, and the answer is a
  quantity — `100 euro`, `3/2 euro`, and `N = 300` for
  `{Q = N * constant(one_euro)}, Q = 300 euro`. Every such post used to
  raise a raw `TypeError: CLP(Q) requires linear constraints`. A quantity
  leaf inside an arithmetic cell built at run time (`Q = 6000 * constant(c)`
  in ISO syntax) is evaluable in a post too, instead of
  `type_error(evaluable, ...)`. See [docs/clpq.md](docs/clpq.md#units).
- **`true` in a `.pl` data position is the truth value.** The native front
  end left `true`/`false`/`undefined` as atoms where the seam folds them to
  `True`/`False`/`Undefined`, so `memberd_t(b, [a, b], true)` FAILED (the
  reified `T` is `True`). They fold now, as in the seam; `True`/`False`
  written in a `.pl` file stay ordinary variables. Known divergence (as in
  the seam): the engine treats the folded values as bools, not atoms, so
  `atom(true)` fails, `atom_length(false, N)` and `functor(F, true, 1)`
  raise `type_error(atom, _)`, `true = 1` succeeds and `compare(O, true, a)`
  gives `<` (Scryer: yes, 5, `true(_)`, no, `>`).
- **A user-defined `true/N` or `false/N` (N >= 1) loads,** in `.seam` and
  `.pl` alike (ISO and Scryer allow it): the seam refused it as a "reserved
  truth value name", and `call(true, X)` now reaches it. `true/0` and
  `false/0` stay the truth values; `undefined/N` stays reserved.
- **A listless `use_module/1` of a `.seam` module imports its export list**
  on the native front end: the bare names of its `-module` list were
  skipped, so the module's predicates were not in scope; a module exporting
  nothing is still loaded, so `m:G` reaches it.

- **A procedure `assertz` creates is no longer shadowed by an atom of the
  same name some other module declared.** Module dicts are seeded from the
  process-wide atom pool, so the body goal `note(X)` of a later,
  assert-created `note/1` bound to the atom `note` and raised
  `existence_error(procedure, note/1)`, depending on what the process had
  loaded first. The call now re-resolves in the calling module (its own
  row, then a builtin) and raises the same error only when nothing answers.
- **`:- use_module(m, []).` in a `.pl` file is a located translation
  error**, not a loader crash (`ValueError: empty names on ImportFrom`).
  Scryer reads it as `remove_module/2` (drops the imports, never loads
  `m`), Trealla and SWI as "load `m`, import nothing", so the error names
  both and points at `use_module(m)` / `use_module(m, [p/1])`. See
  [docs/importing_prolog.md](docs/importing_prolog.md).
- **A tail-recursive clause keeps its effects on caller variables.**
  Tail-recursion optimisation restarted the clause after undoing its whole
  trail segment, so a `dif` or CLP constraint on a caller variable
  (`K is not H`, `K != 3`), a binding of one (`K is foo`) and a binding
  nested in a tail argument were silently lost:
  `findall(1, (ka(K, [a, b]), K is a), R)` gave `R = [1]` for
  `ka(K, [H, *T]) <- (K is not H, ka(K, T))`. The restart is now taken only
  when the clause touched nothing but variables it created; otherwise it
  makes the ordinary recursive call. See
  [docs/compiler.md](docs/compiler.md#tail-recursion-optimization-tro).
- **`==` and `!=` see through bound variables.** A variable bound inside a
  list, cell or dict reads as its value, as ISO `==/2` dereferences every
  subterm: `X is [Y], Y is 1, X == [1]` failed silently.
- **`.pl` import: `bagof/3` and `setof/3` keep `Y^Goal`.** The quantifier
  was stripped, so `setof(X, Y^p(X, Y), L)` answered once per `Y`.
- **`.pl` import declares a program's data functors.** `p(f(1)).` in an
  imported `.pl` file answers `p(f(1))` instead of raising
  `existence_error(procedure, f/1)`; a name used as data at two arities is
  declared at both.
- **The native ISO reader keeps the last clause** of a text with no
  trailing newline (`clausal.tools.iso_l3.read_iso`, internal; not yet the
  `.pl` import path), and its `lower_items` raises on a refusal by default.
- **The bytecode cache key covers everything that decides the emitted
  code**: the evaluable table, the units and countries tables, the term
  helpers and the `.pl` translator with its tokenizer, as well as the
  compiler. Editing any of them used to leave stale cached bytecode.
- **The Prolog exporter names each import and export once.** A `-module`
  export list is deduplicated by `Name/Arity`, and so is an import list
  whose arities are known (`[helper/1, helper/1]`, `helper(X)` beside
  `helper/1`, `sent//1` beside `sent/3`). An import list holding a bare
  name, with no module signatures to give its arity, is written as a
  listless `use_module(lib)`: Scryer refuses a bare atom in an import list
  and Trealla imports nothing.
- **An imported `.pl` file's `_Name` variable is no singleton.** By the
  Prolog convention (ISO, Scryer) `_Y` in `setof(X, p(X, _Y), L)` is used
  once on purpose; the `.pl` load warned "rename to `_Y_UNUSED`". The
  `.clausal`/`.seam` rule is unchanged: every named variable used once
  warns.
- **`python -m clausal.testing` skips what the pytest plugin skips.** A
  directory scan honours `collect_ignore`/`collect_ignore_glob` from the
  `conftest.py` files under it, so `tests/` no longer reports the golden
  translator inputs as failing loads, and the Prolog files shipped as
  package data (the toklex specs and the constants preludes) carry the
  `% clausal: no-collect` marker.
- **A lambda called with the wrong number of arguments** raises an ISO
  error term instead of a Python `TypeError`: too many arguments extend the
  body goal (`maplist((S) <- (S > 0), [1, 2], R)` is
  `existence_error(procedure, (>)/3)`, as Scryer's library(lambda)), too
  few are `existence_error(lambda_parameter, Lambda)`.
- **Indexing:** clause selection no longer drops answers when:
    - an argument slot holds a variable bound to a structure,
    - a structured head was asserted at runtime,
    - a keyword data head is called positionally.
- **WFS:**
    - A clause-prefix delay covers every answer.
    - A detached judging leader no longer loses the outer loop's answers.
- **Exceptions:** `catch/3` works around a trampolined subgoal, and
  `throw/1` raises a copy of the ball (ISO 7.8.10).
- **Crashes:**
    - A crash on garbage collection of a `Trail` (weakref ordering).
    - A reference-counting bug in CLP(B) node construction.
- **CLP(FD):** crashes and unsound saturation on bignum bounds past float
  range.
- **Arithmetic:** `5 + money` raises what `money + 5` raises.
- **ISO equality:** `'=='` is an equivalence relation, and it distinguishes
  `1` from `1.0`.
- **Validation:** `global_atom/2` raises `type_error(atom, Name)` instead of
  failing silently.
- **A bare builtin name in a data position is the atom** (`integer`,
  `assertz`, `in_`), as in every Prolog: `must_be(integer, 3)` succeeds
  (it raised `type_error(atom, <builtin integer/1>)`), `X is assertz` binds
  the atom `assertz`, and `call(in_, X, [1])` answers `X = 1` instead of
  leaking a Python `TypeError`. A meta-argument (`call/N`, `maplist`'s
  closure) receives the atom and resolves it when called.
- **A package whose `__init__` is a `.clausal` file** loads as a Clausal
  package even when it is imported before `clausal.import_hook`; it used to
  become an empty namespace package, and its `-import_from` of sibling
  files never ran.
- **A top-level `--goal` over a predicate of the same file** (which runs
  before the file's clauses are compiled) raises
  `existence_error(procedure, p/1)` with a message giving the file and
  line and the fix, instead of a bare "not defined".
- **sqlite: TEXT columns are strings in every row shape.** A multi-column
  row from `query/3,4` used to carry its TEXT columns as atoms (so
  `SELECT name, age` gave `('alice', 30)`, which is also the compound
  `alice(30)`); it is now `("alice", 30)`, as a single-column row already
  was.
- **`.clausal` bytecode is written atomically.** The loader wrote a cached
  `.pyc` in place, so a process sharing the `__pycache__` could read a torn
  file; it now writes a temp file beside it and `os.replace`s it in, as
  CPython does, and removes the temp file if the write fails.
- **The Prolog exporter keeps `!=` a constraint.** It wrote `X != Y` as the
  plain test `\==` (or `=\=` beside arithmetic), which differs whenever an
  argument is unbound. A numeric `!=` (a side that exports as an integer --
  including `-3`, a quantity literal such as `5000(euro)` and a constant
  folded to an integer -- or as arithmetic, including a clpz evaluable
  such as `abs(X)`) is now clpz's `#\=`, imported beside `#=`; any other,
  including a float, is `dif/2`. `is not` stays `dif/2`. See
  [docs/prolog_translation.md](docs/prolog_translation.md).

### Migration guide: 0.x to 1.0

| 0.x | 1.0 |
|---|---|
| `m.pred(X)` | `solve(("pred", X), module=m)` |
| `make_predicate(...)` / a Python predicate class | a `.clausal` module, or an object with `_get_dispatch()` |
| `atom("x")` | `"x"` |
| `isinstance(v, atom)` | `type(v) is str` |
| comparing a seam answer with `"text"` | `v == --"text"` or `to_python(v) == "text"` |
| `"sym"` used as a symbol in a `.clausal` file | `'sym'` or bare `sym` |
| `Test("…") <- …` | `test("…") <- …` |
| `[K, V]` pairs for `pairs_*` / `group_pairs_by_key` | `'-'(K, V)` |
| `-implicit_atoms` | list the atoms in `-private([...])` / `-module(name, [...])`, or quote them |
| `X := Expr` in a body | `eval_(Expr, X)` |
| `Compound(f, args)` / `KWTerm(...)` | the cell `(f, *args)` |
| `exc.term` read as an object (`.args`, `.functor`) | `cell_functor(exc.term)`, `cell_args(exc.term)` |
| matching the context text in `error(_, Context)` | match the culprit indicator, or `_`; the prose is `exc.message` |
| `assertz` into an undeclared predicate | declare it `-dynamic` first |

## 0.4.0

See the `v0.4.0` tag.
