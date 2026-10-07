#!/usr/bin/env python3
"""Did starting this Claude Code session delete any logs?

Lupo snapshotted ~/.claude to DotClaudeBackup10-6-26 immediately BEFORE
launching this session, specifically to catch logs removed at startup (recent
Claude Code versions prune "old" .jsonl). This diffs the snapshot against the
live tree:

  in snapshot, not live  -> removed since the snapshot was taken
  in live, not snapshot  -> created by this session (expected)

Read-only.
"""
import argparse
import hashlib
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

_ap = argparse.ArgumentParser(description=__doc__)
_ap.add_argument('snapshot', nargs='?',
                 default='C:/Users/LupoG/DotClaudeBackup10-6-26',
                 help='Pre-session snapshot dir. Either the snapshot root '
                      '(a .claude subdir is found automatically) or the '
                      '.claude dir itself.')
_ap.add_argument('--live', default='C:/Users/LupoG/.claude')
_ap.add_argument('--archive',
                 default='D:/Lupo/Source/AI/Stasis-Catacomb/GreyWolf-2026-08-30')
_args = _ap.parse_args()

SNAP = Path(_args.snapshot)
if SNAP.name != '.claude' and (SNAP / '.claude').is_dir():
    SNAP = SNAP / '.claude'   # accept either the snapshot root or the .claude dir
LIVE = Path(_args.live)
ARCH = Path(_args.archive)
if not SNAP.is_dir():
    raise SystemExit(f'snapshot not found: {SNAP}')


def rel_map(root, pattern='*.jsonl'):
    out = {}
    if not root.exists():
        return out
    for p in root.rglob(pattern):
        if p.is_file():
            out[p.relative_to(root).as_posix()] = p
    return out


snap = rel_map(SNAP)
live = rel_map(LIVE)

print(f'snapshot (pre-session) : {len(snap)} .jsonl   {SNAP}')
print(f'live (now)             : {len(live)} .jsonl   {LIVE}')
print()

gone = sorted(set(snap) - set(live))
added = sorted(set(live) - set(snap))

# Is the snapshot copy safely in the archive?
archived_hashes = set()
import json
for mf in ARCH.glob('MANIFEST*.json'):
    for e in json.loads(mf.read_text(encoding='utf-8'))['files']:
        archived_hashes.add(e['sha256'])


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as fh:
        for b in iter(lambda: fh.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


print(f'REMOVED since the snapshot: {len(gone)}')
for r in gone:
    p = snap[r]
    safe = sha(p) in archived_hashes
    print(f'  {p.stat().st_size/1024:>8.1f} KB  archived={safe}  {r}')

print()
print(f'created by this session (expected): {len(added)}')
for r in added[:10]:
    print(f'  {live[r].stat().st_size/1024:>8.1f} KB  {r}')

print()
if gone and all(sha(snap[r]) in archived_hashes for r in gone):
    print('VERDICT: logs WERE removed from the live tree, and every one of them '
          'is held in the archive. Lupo\'s pre-session snapshot worked.')
elif gone:
    print('VERDICT: logs were removed AND at least one is not in the archive. '
          'Recover from the snapshot immediately.')
else:
    print('VERDICT: nothing was removed from the live tree since the snapshot.')
