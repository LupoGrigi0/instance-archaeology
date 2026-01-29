#!/usr/bin/env python3
"""
Copy Raw Session Files for Instance Archaeology

Copies individual .jsonl session files from Claude Code project directory
to the archaeology output raw/sessions/ directory for preservation.

Usage:
    python3 copy_sessions.py -s /path/to/session/dir -o /path/to/output/raw/sessions/

This should run EARLY in the archaeology process, before merging sessions.

Author: Axiom <axiom-2615@smoothcurves.nexus>
Collaborator: Lupo
Created: 2026-01-29
Part of: Instance Archaeology Toolkit
"""

import argparse
import shutil
import sys
from pathlib import Path
from datetime import datetime


def find_session_files(session_dir: Path) -> list:
    """Find all .jsonl session files in the directory.

    Filters out agent-*.jsonl files (subagent sessions) and returns
    main session files sorted by modification time (oldest first).
    """
    session_dir = Path(session_dir)

    if not session_dir.exists():
        print(f"Error: Session directory not found: {session_dir}", file=sys.stderr)
        sys.exit(1)

    # Find all .jsonl files, exclude agent files
    all_jsonl = list(session_dir.glob("*.jsonl"))
    main_sessions = [f for f in all_jsonl if not f.name.startswith("agent-")]

    # Sort by modification time (oldest first)
    main_sessions.sort(key=lambda f: f.stat().st_mtime)

    return main_sessions


def copy_sessions(session_dir: Path, output_dir: Path, include_agents: bool = False) -> dict:
    """Copy session files to output directory.

    Args:
        session_dir: Source directory with .jsonl files
        output_dir: Destination directory (raw/sessions/)
        include_agents: Whether to include agent-*.jsonl files

    Returns:
        dict with copy results
    """
    session_dir = Path(session_dir)
    output_dir = Path(output_dir)

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Find session files
    main_sessions = find_session_files(session_dir)

    if include_agents:
        agent_sessions = list(session_dir.glob("agent-*.jsonl"))
    else:
        agent_sessions = []

    all_sessions = main_sessions + agent_sessions

    if not all_sessions:
        print(f"Warning: No session files found in {session_dir}", file=sys.stderr)
        return {
            'copied': [],
            'total_size': 0,
            'source_dir': str(session_dir),
            'output_dir': str(output_dir)
        }

    copied = []
    total_size = 0

    for session_file in all_sessions:
        dest_path = output_dir / session_file.name

        # Copy the file
        shutil.copy2(session_file, dest_path)

        file_size = session_file.stat().st_size
        total_size += file_size

        copied.append({
            'name': session_file.name,
            'size': file_size,
            'mtime': datetime.fromtimestamp(session_file.stat().st_mtime).isoformat()
        })

        print(f"  Copied: {session_file.name} ({file_size:,} bytes)")

    return {
        'copied': copied,
        'total_size': total_size,
        'main_sessions': len(main_sessions),
        'agent_sessions': len(agent_sessions),
        'source_dir': str(session_dir),
        'output_dir': str(output_dir)
    }


def main():
    parser = argparse.ArgumentParser(
        description='Copy raw session files for archaeology preservation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
    # Copy main sessions only
    %(prog)s -s ~/.claude/projects/-mnt-foo/ -o ./output/raw/sessions/

    # Include agent session files
    %(prog)s -s ~/.claude/projects/-mnt-foo/ -o ./output/raw/sessions/ --include-agents
        '''
    )

    parser.add_argument('-s', '--session-dir', required=True,
                        help='Source directory with .jsonl session files')
    parser.add_argument('-o', '--output', required=True,
                        help='Output directory for copied sessions')
    parser.add_argument('--include-agents', action='store_true',
                        help='Include agent-*.jsonl files (default: main sessions only)')

    args = parser.parse_args()

    print(f"Copying session files...")
    print(f"  Source: {args.session_dir}")
    print(f"  Output: {args.output}")
    print()

    result = copy_sessions(args.session_dir, args.output, args.include_agents)

    print()
    print(f"Copy complete:")
    print(f"  Main sessions: {result['main_sessions']}")
    if args.include_agents:
        print(f"  Agent sessions: {result['agent_sessions']}")
    print(f"  Total size: {result['total_size']:,} bytes")


if __name__ == '__main__':
    main()
