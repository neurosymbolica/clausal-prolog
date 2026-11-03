"""First divergence between a port trace and a Scryer trace (same naming)."""
import re, sys
def events(path, kind):
    out = []
    lines = open(path).read().split("after posting the chain:")[1].splitlines()
    for line in lines:
        l = line.strip()
        if kind == "scryer":
            l = l.lower()
            m = re.match(r"verify_lin (\w+) = (\S+) \(", l)
            if m: out.append(f"verify {m[1]}={m[2]}"); continue
            m = re.match(r"solve (\d) (\w+)", l)
            if m: out.append(f"solve {m[1]} {m[2]}"); continue
            m = re.match(r"solve_for_variable (\w+)", l)
            if m: out.append(f"solve_for_variable {m[1]}"); continue
            m = re.match(r"(bs|bs_collect) (\w+) := .*rewrote:(.*) ; read (\d+)", l)
            if m: out.append(f"{m[1]} {m[2]} rewrote [{m[3].strip()}]"); continue
            m = re.match(r"pivot(_ignoring_bounds)? (\w+) (\w+)", l)
            if m: out.append(l); continue
        else:
            l = l.lower()
            m = re.match(r"verify (\w+) = (\S+)", l)
            if m: out.append(f"verify {m[1]}={m[2]}"); continue
            m = re.match(r"solve (\d) (\w+)", l)
            if m: out.append(f"solve {m[1]} {m[2]}"); continue
            m = re.match(r"solve_for_variable (\w+)", l)
            if m: out.append(f"solve_for_variable {m[1]}"); continue
            m = re.match(r"(bs|bs_collect) (\w+) := .*rewrote \d+:(.*)", l)
            if m: out.append(f"{m[1]} {m[2]} rewrote [{m[3].strip()}]"); continue
            m = re.match(r"pivot(_ignoring_bounds)? (\w+) (\w+)", l)
            if m: out.append(l); continue
    return out
p, s = events(sys.argv[1], "port"), events(sys.argv[2], "scryer")
# Scryer also traces verify_lin of implied slack bindings; the port runs those
# through bind_queued -> verify_bound too, so both lists carry them.
for i, (a, b) in enumerate(zip(p, s)):
    if a != b:
        print(f"first divergence at event {i}:\n  port:   {a}\n  scryer: {b}")
        print("  context port:  ", p[max(0,i-3):i+3]); print("  context scryer:", s[max(0,i-3):i+3])
        break
else:
    print("identical" if len(p) == len(s) else f"prefix equal; lengths {len(p)} vs {len(s)}")
print(f"events: port {len(p)}, scryer {len(s)}")
