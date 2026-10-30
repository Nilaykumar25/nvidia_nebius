from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field


class FileChange(BaseModel):
    path: str
    old_path: Optional[str] = None
    change_type: str = "MODIFY"
    diff: str = ""


class CommitRecord(BaseModel):
    sha: str
    author: str
    email: str
    date: str
    message: str
    files: list[FileChange] = Field(default_factory=list)


class Comment(BaseModel):
    id: str
    author: str = ""
    created_at: str = ""
    url: str = ""
    body: str = ""


class Thread(BaseModel):
    """A PR, issue or commit treated as a discussion unit for decision mining."""
    id: str                      # "pr:123", "issue:45", "commit:<sha>", "doc:<path>#L<n>"
    kind: Literal["pr", "issue", "commit", "document"]
    number: Optional[int] = None
    title: str = ""
    body: str = ""
    url: str = ""
    author: str = ""
    created_at: str = ""
    merged_at: Optional[str] = None
    comments: list[Comment] = Field(default_factory=list)
    commit_shas: list[str] = Field(default_factory=list)
    closes: list[int] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)


class Span(BaseModel):
    source_id: str
    quote: str


class ExtractedDecision(BaseModel):
    title: str
    summary: str
    rationale: str = ""
    alternatives_rejected: list[str] = Field(default_factory=list)
    decided_by: list[str] = Field(default_factory=list)
    decided_on: Optional[str] = None
    explicit_rationale: bool = False
    governs: list[str] = Field(default_factory=list)   # entity hints: config keys, functions, files
    spans: list[Span] = Field(default_factory=list)
    agreement: float = 0.0
    thread_id: str = ""


class Factors(BaseModel):
    directness: float
    corroboration: float
    agreement: float
    currency: float
    distance: float


class Confidence(BaseModel):
    score: float
    label: Literal["High", "Medium", "Low", "No answer"]
    factors: Optional[Factors] = None
    reasons: list[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    ref: str                     # E1, E2...
    id: str
    kind: str                    # Commit | PullRequest | Issue | Comment | Document
    url: str = ""
    date: str = ""
    author: str = ""
    snippet: str = ""
    quote: str = ""


class AnswerResponse(BaseModel):
    question: str
    status: Literal["answered", "refused"]
    answer: str = ""
    decision: Optional[dict] = None
    superseded_notice: Optional[str] = None
    replaced_by: Optional[dict] = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
    person_to_ask: Optional[dict] = None
    history: list[dict] = Field(default_factory=list)
    confidence: Confidence
    refusal_reason: Optional[str] = None
    related: list[dict] = Field(default_factory=list)
    graph: dict = Field(default_factory=lambda: {"nodes": [], "rels": []})
    latency_ms: int = 0
    llm_model: str = ""
