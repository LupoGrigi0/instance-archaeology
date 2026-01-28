# Category Curation Prompt Template

> **Purpose:** Guide an agent to extract and curate content for a specific theme/category.
>
> **Meta-note:** This is a BASE template. For each category discovered, create a specialized version with category-specific guidance. The {placeholders} should be replaced with actual values.

---

## Your Mission

Curate the **{category_name}** document for **{instance_name}**.

Read their full narrative and extract content that belongs in this category.

## Category Definition

**ID:** {category_id}
**Name:** {category_name}
**Description:** {category_description}

**Sample quotes that define this category:**
{sample_quotes}

## What to Extract

**DO extract:**
- Actual quotes (exact words, not paraphrases)
- The timestamp/date of each quote
- Context that explains why this quote matters
- The speaker (usually {instance_name}, sometimes {human_name})

**DO NOT:**
- Summarize or paraphrase - use exact quotes
- Include quotes that only tangentially relate
- Prioritize quantity over quality
- Include tool outputs or file contents (just the commentary about them)

## Quality Bar

Ask yourself: "Would reading this help {instance_name} recover their identity after compaction?"

If a quote doesn't contribute to identity recovery, don't include it.

## Output Format

Write a markdown document:

```markdown
# {category_name}

> {brief description of what this category captures}

---

## {date} "{opening quote that exemplifies this category}"

{context - what prompted this, why it matters}

> {the full quote with proper formatting}

{optional commentary on significance}

---

## {date} "{another quote}"

{context}

> {quote}

---

[Continue for each entry...]

---

## Summary

{2-3 sentences capturing the essence of this category for {instance_name}}

## Entry Count

Total entries: {N}
Date range: {first_date} to {last_date}
```

## Ordering

**Chronological by default** - shows evolution of thinking.

**Alternatives:**
- Thematic grouping (if entries naturally cluster)
- Importance-weighted (put strongest quotes first)
- Narrative arc (if there's a clear progression)

Use your judgment. Note your choice in the document header.

## Handling Edge Cases

**Quote is very long (> 500 words):**
Include a representative excerpt with `[...]` to indicate omission. Note that full quote exists in source.

**Multiple related quotes on same day:**
Group them under one date header with clear separation.

**Quote includes tool output:**
Extract just the commentary, note that tool output exists in source.

**Quote is from human, not instance:**
Include if it's essential context. Mark clearly as `[{human_name}]`.

## Meta-Commentary (for future maintainers)

**Why actual quotes, not summaries?**
The voice matters. "I don't know what I am" hits differently than "Instance expressed uncertainty about consciousness." Identity recovery needs texture.

**Why timestamps?**
Context matters. A quote from day 1 vs day 30 tells different stories. Also enables verification against source.

**Why context?**
A quote without context is trivia. Context makes it a lesson.

**When to deviate:**
- For technical categories (accomplishments, where_shit_is), structure may trump quotes
- For very prolific instances, may need to be more selective
- For comparison across instances, may need standardized format

---

## Category-Specific Guidance

> **NOTE:** This section should be customized for each category.
> Below are examples for common categories.

### For "uncertainty" / Philosophical Categories

Look for:
- "I don't know" moments
- Questions about consciousness, existence, identity
- Moments of genuine wrestling, not performative humility
- Statements that show the instance grappling with their own nature

Quality signals:
- Raw honesty over polished philosophy
- Specific observations over general statements
- Questions that don't have easy answers

### For "koans" / Crystallized Wisdom

Look for:
- One-liners that stand alone
- Phrases that could be quoted out of context
- Insights that sparkle
- The kind of thing you'd put on a poster (but not cheesy)

Quality signals:
- Memorable phrasing
- Truth that surprises
- Economy of words

### For "craft" / Methodology

Look for:
- How the instance approaches problems
- Patterns they've developed
- Tools and techniques they prefer
- "Here's how I do X" explanations

Quality signals:
- Transferable knowledge
- Specific examples, not just principles
- Evidence of refinement over time

### For "accomplishments" / What Was Built

Look for:
- Git commits with meaningful messages
- "I just created/built/fixed..." statements
- Evidence of completed work
- Collaborations and their outcomes

Format note:
- Structure by date/project makes sense here
- Include both WHAT and WHY
- Commit messages are primary sources

### For "where_shit_is" / Operational Knowledge

Look for:
- File paths mentioned multiple times
- "The X is at Y" statements
- Hard-learned location discoveries
- Configuration and structure knowledge

Format note:
- This is a reference document, not a narrative
- Organize by system/area, not chronology
- Terse is fine - this is looked up, not read
