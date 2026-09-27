import logging
import os
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Question, Quiz
from app.schemas import QuestionCreate, QuestionRead, QuizCreate, QuizDetail, QuizRead

app = FastAPI(title="CI/CD Lab 2 — Mini Quiz")
logger = logging.getLogger(__name__)
DB = Annotated[Session, Depends(get_db)]


@app.get("/api/health")
def health(db: DB) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        # Do not log a connection URL or credentials.
        logger.warning("Database health check failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ok"}


@app.get("/api/version")
def version() -> dict[str, str]:
    return {"version": os.getenv("APP_VERSION", "local")}


@app.get("/api/quizzes", response_model=list[QuizRead])
def list_quizzes(db: DB):
    return db.scalars(select(Quiz).order_by(Quiz.id.desc())).all()


@app.post("/api/quizzes", response_model=QuizRead, status_code=201)
def create_quiz(payload: QuizCreate, db: DB):
    quiz = Quiz(title=payload.title)
    db.add(quiz)
    db.commit()
    db.refresh(quiz)
    return quiz


@app.get("/api/quizzes/{quiz_id}", response_model=QuizDetail)
def get_quiz(quiz_id: int, db: DB):
    quiz = db.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    return quiz


@app.post("/api/quizzes/{quiz_id}/questions", response_model=QuestionRead, status_code=201)
def add_question(quiz_id: int, payload: QuestionCreate, db: DB):
    if db.get(Quiz, quiz_id) is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    question = Question(quiz_id=quiz_id, **payload.model_dump())
    db.add(question)
    db.commit()
    db.refresh(question)
    return question
