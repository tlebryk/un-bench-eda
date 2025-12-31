"""Database connection configuration"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Check if we should use dev database
USE_DEV_DB = os.getenv('USE_DEV_DB', 'false').lower() == 'true'

# Get database URL from environment
# Option 1: Direct DATABASE_URL (local development)
DATABASE_URL = os.getenv('DATABASE_URL')
DEV_DATABASE_URL = os.getenv('DEV_DATABASE_URL')

# Option 2: Construct from Supabase individual variables
if not DATABASE_URL:
    user = os.getenv('user')
    password = os.getenv('password')
    host = os.getenv('host')
    port = os.getenv('port')
    dbname = os.getenv('dbname')

    if all([user, password, host, port, dbname]):
        DATABASE_URL = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
        print(f"✅ Constructed DATABASE_URL from Supabase variables (host: {host})")
    else:
        raise ValueError(
            "DATABASE_URL not set. Provide either:\n"
            "  1. DATABASE_URL=postgresql://...\n"
            "  2. Individual variables: user, password, host, port, dbname"
        )

# Override with dev database if USE_DEV_DB is set
if USE_DEV_DB:
    if not DEV_DATABASE_URL:
        raise ValueError(
            "USE_DEV_DB=true but DEV_DATABASE_URL is not set!\n"
            "Add to your .env file:\n"
            "  DEV_DATABASE_URL=postgresql://un_user:un_password@localhost:5434/un_documents_dev"
        )
    DATABASE_URL = DEV_DATABASE_URL
    print("🔧 Using development database")

# Detect if we're using Supabase (requires SSL/TLS)
is_supabase = 'supabase.co' in DATABASE_URL or 'pooler.supabase.com' in DATABASE_URL

# Create engine with appropriate SSL settings
engine_kwargs = {'echo': False}
if is_supabase:
    # Supabase requires SSL connections in production
    engine_kwargs['connect_args'] = {'sslmode': 'require'}

engine = create_engine(DATABASE_URL, **engine_kwargs)

# Create dev engine (if DEV_DATABASE_URL is set, for reference)
dev_engine = None
if DEV_DATABASE_URL and not USE_DEV_DB:
    dev_kwargs = {'echo': False}
    if 'supabase.co' in DEV_DATABASE_URL:
        # Dev database on Supabase also needs SSL
        dev_kwargs['connect_args'] = {'sslmode': 'require'}
    dev_engine = create_engine(DEV_DATABASE_URL, **dev_kwargs)

# Create session factory
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_session():
    """Get a new database session"""
    return SessionLocal()


def get_dev_engine():
    """Get dev database engine. Returns None if DEV_DATABASE_URL not set."""
    return dev_engine
