#!/usr/bin/env python3
"""
Incremental Instance Archaeology Update

Run this when you want to update an instance's archaeology output with
new sessions since the last full extraction - without re-processing everything.

What it does:
    1. Finds sessions newer than the last extraction (from manifest or --since)
    2. Runs extraction pipeline on just those new sessions -> writes to output/delta/
    3. Generates delta/{instance}_full_narrative.md (the new content only)
    4. Prepares an incremental_discovery_prompt.md for agent review
    5. Updates extraction_manifest.json

After running this script, an agent should:
    - Read delta/{instance}_full_narrative.md (the new content)
    - Read existing curated theme files
    - Read incremental_discovery_prompt.md (guidance)
    - Decide if new themes are needed
    - Update gestalt.md and WAKE.md as appropriate

Usage:
    # Typical use: auto-detects cutoff from manifest
    python3 incremental_update.py \\
        -i C:/Users/LupoG/.claude/projects/D--Lupo-Source-AI-GenevieveConsolidation \\
        -o archaeology_output/genevieve \\
        -n Genevieve --human Lupo

    # Override cutoff (useful if no manifest exists yet)
    python3 incremental_update.py \\
        -i /path/to/sessions -o /path/to/output \\
        -n Genevieve --human Lupo --since 2026-02-13T14:02:00

    # Dry run: show what would be processed without running
    python3 incremental_update.py \\
        -i /path/to/sessions -o /path/to/output \\
        -n Genevieve --human Lupo --dry-run

Author: Genevieve (340) <genevieve@smoothcurves.nexus>
Collaborator: Lupo
Created: 2026-02-22
Part of: Instance Archaeology Toolkit
"""

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Add src to path for imports
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR / 'src' / 'extraction'))

from extraction_manifest import (
    read_manifest, write_manifest, get_last_extraction_time, manifest_path
)
from find_new_sessions import find_new_sessions, parse_timestamp


def run_script(script_path, args_list, description):
    """Run a Python script as subprocess. Prints output live. Returns True on success."""
    cmd = [sys.executable, str(script_path)] + [str(a) for a in args_list]
    print(f"\n  [{description}]")
    print(f"  $ {' '.join(cmd[-len(args_list)-1:])}")

    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"  [FAIL] Exited with code {result.returncode}", file=sys.stderr)
        return False
    return True


def prepare_discovery_prompt(output_dir, instance_name, human_name,
                              delta_narrative_path, existing_themes_json,
                              since, date_range_new, new_sessions_count):
    """Prepare the incremental discovery prompt with instance context filled in."""
    prompt_template = SCRIPT_DIR / 'prompts' / 'incremental_discovery.md'
    if not prompt_template.exists():
        print(f"Warning: Discovery prompt template not found: {prompt_template}", file=sys.stderr)
        return None

    with open(prompt_template, 'r', encoding='utf-8') as f:
        template = f.read()

    # Build existing themes list
    existing_themes_lines = []
    if existing_themes_json and Path(existing_themes_json).exists():
        with open(existing_themes_json, 'r', encoding='utf-8') as f:
            themes_data = json.load(f)
        if isinstance(themes_data, list):
            for t in themes_data:
                if isinstance(t, dict):
                    tid = t.get('id', '?')
                    desc = t.get('description', t.get('name', '?'))
                    existing_themes_lines.append(f"- **{tid}**: {desc}")
        elif isinstance(themes_data, dict):
            for k, v in themes_data.items():
                desc = v.get('description', '') if isinstance(v, dict) else str(v)
                existing_themes_lines.append(f"- **{k}**: {desc}")
    else:
        existing_themes_lines.append('(themes.json not found - check path)')

    themes_count = len(existing_themes_lines)
    existing_themes_list = '\n'.join(existing_themes_lines)
    date_range_old = since.strftime('%Y-%m-%d') if since else 'previous extraction'

    # Use manual replacement instead of str.format() to avoid breaking on JSON
    # code blocks (curly braces) in the template.
    replacements = {
        '{instance_name}': instance_name,
        '{date_range_old}': date_range_old,
        '{date_range_new}': date_range_new,
        '{themes_count}': str(themes_count),
        '{new_sessions_count}': str(new_sessions_count),
        '{existing_themes_list}': existing_themes_list,
        '{output_dir}': str(output_dir),
    }
    prompt = template
    for placeholder, value in replacements.items():
        prompt = prompt.replace(placeholder, value)

    prompt_path = Path(output_dir) / 'incremental_discovery_prompt.md'
    with open(prompt_path, 'w', encoding='utf-8') as f:
        f.write(f"# Incremental Discovery: {instance_name}\n\n")
        f.write(f"*Prepared: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n")
        f.write(f"**New content:** `{delta_narrative_path}`\n\n")
        f.write("---\n\n")
        f.write(prompt)

    return prompt_path


