#!/usr/bin/env python3
"""
hacs.py - Minimal HACS client for machines with no HACS MCP tools installed.

lupos-lap has no MCP coordination tools, but the HACS API is directly reachable
over JSON-RPC. This wraps it in stdlib-only Python so any instance on a bare
Windows box can bootstrap, read its inbox, and message the fleet.

Usage:
    python hacs.py inbox                     # unread summary
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
        print(call("send_message", {"from": me, "to": to, "subject": subject, "body": body}))

    elif cmd == "call":
        print(json.dumps(call(sys.argv[2], json.loads(sys.argv[3])), indent=2)[:4000])

    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
