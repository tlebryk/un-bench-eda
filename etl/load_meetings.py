"""Load meetings and extract voting records and utterances from parsed PDF meetings"""

from pathlib import Path
from typing import List, Optional
from etl.base import BaseLoader
from db.models import Document, Vote, Utterance, UtteranceDocument, VoteEvent, DocumentRelationship
import re


class MeetingLoader(BaseLoader):
    """Load meetings and voting records from data/parsed/pdfs/meetings/"""

    def load_all(self):
        """Load all meeting JSONs and extract votes"""
        meetings_dir = self.data_root / "parsed" / "pdfs" / "meetings"

        if not meetings_dir.exists():
            print(f"Error: {meetings_dir} does not exist")
            return

        json_files = list(meetings_dir.glob("*.json"))
        total = len(json_files)
        print(f"Found {total} meeting files")

        for idx, json_file in enumerate(json_files, 1):
            if idx % 10 == 0 or idx == 1:  # Progress every 10 files
                print(f"  Processing meeting {idx}/{total}...")
            self.load_meeting(json_file)

        # Commit all changes
        try:
            self.session.commit()
            print(f"✅ Committed all changes")
        except Exception as e:
            self.session.rollback()
            print(f"❌ Commit failed: {e}")
            raise

        self.print_stats()

    def load_meeting(self, json_path: Path):
        """Load a single meeting and extract vote data"""
        data = self.load_json(json_path)
        if not data:
            return

        metadata = data.get("metadata", {})
        symbol = metadata.get("symbol")

        if not symbol:
            print(f"No symbol in {json_path.name}")
            self.stats["skipped"] += 1
            return

        symbol = self.normalize_symbol(symbol)

        # Extract body_text from preface + all utterances
        body_text_parts = []

        # Add preface if present
        if data.get('preface'):
            body_text_parts.append(data['preface'])

        # Add all utterances
        for section in data.get("sections", []):
            for utterance in section.get("utterances", []):
                speaker_line = f"\n{'=' * 80}\n"
                if utterance.get('speaker_name'):
                    speaker_line += utterance['speaker_name']
                    if utterance.get('speaker_affiliation'):
                        speaker_line += f" ({utterance['speaker_affiliation']})"
                    speaker_line += ":\n\n"
                body_text_parts.append(speaker_line + utterance.get('text', ''))

        body_text = '\n\n'.join(body_text_parts) if body_text_parts else None

        # Check if meeting document already exists
        existing_doc = self.session.query(Document).filter_by(symbol=symbol).first()

        if not existing_doc:
            # Create meeting document
            doc = Document(
                symbol=symbol,
                doc_type="meeting",
                session=self.extract_session(symbol),
                title=f"Plenary meeting {metadata.get('meeting_number', '')}",
                date=self.parse_meeting_date(metadata.get("datetime")),
                body_text=body_text,
                doc_metadata=data  # Store full JSON
            )

            try:
                self.session.add(doc)
                self.session.flush()
            except Exception as e:
                print(f"Error creating meeting doc {symbol}: {e}")
                self.stats["errors"] += 1
                return
        else:
            # Update placeholder with real metadata
            doc = existing_doc
            doc.doc_type = "meeting"
            doc.session = doc.session or self.extract_session(symbol)
            doc.title = f"Plenary meeting {metadata.get('meeting_number', '')}" or doc.title
            doc.date = self.parse_meeting_date(metadata.get("datetime")) or doc.date
            doc.body_text = body_text
            doc.doc_metadata = data
            self.session.flush()

        # Extract utterances and votes
        utterances_extracted = 0
        votes_extracted = 0
        position_in_meeting = 0
        
        relationship_targets = set()

        for section in data.get("sections", []):
            agenda_item_number = section.get("agenda_item_number")
            # For ranges, agenda_item_number will be like "90-106"
            # agenda_item_numbers will contain the full list: ["90", "91", ..., "106"]
            agenda_item_numbers = section.get("agenda_item_numbers", [agenda_item_number])
            section_id = section.get("id", f"{symbol}_section_{agenda_item_number}")
            section_documents = section.get("documents", [])  # Documents mentioned at section level
            position_in_section = 0
            
            for utterance_data in section.get("utterances", []):
                position_in_meeting += 1
                position_in_section += 1
                
                # Store agenda item numbers in utterance metadata for ranges
                if len(agenda_item_numbers) > 1 and 'utterance_metadata' not in utterance_data:
                    utterance_data['utterance_metadata'] = {}
                if len(agenda_item_numbers) > 1:
                    utterance_data.setdefault('utterance_metadata', {})['agenda_item_numbers'] = agenda_item_numbers
                
                # Extract utterance
                utterance = self._extract_utterance(
                    doc.id,
                    section_id,
                    agenda_item_number,
                    utterance_data,
                    position_in_meeting,
                    position_in_section
                )
                
                if utterance:
                    utterances_extracted += 1

                    linked_docs = self._link_utterance_to_documents(
                        utterance,
                        utterance_data,
                        section_documents
                    )
                    self._ensure_meeting_relationships(doc, linked_docs, relationship_targets)
                    
                    # Extract votes if this utterance contains vote information
                    resolution_metadata = utterance_data.get("resolution_metadata")
                    if resolution_metadata:
                        vote_count = self._extract_votes_from_utterance(
                            resolution_metadata,
                            utterance_data
                        )
                        votes_extracted += vote_count

                    # Extract procedural events
                    procedural_events = utterance_data.get("procedural_events")
                    if procedural_events:
                        votes_extracted += self._extract_procedural_events(utterance, procedural_events, doc)

        # Backfill meeting relationships from already-linked utterance documents
        self._backfill_meeting_relationships(doc)

        if utterances_extracted > 0 or votes_extracted > 0:
            self.stats["loaded"] += 1
            print(f"  {symbol}: Extracted {utterances_extracted} utterances, {votes_extracted} votes")
        else:
            self.stats["skipped"] += 1

    def _extract_utterance(self, meeting_id: int, section_id: str, agenda_item_number: str,
                          utterance_data: dict, position_in_meeting: int, position_in_section: int) -> Utterance:
        """Extract and store an utterance from parsed JSON"""
        speaker_data = utterance_data.get("speaker", {})
        text = utterance_data.get("text", "")
        
        if not text:
            return None
        
        # Get or create speaker actor
        speaker_actor_id = None
        speaker_name = speaker_data.get("name")
        speaker_affiliation = speaker_data.get("affiliation")
        
        # Try to create actor from affiliation (country) first
        if speaker_affiliation:
            speaker_actor_id = self.get_or_create_actor(speaker_affiliation)
        elif speaker_name and speaker_name != "The President":
            # For non-President speakers, try to use name
            # But we'll store it as speaker_name, not create an actor
            pass
        
        # Prepare utterance metadata
        utterance_metadata = utterance_data.get("utterance_metadata") or {}
        # Merge in resolution_metadata if present
        if utterance_data.get("resolution_metadata"):
            utterance_metadata.update(utterance_data.get("resolution_metadata", {}))
        # Store agenda_item_numbers if present (for ranges)
        if "agenda_item_numbers" in utterance_data.get("utterance_metadata", {}):
            utterance_metadata["agenda_item_numbers"] = utterance_data["utterance_metadata"]["agenda_item_numbers"]
        
        # Create utterance
        utterance = Utterance(
            meeting_id=meeting_id,
            section_id=section_id,
            agenda_item_number=agenda_item_number,  # For ranges, this will be "90-106"
            speaker_actor_id=speaker_actor_id,
            speaker_name=speaker_name,
            speaker_role=speaker_data.get("role"),
            speaker_raw=speaker_data.get("raw"),
            speaker_affiliation=speaker_affiliation,
            text=text,
            word_count=utterance_data.get("word_count"),
            position_in_meeting=position_in_meeting,
            position_in_section=position_in_section,
            utterance_metadata=utterance_metadata or {}
        )
        
        self.session.add(utterance)
        self.session.flush()
        
        return utterance
    
    def _link_utterance_to_documents(self, utterance: Utterance, utterance_data: dict,
                                    section_documents: list = None) -> List[Document]:
        """Link utterance to documents it references (drafts, resolutions, agenda items)"""
        # Get documents mentioned in the utterance
        documents = utterance_data.get("documents", [])
        
        # Also include section-level documents for context
        if section_documents:
            documents.extend(section_documents)
        
        # Track which documents we've already linked to avoid duplicates
        linked_doc_ids = set()
        linked_documents: List[Document] = []
        
        for doc_ref in documents:
            # Handle both string and dict formats
            if isinstance(doc_ref, str):
                doc_symbol = doc_ref
                context = ""
            elif isinstance(doc_ref, dict):
                doc_symbol = doc_ref.get("symbol") or ""
                context = doc_ref.get("context", "")
                # If symbol is empty, try to extract from context
                if not doc_symbol and context:
                    # Try to find a document symbol in the context
                    import re
                    symbol_match = re.search(r'\b[A-Z]/[\dA-Z]+(?:/[A-Z0-9.\-]+)+\b', context)
                    if symbol_match:
                        doc_symbol = symbol_match.group(0)
            else:
                continue
            
            if not doc_symbol or not isinstance(doc_symbol, str):
                continue
            
            doc_symbol = self.normalize_symbol(doc_symbol)
            
            # Find the document in database
            doc = self.session.query(Document).filter_by(symbol=doc_symbol).first()
            if not doc:
                doc_symbol = self._resolve_resolution_symbol(doc_symbol)
                if doc_symbol:
                    doc = self.session.query(Document).filter_by(symbol=doc_symbol).first()
            
            if doc and doc.id not in linked_doc_ids:
                # Check if link already exists
                existing_link = self.session.query(UtteranceDocument).filter_by(
                    utterance_id=utterance.id,
                    document_id=doc.id
                ).first()
                
                if not existing_link:
                    link = UtteranceDocument(
                        utterance_id=utterance.id,
                        document_id=doc.id,
                        reference_type="mentioned",
                        context=context
                    )
                    self.session.add(link)
                    linked_doc_ids.add(doc.id)
                    linked_documents.append(doc)
        
        # Also check resolution_metadata for resolution links
        resolution_metadata = utterance_data.get("resolution_metadata", {})
        if resolution_metadata:
            resolution_symbol = resolution_metadata.get("resolution_symbol")
            if resolution_symbol:
                resolution_symbol = self.normalize_symbol(resolution_symbol)
                resolution_doc = self.session.query(Document).filter_by(symbol=resolution_symbol).first()
                
                if resolution_doc and resolution_doc.id not in linked_doc_ids:
                    # Check if link already exists
                    existing_link = self.session.query(UtteranceDocument).filter_by(
                        utterance_id=utterance.id,
                        document_id=resolution_doc.id
                    ).first()
                    
                    if not existing_link:
                        link = UtteranceDocument(
                            utterance_id=utterance.id,
                            document_id=resolution_doc.id,
                            reference_type="voting_on",
                            context=""
                        )
                        self.session.add(link)
                        linked_doc_ids.add(resolution_doc.id)
                        linked_documents.append(resolution_doc)

        return linked_documents

    def _resolve_resolution_symbol(self, doc_symbol: str) -> Optional[str]:
        if not doc_symbol:
            return None
        if doc_symbol.startswith("A/RES/"):
            return None
        match = re.fullmatch(r"A/(\d+)/(\d+)", doc_symbol)
        if not match:
            return None
        session, number = match.groups()
        return f"A/RES/{session}/{number}"

    def _backfill_meeting_relationships(self, meeting_doc: Document):
        """
        Ensure meeting_record_for edges exist for any documents already linked via utterance_documents.
        This catches cases where utterance links were created before the related resolution/draft was in the DB.
        """
        linked_doc_rows = (
            self.session.query(UtteranceDocument.document_id)
            .join(Utterance, Utterance.id == UtteranceDocument.utterance_id)
            .filter(Utterance.meeting_id == meeting_doc.id)
            .distinct()
            .all()
        )

        seen_ids = set()
        for (doc_id,) in linked_doc_rows:
            if not doc_id or doc_id in seen_ids:
                continue

            doc = self.session.query(Document).get(doc_id)
            if not doc or doc.doc_type not in {"resolution", "draft", "committee_report"}:
                continue

            existing = self.session.query(DocumentRelationship).filter_by(
                source_id=meeting_doc.id,
                target_id=doc.id,
                relationship_type="meeting_record_for"
            ).first()

            if not existing:
                rel = DocumentRelationship(
                    source_id=meeting_doc.id,
                    target_id=doc.id,
                    relationship_type="meeting_record_for"
                )
                self.session.add(rel)

            seen_ids.add(doc_id)

    def _ensure_meeting_relationships(self, meeting_doc: Document,
                                      linked_docs: List[Document],
                                      seen_doc_ids: set):
        """Ensure meeting → document relationships exist for linked drafts/resolutions."""
        if not linked_docs:
            return

        for linked_doc in linked_docs:
            if not linked_doc or not linked_doc.id:
                continue
            if linked_doc.doc_type not in {"resolution", "draft"}:
                continue
            if linked_doc.id in seen_doc_ids:
                continue

            existing = self.session.query(DocumentRelationship).filter_by(
                source_id=meeting_doc.id,
                target_id=linked_doc.id,
                relationship_type="meeting_record_for"
            ).first()

            if not existing:
                rel = DocumentRelationship(
                    source_id=meeting_doc.id,
                    target_id=linked_doc.id,
                    relationship_type="meeting_record_for"
                )
                self.session.add(rel)

            seen_doc_ids.add(linked_doc.id)
    
    def _extract_votes_from_utterance(self, resolution_metadata: dict, utterance_data: dict) -> int:
        """Extract vote records from utterance resolution_metadata"""
        vote_details = resolution_metadata.get("vote_details")
        if not vote_details:
            return 0
        
        resolution_symbol = resolution_metadata.get("resolution_symbol")
        if not resolution_symbol:
            return 0
        
        resolution_symbol = self.normalize_symbol(resolution_symbol)
        resolution_doc = self.session.query(Document).filter_by(symbol=resolution_symbol).first()
        
        if not resolution_doc:
            return 0
        
        return self._load_votes_from_meeting(resolution_doc.id, vote_details)
    
    def _load_votes_from_meeting(self, doc_id: int, vote_details: dict, vote_event_id: int = None) -> int:
        """Load vote records from meeting vote_details"""
        vote_types = {
            'in_favour': vote_details.get('in_favour', []),
            'against': vote_details.get('against', []),
            'abstaining': vote_details.get('abstaining', [])
        }

        vote_count = 0

        for vote_type, countries in vote_types.items():
            if not countries or not isinstance(countries, list):
                continue

            for country in countries:
                if not country:
                    continue

                actor_id = self.get_or_create_actor(country)

                # Check if vote already exists (avoid duplicates)
                criteria = {'actor_id': actor_id, 'vote_type': vote_type}
                if doc_id:
                    criteria['document_id'] = doc_id
                if vote_event_id:
                    criteria['vote_event_id'] = vote_event_id

                if not doc_id and not vote_event_id:
                    continue

                existing_vote = self.session.query(Vote).filter_by(**criteria).first()

                if existing_vote:
                    continue

                vote = Vote(
                    document_id=doc_id,
                    vote_event_id=vote_event_id,
                    actor_id=actor_id,
                    vote_type=vote_type,
                    vote_context='plenary'
                )
                self.session.add(vote)
                vote_count += 1

        return vote_count

    def _extract_procedural_events(self, utterance: Utterance, events: list, meeting_doc: Document) -> int:
        """Extract procedural events and linked votes"""
        votes_count = 0
        for event_data in events:
            # Try to resolve target document (Draft)
            target_doc_id = None
            draft_id = event_data.get('draft_resolution_identifier')
            
            if draft_id:
                # Case 1: Full symbol (e.g. A/78/L.108)
                if '/' in draft_id:
                    symbol = self.normalize_symbol(draft_id)
                    target_doc = self.session.query(Document).filter_by(symbol=symbol).first()
                    if target_doc:
                        target_doc_id = target_doc.id
                        print(f"  ✓ Linked event to draft: {symbol} (ID: {target_doc.id})")
                    else:
                        print(f"  ✗ Could not find target draft for event: {symbol} (raw: {draft_id})")
                
                # Case 2: Short form (e.g. L.19) -> Construct full symbol
                elif re.match(r'L\.\d+', draft_id):
                    symbol = f"A/{meeting_doc.session}/{draft_id}"
                    target_doc = self.session.query(Document).filter_by(symbol=symbol).first()
                    if target_doc:
                        target_doc_id = target_doc.id
            
            # If no draft ID found but we have a resolution symbol, try that
            if not target_doc_id and event_data.get('resolution_symbol'):
                res_symbol = self.normalize_symbol(event_data['resolution_symbol'])
                target_doc = self.session.query(Document).filter_by(symbol=res_symbol).first()
                if target_doc:
                    target_doc_id = target_doc.id

            vote_event = VoteEvent(
                meeting_id=meeting_doc.id,
                utterance_id=utterance.id,
                target_document_id=target_doc_id,
                event_type=event_data.get('event_type'),
                description=event_data.get('description'),
                result=event_data.get('adoption_status')
            )
            self.session.add(vote_event)
            self.session.flush()

            # Extract votes if present
            vote_details = event_data.get('vote_details')
            if vote_details:
                 votes_count += self._load_votes_from_meeting(None, vote_details, vote_event_id=vote_event.id)
        
        return votes_count

    def parse_meeting_date(self, datetime_str: str):
        """Parse meeting datetime: 'Tuesday, 9 January 2024, 10 a.m.'"""
        if not datetime_str:
            return None

        from datetime import datetime

        # Try to extract just the date part
        try:
            # Remove day of week and time
            parts = datetime_str.split(',')
            if len(parts) >= 2:
                date_part = parts[1].strip()  # "9 January 2024"
                return datetime.strptime(date_part, '%d %B %Y').date()
        except Exception:
            pass

        return None
