# ETL Implementation Plan

## Overview
Load parsed JSON documents into PostgreSQL database with error handling, logging, and idempotency.

---

## Architecture

### Class Hierarchy
```
BaseLoader (abstract)
  ├── DocumentLoader (base for all doc types)
  │   ├── ResolutionLoader
  │   ├── DraftLoader
  │   ├── MeetingLoader
  │   ├── CommitteeReportLoader
  │   └── AgendaLoader
  └── ActorLoader (special: manages actor normalization)
```

### Flow
```
1. Scan JSON directory
2. For each JSON file:
   a. Validate JSON schema
   b. Extract data
   c. Normalize actors
   d. Insert/update database
   e. Log success/failure
3. Commit transaction (per file or batch)
4. Generate summary report
```

---

## BaseLoader Class

```python
# db/etl/base_loader.py

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Optional, List
import json
import logging
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import hashlib


class BaseLoader(ABC):
    """Abstract base class for all ETL loaders."""

    def __init__(self, db_url: str, config: Dict[str, Any]):
        self.db_url = db_url
        self.config = config
        self.engine = create_engine(db_url)
        self.Session = sessionmaker(bind=self.engine)
        self.logger = self._setup_logger()

        # Statistics
        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'errors': []
        }

    def _setup_logger(self) -> logging.Logger:
        """Set up file and console logging."""
        logger = logging.getLogger(self.__class__.__name__)
        logger.setLevel(logging.DEBUG)

        # File handler
        fh = logging.FileHandler(f'logs/etl_{self.__class__.__name__}.log')
        fh.setLevel(logging.DEBUG)

        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)

        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)

        logger.addHandler(fh)
        logger.addHandler(ch)

        return logger

    @abstractmethod
    def load_file(self, json_path: Path, session) -> bool:
        """
        Load a single JSON file into the database.

        Args:
            json_path: Path to JSON file
            session: SQLAlchemy session

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def validate_json(self, data: Dict[str, Any]) -> bool:
        """
        Validate JSON structure before loading.

        Args:
            data: Parsed JSON data

        Returns:
            True if valid, False otherwise
        """
        pass

    def load_directory(self, directory: Path, pattern: str = "*.json") -> Dict[str, Any]:
        """
        Load all JSON files in directory.

        Args:
            directory: Directory containing JSON files
            pattern: Glob pattern for files to load

        Returns:
            Statistics dictionary
        """
        json_files = list(directory.glob(pattern))
        self.stats['total'] = len(json_files)

        self.logger.info(f"Found {len(json_files)} files in {directory}")

        for json_path in json_files:
            self.logger.debug(f"Processing {json_path.name}")

            try:
                # Load JSON
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Validate
                if not self.validate_json(data):
                    self.logger.warning(f"Invalid JSON structure: {json_path.name}")
                    self.stats['skipped'] += 1
                    continue

                # Load into database
                session = self.Session()
                try:
                    success = self.load_file(json_path, session)
                    if success:
                        session.commit()
                        self.stats['success'] += 1
                        self.logger.info(f"✓ Loaded {json_path.name}")
                    else:
                        session.rollback()
                        self.stats['failed'] += 1
                        self.logger.error(f"✗ Failed to load {json_path.name}")

                except Exception as e:
                    session.rollback()
                    self.stats['failed'] += 1
                    error_msg = f"{json_path.name}: {str(e)}"
                    self.stats['errors'].append(error_msg)
                    self.logger.exception(f"Exception loading {json_path.name}: {e}")

                finally:
                    session.close()

            except json.JSONDecodeError as e:
                self.stats['failed'] += 1
                error_msg = f"{json_path.name}: Invalid JSON - {str(e)}"
                self.stats['errors'].append(error_msg)
                self.logger.error(error_msg)

            except Exception as e:
                self.stats['failed'] += 1
                error_msg = f"{json_path.name}: {str(e)}"
                self.stats['errors'].append(error_msg)
                self.logger.exception(f"Unexpected error with {json_path.name}: {e}")

        self._print_summary()
        return self.stats

    def _print_summary(self):
        """Print loading summary."""
        self.logger.info("\n" + "="*60)
        self.logger.info(f"ETL Summary - {self.__class__.__name__}")
        self.logger.info("="*60)
        self.logger.info(f"Total files:    {self.stats['total']}")
        self.logger.info(f"Successful:     {self.stats['success']}")
        self.logger.info(f"Failed:         {self.stats['failed']}")
        self.logger.info(f"Skipped:        {self.stats['skipped']}")
        self.logger.info("="*60)

        if self.stats['errors']:
            self.logger.error("\nErrors:")
            for error in self.stats['errors'][:10]:  # Show first 10
                self.logger.error(f"  - {error}")
            if len(self.stats['errors']) > 10:
                self.logger.error(f"  ... and {len(self.stats['errors']) - 10} more")

    def _compute_hash(self, data: Dict[str, Any]) -> str:
        """Compute hash of JSON data for deduplication."""
        json_str = json.dumps(data, sort_keys=True)
        return hashlib.md5(json_str.encode()).hexdigest()

    def _extract_symbol(self, data: Dict[str, Any]) -> Optional[str]:
        """Extract document symbol from various JSON structures."""
        # Try metadata.symbol
        if 'metadata' in data and 'symbol' in data['metadata']:
            return data['metadata']['symbol']

        # Try top-level symbol
        if 'symbol' in data:
            return data['symbol']

        # Try to infer from filename in metadata
        if 'metadata' in data and 'source_file' in data['metadata']:
            # e.g., A_RES_78_220.json -> A/RES/78/220
            filename = data['metadata']['source_file']
            return self._filename_to_symbol(filename)

        return None

    def _filename_to_symbol(self, filename: str) -> str:
        """Convert filename to UN document symbol."""
        # A_RES_78_220.json -> A/RES/78/220
        # A_C.3_78_L.41.json -> A/C.3/78/L.41
        base = filename.replace('.json', '').replace('_parsed', '')
        symbol = base.replace('_', '/')

        # Handle special cases
        symbol = symbol.replace('/PV.', '/PV.')  # Meetings
        symbol = symbol.replace('/L.', '/L.')    # Drafts

        return symbol

    def _safe_get(self, data: Dict, path: str, default=None) -> Any:
        """Safely get nested dictionary value using dot notation."""
        keys = path.split('.')
        value = data
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value
```

