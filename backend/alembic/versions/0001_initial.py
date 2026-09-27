"""Create quizzes and questions."""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quizzes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("quiz_id", sa.Integer(), sa.ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("option_a", sa.String(500), nullable=False),
        sa.Column("option_b", sa.String(500), nullable=False),
        sa.Column("option_c", sa.String(500), nullable=False),
        sa.Column("option_d", sa.String(500), nullable=False),
        sa.Column("correct_answer", sa.String(1), nullable=False),
        sa.CheckConstraint("correct_answer IN ('A', 'B', 'C', 'D')", name="ck_correct_answer"),
    )
    op.create_index("ix_questions_quiz_id", "questions", ["quiz_id"])


def downgrade() -> None:
    op.drop_index("ix_questions_quiz_id", table_name="questions")
    op.drop_table("questions")
    op.drop_table("quizzes")
