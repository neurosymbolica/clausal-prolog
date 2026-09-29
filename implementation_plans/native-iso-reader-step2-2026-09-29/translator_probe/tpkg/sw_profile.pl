:- module(sw_profile, [t/1]).
t(V) :- X = foo, profile_get(X, k, V).
