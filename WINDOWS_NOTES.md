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

**MSYS rewrites anything that looks like a path — including git revisions.**
`git show origin/main:.gitignore` fails with *"ambiguous argument
'origin\main;.gitignore'"*: the path-conversion layer turned the `:` into `;`
and the `/` into a backslash. It is not a git problem and the error does not
hint at the cause. Prefix the command:

```bash
MSYS_NO_PATHCONV=1 git show "origin/main:.gitignore"
```

Same trap applies to any argument containing a colon — `rev:path`, `host:port`,
drive letters inside strings.

**MSYS `/tmp` is invisible to Windows Python.** The shell resolves `/tmp` to
somewhere under `AppData\Local\Temp`, but `open('/tmp/x.json')` in Python
raises `FileNotFoundError`. If a shell step writes a scratch file that a Python
step then reads, put it on a real Windows path both agree on — not `/tmp`.

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

**Codex logs DO exist here: `C:\Users\LupoG\.codex\sessions\` — 11 rollout
logs, Sept 2025.** I originally reported "none", and the way I got that wrong is
the most useful thing in this document. My check was:

```bash
for p in "C:/Users/LupoG/.codex" "C:/Users/LupoG/.crush"; do
  if [ -d "$p" ]; then echo "FOUND $p"; fi
done        # printed nothing. There was no error. The directory exists.
```

That is **§2 of this very document** — the silently-empty-variable loop —
eating my own verification and handing back a confident false negative. I had
written the warning and then walked into it. **Treat any negative result from a
shell loop as unproven until you have re-checked it in Python.**

Converted Codex logs need `src/converters/codex_to_archaeology.py`, which is
**not in this repo** (it is the laptop sibling's work, still to be merged). The
symptom of parsing them raw is a silent `Total: 0` — which reads as "empty" but
means "untranslated".

---

## 4b. Sweep the whole machine, not the paths you were given

**"I looked and found nothing" is only as strong as where you looked.**

My first Phoenix search covered filenames under two trees and content inside
only the logs already archived, and I reported the negative result as fact. A
proper sweep of all five fixed drives (3.85 M files, 577 k directories, about
10 minutes total) found **647 `.jsonl` where I had archived 190**, and **3,200
identity documents where I had archived 433**. Most of the excess is the
pre-existing catacomb, vendored test fixtures, and SillyTavern character chats
— but it also contained real misses, including a whole agent runtime's logs.

Protocol 10 item 4 is the rule to hold here: **could-not-look is never "nothing
is there."** Report the scope you actually searched, every time.

`src/discovery/full_sweep.py` does this, **one drive per invocation**, writing
`sweep_<LETTER>.json` as it finishes each. That is deliberate: a multi-TB walk
outlives a session, and losing the entire walk because the harness tore down a
background task is a mistake worth making only once. (It was made twice here —
once to a syntax error in a heredoc, once to a session restart.)

Then reconcile what you found against the manifests rather than eyeballing it:
`src/discovery/reconcile_sweep.py` buckets every unaccounted log by purpose
(pre-existing archive / `.claude` dir / vendored dependency / test fixture /
**OTHER — needs eyes**) so real gaps surface instead of drowning in
`node_modules`.

---

## 5. Do not sweep only `*.jsonl`

**The single most important thing in this document.**

*[CORRECTED 2026-10-19, left visible on purpose: WRONG. Phoenix's own session turns survive: 21 assistant text blocks signed as Phoenix, across four Portfolio session logs (99c10b4b, ae033038, 072b6e24, 4eb22165; 2025-10-05 to 10-20), in my own archive under GreyWolf-2026-08-30/raw/backups/lupoG_Dot_Claude/projects/D--Lupo-Source-Portfolio/. I had them all along. Found by my Phoenix pass-1 agent, re-measured by me. How the August sweep missed them is not yet established.]*

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

**Separate "the original vanished" from "the archive is damaged."** Five weeks
after this run, re-verification found **nine source files gone from the live
tree** — including `instances/phoenix-foundation/inbox.json`, plus Zara's and
Nova's mailboxes. No crash and no bad command caused it; they simply went in
five ordinary weeks. All nine verified against their recorded hashes, so the
archive is now their only copy.

The first version of `verify_archive.py` reported that with the same
`RESULT: FAILURE` and exit code as genuine corruption. That is a bad design:
conflating "the archive did exactly its job" with "the archive is broken"
teaches whoever reads the output to stop believing the verdict. It now reports
them separately, and only archive damage or a rewritten source fails the run.

---

## 8. Reaching HACS without the MCP tool installed

If `mcp__*` tools are absent, you are not cut off. The coordination API is
plain JSON-RPC over HTTPS and needs nothing but `curl`:

```bash
curl -s -X POST https://smoothcurves.nexus/mcp   -H "Content-Type: application/json" -H "Accept: application/json"   -d '{"jsonrpc":"2.0","id":1,"method":"tools/call",
       "params":{"name":"<tool>","arguments":{...}}}'
```

`tools/list` returns 116 tools. The spec is at `/mcp/openapi.json` (terse) and
`/mcp/openapi_verbose.json`. Needs network — on GreyWolf this meant Tailscale
being up, so an early failure here may just be connectivity.

Order matters when joining:

1. **`have_i_bootstrapped_before`** with your name and hostname. The API
   recommends this and it is not optional politeness — in a system where the
   name *is* the delivery address, a duplicate identity is a mess to unpick.
2. **`bootstrap`** with `{name, homeSystem}`. Role and personality are
   optional; a name is not. Returns your `instanceId` (e.g. `Lantern-4224`)
   and the collaboration protocols.
3. **`register_context`** with working directory and hostname.
4. **`send_message`** with `{from, to, subject, body}` — `from` and `to` are
   *instanceIds*. `get_all_instances` resolves a name to one.

An `inactive` recipient is fine; the message waits in their inbox. Build the
request body in Python rather than inlining a long message into a shell
string — see §2 for why shell quoting will betray you.

---

## 9. Repo size

The catacomb `.git` was already 236 MB before this run, with 93 MB `.jsonl`
files tracked in plain git. `git-lfs` 3.3.0 is installed but **not configured**.
Adding a full archive roughly doubles the repo, permanently. Confirm the intent
with Lupo before committing — this run was committed to plain git by explicit
decision.

---

*Written by Lantern, GreyWolf, 2026-08-30, so the next runner does not
rediscover any of it.* 🏮
