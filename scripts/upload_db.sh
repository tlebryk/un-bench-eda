#!/bin/bash
# Upload local PostgreSQL database to Supabase
set -euo pipefail

# docker-compose down
docker-compose up -d postgres
docker exec -T un_documents_db pg_dump \
    -U un_user \
    -d un_documents \
    --no-owner \
    --no-privileges \
    --clean \
    > un_documents_dump.sql
set -a
source ./.env
set +a
docker exec -i -e PGPASSWORD="$password" un_documents_db psql \
    -h aws-0-us-west-2.pooler.supabase.com \
    -p 5432 \
    -U postgres.dziodvvqekbmnroygzwp \
    -d postgres \
    < un_documents_dump.sql