"""
Analyze revision coverage in collected data
"""

import json
from pathlib import Path
from collections import defaultdict

def analyze_revisions():
    """Analyze all collected committee drafts for revisions."""

    print("="*60)
    print("Revision Analysis - Session 78 Committee Drafts")
    print("="*60)
    print()

    total_docs = 0
    total_revisions = 0
    revision_examples = []

    for json_file in sorted(Path("data/parsed/metadata").glob("session_78_committee_*_drafts.json")):
        committee = json_file.stem.split('_')[3]  # Extract committee number

        data = json.load(open(json_file))
        symbols = [d.get('symbol', '') for d in data if d.get('symbol')]

        # Find revisions
        revisions = [s for s in symbols if '/Rev.' in s or '/Add.' in s or '/Corr.' in s]

        total_docs += len(symbols)
        total_revisions += len(revisions)

        pct = (len(revisions) / len(symbols) * 100) if symbols else 0
        print(f"Committee {committee}:")
        print(f"  Total: {len(symbols)}")
        print(f"  With modifications: {len(revisions)} ({pct:.1f}%)")

        if revisions:
            print(f"  Examples:")
            for rev in revisions:
                print(f"    - {rev}")
                revision_examples.append(rev)
        print()

    print("="*60)
    print("Summary")
    print("="*60)
    print(f"Total documents: {total_docs}")
    print(f"Documents with modifications: {total_revisions} ({total_revisions/total_docs*100:.1f}%)")
    print()

    if revision_examples:
        print(f"Total unique revisions collected: {len(revision_examples)}")
        print()

        # Count modification types
        rev_count = sum(1 for s in revision_examples if '/Rev.' in s)
        add_count = sum(1 for s in revision_examples if '/Add.' in s)
        corr_count = sum(1 for s in revision_examples if '/Corr.' in s)

        print("By modification type:")
        print(f"  Rev (Revisions): {rev_count}")
        print(f"  Add (Addenda): {add_count}")
        print(f"  Corr (Corrigenda): {corr_count}")
        print()

        # Check for version chains (multiple revisions of same base)
        base_symbols = defaultdict(list)
        for rev in revision_examples:
            # Extract base (everything before first modification)
            if '/Rev.' in rev:
                base = rev.split('/Rev.')[0]
            elif '/Add.' in rev:
                base = rev.split('/Add.')[0]
            elif '/Corr.' in rev:
                base = rev.split('/Corr.')[0]
            else:
                continue
            base_symbols[base].append(rev)

        chains = {base: versions for base, versions in base_symbols.items() if len(versions) > 1}
        if chains:
            print(f"Version chains (multiple modifications of same base): {len(chains)}")
            for base, versions in list(chains.items())[:5]:
                print(f"  {base}:")
                for v in sorted(versions):
                    print(f"    → {v}")
        else:
            print("⚠️  No version chains found (no documents with multiple modifications)")

    else:
        print("❌ NO REVISIONS FOUND")
        print()
        print("This suggests:")
        print("  1. API query might not be capturing revisions")
        print("  2. Revisions might be in a separate collection")
        print("  3. Session 78 may have few revised drafts")

if __name__ == "__main__":
    analyze_revisions()
