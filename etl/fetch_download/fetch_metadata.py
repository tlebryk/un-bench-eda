"""
Step 1: Fetch metadata XML from UN Digital Library API

This script fetches and dumps XML responses to files for later parsing.
Saves to: data/raw/xml/
"""

import requests
import sys
import re
import xml.etree.ElementTree as ET
from pathlib import Path

# Data directory structure
DATA_DIR = Path("data/raw/xml")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Default records per page for pagination (conservative to avoid server limits)
DEFAULT_RG = 200


def fetch_paginated_xml(url: str, params: dict, timeout: int = 30, records_per_page: int = DEFAULT_RG) -> str:
    """
    Fetch all records from a paginated UN Digital Library API request.
    
    The API returns XML with a comment header indicating total results:
    <!-- Search-Engine-Total-Number-Of-Results: 12 -->
    
    Args:
        url: API endpoint URL
        params: Base parameters for the search (will be modified for pagination)
        timeout: Request timeout in seconds
        records_per_page: Number of records per page (rg parameter)
    
    Returns:
        Combined XML string with all records in a single <collection> element
    """
    # Extract base params and ensure we have the right format
    base_params = params.copy()
    base_params['of'] = 'xm'  # Ensure XML output
    base_params['rg'] = records_per_page
    
    # Make first request
    print(f"  Making initial request (rg={records_per_page})...")
    response = requests.get(url, params=base_params, timeout=timeout)
    
    if response.status_code != 200:
        raise Exception(f"API request failed with status {response.status_code}")
    
    # Parse total number of results from XML comment
    # Format: <!-- Search-Engine-Total-Number-Of-Results: 12 -->
    total_results_match = re.search(
        r'<!--\s*Search-Engine-Total-Number-Of-Results:\s*(\d+)\s*-->',
        response.text
    )
    
    if total_results_match:
        total_results = int(total_results_match.group(1))
        print(f"  Total results reported: {total_results}")
    else:
        # Fallback: count records in first response
        first_count = response.text.count('<record>')
        print(f"  Could not parse total from header, found {first_count} records in first page")
        total_results = first_count
    
    # Extract records from first response
    all_records = []
    use_regex = False  # Track if we're using regex fallback
    namespace = None  # Track namespace for proper XML construction
    
    # Parse XML to extract records
    try:
        root = ET.fromstring(response.text)
        # Check for namespace
        if root.tag.startswith('{'):
            namespace = root.tag.split('}')[0][1:]
        # Find all record elements (handle both with and without namespace)
        ns = {'marc': 'http://www.loc.gov/MARC21/slim'} if namespace else {}
        records = root.findall('.//marc:record', ns) if namespace else root.findall('.//record')
        if not records:
            # Try without namespace prefix
            records = root.findall('.//{http://www.loc.gov/MARC21/slim}record') or root.findall('.//record')
        all_records.extend(records)
        print(f"  Page 1: Retrieved {len(records)} records")
    except ET.ParseError as e:
        # Fallback: extract records using regex if XML parsing fails
        print(f"  Warning: XML parsing failed, using regex fallback: {e}")
        use_regex = True
        record_matches = re.findall(r'<record[^>]*>.*?</record>', response.text, re.DOTALL)
        all_records.extend(record_matches)
        print(f"  Page 1: Retrieved {len(record_matches)} records (regex)")
    
    # If we have more results, fetch additional pages
    # Also check if we got exactly records_per_page - this might indicate more results
    # even if the header says total_results == records_per_page (API might cap the count)
    first_page_count = len(all_records)
    should_paginate = total_results > records_per_page or (first_page_count == records_per_page and total_results == records_per_page)
    
    if should_paginate:
        # Calculate number of pages based on reported total, but also continue if we hit the limit
        if total_results > records_per_page:
            num_pages = (total_results + records_per_page - 1) // records_per_page  # Ceiling division
        else:
            # If total equals records_per_page but we got exactly that many, try at least one more page
            num_pages = 2
        
        print(f"  Fetching additional pages (estimated {num_pages - 1} more)...")
        
        page = 2
        while True:
            jrec = (page - 1) * records_per_page + 1  # jrec is 1-based
            page_params = base_params.copy()
            page_params['jrec'] = jrec
            
            print(f"  Page {page} (jrec={jrec})...", end=' ')
            page_response = requests.get(url, params=page_params, timeout=timeout)
            
            if page_response.status_code != 200:
                print(f"Error: {page_response.status_code}")
                break
            
            # Extract records from this page
            if use_regex:
                page_record_matches = re.findall(r'<record[^>]*>.*?</record>', page_response.text, re.DOTALL)
                page_count = len(page_record_matches)
                all_records.extend(page_record_matches)
                print(f"Retrieved {page_count} records (regex)")
            else:
                try:
                    page_root = ET.fromstring(page_response.text)
                    ns = {'marc': 'http://www.loc.gov/MARC21/slim'} if namespace else {}
                    page_records = page_root.findall('.//marc:record', ns) if namespace else page_root.findall('.//record')
                    if not page_records:
                        page_records = page_root.findall('.//{http://www.loc.gov/MARC21/slim}record') or page_root.findall('.//record')
                    page_count = len(page_records)
                    all_records.extend(page_records)
                    print(f"Retrieved {page_count} records")
                except ET.ParseError:
                    # Fallback to regex for this page
                    use_regex = True
                    page_record_matches = re.findall(r'<record[^>]*>.*?</record>', page_response.text, re.DOTALL)
                    page_count = len(page_record_matches)
                    all_records.extend(page_record_matches)
                    print(f"Retrieved {page_count} records (regex)")
            
            # Stop if we got fewer records than records_per_page (last page)
            # or if we've fetched enough pages based on the reported total
            if page_count < records_per_page:
                break
            if total_results > records_per_page and page >= num_pages:
                break
            
            page += 1
    
    # Combine all records into a single XML collection
    # Update header comment with actual total retrieved
    actual_total = len(all_records)
    header_comment = f"<!-- Search-Engine-Total-Number-Of-Results: {actual_total} -->\n"
    
    # Build the combined XML
    if not all_records:
        records_xml = ""
    elif use_regex or isinstance(all_records[0], str):
        # Records are strings (regex fallback)
        records_xml = '\n'.join(all_records)
    else:
        # Records are ElementTree elements
        records_xml = '\n'.join(ET.tostring(record, encoding='unicode') for record in all_records)
    
    # Determine namespace attribute for collection tag
    ns_attr = ' xmlns="http://www.loc.gov/MARC21/slim"' if namespace else ''
    
    combined_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
{header_comment}<collection{ns_attr}>
{records_xml}
</collection>"""
    
    print(f"  Total records retrieved: {len(all_records)}")
    return combined_xml


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
        'p': f'191__a:"A/RES/{session}/*"',  # MARC field syntax with wildcard
        # TODO: maybe we can filter for english language at this level?
    }

    print(f"Fetching resolutions for session {session}...")
    
    try:
        combined_xml = fetch_paginated_xml(url, params, timeout=30)
        Path(output_file).write_text(combined_xml, encoding='utf-8')
        print(f"Saved to: {output_file}")
        return output_file
    except Exception as e:
        print(f"Error: {e}")
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
        'p': f'191__a:"A/C.{committee}/{session}/L.*"',  # MARC field syntax with wildcard
    }

    print(f"Fetching Committee {committee} drafts for session {session}...")

    try:
        combined_xml = fetch_paginated_xml(url, params, timeout=30)
        Path(output_file).write_text(combined_xml, encoding='utf-8')
        print(f"Saved to: {output_file}")
        return output_file
    except Exception as e:
        print(f"Error: {e}")
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
    params = {'p': f'191__a:"A/{session}/L.*"'}

    print(f"Fetching plenary drafts for session {session}...")
    
    try:
        combined_xml = fetch_paginated_xml(url, params, timeout=30)
        Path(output_file).write_text(combined_xml, encoding='utf-8')
        print(f"Saved to: {output_file}")
        return output_file
    except Exception as e:
        print(f"Error: {e}")
        return None


def fetch_agenda(session: int, output_file: str = None, base_dir: str = "data"):
    """Fetch session agenda documents (A/{session}/251 and A/{session}/252)"""
    if output_file is None:
        data_dir = Path(base_dir) / "raw" / "xml"
        data_dir.mkdir(parents=True, exist_ok=True)
        output_file = data_dir / f"session_{session}_agenda.xml"
    else:
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)

    url = "https://digitallibrary.un.org/search"
    
    # Fetch both 251 (agenda) and 252 (allocation of work) documents
    # Use OR syntax to get both in a single query
    params = {'p': f'191__a:"A/{session}/251*" OR 191__a:"A/{session}/252*"'}

    print(f"Fetching agenda (251) and allocation of work (252) for session {session}...")
    
    try:
        combined_xml = fetch_paginated_xml(url, params, timeout=30)
        Path(output_file).write_text(combined_xml, encoding='utf-8')
        print(f"Saved to: {output_file}")
        return output_file
    except Exception as e:
        print(f"Error: {e}")
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
    # Use MARC field syntax to get actual meeting documents (not speeches)
    params = {'p': f'191__a:"A/{session}/PV.*"'}

    print(f"Fetching meeting records for session {session}...")
    
    try:
        combined_xml = fetch_paginated_xml(url, params, timeout=30)
        Path(output_file).write_text(combined_xml, encoding='utf-8')
        print(f"Saved to: {output_file}")
        return output_file
    except Exception as e:
        print(f"Error: {e}")
        return None


def fetch_committee_reports(session: int, output_file: str = None, base_dir: str = "data"):
    """
    Fetch all committee reports for a session.
    
    Committee reports are documents like A/78/411 (report of the 1st Committee).
    They typically fall in the A/{session}/4xx range (approximately 400-499).
    These reports contain the committee's recommendations and are distinct from
    committee drafts (A/C.N/{session}/L.*).
    
    Args:
        session: GA session number (e.g., 78)
        output_file: Path to save XML (default: {base_dir}/raw/xml/session_{session}_committee_reports.xml)
        base_dir: Base data directory (default: "data")
    """
    if output_file is None:
        data_dir = Path(base_dir) / "raw" / "xml"
        data_dir.mkdir(parents=True, exist_ok=True)
        output_file = data_dir / f"session_{session}_committee_reports.xml"
    else:
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)

    url = "https://digitallibrary.un.org/search"
    params = {
        'p': f'191__a:"A/{session}/*"',  # MARC field syntax with wildcard
        "fct__1": "Reports",
        "fct__2": "General Assembly",
    }

    print(f"Fetching committee reports for session {session}...")
    
    try:
        combined_xml = fetch_paginated_xml(url, params, timeout=30)
        Path(output_file).write_text(combined_xml, encoding='utf-8')
        print(f"Saved to: {output_file}")
        return output_file
    except Exception as e:
        print(f"Error: {e}")
        return None


def fetch_committee_summary_records(committee: int, session: int, output_file: str = None, base_dir: str = "data"):
    """
    Fetch committee summary records (SR documents).

    Example: A/C.3/78/SR.16 = Third Committee, Session 78, Summary Record 16

    Args:
        committee: Committee number (1-6)
        session: GA session number (e.g., 78)
        output_file: Path to save XML (default: {base_dir}/raw/xml/session_{session}_committee_{committee}_summary_records.xml)
        base_dir: Base data directory (default: "data")
    """
    if output_file is None:
        data_dir = Path(base_dir) / "raw" / "xml"
        data_dir.mkdir(parents=True, exist_ok=True)
        output_file = data_dir / f"session_{session}_committee_{committee}_summary_records.xml"
    else:
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)

    url = "https://digitallibrary.un.org/search"
    # SR = Summary Record
    params = {'p': f'191__a:"A/C.{committee}/{session}/SR.*"'}

    print(f"Fetching Committee {committee} summary records for session {session}...")

    try:
        combined_xml = fetch_paginated_xml(url, params, timeout=30)
        Path(output_file).write_text(combined_xml, encoding='utf-8')
        print(f"Saved to: {output_file}")
        return output_file
    except Exception as e:
        print(f"Error: {e}")
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
    params = {'c': 'Voting Data', 'p': f'191__a:"A/RES/{session}/*"'}

    print(f"Fetching voting records for session {session}...")
    
    try:
        combined_xml = fetch_paginated_xml(url, params, timeout=30)
        Path(output_file).write_text(combined_xml, encoding='utf-8')
        print(f"Saved to: {output_file}")
        return output_file
    except Exception as e:
        print(f"Error: {e}")
        return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Fetch UN documents from Digital Library')
    parser.add_argument('session', type=int, help='GA session number (e.g., 78)')
    parser.add_argument('--base-dir', default='data', help='Base directory for data (default: data)')
    parser.add_argument('--types', nargs='+',
                        choices=['resolutions', 'committee-drafts', 'committee-reports', 'committee-summary-records', 'plenary-drafts', 'agenda', 'meetings', 'voting', 'all'],
                        default=['all'],
                        help='Document types to fetch (default: all)')

    args = parser.parse_args()

    session = args.session
    base_dir = args.base_dir
    types = args.types

    # Expand 'all' to all types
    if 'all' in types:
        types = ['resolutions', 'committee-drafts', 'committee-reports', 'committee-summary-records', 'plenary-drafts', 'agenda', 'meetings', 'voting']

    print("="*60)
    print(f"UN METADATA FETCHER - Session {session}")
    print(f"Base directory: {base_dir}")
    print(f"Fetching: {', '.join(types)}")
    print("="*60)

    if 'resolutions' in types:
        print("\n[1/8] Fetching resolutions...")
        fetch_session_resolutions(session, base_dir=base_dir)

    if 'committee-drafts' in types:
        print("\n[2/8] Fetching committee drafts...")
        for committee in range(1, 7):
            fetch_committee_drafts(committee, session, base_dir=base_dir)

    if 'committee-reports' in types:
        print("\n[3/8] Fetching committee reports...")
        fetch_committee_reports(session, base_dir=base_dir)

    if 'committee-summary-records' in types:
        print("\n[4/8] Fetching committee summary records...")
        for committee in range(1, 7):
            fetch_committee_summary_records(committee, session, base_dir=base_dir)

    if 'plenary-drafts' in types:
        print("\n[5/8] Fetching plenary drafts...")
        fetch_plenary_drafts(session, base_dir=base_dir)

    if 'agenda' in types:
        print("\n[6/8] Fetching agenda...")
        fetch_agenda(session, base_dir=base_dir)

    if 'meetings' in types:
        print("\n[7/8] Fetching meeting records...")
        fetch_meeting_records(session, base_dir=base_dir)

    if 'voting' in types:
        print("\n[8/8] Fetching voting records...")
        fetch_voting_records(session, base_dir=base_dir)

    print("\n" + "="*60)
    print("✓ Done!")
    print("="*60)
