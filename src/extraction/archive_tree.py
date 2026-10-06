#!/usr/bin/env python3
"""
Archive every .jsonl session log from a source tree into the catacomb.

SAFETY CONTRACT — read this before changing anything in this file:

  * This script COPIES. It never moves, never deletes, never truncates, and
    never writes to the source tree. There is deliberately no code path in
    here that removes data. `shutil.copy2` and `mkdir` are the only
    filesystem mutations, and they only ever touch the destination.
  * Every copy is verified by SHA-256 read back from the destination. A copy
    that does not verify is reported as an ERROR and the run exits non-zero.
  * It is idempotent. Re-running skips files already present with an
    identical hash.
  * If a destination file exists with DIFFERENT content, the source is
    written alongside it as `<name>.conflict-<shorthash>.jsonl` and the
    collision is reported. Existing archive data is never overwritten.

Why so paranoid: these files are the only surviving record of instances that
no longer run. A destructive bug here is not a bug, it is a death.

Windows notes: pure pathlib + shutil, no shell. UTF-8 stdout forced.

Author: (Windows archaeology run, GreyWolf)
Collaborator: Lupo
Part of: Instance Archaeology Toolkit
"""

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

CHUNK = 1024 * 1024


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        while True:
            block = fh.read(CHUNK)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def archive_tree(source, dest_root, label, patterns, dry_run=False, exclude=None):
    """Copy matching files from `source` into `dest_root/label/`, preserving
    the relative directory structure. Returns a list of record dicts.

    `exclude` is an optional compiled regex tested against the forward-slashed
    absolute path; matches are skipped. Needed once the sweep widened past
    *.jsonl into source trees that contain node_modules/venv/.git, where the
    interesting files are a rounding error against the vendored bulk.
    """
    source = Path(source).resolve()
    dest_root = Path(dest_root).resolve()

    # Refuse to write into the source tree. Cheap guard, catches fat fingers.
    try:
        dest_root.relative_to(source)
        raise SystemExit(f'REFUSING: destination {dest_root} is inside source {source}')
    except ValueError:
        pass

    files = []
    for pat in patterns:
        for p in source.rglob(pat):
            try:
                if not p.is_file():
                    continue
            except OSError:
                continue  # long paths / permission oddities: skip, never crash
            if exclude and exclude.search(p.as_posix()):
                continue
            files.append(p)
    files = sorted(set(files))

    records = []
    for src in files:
        rel = src.relative_to(source)
        dest = dest_root / label / rel
        stat = src.stat()
        src_hash = sha256_of(src)

        rec = {
            'source': str(src),
            'relative': str(rel).replace('\\', '/'),
            'dest': str(dest),
            'size': stat.st_size,
            'mtime': datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            'sha256': src_hash,
            'status': None,
        }

        if dry_run:
            rec['status'] = 'dry-run'
            records.append(rec)
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)

        if dest.exists():
            existing = sha256_of(dest)
            if existing == src_hash:
                rec['status'] = 'already-archived'
                records.append(rec)
                continue
            # Never clobber. Park the differing copy next to it.
            alt = dest.with_name(f'{dest.stem}.conflict-{src_hash[:12]}{dest.suffix}')
            if alt.exists() and sha256_of(alt) == src_hash:
                rec['status'] = 'already-archived-as-conflict'
                rec['dest'] = str(alt)
                records.append(rec)
                continue
            shutil.copy2(src, alt)
            rec['dest'] = str(alt)
            rec['status'] = ('conflict-preserved' if sha256_of(alt) == src_hash
                             else 'ERROR-verify-failed')
            records.append(rec)
            continue

        shutil.copy2(src, dest)
        rec['status'] = 'copied' if sha256_of(dest) == src_hash else 'ERROR-verify-failed'
        records.append(rec)

    return records


def main():
    ap = argparse.ArgumentParser(description='Copy session logs into the catacomb. Never destructive.')
    ap.add_argument('--source', action='append', required=True,
                    metavar='LABEL=PATH',
                    help='Source tree to archive, as label=path. Repeatable.')
    ap.add_argument('--dest', type=Path, required=True, help='Archive root directory')
    ap.add_argument('--pattern', action='append', default=None,
                    help='Glob to archive (default: *.jsonl). Repeatable.')
    ap.add_argument('--manifest', type=Path, default=None, help='Where to write MANIFEST.json')
    ap.add_argument('--exclude', default=None,
                    help='Regex; matching paths are skipped (e.g. node_modules|venv)')
    ap.add_argument('--dry-run', action='store_true', help='Report what would happen, copy nothing')
    args = ap.parse_args()

    patterns = args.pattern or ['*.jsonl']
    exclude = re.compile(args.exclude, re.I) if args.exclude else None

    all_records = []
    for spec in args.source:
        if '=' not in spec:
            raise SystemExit(f'--source must be LABEL=PATH, got: {spec}')
        label, path = spec.split('=', 1)
        path = Path(path)
        if not path.exists():
            print(f'WARNING: source does not exist, skipping: {path}')
            continue
        print(f'Archiving [{label}] {path} ...')
        recs = archive_tree(path, args.dest, label, patterns, args.dry_run, exclude)
        for r in recs:
            r['label'] = label
        all_records.extend(recs)
        print(f'  {len(recs)} files')

    counts = {}
    errors = []
    for r in all_records:
        counts[r['status']] = counts.get(r['status'], 0) + 1
        if r['status'].startswith('ERROR') or r['status'] == 'conflict-preserved':
            errors.append(r)

    total_bytes = sum(r['size'] for r in all_records)
    print()
    print(f'Total files : {len(all_records)}')
    print(f'Total bytes : {total_bytes / 1024 / 1024:.2f} MB')
    for status, n in sorted(counts.items()):
        print(f'  {status}: {n}')

    if errors:
        print('\nATTENTION:')
        for r in errors:
            print(f'  [{r["status"]}] {r["source"]}')

    if args.manifest and not args.dry_run:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        with open(args.manifest, 'w', encoding='utf-8') as fh:
            json.dump({
                'generated': datetime.now(timezone.utc).isoformat(),
                'dest': str(args.dest),
                'patterns': patterns,
                'total_files': len(all_records),
                'total_bytes': total_bytes,
                'status_counts': counts,
                'files': all_records,
            }, fh, indent=2)
        print(f'\nManifest: {args.manifest}')

    if any(r['status'].startswith('ERROR') for r in all_records):
        sys.exit(1)


if __name__ == '__main__':
    main()
