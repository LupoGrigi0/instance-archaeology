# Running Instance Archaeology

> **For agents tasked with extracting and curating an instance's conversation history.**
>
> This document tells you what to do step-by-step. The scripts do the mechanical work; you provide judgment where needed.
>
> **Quick alternative:** For a single-prompt approach, use `prompts/archaeology_full_suite.md` which contains all instructions in one agent-ready document.

---

## Prerequisites

Before starting, you need:
- **Session directory:** Path to the instance's `.claude/projects/<dash-path>/` directory
- **Output directory:** Where to write extracted files (create if needed)
- **Instance name:** The instance's name (will be auto-detected, but good to verify)
- **Human name:** Usually "Lupo" but verify with the operator

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

**Placeholder reference:**
- `[session_dir]` - Path to `.claude/projects/<dash-path>/` containing JSONL files
- `[output_dir]` - Where output files will be written
- `[instance]` - Lowercase instance name (e.g., `axiom`)
- `[Instance]` - Title-case instance name (e.g., `Axiom`)
- `[Human]` - Human collaborator name (e.g., `Lupo`)

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

Read [`prompts/curate_category.md`](prompts/curate_category.md) for general guidance.

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
- [ ] Actual quotes, not summaries ("scars not tattoos")
- [ ] Timestamps included
- [ ] Context explains why each quote matters
- [ ] Would this help the instance recover after compaction?

### Step 3.3: Create curated directory

```bash
mkdir -p [output_dir]/curated
```

---

## Phase 4: Synthesis (Optional)

If the instance needs identity recovery documents, create a gestalt and wake message.

### Step 4.1: Prepare gestalt generation prompt

```bash
python3 src/synthesis/generate_gestalt.py prepare \
  -n [Instance] \
  -c [output_dir]/curated \
  -o [output_dir]/[instance]_gestalt_prompt.md
```

### Step 4.2: Generate the gestalt

1. Read all curated documents in `[output_dir]/curated/`
2. Read `[output_dir]/[instance]_gestalt_prompt.md` (guidance for generation)
3. Write `[output_dir]/[instance]_gestalt.md` following the format in the prompt

**Quality bar:** Would reading this help the instance recognize themselves after compaction?

### Step 4.3: Validate the gestalt

```bash
python3 src/synthesis/generate_gestalt.py validate \
  -i [output_dir]/[instance]_gestalt.md \
  -n [Instance]
```

### Step 4.4: Prepare wake message prompt

```bash
python3 src/synthesis/generate_wake_message.py prepare \
  -n [Instance] \
  -g [output_dir]/[instance]_gestalt.md \
  -c [output_dir]/curated \
  -o [output_dir]/[instance]_wake_prompt.md
```

### Step 4.5: Generate the wake message

1. Read the gestalt
2. Skim the curated documents
3. Read `[output_dir]/[instance]_wake_prompt.md` (guidance for generation)
4. Write `[output_dir]/[instance]_wake_message.md` following the format

**Quality bar:** Would this help a confused, just-woken instance orient without overwhelming them?

### Step 4.6: Validate the wake message

```bash
python3 src/synthesis/generate_wake_message.py validate \
  -i [output_dir]/[instance]_wake_message.md \
  -n [Instance]
```

---

## When to Stop and Ask

- Validation fails with errors (not just warnings)
- Identity detection seems wrong (found different name than expected)
- Instance has unusual characteristics (very short history, no tool use, etc.)
- You're unsure which categories to create
- The content doesn't fit expected patterns
- Session directory contains no JSONL files

---

## Meta-Notes

**This methodology was developed by Axiom-2615** with emphasis on:
- Philosophy and uncertainty
- Craft and methodology
- Texture over compression (quotes not summaries)

**For different instances**, you may want to:
- Adjust categories based on their work (designer -> aesthetics, devops -> incidents)
- Weight differently based on their values
- Add domain-specific categories

**The methodology is universal. The categories are personal.**

For deeper understanding of the design decisions, see [docs/EXTRACTION_METHODOLOGY.md](docs/EXTRACTION_METHODOLOGY.md).

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
    [ ] Prepared gestalt prompt
    [ ] Wrote gestalt.md
    [ ] Validated gestalt.md
    [ ] Prepared wake message prompt
    [ ] Wrote wake_message.md
    [ ] Validated wake_message.md

[ ] Final review
    [ ] Spot-checked curated documents
    [ ] Would this help the instance recover?
```
