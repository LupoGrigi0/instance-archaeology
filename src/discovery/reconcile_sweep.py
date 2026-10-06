#!/usr/bin/env python3
"""Reconcile the whole-machine sweep against what was actually archived.

Answers the question I answered too confidently the first time: of every
.jsonl on this machine, which ones are NOT accounted for by the GreyWolf
archive, and are any of them an instance's record nobody has rescued?
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

SCAN = Path('D:/Lupo/Source/AI/instance-archaeology/_scan')
CAT = 'd:/lupo/source/ai/stasis-catacomb'

logs, docs = [], []
for f in sorted(SCAN.glob('sweep_*.json')):
    d = json.loads(f.read_text(encoding='utf-8'))
    logs += d['logs']
    docs += d['docs']

# Everything the GreyWolf run copied, by source and by destination.
known = set()
for mf in Path(CAT.replace('d:', 'D:') + '/GreyWolf-2026-08-30').glob('MANIFEST*.json'):
    m = json.loads(mf.read_text(encoding='utf-8'))
    for e in m['files']:
        known.add(e['source'].replace('\\', '/').lower())
        known.add(e['dest'].replace('\\', '/').lower())

print(f'.jsonl found on machine : {len(logs):,}')
print(f'identity docs found     : {len(docs):,}')
print(f'archived by GreyWolf run: {len(known)//2:,} files (source+dest tracked)')
print()

unaccounted = [L for L in logs if L['path'].lower() not in known]
print(f'.jsonl NOT in the GreyWolf manifests: {len(unaccounted):,}')
print()

# Where do they live? Classify by purpose so the real gaps stand out.
def bucket(p):
    q = p.lower()
    if CAT in q:
        return 'pre-existing catacomb (already preserved archaeology)'
    if '/.claude/projects/' in q or '/dot_claude/' in q or 'lupog_dot_claude' in q:
        return 'a .claude projects dir'
    if '/node_modules/' in q or '/site-packages/' in q or '/venv/' in q:
        return 'vendored dependency (not a transcript)'
    if re.search(r'/(test|tests|fixtures?|sample|example|spec)/', q):
        return 'test fixture / sample data'
    return 'OTHER - needs eyes'

b = Counter(bucket(L['path']) for L in unaccounted)
for k, n in b.most_common():
    sz = sum(L['size'] for L in unaccounted if bucket(L['path']) == k)
    print(f'  {n:>4} files  {sz/1024/1024:>9.1f} MB  {k}')

other = [L for L in unaccounted if bucket(L['path']) == 'OTHER - needs eyes']
if other:
    print()
    print('OTHER, largest first:')
    for L in sorted(other, key=lambda x: -x['size'])[:40]:
        print(f'  {L["size"]/1024:>10.0f} KB  {L["path"]}')

out = SCAN / 'unaccounted_logs.json'
out.write_text(json.dumps({'unaccounted': unaccounted, 'other': other,
                           'all_docs': docs}, indent=1), encoding='utf-8')
print()
print(f'written: {out}')
