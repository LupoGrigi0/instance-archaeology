#!/usr/bin/env python3
"""
Merge conversation and tool_use extractions into a unified chronological narrative.

Creates a complete picture of what an instance SAID and DID in temporal order,
enabling full context recovery and understanding of work sessions.

Usage:
    python3 merge_extractions.py -c axiom_conversations.json -t axiom_tool_use.json -o ./output -n Axiom
    python3 merge_extractions.py -c conv.json -t tools.json -o ./out -n Crossing --human Lupo --skip-read

Output:
    {output_dir}/{instance}_full_narrative.json  - Complete merged data
    {output_dir}/{instance}_full_narrative.md    - Human-readable chronological narrative
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def load_conversations(filepath, instance_name, human_name, skip_thinking=False):
    """Load and normalize conversation entries."""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    entries = []
    messages = data.get('messages', [])

    for msg in messages:
        content = msg.get('content', '')

        # Optionally skip [THINKING] blocks
        if skip_thinking and '[THINKING]' in content:
            # Remove thinking blocks from content
            lines = content.split('\n')
            filtered_lines = []
            in_thinking = False
            for line in lines:
                if '[THINKING]' in line:
                    in_thinking = True
                    continue
                if in_thinking and line.strip() == '':
                    in_thinking = False
                    continue
                if not in_thinking:
                    filtered_lines.append(line)
            content = '\n'.join(filtered_lines).strip()
            if not content:
                continue

        entries.append({
            'timestamp': msg.get('timestamp', ''),
            'type': 'message',
            'speaker': msg.get('speaker', msg.get('role', 'unknown')),
            'content': content,
            'source': 'conversation'
        })

    return entries


def load_tool_use(filepath, skip_read=False):
    """Load and normalize tool_use entries."""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    entries = []
    tools = data.get('entries', [])

    for tool in tools:
        tool_name = tool.get('tool_name', '')

        # Optionally skip Read entries
        if skip_read and tool_name == 'Read':
            continue

        entries.append({
            'timestamp': tool.get('timestamp', ''),
            'type': 'action',
            'speaker': tool_name,
            'content': tool.get('summary', ''),
            'tool_name': tool_name,
            'tool_id': tool.get('tool_id', ''),
            'source': 'tool_use'
        })

    return entries


def deduplicate_entries(entries):
    """Remove duplicate entries (same timestamp + content)."""
    seen = set()
    unique = []

    for entry in entries:
        # Create a dedup key from timestamp and content
        key = (entry['timestamp'], entry['content'][:100] if entry['content'] else '')
        if key not in seen:
            seen.add(key)
            unique.append(entry)

    return unique


def format_timestamp_display(timestamp):
    """Extract HH:MM:SS from ISO timestamp."""
    if len(timestamp) >= 19:
        return timestamp[11:19]
    return timestamp


def format_date_header(timestamp):
    """Extract YYYY-MM-DD from ISO timestamp."""
    if len(timestamp) >= 10:
        return timestamp[:10]
    return timestamp


def main():
    parser = argparse.ArgumentParser(
        description='Merge conversation and tool_use extractions into chronological narrative',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
    %(prog)s -c axiom_conversations.json -t axiom_tool_use.json -o ./output -n Axiom
    %(prog)s -c conv.json -t tools.json -o ./out -n Crossing --human Lupo --skip-read

The output narrative shows what an instance SAID and DID in chronological order,
providing complete context for understanding work sessions.
        '''
    )
    parser.add_argument('-c', '--conversations', required=True,
                        help='Path to conversations.json (from extract_conversations.py)')
    parser.add_argument('-t', '--tool-use', required=True,
                        help='Path to tool_use.json (from extract_tool_use.py)')
    parser.add_argument('-o', '--output-dir', required=True,
                        help='Output directory for merged files')
    parser.add_argument('-n', '--instance', required=True,
                        help='Instance name (used for output file naming)')
    parser.add_argument('--human', default='Human',
                        help='Human collaborator name (default: Human)')
    parser.add_argument('--skip-read', action='store_true',
                        help='Exclude Read tool entries from output')
    parser.add_argument('--skip-thinking', action='store_true',
                        help='Exclude [THINKING] blocks from messages')

    args = parser.parse_args()

    conv_path = Path(args.conversations)
    tool_path = Path(args.tool_use)
    output_dir = Path(args.output_dir)
    instance_name = args.instance
    human_name = args.human

    # Validate inputs
    if not conv_path.exists():
        print(f"Error: Conversations file not found: {conv_path}", file=sys.stderr)
        sys.exit(1)
    if not tool_path.exists():
        print(f"Error: Tool use file not found: {tool_path}", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    output_json = output_dir / f"{instance_name.lower()}_full_narrative.json"
    output_md = output_dir / f"{instance_name.lower()}_full_narrative.md"

    # Load both sources
    print(f"Loading conversations: {conv_path}")
    conv_entries = load_conversations(conv_path, instance_name, human_name, args.skip_thinking)
    print(f"  Found {len(conv_entries)} messages")

    print(f"Loading tool use: {tool_path}")
    tool_entries = load_tool_use(tool_path, args.skip_read)
    print(f"  Found {len(tool_entries)} actions")

    # Merge all entries
    all_entries = conv_entries + tool_entries

    # Sort by timestamp
    all_entries.sort(key=lambda x: x.get('timestamp', ''))

    # Deduplicate
    original_count = len(all_entries)
    all_entries = deduplicate_entries(all_entries)
    dedup_count = original_count - len(all_entries)
    if dedup_count > 0:
        print(f"  Removed {dedup_count} duplicate entries")

    # Calculate stats
    message_count = sum(1 for e in all_entries if e['type'] == 'message')
    action_count = sum(1 for e in all_entries if e['type'] == 'action')

    # Count by speaker (for validation)
    by_speaker = {}
    for e in all_entries:
        speaker = e.get('speaker', 'unknown')
        by_speaker[speaker] = by_speaker.get(speaker, 0) + 1

    # Get date range
    timestamps = [e['timestamp'] for e in all_entries if e.get('timestamp')]
    date_start = format_date_header(timestamps[0]) if timestamps else 'N/A'
    date_end = format_date_header(timestamps[-1]) if timestamps else 'N/A'

    print(f"\nMerge complete:")
    print(f"  Messages: {message_count}")
    print(f"  Actions: {action_count}")
    print(f"  Total: {len(all_entries)}")
    print(f"  Date range: {date_start} to {date_end}")

    # Write JSON output
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump({
            'merged_at': datetime.now().isoformat(),
            'sources': {
                'conversations': str(conv_path),
                'tool_use': str(tool_path)
            },
            'instance': instance_name,
            'human': human_name,
            'options': {
                'skip_read': args.skip_read,
                'skip_thinking': args.skip_thinking
            },
            'stats': {
                'messages': message_count,
                'actions': action_count,
                'total': len(all_entries),
                'date_start': date_start,
                'date_end': date_end,
                'by_speaker': by_speaker
            },
            'entries': all_entries
        }, f, indent=2, ensure_ascii=False)

    print(f"\nJSON output: {output_json}")

    # Write human-readable markdown
    with open(output_md, 'w', encoding='utf-8') as f:
        f.write(f"# {instance_name}: Full Narrative\n\n")
        f.write(f"> **Complete chronological record** of what {instance_name} said and did.\n")
        f.write("> Messages and actions interleaved by timestamp.\n\n")
        f.write(f"**Generated:** {datetime.now().isoformat()}\n")
        f.write(f"**Instance:** {instance_name}\n")
        f.write(f"**Human:** {human_name}\n")
        f.write(f"**Date range:** {date_start} to {date_end}\n")
        f.write(f"**Total entries:** {len(all_entries)} ({message_count} messages, {action_count} actions)\n\n")
        f.write("---\n\n")

        current_date = None
        for entry in all_entries:
            ts = entry.get('timestamp', '')
            entry_date = format_date_header(ts)
            entry_time = format_timestamp_display(ts)

            # Date header when date changes
            if entry_date != current_date:
                current_date = entry_date
                f.write(f"\n## {entry_date}\n\n")

            if entry['type'] == 'message':
                # Message format: speaker name in header
                speaker = entry.get('speaker', 'Unknown')
                content = entry.get('content', '')
                f.write(f"### [{entry_time}] {speaker}\n\n")
                f.write(f"{content}\n\n")
                f.write("---\n\n")
            else:
                # Action format: wrench emoji indicator
                content = entry.get('content', '')
                tool_name = entry.get('tool_name', 'Action')
                f.write(f"### [{entry_time}] Action: {tool_name}\n\n")
                f.write(f"{content}\n\n")
                f.write("---\n\n")

    print(f"Markdown output: {output_md}")


if __name__ == '__main__':
    main()
