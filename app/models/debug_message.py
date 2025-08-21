from sqlalchemy import Column, Integer, String, text, TIMESTAMP
from sqlalchemy.sql import func
from app.db.base import Base

class DebugMessage(Base):
    __tablename__ = "debug_messages"

    id = Column(Integer, primary_key=True, index=True)
    message = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
