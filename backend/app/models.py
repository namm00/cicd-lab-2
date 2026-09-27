from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    questions: Mapped[list["Question"]] = relationship(
        back_populates="quiz", cascade="all, delete-orphan", passive_deletes=True,
        order_by="Question.id",
    )


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        CheckConstraint("correct_answer IN ('A', 'B', 'C', 'D')", name="ck_correct_answer"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), index=True)
    question_text: Mapped[str] = mapped_column(Text)
    option_a: Mapped[str] = mapped_column(String(500))
    option_b: Mapped[str] = mapped_column(String(500))
    option_c: Mapped[str] = mapped_column(String(500))
    option_d: Mapped[str] = mapped_column(String(500))
    correct_answer: Mapped[str] = mapped_column(String(1))
    quiz: Mapped[Quiz] = relationship(back_populates="questions")
