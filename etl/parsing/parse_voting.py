import xml.etree.ElementTree as ET
from pathlib import Path
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def parse_voting_xml(xml_file: Path, output_dir: Path):
    """
    Parse voting MARCXML file and save individual JSON files per resolution/vote.
    """
    if not xml_file.exists():
        logger.error(f"File not found: {xml_file}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        ns = {'marc': 'http://www.loc.gov/MARC21/slim'}
        
        records = root.findall('.//marc:record', ns)
        logger.info(f"Found {len(records)} records in {xml_file}")
        
        parsed_count = 0
        
        for record in records:
            # Extract basic metadata
            f001 = record.find("marc:controlfield[@tag='001']", ns)
            record_id = f001.text if f001 is not None else "unknown"
            
            # Resolution Symbol (791 $a)
            f791 = record.find(".//marc:datafield[@tag='791']/marc:subfield[@code='a']", ns)
            symbol = f791.text if f791 is not None else f"vote_{record_id}"
            
            # Title (245 $a $b $c)
            title_parts = []
            for code in ['a', 'b', 'c']:
                sub = record.find(f".//marc:datafield[@tag='245']/marc:subfield[@code='{code}']", ns)
                if sub is not None:
                    title_parts.append(sub.text)
            title = " ".join(title_parts)
            
            # Date (269 $a)
            f269 = record.find(".//marc:datafield[@tag='269']/marc:subfield[@code='a']", ns)
            date = f269.text if f269 is not None else None
            
            # Vote Summary (591 $a) - e.g. "RECORDED - No machine generated vote" or stats
            # Actually, the vote counts are often in 996
            # 590: Vote type (Vote / Without Vote)
            f590 = record.find(".//marc:datafield[@tag='590']/marc:subfield[@code='a']", ns)
            vote_type = f590.text if f590 is not None else "Unknown"
            
            # Vote Counts (996)
            # $b: Yes, $c: No, $d: Abstain, $e: Non-voting, $f: Total
            counts = {}
            f996 = record.find(".//marc:datafield[@tag='996']", ns)
            if f996 is not None:
                counts = {
                    "yes": int(f996.find("marc:subfield[@code='b']", ns).text or 0),
                    "no": int(f996.find("marc:subfield[@code='c']", ns).text or 0),
                    "abstain": int(f996.find("marc:subfield[@code='d']", ns).text or 0),
                    "non_voting": int(f996.find("marc:subfield[@code='e']", ns).text or 0),
                    "total": int(f996.find("marc:subfield[@code='f']", ns).text or 0),
                }

            # Individual Votes (967)
            individual_votes = []
            for field in record.findall(".//marc:datafield[@tag='967']", ns):
                country = field.find("marc:subfield[@code='e']", ns)
                vote_code = field.find("marc:subfield[@code='d']", ns)
                
                if country is not None:
                    individual_votes.append({
                        "country": country.text,
                        "vote": vote_code.text if vote_code is not None else "X" # X usually means non-voting present or similar? Or just absent code.
                    })
            
            # Construct output object
            voting_data = {
                "record_id": record_id,
                "symbol": symbol,
                "title": title,
                "date": date,
                "vote_type": vote_type,
                "counts": counts,
                "votes": individual_votes
            }
            
            # Sanitize filename
            safe_filename = symbol.replace("/", "_").replace(" ", "_") + ".json"
            output_file = output_dir / safe_filename
            
            with open(output_file, 'w') as f:
                json.dump(voting_data, f, indent=2)
                
            parsed_count += 1
            
        logger.info(f"Successfully parsed {parsed_count} voting records to {output_dir}")
        
    except Exception as e:
        logger.error(f"Failed to parse XML: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("xml_file", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("data/parsed/voting"))
    args = parser.parse_args()
    
    parse_voting_xml(args.xml_file, args.output_dir)
