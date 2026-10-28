% clausal: no-collect
% (Scryer-only plumbing for tests/fuzz/scryer_diff.py, not a Clausal test file.)
/*  Answer ONE query with every answer printed, as Clausal's `-g` prints it:
    each leaf answer on its own line, ended by `.`, with Scryer's own
    toplevel printer (`'$toplevel':write_leaf_answer/2`, no depth limit),
    and then the next answer -- where the interactive toplevel would wait
    for a key.  Loaded after the program under test:

        scryer-prolog prog.pl _scryer_fz_top.pl \
            -g "'$fz_top':query(N, '<query text> .')" ... -g halt </dev/null

    A query that does not parse prints fz_syntax(E) and the case's end
    marker fz_end(N), so the cases after it stay apart.
*/
:- module('$fz_top', []).

:- use_module(library(charsio)).
:- use_module(library(iso_ext), [bb_put/2]).

query(N, Atom) :-
    atom_chars(Atom, Chars),
    % not the first answer: no three-space indent before it
    bb_put('$answer_count', 1),
    bb_put('$report_all', true),
    bb_put('$report_n_more', 0),
    catch(read_term_from_chars(Chars, Goal, [variable_names(VNs)]), E, true),
    (   nonvar(E)
    ->  write(fz_syntax(E)), nl, writeq(fz_end(N)), nl
    ;   % each answer's callback says continue: backtrack for the next
        (   '$toplevel':run_query_goal(Goal, VNs, '$fz_top':answer, []),
            fail
        ;   true
        )
    ).

answer(pending(Leaf), _, continue) :- leaf(Leaf).
answer(final(Leaf), _, continue) :- leaf(Leaf).

leaf(exception(E)) :- !, write(fz_uncaught(E)), nl.
leaf(Leaf) :-
    '$toplevel':write_leaf_answer(Leaf, [depth(deep)]),
    write('.'), nl.
