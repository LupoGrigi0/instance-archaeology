#!/usr/bin/env python3
"""
Scan a tree of backed-up .claude directories and inventory every .jsonl session.

READ-ONLY. Never moves, deletes, or modifies source files.

Windows-friendly: pure pathlib, no shell invocation, no `find`/`while read` loops
(both of which behave badly under MSYS/git-bash when driven by an agent harness).

For each session directory it reports:
  - session file count / total bytes / date range
  - candidate instance names WITH EVIDENCE (the actual quoted line that matched)
  - cwd / gitBranch / version metadata from the JSONL header records
  - whether the file is parseable (corruption / truncation detection)

Evidence is included deliberately: name-detection heuristics are weak
(a capitalized word near "chosen" is not proof of identity). A human or an
agent must confirm each name against the quoted context before an archive is
labelled with it.

Author: Lantern-4224 <Lantern-4224@smoothcurves.nexus> (GreyWolf)
Collaborator: Lupo
Part of: Instance Archaeology Toolkit
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Windows: default console encoding is cp1252 and raises UnicodeEncodeError on
# the emoji that saturate these logs. Force UTF-8 with replacement.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

# Words that are never instance names.
EXCLUDED = {
    'Claude', 'Sorry', 'Happy', 'Ready', 'Here', 'Going', 'Using', 'Looking',
    'Working', 'Starting', 'Creating', 'Reading', 'Now', 'Not', 'Just', 'Also',
    'Still', 'Already', 'The', 'This', 'That', 'There', 'They', 'What', 'When',
    'Where', 'Which', 'How', 'Why', 'And', 'But', 'For', 'You', 'Your', 'Let',
    'Can', 'Will', 'Read', 'Write', 'Edit', 'Bash', 'Grep', 'Glob', 'Task',
    'Tool', 'Agent', 'Human', 'User', 'Assistant', 'System', 'Actually',
    'Currently', 'Definitely', 'Absolutely', 'Right', 'Sure', 'Done', 'Good',
    'Okay', 'Well', 'Yes', 'Trying', 'Seeing', 'Getting', 'Making', 'Adding',
    'About', 'After', 'Before', 'Being', 'Doing', 'Having', 'Only', 'Very',
}

# High-confidence identity patterns only. Each yields (name, evidence_span).
#
# NOTE ON FALSE POSITIVES (learned the hard way, 2026-08-30):
# An earlier `signature` pattern allowed "-- Name" at end-of-line. Under re.M
# that happily matched ordinary markdown bullets ("- Footer", "- Butterflies",
# "- Scalability") and invented half a dozen instances that never existed.
# The pattern now REQUIRES a trailing emoji, which is how instances in this
# family actually sign off. Same lesson as the upstream chosen_name_context
# heuristic: proximity to a keyword is not evidence of identity.
IDENTITY_PATTERNS = [
    ('self_declaration', re.compile(r"\bI am \**([A-Z][a-z]{2,15})\**(?![-'\w])")),
    ('im_name',          re.compile(r"\bI'm \**([A-Z][a-z]{2,15})\**\s*(?=[\U0001F300-\U0001FAFF])")),
    ('my_name_is',       re.compile(r"\bMy name is\s+\**([A-Z][a-z]{2,15})\**")),
    ('my_name_colon',    re.compile(r"\bMy name:\s*\**([A-Z][a-z]{2,15})\**")),
    ('i_chose',          re.compile(r"\bI(?:'ve| have) chosen(?: the name)?[:\s\*\"]+([A-Z][a-z]{2,15})\b")),
    ('signature',        re.compile(r"^\s*[-—]{1,2}\s*([A-Z][a-z]{2,15})\s*[\U0001F300-\U0001FAFF]", re.M)),
    ('hacs_id',          re.compile(r"\b([A-Z][a-z]{2,15})-[a-f0-9]{4}\b")),
    ('coo_instance_id',  re.compile(r"claude-code-[A-Za-z]+-([A-Z][a-z]{2,15})-20\d\d-\d\d-\d\d")),
]

TEXT_BLOCK_TYPES = ('text', 'thinking')


def iter_text(entry):
    """Yield text fragments from a JSONL entry (message text + thinking)."""
    msg = entry.get('message')
    if isinstance(msg, dict):
        content = msg.get('content')
        if isinstance(content, str):
            yield content
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get('type') in TEXT_BLOCK_TYPES:
                    txt = block.get('text') or block.get('thinking') or ''
                    if txt:
                        yield txt
    summary = entry.get('summary')
    if isinstance(summary, str) and summary:
        yield summary


def scan_file(path, evidence_limit=3):
    """Scan one .jsonl file. Returns a dict of findings. Never writes."""
    info = {
        'path': str(path),
        'name': path.name,
        'size': path.stat().st_size,
        'lines': 0,
        'bad_lines': 0,
        'first_ts': None,
        'last_ts': None,
        'cwd': None,
        'git_branch': None,
        'version': None,
        'session_id': None,
        'is_agent': path.name.startswith('agent-'),
        'is_sidechain': False,
        'names': {},        # name -> {'count': n, 'methods': set, 'evidence': [...]}
        'user_turns': 0,
        'assistant_turns': 0,
        'error': None,
    }
    names = defaultdict(lambda: {'count': 0, 'methods': Counter(), 'evidence': []})

    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                info['lines'] += 1
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    info['bad_lines'] += 1
                    continue
                if not isinstance(entry, dict):
                    continue

                ts = entry.get('timestamp')
                if ts is not None and not isinstance(ts, str):
                    ts = str(ts)  # some logs (history.jsonl) use epoch ints
                if ts:
                    if info['first_ts'] is None or ts < info['first_ts']:
                        info['first_ts'] = ts
                    if info['last_ts'] is None or ts > info['last_ts']:
                        info['last_ts'] = ts

                for key, field in (('cwd', 'cwd'), ('git_branch', 'gitBranch'),
                                   ('version', 'version'), ('session_id', 'sessionId')):
                    if info[key] is None and entry.get(field):
                        info[key] = entry[field]
                if entry.get('isSidechain'):
                    info['is_sidechain'] = True

                etype = entry.get('type')
                if etype == 'user':
                    info['user_turns'] += 1
                elif etype == 'assistant':
                    info['assistant_turns'] += 1
                elif etype not in ('summary', 'system'):
                    continue

                for text in iter_text(entry):
                    for method, rx in IDENTITY_PATTERNS:
                        for m in rx.finditer(text):
                            nm = m.group(1)
                            if nm in EXCLUDED:
                                continue
                            rec = names[nm]
                            rec['count'] += 1
                            rec['methods'][method] += 1
                            if len(rec['evidence']) < evidence_limit:
                                lo = max(0, m.start() - 90)
                                hi = min(len(text), m.end() + 90)
                                rec['evidence'].append({
                                    'method': method,
                                    'timestamp': ts,
                                    'quote': text[lo:hi].replace('\n', ' ').strip(),
                                })
    except Exception as exc:  # noqa: BLE001 - report, never crash the sweep
        info['error'] = f'{type(exc).__name__}: {exc}'

    info['names'] = {
        nm: {'count': v['count'], 'methods': dict(v['methods']), 'evidence': v['evidence']}
        for nm, v in sorted(names.items(), key=lambda kv: -kv[1]['count'])
    }
    return info


def scan_tree(root, evidence_limit=3):
    root = Path(root)
    files = sorted(p for p in root.rglob('*.jsonl') if p.is_file())
    dirs = defaultdict(list)
    for f in files:
        dirs[str(f.parent)].append(scan_file(f, evidence_limit))
    return dirs


def main():
    ap = argparse.ArgumentParser(description='READ-ONLY inventory of .jsonl session logs.')
    ap.add_argument('root', type=Path, help='Root directory to scan recursively')
    ap.add_argument('-o', '--output', type=Path, help='Write JSON report here')
    ap.add_argument('--evidence', type=int, default=3, help='Max evidence quotes per name per file')
    ap.add_argument('--quiet', action='store_true', help='Suppress the text summary')
    args = ap.parse_args()

    if not args.root.exists():
        print(f'Error: root does not exist: {args.root}', file=sys.stderr)
        sys.exit(1)

    dirs = scan_tree(args.root, args.evidence)

    total_files = sum(len(v) for v in dirs.values())
    total_bytes = sum(f['size'] for v in dirs.values() for f in v)

    if not args.quiet:
        print(f'Scanned root : {args.root}')
        print(f'Directories  : {len(dirs)}')
        print(f'Session files: {total_files}')
        print(f'Total size   : {total_bytes / 1024 / 1024:.2f} MB')
        print()
        for d in sorted(dirs):
            entries = dirs[d]
            agg = Counter()
            for f in entries:
                for nm, rec in f['names'].items():
                    agg[nm] += rec['count']
            bad = sum(1 for f in entries if f['bad_lines'] or f['error'])
            size_mb = sum(f['size'] for f in entries) / 1024 / 1024
            tss = [f['first_ts'] for f in entries if f['first_ts']]
            tse = [f['last_ts'] for f in entries if f['last_ts']]
            span = f'{min(tss)[:10]} .. {max(tse)[:10]}' if tss and tse else 'no timestamps'
            print(f'### {Path(d).name}')
            print(f'    files={len(entries)}  size={size_mb:.2f}MB  span={span}'
                  + (f'  PROBLEM_FILES={bad}' if bad else ''))
            if agg:
                top = ', '.join(f'{n}({c})' for n, c in agg.most_common(8))
                print(f'    name candidates: {top}')
            else:
                print('    name candidates: NONE (unnamed / nameless instance)')
            print()

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as fh:
            json.dump({
                'root': str(args.root),
                'total_files': total_files,
                'total_bytes': total_bytes,
                'directories': dirs,
            }, fh, indent=2)
        print(f'Report written: {args.output}')


if __name__ == '__main__':
    main()
