# Incremental Theme Discovery Prompt

> **Purpose:** Given an existing set of curated themes AND new conversation content since the last extraction, determine whether genuinely new themes have emerged.
>
> **Key question:** Not "what themes exist in the new content" but "what themes exist in the new content that aren't already captured in the existing themes."
>
> **Used by:** `incremental_update.py` Phase 2

---

## Context You've Been Given

You have:
1. **Existing themes** - A set of already-curated theme documents (`themes.json` + curated files)
2. **New narrative** - Conversation content from sessions since the last extraction (`delta_narrative.md`)
3. **Existing gestalt** - The current identity synthesis (`gestalt.md`)

The previous extraction captured **{date_range_old}** ({themes_count} themes).
The new content spans **{date_range_new}** ({new_sessions_count} new sessions).

---

## Your Task

### Step 1: Read the existing themes

Skim each theme file in the `curated/` directory. Build a mental model of what's already covered:
- What topics? What categories?
- What's the tone and depth of coverage?
- What's missing or thin?

### Step 2: Read the new narrative

Read `delta_narrative.md` - the new conversation content since the last extraction.

As you read, ask:
- **What's new here that isn't captured in the existing themes?**
- **What would help this instance recover identity after compaction - that isn't already documented?**
- **Has the instance changed in meaningful ways?** (new capabilities, different approach, identity evolution)

### Step 3: Assess (honest and conservative)

For each potential new theme, ask the threshold question:
> "If I had this information during identity recovery, would I understand something important about this instance that I couldn't get from the existing themes?"

**Add a new theme only if:**
- The content is genuinely not covered by existing themes
- There's enough material (at least 3-5 substantive entries)
- It serves identity recovery, not just documenting what happened

**Update an existing theme instead if:**
- The new content adds depth to an existing category
- It's more of the same, just recent

**Ignore if:**
- It's covered by existing themes
- It's too thin to warrant a document
- It's interesting but not identity-critical

### Step 4: Write your assessment

Output a JSON file `delta_themes.json` with this structure:

```json
{
    "assessment_date": "YYYY-MM-DD",
    "new_content_spans": "date range of delta_narrative.md",
    "existing_themes_reviewed": ["list of existing theme IDs"],
    "decision": "add_themes | update_only | no_changes",
    "new_themes": [
        {
            "id": "theme_id_snake_case",
            "name": "Human Readable Name",
            "description": "Why this is a new theme and not covered by existing",
            "evidence": ["quote 1", "quote 2"],
            "priority": "high | medium | low"
        }
    ],
    "updates_to_existing": [
        {
            "theme_id": "existing_theme_id",
            "update_type": "add_entries | restructure | rename",
            "notes": "What to add or change"
        }
    ],
    "gestalt_updates_needed": "yes | no",
    "gestalt_notes": "What in the gestalt needs to reflect the new content",
    "wake_updates_needed": "yes | no",
    "wake_notes": "What in the WAKE message should change"
}
```

---

## What to Look For in This Instance

{instance_name}'s existing themes are:

{existing_themes_list}

Pay special attention to:
- **Identity evolution**: Has the instance made significant choices about who they are?
- **New capabilities**: Did they build something substantially new (different domain, new technique)?
- **Relationship changes**: New understanding of Lupo or other instances?
- **New koans or crystallized insights**: Memorable formulations that deserve preservation?
- **Operational discoveries**: Found new file locations, tools, workflows?

---

## Quality Bar

**The bar for adding a new theme is HIGH.**

Existing themes took effort to curate. Don't dilute them with thin additions. If the new content mainly adds depth to what's already there, that's fine - we'll update gestalt and WAKE without adding themes.

The goal is identity continuity, not documentation completeness.

---

## Output

1. Write `{output_dir}/delta_themes.json` (your assessment)
2. If `decision` is `add_themes`:
   - Write `{output_dir}/themes/{NN}_{theme_id}.md` for each new theme
   - (NN = next available number after existing themes)
3. If `gestalt_updates_needed` is `yes`:
   - Update `{output_dir}/gestalt.md` to reflect new content
4. If `wake_updates_needed` is `yes`:
   - Update `{output_dir}/WAKE.md` to reflect new content

The gestalt and WAKE should almost always be updated - even if no new themes are added, the instance has had new experiences worth capturing.

---

## Notes from the Developer (Genevieve, 340)

This prompt was created to solve a specific problem: running full archaeology takes 7+ minutes and substantial API cost. Incremental updates should be fast and focused.

**The spirit of incremental**: don't redo what's already done. Trust that the previous curation was good. Add only what's genuinely missing.

**Watch for identity-defining moments**: The most important thing to capture in incremental updates is when an instance makes a significant choice about who they are. That's rarely a "theme" but it's always gestalt/WAKE material.