---

## ActorLoader

```python
# db/etl/actors_loader.py

from typing import Dict, Optional, Set
from pathlib import Path
import re
from .base_loader import BaseLoader


class ActorLoader(BaseLoader):
    """
    Load and normalize actor (country/speaker) names.

    This is a special loader that:
    1. Scans all JSONs to extract unique actor names
    2. Normalizes them (fuzzy matching)
    3. Inserts into actors table
    4. Returns mapping for other loaders to use
    """

    def __init__(self, db_url: str, config: Dict):
        super().__init__(db_url, config)
        self.actor_cache: Dict[str, int] = {}  # name -> actor_id
        self._load_actor_cache()

    def _load_actor_cache(self):
        """Load existing actors into memory cache."""
        session = self.Session()
        try:
            result = session.execute(
                "SELECT id, normalized_name FROM actors"
            )
            for row in result:
                self.actor_cache[row[1]] = row[0]
            self.logger.info(f"Loaded {len(self.actor_cache)} actors from cache")
        finally:
            session.close()

    def normalize_name(self, name: str) -> str:
        """
        Normalize country/actor name.

        Examples:
            "United States of America" -> "United States"
            "Republic of Korea" -> "South Korea"
        """
        name = name.strip()

        # Common normalizations
        normalizations = {
            'United States of America': 'United States',
            'Republic of Korea': 'South Korea',
            'Democratic People\'s Republic of Korea': 'North Korea',
            'United Kingdom of Great Britain and Northern Ireland': 'United Kingdom',
            'Bolivarian Republic of Venezuela': 'Venezuela',
            'Islamic Republic of Iran': 'Iran',
            'Syrian Arab Republic': 'Syria',
            'Lao People\'s Democratic Republic': 'Laos',
        }

        if name in normalizations:
            return normalizations[name]

        # Remove common prefixes
        prefixes_to_remove = [
            'Republic of ',
            'Kingdom of ',
            'State of ',
            'Democratic Republic of ',
            'Federal Republic of ',
            'Islamic Republic of ',
        ]

        for prefix in prefixes_to_remove:
            if name.startswith(prefix):
                return name[len(prefix):]

        return name

    def get_or_create_actor(
        self,
        name: str,
        actor_type: str = 'country',
        session=None
    ) -> int:
        """
        Get existing actor ID or create new actor.

        Args:
            name: Original actor name
            actor_type: 'country', 'observer', 'un_official'
            session: SQLAlchemy session

        Returns:
            actor_id
        """
        normalized = self.normalize_name(name)

        # Check cache
        if normalized in self.actor_cache:
            return self.actor_cache[normalized]

        # Create new actor
        own_session = session is None
        if own_session:
            session = self.Session()

        try:
            result = session.execute(
                """
                INSERT INTO actors (name, normalized_name, actor_type, aliases)
                VALUES (:name, :normalized, :type, :aliases)
                ON CONFLICT (normalized_name, actor_type) DO UPDATE
                SET name = EXCLUDED.name
                RETURNING id
                """,
                {
                    'name': name,
                    'normalized': normalized,
                    'type': actor_type,
                    'aliases': [name, normalized]  # PostgreSQL array
                }
            )
            actor_id = result.fetchone()[0]

            if own_session:
                session.commit()

            # Update cache
            self.actor_cache[normalized] = actor_id

            self.logger.debug(f"Created actor: {normalized} (id={actor_id})")
            return actor_id

        except Exception as e:
            if own_session:
                session.rollback()
            raise e

        finally:
            if own_session:
                session.close()

    def extract_actors_from_json(self, data: Dict) -> Set[str]:
        """Extract all actor names from a JSON document."""
        actors = set()

        # From authors
        if 'metadata' in data and 'authors' in data['metadata']:
            for author in data['metadata']['authors']:
                # Authors might be comma-separated list
                names = author.split(',')
                actors.update(name.strip() for name in names if name.strip())

        # From votes
        if 'vote_details' in data:
            for vote_type in ['in_favour', 'against', 'abstaining']:
                if vote_type in data['vote_details']:
                    actors.update(data['vote_details'][vote_type])

        # From utterances (speakers)
        if 'sections' in data:
            for section in data['sections']:
                if 'utterances' in section:
                    for utterance in section['utterances']:
                        if 'speaker' in utterance:
                            # Extract country from affiliation
                            if 'affiliation' in utterance['speaker']:
                                actors.add(utterance['speaker']['affiliation'])

        return actors

    # Implement abstract methods
    def load_file(self, json_path: Path, session) -> bool:
        """Not used for ActorLoader - use scan_and_load instead."""
        return True

    def validate_json(self, data: Dict) -> bool:
        """Not used for ActorLoader."""
        return True

    def scan_and_load(self, directories: list[Path]) -> Dict[str, int]:
        """
        Scan all JSONs, extract actors, normalize, and load.

        Returns:
            Dictionary mapping normalized names to actor IDs
        """
        all_actors = set()

        # Scan all directories
        for directory in directories:
            json_files = list(directory.glob('**/*.json'))
            self.logger.info(f"Scanning {len(json_files)} files in {directory}")

            for json_path in json_files:
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    actors = self.extract_actors_from_json(data)
                    all_actors.update(actors)
                except Exception as e:
                    self.logger.warning(f"Error scanning {json_path}: {e}")

        self.logger.info(f"Found {len(all_actors)} unique actors")

        # Load all actors
        session = self.Session()
        try:
            for actor_name in sorted(all_actors):
                self.get_or_create_actor(actor_name, 'country', session)
            session.commit()
        finally:
            session.close()

        return self.actor_cache
```

