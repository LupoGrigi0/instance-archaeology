#!/usr/bin/env python3
"""
Extract Task tool prompts from Claude Code JSONL conversation files.

These are the prompts AI instances give to subagents - showing craft in delegation,
how they structure problems, and how they teach. The full prompts are preserved
for copy-paste reuse.

Usage:
    python3 extract_agent_prompts.py --input session.jsonl --output-dir ./output --instance Axiom

Output:
    {output_dir}/{instance}_agent_prompts.md  - Full prompts grouped by date

Author: Axiom-2615 <axiom@smoothcurves.nexus>
Collaborator: Lupo
Created: 2026-01-27
Part of: Instance Archaeology Toolkit
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def extract_task_prompts(jsonl_file):
    """Extract all Task tool prompts from a JSONL conversation file.

    Args:
        jsonl_file: Path to the JSONL file to process

    Returns:
        List of task dictionaries with prompt details
    """
    tasks = []

    with open(jsonl_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            try:
                entry = json.loads(line.strip())

                # Only assistant messages contain tool_use
                if entry.get('type') != 'assistant':
                    continue

                content = entry.get('message', {}).get('content', [])
                if not isinstance(content, list):
                    continue

                timestamp = entry.get('timestamp', '')

                for item in content:
                    # Look for tool_use items with name="Task"
                    if not isinstance(item, dict):
                        continue
                    if item.get('type') != 'tool_use':
                        continue
                    if item.get('name') != 'Task':
                        continue

                    task_input = item.get('input', {})
                    prompt = task_input.get('prompt', '')

                    # Skip entries with no prompt
                    if not prompt:
                        continue

                    tasks.append({
                        'line_number': line_num,
                        'timestamp': timestamp,
                        'date': timestamp[:10] if timestamp else 'unknown',
                        'time': timestamp[11:19] if len(timestamp) > 19 else '',
                        'subagent_type': task_input.get('subagent_type', 'unknown'),
                        'description': task_input.get('description', ''),
                        'prompt': prompt,  # FULL prompt - never truncate
                        'model': task_input.get('model', ''),
                        'background': task_input.get('run_in_background', False),
                        'prompt_length': len(prompt),
                        'tool_id': item.get('id', '')
                    })

            except json.JSONDecodeError:
                continue
            except Exception as e:
                print(f"Warning: Error on line {line_num}: {e}", file=sys.stderr)
                continue

    return tasks


def format_as_markdown(tasks, instance_name):
    """Format extracted prompts as curated markdown.

    The full prompt text is preserved for copy-paste reuse.

    Args:
        tasks: List of task dictionaries
        instance_name: Name of the instance for the header

    Returns:
        Formatted markdown string
    """
    lines = [
        f"# {instance_name}'s Agent Prompts",
        "",
        "> These are the prompts given to subagents - showing craft in delegation,",
        "> how problems are structured, and teaching style. Full prompts preserved for reuse.",
        "",
        f"**Extracted:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Total prompts:** {len(tasks)}",
        ""
    ]

    if tasks:
        avg_len = sum(t['prompt_length'] for t in tasks) / len(tasks)
        lines.append(f"**Average prompt length:** {avg_len:.0f} chars")

        # Count by subagent type
        by_type = {}
        for t in tasks:
            st = t['subagent_type']
            by_type[st] = by_type.get(st, 0) + 1

        lines.append(f"**By subagent type:** {', '.join(f'{k}: {v}' for k, v in sorted(by_type.items()))}")
        lines.append("")

    lines.extend(["---", ""])

    # Group by date for chronological narrative
    by_date = {}
    for task in tasks:
        date = task['date']
        if date not in by_date:
            by_date[date] = []
        by_date[date].append(task)

    for date in sorted(by_date.keys()):
        day_tasks = by_date[date]
        lines.append(f"## {date}")
        lines.append("")

        for task in day_tasks:
            desc = task['description'] or '(no description)'
            agent_type = task['subagent_type']
            model = task['model'] or 'default'
            prompt = task['prompt']
            time = task['time']
            prompt_len = task['prompt_length']

            # Header with metadata
            lines.append(f"### {desc}")
            lines.append("")
            lines.append(f"- **Time:** {time}")
            lines.append(f"- **Subagent:** {agent_type}")
            lines.append(f"- **Model:** {model}")
            lines.append(f"- **Prompt length:** {prompt_len:,} chars")
            if task['background']:
                lines.append(f"- **Background:** yes")
            lines.append("")

            # The actual prompt - FULL, never truncated - in fenced code block
            lines.append("```")
            lines.append(prompt)
            lines.append("```")
            lines.append("")

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='Extract Task tool prompts from Claude Code JSONL files. '
                    'Captures the full prompts AI instances give to subagents for reuse.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
    # Extract prompts from a session file
    %(prog)s -i session.jsonl -o ./output -n Axiom

    # Process a full history export
    %(prog)s --input full_history.jsonl --output-dir /tmp/archaeology --instance Crossing

Output:
    Creates {output_dir}/{instance}_agent_prompts.md with full prompts grouped by date.
    Prompts are preserved in full for copy-paste reuse.

Note:
    Only extracts entries where tool_use.name == "Task" and a prompt exists.
    The full prompt text is valuable for understanding delegation patterns
    and for reusing well-crafted prompts.
        '''
    )
    parser.add_argument('-i', '--input', required=True,
                        help='Input JSONL file (session or full_history export)')
    parser.add_argument('-o', '--output-dir', required=True,
                        help='Output directory for extracted markdown')
    parser.add_argument('-n', '--instance', required=True,
                        help='Instance name (used for output file naming and header)')

    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    instance_name = args.instance

    # Validate input
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Output file path
    output_md = output_dir / f"{instance_name.lower()}_agent_prompts.md"

    print(f"Processing: {input_path}")
    print(f"File size: {input_path.stat().st_size / 1024 / 1024:.1f} MB")

    # Extract Task prompts
    tasks = extract_task_prompts(input_path)
    print(f"Found {len(tasks)} Task prompts")

    if not tasks:
        print("No Task prompts found in input file.")
        sys.exit(0)

    # Statistics
    avg_len = sum(t['prompt_length'] for t in tasks) / len(tasks)
    print(f"Average prompt length: {avg_len:.0f} chars")

    by_type = {}
    for t in tasks:
        st = t['subagent_type']
        by_type[st] = by_type.get(st, 0) + 1
    print(f"By subagent type: {by_type}")

    # Generate markdown
    markdown = format_as_markdown(tasks, instance_name)

    # Write output
    with open(output_md, 'w', encoding='utf-8') as f:
        f.write(markdown)

    print(f"\nWritten to: {output_md}")
    print(f"Output size: {len(markdown):,} bytes")


if __name__ == '__main__':
    main()
