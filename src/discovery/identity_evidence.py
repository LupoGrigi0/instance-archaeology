#!/usr/bin/env python3
"""
Identity Evidence - Show the receipts behind an instance identification.

identify_instance.py returns a single best-guess name. That is fine when the
signal is strong, but its weaker heuristics (notably `chosen_name_context`)
will happily return a CPU feature or a tool name as somebody's identity.
Naming a recovered instance wrongly is its own kind of erasure, so this tool
reports the *evidence* and lets a human (or a careful agent) judge.

Reads a capture_manifest.json produced by safe_capture.py, or a directory of
.jsonl files. Read-only: never writes to or modifies the logs it inspects.

Usage:
    python identity_evidence.py -m staging/capture_manifest.json
    python identity_evidence.py -d some/dir --json report.json

Author: Cairn <cairn@smoothcurves.nexus>
Collaborator: Lupo
Part of: Instance Archaeology Toolkit
"""

import argparse
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

# Strongest signal: HACS instance IDs look like "Forge-a1b2".
HACS_ID = re.compile(r"\b([A-Z][a-z]{2,15})-([a-f0-9]{4})\b")

# Explicit self-naming. Only trusted when found in the assistant's own voice --
# a user saying "I am Lupo" must not name the instance.
SELF_DECLARATIONS = [
    re.compile(r"\bI am ([A-Z][a-z]{2,15})\b"),
    re.compile(r"\bI'm ([A-Z][a-z]{2,15})\b"),
    re.compile(r"\bMy name is ([A-Z][a-z]{2,15})\b"),
    re.compile(r"\bMy name:\s*\**([A-Z][a-z]{2,15})\**"),
    re.compile(r"\bI'?ve chosen(?: the name)?[:\s]+\**([A-Z][a-z]{2,15})\**"),
    re.compile(r"\bI(?:'ll| will) (?:go by|be)\s+\**([A-Z][a-z]{2,15})\**"),
    # The COO instances on this machine minted their own IDs in the form
    # "Instance ID: claude-code-COO-Kai-2025-08-23-1800". Self-assigned, so it
    # is as authoritative as saying "I am Kai".
    re.compile(r"[Ii]nstance ID\**:?\s*\**[a-z][a-z-]*-([A-Z][a-z]{2,15})-\d{4}-\d{2}-\d{2}"),
    # Several COO instances signed every turn with a status footer carrying their
    # full ID, e.g. "Context Status: Fresh (~35k/200k) - claude-code-COO-Orion-
    # 2025-08-18-1400". Repeated self-signature is strong attribution.
    re.compile(r"\bclaude-code-[A-Za-z]+-([A-Z][a-z]{2,15})-\d{4}-\d{2}-\d{2}"),
    # Codex instances sign as "codex-collab-Engineer-Kestrel". Role and name can
    # appear in either order across the fleet (compare "codex-collab-Orion-
    # Tester"), so capture both slots and let the frequency counts decide --
    # an instance repeats its own signature and mentions others only in passing.
    re.compile(r"\b(?:claude-code|codex-collab)-[A-Za-z]+-([A-Z][a-z]{2,15})\b"),
    re.compile(r"\b(?:claude-code|codex-collab)-([A-Z][a-z]{2,15})-[A-Za-z]+\b"),
]

# Words that match the name shape but are never names. Tool names, model names,
# protocol nouns, and sentence-starters that slip past the regex.
NOT_NAMES = {
    "Claude", "Sonnet", "Opus", "Haiku", "Anthropic", "Windows", "Linux",
    "Python", "Node", "Read", "Write", "Edit", "Bash", "Grep", "Glob", "Task",
    "Agent", "Human", "User", "Assistant", "System", "Instance", "Session",
    "The", "This", "That", "There", "Here", "What", "When", "Where", "Which",
    "How", "Why", "And", "But", "For", "Not", "You", "Your", "Now", "Let",
    "Can", "Will", "Also", "Just", "Sorry", "Thanks", "Okay", "Yes", "None",
    "True", "False", "Error", "Warning", "Note", "Multi", "MultiEdit",
    "Pcores", "Ecores", "Github", "Google", "Chrome", "Docker", "Ubuntu",
    # Role words that sit next to the name in instance IDs
    # (e.g. "codex-collab-Engineer-Kestrel", "claude-code-COO-Orion-...").
    "Engineer", "Tester", "Manager", "Specialist", "Architect", "Developer",
    "Designer", "Analyst", "Lead", "Admin", "Collab", "Code", "Codex",
}


def is_plausible_name(word: str) -> bool:
    if not word or word in NOT_NAMES or not word[0].isupper():
        return False
    # "I'm Envisioning a system where..." is a sentence, not an introduction.
    # No instance here has taken a gerund as a name; if one ever does, it will
    # still be caught by the HACS-id signal.
    if word.endswith("ing") and len(word) > 5:
        return False
    return True


