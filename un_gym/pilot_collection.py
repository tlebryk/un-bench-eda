"""
Pilot Collection Script for UN Documents

This script executes a complete pilot collection for a single GA session (78th),
collecting metadata, building version chains, and optionally downloading documents.
"""

import logging
from pathlib import Path
import json
from datetime import datetime
import argparse

from metadata_collector import UNMetadataCollector
from version_chain import VersionChainBuilder
from document_downloader import UNDocumentDownloader

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('data/logs/pilot_collection.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def collect_session_metadata(session: int, collector: UNMetadataCollector) -> dict:
    """
    Collect all metadata for a session.

    Args:
        session: Session number
        collector: UNMetadataCollector instance

    Returns:
        Dictionary with all metadata
    """
    logger.info(f"=" * 80)
    logger.info(f"PHASE 1: Collecting metadata for session {session}")
    logger.info(f"=" * 80)

    metadata = {
        'session': session,
        'collection_timestamp': datetime.now().isoformat(),
        'resolutions': [],
        'committee_drafts': {},
        'plenary_drafts': [],
        'voting_records': []
    }

    # Collect resolutions
    logger.info(f"Collecting resolutions for session {session}...")
    resolutions = collector.get_session_resolutions(session)
    metadata['resolutions'] = resolutions
    logger.info(f"Found {len(resolutions)} resolutions")

    # Collect committee drafts
    logger.info(f"Collecting committee drafts for session {session}...")
    for committee in range(1, 7):
        logger.info(f"  Committee {committee}...")
        drafts = collector.get_committee_drafts(committee, session)
        metadata['committee_drafts'][committee] = drafts
        logger.info(f"  Found {len(drafts)} drafts for Committee {committee}")

    # Collect plenary drafts
    logger.info(f"Collecting plenary drafts for session {session}...")
    plenary_drafts = collector.get_session_drafts(session)
    metadata['plenary_drafts'] = plenary_drafts
    logger.info(f"Found {len(plenary_drafts)} plenary drafts")

    # Collect voting records
    logger.info(f"Collecting voting records for session {session}...")
    voting_records = collector.get_voting_records(session)
    metadata['voting_records'] = voting_records
    logger.info(f"Found {len(voting_records)} voting records")

    # Summary statistics
    total_drafts = len(plenary_drafts) + sum(len(drafts) for drafts in metadata['committee_drafts'].values())
    logger.info(f"\nMetadata collection complete:")
    logger.info(f"  Resolutions: {len(resolutions)}")
    logger.info(f"  Total drafts: {total_drafts}")
    logger.info(f"  Voting records: {len(voting_records)}")

    return metadata


def save_metadata(metadata: dict, output_dir: Path):
    """
    Save metadata to JSON files.

    Args:
        metadata: Metadata dictionary
        output_dir: Output directory
    """
    logger.info(f"Saving metadata to {output_dir}...")

    session = metadata['session']
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save resolutions
    with open(output_dir / f"{session}_resolutions.json", 'w', encoding='utf-8') as f:
        json.dump(metadata['resolutions'], f, indent=2, ensure_ascii=False)

    # Save committee drafts
    for committee, drafts in metadata['committee_drafts'].items():
        with open(output_dir / f"{session}_committee_{committee}_drafts.json", 'w', encoding='utf-8') as f:
            json.dump(drafts, f, indent=2, ensure_ascii=False)

    # Save plenary drafts
    with open(output_dir / f"{session}_plenary_drafts.json", 'w', encoding='utf-8') as f:
        json.dump(metadata['plenary_drafts'], f, indent=2, ensure_ascii=False)

    # Save voting records
    with open(output_dir / f"{session}_voting_records.json", 'w', encoding='utf-8') as f:
        json.dump(metadata['voting_records'], f, indent=2, ensure_ascii=False)

    # Save complete metadata
    with open(output_dir / f"{session}_complete_metadata.json", 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    logger.info(f"Metadata saved successfully")


def build_version_chains(metadata: dict, builder: VersionChainBuilder) -> list:
    """
    Build version chains from metadata.

    Args:
        metadata: Metadata dictionary
        builder: VersionChainBuilder instance

    Returns:
        List of VersionChain objects
    """
    logger.info(f"=" * 80)
    logger.info(f"PHASE 2: Building version chains")
    logger.info(f"=" * 80)

    # Combine all drafts
    all_drafts = metadata['plenary_drafts'].copy()
    for drafts in metadata['committee_drafts'].values():
        all_drafts.extend(drafts)

    logger.info(f"Total drafts: {len(all_drafts)}")

    # Build chains
    chains = builder.build_all_chains(
        metadata['resolutions'],
        all_drafts,
        metadata['voting_records']
    )

    # Print statistics
    stats = builder.get_statistics(chains)
    logger.info(f"\nVersion chain statistics:")
    logger.info(f"  Total chains: {stats['total_chains']}")
    logger.info(f"  Chains with drafts: {stats['chains_with_drafts']}")
    logger.info(f"  Chains without drafts: {stats['chains_without_drafts']}")
    logger.info(f"  Total versions: {stats['total_versions']}")
    logger.info(f"  Average versions per chain: {stats['average_versions_per_chain']:.2f}")

    if stats['modification_type_counts']:
        logger.info(f"  Modification types:")
        for mod_type, count in stats['modification_type_counts'].items():
            logger.info(f"    {mod_type}: {count}")

    return chains


def download_documents(chains: list, downloader: UNDocumentDownloader, max_downloads: int = None):
    """
    Download documents for version chains.

    Args:
        chains: List of VersionChain objects
        downloader: UNDocumentDownloader instance
        max_downloads: Optional maximum number of documents to download
    """
    logger.info(f"=" * 80)
    logger.info(f"PHASE 3: Downloading documents")
    logger.info(f"=" * 80)

    # Collect all documents to download
    documents = []
    for chain in chains:
        for version in chain.versions:
            documents.append({
                'symbol': version.symbol,
                'record_id': version.record_id,
                'title': version.title
            })

    if max_downloads:
        logger.info(f"Limiting downloads to {max_downloads} documents")
        documents = documents[:max_downloads]

    logger.info(f"Downloading {len(documents)} documents...")

    # Download
    successful, failed = downloader.batch_download(documents, skip_existing=True)

    logger.info(f"\nDownload complete:")
    logger.info(f"  Successful: {len(successful)}")
    logger.info(f"  Failed: {len(failed)}")

    if failed:
        logger.info(f"  Failed symbols:")
        for symbol in failed[:10]:  # Show first 10
            logger.info(f"    - {symbol}")
        if len(failed) > 10:
            logger.info(f"    ... and {len(failed) - 10} more")

    # Show download statistics
    stats = downloader.get_download_statistics()
    logger.info(f"\nOverall download statistics:")
    logger.info(f"  Total downloads attempted: {stats['total_downloads']}")
    logger.info(f"  Success rate: {stats['success_rate']:.1%}")
    logger.info(f"  Total size: {stats['total_size_mb']:.2f} MB")


def validate_chains(chains: list, num_samples: int = 5):
    """
    Display sample chains for manual validation.

    Args:
        chains: List of VersionChain objects
        num_samples: Number of sample chains to display
    """
    logger.info(f"=" * 80)
    logger.info(f"VALIDATION: Sample version chains")
    logger.info(f"=" * 80)

    # Filter chains with drafts
    chains_with_drafts = [c for c in chains if c.draft_base_symbol]

    if not chains_with_drafts:
        logger.warning("No chains with drafts found for validation")
        return

    samples = chains_with_drafts[:num_samples]

    for i, chain in enumerate(samples, 1):
        logger.info(f"\nSample Chain {i}:")
        logger.info(f"  Resolution: {chain.resolution_symbol}")
        logger.info(f"  Draft base: {chain.draft_base_symbol}")
        logger.info(f"  Versions ({len(chain.versions)}):")
        for version in chain.versions:
            logger.info(f"    - {version.symbol}")
            if version.title:
                logger.info(f"      Title: {version.title[:80]}...")
            if version.date:
                logger.info(f"      Date: {version.date}")


def main():
    """Execute pilot collection."""
    parser = argparse.ArgumentParser(description='UN Document Pilot Collection')
    parser.add_argument('--session', type=int, default=78,
                        help='GA session number (default: 78)')
    parser.add_argument('--download', action='store_true',
                        help='Download documents (default: metadata only)')
    parser.add_argument('--max-downloads', type=int, default=None,
                        help='Maximum number of documents to download')
    parser.add_argument('--validate', type=int, default=5,
                        help='Number of sample chains to display for validation (default: 5)')

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("UN DOCUMENT PILOT COLLECTION")
    logger.info(f"Session: {args.session}")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 80)

    # Initialize components
    collector = UNMetadataCollector(rate_limit=0.5, use_cache=True)
    builder = VersionChainBuilder()
    downloader = UNDocumentDownloader(rate_limit=1.0)

    # Phase 1: Collect metadata
    metadata = collect_session_metadata(args.session, collector)

    # Save metadata
    metadata_dir = Path(f"data/metadata/sessions")
    save_metadata(metadata, metadata_dir)

    # Phase 2: Build version chains
    chains = build_version_chains(metadata, builder)

    # Save chains
    chains_dir = Path(f"data/metadata/version_chains")
    chains_dir.mkdir(parents=True, exist_ok=True)
    builder.save_chains(chains, chains_dir / f"{args.session}_chains.json")

    # Validation
    if args.validate > 0:
        validate_chains(chains, args.validate)

    # Phase 3: Download documents (optional)
    if args.download:
        download_documents(chains, downloader, args.max_downloads)
    else:
        logger.info(f"=" * 80)
        logger.info("Skipping document download (use --download to enable)")
        logger.info(f"=" * 80)

    # Final summary
    logger.info(f"\n" + "=" * 80)
    logger.info("PILOT COLLECTION COMPLETE")
    logger.info(f"=" * 80)
    logger.info(f"Session: {args.session}")
    logger.info(f"Resolutions: {len(metadata['resolutions'])}")
    logger.info(f"Version chains: {len(chains)}")
    logger.info(f"Metadata saved to: {metadata_dir}")
    logger.info(f"Chains saved to: {chains_dir / f'{args.session}_chains.json'}")

    if args.download:
        stats = downloader.get_download_statistics()
        logger.info(f"Documents downloaded: {stats['successful']}")
        logger.info(f"Download size: {stats['total_size_mb']:.2f} MB")

    logger.info(f"\nNext steps:")
    logger.info(f"  1. Review validation samples above")
    logger.info(f"  2. Check metadata files in {metadata_dir}")
    logger.info(f"  3. Inspect version chains in {chains_dir}")
    if not args.download:
        logger.info(f"  4. Run with --download to fetch documents")
    else:
        logger.info(f"  4. Review downloaded documents in data/documents/pdfs/")


if __name__ == "__main__":
    main()
