"""Database utility functions"""

from db.models import Base
from db.config import engine


def create_tables():
    """Create all database tables"""
    Base.metadata.create_all(engine)
    print("✅ Database tables created successfully")


def drop_tables():
    """Drop all database tables - USE WITH CAUTION"""
    Base.metadata.drop_all(engine)
    print("⚠️  All database tables dropped")


def reset_database():
    """Drop and recreate all tables - USE WITH CAUTION"""
    print("⚠️  Resetting database...")
    drop_tables()
    create_tables()
    print("✅ Database reset complete")
