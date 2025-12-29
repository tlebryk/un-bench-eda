#!/usr/bin/env python3
"""
Test script for new document types (agenda, plenary drafts, voting records, meetings)

This is a simple wrapper around fetch_metadata.py that tests all new document types.
"""

import subprocess
import sys

def main():
    """Test fetching all new document types for session 78"""

    print("Testing all document types for session 78...")
    print("="*60)

    # Use fetch_metadata.py with command line args
    result = subprocess.run([
        sys.executable,
        'fetch_metadata.py',
        '78',
        '--base-dir', 'test_data'
    ])

    if result.returncode == 0:
        print("\n" + "="*60)
        print("✓ All tests completed successfully!")
        print("\nNext steps:")
        print("  1. Parse XML: python3 parse_metadata.py test_data/raw/xml/session_78_resolutions.xml")
        print("  2. Download PDFs: python3 download_pdfs.py test_data/parsed/metadata/session_78_resolutions.json --max-docs 5")
        print("="*60)
    else:
        print("\n✗ Tests failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