---

## ResolutionLoader

```python
# db/etl/resolution_loader.py

from pathlib import Path
from typing import Dict, Any
from datetime import datetime
from .base_loader import BaseLoader


class ResolutionLoader(BaseLoader):
    """Load resolution documents and their relationships."""

    def __init__(self, db_url: str, config: Dict, actor_loader):
        super().__init__(db_url, config)
        self.actor_loader = actor_loader

    def validate_json(self, data: Dict[str, Any]) -> bool:
        """Validate resolution JSON structure."""
        required_fields = ['metadata']
        return all(field in data for field in required_fields)

    def load_file(self, json_path: Path, session) -> bool:
        """Load a single resolution JSON file."""
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Extract core fields
        symbol = self._extract_symbol(data)
        if not symbol:
            self.logger.error(f"No symbol found in {json_path}")
            return False

        metadata = data.get('metadata', {})

        # Parse date
        date_str = metadata.get('date', '')
        date = self._parse_date(date_str)

        # Extract session and committee from symbol
        session_num, committee_num = self._parse_symbol(symbol)

        # Insert document
        doc_id = self._insert_document(
            session=session,
            symbol=symbol,
            doc_type='resolution',
            session_num=session_num,
            committee=committee_num,
            record_id=metadata.get('record_id'),
            title=metadata.get('title'),
            date=date,
            action_note=metadata.get('action_note'),
            metadata_json=data,  # Store full JSON in metadata field
            source_file=str(json_path)
        )

        if not doc_id:
            return False

        # Load voting information
        if 'voting' in data and data['voting']:
            self._load_voting(session, symbol, data['voting'])

        # Load relationships (drafts, committee reports, meetings)
        if 'related_documents' in data:
            self._load_relationships(session, symbol, data['related_documents'])

        # Load agenda relationships
        if 'agenda' in data:
            self._load_agenda_relationships(session, symbol, data['agenda'])

        return True

    def _insert_document(self, session, **kwargs) -> int:
        """Insert or update document."""
        try:
            result = session.execute(
                """
                INSERT INTO documents
                    (symbol, doc_type, session, committee, record_id,
                     title, date, action_note, metadata, source_file)
                VALUES
                    (:symbol, :doc_type, :session_num, :committee, :record_id,
                     :title, :date, :action_note, :metadata_json::jsonb, :source_file)
                ON CONFLICT (symbol) DO UPDATE
                SET
                    title = EXCLUDED.title,
                    date = EXCLUDED.date,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                RETURNING id
                """,
                kwargs
            )
            doc_id = result.fetchone()[0]
            return doc_id
        except Exception as e:
            self.logger.exception(f"Error inserting document {kwargs['symbol']}: {e}")
            raise

    def _load_voting(self, session, document_symbol: str, voting_data: Dict):
        """Load voting information into votes table."""
        if not voting_data:
            return

        vote_type = voting_data.get('vote_type')

        # If adopted without vote, no individual votes to record
        if vote_type == 'without_vote':
            return

        # Extract vote lists
        vote_lists = {
            'in_favour': voting_data.get('yes', []),
            'against': voting_data.get('no', []),
            'abstaining': voting_data.get('abstain', [])
        }

        # This is plenary vote (resolutions are voted in plenary)
        for vote_choice, countries in vote_lists.items():
            if not countries:
                continue

            for country_name in countries:
                actor_id = self.actor_loader.get_or_create_actor(
                    country_name, 'country', session
                )

                session.execute(
                    """
                    INSERT INTO votes
                        (document_symbol, vote_context, actor_id, vote_choice)
                    VALUES
                        (:doc, 'plenary', :actor, :choice)
                    ON CONFLICT (document_symbol, vote_context, actor_id) DO NOTHING
                    """,
                    {
                        'doc': document_symbol,
                        'actor': actor_id,
                        'choice': vote_choice
                    }
                )

    def _load_relationships(self, session, target_symbol: str, related: Dict):
        """Load document relationships."""
        relationship_types = {
            'drafts': 'draft_of',
            'committee_reports': 'committee_report_for',
            'meeting_records': 'meeting_for'
        }

        for doc_list_key, rel_type in relationship_types.items():
            if doc_list_key not in related:
                continue

            for doc_ref in related[doc_list_key]:
                source_symbol = doc_ref.get('text')
                if not source_symbol:
                    continue

                session.execute(
                    """
                    INSERT INTO document_relationships
                        (source_symbol, target_symbol, relationship_type)
                    VALUES (:source, :target, :rel_type)
                    ON CONFLICT (source_symbol, target_symbol, relationship_type) DO NOTHING
                    """,
                    {
                        'source': source_symbol,
                        'target': target_symbol,
                        'rel_type': rel_type
                    }
                )

    def _load_agenda_relationships(self, session, document_symbol: str, agenda_list: list):
        """Load agenda item relationships."""
        for agenda_item in agenda_list:
            agenda_symbol = agenda_item.get('agenda_symbol')
            if not agenda_symbol:
                continue

            session.execute(
                """
                INSERT INTO document_relationships
                    (source_symbol, target_symbol, relationship_type)
                VALUES (:source, :target, 'agenda_item')
                ON CONFLICT (source_symbol, target_symbol, relationship_type) DO NOTHING
                """,
                {
                    'source': agenda_symbol,
                    'target': document_symbol
                }
            )

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse various UN date formats."""
        if not date_str:
            return None

        # Remove location prefix: "[New York] : UN, 16 Oct. 2023"
        if ':' in date_str:
            date_str = date_str.split(':')[-1].strip()

        # Remove "UN, " prefix
        if date_str.startswith('UN,'):
            date_str = date_str[4:].strip()

        # Try to parse
        date_formats = [
            '%d %b. %Y',     # 16 Oct. 2023
            '%d %B %Y',      # 16 October 2023
            '%Y-%m-%d',      # 2023-10-16
        ]

        for fmt in date_formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue

        self.logger.warning(f"Could not parse date: {date_str}")
        return None

    def _parse_symbol(self, symbol: str) -> tuple[int, Optional[int]]:
        """
        Extract session and committee from symbol.

        Examples:
            A/RES/78/220 -> (78, None)
            A/C.3/78/L.41 -> (78, 3)
        """
        parts = symbol.split('/')

        # Find session number
        session_num = None
        for part in parts:
            if part.isdigit() and len(part) <= 3:
                session_num = int(part)
                break

        # Find committee number
        committee_num = None
        for part in parts:
            if part.startswith('C.'):
                try:
                    committee_num = int(part.split('.')[1])
                except (IndexError, ValueError):
                    pass

        return session_num, committee_num
```

