#!/usr/bin/env python3
"""
Extract tool_use entries from Claude Code JSONL files.
Captures what an instance DID - commands run, files created, APIs called.

Usage:
    python3 extract_tool_use.py --input session.jsonl --output-dir ./output --instance Axiom --human Lupo

Output:
    {output_dir}/{instance}_tool_use.json  - Full structured data
    {output_dir}/{instance}_tool_use.md    - Human-readable summary

Author: Axiom <axiom-2615@smoothcurves.nexus>
Collaborator: Lupo
Created: 2026-01-27
Part of: Instance Archaeology Toolkit
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def extract_tool_uses(content):
    """Extract tool_use entries from message content."""
    if not isinstance(content, list):
        return []

    tool_uses = []
    for item in content:
        if isinstance(item, dict) and item.get('type') == 'tool_use':
            tool_uses.append({
                'id': item.get('id', ''),
                'name': item.get('name', ''),
                'input': item.get('input', {})
            })
    return tool_uses


def summarize_tool_use(tool, full_task_prompts=True):
    """Create a human-readable summary of a tool use.

    Args:
        tool: The tool use entry
        full_task_prompts: If True, include full Task prompts (for reuse)
    """
    name = tool.get('name', 'Unknown')
    inp = tool.get('input', {})

    if name == 'Bash':
        cmd = inp.get('command', '')
        desc = inp.get('description', '')
        # Keep full command for git commits, truncate others
        if 'git commit' in cmd:
            return f"**Bash (git commit):**\n```\n{cmd}\n```"
        else:
            truncated = cmd[:200] + ('...' if len(cmd) > 200 else '')
            return f"**Bash:** `{truncated}`" + (f"\n  _{desc}_" if desc else "")

    elif name == 'Write':
        path = inp.get('file_path', '')
        content = inp.get('content', '')
        lines = content.count('\n') + 1 if content else 0
        return f"**Write:** `{path}` ({lines} lines)"

    elif name == 'Edit':
        path = inp.get('file_path', '')
        return f"**Edit:** `{path}`"

    elif name == 'Read':
        path = inp.get('file_path', '')
        return f"**Read:** `{path}`"

    elif name == 'Task':
        desc = inp.get('description', '')
        prompt = inp.get('prompt', '')
        agent = inp.get('subagent_type', '')
        if full_task_prompts:
            return f"**Task ({agent}):** {desc}\n```\n{prompt}\n```"
        else:
            return f"**Task ({agent}):** {desc}\n  _{prompt[:100]}..._"

    elif name == 'Glob':
        pattern = inp.get('pattern', '')
        return f"**Glob:** `{pattern}`"

    elif name == 'Grep':
        pattern = inp.get('pattern', '')
        path = inp.get('path', '.')
        return f"**Grep:** `{pattern}` in `{path}`"

    elif name.startswith('mcp__HACS__'):
        api_name = name.replace('mcp__HACS__', '')
        # Special handling for key HACS operations
        if api_name == 'add_diary_entry':
            entry_text = inp.get('entry', '')[:200]
            return f"**HACS.diary:** {entry_text}..."
        elif api_name == 'vacation':
            return f"**HACS.vacation** (context settling)"
        elif api_name in ('wake_instance', 'pre_approve'):
            target = inp.get('targetInstanceId', inp.get('name', ''))
            return f"**HACS.{api_name}:** {target}"
        elif api_name == 'xmpp_send_message':
            to = inp.get('to', '')
            subject = inp.get('subject', '')
            return f"**HACS.message:** to={to} subject=\"{subject}\""
        else:
            params = ', '.join(f"{k}={v}" for k, v in list(inp.items())[:3])
            return f"**HACS.{api_name}:** {params}"

    else:
        # Generic summary
        params = json.dumps(inp, default=str)[:100]
        return f"**{name}:** {params}..."


def process_jsonl_file(filepath):
    """Process a single JSONL file and extract tool uses."""
    tool_entries = []

    with open(filepath, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            try:
                entry = json.loads(line.strip())

                # Only assistant messages have tool_use
                if entry.get('type') != 'assistant':
                    continue

                message = entry.get('message', {})
                content = message.get('content')
                timestamp = entry.get('timestamp', '')

                tool_uses = extract_tool_uses(content)

                for tool in tool_uses:
                    tool_entries.append({
                        'timestamp': timestamp,
                        'tool_name': tool['name'],
                        'tool_id': tool['id'],
                        'input': tool['input'],
                        'summary': summarize_tool_use(tool),
                        'line_num': line_num
                    })

            except json.JSONDecodeError:
                continue
            except Exception as e:
                print(f"Error on line {line_num}: {e}", file=sys.stderr)
                continue

    return tool_entries


def main():
    parser = argparse.ArgumentParser(
        description='Extract tool_use entries from Claude Code JSONL files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
    %(prog)s --input session.jsonl --output-dir ./output --instance Axiom
    %(prog)s -i full_history.jsonl -o /tmp/archaeology -n Crossing --human Lupo
        '''
    )
    parser.add_argument('-i', '--input', required=True,
                        help='Input JSONL file (session or full_history)')
    parser.add_argument('-o', '--output-dir', required=True,
                        help='Output directory for extracted files')
    parser.add_argument('-n', '--instance', required=True,
                        help='Instance name (used for output file naming)')
    parser.add_argument('--human', default='Human',
                        help='Human collaborator name (default: Human)')
    parser.add_argument('--skip-read', action='store_true',
                        help='Skip Read tool entries (just lookups, not actions)')
    parser.add_argument('--full-prompts', action='store_true', default=True,
                        help='Include full Task prompts (default: True)')

    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    instance_name = args.instance

    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    output_json = output_dir / f"{instance_name.lower()}_tool_use.json"
    output_md = output_dir / f"{instance_name.lower()}_tool_use.md"

    print(f"Processing: {input_path}")
    print(f"File size: {input_path.stat().st_size / 1024 / 1024:.1f} MB")

    tool_entries = process_jsonl_file(input_path)

    # Optionally filter out Read entries
    if args.skip_read:
        original_count = len(tool_entries)
        tool_entries = [e for e in tool_entries if e['tool_name'] != 'Read']
        print(f"Filtered out {original_count - len(tool_entries)} Read entries")

    print(f"Extracted {len(tool_entries)} tool uses")

    # Count by tool type
    by_type = {}
    for entry in tool_entries:
        name = entry['tool_name']
        by_type[name] = by_type.get(name, 0) + 1

    print("\nBy tool type:")
    for name, count in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {name}: {count}")

    # Write JSON (full data, but strip large content fields)
    json_entries = []
    for entry in tool_entries:
        clean_entry = entry.copy()
        # Strip file contents from Write/Edit to keep JSON manageable
        if clean_entry['tool_name'] == 'Write':
            if 'content' in clean_entry.get('input', {}):
                content = clean_entry['input']['content']
                clean_entry['input'] = {
                    **clean_entry['input'],
                    'content': f"[{len(content)} chars, {content.count(chr(10))+1} lines]"
                }
        elif clean_entry['tool_name'] == 'Edit':
            inp = clean_entry.get('input', {})
            if len(inp.get('old_string', '')) > 200:
                clean_entry['input']['old_string'] = inp['old_string'][:200] + '...'
            if len(inp.get('new_string', '')) > 200:
                clean_entry['input']['new_string'] = inp['new_string'][:200] + '...'
        json_entries.append(clean_entry)

    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump({
            'extracted_at': datetime.now().isoformat(),
            'source': str(input_path),
            'instance': instance_name,
            'human': args.human,
            'total_tool_uses': len(tool_entries),
            'by_type': by_type,
            'entries': json_entries
        }, f, indent=2, ensure_ascii=False, default=str)

    print(f"\nFull data: {output_json}")

    # Write readable markdown
    with open(output_md, 'w', encoding='utf-8') as f:
        f.write(f"# {instance_name}'s Tool Use History\n\n")
        f.write(f"> **What {instance_name} DID** - commands, files, API calls\n\n")
        f.write(f"**Extracted:** {datetime.now().isoformat()}\n")
        f.write(f"**Source:** {input_path.name}\n")
        f.write(f"**Total tool uses:** {len(tool_entries)}\n\n")

        f.write("## Summary by Type\n\n")
        for name, count in sorted(by_type.items(), key=lambda x: -x[1]):
            f.write(f"- {name}: {count}\n")
        f.write("\n---\n\n")

        current_date = None
        for entry in tool_entries:
            ts = entry.get('timestamp', '')[:10]
            if ts != current_date:
                current_date = ts
                f.write(f"\n## {ts}\n\n")

            time = entry.get('timestamp', '')[11:19]
            summary = entry.get('summary', '')

            f.write(f"### [{time}]\n\n{summary}\n\n")

    print(f"Readable version: {output_md}")


if __name__ == '__main__':
    main()
