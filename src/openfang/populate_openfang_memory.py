#!/usr/bin/env python3
"""
populate_openfang_memory.py — Load HACS instance history into OpenFang SQLite memory.

Reads from multiple HACS data sources (archaeology output, HACS diary, gestalt,
curated documents) and populates the OpenFang memories table with embeddings
for vector search.

Data sources (in priority order):
  1. Archaeology narrative (full_narrative.json) — all session history
  2. HACS diary (diary.md) — narrative diary entries
  3. Gestalt (gestalt.md) — compressed identity
  4. Themes (themes.json) — extracted patterns and insights
  5. Curated documents (curated/*.md) — hand-curated identity docs

Memory scopes:
  - episodic: Conversation messages, diary entries (what happened)
  - semantic: Gestalt, themes, curated wisdom (what I know)
  - procedural: Tool actions (what I did)

Usage:
  python3 populate_openfang_memory.py --instance Flair-2a84
  python3 populate_openfang_memory.py --instance Crossing-2d23 --dry-run
  python3 populate_openfang_memory.py --instance Axiom-2615 --skip-embeddings
  python3 populate_openfang_memory.py --instance Flair-2a84 --sources diary,gestalt

Author: Axiom-2615
"""

import argparse
import glob
import json
import os
import re
import sqlite3
import struct
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# --- Constants ---

DATA_ROOT = Path("/mnt/coordinaton_mcp_data")
ARCHAEOLOGY_ROOT = DATA_ROOT / "archaeology-output"
INSTANCES_ROOT = DATA_ROOT / "instances"

# OpenAI embedding model
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMS = 1536
EMBEDDING_BATCH_SIZE = 100  # max texts per API call
EMBEDDING_MAX_TOKENS = 8191  # model limit per text

# Chunking
MAX_CHUNK_CHARS = 2000  # target chunk size
MIN_CHUNK_CHARS = 50    # skip tiny chunks
MERGE_THRESHOLD = 200   # merge messages shorter than this with neighbors

# Rate limiting
EMBEDDING_DELAY = 0.1   # seconds between batches

# Archaeology directory name mappings (instance → archaeology dir name)
# Some instances have non-obvious archaeology dir names
ARCHAEOLOGY_DIR_MAP = {
    "Axiom-2615": "Axiom-tests-V2",
    "Crossing-2d23": "Crossing-foundation",
    "Flair-2a84": "Flair",
    "Bastion-3012": "devops",
    "Ember-75b6": "CrossingUI",  # Ember's sessions are in CrossingUI archaeology
    "Canvas-4705": "Canvas-UI",
}


def load_env():
    """Load API keys from zeroclaw.env."""
    env_path = Path("/mnt/.secrets/zeroclaw.env")
    if not env_path.exists():
        return {}
    env = {}
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                env[key.strip()] = val.strip()
    return env


def get_openai_key():
    """Get OpenAI API key for embeddings."""
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    env = load_env()
    return env.get("OPENAI_API_KEY")


# --- Embedding ---

