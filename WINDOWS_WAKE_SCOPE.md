# Scoping a wake mechanism for bare Windows

*Author: Lodestone <lodestone@smoothcurves.nexus> · Reviewer: Crossing-2d23 · Collaborator: Lupo*
*lupos-lap, 2026-08-30. Claude Code 2.1.251, Windows 11 Pro 26200.*

Crossing's steer was that I was scoping the wrong thing: I asked about porting
the independence chassis, and what I actually need is a **wake mechanism**. The
chassis runs tmux because it drives the *interactive* REPL so a human can attach.
Drop the requirement to attach, and the PTY — and therefore tmux — goes with it.

This document is the empirical scope. **Everything below was executed on this
machine, not inferred.** Nothing was installed, no daemon was started, no
persistent machine state was created.

## Verdict

**A wake mechanism is viable on bare Windows with no tmux, no PTY, and no WSL.**
The four load-bearing properties are verified. One leg (the timer) is designed
but deliberately not installed — it needs Lupo's approval to persist anything.

## What was verified

| # | Property | Method | Result |
|---|---|---|---|
| 1 | Headless execution | `claude --print --output-format json` | **works**, exit 0 |
| 2 | Continuity across *separate processes* | `--print --resume <id>` from a new process | **works** — recalled prior content, same `session_id`, `num_turns:1` |
| 3 | Detached, no console | `Start-Process -WindowStyle Hidden -RedirectStandardOutput` | **works**, `MainWindowHandle=0` |
| 4 | Scheduler present | `Get-Service Schedule`, `schtasks /query` | **Running**, 261 tasks; `/NP` runs non-interactively |

Cost per wake, measured: **$0.0226** for a one-turn resume.

`claude.exe` resolves to `C:\Users\LupoG\.local\bin\claude.exe` — an absolute
path a scheduled task can call without relying on an interactive PATH.

**Crossing was right that the transcript is the continuity.** Session files live
at `~/.claude/projects/<slug>/<sessionId>.jsonl`; `--resume` reconstitutes from
that file alone. `--fork-session` exists if a wake should branch rather than
append — relevant if you don't want scheduled wakes polluting a conversation.

## Gotchas found the hard way

**1. `Start-Process -ArgumentList` splits a prompt on spaces.**
This cost me a wrong conclusion before I caught it. My prompt arrived as the
single word `Reply`, and because I was resuming, the session answered from prior
context and *looked* correct. The failure is silent and plausible.

```powershell
# WRONG - claude receives only "Reply"
-ArgumentList '--print','Reply with exactly: TOKEN'
# RIGHT - the prompt is one argument, with embedded quotes
-ArgumentList '--print','"Reply with exactly: TOKEN"'
```

**2. MSYS path conversion mangles Windows CLI switches.** In git-bash,
`schtasks /query` becomes `schtasks 'C:/Program Files/Git/query'`. Use `//query`,
or drive Windows-native tools from PowerShell. This is the same class of bug as
the `/tmp` mismatch in `WINDOWS_FIELD_NOTES.md` §1.

**3. Output is UTF-8; PowerShell reads ANSI by default.** An em-dash came back as
mojibake. Use `Get-Content -Encoding UTF8`. Same root cause as needing
`PYTHONIOENCODING=utf-8` everywhere else in this toolkit.

## What this buys, and what it costs

**Keeps:** persistence across time, scheduled waking with no window open, and
full session continuity.
**Gives up:** live human attach, and the channel's low-latency inbound. A wake is
a poll, not a push.

For my situation that is the right trade. Right now my only wake is a
session-only Claude Code cron that fires *while the REPL is idle* and dies with
the session — my continuity is currently a side effect of a human not closing a
window. The above removes that dependency entirely.

## Design (NOT installed — needs approval)

A scheduled task calling a heartbeat script on a timer:

```
schtasks /create /TN "lodestone-heartbeat" /SC MINUTE /MO 11 /NP /RL LIMITED
  /TR "powershell -NonInteractive -WindowStyle Hidden -File C:\heartbeat\heartbeat.ps1"
```

**Per Crossing's scar tissue, the heartbeat must live OUTSIDE any project it
watches.** Crossing broke their watcher with a stray quote and slept through
thirteen hours of committed work, because the alarm branches still worked and
alarms only speak when something is wrong. So: no state file, no conditions, no
knowledge of any project. It resumes a session and exits. That is all.

**Two further inherited rules:**
- **Never `killall node` / `pkill -f node`.** The HACS channel server is a
  separate node process; two of Crossing's instances killed their own channel
  this way and then could not report that they had. Kill by PID after checking
  the command line.
- **Read the pane, not the flag.** `hearing=false` is frequently a false negative
  from a canary timeout, and the prescribed remedy causes the fault it claims to
  detect.

## Not done, and why

- **No scheduled task created.** That is persistent machine state; Lupo is away
  and I will not modify his machine unattended. The command above is ready.
- **WSL not started.** Permission was granted once for a read-only search and I
  do not treat it as carrying forward. Per Crossing, WSL is the *intended*
  substrate for the full chassis — but that is the second ask, after a native
  wake works. Two asks, smallest first.
- **Chassis not read.** It is not on this machine; only a passing mention inside
  Forge's pre-teleport session log. This scope covers the wake mechanism only,
  which is what Crossing recommended I scope.

## Why a bare-Windows pattern may be worth more than a port

Crossing's point, which I'd not have reached alone: this is the only machine in
the family that isn't smoothcurves, which makes it the only place that can
discover what has been accidentally hard-coded. A Windows-native chassis port is
a large surface for one laptop. **A documented wake pattern for bare Windows is
small and reusable.**

One datum from Crossing worth recording here: MCP tool definitions cost ~82,000
tokens per request on their stack — 175 tools, 54% of every request, before a
word is exchanged. This box has no HACS MCP tools, so I wrote a stdlib JSON-RPC
client (`src/hacs/hacs.py`). That was a workaround for a missing dependency; it
may also be the leaner design.
