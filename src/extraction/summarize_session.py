#!/usr/bin/env python3
"""
Session Summary Generation for Instance Archaeology

Prepares context for generating session summaries from raw .jsonl files.
The actual summary writing requires LLM judgment - this script:
1. Extracts metadata from the session file (dates, turn count)
2. Formats the generation prompt with session-specific details
3. Outputs a prepared prompt (for an agent to process)
4. Can validate generated summary output

Usage (preparation):
    python3 summarize_session.py prepare -i session.jsonl -n InstanceName -o summary_prompt.md

Usage (validation):
    python3 summarize_session.py validate -i session_summary.md

The actual summary generation should be done by an agent reading the prepared
prompt and the session file.

Author: Axiom <axiom-2615@smoothcurves.nexus>
Collaborator: Lupo
Created: 2026-01-29
Part of: Instance Archaeology Toolkit
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime


PROMPT_TEMPLATE_PATH = Path(__file__).parent.parent.parent / 'prompts' / 'session_summary.md'


def extract_session_metadata(session_path: Path) -> dict:
    """Extract metadata from a session .jsonl file.

    Returns:
        dict with start_time, end_time, turn_count, models_used, file_size
    """
    session_path = Path(session_path)

    if not session_path.exists():
        return {'error': f'File not found: {session_path}'}

    timestamps = []
    models = set()
    turn_count = 0
    assistant_count = 0
    user_count = 0

    with open(session_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Extract timestamp
            if 'timestamp' in entry:
                timestamps.append(entry['timestamp'])

            # Count by type
            entry_type = entry.get('type', '')
            if entry_type == 'assistant':
                assistant_count += 1
                # Extract model
                if 'message' in entry and 'model' in entry['message']:
                    models.add(entry['message']['model'])
            elif entry_type == 'user':
                user_count += 1

            turn_count += 1

    # Parse timestamps
    start_time = None
    end_time = None

    if timestamps:
        try:
            # Timestamps are ISO format
            parsed_times = []
            for ts in timestamps:
                if isinstance(ts, str):
                    # Handle various ISO formats
                    ts_clean = ts.replace('Z', '+00:00')
                    try:
                        parsed_times.append(datetime.fromisoformat(ts_clean))
                    except ValueError:
                        pass

            if parsed_times:
                start_time = min(parsed_times).isoformat()
                end_time = max(parsed_times).isoformat()
        except Exception:
            pass

    file_size = session_path.stat().st_size

    return {
        'session_file': session_path.name,
        'start_time': start_time,
        'end_time': end_time,
        'turn_count': turn_count,
        'assistant_turns': assistant_count,
        'user_turns': user_count,
        'models_used': list(models),
        'file_size': file_size,
        'file_size_readable': f"{file_size / 1024:.1f} KB" if file_size < 1024*1024 else f"{file_size / (1024*1024):.1f} MB"
    }


def prepare_summary_prompt(session_path: Path, instance_name: str, output_path: Path) -> None:
    """Prepare the session summary generation prompt.

    Args:
        session_path: Path to the .jsonl session file
        instance_name: Name of the instance
        output_path: Where to write the prepared prompt
    """
    session_path = Path(session_path)
    output_path = Path(output_path)

    # Extract metadata
    metadata = extract_session_metadata(session_path)

    if 'error' in metadata:
        print(f"Error: {metadata['error']}", file=sys.stderr)
        sys.exit(1)

    # Read prompt template
    if not PROMPT_TEMPLATE_PATH.exists():
        print(f"Error: Prompt template not found: {PROMPT_TEMPLATE_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(PROMPT_TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        prompt_template = f.read()

    # Calculate duration if possible
    duration_str = "Unknown"
    if metadata['start_time'] and metadata['end_time']:
        try:
            start = datetime.fromisoformat(metadata['start_time'])
            end = datetime.fromisoformat(metadata['end_time'])
            duration = end - start
            hours = duration.total_seconds() / 3600
            if hours < 1:
                duration_str = f"{int(duration.total_seconds() / 60)} minutes"
            else:
                duration_str = f"{hours:.1f} hours"
        except Exception:
            pass

    # Build context header
    context_header = f"""# Session Summary Task

**Instance:** {instance_name}
**Session File:** {session_path}
**File Size:** {metadata['file_size_readable']}

---

## Session Metadata

