:- module(sw_euro, [c/1]).
:- use_module('tpkg.cur', [euro/0, price/1]).
c(X) :- price(X), X == euro.
