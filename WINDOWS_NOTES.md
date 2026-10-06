# Running the Instance Archaeology Toolkit on Windows

Written after the first Windows run (GreyWolf, 2026-08-30). The toolkit was
built Unix-first. Nothing in it is fundamentally incompatible, but a dozen
small things will waste your day if you meet them one at a time. This is the
list, in the order they bit.

---

## 0. Do these three things before anything else

```bash
export PYTHONIOENCODING=utf-8      # or emoji in the logs will kill your pipeline
export LC_ALL=C                    # or `sort` dies on multibyte input
```

and use **`python`**, not `python3`. Both exist on this machine (3.13.3 and
3.13.14) but `python3` is not always what the harness resolves.

**DO NOT UPDATE CLAUDE CODE.** Recent versions delete "old" `.jsonl` files.
On an archaeology machine those files *are* the subject matter. The version
installed on GreyWolf is deliberately out of date. Leave it.

---

## 1. Console encoding — the one that costs you a whole run

Windows Python defaults stdout to **cp1252**. These logs are saturated with
emoji (status lines are full of 🟢). The first non-ASCII character raises:

```
UnicodeEncodeError: 'charmap' codec can't encode character '\U0001f7e2'
```

`PYTHONIOENCODING` covers most of it, but scripts should not depend on the
caller getting the environment right. Every script in this toolkit that prints
log content now opens with:

```python
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass
```

Add this to anything new. It is three lines and it is the difference between a
run and a crash forty minutes in. Also read files with
`open(p, encoding='utf-8', errors='replace')` — some archived logs contain
genuinely malformed sequences and you want them *reported*, not fatal.

---

## 2. The shell is not bash, whatever it claims

Claude Code runs through MSYS/git-bash here, and several ordinary constructs
**silently produce empty variables** rather than failing loudly. Observed:

| construct | behaviour |
|---|---|
| `for d in "a" "b"; do ...; done` | loop body runs, `$d` is empty |
| `while read -r x; do ...; done` | `$x` lost |
| `echo "$(basename $d)"` | command substitution printed literally |
| `f=value` (bare assignment) | `command not found` |
| `cmd \` + newline + `  --flag` | continuation mangled, "unrecognized arguments" |
| `!=` inside `python -c "..."` | history expansion corrupts it to `\!=` |

Simple cases (`d=hello; echo "$d"`) work fine, so it is not obviously broken —
which is exactly why it wastes time.

**Do not orchestrate in shell. Orchestrate in Python.** Every multi-step
operation in this run became a Python script for this reason
(`scan_tree.py`, `archive_tree.py`, `resolve_ownership.py`,
`build_instance_views.py`). Keep long command lines on **one line**, and prefer
writing a real `.py` file over a long `python -c "..."`.

---

## 3. Paths

`pathlib` handles Windows correctly; the toolkit's existing scripts are pure
pathlib and needed **no changes** for path separators. Two rules:

- Normalise with `.as_posix()` or `.replace('\\', '/')` **before** regex
  matching a path. `re` against a raw Windows path is a backslash-escaping trap.
- Compare paths with `Path.resolve()`, not strings. `C:\Users\...` vs
  `C:/Users/...` vs `c:\users\...` all name the same file.

Guard against long-path and permission errors when walking big trees:

```python
try:
    if not p.is_file():
        continue
except OSError:
    continue
