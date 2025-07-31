from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel


class AnalysisStatusResponse(BaseModel):
    doc_id: int
    status: str


class AnalysisResultResponse(BaseModel):
    doc_id: int
    status: str
    result: str | None = None
    error: str | None = None


class Chunk(BaseModel):
    id: int
    chunk_index: int
    text: str


class Document(BaseModel):
    id: int
    filename: str
    content_type: str
    upload_time: datetime
    num_chunks: int


class DocumentAnalysisResponse(BaseModel):
    document: Document
    chunks: list[Chunk]
    total_chunks: int
    skip: int
    limit: int


class AnalysisStatusResponse(BaseModel):
    status: str
    message: str
    document_id: int
    task_id: int


class TaskStatusResponse(BaseModel):
    task_id: str
    task_status: str  # PENDING, STARTED, SUCCESS, FAILURE, RETRY, REVOKED etc.
    document_id: Optional[int]
    analysis_result: Optional[str]  # completed, failed, in_progress
    issues_found: Optional[List[dict]]
    error: Optional[str]

class DocumentAnalysisStatusResponse(BaseModel):
    document_id: int
    analyzed: bool
    issues_count: int
    status: str  # not_analyzed, in_progress, completed
    last_analyzed: Optional[datetime]
    sample_issues: Optional[List[str]]