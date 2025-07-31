from typing import Literal

from sqlalchemy import Integer, Text, String
from sqlalchemy.orm import Mapped, mapped_column

from app.backend.db import Base

SeverityStages = Literal['critical', 'minor', 'ignore']


class AnalyzedDocIssues(Base):
    """All analyzed issues"""
    __tablename__ = 'analyzed_docs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(Integer, nullable=False)
    issue: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[SeverityStages] = mapped_column(String(8), nullable=False)
