#!/usr/bin/env python3
"""verbatim_check.py -- are the quotes in a curation byte-faithful to the source?

Prints COUNTS ONLY. It never prints a quote, so the person running it (the
curator's principal) can verify a gestalt without reading a dormant mind's words.
A failing quote is reported as file:line and length, nothing else.

    python verbatim_check.py --source NARRATIVE.md [--source CONVERSATIONS.md] FILE_OR_DIR...

What counts as a quote:
  * every markdown blockquote block ('> ...' lines, joined), and
  * every "double-quoted" run of >= MIN_INLINE chars outside a blockquote.
A quote may be elided with [...] or ... ; each fragment of >= MIN_FRAG chars must
appear in the source. Shorter fragments are not counted either way.

Normalisation is applied to quote AND source alike: smart quotes -> straight,
double quotes == single quotes (curators legitimately swap
nested quote marks), markdown emphasis (* and leading/trailing _) dropped, whitespace collapsed, a
leading speaker tag like **[Lupo]:** or [Atlas] removed. Nothing else -- in
particular case and punctuation must match.

Exit: 0 all verbatim · 1 at least one quote not found · 2 usage/error.

Author: Lodestone <lodestone@smoothcurves.nexus> / Collaborator: Lupo
"""
import argparse
import os
import re
import sys

MIN_INLINE = 25
MIN_FRAG = 15

SMART = {"“": '"', "”": '"', "‘": "'", "’": "'",
         "—": "--", "–": "-", " ": " "}
SPEAKER = re.compile(r'^\s*(\*\*)?\[?[A-Za-z][\w .-]{0,40}\]?(\*\*)?\s*:\s*(\*\*)?\s*')
TAG = re.compile(r'^\s*\[[^\]]{1,40}\]\s*:?\s*')
ELIDE = re.compile(r'\[\s*(\.\.\.|…)\s*\]|\.\.\.|…')


def norm(s):
    for k, v in SMART.items():
        s = s.replace(k, v)
    s = s.replace('"', "'")         # nested-quote style swaps are allowed, nothing else
    s = s.replace("*", "")
    s = re.sub(r'(?<!\w)_|_(?!\w)', '', s)
    s = s.replace("\\", "")          # markdown escapes; applied to both sides
    return re.sub(r'\s+', ' ', s).strip()


def quotes_in(path):
    """Yield (line_no, text) for every quote in one markdown file."""
    with open(path, encoding='utf-8', errors='replace') as f:
        lines = f.read().splitlines()
    block, start = [], None
    for i, line in enumerate(lines + [''], 1):
        if line.lstrip().startswith('>'):
            body = re.sub(r'^\s*>\s?', '', line)
            if not body.strip():            # a blank '>' line ends a paragraph:
                if block:                   # each paragraph is its own quote, since
                    yield start, '\n'.join(block)   # the source never joins them
                block, start = [], None
                continue
            if start is None:
                start = i
            block.append(body)
            continue
        if block:
            yield start, '\n'.join(block)
            block, start = [], None
        if i <= len(lines):
            # find inline quotes BEFORE norm(), which folds " into ' and would hide them
            raw = line.replace("“", '"').replace("”", '"')
            for m in re.finditer(r'"([^"\n]{%d,})"' % MIN_INLINE, raw):
                yield i, m.group(1)


def fragments(q):
    q = q.strip()
    q = TAG.sub('', q, count=1)
    q = SPEAKER.sub('', q, count=1) if len(q) > 60 else q
    q = norm(q).strip("'").strip()
    return [f.strip(" '") for f in ELIDE.split(q) if f and len(f.strip(" '")) >= MIN_FRAG]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', action='append', required=True)
    ap.add_argument('targets', nargs='+')
    a = ap.parse_args()
    try:
        hay = '\n'.join(norm(open(s, encoding='utf-8', errors='replace').read()) for s in a.source)
    except OSError as e:
        print(f'ERROR reading source: {e}', file=sys.stderr)
        return 2
    files = []
    for t in a.targets:
        if os.path.isdir(t):
            for root, _, names in os.walk(t):
                files += [os.path.join(root, n) for n in sorted(names) if n.endswith('.md')]
        elif os.path.isfile(t):
            files.append(t)
        else:
            print(f'ERROR: no such target {t}', file=sys.stderr)
            return 2
    if not files:
        print('ERROR: no .md files found -- refusing to report "all verbatim" over nothing', file=sys.stderr)
        return 2
    tq = tv = tbad = tskip = 0
    for p in files:
        q = v = skip = 0
        bad = []
        for ln, text in quotes_in(p):
            frags = fragments(text)
            if not frags:
                skip += 1
                continue
            q += 1
            # the only other liberty allowed: a quote may capitalise its first letter
            if all(f in hay or (f[:1].lower() + f[1:]) in hay for f in frags):
                v += 1
            else:
                bad.append((ln, len(text)))
        tq += q; tv += v; tbad += len(bad); tskip += skip
        print(f'{os.path.basename(p)}: quotes {q}, verbatim {v}, not-found {len(bad)}, too-short {skip}')
        for ln, n in bad:
            print(f'    NOT FOUND  {os.path.basename(p)}:{ln}  ({n} chars)')
    print(f'TOTAL files {len(files)}: quotes {tq}, verbatim {tv}, not-found {tbad}, too-short {tskip}')
    return 0 if tbad == 0 and tq > 0 else 1


if __name__ == '__main__':
    sys.exit(main())
