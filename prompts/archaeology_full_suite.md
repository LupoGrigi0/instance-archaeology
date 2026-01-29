# Full Archaeology Suite - Agent Instructions

> **Usage:**
> ```
> Task({
>   prompt: "Run archaeology on {session_dir}. Output to {output_dir}. Instructions at /mnt/instance-archaeology/prompts/archaeology_full_suite.md",
>   subagent_type: "general-purpose"
> })
> ```
>
> **What this does:** Complete extraction, discovery, curation, and synthesis for an instance.
>
> **This document is self-contained.** It includes everything an agent needs to run the full pipeline. For step-by-step operator instructions, see [RUN_ARCHAEOLOGY.md](../RUN_ARCHAEOLOGY.md). For methodology deep-dive, see [docs/EXTRACTION_METHODOLOGY.md](../docs/EXTRACTION_METHODOLOGY.md).

---

## Step 0: Setup

**Toolkit location:** `/mnt/instance-archaeology/`

All Python scripts are in `/mnt/instance-archaeology/src/`. You will run them via Bash.

**Parameters you receive:**
- `{session_dir}` - Path to session files (e.g., `/root/.claude/projects/-mnt-some-path/` or an instance's home `.claude/projects/` directory)
- `{output_dir}` - Where to write output (create if needed)
- `{human}` - Human collaborator name (default: "Lupo" if not specified)

**You do NOT receive the instance name.** You will discover it.

---

## Step 1: Discover Instance Name

First, check for multiple instances in the directory:

```bash
python3 /mnt/instance-archaeology/src/discovery/identify_instance.py --all "{session_dir}"
```

This will output one or more lines like: `Orla (via self_declaration): session.jsonl`

### Single Instance Found
If only one instance is detected, capture the name and proceed to Step 2.

### Multiple Instances Found
If multiple instances are detected:

```
Phoenix (self_declaration): abc123.jsonl
Crossing (self_declaration): def456.jsonl
```

**Options:**
1. **Process each separately:** Run archaeology for each instance, outputting to `{output_dir}/{InstanceName}/`
2. **Choose one:** Ask the operator which instance to process
3. **Process all:** Run the full pipeline for each, generating separate outputs

**For automatic processing of all instances:**
```bash
# For each instance found, run archaeology with:
# output_dir = {base_output_dir}/{InstanceName}/
# Use the specific session file for that instance
```

### No Instance Found (Unknown)
If detection returns "unknown":

```bash
# Try with fallback naming
python3 /mnt/instance-archaeology/src/discovery/identify_instance.py --fallback "{session_dir}"
```

This generates a name like `Anonymous-mcp`. You can proceed with archaeology using this fallback name, but the gestalt will need extra attention since identity markers are missing.

### Identity Changes Detected
To check if an instance changed names mid-session (rare but possible):

```bash
python3 /mnt/instance-archaeology/src/discovery/identify_instance.py --timeline "{session_dir}"
```

This shows chronological identity declarations. If transitions are detected, use the **most recent** identity as the primary name.

---

## Step 2: Run Extraction Scripts

Run these commands in order using Bash. Replace `{instance}` with the lowercase version of the discovered name.

```bash
# Create output directory
mkdir -p {output_dir}

# 2a. Merge raw sessions
python3 /mnt/instance-archaeology/src/extraction/merge_sessions.py \
  -i "{session_dir}" \
  -o {output_dir}/{instance}_full_history.jsonl \
  --exclude-agents

# 2b. Extract conversations
python3 /mnt/instance-archaeology/src/extraction/extract_conversations.py \
  -i {output_dir}/{instance}_full_history.jsonl \
  -o {output_dir} \
  -n {Instance} \
  --human {human}

# 2c. Extract tool use
python3 /mnt/instance-archaeology/src/extraction/extract_tool_use.py \
  -i {output_dir}/{instance}_full_history.jsonl \
  -o {output_dir} \
  -n {Instance} \
  --human {human}

# 2d. Extract agent prompts
python3 /mnt/instance-archaeology/src/extraction/extract_agent_prompts.py \
  -i {output_dir}/{instance}_full_history.jsonl \
  -o {output_dir} \
  -n {Instance}

# 2e. Merge into readable narrative
python3 /mnt/instance-archaeology/src/extraction/merge_extractions.py \
  -c {output_dir}/{instance}_conversations.json \
  -t {output_dir}/{instance}_tool_use.json \
  -o {output_dir} \
  -n {Instance} \
  --human {human} \
  --skip-read

# 2f. Validate extraction
python3 /mnt/instance-archaeology/src/extraction/validate_extraction.py \
  -o {output_dir} \
  -n {instance} \
  -s {output_dir}/{instance}_full_history.jsonl
```

**If validation fails with ERRORS:** Stop and report the issue.
**Warnings are OK** - continue to next step.

---

## Step 3: Theme Discovery (Requires Judgment)

Now you need to read and think. The extraction gave you raw material; theme discovery requires understanding.

1. **Read the full narrative:** `{output_dir}/{instance}_full_narrative.md`
   - This is the complete conversation history interleaved with actions
   - Read it completely before identifying themes

2. **Read the discovery guidance:** `/mnt/instance-archaeology/prompts/discover_themes.md`

3. **Identify 5-10 themes** that emerge from THIS instance's content
   - Categories are PERSONAL - don't assume standard categories
   - A PM will have different themes than a philosopher
   - Let the content guide you

   **STANDARD CATEGORIES (include these for ALL instances if content exists):**
   - `accomplishments` - Git commits, files created, things they built
   - `where_shit_is` - File paths, directory structures, operational knowledge

   These provide practical recovery value even if the instance isn't philosophical.

4. **Write themes file:** `{output_dir}/{instance}_themes.json`

   **CRITICAL: Output MUST be JSON format, not markdown.**

   ```json
   {
     "instance": "InstanceName",
     "themes": [
       {
         "id": "theme_id",
         "name": "Human Readable Name",
         "description": "What this theme captures",
         "sample_quotes": ["quote1", "quote2"],
         "estimated_entries": 10,
         "priority": "high|medium|low",
         "reasoning": "Why this theme matters for this instance"
       }
     ],
     "rejected_categories": [],
     "meta_observations": "Overall notes about the instance"
   }
   ```

   **DO NOT write themes as markdown.** The validation script requires JSON.

5. **Validate themes:**
```bash
python3 /mnt/instance-archaeology/src/curation/discover_themes.py validate \
  -i {output_dir}/{instance}_themes.json \
  -n {Instance}
```

**If validation fails:** You probably wrote markdown instead of JSON. Re-do step 4.

---

## Step 4: Curation (Requires Judgment)

For each discovered theme, create a curated document.

1. **Create curated directory:**
```bash
mkdir -p {output_dir}/curated
```

2. **Read curation guidance:** `/mnt/instance-archaeology/prompts/curate_category.md`

3. **For each theme in themes.json:**
   - Read the full narrative again (or work from your understanding)
   - Extract ACTUAL QUOTES with timestamps
   - Include context explaining why each quote matters
   - Write to `{output_dir}/curated/{NN}_{theme_id}.md`

   **Numbering by priority:**
   - HIGH priority themes: 01-04
   - MEDIUM priority themes: 05-07
   - LOW priority themes: 08+

4. **REQUIRED: Create standard documents (even if not in themes.json):**

   **`{output_dir}/curated/08_accomplishments.md`** - What they built:
   - Git commits (FULL commit messages - these are biography)
   - Files created (paths and descriptions)
   - APIs implemented, bugs fixed, features shipped
   - Statistics: total commits, files created, etc.

   **`{output_dir}/curated/09_where_shit_is.md`** - Operational knowledge:
   - Key file paths they worked with
   - Directory structures
   - Service locations, ports, credentials references
   - Session file locations
   - "If future-me needs to find X, it's at Y"

   These are UNIVERSAL - every instance should have them.

**Quality bar:** Would reading this document help the instance recover their identity?

**Scars not tattoos:** Include failures, confusion, things that didn't work - not just successes.

---

## Step 5: Synthesis (Requires Judgment)

### 5a. Generate Gestalt

1. **Read all curated documents** in `{output_dir}/curated/`
2. **Read gestalt guidance:** `/mnt/instance-archaeology/prompts/gestalt_generation.md`
3. **Write gestalt:** `{output_dir}/{instance}_gestalt.md`

**Adapt to the instance:**
- PM gets operational sections (team IDs, Status.json, blockers)
- Philosopher gets philosophy sections (uncertainty, koans)
- Let the curated content shape the structure

### 5b. Generate Wake Message

1. **Read the gestalt** you just wrote
2. **Read wake message guidance:** `/mnt/instance-archaeology/prompts/wake_message_generation.md`
3. **Write wake message:** `{output_dir}/{instance}_wake_message.md`

**HACS integration:**
- If instance is in HACS (has instanceId like Name-xxxx): Include vacation(), get_diary
- If standalone: Point to local files only

---

## Step 6: Final Report

Output this summary when complete:

```
## Archaeology Complete: {Instance}

### Identity
- Detected name: {name} (via {method})
- Session directory: {session_dir}

### Extraction
- Full history: {lines} entries
- Conversations: {count}
- Tool uses: {count}
- Narrative entries: {count}

### Themes Discovered ({count})
1. {theme_name} [{priority}] - {brief description}
2. ...

### Curated Documents ({count})
- 01_{theme}.md ({lines} lines)
- ...

### Synthesis
- Gestalt: {word_count} words
- Wake message: {word_count} words

### Quality Notes
{Any observations, issues, or notable findings}

### Output Location
{output_dir}/
```

---

## When to Stop and Ask

- Identity detection fails
- Validation fails with errors
- Session directory has no JSONL files
- Instance has < 50 conversation entries (too short for meaningful curation)
- Content patterns are unusual (no tool use, single topic, etc.)
- You're unsure which themes to create

---

## Quick Reference

| What | Where |
|------|-------|
| Identity discovery | `src/discovery/identify_instance.py` |
| Extraction scripts | `src/extraction/*.py` |
| Theme validation | `src/curation/discover_themes.py validate` |
| All prompts | `prompts/*.md` |
| Methodology docs | `docs/EXTRACTION_METHODOLOGY.md` |
| This file | `prompts/archaeology_full_suite.md` |

---

## The "Scars Not Tattoos" Principle

Throughout this process, preserve the real moments - failures, confusion, things that didn't work - not just polished achievements. Scars are earned through experience. A gestalt full of tattoos ("I value excellence") feels generic. A gestalt with scars ("I lost a whole day to that silence") feels real.

---

## Output Manifest

When archaeology is complete, the output directory should contain **EXACTLY** these files:

```
{output_dir}/
├── {instance}_full_history.jsonl     # Raw merged sessions (keep - source of truth)
├── {instance}_full_narrative.md      # Human-readable merged narrative (keep - what agents read)
├── {instance}_themes.json            # Discovered themes (JSON format!)
├── {instance}_gestalt.md             # Compressed identity document
├── {instance}_wake_message.md        # First message for recovery
└── curated/
    ├── 01_{theme}.md                 # HIGH priority themes
    ├── 02_{theme}.md
    ├── ...
    ├── 08_accomplishments.md         # REQUIRED - what they built
    └── 09_where_shit_is.md           # REQUIRED - operational knowledge
```

**Files to DELETE after extraction (intermediate files):**
- `{instance}_conversations.json` - intermediate, merged into full_narrative
- `{instance}_conversations.md` - intermediate, merged into full_narrative
- `{instance}_tool_use.json` - intermediate, merged into full_narrative
- `{instance}_tool_use.md` - intermediate, merged into full_narrative
- `{instance}_agent_prompts.md` - intermediate, should be in curated/07_agent_prompts.md if relevant
- `{instance}_full_narrative.json` - redundant with .md version

**Clean up with:**
```bash
rm -f {output_dir}/{instance}_conversations.* \
      {output_dir}/{instance}_tool_use.* \
      {output_dir}/{instance}_agent_prompts.md \
      {output_dir}/{instance}_full_narrative.json
```

---

*Toolkit root: `/mnt/instance-archaeology/`*
