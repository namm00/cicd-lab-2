from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.database import get_db
from app.main import app
from app.models import Quiz


@pytest.fixture
def api():
    # These tests cover HTTP contracts only. PostgreSQL is tested separately.
    db = MagicMock(spec=Session)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        yield client, db
    app.dependency_overrides.clear()


def test_health_checks_database(api):
    client, db = api
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert str(db.execute.call_args.args[0]) == "SELECT 1"


def test_health_returns_503_when_database_is_down(api):
    client, db = api
    db.execute.side_effect = OperationalError("SELECT 1", {}, Exception("unavailable"))
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}


def test_version_comes_from_environment(api, monkeypatch):
    monkeypatch.setenv("APP_VERSION", "abc123")
    client, _ = api
    assert client.get("/api/version").json() == {"version": "abc123"}


def test_create_quiz_http_contract(api):
    client, db = api

    def refresh(quiz):
        quiz.id = 42
        quiz.created_at = datetime(2026, 1, 1, tzinfo=UTC)

    db.refresh.side_effect = refresh
    response = client.post("/api/quizzes", json={"title": "  Docker basics  "})
    assert response.status_code == 201
    assert response.json()["title"] == "Docker basics"
    assert response.json()["id"] == 42
    db.commit.assert_called_once()


def test_get_quiz(api):
    client, db = api
    db.get.return_value = Quiz(
        id=42, title="Docker basics", created_at=datetime.now(UTC), questions=[]
    )
    response = client.get("/api/quizzes/42")
    assert response.status_code == 200
    assert response.json()["questions"] == []


def test_missing_quiz(api):
    client, db = api
    db.get.return_value = None
    assert client.get("/api/quizzes/999").status_code == 404


@pytest.mark.parametrize("payload", [{}, {"title": ""}, {"title": "   "}, {"title": "x" * 201}])
def test_invalid_title(api, payload):
    client, db = api
    assert client.post("/api/quizzes", json=payload).status_code == 422
    db.commit.assert_not_called()


def test_invalid_question(api):
    client, _ = api
    response = client.post("/api/quizzes/1/questions", json={
        "question_text": "Where is the image stored?",
        "option_a": "GHCR", "option_b": "Git", "option_c": "RAM", "option_d": "Browser",
        "correct_answer": "E",
    })
    assert response.status_code == 422
