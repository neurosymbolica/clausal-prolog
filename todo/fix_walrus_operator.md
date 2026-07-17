Python's := walrus operator has been abused by Clausal - it was used to implement an equivalent of Prolog's is/2 but is/2 has issues itself and subsequently, in Clausal it is on the verge of deprecation. := can be done with ++(python expression) escapes anyway. There were many cases where LLMs used :=/2 wrongly instead of is/2 or ==/2, because it kind of worked and they were reaching for expression evaluation (which is too declarative).

Also, the Pythonic semantics of := are in fact very useful. Sometimes we might, for example, wish to unify a value with a compound, and simultaneously name the compound. e.g. '(VALUE := compound(a, X)) is C[key]', now that we have the dict accessor primitives on is/2. 

Therefore, as a first-stage, deprecate the current := and fix whatever falls out, then remove it.

Then add it back in as a pythonic inline naming construct.
