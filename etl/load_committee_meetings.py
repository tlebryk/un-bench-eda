"Load committee summary records and extract utterances from parsed PDF records"

from pathlib import Path
from etl.load_meetings import MeetingLoader
from db.models import Document, Utterance, UtteranceDocument


class CommitteeMeetingLoader(MeetingLoader):
    """Load committee meetings from data/parsed/pdfs/committee-summary-records/"""

    def load_all(self):
        """Load all committee meeting JSONs"""
        meetings_dir = self.data_root / "parsed" / "pdfs" / "committee-summary-records"

        if not meetings_dir.exists():
            print(f"Error: {meetings_dir} does not exist")
            return

        json_files = list(meetings_dir.glob("*.json"))
        total = len(json_files)
        print(f"Found {total} committee meeting files")

        for idx, json_file in enumerate(json_files, 1):
            if idx % 10 == 0 or idx == 1:
                print(f"  Processing committee meeting {idx}/{total}...")
            self.load_meeting(json_file)

        # Commit all changes
        try:
            self.session.commit()
            print(f"✅ Committed all committee meeting changes")
        except Exception as e:
            self.session.rollback()
            print(f"❌ Commit failed: {e}")
            raise

        self.print_stats()

    def load_meeting(self, json_path: Path):
        """Load a single committee meeting"""
        # We override this to set doc_type='committee_meeting' or just 'meeting'
        # Re-using the base implementation but maybe we want to distinguish?
        # The base implementation hardcodes doc_type="meeting" and title prefix "Plenary meeting"
        
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

        # Extract body_text
        body_text_parts = []
        if data.get('preface'):
            body_text_parts.append(data['preface'])

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

        # Check if document exists
        existing_doc = self.session.query(Document).filter_by(symbol=symbol).first()

        title = f"Committee meeting {metadata.get('meeting_number', '')}"
        # If metadata has a specific title (e.g. "Summary record of the 33rd meeting"), use it or fallback
        
        if not existing_doc:
            doc = Document(
                symbol=symbol,
                doc_type="committee_meeting", # Distinguish from plenary
                session=self.extract_session(symbol),
                title=title,
                date=self.parse_meeting_date(metadata.get("datetime")),
                body_text=body_text,
                doc_metadata=data
            )
            try:
                self.session.add(doc)
                self.session.flush()
            except Exception as e:
                print(f"Error creating committee doc {symbol}: {e}")
                self.stats["errors"] += 1
                return
        else:
            doc = existing_doc
            doc.doc_type = "committee_meeting"
            doc.body_text = body_text
            doc.doc_metadata = data
            self.session.flush()

        # Extract utterances using the logic from base class
        # We need to manually call _extract_utterance loop because we overrode load_meeting
        # Copy-pasting the loop logic from base class but adapting where needed
        
        utterances_extracted = 0
        position_in_meeting = 0
        
        for section in data.get("sections", []):
            agenda_item_number = section.get("agenda_item_number")
            agenda_item_numbers = section.get("agenda_item_numbers", [agenda_item_number])
            section_id = section.get("id", f"{symbol}_section_{agenda_item_number}")
            section_documents = section.get("documents", [])
            position_in_section = 0
            
            for utterance_data in section.get("utterances", []):
                position_in_meeting += 1
                position_in_section += 1
                
                if len(agenda_item_numbers) > 1 and 'utterance_metadata' not in utterance_data:
                    utterance_data['utterance_metadata'] = {}
                if len(agenda_item_numbers) > 1:
                    utterance_data.setdefault('utterance_metadata', {})['agenda_item_numbers'] = agenda_item_numbers
                
                # Check if utterance already exists to avoid duplicates if re-running
                # (Simple check based on meeting_id and position)
                existing_utt = self.session.query(Utterance).filter_by(
                    meeting_id=doc.id,
                    position_in_meeting=position_in_meeting
                ).first()

                if not existing_utt:
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
                        self._link_utterance_to_documents(utterance, utterance_data, section_documents)
                        # Committee SRs usually don't have recorded votes in utterances in the same format
                        # but we can try extracting if they do
                        
        if utterances_extracted > 0:
            self.stats["loaded"] += 1