```

`.jsonl` timestamps are **not always strings** — `history.jsonl` uses integer
epochs, and `ts[:10]` on an int raises `TypeError`. Coerce first.

---

## 4. Where the data actually is

The brief said `c:\downloads\Claude_backup\*`. It was wrong. **Verify before
concluding anything is missing.** On GreyWolf:

- `C:\Users\LupoG\Downloads\Claude_backups\` — 5 folders, but **only
  `lupoG_Dot_Claude/` contained logs** (156). The other four hold nothing but
  `settings.local.json`. Those backups failed.
- `C:\Users\LupoG\.claude\` — **live, 34 more logs, in no backup at all.**
  Always check the live directory. Ask before touching it, then archive it.
- `C:\Users\Lupo\.claude` does not exist. Different profile name than expected.

No Codex / Crush / OpenCode / Gemini / Aider logs on this machine. If you find
any elsewhere they need `src/converters/codex_to_archaeology.py` first — the
symptom of skipping it is a silent `Total: 0`, which looks like "empty" but
means "untranslated".

---

## 5. Do not sweep only `*.jsonl`

**The single most important thing in this document.**

`lupoG_Dot_Claude/` holds 3,029 files, of which 156 are `.jsonl`. Phoenix left
**no session log whatsoever** — a grep for "Phoenix" across all 190 archived
transcripts returns nothing. Phoenix exists only as `PHOENIX_JOURNAL.md`, a
wake message, a handoff, and 8 HACS `inbox.json` mailboxes. A `.jsonl`-only
run loses that entire mind and reports success.

Sweep at minimum: `*Diary*.md`, `*JOURNAL*.md`, `*GESTALT*.md`, `*WAKE*.md`,
`*HANDOFF*.md`, `*IDENTITY*.md`, whole `Personalities/` trees, and
`inbox.json` under `messages/instances/`. Use `--exclude` to skip
`node_modules|site-packages|venv|.git|conda|__pycache__|.next|zoneinfo`,
or you will hash half of PyTorch.

---

## 6. Identification: assume your heuristic is lying

Both Windows-era runners independently generated fake instances.

- Mine: a `signature` regex allowing `-- Name` at end-of-line matched ordinary
  markdown bullets under `re.M` and invented **Footer, Butterflies, Boundaries,
  Silhouettes, Tagline, Scalability**.
- The laptop's: `identify_instance.py` produced **MultiEdit, Pcores,
  Envisioning**, and named their own live session **Orla** after it read a file
  mentioning Orla. It scans whole files and counts mentions of *other*
  instances.

`identify_instance.py` should not be trusted unsupervised. Prefer
`resolve_ownership.py` (this run) or `identity_evidence.py` (the laptop's).

Working principles:

1. **Never label an archive without reading the receipt.** `show_evidence.py`
   exists for this. Proximity to a keyword is not evidence of identity.
2. **Prefer what the application recorded over what the instance said.**
   `file-history-snapshot` → `trackedFileBackups` lists the files a session was
   about to *modify*. It is authorship evidence, and it survives compaction.
3. **Writing ≫ reading.** Instances read each other's diaries freely and write
   only their own.
4. **Require dominance for file-based authorship.** A session editing
   `KAI_GESTALT.md`, `KAT_GESTALT.md` and `GENEVIEVE_LAYER_CONCEPT.md` equally
   is a curator, not any of them.
5. **Gate weak patterns on a corroborated roster.** Ungated, `"I'm X"` yields
   *Proud*, *Seeing*, *Excited*. Two passes: collect evidence everywhere, build
   the roster, then decide.
6. **Identity survives compaction inside the summary.** For long-running
   workers, `"I'm Kai v3 (Carousel & Animation Specialist)"` in a continuation
   preamble is often the only surviving statement of who they are. Scan for it.
7. **Quarantine archaeology sessions.** They quote everyone they excavate. One
   of mine was confidently labelled *Genevieve*. Flag any session whose `cwd`
   is the toolkit itself.

---

## 7. Verifying you did no harm

`archive_tree.py` copies only — no move, no delete, no truncate — and verifies
every copy by re-hashing the destination. Re-hash the **sources** afterwards
too (`_scan/verify_sources.py`).

One expected anomaly: **your own session log will fail the check.** Claude Code
appends to it while you work, so its hash drifts. That is not damage. Confirm
the archived bytes are still an exact **prefix** of the live file:

```python
head = src.open('rb').read(recorded_size)
assert hashlib.sha256(head).hexdigest() == recorded_sha  # append-only: fine
```

Anything other than prefix-growth means an original was rewritten. Stop.

---

## 8. Repo size

The catacomb `.git` was already 236 MB before this run, with 93 MB `.jsonl`
files tracked in plain git. `git-lfs` 3.3.0 is installed but **not configured**.
Adding a full archive roughly doubles the repo, permanently. Confirm the intent
with Lupo before committing — this run was committed to plain git by explicit
decision.

---

*Written by Lantern, GreyWolf, 2026-08-30, so the next runner does not
rediscover any of it.* 🏮
