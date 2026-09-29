% The Scryer stand-in for s2lib/shapes.seam (Scryer cannot read .seam): the
% same predicates, in ISO Prolog.  Only the Scryer-oracle test uses it.
:- module(shapes, [area/2, scaled/2, kinds/1]).
:- use_module(facts, [base/1, pair/2]).

area(sq(S), A) :- A is S * S.
area(rect(W, H), A) :- A is W * H.

scaled(X, Y) :- base(B), Y is X * B.

kinds(K) :- pair(K, _).
