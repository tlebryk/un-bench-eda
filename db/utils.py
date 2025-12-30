"""Database utility functions"""

from db.models import Base
from db.config import engine


def create_tables(db_engine=None):
    """Create all database tables

    Args:
        db_engine: SQLAlchemy engine to use (default: production engine)
    """
    target_engine = db_engine or engine
    Base.metadata.create_all(target_engine)
    print("✅ Database tables created successfully")


def drop_tables(db_engine=None):
    """Drop all database tables - USE WITH CAUTION

    Args:
        db_engine: SQLAlchemy engine to use (default: production engine)
    """
    target_engine = db_engine or engine
    Base.metadata.drop_all(target_engine)
    print("⚠️  All database tables dropped")


def reset_database(db_engine=None):
    """Drop and recreate all tables - USE WITH CAUTION

    Args:
        db_engine: SQLAlchemy engine to use (default: production engine)
    """
    print("⚠️  Resetting database...")
    drop_tables(db_engine)
    create_tables(db_engine)
    print("✅ Database reset complete")
