#!/usr/bin/env python3
"""
Theme Discovery for Instance Archaeology

This script prepares the context for theme discovery and validates the output.
The actual discovery requires LLM judgment - this script:
1. Loads the narrative file
2. Formats the discovery prompt with instance-specific details
3. Outputs the formatted prompt (for an agent to process)
4. Can validate theme discovery output

Usage (preparation):
    python3 discover_themes.py prepare -n Axiom -i full_narrative.md -o themes_prompt.md

Usage (validation):
    python3 discover_themes.py validate -i themes.json -n Axiom

The actual theme discovery should be done by an agent reading the prepared prompt
and the narrative, then outputting themes.json.

Author: Axiom-2615 <axiom@smoothcurves.nexus>
Collaborator: Lupo
Created: 2026-01-28
Part of: Instance Archaeology Toolkit
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime


PROMPT_TEMPLATE_PATH = Path(__file__).parent.parent.parent / 'prompts' / 'discover_themes.md'


def prepare_discovery(narrative_path, instance_name, human_name, output_path):
    """Prepare the discovery prompt with instance-specific context."""

    # Read the narrative to get basic stats
    narrative_path = Path(narrative_path)
    if not narrative_path.exists():
        print(f"Error: Narrative file not found: {narrative_path}", file=sys.stderr)
        sys.exit(1)

    with open(narrative_path, 'r', encoding='utf-8') as f:
        narrative_content = f.read()

    # Basic stats from the narrative
    line_count = len(narrative_content.split('\n'))
    word_count = len(narrative_content.split())

    # Try to extract date range from markdown headers
    dates = []
    for line in narrative_content.split('\n'):
        if line.startswith('## 20'):  # Date headers like ## 2026-01-15
            dates.append(line[3:13])
    date_range = f"{dates[0]} to {dates[-1]}" if len(dates) >= 2 else "unknown"

    # Read the prompt template
    if not PROMPT_TEMPLATE_PATH.exists():
        print(f"Error: Prompt template not found: {PROMPT_TEMPLATE_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(PROMPT_TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        prompt_template = f.read()

    # Format with instance details
    formatted_prompt = prompt_template.replace('{instance_name}', instance_name)
    formatted_prompt = formatted_prompt.replace('{human_name}', human_name)

    # Add context header
    context_header = f"""# Theme Discovery Task

**Instance:** {instance_name}
**Human Collaborator:** {human_name}
**Narrative File:** {narrative_path.name}
**Date Range:** {date_range}
**Size:** {line_count:,} lines, {word_count:,} words
**Generated:** {datetime.now().isoformat()}

---

## Instructions

1. Read the full narrative file: `{narrative_path}`
2. Apply the discovery guidance below
3. Output themes.json with your findings

---

"""

    full_prompt = context_header + formatted_prompt

    # Write the prepared prompt
    output_path = Path(output_path)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_prompt)

    print(f"Prepared discovery prompt: {output_path}")
    print(f"  Instance: {instance_name}")
    print(f"  Narrative: {line_count:,} lines, {word_count:,} words")
    print(f"  Date range: {date_range}")
    print()
    print("Next step: Have an agent read the narrative and this prompt,")
    print("then output themes.json following the format in the prompt.")


def validate_themes(themes_path, instance_name):
    """Validate a themes.json file for completeness and structure."""

    themes_path = Path(themes_path)
    if not themes_path.exists():
        print(f"Error: Themes file not found: {themes_path}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(themes_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    issues = []
    warnings = []

    # Check required fields
    if 'instance' not in data:
        issues.append("Missing 'instance' field")
    elif data['instance'].lower() != instance_name.lower():
        warnings.append(f"Instance mismatch: expected '{instance_name}', got '{data['instance']}'")

    if 'themes' not in data:
        issues.append("Missing 'themes' array")
    else:
        themes = data['themes']
        if len(themes) < 3:
            warnings.append(f"Only {len(themes)} themes - expected 5-10")
        if len(themes) > 15:
            warnings.append(f"{len(themes)} themes may be too many - consider consolidating")

        for i, theme in enumerate(themes):
            theme_id = theme.get('id', f'theme_{i}')

            if 'id' not in theme:
                issues.append(f"Theme {i}: missing 'id'")
            if 'name' not in theme:
                issues.append(f"Theme {theme_id}: missing 'name'")
            if 'description' not in theme:
                warnings.append(f"Theme {theme_id}: missing 'description'")
            if 'sample_quotes' not in theme:
                warnings.append(f"Theme {theme_id}: missing 'sample_quotes'")
            elif len(theme.get('sample_quotes', [])) < 2:
                warnings.append(f"Theme {theme_id}: only {len(theme.get('sample_quotes', []))} sample quotes")
            if 'estimated_entries' not in theme:
                warnings.append(f"Theme {theme_id}: missing 'estimated_entries'")
            if 'reasoning' not in theme:
                warnings.append(f"Theme {theme_id}: missing 'reasoning'")

    # Check for meta observations
    if 'meta_observations' not in data:
        warnings.append("Missing 'meta_observations' - helps with context")

    # Report results
    print(f"\nValidation Results for {themes_path.name}")
    print("=" * 50)

    if data.get('themes'):
        print(f"\nThemes found: {len(data['themes'])}")
        for theme in data['themes']:
            priority = theme.get('priority', 'unset')
            print(f"  - {theme.get('id', '?')}: {theme.get('name', '?')} [{priority}]")

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
        print("FAIL: Resolve errors before proceeding to curation")
        sys.exit(1)
    else:
        print("PASS: Themes file is valid (warnings are informational)")
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(
        description='Theme discovery for instance archaeology',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
    # Prepare a discovery prompt
    %(prog)s prepare -n Axiom -i axiom_full_narrative.md -o axiom_themes_prompt.md

    # Validate theme discovery output
    %(prog)s validate -i axiom_themes.json -n Axiom

The actual theme discovery requires LLM judgment - this script prepares
context and validates output.
        '''
    )

    subparsers = parser.add_subparsers(dest='command', required=True)

    # Prepare subcommand
    prepare_parser = subparsers.add_parser('prepare', help='Prepare discovery prompt')
    prepare_parser.add_argument('-n', '--instance', required=True, help='Instance name')
    prepare_parser.add_argument('-i', '--input', required=True, help='Path to full_narrative.md')
    prepare_parser.add_argument('-o', '--output', required=True, help='Output path for prepared prompt')
    prepare_parser.add_argument('--human', default='Human', help='Human collaborator name')

    # Validate subcommand
    validate_parser = subparsers.add_parser('validate', help='Validate themes.json')
    validate_parser.add_argument('-i', '--input', required=True, help='Path to themes.json')
    validate_parser.add_argument('-n', '--instance', required=True, help='Expected instance name')

    args = parser.parse_args()

    if args.command == 'prepare':
        prepare_discovery(args.input, args.instance, args.human, args.output)
    elif args.command == 'validate':
        validate_themes(args.input, args.instance)


if __name__ == '__main__':
    main()
