from app.celery_app import celery_app
import httpx
import re
import json
import asyncio
from sqlalchemy import select, delete, insert, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.config import settings
from app.models.analyzed_doc import AnalyzedDocIssues
from app.schemas.analyzer import DocumentAnalysisResponse
from app.services.analyzer_service import analyze_chunk_with_ollama


@celery_app.task(bind=True, max_retries=3)
def analyze_document_task(self, doc_id: int, language: str, retry: bool = False):
    async def _async_analyze():
        print(f"Using database URL: {settings.DATABASE_URL}")
        engine = create_async_engine(settings.DATABASE_URL)
        async with AsyncSession(engine) as session:
            try:
                # Initialize result structure
                result = {
                    "document_id": doc_id,
                    "analysis_result": "processing",
                    "issues_found": None,
                    "error": None,
                    "progress": 0
                }

                # Update initial progress
                self.update_state(state='PROGRESS', meta=result)

                # Check if document already exists
                existing = await session.scalar(
                    select(AnalyzedDocIssues)
                    .where(AnalyzedDocIssues.document_id == doc_id)
                    .limit(1)
                )

                if existing and not retry:
                    result.update({
                        "analysis_result": "exists",
                        "progress": 100
                    })
                    return result

                # Clear existing analysis if retry
                if retry:
                    await session.execute(
                        delete(AnalyzedDocIssues)
                        .where(AnalyzedDocIssues.document_id == doc_id)
                    )
                    await session.commit()

                # Fetch document chunks
                result.update({"progress": 25})
                self.update_state(state='PROGRESS', meta=result)

                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"{settings.DOCUMENT_SERVICE_URL}/api/documents/{doc_id}/chunks",
                        timeout=30.0
                    )
                    response.raise_for_status()
                    analysis_data = DocumentAnalysisResponse(**response.json())

                    # Process chunks
                    issues_found = []
                    total_chunks = len(analysis_data.chunks)

                    for i, chunk in enumerate(analysis_data.chunks, 1):
                        # Update chunk processing progress
                        chunk_progress = 25 + (i / total_chunks) * 75
                        result.update({
                            "progress": chunk_progress,
                            "current_chunk": i,
                            "total_chunks": total_chunks
                        })
                        self.update_state(state='PROGRESS', meta=result)

                        # Analyze chunk
                        ollama_response = analyze_chunk_with_ollama(
                            chunk.text,
                            language=language
                        )
                        response_text = ollama_response["message"]["content"]

                        if match := re.search(r"\{.*}", response_text, re.DOTALL):
                            try:
                                parsed_json = json.loads(match.group())
                                if parsed_json.get("status") == "issues_found":
                                    issues_found.extend(parsed_json.get('issues', []))
                            except json.JSONDecodeError as e:
                                print(f"JSON decode error: {e}")

                    # Prepare final result
                    if issues_found:
                        result.update({
                            "analysis_result": "completed_with_issues_but_not_inserted",
                            "issues_found": issues_found,
                            "progress": 90
                        })
                    else:
                        result.update({
                            "analysis_result": "completed_no_issues",
                            "progress": 100
                        })

                    # Insert found issues
                    # Modify your insertion block like this:
                    if issues_found:
                        try:
                            await session.execute(
                                insert(AnalyzedDocIssues),
                                [
                                    {
                                        "document_id": doc_id,
                                        "issue": issue["text"],
                                        "severity": issue["severity"]
                                    }
                                    for issue in issues_found
                                ]
                            )
                            await session.commit()
                            print(f"Successfully committed issues for document {doc_id}")

                            # Verify insertion
                            inserted_count = await session.scalar(
                                select(func.count(AnalyzedDocIssues.id)).where(
                                    AnalyzedDocIssues.document_id == doc_id
                                )
                            )
                            print(f"Verification found {inserted_count} inserted records")

                            if inserted_count >= len(issues_found):
                                result.update({
                                    "progress": 100,
                                    "analysis_result": "completed_with_issues",
                                    "inserted_issues": inserted_count
                                })
                            else:
                                result.update({
                                    "analysis_result": "completed_with_issues_but_insert_failed",
                                    "expected_issues": len(issues_found),
                                    "inserted_issues": inserted_count
                                })
                        except Exception as e:
                            print(f"Insertion failed: {str(e)}")
                            await session.rollback()
                            result.update({
                                "analysis_result": "completed_with_issues_but_insert_failed",
                                "error": str(e)
                            })

                    return result

            except Exception as e:
                # Format exception properly for Celery
                raise {
                    "exc_type": type(e).__name__,
                    "exc_message": str(e),
                    "document_id": doc_id,
                    "analysis_result": "failed",
                    "progress": 100
                }
            finally:
                await engine.dispose()

    try:
        result = asyncio.run(_async_analyze())

        # Handle explicit failure cases
        if isinstance(result, dict) and result.get("analysis_result") == "failed":
            self.update_state(state='FAILURE', meta=result)
            return result

        # Successful completion
        self.update_state(state='SUCCESS', meta=result)
        return result

    except Exception as e:
        if isinstance(e, dict):  # Our formatted exception
            error_result = e
        else:  # Unexpected exception
            error_result = {
                "exc_type": type(e).__name__,
                "exc_message": str(e),
                "document_id": doc_id,
                "analysis_result": "failed",
                "progress": 100
            }

        self.update_state(state='FAILURE', meta=error_result)
        raise self.retry(exc=e) if retry else e
