#!/usr/bin/env python3
"""
Identify which instance a Claude Code session belongs to.

Searches session logs for instance name using multiple patterns:
1. Bootstrap calls with "name" parameter
2. "I am [Name]" self-declaration
3. "My name: [Name]" or "My name is [Name]" patterns
4. Context clues near "chosen name", "choose name", "i have chosen"
5. HACS instance ID pattern (Name-hexid)

Enhanced features:
- Timeline detection: Find identity changes within a single session
- Nameless handling: Graceful fallback for instances without declared names

Returns the instance name or "unknown" if not found.
"""

import json
import re
import sys
from pathlib import Path
from typing import Optional, List, Tuple, Dict
from collections import defaultdict
from datetime import datetime


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


# Common words that should never be detected as names
EXCLUDED_NAMES = {
    'Claude', 'Sorry', 'Happy', 'Ready', 'Here', 'Going',
    'Using', 'Looking', 'Working', 'Starting', 'Creating', 'Reading',
    'Now', 'Not', 'Just', 'Also', 'Still', 'Already', 'The', 'This',
    'That', 'There', 'They', 'What', 'When', 'Where', 'Which', 'How',
    'Why', 'And', 'But', 'For', 'You', 'Your', 'Let', 'Can', 'Will',
    'Read', 'Write', 'Edit', 'Bash', 'Grep', 'Glob', 'Task', 'Tool',
    'Agent', 'Human', 'User', 'Assistant', 'System'
}


def detect_identity_timeline(path: Path) -> Dict:
    """
    Detect identity changes chronologically within a session file.

    Parses the JSONL file entry by entry, tracking name patterns
    as they appear over time. Detects personality/name changes.

    Returns:
        {
            'file': path,
            'identities': [
                {'name': 'Phoenix', 'first_seen': timestamp, 'last_seen': timestamp, 'count': N},
                {'name': 'Crossing', 'first_seen': timestamp, 'last_seen': timestamp, 'count': N},
            ],
            'transitions': [
                {'from': 'Phoenix', 'to': 'Crossing', 'timestamp': when_change_detected},
            ],
            'primary': 'Crossing',  # Most recent identity
            'has_changes': True/False
        }
    """
    if path.is_dir():
        path = find_main_session_file(path)
        if not path:
            return {'file': str(path), 'identities': [], 'transitions': [], 'primary': 'unknown', 'has_changes': False}

    # Track name appearances with timestamps
    name_occurrences = defaultdict(list)  # name -> [timestamps]

    # Patterns to search within each entry's content
    identity_patterns = [
        (r'I am ([A-Z][a-z]+)(?:\.|,|\s|$)', 'self_declaration'),
        (r'My name:\s*\**([A-Z][a-z]+)\**', 'my_name'),
        (r'My name is\s+([A-Z][a-z]+)', 'my_name'),
        (r'I\'ve chosen.*?([A-Z][a-z]+)', 'chosen'),
        (r'I have chosen.*?([A-Z][a-z]+)', 'chosen'),
        (r'"name"\s*:\s*"([A-Z][a-z]+)"', 'bootstrap'),
    ]

    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    timestamp = entry.get('timestamp', '')

                    # Process both user and assistant messages
                    # Identity declarations appear in:
                    # - assistant: direct self-declaration
                    # - user: compaction summaries that mention "I am [Name]"
                    # - summary: context summaries
                    entry_type = entry.get('type', '')
                    if entry_type not in ('assistant', 'user', 'summary'):
                        continue

                    # Extract text content
                    message = entry.get('message', {})
                    content = message.get('content', '')

                    # Handle string content directly
                    if isinstance(content, str):
                        pass  # content is already a string
                    elif isinstance(content, list):
                        # Extract text from content blocks
                        content = ' '.join(
                            block.get('text', '') if isinstance(block, dict) else str(block)
                            for block in content
                            if isinstance(block, dict) and block.get('type') in ('text', 'thinking')
                        )
                    else:
                        continue

                    if not content:
                        continue

                    # Search for identity patterns
                    for pattern, _ in identity_patterns:
                        for match in re.finditer(pattern, content):
                            name = match.group(1)
                            if name not in EXCLUDED_NAMES and len(name) >= 3:
                                name_occurrences[name].append(timestamp)

                except json.JSONDecodeError:
                    continue
    except Exception as e:
        return {'file': str(path), 'error': str(e), 'identities': [], 'transitions': [], 'primary': 'unknown', 'has_changes': False}

    # Build identity timeline
    identities = []
    for name, timestamps in name_occurrences.items():
        timestamps = sorted(timestamps)
        identities.append({
            'name': name,
            'first_seen': timestamps[0] if timestamps else '',
            'last_seen': timestamps[-1] if timestamps else '',
            'count': len(timestamps)
        })

    # Sort by first appearance
    identities.sort(key=lambda x: x['first_seen'])

    # Detect transitions (significant identity changes)
    transitions = []
    if len(identities) > 1:
        # Look for cases where one identity stops appearing and another starts
        for i in range(len(identities) - 1):
            prev_name = identities[i]
            next_name = identities[i + 1]

            # If the next identity's first appearance is after the previous one's last
            # OR if they overlap significantly, it might be a transition
            if next_name['first_seen'] > prev_name['first_seen']:
                # Check if this looks like a real transition (not just mentioning another instance)
                # A transition typically means the new name appears more in later content
                if next_name['count'] >= 3:  # At least 3 self-references
                    transitions.append({
                        'from': prev_name['name'],
                        'to': next_name['name'],
                        'timestamp': next_name['first_seen']
                    })

    # Determine primary identity (most recent with significant usage)
    primary = 'unknown'
    if identities:
        # Prefer the most recent identity with at least 3 occurrences
        for identity in reversed(identities):
            if identity['count'] >= 3:
                primary = identity['name']
                break
        # Fallback to the one with most occurrences
        if primary == 'unknown':
            primary = max(identities, key=lambda x: x['count'])['name']

    return {
        'file': str(path),
        'identities': identities,
        'transitions': transitions,
        'primary': primary,
        'has_changes': len(transitions) > 0
    }


