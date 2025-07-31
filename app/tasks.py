import httpx
import re
import json
from app.celery_app import celery_app

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, insert

from app.backend.db import create_async_engine
from app.config import settings
from app.models.analyzed_doc import AnalyzedDocIssues
from app.schemas.analyzer import DocumentAnalysisResponse
from app.services.analyzer_service import analyze_chunk_with_ollama


@celery_app.task(bind=True)
async def analyze_document_task(self, doc_id: int, language: str, retry: bool = False):
    engine = create_async_engine(settings.DATABASE_URL)
    async with AsyncSession(engine) as db:
        try:
            analyzed_issues = await db.scalar(
                select(AnalyzedDocIssues).where(AnalyzedDocIssues.document_id == doc_id).exists().select())
            if analyzed_issues and not retry:
                return {
                    "status": "success",
                    "message": f"Analysis is already done for document {doc_id}",
                    "document_id": doc_id
                }

            if retry:
                await db.execute(delete(AnalyzedDocIssues).where(AnalyzedDocIssues.document_id == doc_id))
                await db.commit()

            async with httpx.AsyncClient() as client:
                response = await client.get(f"{settings.DOCUMENT_SERVICE_URL}/api/documents/{doc_id}/chunks")
                response.raise_for_status()
                analysis_data = DocumentAnalysisResponse(**response.json())

                for chunk in analysis_data.chunks:
                    ollama_response = await analyze_chunk_with_ollama(chunk.text, language=language)
                    response_text = ollama_response.message['content']
                    match = re.search(r"\{.*}", response_text, re.DOTALL)
                    if match:
                        try:
                            parsed_json = json.loads(match.group())
                            if parsed_json.get('status') == 'issues_found':
                                for issue in parsed_json.get('issues'):
                                    await db.execute(insert(AnalyzedDocIssues).values(
                                        document_id=doc_id,
                                        issue=issue['text'],
                                        severity=issue['severity']
                                    ))
                                    await db.commit()
                        except json.JSONDecodeError:
                            continue

            return {
                "status": "success",
                "message": f"Analysis completed for document {doc_id}",
                "document_id": doc_id
            }

        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
                "document_id": doc_id
            }
