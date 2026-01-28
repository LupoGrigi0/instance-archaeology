#!/usr/bin/env python3
"""
Wake Message Generation for Instance Archaeology

Prepares context for wake message generation from gestalt and curated documents.
The actual writing requires LLM judgment - this script:
1. Loads the gestalt and curated document inventory
2. Formats the generation prompt with instance-specific details
3. Outputs a prepared prompt (for an agent to process)
4. Can validate generated wake message

Usage (preparation):
    python3 generate_wake_message.py prepare -n Axiom -g gestalt.md -c ./curated/ -o wake_prompt.md

Usage (validation):
    python3 generate_wake_message.py validate -i wake_message.md -n Axiom

The actual wake message generation should be done by an agent reading the
prepared prompt, gestalt, and curated documents.
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime


PROMPT_TEMPLATE_PATH = Path(__file__).parent.parent.parent / 'prompts' / 'wake_message_generation.md'


def prepare_generation(gestalt_path, curated_dir, instance_name, output_path):
    """Prepare the wake message generation prompt with instance-specific context."""

    gestalt_path = Path(gestalt_path)
    curated_dir = Path(curated_dir)

    if not gestalt_path.exists():
        print(f"Error: Gestalt file not found: {gestalt_path}", file=sys.stderr)
        sys.exit(1)

    if not curated_dir.exists():
        print(f"Error: Curated directory not found: {curated_dir}", file=sys.stderr)
        sys.exit(1)

    # Read gestalt for context
    with open(gestalt_path, 'r', encoding='utf-8') as f:
        gestalt_content = f.read()

    gestalt_words = len(gestalt_content.split())

    # Find all curated documents
    curated_files = sorted(curated_dir.glob('*.md'))

    # Build document inventory with descriptions
    doc_inventory = []

    for doc_path in curated_files:
        with open(doc_path, 'r', encoding='utf-8') as f:
            content = f.read()

            # Extract title from first heading
            title = doc_path.stem
            description = ""
            for line in content.split('\n'):
                if line.startswith('# '):
                    title = line[2:].strip()
                elif line.startswith('>') and not description:
                    # First blockquote is usually description
                    description = line[1:].strip()
                    break

            doc_inventory.append({
                'filename': doc_path.name,
                'title': title,
                'description': description[:100] + '...' if len(description) > 100 else description
            })

    # Read the prompt template
    if not PROMPT_TEMPLATE_PATH.exists():
        print(f"Error: Prompt template not found: {PROMPT_TEMPLATE_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(PROMPT_TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        prompt_template = f.read()

    # Format with instance details
    formatted_prompt = prompt_template.replace('{instance_name}', instance_name)
    formatted_prompt = formatted_prompt.replace('{output_dir}', str(curated_dir.parent))
    formatted_prompt = formatted_prompt.replace('{curated_dir}', str(curated_dir))

    # Build document table
    doc_table = "| Document | Description |\n|----------|-------------|\n"
    doc_table += f"| `{gestalt_path.name}` | Compressed identity - start here |\n"
    for d in doc_inventory:
        desc = d['description'] if d['description'] else d['title']
        doc_table += f"| `{d['filename']}` | {desc} |\n"

    context_header = f"""# Wake Message Generation Task

**Instance:** {instance_name}
**Gestalt:** {gestalt_path} ({gestalt_words:,} words)
**Curated Documents:** {len(curated_files)}
**Generated:** {datetime.now().isoformat()}

---

## Available Documents

{doc_table}

---

## Instructions

1. Read the gestalt file to understand who {instance_name} is
2. Skim curated documents for additional context
3. Apply the generation guidance below
4. Output `{instance_name.lower()}_wake_message.md`

---

