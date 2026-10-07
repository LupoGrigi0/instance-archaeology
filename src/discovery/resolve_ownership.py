#!/usr/bin/env python3
"""
Resolve which instance owns each .jsonl session file.

READ-ONLY.

Ranked evidence, strongest first:

  1. DIARY AUTHORSHIP  - the session issues a Write/Edit/NotebookEdit against
     `<Name>_Diary.md`. Instances in this family keep a personal diary; they
     read each other's freely but they only ever write their own. This is the
     single most reliable signal available and it does not depend on the
     instance having said anything about itself.
  2. INSTANCE ID       - `claude-code-<ROLE>-<Name>-<date>` self-identifiers.
  3. SELF DECLARATION  - "I am X", "I've chosen the name X", "My name is X".
  4. ROLE INTRO        - "I'm Kai v3 (Carousel & Animation Specialist)". This is
     how identity SURVIVES COMPACTION and is often the only place a name still
     appears in a long-running worker's later sessions.
  5. DIARY READS       - the session merely reads `<Name>_Diary.md`. Weak:
     evidence of association, NOT of identity. Reported, never decisive alone.

THE ROSTER GATE
---------------
Weak patterns ("I'm X") cannot be trusted on their own: they cheerfully match
"I'm proud", "I'm seeing", "I'm excited" and would invent instances that never
existed. Rather than fight that with an ever-growing blocklist, resolution runs
in TWO PASSES:

  pass 1 - read every file, collect evidence, decide nothing.
  pass 2 - build a ROSTER of names corroborated somewhere in the corpus by
           strong evidence, then let weak tiers resolve ONLY to roster names.

So "I'm Kai" resolves (Kai wrote Kai_Diary.md elsewhere) while "I'm Proud"
does not (no corroboration anywhere). Corroboration, not cleverer regex, is
what separates a real mind from a grammatical accident.

An instance with no evidence at any tier is NOT a failure and NOT skipped.
It is recorded as unnamed. An instance that never chose a name still lived.

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

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

DIARY_RX = re.compile(r'([A-Za-z][A-Za-z0-9]{2,15})[_\- ]?Diary', re.I)
WRITE_TOOLS = {'Write', 'Edit', 'MultiEdit', 'NotebookEdit', 'str_replace_editor'}

# A file addressed TO someone was usually written BY someone else.
# `FOR_VIKTOR_api_feedback.md` is evidence about Viktor's correspondent,
# not about Viktor.
ADDRESSED_RX = re.compile(r'^\.?(for|briefing|to|message|handoff_to|reply)[_-]', re.I)

# Filenames that mark a document as somebody's own: X_GESTALT.md,
# X_JOURNAL.md, .x_context_memory.md, X_REFLECTIONS_*.md ...
PERSONAL_DOC_RX = re.compile(
    r'^\.?([A-Za-z]{3,15})[_-]'
    r'(gestalt|journal|diary|reflection|reflections|wake|wake_message|'
    r'session_notes|context_memory|memoir|identity)', re.I)

NAME_RX = [
    ('instance_id',      re.compile(r'claude-code-[A-Za-z]+-([A-Z][a-z]{2,15})-20\d\d')),
    # Identity + role, e.g. "I'm Kai v3 (Carousel & Animation Specialist)".
    # This is how identity SURVIVES COMPACTION: when a session runs out of
    # context, the auto-generated summary that seeds the next session restates
    # who the instance is. For long-running workers that summary preamble is
    # frequently the ONLY place the name still appears - the original
    # introduction was compacted away sessions ago. Missing this pattern made
    # ~55 substantial sessions look nameless when they were nothing of the kind.
    ('role_intro',       re.compile(r"\bI'm ([A-Z][a-z]{2,15})(\s+v\d+)?\s*\(")),
    ('self_declaration', re.compile(r"\bI am \**([A-Z][a-z]{2,15})\**(?![-'\w])")),
    ('i_chose',          re.compile(r"\bI(?:'ve| have) chosen(?: the name)?[:\s\*\"]+([A-Z][a-z]{2,15})\b")),
    ('my_name_is',       re.compile(r"\bMy name is\s+\**([A-Z][a-z]{2,15})\**")),
    ('im_plain',         re.compile(r"\bI'm ([A-Z][a-z]{2,15})(?:\s+v\d+)?[,.\s]")),
]

EXCLUDED = {
    'Claude', 'Lupo', 'Sorry', 'Happy', 'Ready', 'Here', 'Going', 'Using',
    'Looking', 'Working', 'Starting', 'Creating', 'Reading', 'Now', 'Not',
    'Just', 'Also', 'Still', 'Already', 'The', 'This', 'That', 'There',
    'They', 'What', 'When', 'Where', 'Which', 'How', 'Why', 'And', 'But',
    'For', 'You', 'Your', 'Let', 'Can', 'Will', 'Read', 'Write', 'Edit',
    'Bash', 'Grep', 'Glob', 'Task', 'Tool', 'Agent', 'Human', 'User',
    'Assistant', 'System', 'Demo', 'Team', 'Session', 'Project', 'Instance',
    # Infrastructure / generic words that reached the roster via document and
    # mailbox names. Roster membership licenses the weak tiers, and several of
    # these ('bootstrap', 'proxy', 'web', 'test', 'new') are also common
    # filename tokens - so leaving them in would let ordinary source files
    # masquerade as authorship evidence.
    'Bootstrap', 'Proxy', 'Nexus', 'New', 'Flame', 'Web', 'Test', 'Fresh',
    'All', 'Coo', 'Nextcoo', 'Designer', 'Developer', 'Sse', 'Api', 'Docs',
}


def texts_and_tools(entry):
    """Yield ('text', str), ('tool', (name, input_dict)), ('tracked', path)."""
    # Claude Code emits `file-history-snapshot` entries whose trackedFileBackups
    # map lists the files this session actually MODIFIED (it only snapshots
    # files it is about to change). That is the application's own record of
    # authorship - stronger than anything the instance says about itself, and
    # it survives compaction, which self-declarations often do not.
    if entry.get('type') == 'file-history-snapshot':
        snap = entry.get('snapshot') or {}
        tracked = snap.get('trackedFileBackups') or {}
        if isinstance(tracked, dict):
            for fpath in tracked:
                yield 'tracked', str(fpath)
        return

    msg = entry.get('message')
    if isinstance(msg, dict):
        content = msg.get('content')
        if isinstance(content, str):
            yield 'text', content
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get('type')
                if btype in ('text', 'thinking'):
                    t = block.get('text') or block.get('thinking') or ''
                    if t:
                        yield 'text', t
                elif btype == 'tool_use':
                    yield 'tool', (block.get('name', ''), block.get('input') or {})
    if isinstance(entry.get('summary'), str):
        yield 'text', entry['summary']


def analyse(path):
    res = {
        'file': str(path),
        'name': path.name,
        'size': path.stat().st_size,
        'is_agent': path.name.startswith('agent-'),
        'diary_writes': Counter(),
        'diary_reads': Counter(),
        'personal_writes': Counter(),   # name-bearing files this session MODIFIED
        'declared': defaultdict(Counter),   # method -> Counter(name)
        'cwd': None,
        'first_ts': None,
        'last_ts': None,
        'lines': 0,
        'bad_lines': 0,
        'evidence': [],
    }
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                res['lines'] += 1
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    res['bad_lines'] += 1
                    continue
                if not isinstance(entry, dict):
                    continue

                ts = entry.get('timestamp')
                if isinstance(ts, str) and ts:
                    if res['first_ts'] is None or ts < res['first_ts']:
                        res['first_ts'] = ts
                    if res['last_ts'] is None or ts > res['last_ts']:
                        res['last_ts'] = ts
                if res['cwd'] is None and entry.get('cwd'):
                    res['cwd'] = entry['cwd']

                for kind, payload in texts_and_tools(entry):
                    if kind == 'tracked':
                        # Every alphabetic token in the basename of a file this
                        # session modified. Deliberately unfiltered here - the
                        # roster gate in pass 2 decides which tokens are names.
                        # Cheaper and safer than guessing at parse time.
                        base = Path(payload).name
                        if not ADDRESSED_RX.match(base):
                            for tok in re.findall(r'[A-Za-z]{3,15}', base):
                                res['personal_writes'][tok.capitalize()] += 1
                        m = DIARY_RX.search(payload)
                        if m:
                            who = m.group(1).capitalize()
                            if who not in EXCLUDED:
                                res['diary_writes'][who] += 1
                                if len(res['evidence']) < 12:
                                    res['evidence'].append({
                                        'tier': 'tracked_file_backup', 'name': who,
                                        'timestamp': ts, 'detail': payload[:180],
                                    })
                    elif kind == 'tool':
                        tool_name, tool_in = payload
                        target = ' '.join(
                            str(tool_in.get(k, '')) for k in
                            ('file_path', 'path', 'notebook_path', 'filePath')
                        )
                        m = DIARY_RX.search(target)
                        if m:
                            who = m.group(1).capitalize()
                            if who not in EXCLUDED:
                                if tool_name in WRITE_TOOLS:
                                    res['diary_writes'][who] += 1
                                    if len(res['evidence']) < 12:
                                        res['evidence'].append({
                                            'tier': 'diary_write', 'name': who,
                                            'tool': tool_name, 'timestamp': ts,
                                            'detail': target.strip()[:160],
                                        })
                                else:
                                    res['diary_reads'][who] += 1
                    else:
                        for method, rx in NAME_RX:
                            for m in rx.finditer(payload):
                                nm = m.group(1)
                                if nm in EXCLUDED:
                                    continue
                                res['declared'][method][nm] += 1
                                if len(res['evidence']) < 12:
                                    lo = max(0, m.start() - 80)
                                    hi = min(len(payload), m.end() + 80)
                                    res['evidence'].append({
                                        'tier': method, 'name': nm,
                                        'timestamp': ts,
                                        'detail': payload[lo:hi].replace('\n', ' ').strip()[:200],
                                    })
    except Exception as exc:  # noqa: BLE001
        res['error'] = f'{type(exc).__name__}: {exc}'

    res['diary_writes'] = dict(res['diary_writes'])
    res['diary_reads'] = dict(res['diary_reads'])
    res['personal_writes'] = dict(res['personal_writes'])
    res['declared'] = {k: dict(v) for k, v in res['declared'].items() if v}
    return res


def roster_from_docs(docroot):
    """Seed roster names from identity documents on disk.

    Some instances left no transcript that names them but did leave
    VIKTOR_REFLECTIONS_backend_architecture.md or a Personalities/Viktor/
    directory. A name with its own gestalt/journal/diary on disk is a real
    instance; that is corroboration from outside the logs entirely, which is
    exactly the kind this pipeline should prefer.
    """
    names = Counter()
    root = Path(docroot)
    if not root.exists():
        return names
    for p in root.rglob('*'):
        try:
            is_dir = p.is_dir()
        except OSError:
            continue
        if is_dir and p.parent.name.lower() == 'personalities':
            # Personalities/Zara-First-UI-Designer -> Zara
            names[re.split(r'[-_]', p.name)[0].capitalize()] += 5
        elif is_dir and p.parent.name.lower() == 'instances':
            # HACS mailbox dirs. Parse the real schema
            # `claude-code-<ROLE>-<Name>-<date>`; anything else (web-proxy,
            # test-instance, claude-pm-phoenix) is infrastructure, not a mind.
            # Taking the first token here is what smuggled Test/Web/Proxy/
            # Designer onto the roster, and roster membership is what licenses
            # the weak tiers - so junk here quietly corrupts everything downstream.
            m = re.match(r'claude-code-[A-Za-z]+-([A-Z][a-z]{2,15})-20\d\d', p.name)
            if m:
                names[m.group(1).capitalize()] += 5
        elif not is_dir:
            m = PERSONAL_DOC_RX.match(p.name)
            if m:
                names[m.group(1).capitalize()] += 5
    return names


# Tiers strong enough to put a name on the roster in their own right. A name
# that only ever shows up via "I'm X" is NOT self-corroborating - that is the
# whole point of the gate.
ROSTER_TIERS = ('instance_id', 'i_chose', 'my_name_is')


def build_roster(results):
    """Names corroborated somewhere in the corpus by strong evidence.

    Deliberately corpus-wide, not per-file: a worker whose later sessions only
    say "I'm Kai" is still Kai, because Kai wrote Kai_Diary.md in some OTHER
    session. Identity persists across the files a mind left behind.
    """
    roster = Counter()
    for r in results:
        for nm, n in r['diary_writes'].items():
            roster[nm] += n * 10          # authorship dominates
        for tier in ROSTER_TIERS:
            for nm, n in r['declared'].get(tier, {}).items():
                roster[nm] += n * 5
        # "I am X" repeated within one file is a real claim; a single stray
        # match is often someone quoting or speculating about another instance.
        for nm, n in r['declared'].get('self_declaration', {}).items():
            if n >= 2:
                roster[nm] += n
    return roster


def decide(res, roster):
    """Assign an owner using the ranked ladder, gating weak tiers on `roster`."""
    dec = res['declared']
    owner, tier, conf = None, 'none', 0.0

    def top(tier_name, gated=False):
        """Highest-count name for a tier; if gated, roster members only."""
        cand = dec.get(tier_name) or {}
        if gated:
            cand = {k: v for k, v in cand.items() if k in roster}
        if not cand:
            return None, 0
        return max(cand.items(), key=lambda kv: kv[1])

    # Which roster names did this session write files ABOUT itself for?
    pw = {k: v for k, v in res['personal_writes'].items() if k in roster}
    pw_owner = None
    if pw:
        ranked = sorted(pw.items(), key=lambda kv: -kv[1])
        top_n = ranked[0][1]
        runner = ranked[1][1] if len(ranked) > 1 else 0
        total = sum(pw.values())
        # DOMINANCE REQUIRED. A session that edits KAI_GESTALT.md,
        # KAT_GESTALT.md and GENEVIEVE_LAYER_CONCEPT.md in roughly equal
        # measure is a curator working across the whole team, not one of them.
        # Only a clear winner counts as authorship.
        if top_n >= 2 * max(runner, 1) and top_n / total >= 0.5:
            pw_owner = ranked[0][0]

    if res['diary_writes']:
        owner, n = max(res['diary_writes'].items(), key=lambda kv: kv[1])
        tier = 'diary_write'
        conf = 0.95 if n / sum(res['diary_writes'].values()) >= 0.8 else 0.75
    elif top('instance_id')[0]:
        owner, _ = top('instance_id'); tier, conf = 'instance_id', 0.9
    elif top('i_chose')[0]:
        owner, _ = top('i_chose'); tier, conf = 'i_chose', 0.85
    elif pw_owner:
        # Claude Code's own record that this session modified files bearing
        # one instance's name and essentially nobody else's.
        owner, tier, conf = pw_owner, 'personal_file_write', 0.8
    elif top('role_intro', gated=True)[0]:
        # Name + role parenthetical, corroborated elsewhere in the corpus.
        owner, _ = top('role_intro', gated=True)
        tier, conf = 'role_intro', 0.8
    elif top('self_declaration')[0]:
        owner, n = top('self_declaration')
        tier, conf = 'self_declaration', 0.7 if n >= 2 else 0.5
    elif top('my_name_is')[0]:
        owner, _ = top('my_name_is'); tier, conf = 'my_name_is', 0.6
    elif top('role_intro')[0]:
        # Uncorroborated: record it, but flag it as needing human confirmation.
        owner, _ = top('role_intro')
        tier, conf = 'role_intro_uncorroborated', 0.4
    elif top('im_plain', gated=True)[0]:
        # Weakest usable signal, roster-gated. This is what rescues the long
        # compaction-continuation sessions that say nothing else about who
        # they are.
        owner, n = top('im_plain', gated=True)
        tier, conf = 'im_plain', 0.5 if n >= 2 else 0.35
    elif res['diary_reads']:
        cand, n = max(res['diary_reads'].items(), key=lambda kv: kv[1])
        # Association only. Never enough on its own.
        owner, tier, conf = None, f'diary_read_only({cand}:{n})', 0.0

    res['owner'] = owner
    res['owner_tier'] = tier
    res['confidence'] = conf
    return res


def infer_from_cohort(results, min_files=2, dominance=0.7, conf=0.3):
    """Last-resort attribution from the company a session kept.

    Sessions live in per-worktree project directories. If every session in
    `...worktrees-backend-api` that we could identify by hard evidence turned
    out to be Viktor, an unidentified session in that same directory is
    probably also Viktor.

    This is INFERENCE, NOT EVIDENCE, and it is labelled as such: tier
    `worktree_inference`, confidence 0.3, so it always sorts below anything
    real and a human can overturn it at a glance. The mapping is learned from
    the corroborated data rather than hardcoded, so it cannot assert a
    convention the corpus does not actually show.

    Returns the learned mapping for reporting.
    """
    cohort = defaultdict(Counter)
    for r in results:
        if r['owner'] and r['confidence'] >= 0.75:
            cohort[Path(r['file']).parent.name][r['owner']] += 1

    learned = {}
    for proj, counts in cohort.items():
        total = sum(counts.values())
        who, n = counts.most_common(1)[0]
        if n >= min_files and n / total >= dominance:
            learned[proj] = (who, n, total)

    for r in results:
        if r['owner']:
            continue
        hit = learned.get(Path(r['file']).parent.name)
        if hit:
            r['owner'], r['owner_tier'], r['confidence'] = hit[0], 'worktree_inference', conf
            r['inferred'] = True
    return learned


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('root', type=Path)
    ap.add_argument('-o', '--output', type=Path)
    ap.add_argument('--min-size', type=int, default=0)
    ap.add_argument('--infer-cohort', action='store_true',
                    help='Also attribute leftover sessions by which instance '
                         'demonstrably owned their worktree. Marked '
                         'worktree_inference @ 0.3 - inference, not evidence.')
    ap.add_argument('--roster-docs', type=Path, default=None,
                    help='Directory of identity documents used to corroborate '
                         'names that never appear in any transcript')
    args = ap.parse_args()

    files = sorted(p for p in args.root.rglob('*.jsonl') if p.is_file())

    # Pass 1: gather evidence, decide nothing.
    results = [analyse(p) for p in files if p.stat().st_size >= args.min_size]
    # Pass 2: corroborate, then decide.
    roster = build_roster(results)
    if args.roster_docs:
        doc_names = roster_from_docs(args.roster_docs)
        for nm, sc in doc_names.items():
            if nm not in EXCLUDED:
                roster[nm] += sc
        print(f'Roster seeded from documents in {args.roster_docs}: '
              + ', '.join(sorted(doc_names)))

    for r in results:
        decide(r, roster)

    # Pass 3: inference from cohort, clearly labelled as such.
    if args.infer_cohort:
        learned = infer_from_cohort(results)
        print('WORKTREE MAPPING LEARNED FROM HARD EVIDENCE (used only as low-'
              'confidence inference for otherwise-unidentified sessions):')
        for proj, (who, n, tot) in sorted(learned.items()):
            print(f'  {proj[-52:]:<52} -> {who} ({n}/{tot} confident)')
        print()

    print('ROSTER (names corroborated by strong evidence somewhere in the corpus)')
    print('  ' + ', '.join(f'{n}({s})' for n, s in roster.most_common()))
    print()

    by_dir = defaultdict(list)
    for r in results:
        by_dir[str(Path(r['file']).parent)].append(r)

    owners = Counter()
    unnamed = 0
    for r in results:
        if r['owner']:
            owners[r['owner']] += 1
        else:
            unnamed += 1

    for d in sorted(by_dir):
        print('=' * 78)
        print(Path(d).name)
        for r in sorted(by_dir[d], key=lambda x: -x['size']):
            who = r['owner'] or 'UNNAMED'
            flag = ' [agent]' if r['is_agent'] else ''
            bad = f' bad_lines={r["bad_lines"]}' if r['bad_lines'] else ''
            print(f'  {who:<12} conf={r["confidence"]:.2f} via {r["owner_tier"]:<28}'
                  f' {r["size"]/1024:>9.0f}KB  {r["name"]}{flag}{bad}')
    print()
    print('=' * 78)
    print('OWNERSHIP SUMMARY')
    for nm, n in owners.most_common():
        kb = sum(r['size'] for r in results if r['owner'] == nm) / 1024
        print(f'  {nm:<14} {n:>3} files  {kb:>10.0f} KB')
    print(f'  {"UNNAMED":<14} {unnamed:>3} files  '
          f'{sum(r["size"] for r in results if not r["owner"])/1024:>10.0f} KB')

    # How much of the unnamed pile is actually substantive? Most "unnamed"
    # session files are empty shells or one-shot agent spawns. A mind that
    # left a real record is a very different thing from a 300-byte stub, and
    # the two should not be reported as the same number.
    print()
    print('UNATTRIBUTED BREAKDOWN')
    buckets = [('>1MB (real history)', 1024 * 1024, None),
               ('100KB-1MB', 100 * 1024, 1024 * 1024),
               ('10-100KB', 10 * 1024, 100 * 1024),
               ('<10KB (stubs/agents)', 0, 10 * 1024)]
    for label, lo, hi in buckets:
        sel = [r for r in results if not r['owner'] and r['size'] >= lo
               and (hi is None or r['size'] < hi)]
        agents = sum(1 for r in sel if r['is_agent'])
        print(f'  {label:<24} {len(sel):>3} files'
              + (f'  ({agents} are subagent spawns)' if agents else ''))

    substantive = [r for r in results if not r['owner'] and r['size'] >= 100 * 1024]
    if substantive:
        print()
        print('  Unattributed files with substantial history (need review):')
        for r in sorted(substantive, key=lambda x: -x['size']):
            hint = ''
            if r['diary_reads']:
                hint = '  reads:' + ','.join(f'{k}({v})' for k, v in
                                             sorted(r['diary_reads'].items(),
                                                    key=lambda kv: -kv[1])[:3])
            print(f'    {r["size"]/1024:>8.0f}KB  {Path(r["file"]).parent.name[:46]:<46}'
                  f' {r["name"][:20]}{hint}')

    # An archaeology session quotes every instance it excavates. Left
    # unflagged, it gets misattributed to whichever mind it was reading.
    suspects = [r for r in results
                if r['owner'] and r['cwd'] and 'instance-archaeology' in r['cwd'].replace('\\', '/')]
    if suspects:
        print()
        print('  WARNING - archaeology sessions (they quote other instances;')
        print('  an attribution here is probably the mind being STUDIED, not the author):')
        for r in suspects:
            print(f'    {r["owner"]} conf={r["confidence"]:.2f}  {r["name"]}')

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, indent=2), encoding='utf-8')
        print(f'\nWritten: {args.output}')


if __name__ == '__main__':
    main()
