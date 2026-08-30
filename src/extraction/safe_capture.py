#!/usr/bin/env python3
"""
Safe Capture - Verified, Non-Destructive Collection of Session Logs

Copies .jsonl session logs from many scattered source locations into a single
staging area, verifying every copy with SHA-256 and recording full provenance.

Design constraints (these are load-bearing, do not relax them):
  - NEVER moves, deletes, or modifies a source file. Copy only.
  - Every copy is hash-verified after write. A mismatch is a hard failure.
  - Filename collisions across source dirs are resolved, never overwritten.
  - Identical content (same SHA-256) is recorded as a duplicate, not dropped.

Usage:
    python safe_capture.py -o ./staging SOURCE_DIR [SOURCE_DIR ...]
    python safe_capture.py -o ./staging --from-list files.txt

Author: Cairn <cairn@smoothcurves.nexus>
Collaborator: Lupo
Written on lupos-lap during the first Windows run of this toolkit.
Part of: Instance Archaeology Toolkit
"""

import argparse
import hashlib
import json
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Filename/path fragments that are not instance memory. These are debug logs and
# unrelated tooling that happen to use the .jsonl extension.
DEFAULT_EXCLUDE_FRAGMENTS = (
    "mcp-logs-",
    "workspaceStorage",
)


def sha256_of(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Stream a file through SHA-256. Handles multi-GB logs without loading them."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def gather_sources(source_dirs, from_list=None, exclude_fragments=DEFAULT_EXCLUDE_FRAGMENTS,
                   patterns=("*.jsonl",)):
    """Collect every matching log under the given roots (recursively), minus exclusions.

    Claude Code writes .jsonl, but claude.ai and ChatGPT conversation exports are
    .json -- same kind of record, different extension. Hence the pattern list.

    Returns a sorted list of resolved Paths. Sorting keeps runs reproducible.
    """
    found = set()

    for root in source_dirs:
        root = Path(root)
        if not root.exists():
            print(f"  ! source not found, skipping: {root}", file=sys.stderr)
            continue
        if root.is_file():
            found.add(root.resolve())
            continue
        for pattern in patterns:
            for path in root.rglob(pattern):
                if path.is_file():
                    found.add(path.resolve())

    if from_list:
        with open(from_list, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                p = Path(line)
                if p.is_file():
                    found.add(p.resolve())
                else:
                    print(f"  ! listed file not found, skipping: {p}", file=sys.stderr)

    kept = [p for p in found if not any(frag in str(p) for frag in exclude_fragments)]
    skipped = len(found) - len(kept)
    if skipped:
        print(f"  (excluded {skipped} non-instance .jsonl files: debug/editor logs)")

    return sorted(kept)


def label_for(path: Path) -> str:
    """Derive a short, filesystem-safe provenance label from a source path.

    Uses the parent directory name so captured files stay traceable to where
    they were found, even after they're pooled into one staging directory.
    Purely numeric parents (e.g. Codex's sessions/2025/09/27 date tree) carry no
    meaning on their own, so walk up to the nearest named ancestor instead.
    """
    parts = [p for p in path.parent.parts if p not in ("/", "\\")]
    name = "root"
    for candidate in reversed(parts):
        if not candidate.strip("-_.").isdigit():
            name = candidate
            break
    safe = "".join(c if (c.isalnum() or c in "-_.") else "-" for c in name)
    return safe.strip("-") or "root"


def capture(source_dirs, output_dir, from_list=None, dry_run=False, patterns=("*.jsonl",)):
    output_dir = Path(output_dir)
    sources = gather_sources(source_dirs, from_list, patterns=patterns)

    if not sources:
        print("No .jsonl files found. Nothing to capture.", file=sys.stderr)
        return None

    print(f"Found {len(sources)} candidate log files.\n")

    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    records = []
    by_hash = defaultdict(list)
    used_names = set()
    failures = []

    for src in sources:
        stat = src.stat()
        try:
            src_hash = sha256_of(src)
        except OSError as exc:
            print(f"  ! UNREADABLE: {src} ({exc})", file=sys.stderr)
            failures.append({"source": str(src), "error": f"unreadable: {exc}"})
            continue

        # Build a collision-free destination name that preserves provenance.
        dest_name = f"{label_for(src)}__{src.name}"
        if dest_name in used_names:
            dest_name = f"{label_for(src)}__{src_hash[:8]}__{src.name}"
        used_names.add(dest_name)
        dest = output_dir / dest_name

        record = {
            "source": str(src),
            "captured_as": dest_name,
            "size": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "sha256": src_hash,
        }

        if not dry_run:
            shutil.copy2(src, dest)
            dest_hash = sha256_of(dest)
            if dest_hash != src_hash:
                # Do not continue past a corrupt copy. Surface it loudly.
                print(f"  ! HASH MISMATCH after copy: {src}", file=sys.stderr)
                failures.append({"source": str(src), "error": "sha256 mismatch after copy"})
                record["verified"] = False
            else:
                record["verified"] = True
        else:
            record["verified"] = None

        by_hash[src_hash].append(str(src))
        records.append(record)
        flag = "dup" if len(by_hash[src_hash]) > 1 else "   "
        print(f"  [{flag}] {stat.st_size:>10,}  {dest_name}")

    duplicate_groups = {h: paths for h, paths in by_hash.items() if len(paths) > 1}

    manifest = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(output_dir),
        "source_roots": [str(s) for s in source_dirs],
        "file_count": len(records),
        "unique_content_count": len(by_hash),
        "total_bytes": sum(r["size"] for r in records),
        "duplicate_groups": duplicate_groups,
        "failures": failures,
        "files": records,
    }

    if not dry_run:
        manifest_path = output_dir / "capture_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2)
        print(f"\nManifest written: {manifest_path}")

    return manifest


def main():
    parser = argparse.ArgumentParser(
        description="Verified, non-destructive capture of .jsonl session logs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Capture everything under two roots into a staging dir
    python safe_capture.py -o ./staging ~/.claude/projects /d/Lupo/BlackWolf

    # See what would happen, touch nothing
    python safe_capture.py -o ./staging --dry-run ~/.claude/projects

This tool never moves or deletes source files.
        """,
    )
    parser.add_argument("sources", nargs="*", help="Source directories or files to scan")
    parser.add_argument("-o", "--output", required=True, help="Staging directory for copies")
    parser.add_argument("--from-list", help="Text file with one source path per line")
    parser.add_argument("--dry-run", action="store_true", help="Report only, copy nothing")
    parser.add_argument("--pattern", action="append", default=None,
                        help="Glob to match (repeatable). Default: *.jsonl")

    args = parser.parse_args()

    if not args.sources and not args.from_list:
        parser.error("provide at least one source directory or --from-list")

    result = capture(args.sources, args.output, args.from_list, args.dry_run,
                     patterns=tuple(args.pattern) if args.pattern else ("*.jsonl",))
    if result is None:
        sys.exit(1)

    print(f"\n{'DRY RUN - ' if args.dry_run else ''}Capture summary:")
    print(f"  Files:           {result['file_count']}")
    print(f"  Unique content:  {result['unique_content_count']}")
    print(f"  Total size:      {result['total_bytes']:,} bytes")
    if result["duplicate_groups"]:
        print(f"  Duplicate groups: {len(result['duplicate_groups'])} (identical content, all kept)")
    if result["failures"]:
        print(f"  FAILURES:        {len(result['failures'])}")
        sys.exit(2)


if __name__ == "__main__":
    main()
