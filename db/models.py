"""SQLAlchemy models for UN documents database"""

from sqlalchemy import Column, Integer, String, Text, Date, DateTime, ForeignKey, JSON
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime

Base = declarative_base()


class Document(Base):
    """Core table for all UN documents"""
    __tablename__ = 'documents'

    id = Column(Integer, primary_key=True)
    symbol = Column(String, unique=True, nullable=False, index=True)  # e.g., A/RES/78/220
    doc_type = Column(String, nullable=False, index=True)             # resolution, draft, meeting, etc.
    session = Column(Integer, index=True)                              # e.g., 78
    title = Column(Text)
    date = Column(Date)
    doc_metadata = Column(JSONB)  # Full JSON for flexibility (renamed to avoid SQLAlchemy reserved word)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    votes = relationship("Vote", back_populates="document", cascade="all, delete-orphan")
    source_relationships = relationship(
        "DocumentRelationship",
        foreign_keys="DocumentRelationship.source_id",
        back_populates="source_document",
        cascade="all, delete-orphan"
    )
    target_relationships = relationship(
        "DocumentRelationship",
        foreign_keys="DocumentRelationship.target_id",
        back_populates="target_document",
        cascade="all, delete-orphan"
    )
    utterances = relationship("Utterance", foreign_keys="Utterance.meeting_id", cascade="all, delete-orphan")
    referenced_in_utterances = relationship("UtteranceDocument", foreign_keys="UtteranceDocument.document_id", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Document(symbol='{self.symbol}', type='{self.doc_type}')>"


class Actor(Base):
    """Countries, organizations, and speakers"""
    __tablename__ = 'actors'

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False, index=True)
    actor_type = Column(String, default='country')  # country, observer, un_official
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    votes = relationship("Vote", back_populates="actor")
    utterances = relationship("Utterance", foreign_keys="Utterance.speaker_actor_id")

    def __repr__(self):
        return f"<Actor(name='{self.name}', type='{self.actor_type}')>"


class Vote(Base):
    """Voting records (committee and plenary)"""
    __tablename__ = 'votes'

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey('documents.id', ondelete='CASCADE'), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey('actors.id'), nullable=False, index=True)
    vote_type = Column(String, nullable=False)      # in_favour, against, abstaining
    vote_context = Column(String)                    # plenary, committee
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    document = relationship("Document", back_populates="votes")
    actor = relationship("Actor", back_populates="votes")

    def __repr__(self):
        return f"<Vote(doc={self.document_id}, actor={self.actor_id}, type='{self.vote_type}')>"


class DocumentRelationship(Base):
    """Links between documents (draft -> resolution, etc.)"""
    __tablename__ = 'document_relationships'

    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey('documents.id', ondelete='CASCADE'), nullable=False, index=True)
    target_id = Column(Integer, ForeignKey('documents.id', ondelete='CASCADE'), nullable=False, index=True)
    relationship_type = Column(String, nullable=False, index=True)  # draft_of, committee_report_for, etc.
    rel_metadata = Column(JSONB)  # Renamed to avoid SQLAlchemy reserved word
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    source_document = relationship("Document", foreign_keys=[source_id], back_populates="source_relationships")
    target_document = relationship("Document", foreign_keys=[target_id], back_populates="target_relationships")

    def __repr__(self):
        return f"<DocumentRelationship(source={self.source_id}, target={self.target_id}, type='{self.relationship_type}')>"


class Utterance(Base):
    """Statements made in meetings (plenary and committee)"""
    __tablename__ = 'utterances'

    id = Column(Integer, primary_key=True)
    meeting_id = Column(Integer, ForeignKey('documents.id', ondelete='CASCADE'), nullable=False, index=True)
    section_id = Column(String)  # e.g., "A/78/PV.80_section_11" for tracking which agenda item section
    agenda_item_number = Column(String, index=True)  # e.g., "11", "20"
    
    # Speaker information
    speaker_actor_id = Column(Integer, ForeignKey('actors.id', ondelete='SET NULL'), nullable=True, index=True)
    speaker_name = Column(String)  # Parsed name (e.g., "El-Sonni")
    speaker_role = Column(String)  # e.g., "The President", "delegate"
    speaker_raw = Column(Text)  # Original speaker string from PDF
    speaker_affiliation = Column(String)  # Country or organization (e.g., "Libya")
    
    # Content
    text = Column(Text, nullable=False)
    word_count = Column(Integer)
    position_in_meeting = Column(Integer)  # Order within meeting
    position_in_section = Column(Integer)  # Order within agenda item section
    
    # Metadata from parsing
    utterance_metadata = Column(JSONB)  # resolution_metadata, draft_resolution_mentions, etc.
    
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    meeting = relationship("Document", foreign_keys=[meeting_id], overlaps="utterances")
    speaker_actor = relationship("Actor", foreign_keys=[speaker_actor_id], overlaps="utterances")
    referenced_documents = relationship(
        "UtteranceDocument",
        back_populates="utterance",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Utterance(id={self.id}, meeting_id={self.meeting_id}, speaker='{self.speaker_name}')>"


class UtteranceDocument(Base):
    """Junction table linking utterances to documents they reference (drafts, resolutions, agenda items)"""
    __tablename__ = 'utterance_documents'

    id = Column(Integer, primary_key=True)
    utterance_id = Column(Integer, ForeignKey('utterances.id', ondelete='CASCADE'), nullable=False, index=True)
    document_id = Column(Integer, ForeignKey('documents.id', ondelete='CASCADE'), nullable=False, index=True)
    reference_type = Column(String)  # 'mentioned', 'about', 'voting_on', etc.
    context = Column(Text)  # The sentence/context where the document was mentioned
    
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    utterance = relationship("Utterance", back_populates="referenced_documents")
    document = relationship("Document", overlaps="referenced_in_utterances")

    def __repr__(self):
        return f"<UtteranceDocument(utterance_id={self.utterance_id}, document_id={self.document_id})>"
