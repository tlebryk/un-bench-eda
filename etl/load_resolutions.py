"""Load resolutions from parsed HTML metadata"""

from pathlib import Path
from etl.base import BaseLoader
from db.models import Document, Vote, DocumentRelationship


class ResolutionLoader(BaseLoader):
    """Load resolutions from data/parsed/html/resolutions/"""

    def load_all(self):
        """Load all resolution JSONs"""
        res_dir = self.data_root / "parsed" / "html" / "resolutions"

        if not res_dir.exists():
            print(f"Error: {res_dir} does not exist")
            return

        json_files = list(res_dir.glob("*.json"))
        total = len(json_files)
        print(f"Found {total} resolution files")

        for idx, json_file in enumerate(json_files, 1):
            if idx % 10 == 0 or idx == 1:  # Progress every 10 files
                print(f"  Processing resolution {idx}/{total}...")
            self.load_resolution(json_file)

        # Commit all changes
        try:
            self.session.commit()
            print(f"✅ Committed all changes")
        except Exception as e:
            self.session.rollback()
            print(f"❌ Commit failed: {e}")
            raise

        self.print_stats()

    def _load_pdf_text(self, symbol: str) -> str | None:
        """
        Load body text from corresponding PDF-parsed JSON file.

        Handles multiple PDF parsing formats:
        - Old format: 'draft_text' field
        - New format: 'raw_text.full_text' or combined 'text_segments'

        Also handles combined PDFs with naming variants:
        - A/RES/78/80[A] → tries A_RES_78_80[A].json, A_RES_78_80_A.json, A_RES_78_80_A-B.json

        Args:
            symbol: Document symbol (e.g., 'A/RES/78/1')

        Returns:
            Body text string or None if not found
        """
        pdf_dir = self.data_root / "parsed" / "pdfs" / "resolutions"

        # Try multiple filename patterns
        # Pattern 1: Direct conversion (A/RES/78/1 -> A_RES_78_1.json)
        filename_attempts = [symbol.replace('/', '_') + '.json']

        # Pattern 2: Handle [A]/[B] brackets (A/RES/78/80[A] -> A_RES_78_80_A.json)
        if '[' in symbol:
            base_symbol = symbol.replace('[', '_').replace(']', '')
            filename_attempts.append(base_symbol.replace('/', '_') + '.json')

            # Pattern 3: Combined A-B format (A/RES/78/80[A] -> A_RES_78_80_A-B.json)
            if '[A]' in symbol:
                combined = symbol.replace('[A]', '_A-B')
                filename_attempts.append(combined.replace('/', '_') + '.json')
            elif '[B]' in symbol:
                combined = symbol.replace('[B]', '_A-B')
                filename_attempts.append(combined.replace('/', '_') + '.json')

        # Try each filename pattern
        pdf_path = None
        for filename in filename_attempts:
            candidate_path = pdf_dir / filename
            if candidate_path.exists():
                pdf_path = candidate_path
                break

        if not pdf_path:
            return None

        try:
            pdf_data = self.load_json(pdf_path)
            if not pdf_data:
                return None

            # Try old format: draft_text field
            if 'draft_text' in pdf_data:
                return pdf_data['draft_text']

            # Try new format: raw_text.full_text
            if 'raw_text' in pdf_data and isinstance(pdf_data['raw_text'], dict):
                full_text = pdf_data['raw_text'].get('full_text')
                if full_text:
                    return full_text

            # Fallback: combine text_segments (preamble + operative)
            if 'text_segments' in pdf_data and isinstance(pdf_data['text_segments'], dict):
                segments = pdf_data['text_segments']
                preamble = segments.get('preamble', '')
                operative = segments.get('operative', '')
                if preamble or operative:
                    return f"{preamble}\n\n{operative}".strip()

        except Exception as e:
            print(f"  Warning: Could not load PDF text from {pdf_path.name}: {e}")

        return None

    def load_resolution(self, json_path: Path):
        """Load a single resolution"""
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

        # Try to load PDF text
        body_text = self._load_pdf_text(symbol)

        # Create document
        doc = Document(
            symbol=symbol,
            doc_type="resolution",
            session=self.extract_session(symbol),
            title=metadata.get("title"),
            date=self.parse_date(metadata.get("date")),
            body_text=body_text,
            doc_metadata=data  # Store full JSON
        )

        try:
            self.session.add(doc)
            self.session.flush()  # Get doc.id
            
            self._process_metadata_enrichment(doc, data)

            # Load voting
            voting = data.get("voting", {})
            if voting:
                self._load_votes(doc.id, voting)

            # Load relationships
            related = data.get("related_documents", {})
            if related:
                self._load_relationships(doc.id, related)

            agenda_items = data.get("agenda", [])
            if agenda_items:
                self._load_agenda_relationships(doc.id, agenda_items)

            self.stats["loaded"] += 1

        except Exception as e:
            print(f"Error loading {symbol}: {e}")
            self.stats["errors"] += 1

    def _load_votes(self, doc_id: int, voting: dict):
        """Load vote records - handles both individual votes (lists) and tallies (integers)"""
        vote_types = {
            'in_favour': voting.get('yes', []),
            'against': voting.get('no', []),
            'abstaining': voting.get('abstain', [])
        }

        has_tallies = False
        tallies = {}

        for vote_type, countries in vote_types.items():
            if not countries:
                continue

            # Handle integer tallies - store in tallies dict for doc_metadata
            if isinstance(countries, int):
                has_tallies = True
                tallies[vote_type] = countries
                continue

            # Handle list of countries - create individual Vote records
            if not isinstance(countries, list):
                continue

            for country in countries:
                if not country:
                    continue

                actor_id = self.get_or_create_actor(country)
                vote = Vote(
                    document_id=doc_id,
                    actor_id=actor_id,
                    vote_type=vote_type,
                    vote_context='plenary'
                )
                self.session.add(vote)

        # If we have tallies, store them in the document's metadata
        if has_tallies:
            from db.models import Document
            doc = self.session.query(Document).filter_by(id=doc_id).first()
            if doc and doc.doc_metadata:
                # Add vote_tallies to existing metadata
                if 'vote_tallies' not in doc.doc_metadata:
                    doc.doc_metadata['vote_tallies'] = tallies
                self.session.flush()

    def _get_or_create_document(
        self,
        symbol: str,
        doc_type: str,
        title: str | None = None,
        metadata: dict | None = None,
        normalize: bool = True,
    ) -> Document:
        """Fetch an existing document or create a lightweight placeholder."""
        symbol = self.normalize_symbol(symbol) if normalize else symbol.strip()
        doc = self.session.query(Document).filter_by(symbol=symbol).first()

        if doc:
            # Populate missing fields if we learned something new
            updated = False
            if title and not doc.title:
                doc.title = title
                updated = True
            if metadata and not doc.doc_metadata:
                doc.doc_metadata = metadata
                updated = True
            if doc.doc_type != doc_type and doc.doc_type == "resolution":
                # Resolutions that show up elsewhere shouldn't be overwritten
                pass
            else:
                if doc.doc_type != doc_type:
                    doc.doc_type = doc_type
                    updated = True
            if updated:
                self.session.flush()
            return doc

        doc = Document(
            symbol=symbol,
            doc_type=doc_type,
            session=self.extract_session(symbol),
            title=title,
            doc_metadata=metadata
        )
        self.session.add(doc)
        self.session.flush()
        return doc

    def _ensure_relationship(self, source_id: int, target_id: int, rel_type: str):
        """Create relationship if it doesn't already exist."""
        existing = self.session.query(DocumentRelationship).filter_by(
            source_id=source_id,
            target_id=target_id,
            relationship_type=rel_type
        ).first()

        if existing:
            return

        rel = DocumentRelationship(
            source_id=source_id,
            target_id=target_id,
            relationship_type=rel_type
        )
        self.session.add(rel)

    def _load_relationships(self, target_id: int, related: dict):
        """Load document relationships for drafts, committee reports, and meetings."""

        draft_refs = related.get("drafts", [])
        for draft_ref in draft_refs:
            draft_symbol = draft_ref.get("text")
            if not draft_symbol:
                continue
            draft_doc = self._get_or_create_document(
                draft_symbol,
                "draft",
                metadata={"source_url": draft_ref.get("url")}
            )
            self._ensure_relationship(draft_doc.id, target_id, "draft_of")

        for committee_ref in related.get("committee_reports", []):
            committee_symbol = committee_ref.get("text")
            if not committee_symbol:
                continue
            committee_doc = self._get_or_create_document(
                committee_symbol,
                "committee_report",
                metadata={"source_url": committee_ref.get("url")}
            )
            self._ensure_relationship(committee_doc.id, target_id, "committee_report_for")

        for meeting_ref in related.get("meeting_records", []):
            meeting_symbol = meeting_ref.get("text")
            if not meeting_symbol:
                continue
            meeting_doc = self._get_or_create_document(
                meeting_symbol,
                "meeting",
                metadata={"source_url": meeting_ref.get("url")}
            )
            self._ensure_relationship(meeting_doc.id, target_id, "meeting_record_for")

    def _load_agenda_relationships(self, target_id: int, agenda_items: list[dict]):
        """Link agenda items to the resolution."""
        for item in agenda_items:
            symbol = item.get("id") or item.get("agenda_symbol")
            if not symbol:
                continue

            metadata = {
                "agenda_symbol": item.get("agenda_symbol"),
                "item_number": item.get("item_number"),
                "sub_item": item.get("sub_item"),
                "title": item.get("title"),
                "subjects": item.get("subjects"),
                "url": item.get("url")
            }

            agenda_doc = self._get_or_create_document(
                symbol,
                "agenda_item",
                title=item.get("title"),
                metadata=metadata,
                normalize=False
            )
            self._ensure_relationship(agenda_doc.id, target_id, "agenda_item_for")
