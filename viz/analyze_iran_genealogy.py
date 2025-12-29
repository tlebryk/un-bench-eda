#!/usr/bin/env python3
"""
Comprehensive analysis of A/RES/78/220 genealogy (Iran human rights resolution)

This script extracts all detailed information across the resolution lifecycle:
- Agenda item
- Draft resolution (committee)
- Committee report (with voting)
- Final resolution (plenary)
- Plenary meeting (with statements and voting)

Goal: Extract maximum detail for gym environment construction
"""

import json
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict

class GenealogyAnalyzer:
    def __init__(self, base_path: str = "/Users/theolebryk/projects/un_draft"):
        self.base_path = Path(base_path)
        self.genealogy = {
            "resolution_symbol": "A/RES/78/220",
            "title": "Situation of human rights in the Islamic Republic of Iran",
            "agenda_item": "71c - Human rights situations and reports",
            "stages": {}
        }

    def load_json(self, filepath: Path) -> Dict:
        """Load JSON file"""
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)

    def analyze_agenda(self):
        """Extract agenda item information"""
        print("📋 Analyzing Agenda Item A/78/251 (71c)...")

        agenda_path = self.base_path / "data/parsed/pdfs/agenda/A_78_251.json"
        agenda_data = self.load_json(agenda_path)

        # Find item 71c
        item_71c = None
        for item in agenda_data['items']:
            if item.get('item_number') == 71 and item.get('sub_item') == 'c':
                item_71c = item
                break

        self.genealogy['stages']['agenda'] = {
            "symbol": "A/78/251",
            "item_number": "71",
            "sub_item": "c",
            "title": item_71c.get('text', '') if item_71c else "",
            "date": agenda_data['metadata']['date']
        }

    def analyze_draft(self):
        """Extract draft resolution details"""
        print("📝 Analyzing Draft Resolution A/C.3/78/L.41...")

        draft_path = self.base_path / "data/parsed/pdfs/drafts/A_C.3_78_L.41.json"
        draft_data = self.load_json(draft_path)

        self.genealogy['stages']['draft'] = {
            "symbol": "A/C.3/78/L.41",
            "committee": 3,
            "date": draft_data['metadata']['date'],
            "distribution": draft_data['metadata']['distribution'],
            "language": draft_data['metadata']['original_language'],
            "session": draft_data['metadata']['session_name'],
            "text": draft_data['draft_text'],
            "word_count": draft_data['stats']['word_count'],
            "line_count": draft_data['stats']['line_count'],
            "has_annex": draft_data['stats']['has_annex']
        }

    def analyze_committee_report(self):
        """Extract committee report with voting and proceedings"""
        print("🏛️  Analyzing Committee Report A/78/481/Add.3...")

        # First get HTML metadata
        html_path = self.base_path / "data/parsed/html/committee-reports/A_78_481_Add.3_record_4029949.json"
        html_data = self.load_json(html_path)

        # Then get PDF parse with detailed content
        pdf_path = self.base_path / "data/documents/pdfs/committee-reports/A_78_481_Add.3_parsed.json"
        pdf_data = self.load_json(pdf_path)

        # Find the Iran resolution section (L.41)
        iran_section = None
        for item in pdf_data['items']:
            if item.get('draft_symbol') == 'A/C.3/78/L.41':
                iran_section = item
                break

        if iran_section:
            # Extract detailed voting info from text
            vote_details = iran_section.get('vote_details', {})

            self.genealogy['stages']['committee_report'] = {
                "symbol": "A/78/481/Add.3",
                "date": html_data['metadata']['date'],
                "committee": "Third Committee",
                "rapporteur": pdf_data['metadata']['rapporteur'],
                "draft_symbol": iran_section['draft_symbol'],
                "title": iran_section['title'],
                "submission_info": iran_section['submission_info'],
                "adoption_status": iran_section['adoption_status'],
                "vote_type": "recorded vote",
                "voting": {
                    "in_favour": vote_details.get('in_favour', []),
                    "against": vote_details.get('against', []),
                    "abstaining": vote_details.get('abstaining', []),
                    "vote_summary": iran_section.get('vote_info', '')
                },
                "proceedings": iran_section.get('item_text', ''),
                "related_drafts": [d['text'] for d in html_data.get('related_documents', {}).get('drafts', [])]
            }

    def analyze_plenary_meeting(self):
        """Extract plenary meeting statements and proceedings"""
        print("💬 Analyzing Plenary Meeting A/78/PV.50...")

        # HTML metadata
        html_path = self.base_path / "data/parsed/html/meetings/A_78_PV.50_record_4053909.json"
        html_data = self.load_json(html_path)

        # PDF parse with detailed utterances
        pdf_path = self.base_path / "data/documents/pdfs/meetings/A_78_PV.50_parsed.json"
        pdf_data = self.load_json(pdf_path)

        # Find the section for agenda item 71 sub-item (c)
        iran_section = None
        for section in pdf_data['sections']:
            if section.get('agenda_item_number') == '71':
                # Check if this is the Iran resolution section
                for utterance in section.get('utterances', []):
                    if 'A/78/481/Add.3' in utterance.get('text', ''):
                        iran_section = section
                        break
                if iran_section:
                    break

        # Extract all statements related to Iran resolution
        iran_utterances = []
        if iran_section:
            for utterance in iran_section.get('utterances', []):
                # Look for Iran-related content
                text = utterance.get('text', '')
                if 'iran' in text.lower() or 'A/C.3/78/L.41' in text or 'resolution III' in text:
                    iran_utterances.append({
                        "speaker": utterance['speaker'],
                        "text": text,
                        "word_count": utterance.get('word_count', 0),
                        "documents": utterance.get('documents', []),
                        "resolution_metadata": utterance.get('resolution_metadata', {})
                    })

        self.genealogy['stages']['plenary_meeting'] = {
            "symbol": "A/78/PV.50",
            "date": html_data['metadata']['action_note'],
            "meeting_number": 50,
            "location": "New York",
            "utterances": iran_utterances,
            "total_utterances": len(iran_utterances)
        }

    def analyze_resolution(self):
        """Extract final resolution with voting"""
        print("✅ Analyzing Final Resolution A/RES/78/220...")

        res_path = self.base_path / "data/parsed/html/resolutions/A_RES_78_220_record_4033024.json"
        res_data = self.load_json(res_path)

        self.genealogy['stages']['resolution'] = {
            "symbol": "A/RES/78/220",
            "title": res_data['metadata']['title'],
            "date": res_data['metadata']['date'],
            "action_note": res_data['metadata']['action_note'],
            "vote_type": res_data['voting']['vote_type'],
            "voting": {
                "yes": res_data['voting']['yes'],
                "no": res_data['voting']['no'],
                "abstain": res_data['voting']['abstain'],
                "meeting": res_data['voting']['meeting'],
                "raw_text": res_data['voting']['raw_text']
            },
            "related_documents": res_data['related_documents'],
            "agenda": res_data['agenda'],
            "files": res_data['files']
        }

    def extract_timeline(self) -> List[Dict]:
        """Build chronological timeline of events"""
        timeline = []

        # Agenda
        if 'agenda' in self.genealogy['stages']:
            timeline.append({
                "date": self.genealogy['stages']['agenda']['date'],
                "event": "Agenda item allocated",
                "symbol": self.genealogy['stages']['agenda']['symbol']
            })

        # Draft
        if 'draft' in self.genealogy['stages']:
            timeline.append({
                "date": self.genealogy['stages']['draft']['date'],
                "event": "Draft resolution submitted",
                "symbol": self.genealogy['stages']['draft']['symbol']
            })

        # Committee report
        if 'committee_report' in self.genealogy['stages']:
            timeline.append({
                "date": self.genealogy['stages']['committee_report']['date'],
                "event": "Committee adopted draft (recorded vote)",
                "symbol": self.genealogy['stages']['committee_report']['symbol']
            })

        # Plenary meeting
        if 'plenary_meeting' in self.genealogy['stages']:
            timeline.append({
                "date": self.genealogy['stages']['plenary_meeting']['date'],
                "event": "Plenary meeting considered committee report",
                "symbol": self.genealogy['stages']['plenary_meeting']['symbol']
            })

        # Resolution
        if 'resolution' in self.genealogy['stages']:
            timeline.append({
                "date": self.genealogy['stages']['resolution']['action_note'],
                "event": "General Assembly adopted resolution",
                "symbol": self.genealogy['stages']['resolution']['symbol'],
                "vote": f"{self.genealogy['stages']['resolution']['voting']['yes']}-{self.genealogy['stages']['resolution']['voting']['no']}-{self.genealogy['stages']['resolution']['voting']['abstain']}"
            })

        return sorted(timeline, key=lambda x: x['date'])

    def extract_voting_comparison(self) -> Dict:
        """Compare voting at committee and plenary stages"""
        comparison = {
            "committee": {},
            "plenary": {}
        }

        if 'committee_report' in self.genealogy['stages']:
            cr = self.genealogy['stages']['committee_report']
            comparison['committee'] = {
                "in_favour": len(cr['voting'].get('in_favour', [])),
                "against": len(cr['voting'].get('against', [])),
                "abstaining": len(cr['voting'].get('abstaining', [])),
                "countries_in_favour": cr['voting'].get('in_favour', []),
                "countries_against": cr['voting'].get('against', []),
                "countries_abstaining": cr['voting'].get('abstaining', [])
            }

        if 'resolution' in self.genealogy['stages']:
            res = self.genealogy['stages']['resolution']
            comparison['plenary'] = {
                "yes": res['voting']['yes'],
                "no": res['voting']['no'],
                "abstain": res['voting']['abstain'],
                "meeting": res['voting']['meeting']
            }

        return comparison

    def generate_report(self) -> str:
        """Generate comprehensive markdown report"""
        report = []
        report.append(f"# Genealogy Analysis: {self.genealogy['resolution_symbol']}")
        report.append(f"\n**Title:** {self.genealogy['title']}")
        report.append(f"\n**Agenda Item:** {self.genealogy['agenda_item']}")

        # Timeline
        report.append("\n\n## Timeline\n")
        timeline = self.extract_timeline()
        for event in timeline:
            report.append(f"- **{event['date']}**: {event['event']} ({event['symbol']})")
            if 'vote' in event:
                report.append(f"  - Vote: {event['vote']}")

        # Voting comparison
        report.append("\n\n## Voting Analysis\n")
        voting = self.extract_voting_comparison()

        if voting['committee']:
            report.append("\n### Committee Vote (Third Committee)")
            report.append(f"- **In Favour:** {voting['committee']['in_favour']}")
            report.append(f"- **Against:** {voting['committee']['against']}")
            report.append(f"- **Abstaining:** {voting['committee']['abstaining']}")

        if voting['plenary']:
            report.append("\n### Plenary Vote (General Assembly)")
            report.append(f"- **Yes:** {voting['plenary']['yes']}")
            report.append(f"- **No:** {voting['plenary']['no']}")
            report.append(f"- **Abstain:** {voting['plenary']['abstain']}")
            report.append(f"- **Meeting:** {voting['plenary']['meeting']}")

        # Detailed stages
        report.append("\n\n## Stage Details\n")

        for stage_name, stage_data in self.genealogy['stages'].items():
            report.append(f"\n### {stage_name.replace('_', ' ').title()}")
            report.append(f"- **Symbol:** {stage_data.get('symbol', 'N/A')}")
            report.append(f"- **Date:** {stage_data.get('date', 'N/A')}")

            if stage_name == 'draft':
                report.append(f"- **Word Count:** {stage_data.get('word_count', 'N/A')}")
                report.append(f"- **Distribution:** {stage_data.get('distribution', 'N/A')}")

            if stage_name == 'committee_report':
                report.append(f"- **Rapporteur:** {stage_data.get('rapporteur', 'N/A')}")
                report.append(f"- **Adoption:** {stage_data.get('adoption_status', 'N/A')}")

            if stage_name == 'plenary_meeting':
                report.append(f"- **Meeting Number:** {stage_data.get('meeting_number', 'N/A')}")
                report.append(f"- **Utterances Captured:** {stage_data.get('total_utterances', 0)}")

        # Data availability summary
        report.append("\n\n## Data Availability Summary\n")
        report.append("\n| Document Type | Symbol | Content Parsed | Voting Data | Statements |\n")
        report.append("|--------------|--------|----------------|-------------|------------|\n")

        for stage_name, stage_data in self.genealogy['stages'].items():
            has_content = 'text' in stage_data or 'proceedings' in stage_data
            has_voting = 'voting' in stage_data or 'vote_type' in stage_data
            has_statements = 'utterances' in stage_data

            report.append(f"| {stage_name.replace('_', ' ').title()} | {stage_data.get('symbol', 'N/A')} | "
                        f"{'✓' if has_content else '✗'} | "
                        f"{'✓' if has_voting else '✗'} | "
                        f"{'✓' if has_statements else '✗'} |\n")

        return '\n'.join(report)

    def run_analysis(self):
        """Run complete analysis"""
        print("🔍 Starting comprehensive genealogy analysis...\n")

        self.analyze_agenda()
        self.analyze_draft()
        self.analyze_committee_report()
        self.analyze_plenary_meeting()
        self.analyze_resolution()

        print("\n✅ Analysis complete!\n")

        # Save full data
        output_path = self.base_path / "analysis_iran_genealogy.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.genealogy, f, indent=2, ensure_ascii=False)
        print(f"📊 Full data saved to: {output_path}")

        # Save report
        report = self.generate_report()
        report_path = self.base_path / "analysis_iran_genealogy_report.md"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"📝 Report saved to: {report_path}")

        # Print summary
        print("\n" + "="*60)
        print(report)
        print("="*60)


if __name__ == "__main__":
    analyzer = GenealogyAnalyzer()
    analyzer.run_analysis()
