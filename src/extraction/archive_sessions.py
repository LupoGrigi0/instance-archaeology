#!/usr/bin/env python3
"""
Archive Session Files for Instance Archaeology

Creates a zip archive of all raw .jsonl session files and cleans up.
This is the FINAL step in the archaeology process - runs only after
all other processing is complete.

Operations:
1. Move consolidated .jsonl to raw/sessions/ directory
2. Create sessions.zip containing all .jsonl files
3. Remove the unzipped .jsonl files (summaries are preserved)

Usage:
    python3 archive_sessions.py -d /path/to/instance/output/

Author: Axiom <axiom-2615@smoothcurves.nexus>
Collaborator: Lupo
Created: 2026-01-29
Part of: Instance Archaeology Toolkit
"""

import argparse
import shutil
import zipfile
import sys
from pathlib import Path
from datetime import datetime


def archive_sessions(output_dir: Path, instance_name: str = None, dry_run: bool = False) -> dict:
    """Archive all .jsonl files into sessions.zip.

    Args:
        output_dir: The instance output directory (e.g., archaeology-output/Axiom/)
        instance_name: Optional instance name for finding consolidated file
        dry_run: If True, show what would happen without doing it

    Returns:
        dict with archive results
    """
    output_dir = Path(output_dir)
    raw_dir = output_dir / 'raw'
    sessions_dir = raw_dir / 'sessions'

    if not output_dir.exists():
        print(f"Error: Output directory not found: {output_dir}", file=sys.stderr)
        sys.exit(1)

    # Create raw/sessions if needed
    if not dry_run:
        sessions_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Find and move consolidated .jsonl
    # Look for {instance}_consolidated.jsonl or full_narrative.jsonl in output_dir
    consolidated_files = list(output_dir.glob('*_consolidated.jsonl'))
    if not consolidated_files:
        consolidated_files = list(output_dir.glob('*_full_history.jsonl'))

    consolidated_moved = []
    for cf in consolidated_files:
        dest = sessions_dir / cf.name
        print(f"Moving consolidated file: {cf.name} -> raw/sessions/")
        if not dry_run:
            shutil.move(str(cf), str(dest))
        consolidated_moved.append(cf.name)

    # Step 2: Find all .jsonl files in sessions dir
    jsonl_files = list(sessions_dir.glob('*.jsonl'))

    if not jsonl_files:
        print("Warning: No .jsonl files found to archive", file=sys.stderr)
        return {
            'archived': [],
            'zip_path': None,
            'consolidated_moved': consolidated_moved
        }

    # Step 3: Create zip archive
    zip_path = raw_dir / 'sessions.zip'
    archived = []
    total_size = 0

    print(f"\nCreating archive: {zip_path}")
    print(f"Files to archive: {len(jsonl_files)}")

    if not dry_run:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for jsonl_file in jsonl_files:
                file_size = jsonl_file.stat().st_size
                total_size += file_size

                # Add to zip with just the filename (not full path)
                zf.write(jsonl_file, jsonl_file.name)
                print(f"  Added: {jsonl_file.name} ({file_size:,} bytes)")

                archived.append({
                    'name': jsonl_file.name,
                    'size': file_size
                })
    else:
        for jsonl_file in jsonl_files:
            file_size = jsonl_file.stat().st_size
            total_size += file_size
            print(f"  Would add: {jsonl_file.name} ({file_size:,} bytes)")
            archived.append({
                'name': jsonl_file.name,
                'size': file_size
            })

    # Step 4: Verify zip and remove originals
    if not dry_run and zip_path.exists():
        # Verify the zip file
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                if zf.testzip() is not None:
                    print("Error: Zip file verification failed!", file=sys.stderr)
                    sys.exit(1)

                zip_contents = zf.namelist()
                print(f"\nZip verified: {len(zip_contents)} files")
        except zipfile.BadZipFile:
            print("Error: Created zip file is corrupted!", file=sys.stderr)
            sys.exit(1)

        # Remove original .jsonl files (keep summaries)
        print("\nRemoving archived .jsonl files...")
        for jsonl_file in jsonl_files:
            print(f"  Removing: {jsonl_file.name}")
            jsonl_file.unlink()
    else:
        print("\nDry run - would remove archived .jsonl files")

    # Report results
    zip_size = zip_path.stat().st_size if zip_path.exists() and not dry_run else 0
    compression_ratio = (1 - zip_size / total_size) * 100 if total_size > 0 else 0

    return {
        'archived': archived,
        'file_count': len(archived),
        'total_size_uncompressed': total_size,
        'zip_size': zip_size,
        'compression_ratio': compression_ratio,
        'zip_path': str(zip_path),
        'consolidated_moved': consolidated_moved,
        'summaries_preserved': len(list(sessions_dir.glob('*_summary.md')))
    }


def main():
    parser = argparse.ArgumentParser(
        description='Archive session files (FINAL step in archaeology process)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
    # Archive sessions for an instance
    %(prog)s -d /mnt/coordinaton_mcp_data/archaeology-output/Axiom/

    # Dry run to see what would happen
    %(prog)s -d /mnt/coordinaton_mcp_data/archaeology-output/Axiom/ --dry-run

IMPORTANT: This should be the LAST step in the archaeology process.
Only run after all other processing (extraction, curation, synthesis) is complete.
        '''
    )

    parser.add_argument('-d', '--directory', required=True,
                        help='Instance output directory')
    parser.add_argument('-n', '--instance', default=None,
                        help='Instance name (helps find consolidated file)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would happen without doing it')

    args = parser.parse_args()

    print("=" * 60)
    print("ARCHIVE SESSIONS - Final Cleanup Step")
    print("=" * 60)
    print()
    print(f"Output directory: {args.directory}")
    if args.dry_run:
        print("MODE: Dry run (no changes will be made)")
    print()

    result = archive_sessions(args.directory, args.instance, args.dry_run)

    print()
    print("=" * 60)
    print("Archive Complete")
    print("=" * 60)
    print(f"Files archived: {result['file_count']}")
    print(f"Uncompressed size: {result['total_size_uncompressed']:,} bytes")
    if result['zip_size']:
        print(f"Compressed size: {result['zip_size']:,} bytes")
        print(f"Compression ratio: {result['compression_ratio']:.1f}%")
    if result['consolidated_moved']:
        print(f"Consolidated files moved: {', '.join(result['consolidated_moved'])}")
    print(f"Session summaries preserved: {result['summaries_preserved']}")
    print(f"Archive location: {result['zip_path']}")


if __name__ == '__main__':
    main()
