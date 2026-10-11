# Text construction census: results (2026-10-08)

Data for two open questions: (a) should char lists be compacted to the chars
carrier `('$chars', text)` at construction/copy points, and (b) should the
Python boundary become typed.  Two parts: a static census of the adapters
that a compaction would break, and the measured census of what the engine
builds while it runs the in-repo suites.

**Outcome (ruled 2026-10-11): both (a) and (b) PARKED** on these numbers; see
`compact-char-lists-at-construction-needs-a-typed-boundary-2026-10-08.md`.

The instrument (NOT on main: branch `text-census-2026-10-08`, e33163a2) is `CLAUSAL_TEXT_CENSUS=<path>` (off by default;
`clausal/logic/_text_census.py`, C side `clausal/logic/variables/_text_census.h`,
reader `python -m clausal.tools.text_census <path>.*`).

## Static census: adapters that take a list of atoms

`to_python` hands a carrier over as a `str` and a plain list of one-char
atoms as a `list`.  Most `py.*` adapters that take a list do NOT go through
`to_python` at all: they test the dereferenced term with
`isinstance(x, list)` / `expect_type(x, list)`, and a carrier is a tuple.
So under compaction a list such as `[x, y]` that reached them as a list
would instead reach them as `('$chars', 'xy')`.

| module | predicate | Python function | argument | what it does | under compaction |
|---|---|---|---|---|---|
| json | generate/2 | `_generate_2` clausal/modules/py/json.py:315 (via `_clausal_to_python` :92) | Term, at any depth | list -> JSON array (:131), carrier -> JSON string | BREAKS: `["x","y"]` becomes `"xy"` |
| json | pretty_generate/2 | `_pretty_generate_2` json.py:328 | Term | same converter | BREAKS |
| json | write_file/2 | `_write_file_2` json.py:395 | Term | same converter | BREAKS |
| json | parse/3 | `_parse_options` json.py:215 (check :242) | `atoms(Spellings)` option | `isinstance(spellings, list)` | BREAKS: domain_error(json_option) |
| http | json_post/3 | `_json_post_3` clausal/modules/py/http.py:336 | TermIn | JSON body via the json converter | BREAKS: array body becomes a string |
| csv | generate/2 | `_generate_2` clausal/modules/py/csv.py:138 | each row | `expect_type(row, list)` :149 | BREAKS: type_error(list) |
| csv | write_file/2 | `_write_file_2` csv.py:229 | each row | `expect_type(row, list)` :240 | BREAKS: type_error(list) |
| csv | generate_records/3 | `_generate_records_3` csv.py:156 | Headers | `expect_type(headers, list)` :164 | BREAKS: type_error(list) |
| process | process_create/3 | `_process_create_3` clausal/modules/py/process.py:157 | Args (argv) | `expect_type(args, list)` :166 | BREAKS: type_error, no spawn |
| process | process_create/4 | `_process_create_4` process.py:182 | Args | `expect_type(args, list)` :194 | BREAKS |
| random | choice/2 | `_random_member_2` clausal/modules/py/random.py:84 | List | `expect_type(lst, list)` :87 | BREAKS: type_error |
| random | permutation/2 | `_random_permutation_2` random.py:97 | List | `expect_type` :100 | BREAKS |
| random | sample/3 | `_random_sample_3` random.py:108 | List | `expect_type` :111 | BREAKS |
| sqlite | query/4 | `_sqlite_query_4` clausal/modules/py/sqlite.py:190 | Params | `isinstance(params, (list, tuple))` :196, one `?` per element | BREAKS SILENTLY: binds `'$chars'`, `'xy'` |
| sqlite | exec/3 | `_sqlite_exec_3` sqlite.py:220 | Params | same check :225 | BREAKS SILENTLY |

**15 predicate-argument pairs take a possibly-list-of-atoms argument; all 15
change behaviour under compaction** (13 loudly, the 2 sqlite ones silently).
None is "same".

Already a bug today, independent of compaction: sqlite Params given as a
single string (`query(Db, Sql, "hello", R)`) binds two parameters,
`'$chars'` and `'hello'`, because the carrier passes the `(list, tuple)` test.
FIXED 2026-10-10 (`_param_seq` in clausal/modules/py/sqlite.py): a text is one
parameter.

