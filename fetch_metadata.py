"""
Step 1: Fetch metadata XML from UN Digital Library API

This script fetches and dumps XML responses to files for later parsing.
Saves to: data/raw/xml/
"""

import requests
import sys
from pathlib import Path

# Data directory structure
DATA_DIR = Path("data/raw/xml")
DATA_DIR.mkdir(parents=True, exist_ok=True)

def fetch_session_resolutions(session: int, output_file: str = None):
    """
    Fetch all resolutions for a given session and save to XML file.

    Args:
        session: GA session number (e.g., 78)
        output_file: Path to save XML (default: data/raw/xml/session_{session}_resolutions.xml)
    """
    if output_file is None:
        output_file = DATA_DIR / f"session_{session}_resolutions.xml"
    else:
        output_file = Path(output_file)

    url = "https://digitallibrary.un.org/search"
    params = {
        'p': f'A/RES/{session}',
        'f': 'symbol',  # Field-specific search
        'of': 'xm',     # MARCXML format
        'rg': 1000      # Max results per page
        # TODO: might have to bump and/or paginate using jrec...
        # TODO: maybe we can filter for english langauge at this level? 
    }

    print(f"Fetching resolutions for session {session}...")
    print(f"URL: {url}")
    print(f"Params: {params}")

    response = requests.get(url, params=params, timeout=30)
    print(f"Status: {response.status_code}")
    print(f"Size: {len(response.text)} bytes")

    if response.status_code == 200:
        Path(output_file).write_text(response.text, encoding='utf-8')
        print(f"Saved to: {output_file}")

        # Quick count of records
        record_count = response.text.count('<record>')
        print(f"Records found: {record_count}")
        return output_file
    else:
        print(f"Error: {response.status_code}")
        return None


def fetch_committee_drafts(committee: int, session: int, output_file: str = None):
    """
    Fetch all draft resolutions for a committee and session.

    Args:
        committee: Committee number (1-6)
        session: GA session number
        output_file: Path to save XML (default: data/raw/xml/session_{session}_committee_{committee}_drafts.xml)
    """
    if output_file is None:
        output_file = DATA_DIR / f"session_{session}_committee_{committee}_drafts.xml"
    else:
        output_file = Path(output_file)

    url = "https://digitallibrary.un.org/search"
    params = {
        'p': f'A/C.{committee}/{session}/L',
        'f': 'symbol',
        'of': 'xm',
        'rg': 1000
    }

    print(f"Fetching Committee {committee} drafts for session {session}...")

    response = requests.get(url, params=params, timeout=30)
    print(f"Status: {response.status_code}, Size: {len(response.text)} bytes")

    if response.status_code == 200:
        Path(output_file).write_text(response.text, encoding='utf-8')
        record_count = response.text.count('<record>')
        print(f"Saved {record_count} records to: {output_file}")
        return output_file
    else:
        print(f"Error: {response.status_code}")
        return None


if __name__ == "__main__":
    session = int(sys.argv[1]) if len(sys.argv) > 1 else 78

    print("="*60)
    print(f"UN METADATA FETCHER - Session {session}")
    print("="*60)

    # Fetch resolutions
    fetch_session_resolutions(session)

    print()

    # Fetch committee drafts
    for committee in range(1, 7):
        fetch_committee_drafts(committee, session)
        print()
