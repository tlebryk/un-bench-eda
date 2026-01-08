#!/usr/bin/env python3
"""Update existing documents with body_text from PDF files"""

import os
from pathlib import Path
from db.config import get_session
from db.models import Document
from etl.load_resolutions import ResolutionLoader

# Get database session
session = get_session()

# Create loader to use its _load_pdf_text method
data_root = Path(os.getenv('DATA_ROOT', 'data'))
loader = ResolutionLoader(data_root=data_root, session=session)

# Query all resolutions
resolutions = session.query(Document).filter(
    Document.doc_type == 'resolution'
).all()

print(f"Found {len(resolutions)} resolutions to update")
print("=" * 80)

updated = 0
skipped = 0
errors = 0

for i, doc in enumerate(resolutions, 1):
    if i % 50 == 0:
        print(f"Progress: {i}/{len(resolutions)}...")

    try:
        # Load PDF text using the loader's method
        body_text = loader._load_pdf_text(doc.symbol)

        if body_text:
            doc.body_text = body_text
            updated += 1
        else:
            skipped += 1
            if i <= 5:  # Show first few skips
                print(f"  ⚠️  No PDF text for {doc.symbol}")
    except Exception as e:
        errors += 1
        print(f"  ❌ Error updating {doc.symbol}: {e}")

# Commit changes
try:
    session.commit()
    print("\n" + "=" * 80)
    print(f"✅ Update complete!")
    print(f"   Updated: {updated}")
    print(f"   Skipped (no PDF): {skipped}")
    print(f"   Errors: {errors}")
except Exception as e:
    session.rollback()
    print(f"\n❌ Commit failed: {e}")
finally:
    session.close()