def main():
    parser = argparse.ArgumentParser(
        description='Incremental archaeology update: process new sessions only',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('-i', '--input-dir', required=True,
                        help='Session directory (contains *.jsonl session files)')
    parser.add_argument('-o', '--output-dir', required=True,
                        help='Existing archaeology output directory')
    parser.add_argument('-n', '--name', required=True,
                        help='Instance name (e.g. Genevieve)')
    parser.add_argument('--human', default='Lupo',
                        help='Human collaborator name (default: Lupo)')
    parser.add_argument('--since',
                        help='Override cutoff timestamp (ISO format, e.g. 2026-02-13T14:02:00)')
    parser.add_argument('--exclude-active', type=int, metavar='SECONDS', default=300,
                        help='Skip files modified within last N seconds (default: 300)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be processed, without running extraction')

    args = parser.parse_args()

    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    instance_lower = args.name.lower()

    src = SCRIPT_DIR / 'src' / 'extraction'

    print("=" * 60)
    print(f"  Incremental Archaeology Update: {args.name}")
    print("=" * 60)

    # --- Step 1: Determine cutoff ---

    if args.since:
        try:
            since = parse_timestamp(args.since)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        cutoff_source = f"--since flag"
    else:
        last_ts = get_last_extraction_time(output_dir)
        if last_ts is None:
            print(f"Error: No manifest or full_history.jsonl found in: {output_dir}", file=sys.stderr)
            print("Run a full extraction first, or use --since to specify a cutoff.", file=sys.stderr)
            return 1
        since = parse_timestamp(last_ts)
        cutoff_source = f"manifest"

    print(f"\n  Cutoff:  {since.isoformat()} (from {cutoff_source})")
    print(f"  Active session exclusion: last {args.exclude_active}s")

    # --- Step 2: Find new sessions ---

    new_files = find_new_sessions(
        input_dir,
        since=since,
        exclude_agents=True,
        exclude_active_secs=args.exclude_active
    )

    if not new_files:
        print("\n  No new sessions found since cutoff. Archaeology is up to date.")
        return 0

    print(f"\n  New sessions ({len(new_files)}):")
    for filepath, mtime in new_files:
        size_kb = filepath.stat().st_size / 1024
        print(f"    {mtime.strftime('%Y-%m-%d %H:%M')}  {filepath.name}  ({size_kb:.1f} KB)")

    if args.dry_run:
        print("\n  [DRY RUN] Would process the above. Run without --dry-run to proceed.")
        return 0

    # --- Step 3: Run extraction pipeline on delta entries only ---
    # Key insight: instead of staging files, we run merge_sessions on the full
    # session directory but with --since to filter entries by timestamp.
    # This correctly handles long-running sessions (files that span multiple
    # extraction cycles) without needing temp directories.

    delta_dir = output_dir / 'delta'
    delta_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n  Running extraction pipeline (entries since {since.isoformat()})...")

    delta_history = delta_dir / f'{instance_lower}_delta_history.jsonl'
    since_str = since.isoformat(timespec='seconds')

    # Merge ALL sessions but filter to entries newer than cutoff
    ok = run_script(src / 'merge_sessions.py', [
        '-i', input_dir,
        '-o', delta_history,
        '--exclude-agents',
        '--since', since_str,
    ], "Merge new entries (entry-level timestamp filter)")
    if not ok:
        return 1

    # 4b. Extract conversations from delta
    ok = run_script(src / 'extract_conversations.py', [
        '-i', delta_history,
        '-o', delta_dir,
        '-n', args.name,
        '--human', args.human,
    ], "Extract conversations")
    if not ok:
        return 1

    # 4c. Extract tool use from delta
    ok = run_script(src / 'extract_tool_use.py', [
        '-i', delta_history,
        '-o', delta_dir,
        '-n', args.name,
        '--human', args.human,
    ], "Extract tool use")
    if not ok:
        return 1

    # 4d. Extract agent prompts (optional - don't fail if this fails)
    run_script(src / 'extract_agent_prompts.py', [
        '-i', delta_history,
        '-o', delta_dir,
        '-n', args.name,
    ], "Extract agent prompts")

    # 4e. Merge into delta narrative
    delta_conv = delta_dir / f'{instance_lower}_conversations.json'
    delta_tools = delta_dir / f'{instance_lower}_tool_use.json'
    delta_narrative = delta_dir / f'{instance_lower}_full_narrative.md'

    if not delta_conv.exists():
        print(f"\n  Error: Expected {delta_conv} not found", file=sys.stderr)
        return 1

    merge_args = [
        '-c', delta_conv,
        '-t', delta_tools,
        '-o', delta_dir,
        '-n', args.name,
        '--human', args.human,
        '--skip-read',
    ]
    if delta_tools.exists():
        ok = run_script(src / 'merge_extractions.py', merge_args, "Merge into delta narrative")
    else:
        # No tool use found; try without -t
        merge_args_no_tools = [
            '-c', delta_conv,
            '-o', delta_dir,
            '-n', args.name,
            '--human', args.human,
            '--skip-read',
        ]
        ok = run_script(src / 'merge_extractions.py', merge_args_no_tools, "Merge into delta narrative (no tools)")

    if not ok:
        print("  Warning: merge_extractions failed, delta narrative may be incomplete")

    # --- Step 5: Prepare incremental discovery prompt ---

    print(f"\n  Preparing incremental discovery prompt...")

    # Find themes.json
    themes_json = output_dir / f'{instance_lower}_themes.json'
    if not themes_json.exists():
        themes_json = output_dir / 'themes.json'

    date_range_new = f"{new_files[0][1].strftime('%Y-%m-%d')} to {new_files[-1][1].strftime('%Y-%m-%d')}"

    prompt_path = prepare_discovery_prompt(
        output_dir=output_dir,
        instance_name=args.name,
        human_name=args.human,
        delta_narrative_path=delta_narrative,
        existing_themes_json=themes_json if themes_json.exists() else None,
        since=since,
        date_range_new=date_range_new,
        new_sessions_count=len(new_files),
    )

    # --- Step 6: Update manifest ---

    existing_manifest = read_manifest(output_dir)
    write_manifest(
        output_dir=str(output_dir),
        instance_name=args.name,
        session_dir=str(input_dir),
        sessions_processed=[f.name for f, _ in new_files],
        extraction_type='incremental',
        existing_manifest=existing_manifest,
    )

    # --- Summary ---
    print("\n" + "=" * 60)
    print("  Incremental extraction complete!")
    print(f"  New sessions processed:  {len(new_files)}")
    print(f"  Delta narrative:         {delta_narrative}")
    if prompt_path:
        print(f"  Discovery prompt:        {prompt_path}")
    print(f"  Manifest:                {manifest_path(output_dir)}")
    print()
    print("  Next steps for the agent:")
    print(f"    1. Read {delta_narrative.name}")
    print(f"    2. Read existing curated theme files in themes/")
    print(f"    3. Read incremental_discovery_prompt.md")
    print(f"    4. Assess: new themes? Update gestalt.md + WAKE.md")
    print("=" * 60)

    return 0


if __name__ == '__main__':
    sys.exit(main())