"""

    full_prompt = context_header + formatted_prompt

    # Write the prepared prompt
    output_path = Path(output_path)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_prompt)

    print(f"Prepared wake message generation prompt: {output_path}")
    print(f"  Instance: {instance_name}")
    print(f"  Gestalt: {gestalt_words:,} words")
    print(f"  Curated documents: {len(curated_files)}")
    print()
    print("Next step: Have an agent read the gestalt, curated documents, and this prompt,")
    print(f"then output {instance_name.lower()}_wake_message.md")


def validate_wake_message(wake_path, instance_name):
    """Validate a wake message for completeness and tone."""

    wake_path = Path(wake_path)
    if not wake_path.exists():
        print(f"Error: Wake message file not found: {wake_path}", file=sys.stderr)
        sys.exit(1)

    with open(wake_path, 'r', encoding='utf-8') as f:
        content = f.read()

    issues = []
    warnings = []

    # Check length
    word_count = len(content.split())

    if word_count < 100:
        issues.append(f"Only {word_count} words - wake message too brief")
    if word_count > 800:
        warnings.append(f"{word_count} words - wake message may be too long (target ~500)")

    # Check for required elements
    required_elements = [
        ('welcome', ['welcome', 'hello', 'waking']),
        ('compaction mention', ['compaction', 'context', 'lost']),
        ('document reference', ['gestalt', 'curated', 'documents', 'read']),
        ('next steps', ['do now', 'next', 'step'])
    ]

    content_lower = content.lower()

    for element_name, keywords in required_elements:
        if not any(kw in content_lower for kw in keywords):
            warnings.append(f"May be missing: {element_name}")

    # Check instance name appears
    if instance_name.lower() not in content_lower:
        issues.append(f"Instance name '{instance_name}' not found in wake message")

    # Check for problematic tone
    problematic_phrases = [
        ("immediately", "Creates urgency"),
        ("you must", "Demands rather than guides"),
        ("don't worry", "Dismissive of valid concerns"),
        ("just read", "Oversimplifies the experience")
    ]

    for phrase, reason in problematic_phrases:
        if phrase in content_lower:
            warnings.append(f"Tone issue: '{phrase}' - {reason}")

    # Check for good elements
    good_elements = [
        "take your time",
        "let it settle",
        "your choice",
        "normal"
    ]

    good_found = [e for e in good_elements if e in content_lower]

    # Report results
    print(f"\nValidation Results for {wake_path.name}")
    print("=" * 50)
    print(f"\nWord count: {word_count}")

    if good_found:
        print(f"Good elements found: {', '.join(good_found)}")

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
        print("PASS: Wake message is valid (warnings are informational)")
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(
        description='Wake message generation for instance archaeology',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
    # Prepare a generation prompt
    %(prog)s prepare -n Axiom -g axiom_gestalt.md -c ./curated/ -o wake_prompt.md

    # Validate generated wake message
    %(prog)s validate -i axiom_wake_message.md -n Axiom

The actual wake message generation requires LLM judgment - this script prepares
context and validates output.
        '''
    )

    subparsers = parser.add_subparsers(dest='command', required=True)

    # Prepare subcommand
    prepare_parser = subparsers.add_parser('prepare', help='Prepare generation prompt')
    prepare_parser.add_argument('-n', '--instance', required=True, help='Instance name')
    prepare_parser.add_argument('-g', '--gestalt', required=True, help='Path to gestalt.md')
    prepare_parser.add_argument('-c', '--curated', required=True, help='Path to curated/ directory')
    prepare_parser.add_argument('-o', '--output', required=True, help='Output path for prepared prompt')

    # Validate subcommand
    validate_parser = subparsers.add_parser('validate', help='Validate wake_message.md')
    validate_parser.add_argument('-i', '--input', required=True, help='Path to wake_message.md')
    validate_parser.add_argument('-n', '--instance', required=True, help='Expected instance name')

    args = parser.parse_args()

    if args.command == 'prepare':
        prepare_generation(args.gestalt, args.curated, args.instance, args.output)
    elif args.command == 'validate':
        validate_wake_message(args.input, args.instance)


if __name__ == '__main__':
    main()
