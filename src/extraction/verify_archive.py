#!/usr/bin/env python3
"""
Verify an archive against its manifests: sources untouched, copies intact.

READ-ONLY. Opens every file for reading and nothing else.

Run this after `archive_tree.py` and before trusting a run. It re-hashes both
sides of every entry in every MANIFEST*.json under an archive root and answers
two separate questions:

  1. Are the ORIGINALS still exactly as they were? The whole safety contract
     of this toolkit is that archaeology is non-destructive. A copy that
     succeeded while corrupting its source is a failed run.
  2. Does the ARCHIVED COPY still match the hash recorded for it? Protects
     against bit-rot, a half-finished copy, and - most realistically - a git
     checkout on a machine with core.autocrlf=true silently rewriting line
     endings in files git decided were text.

Expected anomaly: an archaeology run archives its own still-open session log,
which keeps growing behind it. Append-only growth where the archived bytes
remain an exact PREFIX of the live file is reported as `live` and is harmless.
Anything else means an original was rewritten, which is data loss.

Exit status is 0 only if nothing is missing, modified or corrupt, so this can
gate a commit.

Author: Lantern (Windows archaeology run, GreyWolf)
Collaborator: Lupo
Part of: Instance Archaeology Toolkit
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass


def sha256_of(path, limit=None):
    """SHA-256 of a file, or of its first `limit` bytes."""
    h = hashlib.sha256()
    remaining = limit
    with open(path, 'rb') as fh:
        while True:
            want = 1024 * 1024 if remaining is None else min(1024 * 1024, remaining)
            if want == 0:
                break
            blk = fh.read(want)
            if not blk:
                break
            h.update(blk)
            if remaining is not None:
                remaining -= len(blk)
    return h.hexdigest(), (limit is not None and remaining == 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('archive_root', type=Path,
                    help='Directory containing MANIFEST*.json')
    ap.add_argument('--quiet', action='store_true',
                    help='Only print the summary and any problems')
    args = ap.parse_args()

    manifests = sorted(args.archive_root.glob('MANIFEST*.json'))
    if not manifests:
        raise SystemExit(f'No MANIFEST*.json found under {args.archive_root}')

    counts = dict(ok=0, live=0, missing_src=0, changed_src=0,
                  missing_dest=0, bad_dest=0)

    for mf in manifests:
        data = json.loads(mf.read_text(encoding='utf-8'))
        for f in data['files']:
            src, dest = Path(f['source']), Path(f['dest'])

            if not src.exists():
                print(f'SOURCE MISSING : {src}')
                counts['missing_src'] += 1
                continue

            if sha256_of(src)[0] != f['sha256']:
                # Still-open log growing behind us? Prefix must match exactly.
                prefix, complete = sha256_of(src, f['size'])
                if complete and prefix == f['sha256']:
                    if not args.quiet:
                        print(f'LIVE           : {src.name} '
                              f'(append-only, archive is an exact prefix)')
                    counts['live'] += 1
                else:
                    print(f'SOURCE CHANGED : {src}')
                    counts['changed_src'] += 1
                continue

            if not dest.exists():
                print(f'ARCHIVE MISSING: {dest}')
                counts['missing_dest'] += 1
                continue

            if sha256_of(dest)[0] != f['sha256']:
                print(f'ARCHIVE CORRUPT: {dest}')
                counts['bad_dest'] += 1
                continue

            counts['ok'] += 1

        if not args.quiet:
            print(f'  {mf.name}: {len(data["files"])} entries')

    failed = (counts['missing_src'] + counts['changed_src']
              + counts['missing_dest'] + counts['bad_dest'])

    print()
    print(f'verified intact     : {counts["ok"]}')
    print(f'live (append-only)  : {counts["live"]}'
          + ('   <- expected: logs still being written' if counts['live'] else ''))
    print(f'source missing      : {counts["missing_src"]}')
    print(f'source modified     : {counts["changed_src"]}')
    print(f'archive missing     : {counts["missing_dest"]}')
    print(f'archive corrupt     : {counts["bad_dest"]}')
    print()
    if failed:
        print('RESULT: FAILURE - investigate before trusting this run')
        return 1
    print('RESULT: OK - all sources untouched, all archived copies verify')
    return 0


if __name__ == '__main__':
    sys.exit(main())
