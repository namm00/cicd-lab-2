"""Run inside the backend image; HTTP goes through the frontend proxy.

Cleanup uses SQLAlchemy so the public app does not need a delete endpoint.
The unique title also allows cleanup if a POST commits but its response is lost.
"""
import json
import sys
from urllib.request import Request, urlopen
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database import get_engine
from app.models import Quiz


def run(frontend_url: str, expected_version: str) -> None:
    title = f"__smoke__{uuid4().hex}"

    def request(path: str, payload: dict | None = None, status: int = 200):
        body = json.dumps(payload).encode() if payload is not None else None
        req = Request(frontend_url + path, data=body, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=10) as response:
            assert response.status == status, f"Unexpected status for {path}"
            return json.load(response)

    try:
        with urlopen(frontend_url + "/", timeout=10) as response:
            assert response.status == 200
            assert '<div id="root">' in response.read().decode()
        assert request("/api/health") == {"status": "ok"}
        assert request("/api/version") == {"version": expected_version}
        quiz = request("/api/quizzes", {"title": title}, status=201)
        quiz_id = quiz["id"]
        request(f"/api/quizzes/{quiz_id}/questions", {
            "question_text": "Smoke: where are images stored?",
            "option_a": "GHCR", "option_b": "Git", "option_c": "Browser", "option_d": "RAM",
            "correct_answer": "A",
        }, status=201)
        saved = request(f"/api/quizzes/{quiz_id}")
        assert saved["title"] == title
        assert saved["questions"][0]["correct_answer"] == "A"
        print(f"Smoke HTTP passed: frontend → backend → PostgreSQL; version={expected_version}")
    finally:
        with Session(get_engine()) as db:
            db.execute(delete(Quiz).where(Quiz.title == title))
            db.commit()
            assert db.scalar(select(Quiz.id).where(Quiz.title == title)) is None
        print(f"Smoke cleanup complete: {title}")


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2])
