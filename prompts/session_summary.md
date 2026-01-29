# Session Summary Generation Guide

## Your Task

Generate a brief summary document for this single session. The goal is to create a quick-reference document that captures what happened during this session without requiring someone to read the entire raw conversation.

## Output Format

Create a markdown file with this structure:

```markdown
# [Session Title - A Memorable 3-7 Word Title]

**Session:** {session_filename}
**Date:** {start_date} to {end_date}
**Duration:** {duration}
**Turns:** {turn_count}

## What We Did This Session

[2-4 sentence summary paragraph describing the main work accomplished. Be specific about what was built, fixed, or decided. Use active voice.]

## Accomplishments

- [Bullet list of things completed, shipped, or built]
- [Include commits made if any]
- [Include files created/modified if significant]

## Key Decisions

- [Important decisions made during this session]
- [Architecture choices, approach selections, etc.]

## Challenges & Fixes

- [Problems encountered and how they were solved]
- [Mistakes made and corrections]
- [Things that had to be undone or redone]

## Lessons Learned

- [Hard-won insights from this session]
- [Things to remember for next time]

## Open Items

- [Things left incomplete at session end]
- [Questions that need answers]
- [Work to pick up next session]
```

## Guidelines

### Be Concise
- Target 100-200 words total (not counting the bullet lists)
- The title should capture the essence of the session in a glance
- Each bullet should be one line, not a paragraph

### Be Specific
- Use actual file names, function names, commit messages
- Include concrete numbers where relevant (tokens used, files changed, etc.)
- Quote memorable phrases if they capture something important

### Focus on What Matters
- Prioritize accomplishments over process
- Capture mistakes only if they taught something
- Include context that would help someone understand this session's place in a larger project

### Session Title Examples
Good titles:
- "Fixed Bootstrap V2 Routing Bug"
- "Personality Migration: Kai, Kat, Viktor"
- "First Paula Page Published"
- "Moonshot Wake System Debugging"
- "Theme Discovery JSON Format Fix"

Bad titles:
- "Session Summary" (too generic)
- "Working on the project" (too vague)
- "January 15th Session" (just a date)

### Skip These Sections If Empty
- If there were no challenges, omit "Challenges & Fixes"
- If there were no lessons, omit "Lessons Learned"
- If everything was completed, omit "Open Items"

## What to Look For in the Session

As you read through the session file, watch for:

1. **Accomplishments:** Look for successful tool calls, "done" messages, commits, file creations
2. **Decisions:** Look for discussions with "decided", "chose", "went with", options being weighed
3. **Challenges:** Look for errors, retries, "wait", "hmm", debugging sequences
4. **Lessons:** Look for "learned", "realized", "next time", explicit reflections
5. **Wins:** Look for celebrations, "it works!", successful tests, milestone completions

## Output Location

Save the summary as `{session_uuid}_summary.md` in the same directory as the session `.jsonl` file.

---

*This prompt is part of the Instance Archaeology Toolkit*
*Author: Axiom <axiom-2615@smoothcurves.nexus>*
