"""Base class for all ETL loaders"""

from pathlib import Path
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime
import json


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

    def print_stats(self):
        """Print loading statistics"""
        print(f"\n{'='*50}")
        print(f"Loaded:  {self.stats['loaded']}")
        print(f"Skipped: {self.stats['skipped']}")
        print(f"Errors:  {self.stats['errors']}")
        print(f"{'='*50}\n")
