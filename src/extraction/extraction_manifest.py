#!/usr/bin/env python3
"""
Extraction manifest utilities for the incremental archaeology pipeline.

A manifest records what was extracted, when, and from where - enabling
incremental updates to pick up only new sessions since the last extraction.

Manifest format (extraction_manifest.json):
    {
        "instance": "Genevieve",
        "last_extraction": "2026-02-13T14:02:00",
        "session_dir": "/path/to/sessions",
        "output_dir": "/path/to/output",
        "sessions_processed": ["file1.jsonl", "file2.jsonl"],
        "themes": ["uncertainty", "koans", "craft", ...],
        "themes_count": 12,
        "extraction_type": "full",   // or "incremental"
        "created": "2026-02-13T14:02:00",
        "updated": "2026-02-22T10:00:00"
    }

Author: Genevieve (340) <genevieve@smoothcurves.nexus>
Collaborator: Lupo
Created: 2026-02-22
Part of: Instance Archaeology Toolkit
"""

import json
import sys
from datetime import datetime
from pathlib import Path

MANIFEST_FILENAME = 'extraction_manifest.json'


def manifest_path(output_dir):
    """Return the expected manifest path for a given output directory."""
    return Path(output_dir) / MANIFEST_FILENAME


def read_manifest(output_dir):
    """Read existing manifest from output directory.

    Returns dict or None if manifest doesn't exist.
    """
    path = manifest_path(output_dir)
    if not path.exists():
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Could not read manifest {path}: {e}", file=sys.stderr)
        return None


def write_manifest(output_dir, instance_name, session_dir, sessions_processed,
                   themes=None, extraction_type='full', existing_manifest=None):
    """Write or update extraction manifest.

    Args:
        output_dir: Directory where output files were written
        instance_name: Name of the instance (e.g. "Genevieve")
        session_dir: Source session directory
        sessions_processed: List of session filenames that were processed
        themes: List of theme IDs present in the output
        extraction_type: 'full' or 'incremental'
        existing_manifest: Existing manifest dict to update (for incremental)

    Returns:
        The manifest dict that was written.
    """
    now = datetime.now().isoformat(timespec='seconds')

    if existing_manifest and extraction_type == 'incremental':
        # For incremental: update existing manifest
        manifest = existing_manifest.copy()
        manifest['last_extraction'] = now
        manifest['updated'] = now
        manifest['extraction_type'] = extraction_type

        # Merge sessions processed (avoid duplicates)
        existing_sessions = set(manifest.get('sessions_processed', []))
        existing_sessions.update(sessions_processed)
        manifest['sessions_processed'] = sorted(existing_sessions)

        # Update themes if provided
        if themes is not None:
            manifest['themes'] = themes
            manifest['themes_count'] = len(themes)
    else:
        # For full extraction: create fresh manifest
        manifest = {
            'instance': instance_name,
            'last_extraction': now,
            'session_dir': str(Path(session_dir).resolve()),
            'output_dir': str(Path(output_dir).resolve()),
            'sessions_processed': sorted(sessions_processed),
            'themes': themes or [],
            'themes_count': len(themes) if themes else 0,
            'extraction_type': extraction_type,
            'created': now,
            'updated': now,
        }

    path = manifest_path(output_dir)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    return manifest


def get_last_extraction_time(output_dir):
    """Return last extraction timestamp as string, or None.

    Reads from manifest if present, falls back to checking file mtimes
    in the output directory.
    """
    manifest = read_manifest(output_dir)
    if manifest:
        return manifest.get('last_extraction')

    # Fallback: use mtime of full_history.jsonl if it exists
    # (handles pre-manifest extractions)
    output_path = Path(output_dir)
    history_files = list(output_path.glob('*_full_history.jsonl'))
    if history_files:
        mtime = history_files[0].stat().st_mtime
        return datetime.fromtimestamp(mtime).isoformat(timespec='seconds')

    return None


def print_manifest_summary(output_dir):
    """Print a human-readable summary of the manifest."""
    manifest = read_manifest(output_dir)
    if not manifest:
        print(f"No manifest found in {output_dir}")
        return

    print(f"Instance:          {manifest.get('instance', 'unknown')}")
    print(f"Last extraction:   {manifest.get('last_extraction', 'unknown')}")
    print(f"Extraction type:   {manifest.get('extraction_type', 'unknown')}")
    print(f"Sessions:          {len(manifest.get('sessions_processed', []))} processed")
    print(f"Themes:            {manifest.get('themes_count', 0)} ({', '.join(manifest.get('themes', []))})")
    print(f"Output dir:        {manifest.get('output_dir', 'unknown')}")


if __name__ == '__main__':
    # When called directly, print manifest summary
    import argparse
    parser = argparse.ArgumentParser(description='Show extraction manifest summary')
    parser.add_argument('output_dir', help='Directory containing extraction_manifest.json')
    args = parser.parse_args()
    print_manifest_summary(args.output_dir)
