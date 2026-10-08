"""
test_inbox.py - P3: `hacs.py inbox` must never turn "could not look" into "unread: 0".

Swaps hacs.call for a fake hub, runs main() with argv, and checks the printed
line and the exit code. No network, no real inbox. Run:

    PYTHONIOENCODING=utf-8 python src/hacs/test_inbox.py

Exit 0 = all passed. Written to FAIL against the pre-P3 hacs.py (the control).

Author: Lodestone <lodestone@smoothcurves.nexus>
Collaborator: Lupo
"""
import io
import json
import os
import sys
from contextlib import redirect_stdout
from urllib.error import URLError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("HACS_INSTANCE_ID", "Test-0000")
import hacs  # noqa: E402

MSG = {"id": "m1", "date": "2026-10-08T10:00:00Z", "from": "axiom", "subject": "hello"}


def run(reply, *args):
    """reply: a value the fake hub returns, or an exception it raises."""
    def fake(tool, a, timeout=90):
        if isinstance(reply, BaseException):
            raise reply
        return reply
    hacs.call = fake
    sys.argv = ["hacs.py", "inbox", *args]
    buf, code = io.StringIO(), 0
    try:
        with redirect_stdout(buf):
            hacs.main()
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
    except Exception as e:  # the pre-P3 code crashed on a non-dict reply
        code = f"crash:{type(e).__name__}"
    return buf.getvalue(), code


results = []
def check(name, got, want):
    ok = got == want
    results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f" -- got {got!r} wanted {want!r}"))


# Looked, and the inbox is empty. MEASURED shape 2026-10-08: no total_unread at all.
out, code = run({"success": True, "hint": "x", "messages": []})
check("empty inbox (no total_unread field) -> unread: 0", out.splitlines()[0], "unread: 0")
check("and exit 0", code, 0)

out, code = run({"success": True, "messages": [MSG]})
check("one message -> unread: 1", out.splitlines()[0], "unread: 1")

out, code = run({"success": True, "messages": [MSG] * 5, "total_unread": 11, "more_unread": True})
check("paged -> true total shown", out.splitlines()[0], "unread: 11")
check("and the page cap is said out loud", "+6 more unread" in out, True)

# Could NOT look. None of these may print a count.
for name, reply in [
    ("error object without messages", {"error": "room history failed"}),
    ("non-dict text reply", "Internal Server Error"),
    ("messages not a list", {"messages": None}),
    ("network failure", URLError("no route")),
    ("JSON-RPC error", RuntimeError("HACS list_my_messages failed: -32603 boom")),
]:
    out, code = run(reply)
    first = out.splitlines()[0] if out else ""
    check(f"{name} -> never 'unread: 0'", first.startswith("unread: 0"), False)
    check(f"{name} -> exit 3", code, 3)

# --json
out, code = run({"success": True, "messages": [MSG]}, "--json")
j = json.loads(out) if code == 0 else {}
check("--json looked -> ok true", j.get("ok"), True)
check("--json ids", j.get("ids"), ["m1"])
out, code = run(URLError("no route"), "--json")
j = json.loads(out) if out.strip().startswith("{") else {}
check("--json could not look -> ok false", j.get("ok"), False)
check("--json could not look -> exit 3", code, 3)

print(f"\n  {sum(results)} passed, {len(results) - sum(results)} failed")
sys.exit(0 if all(results) else 1)
