from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class StageStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentType(str, Enum):
    COLLECTOR = "collector"
    DISTILLER = "distiller"
    IMPLEMENTER = "implementer"
    PROTOTYPER = "prototyper"
    BENCHMARKER = "benchmarker"


class PaperSource(str, Enum):
    ARXIV = "arxiv"
    SEMANTIC_SCHOLAR = "semantic_scholar"
    LOCAL = "local"


class Paper(BaseModel):
    id: str
    source: PaperSource
    source_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    abstract: str = ""
    url: str | None = None
    pdf_path: str | None = None
    published_date: str | None = None
    tags: list[str] = Field(default_factory=list)
    embedding_id: str | None = None
    status: str = "new"
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class AgentRun(BaseModel):
    id: str
    paper_id: str
    agent_type: AgentType
    input_data: dict[str, Any] | None = None
    output_data: dict[str, Any] | None = None
    status: StageStatus = StageStatus.PENDING
    started_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class BenchmarkResult(BaseModel):
    id: str
    paper_id: str
    run_id: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    compared_to_baseline: bool = False
    passed_threshold: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class Distillation(BaseModel):
    id: str
    paper_id: str
    run_id: str
    summary: str
    methodology: str
    contributions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    key_equations: list[str] = Field(default_factory=list)
    related_work: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class Implementation(BaseModel):
    id: str
    paper_id: str
    run_id: str
    code: str
    language: str = "python"
    dependencies: list[str] = Field(default_factory=list)
    tests: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