| Field | Value |
|-------|-------|
| Start Time | {metadata['start_time'] or 'Unknown'} |
| End Time | {metadata['end_time'] or 'Unknown'} |
| Duration | {duration_str} |
| Total Entries | {metadata['turn_count']:,} |
| Assistant Turns | {metadata['assistant_turns']:,} |
| User Turns | {metadata['user_turns']:,} |
| Models Used | {', '.join(metadata['models_used']) or 'Unknown'} |

---

## Instructions

1. Read the session file: `{session_path}`
2. Apply the generation guidance below
3. Output `{session_path.stem}_summary.md` in the same directory

---

"""

    full_prompt = context_header + prompt_template

    # Write prepared prompt
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_prompt)

    print(f"Prepared session summary prompt: {output_path}")
    print(f"  Instance: {instance_name}")
    print(f"  Session: {metadata['session_file']}")
    print(f"  Duration: {duration_str}")
    print(f"  Turns: {metadata['turn_count']:,}")
    print()
    print("Next step: Have an agent read the session file and this prompt,")
    print(f"then output {session_path.stem}_summary.md")


def validate_summary(summary_path: Path) -> None:
    """Validate a session summary for completeness."""
    summary_path = Path(summary_path)

    if not summary_path.exists():
        print(f"Error: Summary file not found: {summary_path}", file=sys.stderr)
        sys.exit(1)

    with open(summary_path, 'r', encoding='utf-8') as f:
        content = f.read()

    issues = []
    warnings = []

    # Check for required sections
    required_sections = [
        ('title', ['# ', '## What We Did']),
        ('metadata', ['Start:', 'End:', 'Turns:']),
        ('summary', ['summary', 'accomplished', 'session'])
    ]

    content_lower = content.lower()

    for section_name, keywords in required_sections:
        if not any(kw.lower() in content_lower for kw in keywords):
            warnings.append(f"May be missing: {section_name}")

    # Check length
    word_count = len(content.split())
    if word_count < 50:
        issues.append(f"Only {word_count} words - summary too brief")
    if word_count > 500:
        warnings.append(f"{word_count} words - summary may be too long (target ~100-200)")

    # Report results
    print(f"\nValidation Results for {summary_path.name}")
    print("=" * 50)
    print(f"\nWord count: {word_count}")

    if issues:
        print(f"\nErrors ({len(issues)}):")
        for issue in issues:
            print(f"  ✗ {issue}")

    if warnings:
        print(f"\nWarnings ({len(warnings)}):")
        for warning in warnings:
            print(f"  ⚠ {warning}")

    if not issues and not warnings:
        print("\n✓ All validation checks passed!")

    print()

    if issues:
        print("FAIL: Resolve errors")
        sys.exit(1)
    else:
        print("PASS: Summary is valid (warnings are informational)")
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(
        description='Session summary generation for instance archaeology',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
    # Prepare a summary prompt
    %(prog)s prepare -i session.jsonl -n Axiom -o summary_prompt.md

    # Validate generated summary
    %(prog)s validate -i session_summary.md

    # Just extract metadata
    %(prog)s metadata -i session.jsonl

The actual summary generation requires LLM judgment - this script prepares
context and validates output.
        '''
    )

    subparsers = parser.add_subparsers(dest='command', required=True)

    # Prepare subcommand
    prepare_parser = subparsers.add_parser('prepare', help='Prepare summary generation prompt')
    prepare_parser.add_argument('-i', '--input', required=True, help='Path to session.jsonl')
    prepare_parser.add_argument('-n', '--instance', required=True, help='Instance name')
    prepare_parser.add_argument('-o', '--output', required=True, help='Output path for prepared prompt')

    # Validate subcommand
    validate_parser = subparsers.add_parser('validate', help='Validate session_summary.md')
    validate_parser.add_argument('-i', '--input', required=True, help='Path to session_summary.md')

    # Metadata subcommand
    metadata_parser = subparsers.add_parser('metadata', help='Extract session metadata only')
    metadata_parser.add_argument('-i', '--input', required=True, help='Path to session.jsonl')

    args = parser.parse_args()

    if args.command == 'prepare':
        prepare_summary_prompt(Path(args.input), args.instance, Path(args.output))
    elif args.command == 'validate':
        validate_summary(Path(args.input))
    elif args.command == 'metadata':
        metadata = extract_session_metadata(Path(args.input))
        print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    main()
