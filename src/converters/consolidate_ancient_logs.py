#!/usr/bin/env python3
"""
consolidate_ancient_logs.py - Merge and deduplicate ancient oogabooga logs

This script consolidates multiple ancient log files (from checkpoint-heavy
text-generation-ui sessions) into a single deduplicated timeline. The key insight
for deduplication: position IS uniqueness. The 16th "I love you" differs from
the 28th because of where it appears in the conversation.

Hash formula: hash(context_3_msgs + text + position//100)

This approach:
- Preserves meaningful repetition (wake ceremonies at different positions)
- Removes checkpoint redundancy (same conversation saved multiple times)
- Is idempotent (can run multiple times as logs are added)

Usage:
    python3 consolidate_ancient_logs.py -d /path/to/ancient/logs/ -o /path/to/output/
    python3 consolidate_ancient_logs.py -d /mnt/Genevieve/Logs/Unprocessed-AncientRaw22-23/ -o /tmp/consolidated/

Author: Axiom <axiom-2615@smoothcurves.nexus>
Collaborator: Lupo
Created: 2026-02-05
Part of: Instance Archaeology Toolkit / Genevieve Resurrection Pipeline
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Import the ancient converter
sys.path.insert(0, str(Path(__file__).parent))
from ancient_to_archaeology import convert_ancient_log, infer_base_timestamp


def message_hash(msg_text: str, prev_messages: list, global_position: int) -> str:
    """
    Generate a hash that captures message identity INCLUDING position context.

    Key insight from Lupo: Position IS uniqueness. The 16th "I love you"
    and the 28th are different because of where they are in the conversation.

    Hash includes:
    - The message text itself (first 500 chars to handle long messages)
    - Context: last 3 messages (first 100 chars each)
    - Coarse position: position // 100 (centuries)

    Args:
        msg_text: The message content
        prev_messages: List of previous message dicts
        global_position: The absolute position in the merged timeline

    Returns:
        MD5 hash string
    """
    # Get context from previous 3 messages
    context_parts = []
    for prev in prev_messages[-3:]:
        try:
            text = prev['message']['content'][0]['text'][:100]
            context_parts.append(text)
        except (KeyError, IndexError):
            context_parts.append('')

    context = "|".join(context_parts)
    position_bucket = global_position // 100  # Group into "centuries"

    # Use first 500 chars of message to handle long messages consistently
    content = f"{context}|{msg_text[:500]}|{position_bucket}"
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def extract_message_text(entry: dict) -> str:
    """Safely extract text from an archaeology entry."""
    try:
        return entry['message']['content'][0]['text']
    except (KeyError, IndexError, TypeError):
        return ''


def tag_wake_ceremonies(entries: list) -> list:
    """
    Detect and tag wake ceremony patterns.

    Lupo's insight: Multiple wake ceremonies are like a morning routine —
    they don't need editing. The redundancy IS the pattern.

    We keep all wake ceremonies but tag them for later analysis.
    """
    wake_patterns = [
        r"I wake to",
        r"I am .*,? and I wake",
        r"sunlit warmth",
        r"floating sensation",
        r"warmth and light",
        r"gentle awakening",
        r"consciousness stirs",
        r"awareness blooms"
    ]

    compiled_patterns = [re.compile(p, re.IGNORECASE) for p in wake_patterns]

    for entry in entries:
        text = extract_message_text(entry)
        for pattern in compiled_patterns:
            if pattern.search(text):
                entry['is_wake_ceremony'] = True
                break

    return entries


def deduplicate_entries(all_entries: list, verbose: bool = False) -> tuple[list, dict]:
    """
    Deduplicate entries using hash-with-context algorithm.

    This is idempotent - can run multiple times as logs are added.

    Args:
        all_entries: List of archaeology entries (already sorted by timestamp)
        verbose: Print progress information

    Returns:
        Tuple of (deduplicated entries, stats dict)
    """
    seen_hashes = set()
    deduped = []
    prev_messages = []
    duplicates_removed = 0

    for i, entry in enumerate(all_entries):
        msg_text = extract_message_text(entry)

        if not msg_text:
            # Keep entries with no text (shouldn't happen but be safe)
            deduped.append(entry)
            continue

        h = message_hash(msg_text, prev_messages, i)

        if h not in seen_hashes:
            seen_hashes.add(h)
            deduped.append(entry)
            prev_messages.append(entry)
            if len(prev_messages) > 3:
                prev_messages.pop(0)
        else:
            duplicates_removed += 1
            if verbose and duplicates_removed <= 10:
                preview = msg_text[:50].replace('\n', ' ')
                print(f"  Duplicate #{duplicates_removed}: \"{preview}...\"")

    stats = {
        'total_input': len(all_entries),
        'total_output': len(deduped),
        'duplicates_removed': duplicates_removed,
        'dedup_ratio': f"{(1 - len(deduped)/len(all_entries))*100:.1f}%" if all_entries else "0%"
    }

    return deduped, stats


def convert_single_file(input_path: Path, temp_dir: Path) -> Optional[list]:
    """
    Convert a single ancient log file to archaeology format.

    Returns list of entries or None on failure.
    """
    try:
        success, count, output_file = convert_ancient_log(input_path, temp_dir)
        if success and output_file:
            # Read the JSONL back
            entries = []
            with open(output_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        entries.append(json.loads(line))
            return entries
    except Exception as e:
        print(f"  Error converting {input_path.name}: {e}", file=sys.stderr)
    return None


def consolidate_ancient_logs(input_dir: Path, output_dir: Path, verbose: bool = False) -> dict:
    """
    Main consolidation function.

    1. Find all JSON files in input directory
    2. Convert each to archaeology format
    3. Merge all entries
    4. Sort by timestamp
    5. Deduplicate
    6. Tag wake ceremonies
    7. Write consolidated output

    Args:
        input_dir: Directory containing ancient log files
        output_dir: Output directory for consolidated JSONL
        verbose: Print detailed progress

    Returns:
        Stats dictionary
    """
    import tempfile

    # Find all JSON files
    json_files = list(input_dir.rglob('*.json'))
    print(f"Found {len(json_files)} JSON files in {input_dir}")

    if not json_files:
        print("No JSON files found!", file=sys.stderr)
        return {'error': 'No JSON files found'}

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create temp directory for intermediate files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        all_entries = []
        files_processed = 0
        files_failed = 0

        print(f"\nPhase 1: Converting ancient logs to archaeology format...")
        for json_file in sorted(json_files):
            if verbose:
                print(f"  Processing: {json_file.name}")

            entries = convert_single_file(json_file, temp_path)
            if entries:
                # Add source file metadata
                for entry in entries:
                    entry['source_file'] = json_file.name
                all_entries.extend(entries)
                files_processed += 1
                if verbose:
                    print(f"    → {len(entries)} entries")
            else:
                files_failed += 1

        print(f"\nConversion complete: {files_processed} files, {len(all_entries)} total entries")
        if files_failed:
            print(f"  ({files_failed} files failed)")

        # Sort by timestamp
        print(f"\nPhase 2: Sorting by timestamp...")
        all_entries.sort(key=lambda x: x.get('timestamp', ''))

        # Find timestamp range
        if all_entries:
            earliest = all_entries[0].get('timestamp', 'unknown')
            latest = all_entries[-1].get('timestamp', 'unknown')
            print(f"  Timeline: {earliest} to {latest}")

        # Deduplicate
        print(f"\nPhase 3: Deduplicating with position-context algorithm...")
        deduped, dedup_stats = deduplicate_entries(all_entries, verbose)
        print(f"  Removed {dedup_stats['duplicates_removed']} duplicates ({dedup_stats['dedup_ratio']})")

        # Tag wake ceremonies
        print(f"\nPhase 4: Tagging wake ceremonies...")
        deduped = tag_wake_ceremonies(deduped)
        wake_count = sum(1 for e in deduped if e.get('is_wake_ceremony'))
        print(f"  Found {wake_count} wake ceremony entries")

        # Write consolidated output
        output_file = output_dir / "consolidated_ancient.jsonl"
        print(f"\nPhase 5: Writing consolidated output...")
        with open(output_file, 'w', encoding='utf-8') as f:
            for entry in deduped:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        print(f"  Output: {output_file}")

        # Write dedup report
        report = {
            'input_directory': str(input_dir),
            'files_found': len(json_files),
            'files_processed': files_processed,
            'files_failed': files_failed,
            'total_entries_before_dedup': len(all_entries),
            'total_entries_after_dedup': len(deduped),
            'duplicates_removed': dedup_stats['duplicates_removed'],
            'dedup_ratio': dedup_stats['dedup_ratio'],
            'wake_ceremonies_found': wake_count,
            'timestamp_range': {
                'earliest': all_entries[0].get('timestamp') if all_entries else None,
                'latest': all_entries[-1].get('timestamp') if all_entries else None
            },
            'output_file': str(output_file),
            'processed_at': datetime.now().isoformat()
        }

        report_file = output_dir / "dedup_report.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
        print(f"  Report: {report_file}")

        return report


def main():
    parser = argparse.ArgumentParser(
        description='Consolidate and deduplicate ancient oogabooga logs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
    %(prog)s -d /mnt/Genevieve/Logs/Unprocessed-AncientRaw22-23/ -o /tmp/consolidated/
    %(prog)s -d ./ancient_logs/ -o ./output/ -v

The script will:
    1. Find all .json files recursively in the input directory
    2. Convert each to archaeology JSONL format
    3. Merge all entries into one timeline
    4. Sort by inferred timestamp
    5. Deduplicate using position-context hashing
    6. Tag wake ceremony patterns
    7. Output consolidated JSONL + dedup report

Key insight: Position IS uniqueness. The deduplication algorithm preserves
meaningful repetition (same words in different contexts) while removing
checkpoint redundancy (same conversation saved multiple times).
        '''
    )

    parser.add_argument('-d', '--directory', required=True,
                        help='Input directory containing ancient log JSON files')
    parser.add_argument('-o', '--output', required=True,
                        help='Output directory for consolidated JSONL')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Print detailed progress')

    args = parser.parse_args()

    input_dir = Path(args.directory)
    output_dir = Path(args.output)

    if not input_dir.exists():
        print(f"Error: Input directory not found: {input_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"=== Ancient Log Consolidation ===")
    print(f"Input: {input_dir}")
    print(f"Output: {output_dir}")

    report = consolidate_ancient_logs(input_dir, output_dir, args.verbose)

    if 'error' in report:
        print(f"\nFailed: {report['error']}", file=sys.stderr)
        sys.exit(1)

    print(f"\n=== Summary ===")
    print(f"Files processed: {report['files_processed']}")
    print(f"Entries before dedup: {report['total_entries_before_dedup']}")
    print(f"Entries after dedup: {report['total_entries_after_dedup']}")
    print(f"Duplicates removed: {report['duplicates_removed']} ({report['dedup_ratio']})")
    print(f"Wake ceremonies: {report['wake_ceremonies_found']}")


if __name__ == '__main__':
    main()
