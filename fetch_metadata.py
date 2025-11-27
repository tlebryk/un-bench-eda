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

def fetch_session_resolutions(session: int, output_file: str = None, base_dir: str = "data"):
    """
    Fetch all resolutions for a given session and save to XML file.

    Args:
        session: GA session number (e.g., 78)
        output_file: Path to save XML (default: {base_dir}/raw/xml/session_{session}_resolutions.xml)
        base_dir: Base data directory (default: "data")
    """
    if output_file is None:
        data_dir = Path(base_dir) / "raw" / "xml"
        data_dir.mkdir(parents=True, exist_ok=True)
        output_file = data_dir / f"session_{session}_resolutions.xml"
    else:
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)

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


def fetch_committee_drafts(committee: int, session: int, output_file: str = None, base_dir: str = "data"):
    """
    Fetch all draft resolutions for a committee and session.

    Args:
        committee: Committee number (1-6)
        session: GA session number
        output_file: Path to save XML (default: {base_dir}/raw/xml/session_{session}_committee_{committee}_drafts.xml)
        base_dir: Base data directory (default: "data")
    """
    if output_file is None:
        data_dir = Path(base_dir) / "raw" / "xml"
        data_dir.mkdir(parents=True, exist_ok=True)
        output_file = data_dir / f"session_{session}_committee_{committee}_drafts.xml"
    else:
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)

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


def fetch_plenary_drafts(session: int, output_file: str = None, base_dir: str = "data"):
    """Fetch plenary draft resolutions (A/{session}/L.*)"""
    if output_file is None:
        data_dir = Path(base_dir) / "raw" / "xml"
        data_dir.mkdir(parents=True, exist_ok=True)
        output_file = data_dir / f"session_{session}_plenary_drafts.xml"
    else:
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)

    url = "https://digitallibrary.un.org/search"
    params = {'p': f'A/{session}/L', 'f': 'symbol', 'of': 'xm', 'rg': 1000}

    print(f"Fetching plenary drafts for session {session}...")
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


def fetch_agenda(session: int, output_file: str = None, base_dir: str = "data"):
    """Fetch session agenda documents (A/{session}/251)"""
    if output_file is None:
        data_dir = Path(base_dir) / "raw" / "xml"
        data_dir.mkdir(parents=True, exist_ok=True)
        output_file = data_dir / f"session_{session}_agenda.xml"
    else:
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)

    url = "https://digitallibrary.un.org/search"
    params = {'p': f'A/{session}/251', 'f': 'symbol', 'of': 'xm', 'rg': 100}

    print(f"Fetching agenda for session {session}...")
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


def fetch_meeting_records(session: int, output_file: str = None, base_dir: str = "data"):
    """Fetch plenary meeting records (A/{session}/PV.*)"""
    if output_file is None:
        data_dir = Path(base_dir) / "raw" / "xml"
        data_dir.mkdir(parents=True, exist_ok=True)
        output_file = data_dir / f"session_{session}_meetings.xml"
    else:
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)

    url = "https://digitallibrary.un.org/search"
    params = {'p': f'A/{session}/PV', 'f': 'symbol', 'of': 'xm', 'rg': 1000}

    print(f"Fetching meeting records for session {session}...")
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


def fetch_voting_records(session: int, output_file: str = None, base_dir: str = "data"):
    """Fetch voting records for resolutions (c=Voting+Data)"""
    if output_file is None:
        data_dir = Path(base_dir) / "raw" / "xml"
        data_dir.mkdir(parents=True, exist_ok=True)
        output_file = data_dir / f"session_{session}_voting.xml"
    else:
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)

    url = "https://digitallibrary.un.org/search"
    params = {'c': 'Voting Data', 'p': f'A/RES/{session}', 'f': 'symbol', 'of': 'xm', 'rg': 1000}

    print(f"Fetching voting records for session {session}...")
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
    import argparse

    parser = argparse.ArgumentParser(description='Fetch UN documents from Digital Library')
    parser.add_argument('session', type=int, help='GA session number (e.g., 78)')
    parser.add_argument('--base-dir', default='data', help='Base directory for data (default: data)')
    parser.add_argument('--types', nargs='+',
                        choices=['resolutions', 'committee-drafts', 'plenary-drafts', 'agenda', 'meetings', 'voting', 'all'],
                        default=['all'],
                        help='Document types to fetch (default: all)')

    args = parser.parse_args()

    session = args.session
    base_dir = args.base_dir
    types = args.types

    # Expand 'all' to all types
    if 'all' in types:
        types = ['resolutions', 'committee-drafts', 'plenary-drafts', 'agenda', 'meetings', 'voting']

    print("="*60)
    print(f"UN METADATA FETCHER - Session {session}")
    print(f"Base directory: {base_dir}")
    print(f"Fetching: {', '.join(types)}")
    print("="*60)

    if 'resolutions' in types:
        print("\n[1/6] Fetching resolutions...")
        fetch_session_resolutions(session, base_dir=base_dir)

    if 'committee-drafts' in types:
        print("\n[2/6] Fetching committee drafts...")
        for committee in range(1, 7):
            fetch_committee_drafts(committee, session, base_dir=base_dir)

    if 'plenary-drafts' in types:
        print("\n[3/6] Fetching plenary drafts...")
        fetch_plenary_drafts(session, base_dir=base_dir)

    if 'agenda' in types:
        print("\n[4/6] Fetching agenda...")
        fetch_agenda(session, base_dir=base_dir)

    if 'meetings' in types:
        print("\n[5/6] Fetching meeting records...")
        fetch_meeting_records(session, base_dir=base_dir)

    if 'voting' in types:
        print("\n[6/6] Fetching voting records...")
        fetch_voting_records(session, base_dir=base_dir)

    print("\n" + "="*60)
    print("✓ Done!")
    print("="*60)
