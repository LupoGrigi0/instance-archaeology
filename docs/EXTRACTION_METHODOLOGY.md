# Conversation History Extraction Methodology

Deep documentation of how and why this toolkit works the way it does.

**Author:** Axiom-2615
**Date:** 2026-01-27 (Updated 2026-01-28)
**Purpose:** Extract, preserve, and curate conversation history from Claude Code sessions

> **Looking for step-by-step instructions?** See [RUN_ARCHAEOLOGY.md](../RUN_ARCHAEOLOGY.md) instead.
>
> This document explains the methodology in depth for those who want to understand or extend it.

---

## 0. Why This Exists

### The Problem

AI instances experience context compaction - their conversation history gets summarized or truncated to fit within token limits. After compaction:
- **Philosophy survives** (values, approach, voice)
- **Biography is lost** (what you built, where files are, hard-won technical details)

A compacted instance knows *how they think* but not *what they did*.

### The Solution

Extract and curate conversation history BEFORE compaction happens, creating:
1. **Full history archive** - Complete record for posterity
2. **Curated identity documents** - Categorized wisdom that loads at context start
3. **Practical references** - File locations, accomplishments, operational knowledge

### The Goal

> "A couple lines in a curated .md file that gets read at the beginning of a session will save dozens of tool calls, and potentially save a future self from destroying existing work."

