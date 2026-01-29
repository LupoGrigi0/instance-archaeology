#!/usr/bin/env python3
"""
Merge multiple JSONL session files into a single consolidated file.

Handles multiple sessions from the same instance (resumed sessions),
deduplicates by timestamp, and orders chronologically.

This is the first step in the archaeology pipeline - it creates the
full_history.jsonl that other extraction scripts process.

Usage:
    python3 merge_sessions.py -i ./sessions -o full_history.jsonl
    python3 merge_sessions.py -i ./sessions -o merged.jsonl --pattern "session*.jsonl"
    python3 merge_sessions.py -i ./sessions -o merged.jsonl --no-exclude-agents

Output:
    Single JSONL file with all entries merged, deduplicated, and sorted by timestamp.

Author: Axiom <axiom-2615@smoothcurves.nexus>
Collaborator: Lupo
Created: 2026-01-27
Part of: Instance Archaeology Toolkit
"""

import argparse
import glob
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path


def content_hash(entry):
    """Create a hash of entry content for deduplication.

    Uses timestamp + type + deterministic content hash to identify duplicates.
    Same message appearing in multiple session files should only appear once.
    """
    # Start with timestamp and type as primary identifiers
    ts = entry.get('timestamp', '')
    entry_type = entry.get('type', '')

    # Create a deterministic hash of the content
    # We need to handle that dict ordering might vary, so we sort keys
    try:
        # Get the main content - could be 'message' for assistant/user, or other fields
        if 'message' in entry:
            content = json.dumps(entry['message'], sort_keys=True, default=str)
        else:
            # For system messages or other types, hash the whole entry minus volatile fields
            stable_entry = {k: v for k, v in entry.items()
                          if k not in ('line_num', 'source_file')}
            content = json.dumps(stable_entry, sort_keys=True, default=str)
    except (TypeError, ValueError):
        content = str(entry)

    content_digest = hashlib.md5(content.encode()).hexdigest()[:12]

    return f"{ts}|{entry_type}|{content_digest}"


