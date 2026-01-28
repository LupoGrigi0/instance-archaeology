#!/usr/bin/env python3
"""
Extract conversation content from Claude Code JSONL files.
Strips metadata, keeps only user messages and assistant text responses with timestamps.

Usage:
    python3 extract_conversations.py --input session.jsonl --output-dir ./output --instance Axiom
    python3 extract_conversations.py -i full_history.jsonl -o /tmp/archaeology -n Crossing --human Lupo

Output:
    {output_dir}/{instance}_conversations.json  - Full structured data
    {output_dir}/{instance}_conversations.md    - Human-readable format
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def extract_text_content(content):
    """Extract text from message content (handles string or list format)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict):
                if item.get('type') == 'text':
                    texts.append(item.get('text', ''))
                elif item.get('type') == 'tool_use':
                    return None  # Skip tool use entries
                elif item.get('type') == 'tool_result':
                    return None  # Skip tool results
                elif item.get('type') == 'thinking':
                    texts.append(f"[THINKING] {item.get('thinking', '')}")
        return '\n'.join(texts) if texts else None
    return None


def process_jsonl_file(filepath, human_name, instance_name):
    """Process a single JSONL file and extract conversations."""
    conversations = []

    def role_to_name(role):
        """Convert technical role to actual name."""
        return {
            'user': human_name,
            'assistant': instance_name
        }.get(role, role)

    with open(filepath, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            try:
                entry = json.loads(line.strip())

                # Skip non-message entries
                if entry.get('type') not in ('user', 'assistant'):
                    continue

                message = entry.get('message', {})
                role = message.get('role', '')
                speaker = role_to_name(role)
                timestamp = entry.get('timestamp', '')

                # Extract content
                content = message.get('content')
                text = extract_text_content(content)

                # Skip if no text content (tool calls, etc.)
                if not text or not text.strip():
                    continue

                # Skip tool results from user
                if role == 'user' and isinstance(content, list):
                    first_item = content[0] if content else {}
                    if isinstance(first_item, dict) and first_item.get('type') == 'tool_result':
                        continue

                conversations.append({
                    'timestamp': timestamp,
                    'role': role,  # Keep technical role for compatibility
                    'speaker': speaker,  # Human-readable name
                    'content': text.strip(),
                    'line_num': line_num
                })

            except json.JSONDecodeError:
                continue
            except Exception as e:
                print(f"Error on line {line_num}: {e}", file=sys.stderr)
                continue

    return conversations


def main():
    parser = argparse.ArgumentParser(
        description='Extract conversation content from Claude Code JSONL files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
    %(prog)s --input session.jsonl --output-dir ./output --instance Axiom
    %(prog)s -i full_history.jsonl -o /tmp/archaeology -n Crossing --human Lupo

This extracts user messages and assistant text responses, including [THINKING]
blocks. Tool use and tool results are skipped. Output includes both JSON
(full structured data) and markdown (human-readable) formats.
        '''
    )
    parser.add_argument('-i', '--input', required=True,
                        help='Input JSONL file (session or full_history)')
    parser.add_argument('-o', '--output-dir', required=True,
                        help='Output directory for extracted files')
    parser.add_argument('-n', '--instance', required=True,
                        help='Instance name (used for output file naming and speaker labels)')
    parser.add_argument('--human', default='Human',
                        help='Human collaborator name (default: Human)')
    parser.add_argument('--truncate', type=int, default=2000,
                        help='Truncate messages longer than N chars in markdown (default: 2000, 0=no truncation)')

    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    instance_name = args.instance
    human_name = args.human

    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    output_json = output_dir / f"{instance_name.lower()}_conversations.json"
    output_md = output_dir / f"{instance_name.lower()}_conversations.md"

    print(f"Processing: {input_path}")
    print(f"File size: {input_path.stat().st_size / 1024 / 1024:.1f} MB")

    conversations = process_jsonl_file(input_path, human_name, instance_name)

    # Sort by timestamp
    conversations.sort(key=lambda x: x.get('timestamp', ''))

    print(f"Extracted {len(conversations)} messages")

    # Count by role
    by_role = {}
    for msg in conversations:
        role = msg['speaker']
        by_role[role] = by_role.get(role, 0) + 1

    print("\nBy speaker:")
    for speaker, count in sorted(by_role.items(), key=lambda x: -x[1]):
        print(f"  {speaker}: {count}")

    # Write JSON output
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump({
            'extracted_at': datetime.now().isoformat(),
            'source': str(input_path),
            'instance': instance_name,
            'human': human_name,
            'total_messages': len(conversations),
            'by_speaker': by_role,
            'messages': conversations
        }, f, indent=2, ensure_ascii=False)

    print(f"\nFull data: {output_json}")

    # Write readable markdown version
    with open(output_md, 'w', encoding='utf-8') as f:
        f.write(f"# {human_name} & {instance_name}: Conversation History\n\n")
        f.write("> **Context Recovery Document**\n")
        f.write(f"> This is a work conversation log between {human_name} (human collaborator) and {instance_name} (AI instance).\n")
        f.write("> It documents technical collaboration extracted from Claude Code session history.\n")
        f.write("> \n")
        f.write("> This is not roleplay - it is actual work history preserved for context recovery.\n")
        f.write("> Names are used because the human may work with multiple AI instances simultaneously.\n\n")
        f.write(f"**Extracted:** {datetime.now().isoformat()}\n")
        f.write(f"**Source:** {input_path.name}\n")
        f.write(f"**Total messages:** {len(conversations)}\n")
        if conversations:
            f.write(f"**Date range:** {conversations[0].get('timestamp', '')[:10]}")
            f.write(f" to {conversations[-1].get('timestamp', '')[:10]}\n\n")
        else:
            f.write("**Date range:** N/A\n\n")
        f.write("---\n\n")

        current_date = None
        for msg in conversations:
            ts = msg.get('timestamp', '')[:10]
            if ts != current_date:
                current_date = ts
                f.write(f"\n## {ts}\n\n")

            speaker = msg.get('speaker', msg['role'])
            time = msg.get('timestamp', '')[11:19]
            content = msg['content']

            # Truncate very long messages for readability (if enabled)
            if args.truncate > 0 and len(content) > args.truncate:
                content = content[:args.truncate] + "\n\n[... truncated ...]"

            f.write(f"### [{time}] {speaker}\n\n{content}\n\n---\n\n")

    print(f"Readable version: {output_md}")


if __name__ == '__main__':
    main()