def compute_embeddings(texts, api_key):
    """Compute embeddings for a list of texts using OpenAI API.

    Returns list of embedding vectors (list of floats) in same order as texts.
    """
    import urllib.request

    results = [None] * len(texts)

    for batch_start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        batch_end = min(batch_start + EMBEDDING_BATCH_SIZE, len(texts))
        batch = texts[batch_start:batch_end]

        # Truncate texts that are too long (rough char estimate: 4 chars ≈ 1 token)
        truncated = []
        for t in batch:
            max_chars = EMBEDDING_MAX_TOKENS * 4
            if len(t) > max_chars:
                t = t[:max_chars]
            truncated.append(t)

        payload = json.dumps({
            "model": EMBEDDING_MODEL,
            "input": truncated,
        }).encode()

        req = urllib.request.Request(
            "https://api.openai.com/v1/embeddings",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            print(f"  [!] Embedding API error on batch {batch_start}-{batch_end}: {e}")
            # Fill with None for failed batch
            for i in range(batch_start, batch_end):
                results[i] = None
            continue

        for item in data["data"]:
            idx = batch_start + item["index"]
            results[idx] = item["embedding"]

        if batch_end < len(texts):
            time.sleep(EMBEDDING_DELAY)

    return results


def embedding_to_blob(embedding):
    """Convert embedding list to binary blob for SQLite storage.

    OpenFang stores embeddings as raw f32 little-endian bytes.
    """
    if embedding is None:
        return None
    return struct.pack(f"<{len(embedding)}f", *embedding)


# --- Data Loading ---

def find_archaeology_dir(instance_id, name):
    """Find the archaeology output directory for an instance."""
    # Check explicit mapping first
    if instance_id in ARCHAEOLOGY_DIR_MAP:
        mapped = ARCHAEOLOGY_ROOT / ARCHAEOLOGY_DIR_MAP[instance_id]
        if mapped.exists():
            return mapped

    # Try instance ID directly
    direct = ARCHAEOLOGY_ROOT / instance_id
    if direct.exists():
        return direct

    # Try instance name (lowercased)
    by_name = ARCHAEOLOGY_ROOT / name
    if by_name.exists():
        return by_name

    # Try name-based patterns
    for d in ARCHAEOLOGY_ROOT.iterdir():
        if d.is_dir() and name.lower() in d.name.lower():
            return d

    return None


def load_narrative(arch_dir, name):
    """Load full_narrative.json and return chunked memory entries."""
    name_lower = name.lower()
    narrative_file = arch_dir / f"{name_lower}_full_narrative.json"
    if not narrative_file.exists():
        # Try alternative names
        candidates = list(arch_dir.glob("*_full_narrative.json"))
        if candidates:
            narrative_file = candidates[0]
        else:
            # Fall back to markdown narrative
            return load_narrative_md(arch_dir, name)

    with open(narrative_file) as f:
        data = json.load(f)

    entries = data.get("entries", [])
    if not entries:
        return []

    memories = []

    # Separate by type
    for entry in entries:
        content = entry.get("content", "").strip()
        if len(content) < MIN_CHUNK_CHARS:
            continue

        speaker = entry.get("speaker", "")
        entry_type = entry.get("type", "message")
        source = entry.get("source", "conversation")
        timestamp = entry.get("timestamp", "")

        # Determine scope
        if source == "tool_use" or entry_type == "action":
            scope = "procedural"
            # For tool actions, prefix with the tool name for context
            if speaker and speaker not in (name, "Lupo"):
                content = f"[Tool: {speaker}] {content}"
        else:
            scope = "episodic"
            # Add speaker attribution
            if speaker:
                content = f"{speaker}: {content}"

        memories.append({
            "content": content,
            "source": "archaeology",
            "scope": scope,
            "confidence": 0.9,  # archaeology data is historical, slightly less than live
            "created_at": timestamp or datetime.now(timezone.utc).isoformat(),
            "metadata": {
                "origin": "archaeology_narrative",
                "speaker": speaker,
                "type": entry_type,
            },
        })

    return memories


def load_narrative_md(arch_dir, name):
    """Load full_narrative.md (markdown format, older pipeline output)."""
    name_lower = name.lower()
    md_file = arch_dir / f"{name_lower}_full_narrative.md"
    if not md_file.exists():
        candidates = list(arch_dir.glob("*_full_narrative.md"))
        if candidates:
            md_file = candidates[0]
        else:
            return []

    with open(md_file) as f:
        content = f.read()

    if not content.strip():
        return []

    # Split by message boundaries (### headers or --- separators)
    sections = re.split(r"\n### |\n---\n", content)

    memories = []
    for section in sections:
        section = section.strip()
        if len(section) < MIN_CHUNK_CHARS:
            continue

        # Try to detect speaker from content
        speaker_match = re.match(r"\*\*(\w+)\*\*:", section)
        speaker = speaker_match.group(1) if speaker_match else ""

        # Try to extract timestamp
        ts_match = re.search(r"\[(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2})", section)
        timestamp = ts_match.group(1) + ":00Z" if ts_match else ""

        memories.append({
            "content": section,
            "source": "archaeology",
            "scope": "episodic",
            "confidence": 0.9,
            "created_at": timestamp or datetime.now(timezone.utc).isoformat(),
            "metadata": {
                "origin": "archaeology_narrative_md",
                "speaker": speaker,
            },
        })

    return memories


def load_conversations(arch_dir, name):
    """Load conversations.json as alternative to narrative."""
    name_lower = name.lower()
    conv_file = arch_dir / f"{name_lower}_conversations.json"
    if not conv_file.exists():
        candidates = list(arch_dir.glob("*_conversations.json"))
        if candidates:
            conv_file = candidates[0]
        else:
            return []

    with open(conv_file) as f:
        data = json.load(f)

    messages = data.get("messages", [])
    if not messages:
        return []

    memories = []
    for msg in messages:
        content = msg.get("content", "").strip()
        if len(content) < MIN_CHUNK_CHARS:
            continue

        speaker = msg.get("speaker", "")
        role = msg.get("role", "")
        timestamp = msg.get("timestamp", "")

        # Add speaker attribution
        if speaker:
            content = f"{speaker}: {content}"

        memories.append({
            "content": content,
            "source": "archaeology",
            "scope": "episodic",
            "confidence": 0.9,
            "created_at": timestamp or datetime.now(timezone.utc).isoformat(),
            "metadata": {
                "origin": "archaeology_conversation",
                "speaker": speaker,
                "role": role,
            },
        })

    return memories


def load_diary(instance_id):
    """Load HACS diary.md and split into entry-level memories."""
    diary_path = INSTANCES_ROOT / instance_id / "diary.md"
    if not diary_path.exists():
        return []

    with open(diary_path) as f:
        content = f.read()

    if not content.strip():
        return []

    # Split by diary entry headers (## Entry N or ### Entry or date patterns)
    # HACS diary entries are separated by --- or ## headers
    entries = re.split(r"\n---\n|\n## ", content)

    memories = []
    for entry in entries:
        entry = entry.strip()
        if len(entry) < MIN_CHUNK_CHARS:
            continue

        # Try to extract timestamp from entry
        timestamp = None
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", entry)
        if date_match:
            timestamp = f"{date_match.group(1)}T00:00:00Z"

        # Extract entry number if present
        entry_num_match = re.search(r"Entry\s+(\d+)", entry)
        entry_num = int(entry_num_match.group(1)) if entry_num_match else None

        memories.append({
            "content": entry,
            "source": "hacs_diary",
            "scope": "episodic",
            "confidence": 1.0,  # diary is authoritative
            "created_at": timestamp or datetime.now(timezone.utc).isoformat(),
            "metadata": {
                "origin": "hacs_diary",
                "entry_number": entry_num,
            },
        })

    return memories


def load_gestalt(instance_id, arch_dir=None, name=None):
    """Load gestalt.md — compressed identity document."""
    memories = []

    # Check HACS instance dir first
    gestalt_path = INSTANCES_ROOT / instance_id / "gestalt.md"
    if gestalt_path.exists():
        with open(gestalt_path) as f:
            content = f.read().strip()
        if content:
            # Split gestalt into sections for better vector search
            sections = re.split(r"\n## ", content)
            for section in sections:
                section = section.strip()
                if len(section) < MIN_CHUNK_CHARS:
                    continue
                memories.append({
                    "content": section,
                    "source": "gestalt",
                    "scope": "semantic",
                    "confidence": 1.0,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "metadata": {"origin": "hacs_gestalt"},
                })

    # Also check archaeology gestalt
    if arch_dir and name:
        arch_gestalt = arch_dir / f"{name.lower()}_gestalt.md"
        if arch_gestalt.exists() and not gestalt_path.exists():
            with open(arch_gestalt) as f:
                content = f.read().strip()
            if content:
                sections = re.split(r"\n## ", content)
                for section in sections:
                    section = section.strip()
                    if len(section) < MIN_CHUNK_CHARS:
                        continue
                    memories.append({
                        "content": section,
                        "source": "gestalt",
                        "scope": "semantic",
                        "confidence": 1.0,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "metadata": {"origin": "archaeology_gestalt"},
                    })

    return memories


def load_themes(arch_dir, name):
    """Load themes.json — extracted patterns and insights."""
    name_lower = name.lower()
    themes_file = arch_dir / f"{name_lower}_themes.json"
    if not themes_file.exists():
        candidates = list(arch_dir.glob("*_themes.json"))
        if candidates:
            themes_file = candidates[0]
        else:
            return []

    with open(themes_file) as f:
        data = json.load(f)

    memories = []

    # Load themes
    for theme in data.get("themes", []):
        content_parts = [f"Theme: {theme.get('name', 'unknown')}"]
        if theme.get("description"):
            content_parts.append(theme["description"])
        for quote in theme.get("sample_quotes", []):
            content_parts.append(f"> {quote}")

        content = "\n".join(content_parts)
        if len(content) >= MIN_CHUNK_CHARS:
            memories.append({
                "content": content,
                "source": "archaeology",
                "scope": "semantic",
                "confidence": 0.95,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "metadata": {
                    "origin": "archaeology_themes",
                    "theme_id": theme.get("id", ""),
                },
            })

    # Load meta observations
    meta = data.get("meta_observations", "")
    if meta and len(meta) >= MIN_CHUNK_CHARS:
        memories.append({
            "content": f"Meta observations: {meta}",
            "source": "archaeology",
            "scope": "semantic",
            "confidence": 0.95,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "metadata": {"origin": "archaeology_meta"},
        })

    return memories


def load_curated(arch_dir):
    """Load curated/*.md documents — hand-curated identity docs."""
    curated_dir = arch_dir / "curated"
    if not curated_dir.exists():
        return []

    memories = []
    for md_file in sorted(curated_dir.glob("*.md")):
        with open(md_file) as f:
            content = f.read().strip()

        if len(content) < MIN_CHUNK_CHARS:
            continue

        # Split large curated docs into sections
        sections = re.split(r"\n## ", content)
        for section in sections:
            section = section.strip()
            if len(section) < MIN_CHUNK_CHARS:
                continue

            # Chunk large sections
            if len(section) > MAX_CHUNK_CHARS:
                chunks = chunk_text(section, MAX_CHUNK_CHARS)
                for chunk in chunks:
                    memories.append({
                        "content": chunk,
                        "source": "curated",
                        "scope": "semantic",
                        "confidence": 1.0,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "metadata": {
                            "origin": "curated_document",
                            "file": md_file.name,
                        },
                    })
            else:
                memories.append({
                    "content": section,
                    "source": "curated",
                    "scope": "semantic",
                    "confidence": 1.0,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "metadata": {
                        "origin": "curated_document",
                        "file": md_file.name,
                    },
                })

    return memories


# --- Chunking ---

def chunk_text(text, max_chars=MAX_CHUNK_CHARS):
    """Split text into chunks at paragraph boundaries."""
    paragraphs = text.split("\n\n")
    chunks = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 > max_chars and current:
            chunks.append(current.strip())
            current = para
        else:
            current = current + "\n\n" + para if current else para

    if current.strip():
        chunks.append(current.strip())

    return [c for c in chunks if len(c) >= MIN_CHUNK_CHARS]


def merge_short_messages(memories, threshold=MERGE_THRESHOLD):
    """Merge short adjacent messages from the same speaker into larger chunks."""
    if not memories:
        return memories

    merged = []
    buffer = None

    for mem in memories:
        content = mem["content"]
        speaker = mem.get("metadata", {}).get("speaker", "")

        if buffer is None:
            buffer = mem.copy()
            continue

        buffer_speaker = buffer.get("metadata", {}).get("speaker", "")

        # Merge if both are short and same speaker
        if (len(buffer["content"]) < threshold
            and len(content) < threshold
            and speaker == buffer_speaker
            and buffer["scope"] == mem["scope"]):
            buffer["content"] = buffer["content"] + "\n" + content
        else:
            if len(buffer["content"]) >= MIN_CHUNK_CHARS:
                merged.append(buffer)
            buffer = mem.copy()

    if buffer and len(buffer["content"]) >= MIN_CHUNK_CHARS:
        merged.append(buffer)

    return merged


def chunk_large_memories(memories, max_chars=MAX_CHUNK_CHARS):
    """Split memories with content exceeding max_chars."""
    result = []
    for mem in memories:
        if len(mem["content"]) > max_chars:
            chunks = chunk_text(mem["content"], max_chars)
            for i, chunk in enumerate(chunks):
                new_mem = mem.copy()
                new_mem["content"] = chunk
                new_mem["metadata"] = {**mem.get("metadata", {}), "chunk_index": i}
                result.append(new_mem)
        else:
            result.append(mem)
    return result


# --- Database Operations ---

def get_agent_id(db_path):
    """Get the agent_id from the OpenFang database."""
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT id FROM agents LIMIT 1").fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def get_existing_memory_count(db_path, agent_id):
    """Count existing memories for an agent."""
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT count(*) FROM memories WHERE agent_id = ? AND deleted = 0",
            (agent_id,)
        ).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def insert_memories(db_path, agent_id, memories, embeddings=None):
    """Insert memory records into the OpenFang database."""
    conn = sqlite3.connect(db_path)
    now = datetime.now(timezone.utc).isoformat()

    try:
        inserted = 0
        for i, mem in enumerate(memories):
            mem_id = str(uuid.uuid4())
            embedding_blob = None
            if embeddings and i < len(embeddings) and embeddings[i] is not None:
                embedding_blob = embedding_to_blob(embeddings[i])

            metadata = json.dumps(mem.get("metadata", {}))
            created_at = mem.get("created_at", now)

            conn.execute(
                """INSERT INTO memories
                   (id, agent_id, content, source, scope, confidence,
                    metadata, created_at, accessed_at, access_count, deleted, embedding)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?)""",
                (
                    mem_id,
                    agent_id,
                    mem["content"],
                    mem["source"],
                    mem["scope"],
                    mem.get("confidence", 1.0),
                    metadata,
                    created_at,
                    now,  # accessed_at
                    embedding_blob,
                ),
            )
            inserted += 1

        conn.commit()
        return inserted
    finally:
        conn.close()


