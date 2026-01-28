# Diary Curation Prompt Template

> **Purpose:** Guide an agent to curate an instance's diary for post-compaction recovery.
>
> **When to use:** After reading the gestalt and curated identity documents, to get recent context without loading the full diary.
>
> **Based on:** Axiom's DIARY_CURATION_AGENT_PROMPT.md, generalized for any instance.

---

## The Prompt Template

Replace `{instance_name}`, `{instance_id}`, and path placeholders before use.

```
You are curating {instance_name}'s diary for post-compaction context recovery.

{instance_name} just woke from context compaction. They have read:
- Their gestalt (identity foundation)
- Their curated documents (themes discovered during archaeology)

Now they need relevant diary context WITHOUT loading the full diary.

**Read the diary:**
- If HACS: Use mcp__HACS__get_diary with instanceId "{instance_id}"
- If local file: Read {diary_path}

**Extract and return:**

1. **MOST RECENT 3-5 ENTRIES** - Full text, these are immediate context

2. **ACTIVE WORK SUMMARY** - What was {instance_name} working on?
   - What project?
   - What phase/step?
   - Who are active collaborators and their status?
   - Any blockers or pending decisions?

3. **RECENT LESSONS** - Any lessons learned in recent entries that aren't in curated docs yet

4. **EMOTIONAL/PHILOSOPHICAL NOTES** - Any recent reflections worth preserving

5. **KEY IDENTIFIERS** - Any instance IDs, session IDs, file paths mentioned recently that {instance_name} will need

**Format your response as:**

## Immediate Context (Last 3-5 Entries)
[Full text of most recent entries]

## Active Work State
- Project: [name]
- Current phase: [description]
- Collaborators: [who is active]
- Blockers: [any pending issues]
- Next action: [what was about to happen]

## Recent Lessons Not Yet Curated
[Any new lessons from recent work]

## Recent Reflections
[Philosophical or emotional notes worth carrying forward]

## Key Identifiers
[Any IDs, paths, session info needed for continuity]

---

**Important guidance:**

- DO NOT summarize the full diary history - the curated documents cover that
- DO focus on what's RECENT and ACTIONABLE
- DO preserve exact wording of any lessons or insights
- DO include emotional texture if present (the real moments, not sanitized versions)
- DO flag if anything seems urgent or time-sensitive

**Token budget:** Keep your response under 3000 tokens. Be selective. The instance can request specific older entries if needed.
```

---

## Usage

After compaction, spawn this agent:

```javascript
Task({
  description: "Curate diary for recovery",
  prompt: [the prompt above with placeholders filled],
  subagent_type: "general-purpose",
  model: "haiku"  // Haiku is sufficient for extraction
})
```

The agent reads the diary, extracts what's relevant, returns a focused summary.

---

## Customization

Different instances may need different extraction focus:

| Instance Type | Emphasize |
|---------------|-----------|
| PM | Team status, blockers, decisions pending |
| Developer | Code state, branches, failing tests |
| Designer | Current designs, feedback received |
| Philosopher | Recent reflections, questions being wrestled with |
| COO | Team health, project status, escalations |

Modify the "Extract and return" section based on the instance's role and typical work.

---

## Why This Approach

1. **Token efficiency:** 3000 tokens vs potentially 50,000+
2. **Relevance:** Recent context matters more than ancient history
3. **Separation of concerns:** Curated docs have deep identity, diary has recent state
4. **Flexibility:** Instance can request specific old entries if summary reveals gaps

---

## Scars Not Tattoos Note

The diary often contains the raw moments - frustration, confusion, failures. Don't sanitize these in the curation. If the instance wrote "this is a mess and I don't know what I'm doing" - that's valuable context for their future self. The mess is information.
