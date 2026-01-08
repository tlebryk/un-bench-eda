#!/bin/bash
# Sync local PostgreSQL to Supabase
# Usage: ./scripts/sync_to_supabase.sh

set -e

echo "======================================================================"
echo "Sync Local Database to Supabase"
echo "======================================================================"

# Load .env and parse DATABASE_URL
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found"
    exit 1
fi

source .env

# Parse DATABASE_URL to extract credentials
# Format: postgresql://USER:PASSWORD@HOST:PORT/DATABASE
if [ -z "$DATABASE_URL" ]; then
    echo "❌ Error: DATABASE_URL not set in .env"
    exit 1
fi

# Extract connection details from DATABASE_URL
PGPASSWORD=$(echo $DATABASE_URL | sed -n 's/.*:\/\/[^:]*:\([^@]*\)@.*/\1/p')
PGHOST=$(echo $DATABASE_URL | sed -n 's/.*@\([^:]*\):.*/\1/p')
PGPORT=$(echo $DATABASE_URL | sed -n 's/.*:\([0-9]*\)\/.*/\1/p')
PGUSER=$(echo $DATABASE_URL | sed -n 's/.*:\/\/\([^:]*\):.*/\1/p')
PGDATABASE=$(echo $DATABASE_URL | sed -n 's/.*\/\([^?]*\).*/\1/p')

echo ""
echo "Supabase connection:"
echo "  Host: $PGHOST"
echo "  Port: $PGPORT"
echo "  User: $PGUSER"
echo "  Database: $PGDATABASE"

# Step 1: Ensure Docker is running
echo ""
echo "🐳 Step 1: Starting local database..."
docker-compose up -d

# Wait a moment for DB to be ready
sleep 2
echo "   ✅ Local database running"

# Step 2: Dump local database
echo ""
echo "📦 Step 2: Dumping local database..."
docker exec un_documents_db pg_dump \
    -U un_user \
    -d un_documents \
    --no-owner \
    --no-privileges \
    --clean \
    --if-exists \
    > un_documents_dump.sql

lines=$(wc -l < un_documents_dump.sql)
size=$(ls -lh un_documents_dump.sql | awk '{print $5}')
echo "   ✅ Exported $lines lines ($size)"

# Step 3: Restore to Supabase
echo ""
echo "☁️  Step 3: Restoring to Supabase..."
echo "   This may take 1-2 minutes..."

docker exec -i -e PGPASSWORD="$PGPASSWORD" un_documents_db psql \
    -h "$PGHOST" \
    -p "$PGPORT" \
    -U "$PGUSER" \
    -d "$PGDATABASE" \
    < un_documents_dump.sql 2>&1 | grep -E "(ERROR|FATAL)" || true

echo ""
echo "======================================================================"
echo "✅ Sync Complete!"
echo "======================================================================"
echo ""
echo "Verify with:"
echo "  uv run -m scripts.verify_supabase"
echo ""