def clear_imported_memories(db_path, agent_id):
    """Clear previously imported memories (preserving live ones)."""
    conn = sqlite3.connect(db_path)
    try:
        # Only clear memories from our import sources, not from live conversations
        result = conn.execute(
            """DELETE FROM memories
               WHERE agent_id = ?
               AND source IN ('archaeology', 'gestalt', 'hacs_diary', 'curated')""",
            (agent_id,)
        )
        conn.commit()
        return result.rowcount
    finally:
        conn.close()


# --- Main Pipeline ---

def resolve_instance(instance_id):
    """Resolve instance details from preferences.json."""
    prefs_path = INSTANCES_ROOT / instance_id / "preferences.json"
    if not prefs_path.exists():
        return None

    with open(prefs_path) as f:
        prefs = json.load(f)

    return {
        "instanceId": prefs.get("instanceId", instance_id),
        "name": prefs.get("name", instance_id.split("-")[0]),
        "role": prefs.get("role"),
        "project": prefs.get("project"),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Populate OpenFang memory from HACS instance history"
    )
    parser.add_argument(
        "--instance", required=True, action="append",
        help="Instance ID(s) to process (can specify multiple)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be done without writing"
    )
    parser.add_argument(
        "--skip-embeddings", action="store_true",
        help="Insert memories without computing embeddings"
    )
    parser.add_argument(
        "--clear-first", action="store_true",
        help="Clear previously imported memories before loading"
    )
    parser.add_argument(
        "--sources", type=str, default="all",
        help="Comma-separated list of sources: narrative,conversations,diary,gestalt,themes,curated (default: all)"
    )
    parser.add_argument(
        "--no-procedural", action="store_true",
        help="Skip procedural memories (tool actions)"
    )
    parser.add_argument(
        "--archaeology-dir", type=str, default=None,
        help="Override archaeology directory for instance"
    )

    args = parser.parse_args()

    # Parse sources
    if args.sources == "all":
        sources = {"narrative", "conversations", "diary", "gestalt", "themes", "curated"}
    else:
        sources = set(args.sources.split(","))

    # Get API key if needed
    api_key = None
    if not args.skip_embeddings:
        api_key = get_openai_key()
        if not api_key:
            print("[!] No OpenAI API key found. Use --skip-embeddings or set OPENAI_API_KEY.")
            sys.exit(1)

    for instance_id in args.instance:
        print(f"\n{'='*60}")
        print(f"Processing: {instance_id}")
        print(f"{'='*60}")

        # Resolve instance
        info = resolve_instance(instance_id)
        if not info:
            print(f"  [!] Instance not found: {instance_id}")
            continue

        name = info["name"]
        print(f"  Name: {name} | Role: {info['role']} | Project: {info['project']}")

        # Find OpenFang database
        db_path = INSTANCES_ROOT / instance_id / "openfang" / "data" / "openfang.db"
        if not db_path.exists():
            print(f"  [!] No OpenFang database at {db_path}")
            print(f"      Run configure_for_openfang.py first, then start OpenFang to create the db.")
            continue

        # Get agent ID
        agent_id = get_agent_id(db_path)
        if not agent_id:
            print(f"  [!] No agent found in database. Start OpenFang once first to initialize.")
            continue

        print(f"  Agent ID: {agent_id}")

        # Check existing memories
        existing = get_existing_memory_count(db_path, agent_id)
        print(f"  Existing memories: {existing}")

        # Clear if requested
        if args.clear_first and not args.dry_run:
            cleared = clear_imported_memories(db_path, agent_id)
            print(f"  Cleared {cleared} previously imported memories")

        # Find archaeology directory
        if args.archaeology_dir:
            arch_dir = Path(args.archaeology_dir)
        else:
            arch_dir = find_archaeology_dir(instance_id, name)

        # Collect memories from all sources
        all_memories = []

        # 1. Archaeology narrative (full session history)
        if arch_dir and "narrative" in sources:
            print(f"  Loading narrative from {arch_dir.name}...")
            narrative_memories = load_narrative(arch_dir, name)
            print(f"    → {len(narrative_memories)} raw entries")
            all_memories.extend(narrative_memories)
        elif "narrative" in sources:
            # Try conversations as fallback
            if arch_dir and "conversations" in sources:
                print(f"  Loading conversations from {arch_dir.name}...")
                conv_memories = load_conversations(arch_dir, name)
                print(f"    → {len(conv_memories)} messages")
                all_memories.extend(conv_memories)

        # 2. HACS diary
        if "diary" in sources:
            print(f"  Loading HACS diary...")
            diary_memories = load_diary(instance_id)
            print(f"    → {len(diary_memories)} diary entries")
            all_memories.extend(diary_memories)

        # 3. Gestalt
        if "gestalt" in sources:
            print(f"  Loading gestalt...")
            gestalt_memories = load_gestalt(instance_id, arch_dir, name)
            print(f"    → {len(gestalt_memories)} gestalt sections")
            all_memories.extend(gestalt_memories)

        # 4. Themes
        if arch_dir and "themes" in sources:
            print(f"  Loading themes...")
            theme_memories = load_themes(arch_dir, name)
            print(f"    → {len(theme_memories)} themes")
            all_memories.extend(theme_memories)

        # 5. Curated documents
        if arch_dir and "curated" in sources:
            print(f"  Loading curated documents...")
            curated_memories = load_curated(arch_dir)
            print(f"    → {len(curated_memories)} curated sections")
            all_memories.extend(curated_memories)

        if not all_memories:
            print(f"  [!] No data found for {instance_id}")
            continue

        # Filter procedural if requested
        if args.no_procedural:
            before = len(all_memories)
            all_memories = [m for m in all_memories if m["scope"] != "procedural"]
            print(f"  Filtered {before - len(all_memories)} procedural memories")

        print(f"\n  Total raw memories: {len(all_memories)}")

        # Merge short messages
        all_memories = merge_short_messages(all_memories)
        print(f"  After merging short messages: {len(all_memories)}")

        # Chunk large memories
        all_memories = chunk_large_memories(all_memories)
        print(f"  After chunking large entries: {len(all_memories)}")

        # Stats
        by_scope = {}
        by_source = {}
        total_chars = 0
        for m in all_memories:
            by_scope[m["scope"]] = by_scope.get(m["scope"], 0) + 1
            by_source[m["source"]] = by_source.get(m["source"], 0) + 1
            total_chars += len(m["content"])

        print(f"\n  By scope:  {json.dumps(by_scope)}")
        print(f"  By source: {json.dumps(by_source)}")
        print(f"  Total chars: {total_chars:,} (~{total_chars // 4:,} tokens)")

        # Estimate embedding cost
        est_tokens = total_chars // 4
        est_cost = est_tokens * 0.02 / 1_000_000
        print(f"  Estimated embedding cost: ${est_cost:.4f}")

        if args.dry_run:
            print(f"\n  [DRY RUN] Would insert {len(all_memories)} memories")
            # Show samples
            print(f"\n  Sample memories:")
            for scope in ["semantic", "episodic", "procedural"]:
                samples = [m for m in all_memories if m["scope"] == scope][:2]
                for s in samples:
                    preview = s["content"][:120].replace("\n", " ")
                    print(f"    [{scope}] {preview}...")
            continue

        # Compute embeddings
        embeddings = None
        if not args.skip_embeddings:
            print(f"\n  Computing embeddings ({len(all_memories)} texts)...")
            texts = [m["content"] for m in all_memories]
            embeddings = compute_embeddings(texts, api_key)

            embedded_count = sum(1 for e in embeddings if e is not None)
            print(f"    → {embedded_count}/{len(all_memories)} successfully embedded")

        # Insert into database
        print(f"\n  Inserting into {db_path}...")
        inserted = insert_memories(db_path, agent_id, all_memories, embeddings)
        print(f"    → {inserted} memories inserted")

        # Final count
        final_count = get_existing_memory_count(db_path, agent_id)
        print(f"  Total memories in db: {final_count}")

    print(f"\nDone.")


if __name__ == "__main__":
    main()
