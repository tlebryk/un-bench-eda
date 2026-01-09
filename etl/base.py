"""Base class for all ETL loaders"""

from pathlib import Path
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime
import json
import re
from typing import List


class BaseLoader:
    """Base class for all ETL loaders"""

    def __init__(self, session: Session, data_root: Path):
        self.session = session
        self.data_root = Path(data_root)
        self.stats = {"loaded": 0, "skipped": 0, "errors": 0}
        self.actor_cache = {}  # name -> actor_id

    def load_json(self, json_path: Path) -> Optional[Dict[str, Any]]:
        """Load JSON file"""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {json_path}: {e}")
            self.stats["errors"] += 1
            return None

    def normalize_symbol(self, symbol: str) -> str:
        """Normalize document symbols (A_RES_78_220 -> A/RES/78/220)"""
        return symbol.strip().upper().replace("_", "/")

    def parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse UN date format: '[New York] : UN, 16 Oct. 2023'"""
        if not date_str:
            return None

        # Remove location prefix
        if ':' in date_str:
            date_str = date_str.split(':')[-1].strip()

        # Remove "UN, " prefix
        if date_str.startswith('UN,'):
            date_str = date_str[4:].strip()

        # Try parsing common formats
        for fmt in ['%d %b. %Y', '%d %B %Y', '%Y-%m-%d']:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue

        return None

    def extract_session(self, symbol: str) -> Optional[int]:
        """Extract session number from symbol (A/RES/78/220 -> 78)"""
        parts = symbol.split('/')
        for part in parts:
            if part.isdigit() and len(part) <= 3:
                return int(part)
        return None

    def get_or_create_actor(self, name: str) -> int:
        """Get or create actor, return ID"""
        from db.models import Actor

        # Check cache
        if name in self.actor_cache:
            return self.actor_cache[name]

        # Check database
        actor = self.session.query(Actor).filter_by(name=name).first()
        if actor:
            self.actor_cache[name] = actor.id
            return actor.id

        # Create new
        new_actor = Actor(name=name, actor_type='country')
        self.session.add(new_actor)
        self.session.flush()
        self.actor_cache[name] = new_actor.id
        return new_actor.id

    def get_or_create_subject(self, name: str) -> int:
        """Get or create subject, return ID"""
        from db.models import Subject

        # Clean subject name
        name = name.strip().upper()
        if not name:
            return None

        # Check database (cache logic can be added later if performance issue)
        subject = self.session.query(Subject).filter_by(name=name).first()
        if subject:
            return subject.id

        # Create new
        new_subject = Subject(name=name)
        self.session.add(new_subject)
        self.session.flush()
        return new_subject.id

    def load_all_actors(self):
        """Load all actors into cache for matching"""
        from db.models import Actor
        actors = self.session.query(Actor).all()
        for actor in actors:
            self.actor_cache[actor.name] = actor.id

    def extract_sponsors(self, text: str) -> List[int]:
        """Extract sponsors from text string using longest-match against known actors"""
        if not text:
            return []
            
        if not self.actor_cache:
            self.load_all_actors()
        
        found_ids = set()
        # Sort actor names by length descending to ensure longest match
        sorted_names = sorted(self.actor_cache.keys(), key=len, reverse=True)
        
        remaining_text = text
        for name in sorted_names:
            if name in remaining_text:
                found_ids.add(self.actor_cache[name])
                # Remove all occurrences to avoid sub-match confusion
                remaining_text = remaining_text.replace(name, " ")
        
        return list(found_ids)

    def extract_additional_sponsors(self, notes: str) -> List[int]:
        """Parse 'Additional sponsors: ...' from notes"""
        if not notes:
            return []
            
        match = re.search(r"Additional sponsors: (.*?)(?:\(|$)", notes)
        if match:
            sponsors_str = match.group(1)
            return self.extract_sponsors(sponsors_str)
        return []

    def _process_metadata_enrichment(self, doc, data: dict):
        """Process subjects and sponsorships from full parsed data"""
        from db.models import DocumentSubject, Sponsorship
        
        metadata = data.get("metadata", {})
        
        # Subjects (usually top-level in parsed JSON)
        subjects_list = data.get("subjects", [])
        if not subjects_list:
            # Fallback to metadata if present there
            subjects_list = metadata.get("subjects", [])

        if subjects_list and isinstance(subjects_list, list):
            seen_subj_ids = set()
            for subj_name in subjects_list:
                subj_id = self.get_or_create_subject(subj_name)
                if subj_id:
                    if subj_id in seen_subj_ids:
                        continue
                    seen_subj_ids.add(subj_id)
                    
                    # Check if link exists
                    exists = self.session.query(DocumentSubject).filter_by(
                        document_id=doc.id, subject_id=subj_id
                    ).first()
                    if not exists:
                        self.session.add(DocumentSubject(document_id=doc.id, subject_id=subj_id))

        # Sponsorships
        # Initial sponsors
        authors_str = metadata.get("authors")
        # Ensure it's a string. Sometimes might be list?
        if authors_str and isinstance(authors_str, list):
            authors_str = " ".join(authors_str)
            
        if authors_str and isinstance(authors_str, str): 
            sponsor_ids = self.extract_sponsors(authors_str)
            for actor_id in sponsor_ids:
                if not self.session.query(Sponsorship).filter_by(
                    document_id=doc.id, actor_id=actor_id, sponsorship_type='initial'
                ).first():
                    self.session.add(Sponsorship(
                        document_id=doc.id, actor_id=actor_id, sponsorship_type='initial'
                    ))

        # Additional sponsors
        notes_str = metadata.get("notes")
        if notes_str and isinstance(notes_str, str):
            additional_ids = self.extract_additional_sponsors(notes_str)
            for actor_id in additional_ids:
                if not self.session.query(Sponsorship).filter_by(
                    document_id=doc.id, actor_id=actor_id
                ).first():
                    self.session.add(Sponsorship(
                        document_id=doc.id, actor_id=actor_id, sponsorship_type='additional'
                    ))

    def print_stats(self):
        """Print loading statistics"""
        print(f"\n{'='*50}")
        print(f"Loaded:  {self.stats['loaded']}")
        print(f"Skipped: {self.stats['skipped']}")
        print(f"Errors:  {self.stats['errors']}")
        print(f"{'='*50}\n")
