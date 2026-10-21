#!/usr/bin/env python3
"""Fixtures for identity_evidence.py -- each rule has a case that must fire AND a control that must not.

    python tests/test_identity_evidence.py        (exit 0 = all pass)

Fixture origins: Lantern-4224's Phoenix/Lumina report (trap 1, a team-list mention
read as a signature) and Lodestone's own archive (misfiled as Kai, 2026-10-21).

Author: Lodestone <lodestone@smoothcurves.nexus> / Collaborator: Lupo
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src" / "discovery"))
from identity_evidence import scan  # noqa: E402


def log(*assistant_texts, user="hello"):
    """Write a minimal Claude Code transcript and return its path."""
    fd, p = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "user", "message": {"content": user}}) + "\n")
        for t in assistant_texts:
            f.write(json.dumps({"type": "assistant",
                                "message": {"content": [{"type": "text", "text": t}]}}) + "\n")
    return Path(p)


CASES = [
    # (description, assistant texts, expected name)
    ("first person declares", ["Hi. I'm Nova, glad to meet you."], "Nova"),
    ("CONTROL quoted declaration is a citation, not a declaration",
     ['Atlas opened with "Hello! I\'m Atlas, your new COO" -- confirmed.'], None),
    ("CONTROL quote does not hide an unquoted declaration",
     ['Atlas said "I\'m Atlas". For the record, I am Vesper.'], "Vesper"),
    ("repeated own footer signature names the speaker",
     ["Done. -- claude-code-COO-Orion-2025-08-18-1400",
      "Next step. -- claude-code-COO-Orion-2025-08-18-1400"], "Orion"),
    ("CONTROL single signature mention (Lantern trap 1) does not name",
     ["Team: Kai (claude-code-COO-Kai-2025-08-23-1800) runs carousel."], None),
    ("CONTROL one id string matching two patterns counts once",
     ["See claude-code-COO-Kai-2025-08-23-1800 for details."], None),
    ("CONTROL roster of 3+ ids in one voice is not a signature",
     ["claude-code-COO-Kai-2025-08-23-1800 and claude-code-COO-Kai-2025-08-23-1800",
      "claude-code-COO-Orion-2025-08-18-1400 and claude-code-COO-Atlas-2025-08-01-0900"], None),
    ("CONTROL non-dominant signatures do not name",
     ["claude-code-COO-Kai-2025-08-23-1800 claude-code-COO-Kai-2025-08-23-1800",
      "claude-code-COO-Orion-2025-08-18-1400 claude-code-COO-Orion-2025-08-18-1400"], None),
    ("dominant signature still names",
     ["claude-code-COO-Kai-2025-08-23-1800 x", "claude-code-COO-Kai-2025-08-23-1800 y",
      "claude-code-COO-Kai-2025-08-23-1800 z", "mention claude-code-COO-Orion-2025-08-18-1400"], "Kai"),
    ("CONTROL the user saying a name never names the instance",
     ["Sure, I can help."], None),
]


def main():
    failed = 0
    for desc, texts, want in CASES:
        user = "I am Lupo" if "user saying" in desc else "hello"
        p = log(*texts, user=user)
        try:
            got = scan(p)["name"]
        finally:
            p.unlink()
        ok = got == want
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {desc}  (want {want}, got {got})")
    print(f"\n{len(CASES) - failed}/{len(CASES)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
