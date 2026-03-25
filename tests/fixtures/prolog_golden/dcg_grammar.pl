:- module(dcg_grammar, [sentence/2, noun_phrase/2, verb_phrase/2, greeting/2, digit/3, ab/2, look_ahead/3, not_a/2, expr_dcg/3, valid_sentence/1]).

greeting -->
    ["hello", "world"].

noun_phrase -->
    ["the", "dog"] ; ["the", "cat"] ; ["a", "bird"].

verb_phrase -->
    ["chases"] ; ["sees"] ; ["likes"].

sentence -->
    noun_phrase, verb_phrase, noun_phrase.

digit(Digit) -->
    [Digit], {Digit >= 0}, {Digit =< 9}.

ab -->
    ["a"], ab.

ab -->
    ["b"], ab.

ab -->
    [].

look_ahead(Token), [Token] -->
    [Token].

not_a -->
    \+ ["a"], [X].

valid_sentence(Sentence) :-
    phrase(sentence, Sentence).

expr_dcg(Expression) -->
    [Expression], {Expression = Expression + 0}.

test("valid sentence") :-
    valid_sentence(["the", "dog", "chases", "the", "cat"]).

test("greeting") :-
    phrase(greeting, ["hello", "world"]).

test("noun phrase dog") :-
    phrase(noun_phrase, ["the", "dog"]).

test("verb phrase chases") :-
    phrase(verb_phrase, ["chases"]).

test("digit 3") :-
    phrase(digit(3), [3]).
