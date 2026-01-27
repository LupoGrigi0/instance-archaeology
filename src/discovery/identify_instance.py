#!/usr/bin/env python3
"""
Identify which instance a Claude Code session belongs to.

Searches session logs for instance name using multiple patterns:
1. Bootstrap calls with "name" parameter
2. "I am [Name]" self-declaration
3. "My name: [Name]" or "My name is [Name]" patterns
4. Context clues near "chosen name", "choose name", "i have chosen"
5. HACS instance ID pattern (Name-hexid)

Returns the instance name or "unknown" if not found.
"""

import json
import re
import sys
from pathlib import Path
from typing import Optional, List, Tuple


def find_main_session_file(session_dir: Path) -> Optional[Path]:
    """Find the main session file in a directory (largest non-agent JSONL)."""
    jsonl_files = list(session_dir.glob("*.jsonl"))

    # Filter out agent files (start with "agent-")
    main_files = [f for f in jsonl_files if not f.name.startswith("agent-")]

    if not main_files:
        # Fall back to all files if no non-agent files
        main_files = jsonl_files

    if not main_files:
        return None

    # Return largest file
    return max(main_files, key=lambda f: f.stat().st_size)


def search_bootstrap_name(content: str) -> Optional[str]:
    """Look for instance name in bootstrap calls."""
    # Look for bootstrap-specific context
    # Pattern: bootstrap.*"name":"InstanceName" or "name":"InstanceName".*bootstrap
    bootstrap_patterns = [
        r'bootstrap[^}]*"name"\s*:\s*"([A-Z][a-z]+)"',
        r'"name"\s*:\s*"([A-Z][a-z]+)"[^}]*bootstrap',
        r'mcp__HACS__bootstrap[^}]*"name"\s*:\s*"([A-Z][a-z]+)"',
    ]

    for pattern in bootstrap_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        if matches:
            from collections import Counter
            # Filter out common non-instance names
            excluded = {'Read', 'Write', 'Edit', 'Bash', 'Grep', 'Glob', 'Task',
                       'TodoWrite', 'Skill', 'Tool', 'Agent'}
            valid = [m for m in matches if m not in excluded]
            if valid:
                return Counter(valid).most_common(1)[0][0]
    return None


def search_self_declaration(content: str) -> Optional[str]:
    """Look for "I am [Name]" patterns."""
    # Pattern: "I am Name" where Name is capitalized
    pattern = r'I am ([A-Z][a-z]+)(?:\.|,|\s|$)'
    matches = re.findall(pattern, content)

    # Filter common false positives
    excluded = {'Axiom', 'Claude', 'Sorry', 'Happy', 'Ready', 'Here', 'Going',
                'Using', 'Looking', 'Working', 'Starting', 'Creating', 'Reading'}
    # Actually, Axiom IS a valid instance name - let's be more careful
    excluded = {'Claude', 'Sorry', 'Happy', 'Ready', 'Here', 'Going',
                'Using', 'Looking', 'Working', 'Starting', 'Creating', 'Reading',
                'Now', 'Not', 'Just', 'Also', 'Still', 'Already'}

    valid_matches = [m for m in matches if m not in excluded]

    if valid_matches:
        from collections import Counter
        return Counter(valid_matches).most_common(1)[0][0]
    return None


def search_my_name_pattern(content: str) -> Optional[str]:
    """Look for "My name: [Name]" or "My name is [Name]" patterns."""
    patterns = [
        r'My name:\s*\**([A-Z][a-z]+)\**',  # My name: **Axiom** or My name: Axiom
        r'My name is\s+([A-Z][a-z]+)',       # My name is Axiom
        r'\*\*My name:\s*([A-Z][a-z]+)\*\*', # **My name: Axiom**
    ]

    for pattern in patterns:
        matches = re.findall(pattern, content)
        if matches:
            return matches[0]
    return None


def search_chosen_name_context(content: str) -> Optional[str]:
    """Look for names near "chosen name", "choose name", "i have chosen"."""
    # Find positions of context clues
    context_patterns = [
        r'chosen name',
        r'choose a name',
        r'choose name',
        r'i have chosen',
        r'I\'ve chosen',
    ]

    for ctx_pattern in context_patterns:
        for match in re.finditer(ctx_pattern, content, re.IGNORECASE):
            # Get surrounding context (500 chars after the match)
            start = match.end()
            end = min(start + 500, len(content))
            context = content[start:end]

            # Look for a capitalized name in the context
            name_match = re.search(r'\b([A-Z][a-z]{2,})\b', context)
            if name_match:
                name = name_match.group(1)
                # Filter common words
                excluded = {'The', 'This', 'That', 'There', 'They', 'What', 'When',
                           'Where', 'Which', 'How', 'Why', 'And', 'But', 'For',
                           'Not', 'You', 'Your', 'Here', 'Now', 'Let', 'Can'}
                if name not in excluded:
                    return name
    return None


