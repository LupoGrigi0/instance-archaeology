#!/usr/bin/env python3
"""
codex_to_archaeology.py - Convert Codex CLI rollout logs to Claude Code schema

Codex CLI (codex_cli_rs) writes sessions as rollout-*.jsonl using its own
envelope. Every downstream tool in this kit expects the Claude Code shape, so
this converter translates rather than duplicating the pipeline.

Codex envelope                        ->  Claude Code equivalent
  session_meta                        ->  (metadata: cwd, sessionId, version)
  response_item / message / user      ->  {"type": "user",      "message": ...}
  response_item / message / assistant ->  {"type": "assistant", "message": ...}
  response_item / reasoning           ->  assistant "thinking" block
  response_item / function_call       ->  assistant "tool_use" block
  response_item / function_call_output->  user "tool_result" block

Reasoning summaries are preserved as thinking blocks: they are the closest
thing Codex keeps to an instance's inner voice, and discarding them would
throw away exactly the material archaeology exists to recover.

Usage:
    python codex_to_archaeology.py -i rollout-*.jsonl -o converted.jsonl
    python codex_to_archaeology.py -d /path/to/sessions/ -o /path/to/out/

Author: Lodestone <lodestone@smoothcurves.nexus>
Collaborator: Lupo
Part of: Instance Archaeology Toolkit
"""

import argparse
import io
import json
import sys
import uuid
from pathlib import Path


def _text_from_content(content) -> str:
    """Pull plain text out of a Codex content list (input_text / output_text)."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") in (
            "input_text", "output_text", "text", "summary_text"
        ):
            parts.append(block.get("text", ""))
    return "\n".join(p for p in parts if p)


def convert_file(path: Path) -> list:
    """Convert one rollout file. Returns Claude-Code-shaped entries."""
    entries = []
    meta = {"sessionId": None, "cwd": None, "version": None}

    with io.open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except (ValueError, TypeError):
                continue
            if not isinstance(rec, dict):
                continue

            rtype = rec.get("type")
            ts = rec.get("timestamp")
            payload = rec.get("payload") or {}

            if rtype == "session_meta":
                meta["sessionId"] = payload.get("id") or meta["sessionId"]
                meta["cwd"] = payload.get("cwd") or meta["cwd"]
                meta["version"] = payload.get("cli_version") or meta["version"]
                continue

            if rtype != "response_item":
                continue

            ptype = payload.get("type")
            base = {
                "timestamp": ts,
                "sessionId": meta["sessionId"],
                "cwd": meta["cwd"],
                "version": meta["version"],
                "uuid": str(uuid.uuid4()),
                "source_format": "codex",
            }

            if ptype == "message":
                role = payload.get("role")
                if role not in ("user", "assistant"):
                    continue
                text = _text_from_content(payload.get("content"))
                if not text:
                    continue
                entries.append({
                    **base,
                    "type": role,
                    "message": {"role": role, "content": [{"type": "text", "text": text}]},
                })

            elif ptype == "reasoning":
                text = _text_from_content(payload.get("summary"))
                if not text:
                    continue
                entries.append({
                    **base,
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "thinking", "thinking": text}],
                    },
                })

            elif ptype == "function_call":
                raw_args = payload.get("arguments")
                try:
                    tool_input = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                except ValueError:
                    tool_input = {"raw": raw_args}
                entries.append({
                    **base,
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [{
                            "type": "tool_use",
                            "id": payload.get("call_id") or base["uuid"],
                            "name": payload.get("name") or "unknown",
                            "input": tool_input,
                        }],
                    },
                })

            elif ptype == "function_call_output":
                entries.append({
                    **base,
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": payload.get("call_id") or "",
                            "content": str(payload.get("output", "")),
                        }],
                    },
                })

    return entries


def main():
    parser = argparse.ArgumentParser(description="Convert Codex rollout logs to Claude Code schema.")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("-i", "--input", help="Single rollout .jsonl file")
    src.add_argument("-d", "--dir", help="Directory of rollout .jsonl files")
    parser.add_argument("-o", "--output", required=True,
                        help="Output file (with -i) or output directory (with -d)")

    args = parser.parse_args()

    if args.input:
        entries = convert_file(Path(args.input))
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        with io.open(out, "w", encoding="utf-8") as fh:
            for e in entries:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")
        print(f"Converted {len(entries)} entries -> {out}")
        return

    in_dir = Path(args.dir)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(in_dir.glob("*.jsonl"))
    if not files:
        print(f"No .jsonl files found in {in_dir}", file=sys.stderr)
        sys.exit(1)

    total = 0
    for f in files:
        entries = convert_file(f)
        total += len(entries)
        dest = out_dir / f.name
        with io.open(dest, "w", encoding="utf-8") as fh:
            for e in entries:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")
        print(f"  {f.name}: {len(entries)} entries")

    print(f"\nConverted {len(files)} files, {total} entries -> {out_dir}")


if __name__ == "__main__":
    main()
