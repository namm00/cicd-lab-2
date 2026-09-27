from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Option = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
QuestionText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]


class QuizCreate(BaseModel):
    title: Title


class QuizRead(QuizCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


class QuestionCreate(BaseModel):
    question_text: QuestionText
    option_a: Option
    option_b: Option
    option_c: Option
    option_d: Option
    correct_answer: Literal["A", "B", "C", "D"]


class QuestionRead(QuestionCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    quiz_id: int


class QuizDetail(QuizRead):
    questions: list[QuestionRead]
