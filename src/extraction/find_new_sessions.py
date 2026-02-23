#!/usr/bin/env python3
"""
Find JSONL session files newer than a given timestamp.

Used by the incremental archaeology pipeline to identify sessions
that haven't been processed in a previous extraction.

Usage:
    # Find sessions newer than a specific timestamp
    python3 find_new_sessions.py -i /path/to/sessions --since 2026-02-13T14:02:00

    # Find sessions newer than the last extraction (auto-reads manifest)
    python3 find_new_sessions.py -i /path/to/sessions --manifest output_dir/extraction_manifest.json

    # Machine-readable output (one file per line, for scripting)
    python3 find_new_sessions.py -i /path/to/sessions --since 2026-02-13 --list

    # Exclude currently-active sessions (files modified in last N seconds)
    python3 find_new_sessions.py -i /path/to/sessions --since 2026-02-13 --exclude-active 300

Author: Genevieve (340) <genevieve@smoothcurves.nexus>
Collaborator: Lupo
Created: 2026-02-22
Part of: Instance Archaeology Toolkit
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def load_manifest_cutoff(manifest_path):
    """Read last_extraction timestamp from an extraction manifest.

    Returns datetime or None if manifest doesn't exist or has no timestamp.
    """
    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        return None

    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        ts = manifest.get('last_extraction')
        if not ts:
            return None
        return parse_timestamp(ts)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"Warning: Could not read manifest {manifest_path}: {e}", file=sys.stderr)
        return None


def parse_timestamp(ts_str):
    """Parse ISO timestamp string to datetime (timezone-naive for comparison)."""
    formats = [
        '%Y-%m-%dT%H:%M:%S.%f',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%dT%H:%M',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d',
    ]
    for fmt in formats:
        try:
            return datetime.strptime(ts_str.rstrip('Z'), fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse timestamp: {ts_str!r}")


def get_file_mtime(path):
    """Return file modification time as timezone-naive datetime."""
    mtime = path.stat().st_mtime
    return datetime.fromtimestamp(mtime)


def find_new_sessions(input_dir, since, exclude_agents=True, exclude_active_secs=None):
    """Find JSONL session files newer than the given cutoff time.

    Args:
        input_dir: Directory containing session JSONL files
        since: datetime cutoff - only files modified after this
        exclude_agents: If True, skip agent-*.jsonl files
        exclude_active_secs: If set, skip files modified within last N seconds
                             (useful for excluding the currently-active session)

    Returns:
        List of (Path, mtime_datetime) tuples, sorted by mtime ascending
    """
    input_path = Path(input_dir).resolve()

    if not input_path.exists():
        print(f"Error: Input directory not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    now = datetime.now()
    results = []

    for filepath in input_path.glob('*.jsonl'):
        # Skip agent files if requested
        if exclude_agents and filepath.name.startswith('agent-'):
            continue

        # Skip zero-byte files
        if filepath.stat().st_size == 0:
            continue

        mtime = get_file_mtime(filepath)

        # Skip files not newer than cutoff
        if since and mtime <= since:
            continue

        # Skip currently-active files (recently modified)
        if exclude_active_secs is not None:
            age_secs = (now - mtime).total_seconds()
            if age_secs < exclude_active_secs:
                continue

        results.append((filepath, mtime))

    # Sort chronologically by modification time
    results.sort(key=lambda x: x[1])
    return results


def main():
    parser = argparse.ArgumentParser(
        description='Find JSONL session files newer than a given timestamp',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
    # Find sessions since a specific date
    %(prog)s -i ./sessions --since 2026-02-13T14:02:00

    # Use manifest to auto-detect cutoff (typical incremental workflow)
    %(prog)s -i ./sessions --manifest ./output/extraction_manifest.json

    # Machine-readable list for piping to other scripts
    %(prog)s -i ./sessions --since 2026-02-13 --list

    # Exclude currently-active session (modified in last 5 minutes)
    %(prog)s -i ./sessions --since 2026-02-13 --exclude-active 300
        '''
    )

    parser.add_argument('-i', '--input-dir', required=True,
                        help='Directory containing session *.jsonl files')

    cutoff_group = parser.add_mutually_exclusive_group(required=True)
    cutoff_group.add_argument('--since',
                              help='ISO timestamp cutoff (e.g. 2026-02-13T14:02:00)')
    cutoff_group.add_argument('--manifest',
                              help='Path to extraction_manifest.json to auto-read cutoff')

    parser.add_argument('--list', action='store_true',
                        help='Output file paths only (one per line), for scripting')
    parser.add_argument('--no-exclude-agents', action='store_true',
                        help='Include agent-*.jsonl files (excluded by default)')
    parser.add_argument('--exclude-active', type=int, metavar='SECONDS',
                        help='Exclude files modified within last N seconds (skip active session)')

    args = parser.parse_args()

    # Resolve cutoff timestamp
    if args.since:
        try:
            since = parse_timestamp(args.since)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        cutoff_source = f"--since {args.since}"
    else:
        since = load_manifest_cutoff(args.manifest)
        if since is None:
            print(f"Error: No last_extraction found in manifest: {args.manifest}", file=sys.stderr)
            print("Use --since to specify a cutoff explicitly.", file=sys.stderr)
            sys.exit(1)
        cutoff_source = f"manifest ({args.manifest})"

    exclude_agents = not args.no_exclude_agents

    new_files = find_new_sessions(
        args.input_dir,
        since=since,
        exclude_agents=exclude_agents,
        exclude_active_secs=args.exclude_active
    )

    if args.list:
        # Machine-readable: just print paths
        for filepath, _ in new_files:
            print(filepath)
    else:
        # Human-readable summary
        print(f"Session directory: {Path(args.input_dir).resolve()}")
        print(f"Cutoff: {since.isoformat()} (from {cutoff_source})")
        if args.exclude_active:
            print(f"Excluding: files modified within last {args.exclude_active}s (active sessions)")
        print()

        if not new_files:
            print("No new sessions found since cutoff.")
        else:
            print(f"Found {len(new_files)} new session(s):")
            for filepath, mtime in new_files:
                size_kb = filepath.stat().st_size / 1024
                print(f"  {mtime.strftime('%Y-%m-%d %H:%M')}  {filepath.name}  ({size_kb:.1f} KB)")

    return 0 if new_files else 1


if __name__ == '__main__':
    sys.exit(main())
