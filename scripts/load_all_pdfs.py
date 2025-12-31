#!/usr/bin/env python3
"""Load body_text for ALL documents directly from PDFs (bypasses HTML metadata)"""

import os
from pathlib import Path
from db.config import get_session
from db.models import Document
from etl.base import BaseLoader

class PDFTextLoader(BaseLoader):
    """Load body_text directly from all PDFs"""

    def __init__(self, session, data_root: Path):
        super().__init__(session, data_root)
        self.pdf_root = data_root / "parsed" / "pdfs"

    def extract_text(self, pdf_path: Path, doc_type: str) -> tuple[str, str]:
        """
        Extract text and symbol from PDF JSON

        Returns:
            (symbol, body_text) tuple
        """
        data = self.load_json(pdf_path)
        if not data:
            return None, None

        # Extract symbol
        symbol = data.get('metadata', {}).get('symbol') or data.get('id')
        if not symbol:
            return None, None

        symbol = self.normalize_symbol(symbol)
        text = None

        # Resolutions/Drafts: draft_text
        if doc_type in ['resolution', 'draft']:
            if 'draft_text' in data:
                text = data['draft_text']
            elif 'raw_text' in data and isinstance(data['raw_text'], dict):
                text = data['raw_text'].get('full_text')
            elif 'text_segments' in data:
                segments = data['text_segments']
                preamble = segments.get('preamble', '')
                operative = segments.get('operative', '')
                text = f"{preamble}\n\n{operative}".strip() if preamble or operative else None

        # Committee reports: introduction
        elif doc_type == 'committee_report':
            text = data.get('introduction')

        # Meetings: preface
        elif doc_type == 'meeting':
            text = data.get('preface')

        # Agenda: concatenate all item texts
        elif doc_type == 'agenda_item':
            items = data.get('items', [])
            texts = [item.get('text', '') for item in items if item.get('text')]
            text = '\n\n'.join(texts) if texts else None

        return symbol, text

    def load_pdf_directory(self, doc_type: str, pdf_dir_name: str):
        """Load all PDFs from a directory"""
        pdf_dir = self.pdf_root / pdf_dir_name

        if not pdf_dir.exists():
            print(f"⚠️  {pdf_dir} does not exist")
            return

        json_files = list(pdf_dir.glob("*.json"))
        print(f"\n📄 Processing {len(json_files)} {doc_type} PDFs...")

        updated = 0
        created = 0
        skipped = 0

        for idx, pdf_path in enumerate(json_files, 1):
            if idx % 50 == 0:
                print(f"  Progress: {idx}/{len(json_files)}...")

            try:
                symbol, body_text = self.extract_text(pdf_path, doc_type)

                if not symbol:
                    skipped += 1
                    continue

                # Find or create document
                doc = self.session.query(Document).filter_by(symbol=symbol).first()

                if doc:
                    # Update existing document
                    if body_text and (not doc.body_text or len(body_text) > len(doc.body_text or '')):
                        doc.body_text = body_text
                        doc.doc_type = doc_type  # Ensure correct type
                        updated += 1
                else:
                    # Create new document from PDF only
                    doc = Document(
                        symbol=symbol,
                        doc_type=doc_type,
                        session=self.extract_session(symbol),
                        body_text=body_text,
                    )
                    self.session.add(doc)
                    created += 1

            except Exception as e:
                print(f"  ❌ Error processing {pdf_path.name}: {e}")
                skipped += 1

        # Commit
        try:
            self.session.commit()
            print(f"  ✅ Updated: {updated}, Created: {created}, Skipped: {skipped}")
        except Exception as e:
            self.session.rollback()
            print(f"  ❌ Commit failed: {e}")
            raise

    def load_all(self):
        """Load text from all PDF types"""
        print("=" * 80)
        print("Loading body_text from ALL PDFs")
        print("=" * 80)

        # Load each document type
        self.load_pdf_directory('resolution', 'resolutions')
        self.load_pdf_directory('draft', 'drafts')
        self.load_pdf_directory('committee_report', 'committee-reports')
        self.load_pdf_directory('meeting', 'meetings')
        self.load_pdf_directory('agenda_item', 'agenda')

        print("\n" + "=" * 80)
        print("✅ All PDFs processed!")
        print("=" * 80)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Load body_text from all PDFs')
    parser.add_argument('--local', action='store_true', help='Use local DATABASE_URL')
    args = parser.parse_args()

    if args.local:
        os.environ['DATABASE_URL'] = 'postgresql://un_user:un_password@localhost:5433/un_documents'

    session = get_session()
    data_root = Path(os.getenv('DATA_ROOT', 'data'))

    loader = PDFTextLoader(session, data_root)
    loader.load_all()

    session.close()
