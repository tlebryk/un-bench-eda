#!/usr/bin/env python3
"""
Build RL-ready trajectories from UN document genealogies.

A trajectory represents the complete lifecycle of a resolution as a sequence of
timesteps, where each timestep has:
- State (what's observable at that moment)
- Action (what happens)
- Observation (public outcome)

This is designed for MARL environments where multiple agents (countries)
take actions (sponsor, vote, speak) over time.
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import re
from .trace_genealogy import UNDocumentIndex, DocumentGenealogy
from etl.parsing.resolution_metadata import _parse_country_list_comma


class TrajectoryBuilder:
    """Build MARL trajectories from UN document genealogies."""

    def __init__(self, index: UNDocumentIndex):
        self.index = index
        self.genealogy = DocumentGenealogy(index)

    def build_trajectory(self, resolution_symbol: str) -> Dict[str, Any]:
        """Build a complete trajectory from resolution symbol."""

        # Get full genealogy tree
        tree = self.genealogy.trace_backwards(resolution_symbol)
        if "error" in tree:
            return {"error": tree["error"]}

        # Initialize trajectory
        trajectory = {
            "trajectory_id": resolution_symbol,
            "metadata": self._extract_metadata(tree),
            "timesteps": []
        }

        # Build timesteps chronologically
        timesteps = []

        # T0: Agenda allocation
        timesteps.extend(self._build_agenda_timesteps(tree))

        # T1: Draft submission
        timesteps.extend(self._build_draft_timesteps(tree))

        # T1.5: Committee deliberation
        timesteps.extend(self._build_committee_deliberation_timesteps(tree))

        # T2: Committee consideration and vote
        timesteps.extend(self._build_committee_timesteps(tree))

        # T3: Plenary consideration and vote
        timesteps.extend(self._build_plenary_timesteps(tree))

        # Sort by date and assign timestep numbers
        # timesteps.sort(key=lambda x: x.get("date", ""))
        for i, ts in enumerate(timesteps):
            ts["t"] = i

        trajectory["timesteps"] = timesteps
        return trajectory

    def _extract_metadata(self, tree: Dict[str, Any]) -> Dict[str, Any]:
        """Extract trajectory metadata."""
        res_data = tree.get("resolution", {}).get("data", {})
        return {
            "symbol": tree.get("root_symbol"),
            "title": res_data.get("metadata", {}).get("title"),
            "session": self._extract_session(tree.get("root_symbol")),
            "committee": self._extract_committee(tree),
            "agenda_item": self._extract_agenda_item(tree),
            "final_outcome": self._extract_final_outcome(res_data)
        }

    def _extract_session(self, symbol: str) -> Optional[int]:
        """Extract session number from symbol."""
        match = re.search(r'/(\d+)/', symbol or "")
        return int(match.group(1)) if match else None

    def _extract_committee(self, tree: Dict[str, Any]) -> Optional[int]:
        """Extract committee number from drafts."""
        for draft in tree.get("drafts", []):
            symbol = draft.get("symbol", "")
            if "/C." in symbol:
                match = re.search(r'/C\.(\d+)/', symbol)
                if match:
                    return int(match.group(1))
        return None

    def _extract_agenda_item(self, tree: Dict[str, Any]) -> Optional[str]:
        """Extract primary agenda item."""
        for item in tree.get("agenda_items", []):
            num = item.get("item_number")
            sub = item.get("sub_item")
            if num:
                return f"{num}{sub or ''}"
        return None

    def _extract_final_outcome(self, res_data: Dict[str, Any]) -> str:
        """Extract final outcome (adopted/rejected)."""
        voting = res_data.get("voting", {})
        if voting:
            yes_votes = voting.get("yes") or 0
            no_votes = voting.get("no") or 0
            return "adopted" if yes_votes > no_votes else "rejected"
        return "unknown"

    def _build_agenda_timesteps(self, tree: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build timesteps for agenda allocation."""
        timesteps = []

        for agenda_item in tree.get("agenda_items", []):
            if not agenda_item.get("data"):
                continue

            agenda_data = agenda_item["data"]
            date = agenda_data.get("metadata", {}).get("date")

            timesteps.append({
                "date": date,
                "stage": "agenda_allocation",
                "action_type": "allocate_to_committee",
                "state": {
                    "agenda_symbol": agenda_item["symbol"],
                    "item_number": agenda_item.get("item_number"),
                    "sub_item": agenda_item.get("sub_item"),
                    "title": agenda_item.get("title")
                },
                "action": {
                    "actor": "General Assembly",
                    "type": "allocate_agenda_item",
                    "committee": self._extract_committee(tree)
                },
                "observation": {
                    "public": True,
                    "agenda_published": True
                }
            })

        return timesteps

    def _build_draft_timesteps(self, tree: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build timesteps for draft submission."""
        timesteps = []

        for draft in tree.get("drafts", []):
            if not draft.get("data"):
                continue

            draft_data = draft["data"]
            metadata = draft_data.get("metadata", {})
            date = metadata.get("date")

            # Load full draft text from PDF parse if available
            draft_symbol = draft["symbol"]
            pdf_draft = self._load_pdf_draft(draft_symbol)

            draft_text = pdf_draft.get("draft_text", "") if pdf_draft else ""
            sponsors = self._extract_sponsors(draft_symbol, tree)

            timesteps.append({
                "date": date,
                "stage": "draft_submission",
                "action_type": "submit_draft",
                "state": {
                    "draft_symbol": draft_symbol,
                    "distribution": metadata.get("distribution"),
                    "language": metadata.get("original_language")
                },
                "action": {
                    "actor": sponsors[0] if sponsors else "Unknown",
                    "type": "submit_draft_resolution",
                    "draft_text": draft_text[:500] + "..." if len(draft_text) > 500 else draft_text,
                    "draft_text_full_length": len(draft_text),
                    "sponsors": sponsors,
                    "co_sponsors": []  # Now parsed from committee report!
                },
                "observation": {
                    "public": metadata.get("distribution") != "Confidential",
                    "draft_symbol": draft_symbol,
                    "draft_published": True,
                    "sponsor_count": len(sponsors)
                }
            })

        return timesteps

    def _build_committee_deliberation_timesteps(self, tree: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build timesteps for committee deliberations."""
        timesteps = []

        for sr in tree.get("committee_deliberations", []):
            if not sr.get("data"):
                continue

            sr_data = sr["data"]
            metadata = sr_data.get("metadata", {})
            date = metadata.get("date") or metadata.get("datetime")

            # Extract statements/utterances
            utterances = []
            for section in sr_data.get("sections", []):
                for utterance in section.get("utterances", []):
                    # Filter for relevant utterances
                    if self._is_relevant_utterance(utterance, tree):
                        utterances.append({
                            "speaker": utterance["speaker"].get("name", "Unknown"),
                            "text_preview": utterance["text"][:200] + "..." if len(utterance["text"]) > 200 else utterance["text"],
                            "word_count": utterance.get("word_count", 0)
                        })

            if utterances:
                timesteps.append({
                    "date": date,
                    "stage": "committee_deliberation",
                    "action_type": "statements",
                    "state": {
                        "meeting_symbol": sr["symbol"],
                        "meeting_number": metadata.get("meeting_number")
                    },
                    "action": {
                        "actor": "Multiple delegations",
                        "type": "make_statements",
                        "utterances": utterances
                    },
                    "observation": {
                        "public": True,
                        "statement_count": len(utterances)
                    }
                })

        return timesteps

    def _build_committee_timesteps(self, tree: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build timesteps for committee consideration and voting."""
        timesteps = []

        for report in tree.get("committee_reports", []):
            if not report.get("data"):
                continue

            report_data = report["data"]
            metadata = report_data.get("metadata", {})
            date = metadata.get("date")

            # Load PDF parse for detailed voting
            pdf_report = self._load_pdf_committee_report(report["symbol"])

            # Find the specific draft item
            draft_item = self._find_draft_in_report(pdf_report, tree.get("drafts", []))

            if draft_item:
                vote_details = draft_item.get("vote_details", {})

                # Timestep: Committee vote
                timesteps.append({
                    "date": date,
                    "stage": "committee_vote",
                    "action_type": "recorded_vote",
                    "state": {
                        "draft_symbol": draft_item["draft_symbol"],
                        "committee": metadata.get("committee"),
                        "rapporteur": pdf_report.get("metadata", {}).get("rapporteur") if pdf_report else None
                    },
                    "action": {
                        "actor": "Third Committee Members",
                        "type": "vote_on_draft",
                        "votes": {
                            "in_favour": vote_details.get("in_favour", []),
                            "against": vote_details.get("against", []),
                            "abstaining": vote_details.get("abstaining", [])
                        }
                    },
                    "observation": {
                        "public": True,
                        "outcome": draft_item.get("adoption_status"),
                        "vote_tally": {
                            "yes": len(vote_details.get("in_favour", [])),
                            "no": len(vote_details.get("against", [])),
                            "abstain": len(vote_details.get("abstaining", []))
                        },
                        "committee_report_symbol": report["symbol"]
                    }
                })

        return timesteps

    def _build_plenary_timesteps(self, tree: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build timesteps for plenary meeting and voting."""
        timesteps = []

        for meeting in tree.get("meeting_records", []):
            if not meeting.get("data"):
                continue

            meeting_data = meeting["data"]
            metadata = meeting_data.get("metadata", {})
            date = metadata.get("action_note") or metadata.get("date")

            # Load PDF parse for utterances and voting
            pdf_meeting = self._load_pdf_meeting(meeting["symbol"])

            # Extract plenary vote from PDF meeting parse
            plenary_vote_details = None
            if pdf_meeting:
                resolution_symbol = tree.get("root_symbol")
                # Find the utterance with vote details for our resolution
                for section in pdf_meeting.get("sections", []):
                    for utterance in section.get("utterances", []):
                        res_meta = utterance.get("resolution_metadata", {})
                        if res_meta.get("resolution_symbol") == resolution_symbol:
                            plenary_vote_details = res_meta.get("vote_details")
                            break
                    if plenary_vote_details:
                        break

            # Extract statements/utterances
            utterances = []
            if pdf_meeting:
                for section in pdf_meeting.get("sections", []):
                    for utterance in section.get("utterances", []):
                        # Filter for relevant utterances (Iran resolution)
                        if self._is_relevant_utterance(utterance, tree):
                            utterances.append({
                                "speaker": utterance["speaker"].get("name", "Unknown"),
                                "role": utterance["speaker"].get("role", "Unknown"),
                                "text_preview": utterance["text"][:200] + "..." if len(utterance["text"]) > 200 else utterance["text"],
                                "word_count": utterance.get("word_count", 0)
                            })

            # Timestep: Plenary discussion
            if utterances:
                timesteps.append({
                    "date": date,
                    "stage": "plenary_discussion",
                    "action_type": "statements",
                    "state": {
                        "meeting_symbol": meeting["symbol"],
                        "meeting_number": metadata.get("meeting_number")
                    },
                    "action": {
                        "actor": "Multiple delegations",
                        "type": "make_statements",
                        "utterances": utterances
                    },
                    "observation": {
                        "public": True,
                        "statement_count": len(utterances)
                    }
                })

            # Timestep: Plenary vote (if we found vote details)
            if plenary_vote_details:
                timesteps.append({
                    "date": date,
                    "stage": "plenary_vote",
                    "action_type": "recorded_vote",
                    "state": {
                        "resolution_symbol": tree.get("root_symbol"),
                        "meeting_symbol": meeting["symbol"]
                    },
                    "action": {
                        "actor": "General Assembly Members",
                        "type": "vote_on_resolution",
                        "votes": {
                            "in_favour": plenary_vote_details.get("in_favour", []),
                            "against": plenary_vote_details.get("against", []),
                            "abstaining": plenary_vote_details.get("abstaining", [])
                        }
                    },
                    "observation": {
                        "public": True,
                        "outcome": "adopted" if len(plenary_vote_details.get("in_favour", [])) > len(plenary_vote_details.get("against", [])) else "rejected",
                        "vote_tally": {
                            "yes": len(plenary_vote_details.get("in_favour", [])),
                            "no": len(plenary_vote_details.get("against", [])),
                            "abstain": len(plenary_vote_details.get("abstaining", []))
                        },
                        "resolution_symbol": tree.get("root_symbol")
                    }
                })

        return timesteps


    def _load_pdf_draft(self, draft_symbol: str) -> Optional[Dict[str, Any]]:
        """Load PDF parse of draft resolution."""
        # Convert symbol to filename: A/C.3/78/L.41 -> A_C.3_78_L.41.json
        filename = draft_symbol.replace("/", "_") + ".json"
        path = Path("data/parsed/pdfs/drafts") / filename
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return None

    def _load_pdf_committee_report(self, report_symbol: str) -> Optional[Dict[str, Any]]:
        """Load PDF parse of committee report."""
        filename = report_symbol.replace("/", "_") + "_parsed.json"
        path = Path("data/documents/pdfs/committee-reports") / filename
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return None

    def _load_pdf_meeting(self, meeting_symbol: str) -> Optional[Dict[str, Any]]:
        """Load PDF parse of plenary meeting."""
        filename = meeting_symbol.replace("/", "_") + "_parsed.json"
        path = Path("data/documents/pdfs/meetings") / filename
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return None

    def _extract_sponsors(self, draft_symbol: str, tree: Dict[str, Any]) -> List[str]:
        """Extract sponsors from committee reports."""
        sponsors = set()

        # Check all committee reports for this draft
        for report in tree.get("committee_reports", []):
            pdf_report = self._load_pdf_committee_report(report["symbol"])
            if not pdf_report:
                continue

            # Find item for this draft
            draft_item = self._find_draft_item_by_symbol(pdf_report, draft_symbol)
            if not draft_item:
                continue

            item_text = draft_item.get("item_text", "")
            if not item_text:
                continue

            # 1. Submitted by
            submitted_match = re.search(r"submitted by\s+([^.]+)", item_text)
            if submitted_match:
                sponsors.update(_parse_country_list_comma(submitted_match.group(1)))

            # 2. Subsequently ... joined
            joined_matches = re.finditer(r"(?:Subsequently|At the same meeting|Also at the same meeting),\s+([^.]+?)\s+joined", item_text)
            for match in joined_matches:
                sponsors.update(_parse_country_list_comma(match.group(1)))

        return sorted(list(sponsors))

    def _find_draft_item_by_symbol(self, pdf_report: Dict[str, Any], draft_symbol: str) -> Optional[Dict[str, Any]]:
        """Find the specific item in committee report by draft symbol."""
        if not pdf_report:
            return None

        for item in pdf_report.get("items", []):
            # Check draft_symbol field
            if item.get("draft_symbol") == draft_symbol:
                return item
            # Also check text for symbol if explicit field missing or mismatch
            if draft_symbol in item.get("item_text", ""):
                return item

        return None

    def _find_draft_in_report(self, pdf_report: Optional[Dict], drafts: List[Dict]) -> Optional[Dict]:
        """Find the specific draft item in committee report."""
        if not pdf_report or not drafts:
            return None

        # Get draft symbols
        draft_symbols = [d.get("symbol") for d in drafts]

        # Search in report items
        for item in pdf_report.get("items", []):
            if item.get("draft_symbol") in draft_symbols:
                return item

        return None

    def _is_relevant_utterance(self, utterance: Dict[str, Any], tree: Dict[str, Any]) -> bool:
        """Check if utterance is relevant to this resolution."""
        text = utterance.get("text", "").lower()

        # Check for resolution symbol or draft symbol
        for draft in tree.get("drafts", []):
            if draft.get("symbol", "").lower() in text:
                return True

        # Check for Iran-related keywords
        if "iran" in text:
            return True

        return False


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Build MARL trajectory from UN resolution genealogy"
    )
    parser.add_argument(
        "resolution_symbol",
        help="Resolution symbol (e.g., A/RES/78/220)"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output JSON file (default: trajectory_<symbol>.json)"
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output"
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        help="Root directory for parsed HTML data (default: data/documents/html)"
    )

    args = parser.parse_args()

    # Build index
    print(f"Building document index...")
    index = UNDocumentIndex(args.data_root) if args.data_root else UNDocumentIndex()
    print(f"Indexed {len(index.documents)} documents\n")

    # Build trajectory
    print(f"Building trajectory for {args.resolution_symbol}...")
    builder = TrajectoryBuilder(index)
    trajectory = builder.build_trajectory(args.resolution_symbol)

    if "error" in trajectory:
        print(f"❌ {trajectory['error']}")
        return

    # Output
    output_file = args.output or f"trajectory_{args.resolution_symbol.replace('/', '_')}.json"

    indent = 2 if args.pretty else None
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(trajectory, f, indent=indent, default=str, ensure_ascii=False)

    print(f"\n✅ Trajectory saved to {output_file}")
    print(f"\nSummary:")
    print(f"  Total timesteps: {len(trajectory['timesteps'])}")
    print(f"  Stages: {', '.join(set(ts['stage'] for ts in trajectory['timesteps']))}")
    print(f"  Final outcome: {trajectory['metadata']['final_outcome']}")

    # Print timestep summary
    print(f"\nTimestep sequence:")
    for ts in trajectory['timesteps']:
        print(f"  T{ts['t']}: {ts['stage']:20s} - {ts['action_type']:20s} ({ts['date']})")


if __name__ == "__main__":
    main()
