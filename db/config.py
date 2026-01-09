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
# Option 1: Direct DATABASE_URL (admin user - for setup and migrations)
# Option 2: APP_DATABASE_URL (read-only user - for application queries)
DATABASE_URL = os.getenv('DATABASE_URL')
APP_DATABASE_URL = os.getenv('APP_DATABASE_URL')  # Read-only user
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

# Create admin engine (for setup_db.py and migrations)
admin_engine_kwargs = {'echo': False}
if is_supabase:
    # Supabase requires SSL connections in production
    admin_engine_kwargs['connect_args'] = {'sslmode': 'require'}

engine = create_engine(DATABASE_URL, **admin_engine_kwargs)  # Admin engine

# Create read-only engine for application queries (if APP_DATABASE_URL is set)
readonly_engine = None
if APP_DATABASE_URL:
    readonly_kwargs = {'echo': False}
    is_supabase_readonly = 'supabase.co' in APP_DATABASE_URL or 'pooler.supabase.com' in APP_DATABASE_URL
    if is_supabase_readonly:
        readonly_kwargs['connect_args'] = {'sslmode': 'require'}
    readonly_engine = create_engine(APP_DATABASE_URL, **readonly_kwargs)
    print("🔒 Using read-only database user for application queries")

# Create dev engine (if DEV_DATABASE_URL is set, for reference)
dev_engine = None
if DEV_DATABASE_URL and not USE_DEV_DB:
    dev_kwargs = {'echo': False}
    if 'supabase.co' in DEV_DATABASE_URL:
        # Dev database on Supabase also needs SSL
        dev_kwargs['connect_args'] = {'sslmode': 'require'}
    dev_engine = create_engine(DEV_DATABASE_URL, **dev_kwargs)

# Create session factories
# Admin session (for setup and migrations)
AdminSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

# Read-only session (for application queries)
if readonly_engine:
    ReadOnlySessionLocal = sessionmaker(bind=readonly_engine, autocommit=False, autoflush=False)
else:
    # Fall back to admin engine if APP_DATABASE_URL not set (backwards compatibility)
    ReadOnlySessionLocal = AdminSessionLocal
    print("⚠️  APP_DATABASE_URL not set - using admin credentials for queries")
    print("   For better security, run: uv run python db/setup_readonly_user.py")

# Default session uses read-only engine (safer for application use)
SessionLocal = ReadOnlySessionLocal


def get_session():
    """
    Get a new database session for application queries (read-only if configured).

    This uses APP_DATABASE_URL if available, otherwise falls back to DATABASE_URL.
    For write operations, use get_admin_session() instead.
    """
    return SessionLocal()


def get_readonly_session():
    """
    Get a new read-only database session.

    Same as get_session() but more explicit about intent.
    """
    return ReadOnlySessionLocal()


def get_admin_session():
    """
    Get a new admin database session with write permissions.

    Use this for setup_db.py, migrations, and other operations that need
    to modify the database. For normal queries, use get_session() instead.
    """
    return AdminSessionLocal()


def get_readonly_engine():
    """Get read-only database engine. Returns admin engine if APP_DATABASE_URL not set."""
    return readonly_engine if readonly_engine else engine


def get_admin_engine():
    """Get admin database engine with write permissions."""
    return engine


def get_dev_engine():
    """Get dev database engine. Returns None if DEV_DATABASE_URL not set."""
    return dev_engine