Text positions are unaffected: every adapter position that takes TEXT goes
through `to_text` / `text_or_str` / `require_text` / `to_bytes`, which already
promote a char list to a str (`clausal/modules/py/__init__.py:212-220`,
`re._coerce_subject` clausal/modules/py/re.py:85): csv cell values, process
program/cwd/input/env, http data and headers, logging messages, url parts,
re pattern/subject/replacement, files paths and contents, hash/hmac/pbkdf2,
tcp send, uuid name, os env.  datetime, asyncio, os, files, tcp, url, uuid,
hash, hmac, pbkdf2, units, imperial take no list-of-atoms argument.

The `_helpers.py` wrappers (`_pure`, `_bidir_*`, `_check_*`, `_text_arg`,
`_fact_table_2`) have no in-tree py adapter caller; their users are the
packages, where `to_python` would hand a `str` for what was a list (axis or
dimension name lists, for example).  Not audited here.

Outside `clausal/modules/py` (engine and non-py modules), where list vs str
reaches Python code:

- `clausal/modules/graphs.py:90` (and :128, :141, :153, :157, :200, :222,
  :392, :404): an edge is kept only `if isinstance(e, list)`, so a
  compacted edge `[a, b]` is SILENTLY DROPPED; `path_cost/3` (:470) raises
  type_error(list).  The most likely real-world hit (single-letter vertices).
- `clausal/modules/pure_random.py:204` `_proper_list`: type_error(list) on a carrier.
- `clausal/modules/reflection.py:346` `op_node/3`: operands `[x, y]` fail silently.
- `clausal/logic/to_python.py:443` `unwrap_atom` (the `++` / f-string thunk path),
  `clausal/logic/compiler/predicate.py:456` `$to_python`, public `clausal.to_python`,
  `clausal/logic/solve.py:116` raw answers, `clausal/logic/python_terms.py:639`
  `from_term`: a Python caller sees a `str` (or the raw carrier) where it saw a list.
- `clausal/logic/seam.py:308`/`:335` `text_of`/`text_value`: `str(x)` of a list
  renders `"['a', 'b']"`, of a carrier `"ab"`.

There are about 400 `isinstance(..., list)` / `type(...) is list` sites under
`clausal/` outside tests, so the engine-internal exposure to (a) is much wider
than the `to_python` boundary.  Conclusion for (a): compaction is not a
representation-only change while these sites test for `list`; (b) (a typed
boundary that says "text" or "list of symbols" per argument) would be the
prerequisite.

## Measured on the in-repo suites

Run with `CLAUSAL_TEXT_CENSUS` set over `tests/` (278 process files; the
FAILED set was identical to the run with the census off) and over
`packages/` (2 process files).  `values` counts constructions (a value
re-walked or re-copied is counted again); `chars` is the summed length;
lengths are bucketed by log2.  A list counts only when non-empty and all
one-char atoms; a SegList by its concrete elements when they are all
one-char atoms.

Headline:

- By characters, the builders are `SegList.__walk__` (700k chars, 180
  values: 35 walks of ~20000-element lists dominate), `body_star_output`
  (860k values, nearly all ONE-element SegLists `[C|T]` built in one
  in-process test run), then `findall_row`/`reverse/2`/`msort/2`/`copy_term/2`
  (~60k each, three 20000-long values each) and the `append/3` text fast
  path (40k chars, 416 values, up to 200 long).
- Shape: carriers are 44% of the characters built, char lists 6.6%,
  partial SegLists 49%.  Plain char lists are rare in count (519 values)
  and come from `atom_chars/2`, `number_chars/2`, list builtins over list
  inputs (input type wins) and copies of those.
- Lengths are short: outside the few stress tests, nearly every value is
  under 64 chars; the longest is 20000.
- The C split loop (`append/3` with only L3 bound) hands out 2489
  prefix/suffix values, 98.7% carriers, none longer than 5.
- The packages suite builds almost no text through the instrumented engine
  paths (2 `atom_chars/2` values); its carriers come from the adapter
  result funnel `clausal.modules.py.text_result`.

### tests/

