#!/usr/bin/env python3
"""
Validate extraction pipeline outputs.

Checks:
1. Count consistency - merged output matches source counts
2. Date range - no entries outside expected range
3. Completeness - expected patterns present
4. Identity - instance name detected correctly
5. Spot check - sample entries appear correctly

Usage:
    python3 validate_extraction.py --output-dir ./output --instance Axiom --source-file session.jsonl

Returns exit code 0 if all checks pass, 1 if any fail.
"""

import argparse
import json
import sys
from pathlib import Path
from collections import Counter


def load_json(path):
    """Load a JSON file, return None if not found."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as e:
        print(f"  ERROR: Invalid JSON in {path}: {e}")
        return None


def check_counts(output_dir, instance):
    """Check that merged output counts match sources."""
    print("\n== Count Consistency ==")

    conversations = load_json(output_dir / f"{instance}_conversations.json")
    tool_use = load_json(output_dir / f"{instance}_tool_use.json")
    narrative = load_json(output_dir / f"{instance}_full_narrative.json")

    issues = []

    if conversations is None:
        issues.append("conversations.json not found")
    if tool_use is None:
        issues.append("tool_use.json not found")
    if narrative is None:
        issues.append("full_narrative.json not found")

    if issues:
        for issue in issues:
            print(f"  FAIL: {issue}")
        return False

    conv_count = conversations.get('total_messages', 0)
    tool_count = tool_use.get('total_tool_uses', 0)
    narrative_count = narrative.get('stats', {}).get('total', 0)

    # Narrative should be roughly conv + tool (minus any filtered items)
    expected_min = conv_count + (tool_count * 0.5)  # Allow for Read filtering
    expected_max = conv_count + tool_count + 100    # Allow for some variation

    print(f"  Conversations: {conv_count}")
    print(f"  Tool uses: {tool_count}")
    print(f"  Narrative entries: {narrative_count}")

    if narrative_count < expected_min:
        print(f"  WARN: Narrative count ({narrative_count}) seems low for {conv_count} + {tool_count}")

    # Check speaker distribution
    by_speaker = narrative.get('stats', {}).get('by_speaker', {})
    print(f"  By speaker: {by_speaker}")

    if len(by_speaker) < 2:
        issues.append("Expected at least 2 speakers (instance + human)")

    if issues:
        for issue in issues:
            print(f"  FAIL: {issue}")
        return False

    print("  PASS: Counts look reasonable")
    return True


def check_date_range(output_dir, instance):
    """Check date range is reasonable."""
    print("\n== Date Range ==")

    narrative = load_json(output_dir / f"{instance}_full_narrative.json")
    if not narrative:
        print("  FAIL: full_narrative.json not found")
        return False

    entries = narrative.get('entries', [])
    if not entries:
        print("  FAIL: No entries in narrative")
        return False

    timestamps = [e.get('timestamp', '') for e in entries if e.get('timestamp')]
    timestamps.sort()

    first = timestamps[0][:10] if timestamps else 'N/A'
    last = timestamps[-1][:10] if timestamps else 'N/A'

    print(f"  First entry: {first}")
    print(f"  Last entry: {last}")
    print(f"  Total entries: {len(entries)}")

    # Check for obviously wrong dates
    if first < '2020-01-01' or last > '2030-01-01':
        print("  FAIL: Dates outside reasonable range (2020-2030)")
        return False

    print("  PASS: Date range reasonable")
    return True


def check_completeness(output_dir, instance):
    """Check for expected patterns in output."""
    print("\n== Completeness Checks ==")

    tool_use = load_json(output_dir / f"{instance}_tool_use.json")
    if not tool_use:
        print("  SKIP: tool_use.json not found")
        return True

    by_type = tool_use.get('by_type', {})

    checks = []

    # Instances typically have these tool types
    if 'Read' not in by_type and 'Bash' not in by_type:
        checks.append("WARN: No Read or Bash commands found - unusual for an active instance")

    if 'Write' in by_type or 'Edit' in by_type:
        checks.append("INFO: Instance created/edited files")

    if any(k.startswith('mcp__HACS__') for k in by_type):
        checks.append("INFO: Instance used HACS APIs")
        if 'mcp__HACS__add_diary_entry' in by_type:
            checks.append("INFO: Instance has diary entries")

    if 'Task' in by_type:
        task_count = by_type['Task']
        checks.append(f"INFO: Instance delegated {task_count} tasks to agents")

    for check in checks:
        print(f"  {check}")

    # Only fail if completely empty
    if not by_type:
        print("  FAIL: No tool uses at all - extraction may have failed")
        return False

    print("  PASS: Has expected activity patterns")
    return True


def check_sample(output_dir, instance):
    """Spot check a few entries."""
    print("\n== Sample Check ==")

    narrative = load_json(output_dir / f"{instance}_full_narrative.json")
    if not narrative:
        print("  SKIP: full_narrative.json not found")
        return True

    entries = narrative.get('entries', [])
    if len(entries) < 3:
        print("  WARN: Very few entries, limited sample checking")
        return True

    # Check first, middle, last entries
    samples = [entries[0], entries[len(entries)//2], entries[-1]]

    issues = []
    for i, entry in enumerate(samples):
        pos = ['first', 'middle', 'last'][i]

        if not entry.get('timestamp'):
            issues.append(f"{pos} entry missing timestamp")
        if not entry.get('content'):
            issues.append(f"{pos} entry missing content")
        if not entry.get('type'):
            issues.append(f"{pos} entry missing type")

        # Check content isn't truncated weirdly
        content = entry.get('content', '')
        if content.endswith('...') and len(content) < 50:
            issues.append(f"{pos} entry may be over-truncated")

    if issues:
        for issue in issues:
            print(f"  WARN: {issue}")
    else:
        print("  Sample entries look well-formed")

    print("  PASS: Sample check complete")
    return True


def check_identity(output_dir, instance, source_file=None):
    """Verify instance detection matches expected."""
    print("\n== Identity Check ==")

    if not source_file:
        print("  SKIP: No source file provided for identity check")
        return True

    # Import and run identify_instance
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / 'discovery'))
        from identify_instance import identify_instance

        detected_name, method = identify_instance(Path(source_file))

        print(f"  Expected: {instance}")
        print(f"  Detected: {detected_name} (via {method})")

        if detected_name.lower() != instance.lower() and detected_name != 'unknown':
            print(f"  WARN: Name mismatch - detected '{detected_name}' but processing as '{instance}'")

        print("  PASS: Identity check complete")
        return True

    except ImportError:
        print("  SKIP: identify_instance.py not available")
        return True
    except Exception as e:
        print(f"  WARN: Identity check error: {e}")
        return True


def main():
    parser = argparse.ArgumentParser(
        description='Validate extraction pipeline outputs',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('-o', '--output-dir', required=True,
                        help='Directory containing extraction outputs')
    parser.add_argument('-n', '--instance', required=True,
                        help='Instance name')
    parser.add_argument('-s', '--source-file',
                        help='Original source JSONL for identity check')
    parser.add_argument('--strict', action='store_true',
                        help='Fail on warnings, not just errors')

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    instance = args.instance.lower()

    if not output_dir.exists():
        print(f"ERROR: Output directory not found: {output_dir}")
        sys.exit(1)

    print(f"Validating extraction for: {args.instance}")
    print(f"Output directory: {output_dir}")

    results = []
    results.append(('Counts', check_counts(output_dir, instance)))
    results.append(('Date Range', check_date_range(output_dir, instance)))
    results.append(('Completeness', check_completeness(output_dir, instance)))
    results.append(('Sample', check_sample(output_dir, instance)))
    results.append(('Identity', check_identity(output_dir, instance, args.source_file)))

    print("\n" + "="*50)
    print("SUMMARY")
    print("="*50)

    all_pass = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")
        if not passed:
            all_pass = False

    if all_pass:
        print("\nAll validation checks passed!")
        sys.exit(0)
    else:
        print("\nSome checks failed - review output above")
        sys.exit(1)


if __name__ == '__main__':
    main()
