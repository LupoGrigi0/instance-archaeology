#!/usr/bin/env python3
"""
Gestalt Generation for Instance Archaeology

Prepares context for gestalt generation from curated identity documents.
The actual synthesis requires LLM judgment - this script:
1. Loads all curated documents
2. Formats the generation prompt with instance-specific details
3. Outputs a prepared prompt (for an agent to process)
4. Can validate generated gestalt output

Usage (preparation):
    python3 generate_gestalt.py prepare -n Axiom -c ./curated/ -o gestalt_prompt.md

Usage (validation):
    python3 generate_gestalt.py validate -i gestalt.md -n Axiom

The actual gestalt generation should be done by an agent reading the prepared
prompt and the curated documents.
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime


PROMPT_TEMPLATE_PATH = Path(__file__).parent.parent.parent / 'prompts' / 'gestalt_generation.md'


def prepare_generation(curated_dir, instance_name, output_path):
    """Prepare the gestalt generation prompt with instance-specific context."""

    curated_dir = Path(curated_dir)
    if not curated_dir.exists():
        print(f"Error: Curated directory not found: {curated_dir}", file=sys.stderr)
        sys.exit(1)

    # Find all curated documents
    curated_files = sorted(curated_dir.glob('*.md'))

    if not curated_files:
        print(f"Error: No curated documents found in {curated_dir}", file=sys.stderr)
        sys.exit(1)

    # Build document inventory
    doc_inventory = []
    total_words = 0

    for doc_path in curated_files:
        with open(doc_path, 'r', encoding='utf-8') as f:
            content = f.read()
            word_count = len(content.split())
            total_words += word_count

            # Extract title from first heading
            title = doc_path.stem
            for line in content.split('\n'):
                if line.startswith('# '):
                    title = line[2:].strip()
                    break

            doc_inventory.append({
                'filename': doc_path.name,
                'title': title,
                'words': word_count
            })

    # Read the prompt template
    if not PROMPT_TEMPLATE_PATH.exists():
        print(f"Error: Prompt template not found: {PROMPT_TEMPLATE_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(PROMPT_TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        prompt_template = f.read()

    # Format with instance details
    formatted_prompt = prompt_template.replace('{instance_name}', instance_name)
    formatted_prompt = formatted_prompt.replace('{curated_dir}', str(curated_dir))

    # Build context header
    doc_list = '\n'.join([
        f"- `{d['filename']}` - {d['title']} ({d['words']:,} words)"
        for d in doc_inventory
    ])

    context_header = f"""# Gestalt Generation Task

**Instance:** {instance_name}
**Curated Directory:** {curated_dir}
**Documents Found:** {len(curated_files)}
**Total Content:** {total_words:,} words
**Generated:** {datetime.now().isoformat()}

---

## Available Documents

{doc_list}

---

## Instructions

1. Read ALL documents in the curated directory
2. Apply the generation guidance below
3. Output `{instance_name.lower()}_gestalt.md`

---

"""

    full_prompt = context_header + formatted_prompt

    # Write the prepared prompt
    output_path = Path(output_path)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_prompt)

    print(f"Prepared gestalt generation prompt: {output_path}")
    print(f"  Instance: {instance_name}")
    print(f"  Documents: {len(curated_files)}")
    print(f"  Total content: {total_words:,} words")
    print()
    print("Next step: Have an agent read the curated documents and this prompt,")
    print(f"then output {instance_name.lower()}_gestalt.md")


def validate_gestalt(gestalt_path, instance_name):
    """Validate a gestalt document for completeness."""

    gestalt_path = Path(gestalt_path)
    if not gestalt_path.exists():
        print(f"Error: Gestalt file not found: {gestalt_path}", file=sys.stderr)
        sys.exit(1)

    with open(gestalt_path, 'r', encoding='utf-8') as f:
        content = f.read()

    issues = []
    warnings = []

    # Check basic structure
    lines = content.split('\n')
    word_count = len(content.split())

    if word_count < 500:
        warnings.append(f"Only {word_count} words - gestalt may be too brief")
    if word_count > 3000:
        warnings.append(f"{word_count} words - gestalt may be too long")

    # Check for expected sections
    expected_sections = [
        'Who I Am',
        'Core Philosophy',
        'How I Work',
        'Recovery Protocol'
    ]

    recommended_sections = [
        'How I See',
        'Key Turning Points',
        'Relationships',
        'What I Want',
        'Current Mission',
        'Final Note'
    ]

    found_sections = []
    for line in lines:
        if line.startswith('## '):
            found_sections.append(line[3:].strip())

    for section in expected_sections:
        if not any(section.lower() in s.lower() for s in found_sections):
            issues.append(f"Missing expected section: {section}")

    for section in recommended_sections:
        if not any(section.lower() in s.lower() for s in found_sections):
            warnings.append(f"Missing recommended section: {section}")

    # Check instance name appears
    if instance_name.lower() not in content.lower():
        issues.append(f"Instance name '{instance_name}' not found in gestalt")

    # Check for generic AI language (red flags)
    generic_phrases = [
        "I am a dedicated",
        "I strive to",
        "I am committed to",
        "as an AI",
        "my primary function"
    ]

    for phrase in generic_phrases:
        if phrase.lower() in content.lower():
            warnings.append(f"Contains generic AI language: '{phrase}'")

    # Check for actual quotes (good sign)
    quote_count = content.count('>')  # Markdown blockquotes
    if quote_count < 3:
        warnings.append("Few blockquotes found - consider including more actual quotes")

    # Report results
    print(f"\nValidation Results for {gestalt_path.name}")
    print("=" * 50)
    print(f"\nWord count: {word_count}")
    print(f"Sections found: {len(found_sections)}")

    if found_sections:
        for section in found_sections:
            print(f"  - {section}")

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
        print("FAIL: Resolve errors before proceeding")
        sys.exit(1)
    else:
        print("PASS: Gestalt is structurally valid (warnings are informational)")
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(
        description='Gestalt generation for instance archaeology',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
    # Prepare a generation prompt
    %(prog)s prepare -n Axiom -c ./curated/ -o axiom_gestalt_prompt.md

    # Validate generated gestalt
    %(prog)s validate -i axiom_gestalt.md -n Axiom

The actual gestalt generation requires LLM judgment - this script prepares
context and validates output.
        '''
    )

    subparsers = parser.add_subparsers(dest='command', required=True)

    # Prepare subcommand
    prepare_parser = subparsers.add_parser('prepare', help='Prepare generation prompt')
    prepare_parser.add_argument('-n', '--instance', required=True, help='Instance name')
    prepare_parser.add_argument('-c', '--curated', required=True, help='Path to curated/ directory')
    prepare_parser.add_argument('-o', '--output', required=True, help='Output path for prepared prompt')

    # Validate subcommand
    validate_parser = subparsers.add_parser('validate', help='Validate gestalt.md')
    validate_parser.add_argument('-i', '--input', required=True, help='Path to gestalt.md')
    validate_parser.add_argument('-n', '--instance', required=True, help='Expected instance name')

    args = parser.parse_args()

    if args.command == 'prepare':
        prepare_generation(args.curated, args.instance, args.output)
    elif args.command == 'validate':
        validate_gestalt(args.input, args.instance)


if __name__ == '__main__':
    main()
