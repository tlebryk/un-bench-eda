"""Database connection configuration"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get database URL from environment
DATABASE_URL = os.getenv('DATABASE_URL')
DEV_DATABASE_URL = os.getenv('DEV_DATABASE_URL')

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set. Check your .env file.")

# Create production engine
engine = create_engine(DATABASE_URL, echo=False)

# Create dev engine (if DEV_DATABASE_URL is set)
dev_engine = create_engine(DEV_DATABASE_URL, echo=False) if DEV_DATABASE_URL else None

# Create session factory
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_session():
    """Get a new database session"""
    return SessionLocal()


def get_dev_engine():
    """Get dev database engine. Returns None if DEV_DATABASE_URL not set."""
    return dev_engine
