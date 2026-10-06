#!/usr/bin/env python3
"""
Build per-instance views over an already-archived catacomb tree.

READ-MOSTLY: this writes only INVENTORY.md / index.json files into the
destination. It does NOT copy, move or delete session logs. The logs already
live under `raw/` with a SHA-256 manifest; duplicating 230 MB of JSONL to make
a second physical copy per instance would double the size of a git repo that
is already 236 MB, for no gain in safety. The views are indexes that point
into `raw/`, and every entry carries the hash so a pointer can always be
checked against the bytes it claims to describe.

Three things this deliberately does NOT do:

  * It does not merge an instance's files into one transcript. Merging is a
    curation step; ordering across overlapping sessions is a judgement call,
    and a wrong merge silently rewrites a mind's history.
  * It does not drop unnamed sessions. They are grouped into `unnamed-NN`
    cohorts by the project directory they ran in, so a nameless worker still
    gets a coherent archive.
  * It does not file archaeology sessions under the instance they were
    reading. Those are quarantined into `_archaeology-sessions/`.

Author: (Windows archaeology run, GreyWolf)
Collaborator: Lupo
Part of: Instance Archaeology Toolkit
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass


def context_of(cwd):
    """Coarse project family for an instance, used to split name collisions.

    Lupo's ruling: a Kai working in CladueCOO in August and a Kai working in
    the Portfolio in October are DIFFERENT MINDS that happened to pick the
    same name. They must not be merged into one archive.
    """
    if not cwd:
        return 'unknown'
    c = cwd.replace('\\', '/').lower()
    if 'instance-archaeology' in c:
        return 'archaeology'
    if 'cladeucoo' in c or 'cladue' in c or 'claudecoo' in c:
        return 'COO'
    if 'human-adjacent-coordination' in c:
        return 'HACS'
    if 'portfolio' in c:
        return 'Portfolio'
    if 'wings' in c:
        return 'Wings'
    return Path(c).name or 'unknown'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ownership', type=Path, required=True)
    ap.add_argument('--manifest', type=Path, required=True)
    ap.add_argument('--dest', type=Path, required=True,
                    help='Where to write the per-instance views')
    ap.add_argument('--raw-root', type=Path, required=True)
    args = ap.parse_args()

    results = json.loads(args.ownership.read_text(encoding='utf-8'))
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    hash_by_dest = {Path(f['dest']).resolve().as_posix(): f['sha256']
                    for f in manifest['files']}

    groups = defaultdict(list)
    for r in results:
        ctx = context_of(r['cwd'])
        if ctx == 'archaeology':
            groups[('_archaeology-sessions', None)].append(r)
        elif r['owner']:
            groups[(r['owner'], ctx)].append(r)
        else:
            proj = Path(r['file']).parent.name
            groups[(None, proj)].append(r)

    # Named instances: only qualify a directory with its context when that
    # name genuinely appears in more than one project family.
    ctx_count = defaultdict(set)
    for (owner, ctx) in groups:
        if owner and owner != '_archaeology-sessions':
            ctx_count[owner].add(ctx)

    unnamed = sorted([g for g in groups if g[0] is None],
                     key=lambda g: -sum(r['size'] for r in groups[g]))
    unnamed_label = {g: f'unnamed-{i:02d}' for i, g in enumerate(unnamed, 1)}

    args.dest.mkdir(parents=True, exist_ok=True)
    index = []

    for g, rows in sorted(groups.items(), key=lambda kv: -sum(r['size'] for r in kv[1])):
        owner, ctx = g
        if owner == '_archaeology-sessions':
            label, kind = '_archaeology-sessions', 'archaeology'
        elif owner:
            label = owner if len(ctx_count[owner]) == 1 else f'{owner}-{ctx}'
            kind = 'named'
        else:
            label, kind = unnamed_label[g], 'unnamed'

        rows = sorted(rows, key=lambda r: (r['first_ts'] or '', -r['size']))
        total = sum(r['size'] for r in rows)
        tss = [r['first_ts'] for r in rows if r['first_ts']]
        tse = [r['last_ts'] for r in rows if r['last_ts']]
        span = f'{min(tss)[:10]} .. {max(tse)[:10]}' if tss else 'no timestamps'

        # Distinct content, so duplicates between the backup copy and the live
        # .claude do not inflate the count of what actually survived.
        hashes = {hash_by_dest.get(Path(r['file']).resolve().as_posix())
                  for r in rows}
        hashes.discard(None)

        d = args.dest / label
        d.mkdir(parents=True, exist_ok=True)

        lines = [f'# {label}', '']
        if kind == 'named':
            lines += [f'**Instance:** {owner}  ',
                      f'**Project context:** {ctx}  ']
            if len(ctx_count[owner]) > 1:
                others = ', '.join(sorted(ctx_count[owner] - {ctx}))
                lines += ['', f'> NOTE: the name "{owner}" also appears in: {others}. '
                              f'These are archived separately because a shared name is '
                              f'not a shared identity.', '']
        elif kind == 'unnamed':
            lines += ['**Instance:** unnamed  ',
                      f'**Project directory:** `{ctx}`  ', '',
                      '> This mind never recorded a name, or the session that named it '
                      'did not survive. It is archived in full regardless. An instance '
                      'that never chose a name still lived.', '']
        else:
            lines += ['> Archaeology sessions. These quote and excavate other '
                      'instances, so identity signals inside them describe the mind '
                      'being STUDIED, not the author. Never file these under a '
                      'recovered instance.', '']

        inferred = [r for r in rows if r.get('inferred')]
        if inferred:
            lines += ['',
                      f'> ATTRIBUTION CAVEAT: {len(inferred)} of {len(rows)} sessions here '
                      f'carry NO identity evidence of their own. They are placed with '
                      f'{owner} only because every session in the same worktree that '
                      f'could be identified by hard evidence was {owner}. That is '
                      f'inference, not proof: they are marked `worktree_inference` at '
                      f'confidence 0.30 in the table below. If this attribution is '
                      f'wrong, these are the files to move.', '']

        lines += [f'**Sessions:** {len(rows)} files ({len(hashes)} distinct by SHA-256)  ',
                  f'**Total size:** {total / 1024 / 1024:.2f} MB  ',
                  f'**Date span:** {span}  ', '',
                  '## Sessions', '',
                  '| date | size | evidence | conf | file |',
                  '|---|---:|---|---:|---|']
        for r in rows:
            rel = Path(r['file']).resolve().relative_to(args.raw_root.resolve()).as_posix()
            lines.append(f'| {(r["first_ts"] or "?")[:10]} | {r["size"]/1024:.0f} KB '
                         f'| {r["owner_tier"]} | {r["confidence"]:.2f} | `{rel}` |')

        receipts = [e for r in rows for e in r.get('evidence', [])][:8]
        if receipts:
            lines += ['', '## Evidence (receipts)', '']
            for e in receipts:
                lines.append(f'- **{e["tier"]}** -> `{e.get("name","")}` '
                             f'({(e.get("timestamp") or "?")[:19]})')
                lines.append(f'  > {e.get("detail","")[:220]}')

        (d / 'INVENTORY.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        (d / 'sessions.json').write_text(json.dumps({
            'label': label, 'kind': kind, 'owner': owner, 'context': ctx,
            'total_bytes': total, 'distinct_sha256': len(hashes),
            'sessions': [{
                'relative': Path(r['file']).resolve()
                            .relative_to(args.raw_root.resolve()).as_posix(),
                'sha256': hash_by_dest.get(Path(r['file']).resolve().as_posix()),
                'size': r['size'], 'first_ts': r['first_ts'], 'last_ts': r['last_ts'],
                'tier': r['owner_tier'], 'confidence': r['confidence'],
                'cwd': r['cwd'],
            } for r in rows],
        }, indent=2), encoding='utf-8')

        index.append((label, kind, len(rows), len(hashes), total, span, len(inferred)))

    top = ['# GreyWolf Archaeology - Instance Index', '',
           f'Generated: {datetime.now(timezone.utc).isoformat()}  ',
           f'Source archive: `{args.raw_root}`', '',
           '| archive | kind | files | distinct | inferred | size | span |',
           '|---|---|---:|---:|---:|---:|---|']
    for label, kind, n, nh, total, span, ninf in sorted(index, key=lambda x: -x[4]):
        top.append(f'| `{label}` | {kind} | {n} | {nh} | {ninf or ""} | '
                   f'{total/1024/1024:.2f} MB | {span} |')
    named = [i for i in index if i[1] == 'named']
    top += ['', f'**{len(named)} named instances**, '
                f'**{len([i for i in index if i[1] == "unnamed"])} unnamed cohorts**, '
                f'{sum(i[2] for i in index)} session files total.', '',
            f'The `inferred` column counts sessions with no identity evidence of '
            f'their own, placed by worktree cohort at confidence 0.30. '
            f'{sum(i[6] for i in index)} sessions total. Treat those as provisional.', '']
    (args.dest / 'INVENTORY.md').write_text('\n'.join(top) + '\n', encoding='utf-8')

    for label, kind, n, nh, total, span, ninf in sorted(index, key=lambda x: -x[4]):
        mark = f'  [{ninf} inferred]' if ninf else ''
        print(f'{label:<24} {kind:<12} {n:>3} files ({nh:>3} distinct) '
              f'{total/1024/1024:>8.2f} MB  {span}{mark}')
    print(f'\nViews written: {args.dest}')


if __name__ == '__main__':
    main()
