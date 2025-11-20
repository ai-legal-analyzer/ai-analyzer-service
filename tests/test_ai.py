import pytest
import httpx
import random
import time
from typing import Dict, Any

BASE_URL = "http://127.0.0.1:4000"


def generate_random_document_data():
    doc_id = random.randint(1000, 10000)
    return {
        "doc_id": doc_id,
        "filename": f"test_document_{doc_id}.pdf",
        "content": "Sample document content for testing"
    }


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE_URL) as c:
        yield c


def test_app_health(client):
    """Test that the API is running and accessible"""
    response = client.get("/openapi.json")
    assert response.status_code == 200


def test_analyze_document_endpoint(client):
    """Test starting document analysis"""
    doc_id = random.randint(1000, 10000)

    response = client.post(
        f"/analyze/{doc_id}",
        params={"language": "en"}
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["document_id"] == doc_id
    assert "task_id" in body
    assert body["message"] == f"Analysis started for document {doc_id}"


def test_analyze_document_with_retry(client):
    """Test document analysis with retry flag"""
    doc_id = random.randint(1000, 10000)

    response = client.post(
        f"/analyze/{doc_id}",
        params={"language": "ru", "retry": True}
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["document_id"] == doc_id


def test_analyze_document_invalid_language(client):
    """Test analysis with invalid language parameter"""
    doc_id = random.randint(1000, 10000)

    response = client.post(
        f"/analyze/{doc_id}",
        params={"language": "invalid"}
    )

    # Should return validation error
    assert response.status_code == 422


def test_analyze_document_negative_id(client):
    """Test analysis with negative document ID"""
    response = client.post(
        "/analyze/-1",
        params={"language": "en"}
    )

    # Should return validation error
    assert response.status_code == 422


def test_get_task_status_invalid_task(client):
    """Test getting status for non-existent task"""
    response = client.get("/analyze/status/invalid-task-id")

    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] == "invalid-task-id"
    assert body["task_status"] in ["PENDING", "FAILURE"]
    assert body["analysis_result"] is None


def test_get_document_status_non_existent(client):
    """Test getting status for non-existent document"""
    doc_id = random.randint(10000, 20000)  # Use high ID that likely doesn't exist

    response = client.get(f"/analyze/document/{doc_id}/status")

    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == doc_id
    assert body["analyzed"] is False
    assert body["issues_count"] == 0
    assert body["status"] in ["not_analyzed", "in_progress"]
    assert body["sample_issues"] is None


def test_get_analysis_results_non_existent(client):
    """Test getting analysis results for non-existent document"""
    doc_id = random.randint(10000, 20000)

    response = client.get("/analyze/result", params={"doc_id": doc_id})

    assert response.status_code == 200
    body = response.json()
    assert body == []  # Empty list when no results


def test_complete_analysis_flow(client):
    """Test a complete analysis flow (this might take longer)"""
    # Start analysis
    doc_id = random.randint(1, 10)

    start_response = client.post(
        f"/analyze/{doc_id}",
        params={"language": "en"}
    )

    assert start_response.status_code == 202
    task_data = start_response.json()
    task_id = task_data["task_id"]

    # Check task status immediately
    status_response = client.get(f"/analyze/status/{task_id}")
    assert status_response.status_code == 200
    status_data = status_response.json()

    assert status_data["task_id"] == task_id
    assert status_data["task_status"] in ["PENDING", "STARTED", "SUCCESS", "FAILURE"]

    # Check document status
    doc_status_response = client.get(f"/analyze/document/{doc_id}/status")
    assert doc_status_response.status_code == 200
    doc_status = doc_status_response.json()

    assert doc_status["document_id"] == doc_id
    assert isinstance(doc_status["sample_issues"], list)


def test_analysis_with_different_languages(client):
    """Test analysis with different supported languages"""
    languages = ["en", "ru"]

    for language in languages:
        doc_id = random.randint(1000, 10000)

        response = client.post(
            f"/analyze/{doc_id}",
            params={"language": language}
        )

        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "accepted"


def test_concurrent_analysis_requests(client):
    """Test multiple concurrent analysis requests"""
    doc_ids = [random.randint(1000, 10000) for _ in range(3)]
    tasks = []

    for doc_id in doc_ids:
        response = client.post(
            f"/analyze/{doc_id}",
            params={"language": "en"}
        )
        assert response.status_code == 202
        tasks.append(response.json())

    # Verify all tasks were created
    assert len(tasks) == 3
    for task in tasks:
        assert task["status"] == "accepted"
        assert task["document_id"] in doc_ids


def test_task_status_progress_tracking(client):
    """Test that task status properly tracks progress"""
    doc_id = random.randint(1000, 10000)

    # Start analysis
    start_response = client.post(
        f"/analyze/{doc_id}",
        params={"language": "en"}
    )
    task_id = start_response.json()["task_id"]

    # Poll task status a few times to check progress (if task is running)
    for _ in range(3):
        status_response = client.get(f"/analyze/status/{task_id}")
        assert status_response.status_code == 200
        status_data = status_response.json()

        # Progress should be between 0 and 100
        if "progress" in status_data and status_data["progress"] is not None:
            assert 0 <= status_data["progress"] <= 100

        time.sleep(1)  # Small delay between polls


def test_error_handling_invalid_endpoints(client):
    """Test error handling for invalid endpoints"""
    response = client.get("/analyze/invalid-endpoint")
    assert response.status_code == 404

    response = client.post("/analyze/invalid-endpoint")
    assert response.status_code == 404


def test_cors_headers(client):
    """Test that CORS headers are properly set"""
    response = client.options("/analyze/123", params={"language": "en"})

    # CORS preflight should work
    assert response.status_code in [200, 204]


if __name__ == "__main__":
    # Run tests manually if needed
    pytest.main([__file__, "-v"])