def find_jsonl_files(input_dir, pattern, exclude_agents):
    """Find all matching JSONL files in the input directory.

    Uses absolute paths to handle the "dash problem" - directories starting
    with '-' break cd commands, but absolute paths work fine.
    """
    # Convert to absolute path immediately
    input_path = Path(input_dir).resolve()

    if not input_path.exists():
        print(f"Error: Input directory not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    if not input_path.is_dir():
        print(f"Error: Input path is not a directory: {input_path}", file=sys.stderr)
        sys.exit(1)

    # Find matching files using glob
    glob_pattern = str(input_path / pattern)
    all_files = glob.glob(glob_pattern)

    # Filter out agent files if requested
    if exclude_agents:
        original_count = len(all_files)
        all_files = [f for f in all_files if not Path(f).name.startswith('agent-')]
        excluded = original_count - len(all_files)
        if excluded > 0:
            print(f"Excluded {excluded} agent-*.jsonl files")

    # Sort for consistent ordering
    all_files.sort()

    return [Path(f) for f in all_files]


def read_jsonl_file(filepath):
    """Read all entries from a JSONL file.

    Returns list of entries with source file metadata added.
    """
    entries = []

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    entry = json.loads(line)
                    # Add source tracking (useful for debugging)
                    entry['_source_file'] = str(filepath.name)
                    entry['_source_line'] = line_num
                    entries.append(entry)
                except json.JSONDecodeError as e:
                    print(f"Warning: Invalid JSON at {filepath.name}:{line_num}: {e}",
                          file=sys.stderr)
                    continue
    except IOError as e:
        print(f"Error reading {filepath}: {e}", file=sys.stderr)
        return []

    return entries


def parse_timestamp(ts_str):
    """Parse ISO timestamp string to datetime for sorting.

    Handles various ISO formats and returns epoch for unparseable timestamps.
    """
    if not ts_str:
        return datetime.min

    # Try common formats
    formats = [
        '%Y-%m-%dT%H:%M:%S.%fZ',
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%dT%H:%M:%S.%f',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d %H:%M:%S.%f',
        '%Y-%m-%d %H:%M:%S',
    ]

    for fmt in formats:
        try:
            return datetime.strptime(ts_str, fmt)
        except ValueError:
            continue

    # If we can't parse it, return min time so it sorts first
    return datetime.min


def merge_and_dedupe(all_entries):
    """Merge all entries, deduplicate, and sort chronologically.

    Deduplication is based on (timestamp, type, content_hash) - the same
    message shouldn't appear twice even if it's in multiple session files.
    """
    seen_hashes = set()
    unique_entries = []
    duplicates = 0

    for entry in all_entries:
        h = content_hash(entry)
        if h in seen_hashes:
            duplicates += 1
            continue
        seen_hashes.add(h)
        unique_entries.append(entry)

    # Sort by timestamp
    unique_entries.sort(key=lambda e: parse_timestamp(e.get('timestamp', '')))

    return unique_entries, duplicates


def get_date_range(entries):
    """Get the date range of entries."""
    if not entries:
        return None, None

    timestamps = [e.get('timestamp', '') for e in entries if e.get('timestamp')]
    if not timestamps:
        return None, None

    timestamps.sort()
    return timestamps[0], timestamps[-1]


def main():
    parser = argparse.ArgumentParser(
        description='Merge multiple JSONL session files into a single consolidated file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
    # Basic merge of all JSONL files in a directory
    %(prog)s -i ./sessions -o full_history.jsonl

    # Merge with custom pattern
    %(prog)s -i ./sessions -o merged.jsonl --pattern "session*.jsonl"

    # Include agent files (excluded by default)
    %(prog)s -i ./sessions -o merged.jsonl --no-exclude-agents

    # Handle directories with dashes in the name (use absolute paths)
    %(prog)s -i "/mnt/data/-weird-dir-name" -o output.jsonl

Notes:
    - Entries are deduplicated by (timestamp, type, content hash)
    - Output is sorted chronologically by timestamp
    - Agent files (agent-*.jsonl) are excluded by default as they're subagent traces
    - Uses absolute paths internally to handle the "dash problem" with directory names
        '''
    )

    parser.add_argument('-i', '--input-dir', required=True,
                        help='Directory containing *.jsonl files to merge')
    parser.add_argument('-o', '--output', required=True,
                        help='Output file path for merged JSONL')
    parser.add_argument('--pattern', default='*.jsonl',
                        help='Glob pattern for input files (default: *.jsonl)')
    parser.add_argument('--exclude-agents', action='store_true', default=True,
                        dest='exclude_agents',
                        help='Exclude agent-*.jsonl files (default: True)')
    parser.add_argument('--no-exclude-agents', action='store_false',
                        dest='exclude_agents',
                        help='Include agent-*.jsonl files')
    parser.add_argument('--keep-source-metadata', action='store_true',
                        help='Keep _source_file and _source_line fields in output')

    args = parser.parse_args()

    # Convert to absolute paths immediately
    input_dir = Path(args.input_dir).resolve()
    output_path = Path(args.output).resolve()

    print(f"Input directory: {input_dir}")
    print(f"Output file: {output_path}")
    print(f"Pattern: {args.pattern}")
    print()

    # Find all matching files
    files = find_jsonl_files(input_dir, args.pattern, args.exclude_agents)

    if not files:
        print(f"Error: No files matching '{args.pattern}' found in {input_dir}",
              file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(files)} files to merge:")
    for f in files:
        size_kb = f.stat().st_size / 1024
        print(f"  - {f.name} ({size_kb:.1f} KB)")
    print()

    # Read all entries from all files
    all_entries = []
    for filepath in files:
        entries = read_jsonl_file(filepath)
        print(f"  {filepath.name}: {len(entries)} entries")
        all_entries.extend(entries)

    print(f"\nTotal entries before deduplication: {len(all_entries)}")

    # Merge and deduplicate
    unique_entries, duplicates = merge_and_dedupe(all_entries)

    print(f"Duplicates removed: {duplicates}")
    print(f"Unique entries: {len(unique_entries)}")

    # Get date range
    first_ts, last_ts = get_date_range(unique_entries)
    if first_ts and last_ts:
        print(f"\nDate range: {first_ts[:19]} to {last_ts[:19]}")

    # Remove source metadata unless requested to keep
    if not args.keep_source_metadata:
        for entry in unique_entries:
            entry.pop('_source_file', None)
            entry.pop('_source_line', None)

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write output
    with open(output_path, 'w', encoding='utf-8') as f:
        for entry in unique_entries:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + '\n')

    output_size = output_path.stat().st_size / 1024 / 1024
    print(f"\nOutput written to: {output_path}")
    print(f"Output size: {output_size:.2f} MB")

    # Summary stats
    print("\n" + "=" * 50)
    print("MERGE SUMMARY")
    print("=" * 50)
    print(f"Files processed:     {len(files)}")
    print(f"Total entries read:  {len(all_entries)}")
    print(f"Duplicates removed:  {duplicates}")
    print(f"Final entry count:   {len(unique_entries)}")
    if first_ts and last_ts:
        print(f"Date range:          {first_ts[:10]} to {last_ts[:10]}")


if __name__ == '__main__':
    main()
