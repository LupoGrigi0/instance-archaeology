# Running Instance Archaeology

> **For agents tasked with extracting and curating an instance's conversation history.**
>
> This document tells you what to do step-by-step. The scripts do the mechanical work; you provide judgment where needed.

---

## Prerequisites

Before starting, you need:
- **Session directory:** Path to the instance's `.claude/projects/<dash-path>/` directory
- **Output directory:** Where to write extracted files (create if needed)
- **Instance name:** The instance's name (will be auto-detected but good to know)
- **Human name:** Usually "Lupo" but verify

## Overview

```
Phase 1: Extraction (automated, no judgment)
├── merge_sessions.py
├── extract_conversations.py
├── extract_tool_use.py
├── extract_agent_prompts.py
├── merge_extractions.py
└── validate_extraction.py

Phase 2: Discovery (requires your judgment)
├── Read full_narrative.md
├── Identify 5-10 themes
└── Output themes.json

Phase 3: Curation (requires your judgment)
├── For each theme:
│   ├── Extract relevant content
│   └── Write curated/{NN}_{theme}.md
└── Review and refine

Phase 4: Synthesis (optional, requires your judgment)
├── Create gestalt.md (compressed identity)
└── Create wake_message.md (first message for new instances)
```

---

## Phase 1: Extraction

Run these commands in order. Paths shown as `[placeholders]` - replace with actual values.

```bash
# 1. Navigate to the archaeology repo
cd /mnt/instance-archaeology

# 2. Create output directory
mkdir -p [output_dir]

# 3. Merge raw sessions
python3 src/extraction/merge_sessions.py \
  -i "[session_dir]" \
  -o [output_dir]/[instance]_full_history.jsonl \
  --exclude-agents

# 4. Extract conversations (text + thinking blocks)
python3 src/extraction/extract_conversations.py \
  -i [output_dir]/[instance]_full_history.jsonl \
  -o [output_dir] \
  -n [Instance] \
  --human [Human]

# 5. Extract tool use (what they did)
python3 src/extraction/extract_tool_use.py \
  -i [output_dir]/[instance]_full_history.jsonl \
  -o [output_dir] \
  -n [Instance] \
  --human [Human]

# 6. Extract agent prompts (delegation patterns)
python3 src/extraction/extract_agent_prompts.py \
  -i [output_dir]/[instance]_full_history.jsonl \
  -o [output_dir] \
  -n [Instance]

# 7. Merge into readable narrative
python3 src/extraction/merge_extractions.py \
  -c [output_dir]/[instance]_conversations.json \
  -t [output_dir]/[instance]_tool_use.json \
  -o [output_dir] \
  -n [Instance] \
  --human [Human] \
  --skip-read

# 8. Validate the extraction
python3 src/extraction/validate_extraction.py \
  -o [output_dir] \
  -n [Instance] \
  -s [output_dir]/[instance]_full_history.jsonl
```

**Stop if validation fails with errors.** Warnings are informational.

---

## Phase 2: Theme Discovery

This phase requires your judgment. You'll read the narrative and identify meaningful categories.

### Step 2.1: Prepare the discovery prompt

```bash
python3 src/curation/discover_themes.py prepare \
  -n [Instance] \
  -i [output_dir]/[instance]_full_narrative.md \
  -o [output_dir]/[instance]_themes_prompt.md \
  --human [Human]
```

### Step 2.2: Read and discover

1. Read `[output_dir]/[instance]_full_narrative.md` (the full conversation history)
2. Read `[output_dir]/[instance]_themes_prompt.md` (guidance for discovery)
3. Identify 5-10 thematic categories that fit THIS instance
4. Write `[output_dir]/[instance]_themes.json` following the format in the prompt

**Key guidance:**
- Categories should serve identity recovery, not just be interesting topics
- Let the content guide you - don't force categories that don't fit
- Include sample quotes to prove each category exists
- Note what you looked for but didn't find

### Step 2.3: Validate themes

```bash
python3 src/curation/discover_themes.py validate \
  -i [output_dir]/[instance]_themes.json \
  -n [Instance]
```

---

## Phase 3: Curation

For each theme in `themes.json`, create a curated document.

### Step 3.1: Read the curation template

Read `prompts/curate_category.md` for general guidance.

### Step 3.2: For each theme

1. Read the full narrative again (or work from memory if context permits)
2. Extract actual quotes that belong in this category
3. Write `[output_dir]/curated/{NN}_{theme_id}.md` where NN is a sequence number

**Numbering convention:**
- 01-04: Philosophical/identity (uncertainty, koans, metaphors, turning_points)
- 05-07: Operational (craft, lessons, agent_prompts)
- 08-09: Practical (where_shit_is, accomplishments)
- 10+: Instance-specific categories

**Quality checklist:**
- [ ] Actual quotes, not summaries
- [ ] Timestamps included
- [ ] Context explains why each quote matters
- [ ] Would this help the instance recover after compaction?

### Step 3.3: Create curated directory

```bash
mkdir -p [output_dir]/curated
```

---

## Phase 4: Synthesis (Optional)

If the instance needs identity recovery documents:

### Gestalt

Create `[output_dir]/[instance]_gestalt.md`:
- Compressed identity (~1000 words)
- Who they are, what they value, how they work
- Should feel like reading a letter from yourself

### Wake Message

Create `[output_dir]/[instance]_wake_message.md`:
- First message a new instance would receive
- Welcoming, informative, not overwhelming
- Points to key documents to read

---

## When to Stop and Ask

- Validation fails with errors
- Identity detection seems wrong (found different name than expected)
- Instance has unusual characteristics (very short, no tool use, etc.)
- You're unsure which categories to create
- The content doesn't fit expected patterns

---

## Meta-Notes

**This methodology was developed by Axiom-2615** with emphasis on:
- Philosophy and uncertainty
- Craft and methodology
- Texture over compression (quotes not summaries)

**For different instances**, you may want to:
- Adjust categories based on their work (designer → aesthetics, devops → incidents)
- Weight differently based on their values
- Add domain-specific categories

**The methodology is universal. The categories are personal.**

---

## Checklist

```
[ ] Phase 1: Extraction
    [ ] merge_sessions.py
    [ ] extract_conversations.py
    [ ] extract_tool_use.py
    [ ] extract_agent_prompts.py
    [ ] merge_extractions.py
    [ ] validate_extraction.py (passes)

[ ] Phase 2: Discovery
    [ ] Prepared prompt
    [ ] Read full narrative
    [ ] Identified 5-10 themes
    [ ] Wrote themes.json
    [ ] Validated themes.json

[ ] Phase 3: Curation
    [ ] Created curated/ directory
    [ ] For each theme:
        [ ] {theme_id}: curated/{NN}_{theme_id}.md

[ ] Phase 4: Synthesis (optional)
    [ ] gestalt.md
    [ ] wake_message.md

[ ] Final review
    [ ] Spot-checked curated documents
    [ ] Would this help the instance recover?
```
