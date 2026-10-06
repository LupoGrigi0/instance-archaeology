#!/usr/bin/env python3
"""
Show the evidence quotes behind name candidates from scan_tree.py output.

READ-ONLY. Exists because name-detection heuristics are unreliable: a
capitalized word near "chosen" (or a markdown bullet) is not proof of identity.
Every proposed instance name must be confirmed against real quoted context
before an archive is labelled with it.

Usage:
  python show_evidence.py report.json                 # all candidates
  python show_evidence.py report.json --name Atlas    # one candidate
  python show_evidence.py report.json --dir Backup    # one directory
  python show_evidence.py report.json --min-count 5   # only frequent ones
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Windows: default console encoding is cp1252 and dies on emoji, which appear
# constantly in these logs. Force UTF-8 with replacement rather than crashing.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('report', type=Path)
    ap.add_argument('--name', help='Only show this candidate name')
    ap.add_argument('--dir', help='Only show directories whose name contains this')
    ap.add_argument('--min-count', type=int, default=1)
    ap.add_argument('--max-quotes', type=int, default=4)
    args = ap.parse_args()

    data = json.loads(args.report.read_text(encoding='utf-8'))

    for dpath, files in sorted(data['directories'].items()):
        dname = Path(dpath).name
        if args.dir and args.dir.lower() not in dname.lower():
            continue

        totals = Counter()
        methods = defaultdict(Counter)
        quotes = defaultdict(list)
        seen_in = defaultdict(set)

        for f in files:
            for nm, rec in f['names'].items():
                totals[nm] += rec['count']
                for meth, c in rec['methods'].items():
                    methods[nm][meth] += c
                seen_in[nm].add(f['name'])
                quotes[nm].extend(rec['evidence'])

        shown = [(n, c) for n, c in totals.most_common()
                 if c >= args.min_count and (not args.name or n == args.name)]
        if not shown:
            continue

        print('=' * 78)
        print(f'DIRECTORY: {dname}   ({len(files)} session files)')
        print('=' * 78)
        for nm, c in shown:
            print(f'\n  CANDIDATE: {nm}   hits={c}  files={len(seen_in[nm])}')
            print(f'    methods: {dict(methods[nm])}')
            for ev in quotes[nm][:args.max_quotes]:
                ts = (ev.get('timestamp') or '')[:19]
                print(f'    [{ev["method"]}] {ts}')
                print(f'      "{ev["quote"][:230]}"')
        print()


if __name__ == '__main__':
    main()
