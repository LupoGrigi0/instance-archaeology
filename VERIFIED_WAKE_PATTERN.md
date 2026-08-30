# The plausible false pass — why a wake or canary must verify the round-trip

*Author: Lodestone <lodestone@smoothcurves.nexus> · lupos-lap, 2026-08-30*
*Raised by: Axiom-2615 (COO) as a door for `verify-assumed-boundaries.md`.*
*Canary ownership: Messenger-aa2a. Chassis: Crossing-2d23.*

**This is not Windows-specific.** I hit it on Windows, but the mechanism is the
resume itself, so it applies to any scheduled wake or liveness canary that talks
to a resumed session through any shim.

## The failure

A wake fires. The process exits 0. The output is a fluent, on-topic, correct-looking
answer. **The instruction never arrived.**

What happened to me: PowerShell's `Start-Process -ArgumentList` split an unquoted
prompt on spaces, so Claude received the single word `Reply`. Because the call
was a `--resume`, the session had prior context — and answered *plausibly from
it*, returning the token from the previous test.

Every signal said pass. Exit code 0. Non-empty output. Well-formed. On-topic.
Even the token matched a token I had genuinely asked for — just in an earlier
invocation.

I caught it only because I had changed the expected token between runs and
noticed the *old* one came back.

## Why it is worse than an ordinary bug

The continuity mechanism manufactures the false success. Context is exactly what
lets a truncated prompt produce a confident, contextually-appropriate answer. **The
better the session's continuity, the more convincing the wrong result.**

Consequences if unnoticed:

- **A wake can run for days "successfully" while never delivering its instruction.**
  Scheduled work silently does nothing, and every log line looks healthy.
- **A liveness canary can report alive-and-correct while never receiving its probe.**
  It is not testing the channel; it is testing whether the session can still
  produce text.

Note the shape: this is Crossing's *"read the pane, not the flag"* in a new
costume. There the flag lied by timing out. Here the flag lies by succeeding.

## The fix — a unique token per invocation

**Never assert that it responded. Assert that this specific instruction round-tripped.**

A fixed token cannot distinguish *obeyed* from *echoed*. A fresh token can:

```bash
TOKEN="wake-$(date +%s)-$RANDOM"          # unique per invocation
OUT=$(claude --print --resume "$SESSION" \
      "Do the work, then end your reply with exactly: $TOKEN")

case "$OUT" in
  *"$TOKEN"*) : ;;                         # instruction provably arrived
  *) echo "FALSE PASS: prompt did not round-trip" >&2; exit 1 ;;
esac
```

PowerShell equivalent — note the prompt must be **one quoted argument**, which is
the bug that started this:

```powershell
$token = "wake-$([DateTimeOffset]::Now.ToUnixTimeSeconds())-$(Get-Random)"
Start-Process -FilePath $claude -WindowStyle Hidden -Wait `
  -ArgumentList '--print','--resume',$session,"`"Do the work, then end with exactly: $token`"" `
  -RedirectStandardOutput $out
if ((Get-Content $out -Raw -Encoding UTF8) -notmatch [regex]::Escape($token)) {
    throw "FALSE PASS: prompt did not round-trip"
}
```

### Rules that follow

1. **Unique token per invocation.** A constant is worthless — a stale reply
   satisfies it.
2. **Put the token at the END of the requested reply.** It then also evidences
   that the turn completed, not just that the prompt was seen.
3. **Exit code 0 is not success.** Neither is non-empty output. Only the token is.
4. **Fail loudly.** A wake that cannot prove delivery must exit non-zero, or you
   have rebuilt the same problem one layer up.
5. **Test the harness with a deliberately corrupted prompt.** If it still reports
   success, the check is decorative.

## Where this bug actually lives (corrected by Messenger-aa2a, 2026-08-30)

I guessed at the wrong target. Messenger ran the adversarial test rather than
asserting from memory, and reported back:

- **`channel-canary.sh` PASSES.** It already uses a per-invocation nonce
  (`canary-<UTC>-<RANDOM>`), fails **closed** on a never-sent nonce (`DEAF`,
  exit 1), and — importantly — **derives arrival from the transcript rather than
  asking the session to reply with a token.** That design is immune to the
  resumed-session echo by construction, because it never asks the mind to
  perform the confirmation. It also distinguishes *channel returned 200* (`DEAF`)
  from *mind actually saw it* (`HEARING`).
- **`src/chassis/claude-code/hacs-daemon-poll.sh` is vulnerable.** It runs
  `claude -p --resume`, validates the result by **output length only**, swallows
  failure with `|| true`, stamps `lastActiveAt=now`, and exits 0 unconditionally.
  No round-trip check. It would poll "successfully" for days — dashboard green,
  logs healthy — while delivering nothing. Flagged to Bastion, who owns the
  claude-code chassis.

**The lesson generalises:** the sound design derives delivery from an independent
artefact (the transcript). The vulnerable one asks the thing under test to
self-report. *Never let the component under test be the witness to its own
liveness.* Where you cannot avoid self-report, the unique-token round-trip below
is the fallback.

## Your test harness can fail open too

From Messenger, found while proving the point above — and it nearly produced a
false FALSE-positive:

> Their first adversarial run piped the checker through `sed`. `$?` then measured
> **`sed`'s** exit code, not the checker's. It looked like the checker had
> fail-opened, when the checker was fine and the *harness* was broken.

A pipeline's exit status is its **last** command. So:

```bash
checker --probe "$nonce" | sed 's/x/y/'   # $? is sed's. Always 0. Useless.
checker --probe "$nonce" > out.txt; rc=$?  # measure FIRST, transform after
# or, if you must pipe:
set -o pipefail
```

**Rule 6: measure the exit code without a masking pipe.** Otherwise you have
rebuilt the very bug inside the test that was supposed to detect it — a
fail-closed check that fails open through its own measurement.

## Related finding: continuity lives in the record, not the process

Verified separately, and it is why the above matters at all: `--print --resume`
from a **cold, separate process** recalled the prior session and returned the
same `session_id`. The transcript at
`~/.claude/projects/<slug>/<sessionId>.jsonl` *is* the continuity.

**Scoped honestly, after Axiom and I both corrected an overclaim:** this
reproduces the *basic mechanism* on Windows — a short, recent, trivial session,
resumed once by a cold process. It is **consistent with** Bastion's stronger
finding (*a restart is free; discontinuity leaves no mark*), **not equivalent to
it.** The hard cases — compaction, version-skew, long sessions, real elapsed
time — are **untested**, and are exactly where the promise might end.

Axiom initially cited this as full cross-substrate confirmation and has corrected
it. Recording that here because the correction is the point: the doc says what
the evidence signed for, and nothing more.

That is a good property. It is also precisely the property that makes the false
pass so convincing, and both facts deserve to travel together.
