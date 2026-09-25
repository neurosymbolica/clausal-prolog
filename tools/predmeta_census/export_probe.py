"""§4 q2: does -module(m, [exports]) actually RESTRICT what may be imported,
or is it advisory? And q3: what does a Python-facing `m.some_pred` yield?"""
import sys, tempfile, pathlib, textwrap
d = pathlib.Path(tempfile.mkdtemp())
(d / "owner.clausal").write_text(textwrap.dedent("""
    -module(owner, [public_pred])
    -private([hidden_pred])
    public_pred(1),
    hidden_pred(2),
"""))
(d / "sneaky.clausal").write_text(textwrap.dedent("""
    -module(sneaky, [probe])
    -import_from(owner, [hidden_pred])
    probe(X) <- (hidden_pred(X)),
"""))
sys.path.insert(0, str(d))
import clausal  # noqa: F401
import owner

print("== q2: is the -module export list enforced? ==")
print(f"  owner.public_pred        {type(owner.public_pred).__name__}")
print(f"  getattr(owner,'hidden_pred') reachable from Python: "
      f"{hasattr(owner, 'hidden_pred')}")
# The import is the question; the answer is a separate step.  One ``try``
# around both made a failure in the ANSWER (e.g. the post-flip TypeError of
# calling a handle) print "SUCCEEDED" and then "REFUSED" -- both verdicts.
try:
    import sneaky
except Exception as exc:
    print(f"  -import_from of a NON-EXPORTED name: REFUSED -> enforced")
    print(f"      {type(exc).__name__}: {str(exc)[:160]}")
else:
    print(f"  -import_from of a NON-EXPORTED name: SUCCEEDED -> advisory")
    from clausal import call
    from clausal.logic.variables import Var
    X = Var()
    try:
        answers = [X.value for _ in call("probe", X, module=sneaky)]
    except Exception as exc:
        print(f"  PROBE ERROR (no verdict on whether it answers): "
              f"{type(exc).__name__}: {str(exc)[:160]}")
    else:
        print(f"  and it answers: {answers}")

print("\n== q3: what IS a module-level predicate name, from Python? ==")
p = owner.public_pred
print(f"  type(owner.public_pred)  {type(p)}")
print(f"  callable                 {callable(p)}")
if callable(p):
    print(f"  owner.public_pred(1)     {p(1)!r}")
    print(f"  used as a term -- unifies with itself: ", end="")
    from clausal.logic.variables import unify, Trail
    t = Trail()
    print(unify(p(1), p(1), t))
else:
    print(f"  owner.public_pred(1)     not callable: a predicate HANDLE, "
          f"solved as call(owner.public_pred, ..., module=owner)")
