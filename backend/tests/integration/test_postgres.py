import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError

from app.models import Question, Quiz

pytestmark = pytest.mark.integration

QUESTION = {
    "question_text": "Which tool applies schema changes?",
    "option_a": "Alembic", "option_b": "Vite", "option_c": "React", "option_d": "curl",
    "correct_answer": "A",
}


def test_real_postgres_and_migration_head(db):
    assert "PostgreSQL" in db.scalar(text("SELECT version()"))
    expected = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
    assert db.scalar(text("SELECT version_num FROM alembic_version")) == expected


def test_health_with_real_database(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_insert_select_and_question(client, db):
    response = client.post("/api/quizzes", json={"title": "PostgreSQL integration"})
    assert response.status_code == 201
    quiz_id = response.json()["id"]
    # Expire ORM state so verification reads PostgreSQL again.
    db.expire_all()
    assert db.scalar(select(Quiz.title).where(Quiz.id == quiz_id)) == "PostgreSQL integration"
    question = client.post(f"/api/quizzes/{quiz_id}/questions", json=QUESTION)
    assert question.status_code == 201
    result = client.get(f"/api/quizzes/{quiz_id}")
    assert result.status_code == 200
    assert result.json()["questions"][0]["correct_answer"] == "A"
    assert any(quiz["id"] == quiz_id for quiz in client.get("/api/quizzes").json())


def test_database_cascades_question_deletion(client, db):
    quiz_id = client.post("/api/quizzes", json={"title": "Cascade"}).json()["id"]
    response = client.post(f"/api/quizzes/{quiz_id}/questions", json=QUESTION)
    assert response.status_code == 201
    db.execute(delete(Quiz).where(Quiz.id == quiz_id))
    db.commit()
    assert db.scalar(select(Question.id).where(Question.quiz_id == quiz_id)) is None


def test_database_rejects_orphan_question(db):
    db.add(Question(quiz_id=-1, **QUESTION))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_missing_quiz_and_invalid_title(client):
    assert client.get("/api/quizzes/999999999").status_code == 404
    assert client.post("/api/quizzes", json={"title": " "}).status_code == 422
    assert client.post("/api/quizzes/999999999/questions", json=QUESTION).status_code == 404