```
text census: 278 file(s), 39 named source(s), 1096 chars() caller(s)

Sources by characters built
  source                                        values        chars      max  shapes
  body_star_output                              860218       860270        6  carrier 0.0%, seglist 100.0%, segstring 0.0%
  SegList.__walk__                                 180       700292    20000  carrier 65.0%, seglist 35.0%
  findall_row                                       40        60080    20000  carrier 52.5%, char_list 47.5%
  reverse/2                                         16        60036    20000  carrier 62.5%, char_list 37.5%
  msort/2                                            9        60018    20000  carrier 44.4%, char_list 55.6%
  copy_term/2                                        6        60005    20000  carrier 66.7%, char_list 16.7%, segstring 16.7%
  append/3:text_fast_path                          416        40254      200  carrier 100.0%
  head_list_output                                 511        30579    10001  carrier 93.0%, seglist 7.0%
  seg_split_tail                                   367         3937       60  carrier 19.3%, char_list 80.7%
  append/3                                        2489         3771        5  carrier 98.7%, char_list 1.3%
  SegString.__walk__                               187          486       24  carrier 67.9%, segstring 32.1%
  body_star_slice                                  149          269       10  carrier 71.8%, char_list 28.2%
  atom_chars/2                                      21           77       16  char_list 100.0%
  tabling_answer                                    30           57        4  carrier 53.3%, char_list 46.7%
  <lambda>                                          37           45        3  carrier 2.7%, char_list 97.3%
  segstring_split_tail                              23           43        5  carrier 100.0%
  sort/2                                            15           43        6  carrier 13.3%, char_list 86.7%
  atom_codes/2                                      10           26        4  code_list 100.0%
  partition/4                                        9           22        3  carrier 44.4%, char_list 55.6%
  select/3                                           9           20        3  carrier 33.3%, char_list 66.7%
  include/3                                         10           18        5  carrier 60.0%, char_list 40.0%
  union/3                                            4           16        5  carrier 50.0%, char_list 50.0%
  list_to_set/2                                      6           15        3  carrier 50.0%, char_list 50.0%
  number_chars/2                                     6           14        4  char_list 100.0%
  number_codes/2                                     4           12        4  code_list 100.0%
  take/3                                             6           12        3  carrier 66.7%, char_list 33.3%
  split_at/4                                         4           10        3  carrier 100.0%
  split_with/3                                       7            9        3  carrier 100.0%
  drop/3                                             5            8        2  carrier 80.0%, char_list 20.0%
  subtract/3                                         3            6        2  carrier 66.7%, char_list 33.3%
  test_as_items_yields_char_atoms_for_a_str          2            6        3  carrier 50.0%, char_list 50.0%
  exclude/3                                          3            5        3  carrier 66.7%, char_list 33.3%
  sort_by/3                                          2            5        3  carrier 50.0%, char_list 50.0%
  span/4                                             2            5        3  carrier 100.0%
  permutation/2                                      2            4        2  carrier 100.0%
  group_by/3                                         1            3        3  carrier 100.0%
  take_while/3                                       2            3        3  carrier 100.0%
  drop_while/3                                       1            2        2  carrier 100.0%
  intersection/3                                     1            2        2  carrier 100.0%


Shape split over the named sources
  carrier          3925 values (0.5%),       835763 chars (44.4%)
  char_list         519 values (0.1%),       124289 chars (6.6%)
  seglist        860292 values (99.5%),       920303 chars (48.9%)
  segstring          63 values (0.0%),           92 chars (0.0%)
  code_list          14 values (0.0%),           38 chars (0.0%)

chars() constructor by calling module (overlaps the named sources)
  source                                       values        chars      max  shapes
  clausal.logic.runtime._seg_helpers              140       640269    20000  carrier 100.0%
  tests.test_standard_order                     20025       140049        7  carrier 100.0%
  clausal.logic.builtins.lists                    492        40425      200  carrier 100.0%
  tests.test_text_construction_copies_once         22        20633    10001  carrier 100.0%
  clausal.modules.py                              719        10802     1753  carrier 100.0%
  clausal.logic.runtime.list_unify                 26        10057    10001  carrier 100.0%
  tests.test_adapter_io_errors_iso                 79         3767       81  carrier 100.0%
  tests.test_files_module                          71         2344       72  carrier 100.0%
  tests.test_regex                                186         1844       35  carrier 100.0%
  tests.test_dict_set_compiler                     69         1202       38  carrier 100.0%
  tests.test_sqlite                               147         1180       70  carrier 100.0%
  tests.test_reflection_sugar                      12         1170      129  carrier 100.0%
  tests.test_reflection_builtins                   10         1082      145  carrier 100.0%
  tests.audit_2026_07_05.test_09_builtins         325          955        5  carrier 100.0%
  tests.test_logging_module                        68          906       73  carrier 100.0%

Length distribution per source (bucket:values)
  <lambda>
    1:30 2-3:7
  SegList.__walk__
    1:65 2-3:77 4-7:2 32-63:1 16384-32767:35
  SegString.__walk__
    0:2 1:50 2-3:117 4-7:14 8-15:2 16-31:2
  append/3
    0:614 1:626 2-3:1235 4-7:14
  append/3:text_fast_path
    0:2 1:2 2-3:9 4-7:17 8-15:16 16-31:32 32-63:64 64-127:128 128-255:146
  atom_chars/2
    2-3:17 4-7:2 16-31:2
  atom_codes/2
    2-3:8 4-7:2
  body_star_output
    1:860193 2-3:16 4-7:9
  body_star_slice
    0:24 1:69 2-3:32 4-7:21 8-15:3
  copy_term/2
    1:1 2-3:2 16384-32767:3
  drop/3
    0:1 2-3:4
  drop_while/3
    2-3:1
  exclude/3
    1:2 2-3:1
  findall_row
    1:11 2-3:24 4-7:2 16384-32767:3
  group_by/3
    2-3:1
  head_list_output
    1:186 2-3:121 4-7:10 8-15:8 16-31:16 32-63:32 64-127:64 128-255:73 8192-16383:1
  include/3
    0:2 1:2 2-3:5 4-7:1
  intersection/3
    2-3:1
  list_to_set/2
    2-3:6
  msort/2
    2-3:5 4-7:1 16384-32767:3
  number_chars/2
    2-3:5 4-7:1
  number_codes/2
    2-3:2 4-7:2
  partition/4
    2-3:9
  permutation/2
    2-3:2
  reverse/2
    0:1 1:1 2-3:8 4-7:3 16384-32767:3
  seg_split_tail
    0:24 1:151 2-3:67 4-7:20 8-15:16 16-31:32 32-63:57
  segstring_split_tail
    0:5 1:5 2-3:10 4-7:3
  select/3
    1:2 2-3:7
  sort/2
    2-3:12 4-7:3
  sort_by/3
    2-3:2
  span/4
    2-3:2
  split_at/4
    2-3:4
  split_with/3
    1:6 2-3:1
  subtract/3
    2-3:3
  tabling_answer
    0:5 1:3 2-3:17 4-7:5
  take/3
    0:1 2-3:5
  take_while/3
    0:1 2-3:1
  test_as_items_yields_char_atoms_for_a_str
    2-3:2
  union/3
    2-3:1 4-7:3
```

### packages/

```
text census: 2 file(s), 1 named source(s), 98 chars() caller(s)

Sources by characters built
  source                       values        chars      max  shapes
  atom_chars/2                      2           16        8  char_list 100.0%

Length distribution per source (bucket:values)
  atom_chars/2
    8-15:2

Shape split over the named sources
  char_list           2 values (100.0%),           16 chars (100.0%)

chars() constructor by calling module (overlaps the named sources)
  source                                    values        chars      max  shapes
  clausal.modules.py                           352         4749      117  carrier 100.0%
  test_yaml_errors_iso                          13          619       85  carrier 100.0%
  test_spacy_free_form_outputs_stubbed          56          590       55  carrier 100.0%
  test_opencv_free_form_outputs_stubbed          5          371      100  carrier 100.0%
  test_yaml_module                              20          236       20  carrier 100.0%
  test_acl2_bridge_stubbed                      35          224       32  carrier 100.0%
  test_decide_adapter_stubbed                   24          209       17  carrier 100.0%
  test_yaml_free_form_outputs                   11          127       71  carrier 100.0%
  clausal.modules.py.acl2                        9          113       53  carrier 100.0%
  test_sklearn_text_inputs_stubbed              22          112       15  carrier 100.0%

```
