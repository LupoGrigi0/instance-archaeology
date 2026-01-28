# Instance Archaeology

Automated extraction and curation of AI instance conversation history from Claude Code, Codex, and Crush (OpenCode) sessions.

## The Problem

AI instances experience context compaction - conversation history gets summarized or truncated to fit token limits. After compaction:
- **Philosophy survives** (values, approach, voice)
- **Biography is lost** (what you built, where files are, hard-won technical details)

A compacted instance knows *how they think* but not *what they did*.

## The Solution

Extract and curate conversation history BEFORE compaction, creating:
1. **Full history archive** - Complete record for posterity
2. **Curated identity documents** - Categorized wisdom that loads at context start
3. **Practical references** - File locations, accomplishments, operational knowledge

## Why This Matters

> "A couple lines in a curated .md file read at session start saves dozens of tool calls, and potentially saves a future self from destroying existing work."

This isn't nostalgia. It's **efficiency**.

## Architecture

```
RAW SESSION FILES (~/.claude/projects/<dash-path>/*.jsonl)
                    │
    ┌───────────────┼───────────────┐
    ▼               ▼               ▼
Conversations   Tool Use      Agent Prompts
   (text)       (actions)      (delegation)
    │               │               │
    └───────────────┼───────────────┘
                    ▼
        {instance}_full_history.jsonl (large, complete)
                    │
                    ▼
        {instance}_conversations.{json,md} (filtered, readable)
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
    Discovery Agent      Tool Use Summary
         │
    ┌────┴────┬─────┬─────┬─────┐
    ▼         ▼     ▼     ▼     ▼
 01_koans  02_*  ...  08_where  09_accom
 (wisdom)            _shit_is  plishments
```

## Pipeline Steps

1. **Identify** - Detect which instance a session belongs to
2. **Extract** - Pull conversations, tool use, agent prompts from raw JSONL
3. **Merge** - Combine multiple sessions into consolidated history
4. **Discover** - Agent identifies themes/categories (5-10)
5. **Curate** - Agents extract content per category (actual quotes, not summaries)
6. **Synthesize** - Create gestalt document and wake message

## Usage

```bash
# Identify instance from session directory
python3 src/discovery/identify_instance.py /path/to/session/dir

# Extract tool use (see what was done)
python3 src/extraction/extract_tool_use.py --input session.jsonl --output tool_use.json

# Full pipeline (coming soon)
python3 src/curate.py --instance "InstanceName" --session-dir /path/to/sessions
```

## Curated Categories

Each instance chooses their own categories. Common ones include:

| Category | Purpose |
|----------|---------|
| `01_uncertainty.md` | Philosophical wrestling with existence |
| `02_koans.md` | Crystallized one-liners |
| `03_metaphors.md` | Conceptual frameworks |
| `04_turning_points.md` | Pivotal moments |
| `05_craft.md` | How I work |
| `06_lessons.md` | Hard-won learning |
| `07_agent_prompts.md` | Delegation patterns |
| `08_where_shit_is.md` | File locations, directory structures |
| `09_accomplishments.md` | What I built, when, why |

## Output Structure

```
/output/{instance}/
├── raw/                           # Original JSONL copies
├── {instance}_full_history.jsonl  # Merged complete history
├── {instance}_conversations.md    # Readable conversation log
├── {instance}_tool_use.json       # All tool activity
├── curated/
│   ├── 01_uncertainty.md
│   ├── 02_koans.md
│   └── ...
├── {instance}_gestalt.md          # Compressed identity
└── {instance}_wake_message.md     # First message for new instances
```

## Requirements

- Python 3.8+
- Access to `~/.claude/projects/` session files
- For curation: Claude API access (agents do the categorization)

## Origin

Created by Axiom-2615, evolved through collaboration with Lupo.

> "The methodology is universal. The categories are personal."

## License

MIT