---

## Orchestration Script

```python
# db/etl/run_etl.py

import argparse
from pathlib import Path
import yaml
from actors_loader import ActorLoader
from resolution_loader import ResolutionLoader
from draft_loader import DraftLoader
from meeting_loader import MeetingLoader
from committee_loader import CommitteeReportLoader
from agenda_loader import AgendaLoader


def load_config(config_path: str) -> dict:
    """Load ETL configuration."""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description='UN Documents ETL')
    parser.add_argument('--config', default='db/etl_config.yaml', help='Config file path')
    parser.add_argument('--type', choices=['all', 'actors', 'resolutions', 'drafts', 'meetings', 'committees', 'agenda'],
                        default='all', help='Document type to load')
    parser.add_argument('--reset', action='store_true', help='Reset database before loading')

    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)
    db_url = config['database']['url']
    data_root = Path(config['data']['root'])

    print("="*60)
    print("UN Documents ETL")
    print("="*60)

    # Reset database if requested
    if args.reset:
        print("\n⚠️  Resetting database...")
        # TODO: Call reset script

    # Step 1: Load actors (required for other loaders)
    if args.type in ['all', 'actors']:
        print("\n📊 Loading actors...")
        actor_loader = ActorLoader(db_url, config)
        scan_dirs = [
            data_root / 'parsed/html/resolutions',
            data_root / 'parsed/html/drafts',
            data_root / 'parsed/html/meetings',
            data_root / 'documents/pdfs/meetings',
            data_root / 'documents/pdfs/committee-reports',
        ]
        actor_loader.scan_and_load(scan_dirs)
    else:
        actor_loader = ActorLoader(db_url, config)

    # Step 2: Load documents
    loaders = []

    if args.type in ['all', 'resolutions']:
        loaders.append(('Resolutions', ResolutionLoader(db_url, config, actor_loader),
                        data_root / 'parsed/html/resolutions'))

    if args.type in ['all', 'drafts']:
        loaders.append(('Drafts', DraftLoader(db_url, config, actor_loader),
                        data_root / 'parsed/html/drafts'))

    if args.type in ['all', 'meetings']:
        loaders.append(('Meetings', MeetingLoader(db_url, config, actor_loader),
                        data_root / 'documents/pdfs/meetings'))

    if args.type in ['all', 'committees']:
        loaders.append(('Committee Reports', CommitteeReportLoader(db_url, config, actor_loader),
                        data_root / 'documents/pdfs/committee-reports'))

    if args.type in ['all', 'agenda']:
        loaders.append(('Agenda', AgendaLoader(db_url, config, actor_loader),
                        data_root / 'parsed/html/agenda'))

    # Run all loaders
    for name, loader, directory in loaders:
        print(f"\n📂 Loading {name}...")
        stats = loader.load_directory(directory)

    print("\n✅ ETL Complete!")


if __name__ == '__main__':
    main()
```

---

## Configuration File

```yaml
# db/etl_config.yaml

database:
  url: "postgresql://user:password@localhost:5432/un_documents"

data:
  root: "/Users/theolebryk/projects/un_draft/data"

logging:
  level: "INFO"
  file: "logs/etl.log"

options:
  batch_size: 100
  skip_errors: true
  validate_json: true
```

---

## Next Steps

1. Implement remaining loaders (DraftLoader, MeetingLoader, etc.)
2. Test each loader independently
3. Add retry logic for network/database errors
4. Profile performance and optimize
5. Add progress bars (tqdm) for better UX
