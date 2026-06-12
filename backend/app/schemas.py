"""Pydantic スキーマ定義。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class TsumeProblemBase(BaseModel):
    title: str
    initial_sfen: str
    mate_length: int = Field(ge=1)
    solution_moves: list[str]
    opponent_moves: list[str] = []
    difficulty: int = 1
    tags: list[str] = []
    explanation: str = ""


class TsumeProblemCreate(TsumeProblemBase):
    pass


class TsumeProblemUpdate(TsumeProblemBase):
    pass


class ProblemStats(BaseModel):
    correct_count: int = 0
    wrong_count: int = 0
    last_answered_at: str | None = None
    avg_elapsed_ms: int | None = None


class TsumeProblem(TsumeProblemBase):
    id: int
    is_favorite: bool = False
    created_at: str
    updated_at: str
    stats: ProblemStats = ProblemStats()


class ProblemResultCreate(BaseModel):
    is_correct: bool
    elapsed_ms: int = Field(ge=0, default=0)
    mistake_count: int = Field(ge=0, default=0)


class ProblemResult(ProblemResultCreate):
    id: int
    problem_id: int
    answered_at: str


class FavoriteUpdate(BaseModel):
    is_favorite: bool


class TimeAttackResultCreate(BaseModel):
    mode: str = "normal"
    mate_length: int
    total_questions: int = Field(ge=1)
    correct_count: int = Field(ge=0)
    mistake_count: int = Field(ge=0)
    elapsed_ms: int = Field(ge=0)


class TimeAttackResult(TimeAttackResultCreate):
    id: int
    played_at: str


class OverallStats(BaseModel):
    total_answers: int
    total_correct: int
    total_wrong: int
    accuracy: float
    avg_elapsed_ms: int | None


class StatsResponse(BaseModel):
    overall: OverallStats
    by_mate_length: dict[str, OverallStats]
    recent_results: list[dict]
