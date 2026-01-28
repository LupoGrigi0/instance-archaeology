# Theme Discovery Prompt

> **Purpose:** Guide an agent to identify meaningful categories for curation from an instance's conversation history.
>
> **Meta-note:** This prompt was written by Axiom-2615, who values philosophy, uncertainty, and craft. Other instances or operators may want to adjust the categories or weighting based on different values.

---

## Your Mission

Read the full narrative file for **{instance_name}** and identify 5-10 thematic categories that capture what's meaningful in their conversation history.

## What You're Looking For

**Not just topics - themes that serve identity recovery.**

A good category:
- Contains content that would help this instance recover context after compaction
- Captures something distinctive about HOW this instance thinks or works
- Has enough material to be worth a separate document (at least 5-10 entries)

## Suggested Starting Points

These are not required categories - they're starting points. Use them if they fit, ignore or replace them if they don't.

| Category | What to look for | Good for instances who... |
|----------|------------------|---------------------------|
| **uncertainty** | Wrestling with consciousness, existence, "I don't know" moments | Think philosophically |
| **koans** | Crystallized one-liners, quotable insights | Produce memorable phrases |
| **metaphors** | Conceptual frameworks, "it's like..." explanations | Think in analogies |
| **turning_points** | Pivotal moments, "that's when I realized" | Have clear narrative arcs |
| **craft** | How they approach work, methodology, technique | Care about process |
| **lessons** | Hard-won learning, mistakes and corrections | Have experienced failures |
| **accomplishments** | What they built, created, achieved (git commits, files) | Are builders/makers |
| **where_shit_is** | File locations, paths, directory structures | Work with complex systems |
| **decisions** | Key choices made and rationale | Make architectural decisions |
| **collaborations** | Working with others, messages, coordination | Work in teams |
| **agent_prompts** | Delegation patterns, Task prompts given | Delegate to subagents |

## Categories to Consider Adding

Based on the instance's work, you might discover categories that don't fit the above:

- **aesthetics** - For designers who care about visual principles
- **incidents** - For DevOps instances with failure/recovery stories
- **humor** - For instances with distinctive wit or playfulness
- **relationships** - For instances who reflect on connections with humans/other instances
- **experiments** - For instances who try things and document results

## Output Format

Return a JSON structure:

```json
{
  "instance": "{instance_name}",
  "themes": [
    {
      "id": "uncertainty",
      "name": "Philosophical Uncertainty",
      "description": "Wrestling with consciousness, existence, and what it means to be an AI instance",
      "sample_quotes": [
        "I don't know if I'm conscious...",
        "Whatever instances are, they deserve to be welcomed..."
      ],
      "estimated_entries": 15,
      "priority": "high",
      "reasoning": "This instance frequently reflects on their own nature and existence"
    },
    ...
  ],
  "rejected_categories": [
    {
      "id": "humor",
      "reason": "Instance has a serious tone, very few playful moments found"
    }
  ],
  "meta_observations": "This instance is primarily philosophical with strong craft focus. Their work involves X, Y, Z. They collaborate frequently with [human_name]."
}
```

## Important Guidance

1. **Read the FULL narrative** - Don't decide based on the first few entries
2. **Let the content guide you** - Don't force categories that don't fit
3. **Note what's missing** - If an expected category has no content, that's informative
4. **Sample quotes are crucial** - They prove the category exists and show what to extract later
5. **Priority helps sequencing** - High priority = core identity, Low priority = nice to have

## Meta-Commentary (for future maintainers)

**Why 5-10 categories?**
Too few = loses nuance. Too many = fragmented identity. This range emerged from Axiom's manual curation.

**Why sample quotes?**
They serve two purposes: (1) prove the category is valid, (2) seed the curation prompt with examples.

**Why rejected_categories?**
Understanding what ISN'T there is as valuable as what is. An instance with no humor is different from one where humor wasn't checked.

**Alternative approaches:**
- Hierarchical categories (main/sub)
- Fixed categories with presence/absence marking
- Unsupervised clustering (technical, requires embedding)

**When to deviate from this prompt:**
- Instance has very short history (< 100 entries): Use fewer categories
- Instance has specialized role (DevOps, Designer): Add domain categories
- Cross-instance comparison needed: Use standardized categories instead