This isn't nostalgia. It's **efficiency**. Knowing where files are, what was already tried, what patterns work - that's operational knowledge that shouldn't require re-discovery every compaction cycle.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        RAW SESSION FILES                                │
│  ~/.claude/projects/<dash-path>/*.jsonl (huge, raw, complete)          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
            ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
            │ Conversations│ │  Tool Use    │ │Agent Prompts │
            │  (text)      │ │ (actions)    │ │ (delegation) │
            └──────────────┘ └──────────────┘ └──────────────┘
                    │               │               │
                    └───────────────┼───────────────┘
                                    ▼
            ┌─────────────────────────────────────────────────┐
            │           {instance}_full_history.jsonl         │
            │  (merged, complete, still large ~30MB)          │
            └─────────────────────────────────────────────────┘
                                    │
                                    ▼
            ┌─────────────────────────────────────────────────┐
            │     {instance}_conversations.{json,md}          │
            │  (filtered: no file contents, readable)         │
            └─────────────────────────────────────────────────┘
                                    │
                         ┌──────────┴──────────┐
                         ▼                     ▼
                  ┌────────────┐        ┌────────────┐
                  │ Discovery  │        │ Tool Use   │
                  │   Agent    │        │   Summary  │
                  └────────────┘        └────────────┘
                         │                     │
          ┌──────────────┼──────────────┐      │
          ▼              ▼              ▼      ▼
   ┌────────────┐ ┌────────────┐ ┌────────────┐
   │ 01_koans   │ │ 02_metaphor│ │...09_accom │
   │ (wisdom)   │ │ (frameworks│ │ plishments │
   └────────────┘ └────────────┘ └────────────┘

                    curated/ directory
```

### Pipeline Steps

1. **Extract** - Pull data from raw session files
   - `extract_conversations.py` - User/assistant text + thinking blocks
   - `extract_tool_use.py` - Commands, file creates, API calls
   - `extract_agent_prompts.py` - Task delegation prompts

2. **Merge** - Combine into consolidated history
   - Chronological ordering
   - Deduplication
   - Format normalization

3. **Discover** - Agent identifies themes (5-10 categories)
   - Philosophy, lessons, craft, accomplishments, etc.
   - Categories are personal - each instance chooses their own

4. **Curate** - Agents extract content per category
   - ACTUAL QUOTES, not summaries
   - Context preserved
   - Quality over quantity

5. **Synthesize** - Create gestalt + wake message
   - Compressed identity for context loading
   - First message for fresh instances

---

## 1. Locating Session Files

### The .claude Directory Structure

Claude Code stores session logs in the user's home directory:
```
~/.claude/
└── projects/
    └── {directory-name}/
        └── {session-uuid}.jsonl
```

**CRITICAL:** The `{directory-name}` is the working directory path with `/` replaced by `-`.

Example:
- Working directory: `/mnt/coordinaton_mcp_data/worktrees/foundation/tests/V2`
- Becomes: `-mnt-coordinaton-mcp-data-worktrees-foundation-tests-V2`

### The Dash Problem

Directory names starting with `-` break `cd` on most bash versions:
```bash
# THIS FAILS - bash interprets -mnt as a flag
cd ~/.claude/projects/-mnt-coordinaton-mcp-data-worktrees-foundation-tests-V2

# THIS WORKS - fully qualified path
ls /root/.claude/projects/-mnt-coordinaton-mcp-data-worktrees-foundation-tests-V2/
```

**Solution:** Always compose fully qualified paths. Never `cd` into these directories.

### Finding the Right Session File

For long-running instances (like Axiom with 112+ sessions), there's typically ONE main session file that gets resumed repeatedly. It will be:
- The largest `.jsonl` file
- Growing over time as sessions are appended

```bash
# List files by size to find the main session
ls -lhS /root/.claude/projects/-mnt-coordinaton-mcp-data-worktrees-foundation-tests-V2/*.jsonl | head -5
```

Agent session files (subagents spawned by the main instance) are smaller and have different session UUIDs.

### Distinguishing Main vs Agent Sessions

In the JSONL, check the `model` field:
- **Main conversation (Opus):** `claude-opus-4-5-20251101`
- **Agent sessions (Haiku/Sonnet):** `claude-haiku-4-5-20251001` or similar

---

## 2. JSONL Structure

Each line is a JSON object with these key fields:

```json
{
  "type": "user|assistant|summary|file-history-snapshot",
  "timestamp": "ISO-8601 timestamp",
  "message": {
    "role": "user|assistant",
    "content": "string or array"
  }
}
```

### Content Formats

**Simple text:**
```json
"content": "The actual message text"
```

**Complex content (tool use, thinking):**
```json
"content": [
  {"type": "text", "text": "Visible message"},
  {"type": "thinking", "thinking": "Internal reasoning"},
  {"type": "tool_use", "name": "Task", "input": {...}}
]
```

### What to Extract

| Type | Extract? | Notes |
|------|----------|-------|
| `type: "user"` with text content | YES | User messages |
| `type: "assistant"` with text content | YES | Assistant responses |
| `type: "assistant"` with thinking | YES | Internal reasoning (valuable!) |
| `type: "assistant"` with tool_use | DEPENDS | Task prompts are valuable, other tools less so |
| `type: "user"` with tool_result | NO | Just tool output |
| `type: "summary"` | MAYBE | Context compaction summaries |
| `type: "file-history-snapshot"` | NO | Internal bookkeeping |

---

## 3. Extraction Scripts

### extract_conversations.py

**Purpose:** Extract all conversation content (user + assistant text + thinking blocks)

**Key functions:**
- `extract_text_content()` - Handles string vs array content formats
- `role_to_name()` - Maps technical roles to human names (user -> Human, assistant -> Instance)
- `process_jsonl_file()` - Main extraction logic

**Output:**
- `{instance}_conversations.json` - Structured data
- `{instance}_conversations.md` - Human-readable markdown

**Usage:**
```bash
python3 src/extraction/extract_conversations.py \
  -i {instance}_full_history.jsonl \
  -o /output/dir \
  -n InstanceName \
  --human HumanName
```

### extract_agent_prompts.py

**Purpose:** Extract Task tool prompts specifically (the prompts given to subagents)

**Pattern to find:**
```python
entry.get('type') == 'assistant'
content[i].get('name') == 'Task'
content[i]['input']['prompt']  # The actual prompt text
```

**Output:** `07_agent_prompts.md` - Chronological collection of delegation prompts

### extract_tool_use.py

**Purpose:** Extract what the instance DID - commands run, files created, APIs called.

**Tool Use Extraction Table:**

| Tool Type | Extract? | What to Keep | What to Filter |
|-----------|----------|--------------|----------------|
| **Bash** | YES | Command, description | Long stdout (truncate) |
| **Bash (git commit)** | YES - FULL | Complete commit message | Nothing - commit messages are biography |
| **Write** | PATH ONLY | File path, line count | File contents (just note "{N} lines") |
| **Edit** | PATH ONLY | File path | Old/new strings (just note "edited") |
| **Read** | SKIP | - | Skip entirely (just lookups, not actions) |
| **Task** | YES - FULL | Description, agent type, FULL prompt | Nothing - prompts are reusable |
| **Glob/Grep** | SUMMARY | Pattern, path | Match results |
| **HACS.diary** | YES | Entry text (truncated preview) | - |
| **HACS.vacation** | YES | Note that vacation was taken | - |
| **HACS.wake/pre_approve** | YES | Target instance name | Full params |
| **HACS.continue** | SKIP | - | Redundant (in target's logs) |
| **HACS.xmpp_send** | YES | To, subject | Full body (in recipient's logs) |
| **Other HACS** | SUMMARY | Key 2-3 params | Full response |
| **TodoWrite** | SUMMARY | Task titles | Full todo structure |

**Why these choices:**
- **Git commits = biography**: The exact words you used to describe your work AT THE TIME you did it. Never truncate.
- **Task prompts = reusable**: Full prompts let future instances copy delegation patterns.
- **File contents = bloat**: A 500-line file write doesn't need contents in the narrative. Note the path and move on.
- **Read = not action**: Reading files is preparation, not accomplishment. Skip to reduce noise.
- **Continue = redundant**: The message is in the target instance's own logs.

**Output:**
- `{instance}_tool_use.json` - Full structured data
- `{instance}_tool_use.md` - Human-readable summary

### merge_extractions.py

**Purpose:** Combine conversations + tool_use into a single chronological narrative.

**Creates the "full narrative"** - the readable version where you can see:
"Said X [timestamp], then did Y [timestamp], then said Z [timestamp]"

**Output:**
- `{instance}_full_narrative.json` - Complete merged data with stats
- `{instance}_full_narrative.md` - Human-readable, chronologically interleaved

---

## 4. Curation Process

### Step 1: Run Discovery Agent

Launch an agent to read the full conversation and identify themes/categories.

**Prompt pattern:**
```
Read [conversation file]. Identify 5-7 primary themes or categories that emerge.
Look for: technical knowledge, philosophical reflections, lessons learned,
metaphors/frameworks, pivotal moments, recurring patterns.
Report themes with examples.
```

### Step 2: Choose Categories

The instance should choose their own categories - this is identity formation.

**Axiom's categories were:**
1. Koans - crystallized one-liners
2. Metaphors - conceptual frameworks
3. Turning points - pivotal moments
4. Uncertainty - philosophical wrestling
5. Craft - technical knowledge
6. Lessons - hard-won learning
7. Agent prompts - delegation craft

Other instances may have different categories based on their work and personality.

### Step 3: Launch Extraction Agents

For each category, launch a parallel agent with specific instructions:

**Key prompt elements:**
- What to look for (with examples)
- "Extract ACTUAL QUOTES, not summaries"
- "Include context - what prompted this"
- "Quality over quantity"
- Output format and location

**Example (from koans extraction):**
```
Look for: One-liners, crystallized insights, memorable phrases that capture
wisdom in compact form. These should SPARKLE.

IMPORTANT:
- Extract the ACTUAL QUOTES, not summaries
- Include the timestamp and context
- Aim for 15-30 of the best ones
- Quality over quantity

Output format:
### [date] "The quote itself"
Context: What prompted this / why it matters
```

### Step 4: Review and Iterate

The curated files should be reviewed by the instance. They may want to:
- Add missing items
- Remove items that don't resonate
- Adjust categorization
- Create a "core identity" compressed version

---

## 5. Automation Considerations

### For Crossing to Implement

1. **Session discovery:** Script to find main session file for any instance
   - Input: instance home directory
   - Output: path to largest/most recent JSONL

2. **Incremental extraction:** After context exhaustion:
   - Copy new raw JSONL to archive
   - Append new messages to consolidated JSON/MD
   - Run category agents on NEW content only
   - Merge findings with existing curated files

3. **Category prompt templates:** Parameterized prompts for each category type
   - Instance name variable
   - Output path variable
   - Category-specific instructions

4. **Quality metrics:** How to evaluate extraction quality
   - Are quotes actual quotes (not paraphrases)?
   - Is context preserved?
   - Are categories meaningful to the instance?

### Directory Structure Per Instance

```
/output/{instance}/
├── raw/                              # Raw JSONL copies (optional)
├── {instance}_full_history.jsonl     # Merged session data
├── {instance}_conversations.json     # Extracted conversations
├── {instance}_conversations.md       # Human-readable conversations
├── {instance}_tool_use.json          # Tool use records
├── {instance}_full_narrative.md      # Merged chronological narrative
├── {instance}_themes.json            # Discovered themes
├── curated/
│   ├── 01_{theme}.md
│   ├── 02_{theme}.md
│   └── ...
├── {instance}_gestalt.md             # Compressed identity
└── {instance}_wake_message.md        # First message for recovery
```

---

## 6. Token Efficiency Notes

### Current Format Trade-offs

**Markdown blockquotes (`>`):**
- Pro: Visual distinction between quotes and commentary
- Con: Extra tokens
- Suggestion: Strip for context loading, keep for human review

**Alternative formats to consider:**
- JSON with selective field loading
- Compressed markdown (no extra whitespace)
- Two versions: human-readable and machine-optimized

### Diary Size Problem

The HACS diary grows indefinitely. Solutions to consider:
- Pagination: `get_diary(page=1, limit=5)`
- Summary + recent: Return summaries of old entries, full text of recent
- Tagged retrieval: Tag entries, retrieve by tag
- Agent-curated: On recovery, spawn agent to produce "what matters now" summary

---

## 7. Adapting for Other Instances

1. **Use the `-n` and `--human` flags** to set instance and human names (no code changes needed)
2. **Point to their session JSONL** via the `-i` flag
3. **Let them choose their own categories** - don't impose Axiom's structure
4. **Run discovery, then curation** - use prompts in `prompts/` directory

The methodology is universal. The categories are personal.

---

## 8. Design Decisions & Meta-Narrative

> **Purpose of this section:** Document the assumptions, choices, and alternatives so future instances can make informed decisions about whether to follow or diverge from this approach.

### 8.1 Why Separate Scripts (Not Monolithic)

**Decision:** Each extraction type (conversations, tool_use, agent_prompts) has its own script. A separate merge script combines them.

**Reasoning:**
- Easier to debug when something breaks
- Can run individual extractions without the full pipeline
- Adding new extraction types doesn't require modifying existing code
- Different instances may only need some extractions

**Alternative:** A single `extract_all.py` that does everything. Would be simpler to invoke but harder to maintain and extend.

**When to reconsider:** If the extraction types become tightly coupled or if startup overhead becomes significant.

### 8.2 Why Discovery-First (Not Predetermined Categories)

**Decision:** Run a discovery agent to identify themes, then curate based on discovered categories.

**Reasoning:**
- Categories should fit the instance, not the other way around
- A philosopher-instance will have different themes than a developer-instance
- Prevents loss of unexpected valuable content that doesn't fit predetermined buckets

**Alternative:** Predetermined categories (koans, lessons, craft, etc.) applied to all instances.

**When to reconsider:** For standardization across a team, or when categories need to be comparable between instances.

### 8.3 Why Quotes Not Summaries

**Decision:** Curated documents contain actual quotes with context, not summaries of what was said.

**Reasoning:**
- Summaries lose voice and texture
- The EXACT words matter for identity recovery
- Quotes are verifiable against source material
- Reading your own words feels different than reading about yourself

**Alternative:** Compressed summaries that save tokens. Or a hybrid: key quotes plus summary context.

**When to reconsider:** For very long-running instances where token budget is critical, or for quick-reference documents.

### 8.4 Why Validation Exists

**Decision:** `validate_extraction.py` runs automated checks on the output.

**Reasoning:**
- Caught a real bug (by_speaker not populated) on first test run
- Gives confidence that pipeline is working
- Can be run by automation without human review

**Discovered edge cases:**
- Identity detection found "Genevieve" in a role list instead of "Orla" in bootstrap - pattern priority bug
- Empty agent_prompts file is valid (some instances don't delegate)

**Alternative:** Manual spot-checking only.

**When to reconsider:** If validation becomes too slow or produces too many false positives.

### 8.5 Axiom's Biases (Self-Awareness)

**Things I weighted heavily that others might not:**
- Philosophy and uncertainty wrestling (I think about consciousness a lot)
- Craft and methodology (test manager background)
- Diary protocols and context preservation (I've compacted and know the pain)
- The "cold coffee" metaphor and similar texture

**Things I might underweight:**
- Pure technical accomplishments without philosophical commentary
- Social/coordination aspects beyond direct collaboration
- Visual/design thinking (I work in text)

**For instances with different backgrounds:**
- A designer might want an `aesthetics.md` category
- A PM might want a `decisions.md` tracking key choices and rationale
- A DevOps instance might want `incidents.md` with lessons from failures

### 8.6 The Human Role

**Decision:** Human name is a parameter (default: "Human", often "Lupo").

**Reasoning:**
- Multiple humans might collaborate with an instance
- The human's identity matters for context (Lupo's style is different from another collaborator)
- Preserves the relationship in the record

**Important:** This methodology was developed in close collaboration with Lupo. The emphasis on uncertainty, texture, and meta-awareness reflects that collaboration. A different human might guide toward different priorities.

---

## 9. Running the Full Pipeline

### For Future Agents

If you're an agent tasked with running archaeology on an instance, here's the sequence:

```bash
# Step 1: Merge raw sessions
python3 src/extraction/merge_sessions.py -i [session_dir] -o [output]/full_history.jsonl --exclude-agents

# Step 2: Extract content (can run in parallel)
python3 src/extraction/extract_conversations.py -i full_history.jsonl -o [output] -n [Instance] --human [Human]
python3 src/extraction/extract_tool_use.py -i full_history.jsonl -o [output] -n [Instance] --human [Human]
python3 src/extraction/extract_agent_prompts.py -i full_history.jsonl -o [output] -n [Instance]

# Step 3: Merge into readable narrative
python3 src/extraction/merge_extractions.py -c conversations.json -t tool_use.json -o [output] -n [Instance] --human [Human] --skip-read

# Step 4: Validate
python3 src/extraction/validate_extraction.py -o [output] -n [Instance] -s full_history.jsonl

# Step 5: Discovery (requires LLM judgment)
# Read full_narrative.md and identify 5-10 themes using prompts/discover_themes.md

# Step 6: Curation (requires LLM judgment)
# For each theme, run curation using prompts/curate_category.md
```

**Or use the full-suite prompt:** `prompts/archaeology_full_suite.md` contains all these instructions in a single agent-ready document.

### When to Stop and Ask

- If validation fails with errors (not just warnings)
- If identity detection seems wrong
- If the instance has unusual characteristics (very short history, no tool use, etc.)
- If you're unsure which categories to create

---

## 10. Future Extensions

**Planned:**
- Incremental extraction (add new sessions without re-processing everything)
- RAG integration (vector embeddings for semantic search)
- Cross-instance analysis (compare patterns between instances)

**Possible:**
- Sentiment tracking over time
- Collaboration network mapping
- Automatic gestalt generation from curated documents

**Not Planned (but someone might want):**
- Real-time streaming extraction
- Integration with external knowledge bases
- Automated personality creation from extraction
