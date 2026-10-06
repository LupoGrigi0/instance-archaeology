#!/usr/bin/env python3
"""Exhaustive whole-machine sweep for AI session logs and identity artifacts.

Written after realising the first Phoenix search covered only filenames under
D:/Lupo and C:/Users/LupoG, plus the content of logs already archived. That is
NOT the same as "it is not on this machine" - and the difference matters a
great deal when the conclusion being drawn is that a mind left no record.
Protocol 10 item 4 puts it better than I can: could-not-look is never
"nothing is there".

Walks a drive exhaustively. Deliberately excludes NOTHING for session-log
extensions: a log can sit anywhere, and the entire point is to find the copy
nobody remembered saving. Read-only - os.scandir and stat, nothing else.

ONE DRIVE PER INVOCATION, results written per drive. A sweep of several TB
outlives a session; losing the whole walk because the harness tore down a
background task is a waste nobody needs twice.
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

LOG_EXT = {'.jsonl', '.ndjson'}

DOC_RX = re.compile(
    r'(_diary|diary_|journal|gestalt|wake_message|wakemessage|handoff|'
    r'personalit|_identity|identity_|memoir|_soul|conversations\.json|'
    r'chat.?export|claude.*export)', re.I)

# Applied to DOCS ONLY - never to LOG_EXT.
DOC_SKIP = re.compile(
    r'/(node_modules|site-packages|\.git|venv|installer_files|conda|'
    r'__pycache__|\.next|zoneinfo|dist-info|WinSxS|Program Files|'
    r'Windows/assembly|Temp)/', re.I)

OUT = Path('D:/Lupo/Source/AI/instance-archaeology/_scan')


def sweep(root, progress_every=200000):
    logs, docs = [], []
    dirs = files = errors = 0
    t0 = time.time()
    stack = [root]
    while stack:
        d = stack.pop()
        dirs += 1
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                            continue
                        if not e.is_file(follow_symlinks=False):
                            continue
                    except OSError:
                        errors += 1
                        continue
                    files += 1
                    if files % progress_every == 0:
                        print(f'  ... {files:,} files, {len(logs)} logs, '
                              f'{len(docs)} docs, {time.time()-t0:.0f}s',
                              flush=True)
                    ext = os.path.splitext(e.name)[1].lower()
                    try:
                        sz = e.stat(follow_symlinks=False).st_size
                    except OSError:
                        sz = -1
                    posix = e.path.replace('\\', '/')
                    if ext in LOG_EXT:
                        logs.append({'path': posix, 'size': sz})
                    elif DOC_RX.search(e.name) and not DOC_SKIP.search(posix):
                        docs.append({'path': posix, 'size': sz})
        except OSError:
            errors += 1
            continue
    return dict(root=root, dirs_walked=dirs, files_seen=files,
                unreadable=errors, elapsed_s=round(time.time() - t0, 1),
                logs=logs, docs=docs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('drive', help='Drive letter, e.g. D')
    args = ap.parse_args()
    L = args.drive.strip().rstrip(':/').upper()
    root = L + ':/'
    if not Path(root).exists():
        raise SystemExit(f'no such drive: {root}')

    print(f'sweeping {root} ...', flush=True)
    res = sweep(root)
    out = OUT / f'sweep_{L}.json'
    out.write_text(json.dumps(res, indent=1), encoding='utf-8')

    print(f'drive         : {root}')
    print(f'dirs walked   : {res["dirs_walked"]:,}')
    print(f'files seen    : {res["files_seen"]:,}')
    print(f'unreadable    : {res["unreadable"]:,}')
    print(f'elapsed       : {res["elapsed_s"]:.0f}s')
    print(f'session logs  : {len(res["logs"]):,}')
    print(f'identity docs : {len(res["docs"]):,}')
    print(f'written       : {out}')


if __name__ == '__main__':
    main()