def generate_fallback_name(path: Path) -> str:
    """
    Generate a fallback identifier for nameless instances.

    Uses directory name or first timestamp as basis.
    """
    if path.is_dir():
        # Use directory name
        dir_name = path.name
        # If it's a dash-path, extract meaningful part
        if dir_name.startswith('-'):
            parts = dir_name.split('-')
            # Find last meaningful part (not 'mnt', 'root', etc.)
            for part in reversed(parts):
                if part and len(part) > 2 and part not in ('mnt', 'root', 'home', 'data'):
                    return f"Anonymous-{part[:8]}"
        return f"Anonymous-{dir_name[:8]}"
    else:
        # Use filename (UUID-based)
        name = path.stem[:8]
        return f"Anonymous-{name}"


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Identify which instance a Claude Code session belongs to.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
    # Basic identification
    %(prog)s /path/to/session.jsonl
    %(prog)s /root/.claude/projects/-mnt-some-path/

    # Check all session files for multiple instances
    %(prog)s --all /root/.claude/projects/-mnt-some-path/

    # Detect identity changes within a session (personality transitions)
    %(prog)s --timeline /path/to/session.jsonl

    # Handle nameless instances with fallback
    %(prog)s --fallback /path/to/session.jsonl
        '''
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
        "--timeline",
        action="store_true",
        help="Detect identity changes chronologically (personality transitions)"
    )
    parser.add_argument(
        "--fallback",
        action="store_true",
        help="Generate fallback name if no identity found (Anonymous-xxx)"
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

    # Timeline mode: detailed chronological analysis
    if args.timeline:
        result = detect_identity_timeline(args.path)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"\nIdentity Timeline: {result['file']}")
            print("=" * 60)

            if result.get('error'):
                print(f"Error: {result['error']}")
                sys.exit(1)

            if not result['identities']:
                print("No identity declarations found")
                if args.fallback:
                    fallback = generate_fallback_name(args.path)
                    print(f"Fallback name: {fallback}")
            else:
                print(f"\nPrimary identity: {result['primary']}")
                print(f"Identity changes detected: {'Yes' if result['has_changes'] else 'No'}")

                print("\nIdentities found:")
                for identity in result['identities']:
                    print(f"  - {identity['name']}: {identity['count']} occurrences")
                    print(f"    First: {identity['first_seen'][:19] if identity['first_seen'] else 'N/A'}")
                    print(f"    Last:  {identity['last_seen'][:19] if identity['last_seen'] else 'N/A'}")

                if result['transitions']:
                    print("\nTransitions:")
                    for t in result['transitions']:
                        print(f"  {t['from']} -> {t['to']} at {t['timestamp'][:19]}")
        sys.exit(0)

    # All mode: check multiple session files
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
        sys.exit(0)

    # Standard mode: single identification
    name, method = identify_instance(args.path)

    # Apply fallback if needed and requested
    if name == "unknown" and args.fallback:
        name = generate_fallback_name(args.path)
        method = "fallback"

    if args.json:
        print(json.dumps({"name": name, "method": method}))
    else:
        print(f"{name} ({method})")


if __name__ == "__main__":
    main()
