from typing import Annotated
from typing import Literal

from celery.result import AsyncResult
from fastapi import APIRouter, Path, Query, Depends, logger
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.db_depends import get_db
from app.models.analyzed_doc import AnalyzedDocIssues
from app.schemas.analyzer import *
from app.tasks import analyze_document_task

router = APIRouter(prefix='/analyze', tags=['analyzer'])

AllowedLanguage = Literal['ru', 'en']


@router.post('/{doc_id}', status_code=202, summary='Run document analysis', response_model=AnalysisStatusResponse)
async def analyze_doc(
        doc_id: Annotated[int, Path(ge=0)],
        language: Annotated[AllowedLanguage, Query(..., title='Language', description="Select 'ru' or 'en'")],
        retry: bool = False
):
    # Запускаем задачу в Celery
    task = analyze_document_task.delay(doc_id, language, retry)

    return AnalysisStatusResponse(
        status="accepted",
        message=f"Analysis started for document {doc_id}",
        document_id=doc_id,
        task_id=task.id
    )


@router.get('/status/{task_id}', status_code=200,
            summary='Get analysis task status',
            response_model=TaskStatusResponse)
async def get_task_status(
        task_id: str = Path(..., description="ID задачи анализа"),
        db: AsyncSession = Depends(get_db)
):
    """
    Проверяет статус задачи анализа документа.
    Возвращает:
    - Статус задачи (PENDING, STARTED, SUCCESS, FAILURE)
    - Результат анализа (если задача завершена)
    - Информацию об ошибке (если задача завершилась с ошибкой)
    """
    task_result = AsyncResult(task_id)
    response_data = {
        "task_id": task_id,
        "task_status": task_result.status,
        "document_id": None,
        "analysis_result": None,
        "issues_found": None,
        "progress": 0,
        "error": None
    }

    # Task completed successfully
    if task_result.successful():
        result = task_result.result

        # Ensure we have the document_id
        doc_id = result.get("document_id")
        response_data["document_id"] = doc_id

        # Handle different completion states
        if result.get("analysis_result") == "completed_no_issues":
            response_data.update({
                "analysis_result": "completed",
                "issues_found": False,
                "progress": 100
            })
        elif result.get("analysis_result") in ("completed_with_issues", "completed_with_issues_and_failed_to_inserted"):
            # Only query DB if we're sure the task is fully complete
            if result.get("progress") == 100:
                issues_count = await db.scalar(
                    select(func.count(AnalyzedDocIssues.id))
                    .where(AnalyzedDocIssues.document_id == doc_id)
                )
                response_data.update({
                    "analysis_result": "completed",
                    "issues_found": issues_count > 0,
                    "progress": 100,
                    "issues_count": issues_count
                })
            else:
                # Task is still processing issues
                response_data.update({
                    "analysis_result": "processing",
                    "progress": result.get("progress", 0)
                })

    # Task failed
    elif task_result.failed():
        error_info = str(task_result.result)
        response_data.update({
            "analysis_result": "failed",
            "error": error_info,
            "progress": 100,
            "issues_found": False
        })

    return response_data


@router.get('/document/{doc_id}/status', status_code=200,
            summary='Get document analysis status',
            response_model=DocumentAnalysisStatusResponse)
async def get_document_status(
        doc_id: int = Path(..., ge=0, description="ID документа"),
        db: AsyncSession = Depends(get_db)
):
    """
    Проверяет статус анализа для конкретного документа.
    Возвращает:
    - analyzed: Был ли документ проанализирован
    - issues_count: Количество найденных проблем
    - status: Статус анализа (not_analyzed/in_progress/completed)
    - sample_issues: Примеры проблем (первые 3)
    """
    try:
        # Check for existing analysis (single query with aggregation)
        analysis_data = await db.execute(
            select(
                func.count(AnalyzedDocIssues.id).label('total_issues'),
                func.array_agg(
                    case(
                        (AnalyzedDocIssues.severity == 'critical', 'CRITICAL: ' + AnalyzedDocIssues.issue),
                        (AnalyzedDocIssues.severity == 'major', 'MAJOR: ' + AnalyzedDocIssues.issue),
                        else_='MINOR: ' + AnalyzedDocIssues.issue
                    )
                ).label('formatted_issues')
            )
            .where(AnalyzedDocIssues.document_id == doc_id)
        )
        result = analysis_data.first()

        if result and result.total_issues > 0:
            return DocumentAnalysisStatusResponse(
                document_id=doc_id,
                analyzed=True,
                issues_count=result.total_issues,
                status="completed",
                last_analyzed=None,  # Removed since model doesn't have created_at
                sample_issues=result.formatted_issues[:3] if result.formatted_issues else None
            )

        # Check active Celery tasks
        from app.celery_app import celery_app
        inspector = celery_app.control.inspect()

        is_being_analyzed = False
        if active_tasks := inspector.active():
            for worker_tasks in active_tasks.values():
                for task in worker_tasks:
                    task_args = task.get('args', [])
                    task_kwargs = task.get('kwargs', {})
                    if (isinstance(task_args, (list, tuple)) and len(task_args) > 0 and task_args[0] == doc_id) or \
                            (isinstance(task_kwargs, dict) and task_kwargs.get('doc_id') == doc_id):
                        is_being_analyzed = True
                        break

        return DocumentAnalysisStatusResponse(
            document_id=doc_id,
            analyzed=False,
            issues_count=0,
            status="in_progress" if is_being_analyzed else "not_analyzed",
            last_analyzed=None,
            sample_issues=None
        )

    except Exception as e:
        return DocumentAnalysisStatusResponse(
            document_id=doc_id,
            analyzed=False,
            issues_count=0,
            status="not_analyzed",
            last_analyzed=None,
            sample_issues=None
        )


@router.get('/result', status_code=200)
async def get_result(
        doc_id: int,
        db: AsyncSession = Depends(get_db)
):
    results = await db.scalars(
        select(AnalyzedDocIssues)
        .where(AnalyzedDocIssues.document_id == doc_id)
    )
    return results.all()
