"""Load any document type (drafts, committee reports, agenda) from parsed HTML + PDF"""

from pathlib import Path
from etl.base import BaseLoader
from db.models import Document


class DocumentLoader(BaseLoader):
    """Generic loader for drafts, committee reports, and agenda items with PDF text"""

    def __init__(self, session, data_root: Path, doc_type: str):
        """
        Args:
            doc_type: 'draft', 'committee_report', or 'agenda_item'
        """
        super().__init__(session, data_root)
        self.doc_type = doc_type

        # Map doc_type to directory names
        self.dir_map = {
            'draft': {'html': 'drafts', 'pdf': 'drafts'},
            'committee_report': {'html': 'committee-reports', 'pdf': 'committee-reports'},
            'agenda_item': {'html': 'agenda', 'pdf': 'agenda'},
        }

    def load_all(self):
        """Load all documents of this type from HTML + standalone PDFs"""
        dirs = self.dir_map.get(self.doc_type)
        if not dirs:
            print(f"❌ Unknown doc_type: {self.doc_type}")
            return

        # Load from HTML metadata first
        html_dir = self.data_root / "parsed" / "html" / dirs['html']
        html_symbols = set()

        if html_dir.exists():
            json_files = list(html_dir.glob("*.json"))
            print(f"Found {len(json_files)} {self.doc_type} HTML files")

            for idx, json_file in enumerate(json_files, 1):
                if idx % 50 == 0 or idx == 1:
                    print(f"  Processing {self.doc_type} {idx}/{len(json_files)}...")
                symbol = self.load_document(json_file, dirs['pdf'])
                if symbol:
                    html_symbols.add(symbol)

        # Load standalone PDFs that don't have HTML metadata
        pdf_dir = self.data_root / "parsed" / "pdfs" / dirs['pdf']
        if pdf_dir.exists():
            pdf_files = list(pdf_dir.glob("*.json"))
            standalone_pdfs = [f for f in pdf_files if self._pdf_symbol(f) not in html_symbols]

            if standalone_pdfs:
                print(f"Found {len(standalone_pdfs)} additional {self.doc_type} PDFs without HTML")
                for idx, pdf_file in enumerate(standalone_pdfs, 1):
                    if idx % 50 == 0 or idx == 1:
                        print(f"  Processing PDF-only {self.doc_type} {idx}/{len(standalone_pdfs)}...")
                    self.load_pdf_only(pdf_file, dirs['pdf'])

        # Commit all changes
        try:
            self.session.commit()
            print(f"✅ Committed all {self.doc_type} changes")
        except Exception as e:
            self.session.rollback()
            print(f"❌ Commit failed: {e}")
            raise

        self.print_stats()

    def _load_pdf_text(self, symbol: str, pdf_dir_name: str) -> str | None:
        """
        Load body text from corresponding PDF-parsed JSON file.

        Args:
            symbol: Document symbol (e.g., 'A/C.3/78/L.41')
            pdf_dir_name: PDF directory name ('drafts', 'committee-reports', 'agenda')

        Returns:
            Body text string or None if not found
        """
        filename = symbol.replace('/', '_') + '.json'
        pdf_dir = self.data_root / "parsed" / "pdfs" / pdf_dir_name
        pdf_path = pdf_dir / filename

        if not pdf_path.exists():
            return None

        try:
            pdf_data = self.load_json(pdf_path)
            if not pdf_data:
                return None

            # Committee reports: extract 'introduction' field
            if pdf_dir_name == 'committee-reports' and 'introduction' in pdf_data:
                return pdf_data['introduction']

            # Drafts/resolutions: try 'draft_text' field
            if 'draft_text' in pdf_data:
                return pdf_data['draft_text']

            # New format: raw_text.full_text
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

    def _pdf_symbol(self, pdf_path: Path) -> str:
        """Extract normalized symbol from PDF filename"""
        # A_C.3_78_L.41.json → A/C.3/78/L.41
        symbol = pdf_path.stem.replace('_', '/')
        return self.normalize_symbol(symbol)

    def load_pdf_only(self, pdf_path: Path, pdf_dir_name: str):
        """Load document from PDF only (no HTML metadata)"""
        pdf_data = self.load_json(pdf_path)
        if not pdf_data:
            return

        # Extract symbol from PDF metadata or filename
        symbol = pdf_data.get('metadata', {}).get('symbol') or pdf_data.get('id')
        if not symbol:
            symbol = self._pdf_symbol(pdf_path)

        symbol = self.normalize_symbol(symbol)

        # Check if already exists (might be a placeholder from relationships)
        existing_doc = self.session.query(Document).filter_by(symbol=symbol).first()
        if existing_doc:
            # Just update with body_text if missing
            body_text = self._extract_text_from_pdf(pdf_data, pdf_dir_name)
            if body_text and not existing_doc.body_text:
                existing_doc.body_text = body_text
                existing_doc.doc_type = self.doc_type
            return

        # Create new document from PDF
        body_text = self._extract_text_from_pdf(pdf_data, pdf_dir_name)

        doc = Document(
            symbol=symbol,
            doc_type=self.doc_type,
            session=self.extract_session(symbol),
            title=pdf_data.get('metadata', {}).get('title'),
            body_text=body_text,
        )

        try:
            self.session.add(doc)
            self.session.flush()
            self.stats["loaded"] += 1
        except Exception as e:
            self.session.rollback()
            self.stats["errors"] += 1
            print(f"Error loading PDF-only {symbol}: {e}")

    def _extract_text_from_pdf(self, pdf_data: dict, pdf_dir_name: str) -> str | None:
        """Extract text from PDF data structure"""
        # Committee reports: introduction
        if pdf_dir_name == 'committee-reports' and 'introduction' in pdf_data:
            return pdf_data['introduction']

        # Drafts/resolutions: draft_text
        if 'draft_text' in pdf_data:
            return pdf_data['draft_text']

        # New format: raw_text.full_text
        if 'raw_text' in pdf_data and isinstance(pdf_data['raw_text'], dict):
            return pdf_data['raw_text'].get('full_text')

        # Text segments
        if 'text_segments' in pdf_data and isinstance(pdf_data['text_segments'], dict):
            segments = pdf_data['text_segments']
            preamble = segments.get('preamble', '')
            operative = segments.get('operative', '')
            if preamble or operative:
                return f"{preamble}\n\n{operative}".strip()

        return None

    def load_document(self, json_path: Path, pdf_dir_name: str) -> str | None:
        """Load a single document from HTML metadata + PDF text. Returns symbol."""
        data = self.load_json(json_path)
        if not data:
            return None

        metadata = data.get("metadata", {})
        symbol = metadata.get("symbol")

        if not symbol:
            print(f"No symbol in {json_path.name}")
            self.stats["skipped"] += 1
            return None

        symbol = self.normalize_symbol(symbol)

        # Try to load PDF text
        body_text = self._load_pdf_text(symbol, pdf_dir_name)

        # Check if document already exists
        existing_doc = self.session.query(Document).filter_by(symbol=symbol).first()

        if existing_doc:
            # Update existing document with body_text and full metadata
            if body_text and not existing_doc.body_text:
                existing_doc.body_text = body_text
            if not existing_doc.title:
                existing_doc.title = metadata.get("title")
            if not existing_doc.date and metadata.get("date"):
                existing_doc.date = self.parse_date(metadata.get("date"))
            if not existing_doc.doc_metadata:
                existing_doc.doc_metadata = data
            # Ensure doc_type is correct
            if existing_doc.doc_type != self.doc_type:
                existing_doc.doc_type = self.doc_type

            self._process_metadata_enrichment(existing_doc, data)
            self.stats["loaded"] += 1
        else:
            # Create new document
            doc = Document(
                symbol=symbol,
                doc_type=self.doc_type,
                session=self.extract_session(symbol),
                title=metadata.get("title"),
                date=self.parse_date(metadata.get("date")),
                body_text=body_text,
                doc_metadata=data
            )

            try:
                self.session.add(doc)
                self.session.flush()
                self._process_metadata_enrichment(doc, data)
                self.stats["loaded"] += 1
            except Exception as e:
                self.session.rollback()
                self.stats["errors"] += 1
                print(f"Error loading {symbol}: {e}")
                return None

        return symbol
