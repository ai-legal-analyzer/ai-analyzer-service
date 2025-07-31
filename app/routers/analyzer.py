from typing import Annotated
from typing import Literal

from celery.result import AsyncResult
from fastapi import APIRouter, Path, Query, HTTPException, Depends
from sqlalchemy import select
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
    # Получаем информацию о задаче из Celery
    task_result = AsyncResult(task_id)

    response_data = {
        "task_id": task_id,
        "task_status": task_result.status,
        "document_id": None,
        "analysis_result": None,
        "error": None
    }

    # Если задача завершена успешно
    if task_result.successful():
        result = task_result.result
        response_data.update({
            "document_id": result.get("document_id"),
            "analysis_result": "completed" if result.get("status") == "success" else "failed",
            "issues_found": None
        })

        # Если нужно, можно добавить информацию о найденных проблемах
        if result.get("status") == "success":
            issues = await db.scalars(
                select(AnalyzedDocIssues).where(AnalyzedDocIssues.document_id == result.get("document_id"))
            )
            response_data["issues_found"] = issues.all()

    # Если задача завершилась с ошибкой
    elif task_result.failed():
        response_data.update({
            "error": str(task_result.result),
            "analysis_result": "failed"
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
    - Был ли документ проанализирован
    - Количество найденных проблем
    - Общую информацию об анализе
    """
    # Проверяем, есть ли записи об анализе этого документа
    exists = await db.scalar(
        select(AnalyzedDocIssues).where(AnalyzedDocIssues.document_id == doc_id).exists().select()
    )

    if not exists:
        return DocumentAnalysisStatusResponse(
            document_id=doc_id,
            analyzed=False,
            issues_count=0,
            status="not_analyzed"
        )

    # Получаем все проблемы для документа
    issues = await db.scalars(
        select(AnalyzedDocIssues).where(AnalyzedDocIssues.document_id == doc_id)
    )
    issues_list = issues.all()

    return DocumentAnalysisStatusResponse(
        document_id=doc_id,
        analyzed=True,
        issues_count=len(issues_list),
        status="completed",
        last_analyzed=issues_list[0].created_at if issues_list else None,
        sample_issues=[issue.issue for issue in issues_list[:3]] if issues_list else []
    )


@router.get('/result', status_code=200)
async def get_result(doc_id: Annotated[int, Query(ge=0)], db: Annotated[AsyncSession, Depends(get_db)]):
    try:
        result = await db.scalars(select(AnalyzedDocIssues).where(AnalyzedDocIssues.document_id == doc_id))
        return result.all()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
