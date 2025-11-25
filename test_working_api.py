"""
Quick test using the API patterns that we know work from curl testing.
"""

import requests
import xml.etree.ElementTree as ET

# The pattern that WORKS from curl testing
url = "https://digitallibrary.un.org/search"
params = {
    'p': 'A/RES/78',
    'f': 'symbol',  # This is the key - field search
    'of': 'xm',
    'rg': 10
}

print("Making API request...")
response = requests.get(url, params=params)
print(f"Response status: {response.status_code}")
print(f"Response size: {len(response.text)} bytes")

# Parse the XML
root = ET.fromstring(response.text)
ns = {'marc': 'http://www.loc.gov/MARC21/slim'}

# Find all records
records = root.findall('.//marc:record', ns)
print(f"\nFound {len(records)} records\n")

# Parse each record
for i, record in enumerate(records[:5], 1):  # Show first 5
    print(f"=== Record {i} ===")

    # Get record ID
    record_id_elem = record.find('.//marc:controlfield[@tag="001"]', ns)
    record_id = record_id_elem.text.strip() if record_id_elem is not None else "N/A"
    print(f"Record ID: {record_id}")

    # Get symbol
    symbol_field = record.find('.//marc:datafield[@tag="191"]', ns)
    if symbol_field is not None:
        symbol_elem = symbol_field.find('.//marc:subfield[@code="a"]', ns)
        symbol = symbol_elem.text.strip() if symbol_elem is not None else "N/A"
        print(f"Symbol: {symbol}")

    # Get title
    title_field = record.find('.//marc:datafield[@tag="245"]', ns)
    if title_field is not None:
        title_parts = []
        for subfield in title_field.findall('.//marc:subfield', ns):
            if subfield.text:
                title_parts.append(subfield.text.strip())
        title = ' '.join(title_parts)
        print(f"Title: {title[:80]}...")

    # Get date
    date_field = record.find('.//marc:datafield[@tag="269"]', ns)
    if date_field is not None:
        date_elem = date_field.find('.//marc:subfield[@code="a"]', ns)
        date = date_elem.text.strip() if date_elem is not None else "N/A"
        print(f"Date: {date}")

    print()

print(f"\n=== Success! Retrieved {len(records)} GA 78 resolutions ===")