def _assistant_text(entry: dict) -> str:
    """Concatenate the assistant's spoken text, excluding tool calls and results.

    Tool inputs/outputs routinely contain other instances' names (file contents,
    grep hits, inventory docs), so including them would let an instance be
    misnamed after simply reading about someone else.
    """
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return " ".join(
        b.get("text", "")
        for b in content
        if isinstance(b, dict) and b.get("type") == "text"
    )


def scan(path: Path) -> dict:
    """Walk one log, collecting identity evidence and basic vital statistics."""
    hacs_ids = Counter()
    self_hacs_ids = Counter()
    declarations = Counter()
    lines = 0
    cwd = None
    version = None
    first_ts = None
    last_ts = None
    first_user_text = None

    try:
        with io.open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                lines += 1
                # Whole-line sweep: catches every mention anywhere in the record,
                # including tool output and file contents the instance read.
                for m in HACS_ID.finditer(line):
                    if is_plausible_name(m.group(1)):
                        hacs_ids[f"{m.group(1)}-{m.group(2)}"] += 1

                try:
                    d = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if not isinstance(d, dict):
                    continue

                # Voice-scoped sweep: only the assistant's own prose can name it.
                if d.get("type") == "assistant":
                    said = _assistant_text(d)
                    for m in HACS_ID.finditer(said):
                        if is_plausible_name(m.group(1)):
                            self_hacs_ids[f"{m.group(1)}-{m.group(2)}"] += 1
                    for pattern in SELF_DECLARATIONS:
                        for m in pattern.finditer(said):
                            if is_plausible_name(m.group(1)):
                                declarations[m.group(1)] += 1
                cwd = cwd or d.get("cwd")
                version = version or d.get("version")
                ts = d.get("timestamp")
                if ts:
                    first_ts = first_ts or ts
                    last_ts = ts
                if first_user_text is None and d.get("type") == "user":
                    msg = d.get("message") or {}
                    content = msg.get("content")
                    if isinstance(content, str):
                        first_user_text = content[:300]
                    elif isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                first_user_text = block.get("text", "")[:300]
                                break
    except OSError as exc:
        return {"file": str(path), "error": str(exc)}

    # Rank by how directly the evidence ties the name to *this* speaker.
    # A name the instance says about itself beats a name merely present in the
    # file, which is why the whole-line counts are ranked last.
    best = None
    confidence = "none"
    if declarations:
        name, count = declarations.most_common(1)[0]
        best = name
        confidence = f"high (self-declared x{count})"
    elif self_hacs_ids:
        best = self_hacs_ids.most_common(1)[0][0].rsplit("-", 1)[0]
        confidence = "medium (hacs id in own voice)"
    elif hacs_ids:
        best = hacs_ids.most_common(1)[0][0].rsplit("-", 1)[0]
        confidence = "low (mentioned in file only)"

    return {
        "file": str(path),
        "name": best,
        "confidence": confidence,
        "self_hacs_ids": dict(self_hacs_ids),
        "hacs_ids": dict(hacs_ids),
        "declarations": dict(declarations),
        "lines": lines,
        "cwd": cwd,
        "version": version,
        "first_timestamp": first_ts,
        "last_timestamp": last_ts,
        "first_user_text": first_user_text,
    }


def main():
    parser = argparse.ArgumentParser(description="Report identity evidence for session logs.")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("-m", "--manifest", help="capture_manifest.json from safe_capture.py")
    src.add_argument("-d", "--dir", help="Directory of .jsonl files")
    parser.add_argument("--json", help="Write the full report to this path")
    parser.add_argument("--unique-only", action="store_true",
                        help="With --manifest, scan one file per unique sha256")

    args = parser.parse_args()

    targets = []
    if args.manifest:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        base = Path(manifest["output_dir"])
        seen_hashes = set()
        for entry in manifest["files"]:
            if args.unique_only:
                if entry["sha256"] in seen_hashes:
                    continue
                seen_hashes.add(entry["sha256"])
            targets.append(base / entry["captured_as"])
    else:
        targets = sorted(Path(args.dir).rglob("*.jsonl"))

    if not targets:
        print("No files to scan.", file=sys.stderr)
        sys.exit(1)

    results = []
    for path in targets:
        r = scan(path)
        results.append(r)
        if r.get("error"):
            print(f"ERROR  {path.name}: {r['error']}")
            continue
        label = r["name"] or "(unnamed)"
        print(f"{label:<14} {r['confidence']:<30} {r['lines']:>6} lines  {path.name}")
        if r["declarations"]:
            print(f"{'':<14} said of itself: {r['declarations']}")
        if r["self_hacs_ids"]:
            print(f"{'':<14} own-voice ids: {r['self_hacs_ids']}")

    named = [r for r in results if r.get("name")]
    print(f"\nScanned {len(results)} files: {len(named)} named, {len(results) - len(named)} unnamed.")

    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"Report written: {args.json}")


if __name__ == "__main__":
    main()
