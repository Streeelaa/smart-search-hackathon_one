from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


EventType = Literal["search", "click", "favorite", "purchase", "bounce"]
SearchMode = Literal["keyword", "semantic", "hybrid"]


class Product(BaseModel):
    id: int  # ID СТЕ
    title: str  # Наименование
    category: str  # Категория
    attributes: dict[str, str] = Field(default_factory=dict)  # Атрибуты (key:value)
    # Legacy fields kept for backward compat but optional
    sku: str = ""
    description: str = ""
    price: float = Field(default=0, ge=0)
    tags: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)


class CategoryFacet(BaseModel):
    category: str
    count: int
    icon: str = "📦"


class SearchResult(BaseModel):
    product: Product
    score: float
    reasons: list[str] = Field(default_factory=list)
    highlight_title: str = ""  # Title with <mark> tags around matched terms


class SearchResponse(BaseModel):
    query: str
    corrected_query: str
    typo_corrected: bool = False
    expanded_terms: list[str]
    total: int
    personalized: bool
    mode: SearchMode
    semantic_backend: str | None = None
    reranker_backend: str | None = None
    search_time_ms: float = 0.0
    facets: list[CategoryFacet] = Field(default_factory=list)
    items: list[SearchResult]


class EventCreate(BaseModel):
    user_id: str = Field(min_length=1)
    event_type: EventType
    item_id: int | None = None
    query: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class Event(EventCreate):
    event_id: int
    timestamp: datetime


class UserProfile(BaseModel):
    user_id: str
    total_events: int = 0
    category_affinity: dict[str, float] = Field(default_factory=dict)
    tag_affinity: dict[str, float] = Field(default_factory=dict)
    recent_queries: list[str] = Field(default_factory=list)
    average_price: float | None = None


class HealthResponse(BaseModel):
    status: str
    catalog_size: int
    events_count: int
    profiles_count: int
    storage_backend: str


class SemanticStatusResponse(BaseModel):
    ready: bool
    backend: str
    model_name: str
    indexed_products: int
    last_error: str | None = None


class RerankerStatusResponse(BaseModel):
    ready: bool
    backend: str
    model_name: str
    last_error: str | None = None


class ImportRequest(BaseModel):
    path: str = Field(min_length=1)
    replace_existing: bool = True


class ImportResult(BaseModel):
    kind: Literal["catalog", "events"]
    path: str
    imported_count: int
    skipped_count: int = 0
    replace_existing: bool = True
    errors: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class StorageStatusResponse(BaseModel):
    backend: str
    database_url: str
    seed_demo_data: bool


class EvaluationCaseResult(BaseModel):
    query: str
    user_id: str | None = None
    mode: SearchMode = "hybrid"
    expected_ids: list[int]
    expected_categories: list[str] = Field(default_factory=list)
    returned_ids: list[int]
    hit_at_3: bool
    mrr_at_10: float
    ndcg_at_10: float
    case_source: str = "manual"
    case_weight: float = 1.0
    notes: str | None = None


class EvaluationSummary(BaseModel):
    cases_count: int
    mode: SearchMode = "hybrid"
    hit_rate_at_3: float
    mrr_at_10: float
    ndcg_at_10: float
    precision_at_3: float
    recall_at_10: float
    cases: list[EvaluationCaseResult]


class EvaluationComparisonRow(BaseModel):
    mode: SearchMode
    hit_rate_at_3: float
    mrr_at_10: float
    ndcg_at_10: float
    precision_at_3: float
    recall_at_10: float


class EvaluationComparisonResponse(BaseModel):
    rows: list[EvaluationComparisonRow]
    best_mode_by_ndcg: SearchMode
