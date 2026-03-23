:- module(dcg_grammar, [sentence/2, noun_phrase/2, verb_phrase/2, greeting/2, digit/3, ab/2, look_ahead/3, not_a/2, expr_dcg/3, valid_sentence/1]).

greeting -->
    ["hello", "world"].

noun_phrase -->
    ["the", "dog"] ; ["the", "cat"] ; ["a", "bird"].

verb_phrase -->
    ["chases"] ; ["sees"] ; ["likes"].

sentence -->
    noun_phrase, verb_phrase, noun_phrase.

digit(D) -->
    [D], {D >= 0}, {D =< 9}.

ab -->
    ["a"], ab.

ab -->
    ["b"], ab.

ab -->
    [].

look_ahead(T), [T] -->
    [T].

not_a -->
    \+ ["a"], [X].

valid_sentence(S) :-
    phrase(sentence, S).

expr_dcg(E) -->
    [E], {E = E + 0}.
