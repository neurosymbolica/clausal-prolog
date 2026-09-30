% clausal: no-collect
% (Scryer-only oracle plumbing, not a Clausal test file.)
/*  Answer ONE toplevel query the way Scryer's interactive toplevel does,
    for a query handed over with -g instead of on stdin.

    Loaded by tests/_oracles.py:run_scryer after the program under test:

        scryer-prolog prog.pl _scryer_toplevel.pl \
            -g "'$clausal_oracle':query('<query text>')" -g halt </dev/null

    The clean Scryer build hangs when its toplevel reads a pipe, /dev/null or
    a pty, so tests cannot feed it queries on stdin. This module reads the
    query text with variable_names, as the toplevel does, runs it through the
    toplevel's own '$toplevel':run_query_goal/4, and prints each answer with
    the toplevel's own printers -- so `   true.`, `   false.`, bindings,
    residual goals and `   error(...).` come out byte-for-byte as the
    interactive toplevel prints them.

    The one thing a script cannot do is press a key. Where the toplevel
    would wait after an answer with choicepoints left, this answers as a
    user pressing RETURN would: the answer, then `;  ... .`, and stop.
*/
:- module('$clausal_oracle', []).

:- use_module(library(charsio)).
:- use_module(library(iso_ext), [bb_put/2]).

query(Atom) :-
    atom_chars(Atom, Chars),
    % What '$toplevel':submit_query_and_print_results/2 sets before a query.
    bb_put('$answer_count', 0),
    bb_put('$report_all', false),
    bb_put('$report_n_more', 0),
    catch(read_term_from_chars(Chars, Goal, [variable_names(VNs)]), E, true),
    (   nonvar(E)
    ->  '$toplevel':print_exception(E)
    ;   '$toplevel':run_query_goal(Goal, VNs, '$clausal_oracle':answer, [])
    ).

answer(pending(LeafAnswer), _, stop) :-
    '$toplevel':handle_first_answer,
    '$toplevel':increment_answer_count,
    '$toplevel':write_leaf_answer(LeafAnswer, []),
    nl, write(';  ... .'), nl.
answer(final(LeafAnswer), Info, Stop) :-
    '$toplevel':toplevel_query_callback(final(LeafAnswer), Info, Stop).
