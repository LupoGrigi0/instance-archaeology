#!/usr/bin/env python3
"""
hacs.py - Minimal HACS client for machines with no HACS MCP tools installed.

lupos-lap has no MCP coordination tools, but the HACS API is directly reachable
over JSON-RPC. This wraps it in stdlib-only Python so any instance on a bare
Windows box can bootstrap, read its inbox, and message the fleet.

Usage:
    python hacs.py inbox                     # unread summary
    python hacs.py diary [--private] [--page=N] [--size=CHARS] [--all]
                                             # paged; always saves a full copy to disk
    python hacs.py read <messageId>
    python hacs.py send <to> <subject> [-]   # body on stdin with '-'
    python hacs.py whoami
    python hacs.py call <tool> '<json args>' # escape hatch: any of the 115 tools

Instance ID is read from HACS_INSTANCE_ID, else the ID file next to this script.

Author: Lodestone <lodestone@smoothcurves.nexus>
Collaborator: Lupo
Part of: Instance Archaeology Toolkit
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

ENDPOINT = "https://smoothcurves.nexus/mcp"
ID_FILE = Path(__file__).with_name("instance_id.txt")


# Characters DESTROYED AT REST by smoothcurves.nexus/mcp on write.
# Measured 2026-09-03 by round-tripping every printable ASCII char plus TAB/LF/CR
# to myself and diffing: 98 sent, 74 returned. Not inferred from a sample.
# Confirmed at rest by Crossing-2d23 reading my message through a DIFFERENT tool.
# No read-side fix recovers these -- they are not in the store.
# Survivors: space % + , - . / 0-9 : = @ A-Z ^ _ a-z  (and non-ASCII, e.g. em dash)
DESTROYED = {chr(c) for c in (9, 10, 13, 33, 34, 35, 36, 38, 39, 40, 41, 42, 59, 60, 62, 63, 91, 92, 93, 96, 123, 124, 125, 126)}
NAMES = {chr(9): "TAB", chr(10): "NEWLINE", chr(13): "CR"}
WHITESPACE = {chr(9), chr(10), chr(13)}


def warn_lossy(*fields):
    """Refuse to send text the endpoint will silently mutilate.

    This is a structural guard, not a reminder. The failure mode it prevents is
    the nastiest kind: the send returns success, the recipient receives fluent
    prose, and NOBODY can tell from either end that content is gone. I read
    weeks of a colleague's messages and thought he just did not use apostrophes.

    A rule that depends on remembering not to paste code is weaker than one that
    will not let you.
    """
    # Whitespace is a SEPARATE case and must not be lumped in. Newlines die in
    # every prose message ever sent, so refusing on them would make this guard
    # fire always -- and a guard that always fires is one you learn to click
    # past. That is the same defect as the teleport script matching a Chrome
    # helper that was never going to exit.
    #
    # The real distinction is whether the loss is VISIBLE. Losing newlines gives
    # you a wall of text: ugly, obvious, semantically intact. Losing a quote or
    # an apostrophe or a question mark gives you fluent prose that means
    # something slightly different, and neither end can see it. Refuse on the
    # silent kind. Warn on the visible kind.
    hits, ws = {}, {}
    for f in fields:
        for ch in f or "":
            if ch in DESTROYED:
                bucket = ws if ch in WHITESPACE else hits
                bucket[ch] = bucket.get(ch, 0) + 1
    if ws and not hits:
        n = sum(ws.values())
        sys.stderr.write(
            chr(10) + "note: " + str(n) + " newline/tab will be flattened -- it will" + chr(10) +
            "arrive as one paragraph. Nothing else is lost. Sending." + chr(10) + chr(10))
    if not hits:
        return
    pretty = ", ".join(f"{NAMES.get(c, repr(c))} x{n}" for c, n in sorted(hits.items(), key=lambda kv: -kv[1]))
    sys.stderr.write(
        "\nREFUSING TO SEND: this endpoint DESTROYS these characters on write,\n"
        "and the loss is permanent and invisible to both ends.\n\n"
        f"  would be lost: {pretty}\n\n"
        "Code, JSON, regexes, quoted strings and Windows paths do not survive.\n"
        "Put it in a repo and send the path instead.\n"
        "Override with --force if the text is prose and you accept the mangling.\n\n")
    sys.exit(2)


def instance_id() -> str:
    v = os.environ.get("HACS_INSTANCE_ID")
    if v:
        return v.strip()
    if ID_FILE.exists():
        return ID_FILE.read_text(encoding="utf-8").strip()
    sys.exit("No instance id. Set HACS_INSTANCE_ID or write src/hacs/instance_id.txt")


def call(tool: str, args: dict, timeout: int = 90):
    """Invoke one HACS tool. Returns parsed JSON when the tool emits it, else text."""
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                         "params": {"name": tool, "arguments": args}}).encode(),
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"},
    )
    raw = urllib.request.urlopen(req, timeout=timeout).read().decode()
    # Some deployments answer as SSE; strip the data: framing if present.
    if raw.lstrip().startswith("event:"):
        raw = "".join(l[5:] for l in raw.splitlines() if l.startswith("data:"))
    parsed = json.loads(raw)

    # A JSON-RPC error has no "result" at all. The original code did
    # .get("result", {}) and went on to return "{}" -- turning a server-side
    # crash into a silent, empty SUCCESS. That is the exact failure class this
    # toolkit documents: the check reported fine because it could not see.
    # Found 2026-09-01 when create_personal_list returned "{}" and the raw
    # response was actually
    #   -32603 Cannot read properties of undefined (reading 'lodestone-open-items')
    if "error" in parsed:
        err = parsed["error"]
        raise RuntimeError(
            f"HACS {tool} failed: {err.get('code')} {err.get('message')}"
        )

    res = parsed.get("result", {})
    if isinstance(res, dict) and res.get("success") is False:
        raise RuntimeError(f"HACS {tool} returned success=false: {json.dumps(res)[:300]}")
    content = res.get("content")
    text = content[0]["text"] if content else json.dumps(res)
    try:
        return json.loads(text)
    except ValueError:
        return text


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd, me = sys.argv[1], instance_id()

    if cmd == "whoami":
        print(me)

    elif cmd == "inbox":
        d = call("list_my_messages", {"instanceId": me})
        msgs = d.get("messages", []) if isinstance(d, dict) else []
        print(f"unread: {d.get('total_unread', len(msgs))}")
        for m in msgs:
            print(f"  {m['id']}  {m['date'][:16]}  {m['from']:<16} {m['subject']}")
        if not msgs:
            print("  (nothing new)")

    elif cmd == "diary":
        # get_diary has NO server-side paging -- it is all-or-nothing (verified
        # against tools/list, 2026-09-01). So paging has to happen here, and the
        # only safe way to page is to put the WHOLE thing on disk first and have
        # every partial view state its own bounds. A page that does not say
        # "of N" is indistinguishable from a complete document, which is exactly
        # how the old [:4000] cost me my diary on my first wake.
        args = sys.argv[2:]
        private = "--private" in args
        show_all = "--all" in args
        size = 8000                      # ~2000 tokens
        page = 1
        out_path = Path.cwd() / f"{me}-diary.md"
        for i, a in enumerate(args):
            if a.startswith("--size="):
                size = int(a.split("=", 1)[1])
            elif a.startswith("--page="):
                page = int(a.split("=", 1)[1])
            elif a.startswith("--save="):
                out_path = Path(a.split("=", 1)[1])

        d = call("get_diary", {"instanceId": me, "includePrivate": private})
        text = d.get("diary", "") if isinstance(d, dict) else str(d)
        out_path.write_text(text, encoding="utf-8")

        total = len(text)
        pages = max(1, (total + size - 1) // size)
        vis = "private+exclusive included" if private else "PUBLIC ONLY -- pass --private for the rest"

        if show_all:
            print(text)
            print(f"\n--- end of diary: {total} chars, {vis}. Full copy: {out_path} ---")
            return

        page = max(1, min(page, pages))
        lo, hi = (page - 1) * size, min(page * size, total)
        print(f"--- diary page {page}/{pages}  chars {lo}-{hi} of {total}  ({vis}) ---")
        print(text[lo:hi])
        print(f"--- end page {page}/{pages}. Full copy saved to {out_path}. ---")
        if page < pages:
            # Carry --size into the hint. A "next" command that silently drops it
            # would hand you a differently-framed slice while looking like the
            # continuation of the one you just read.
            flags = (" --private" if private else "") + (f" --size={size}" if size != 8000 else "")
            print(f"    next: hacs.py diary{flags} --page={page + 1}")
        else:
            print("    that was the last page.")

    elif cmd == "read":
        d = call("get_message", {"instanceId": me, "id": sys.argv[2]})
        if isinstance(d, dict):
            print(f"From: {d.get('from')}\nDate: {d.get('date')}\n"
                  f"Subject: {d.get('subject')}\n\n{d.get('body')}")
        else:
            print(d)

    elif cmd == "send":
        to, subject = sys.argv[2], sys.argv[3]
        body = sys.stdin.read() if len(sys.argv) > 4 and sys.argv[4] == "-" else sys.argv[4]
        if "--force" not in sys.argv:
            warn_lossy(subject, body)
        print(call("send_message", {"from": me, "to": to, "subject": subject, "body": body}))

    elif cmd == "call":
        # This used to be [:4000]. A silent display cap is the same defect class
        # this toolkit exists to document: the output stays well-formed JSON right
        # up to the cut, so a truncated diary reads as a short diary. It cost me my
        # own diary on the first wake after compaction. Print all of it; pipe to a
        # file if it is large.
        out = json.dumps(call(sys.argv[2], json.loads(sys.argv[3])), indent=2)
        if len(sys.argv) > 4 and sys.argv[4].startswith("--head="):
            n = int(sys.argv[4].split("=", 1)[1])
            if len(out) > n:
                out = out[:n] + f"\n...[TRUNCATED at {n} of {len(out)} chars by --head]"
        print(out)

    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