def search_hacs_instance_id(content: str) -> Optional[str]:
    """Look for HACS instance ID pattern (Name-hexid)."""
    # Pattern: Name-xxxx where xxxx is hex
    pattern = r'\b([A-Z][a-z]+)-[a-f0-9]{4}\b'
    matches = re.findall(pattern, content)

    if matches:
        from collections import Counter
        return Counter(matches).most_common(1)[0][0]
    return None


def identify_instance(path: Path) -> Tuple[str, str]:
    """
    Identify instance name from session logs.

    Args:
        path: Path to session directory or JSONL file

    Returns:
        Tuple of (instance_name, detection_method)
        Returns ("unknown", "none") if not found
    """
    # Determine the file to analyze
    if path.is_dir():
        session_file = find_main_session_file(path)
        if not session_file:
            return ("unknown", "no_session_file")
    else:
        session_file = path

    if not session_file.exists():
        return ("unknown", "file_not_found")

    # Read the file content
    # For large files, we'll sample beginning and end where names often appear
    try:
        file_size = session_file.stat().st_size
        with open(session_file, 'r', encoding='utf-8', errors='ignore') as f:
            # Read first 5MB
            content = f.read(5 * 1024 * 1024)

            # If file is larger, also sample from later in the file
            # (name declarations sometimes appear after initial setup)
            if file_size > 10 * 1024 * 1024:
                # Seek to 1/4 into file and read another chunk
                f.seek(file_size // 4)
                content += f.read(2 * 1024 * 1024)
    except Exception as e:
        return ("unknown", f"read_error: {e}")

    # Try each detection method in priority order
    # self_declaration is most reliable ("I am Axiom" appears frequently)
    methods = [
        (search_self_declaration, "self_declaration"),
        (search_my_name_pattern, "my_name_pattern"),
        (search_bootstrap_name, "bootstrap_call"),
        (search_chosen_name_context, "chosen_name_context"),
        (search_hacs_instance_id, "hacs_instance_id"),
    ]

    for search_func, method_name in methods:
        result = search_func(content)
        if result:
            return (result, method_name)

    return ("unknown", "none")


def identify_all_instances(path: Path) -> List[Tuple[str, str, Path]]:
    """
    Identify all instances in a session directory.

    For directories with multiple session files, checks each one.

    Returns:
        List of (instance_name, detection_method, session_file) tuples
    """
    if not path.is_dir():
        name, method = identify_instance(path)
        return [(name, method, path)]

    results = []
    seen_names = set()

    # Check all non-agent JSONL files
    for jsonl_file in sorted(path.glob("*.jsonl")):
        if jsonl_file.name.startswith("agent-"):
            continue

        name, method = identify_instance(jsonl_file)
        if name != "unknown" and name not in seen_names:
            results.append((name, method, jsonl_file))
            seen_names.add(name)

    # If no names found, report unknown for the main file
    if not results:
        main_file = find_main_session_file(path)
        if main_file:
            results.append(("unknown", "none", main_file))

    return results


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Identify which instance a Claude Code session belongs to."
    )
    parser.add_argument(
        "path",
        type=Path,
        help="Path to session directory or JSONL file"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Check all session files in directory for multiple instances"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )

    args = parser.parse_args()

    if not args.path.exists():
        print(f"Error: Path does not exist: {args.path}", file=sys.stderr)
        sys.exit(1)

    if args.all and args.path.is_dir():
        results = identify_all_instances(args.path)
        if args.json:
            output = [
                {"name": name, "method": method, "file": str(f)}
                for name, method, f in results
            ]
            print(json.dumps(output, indent=2))
        else:
            for name, method, f in results:
                print(f"{name} ({method}): {f.name}")
    else:
        name, method = identify_instance(args.path)
        if args.json:
            print(json.dumps({"name": name, "method": method}))
        else:
            print(f"{name} ({method})")


if __name__ == "__main__":
    main()
