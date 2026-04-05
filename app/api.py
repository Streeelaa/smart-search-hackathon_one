from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.evaluation_compare import compare_search_modes
from app.evaluation_v2 import evaluate_search
from app.ingestion import import_catalog, import_events
from app.repository import repository
from app.reranker import reranker
from app.schemas import EvaluationComparisonResponse, EvaluationSummary, Event, EventCreate, HealthResponse, ImportRequest, ImportResult, Product, RerankerStatusResponse, SearchMode, SearchResponse, SemanticStatusResponse, StorageStatusResponse, UserProfile
from app.semantic import semantic_engine
from app.settings import settings
from app.search import search_products, warm_up
from app.synonyms import get_synonym_map


app = FastAPI(
    title="Smart Search Hackathon API",
    description="Персонализированный умный поиск продукции для портала закупок zakupki.mos.ru",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_warm_up():
    """Pre-build vocabulary for typo correction and semantic index on startup."""
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _startup_init)


def _startup_init():
    """Initialize vocabulary + semantic index in background thread."""
    warm_up()
    try:
        semantic_engine.build_index()
    except Exception:
        pass


@app.get("/")
def root() -> dict[str, str | list[str]]:
    return {
        "message": "Smart Search MVP is running",
        "docs": "/docs",
        "endpoints": [
            "/health",
            "/catalog/items",
            "/search?q=ноутбук&user_id=user-1&mode=hybrid",
            "/search/synonyms",
            "/search/semantic/status",
            "/search/reranker/status",
            "/storage/status",
            "/admin/import/catalog",
            "/admin/import/events",
            "/events",
            "/users/user-1/profile",
            "/metrics/compare",
        ],
    }


@app.get("/health", response_model=HealthResponse)
def healthcheck() -> HealthResponse:
    return HealthResponse(
        status="ok",
        catalog_size=repository.count_products(),
        events_count=repository.count_events(),
        profiles_count=repository.count_profiles(),
        storage_backend=repository.backend_name(),
    )


@app.get("/storage/status", response_model=StorageStatusResponse)
def storage_status() -> StorageStatusResponse:
    return StorageStatusResponse(
        backend=repository.backend_name(),
        database_url=settings.database_url,
        seed_demo_data=settings.seed_demo_data,
    )


@app.get("/catalog/items", response_model=list[Product])
def list_items(
    category: str | None = Query(default=None, description="Filter catalog by category."),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[Product]:
    return repository.list_products(category=category)[:limit]


@app.get("/catalog/items/{item_id}", response_model=Product)
def get_item(item_id: int) -> Product:
    product = repository.get_product(item_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return product


@app.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(min_length=2, description="Search query."),
    limit: int = Query(default=10, ge=1, le=50),
    mode: SearchMode = Query(default="hybrid", description="keyword, semantic or hybrid mode."),
    user_id: str | None = Query(default=None, description="Optional user id for personalized ranking."),
    category: str | None = Query(default=None, description="Filter by category name."),
) -> SearchResponse:
    return search_products(query=q, limit=limit, user_id=user_id, mode=mode, category_filter=category)


@app.get("/catalog/categories")
def list_categories(
    q: str | None = Query(default=None, description="Filter categories by substring."),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict]:
    """List categories with product counts. Optionally filter by substring."""
    if q:
        cats = repository.search_categories(q, limit=limit)
    else:
        cats = repository.get_all_categories(limit=limit)
    return [{"category": c, "count": n} for c, n in cats]


@app.get("/search/suggest")
def search_suggest(
    q: str = Query(min_length=1, description="Partial query for suggestions."),
    limit: int = Query(default=5, ge=1, le=20),
) -> list[dict]:
    """Return search suggestions based on category matches."""
    cats = repository.search_categories(q, limit=limit)
    return [{"suggestion": c, "type": "category", "count": n} for c, n in cats]


@app.get("/search/synonyms", response_model=dict[str, list[str]])
def search_synonyms() -> dict[str, list[str]]:
    return get_synonym_map()


@app.get("/search/semantic/status", response_model=SemanticStatusResponse)
def search_semantic_status() -> SemanticStatusResponse:
    status = semantic_engine.status()
    return SemanticStatusResponse(
        ready=status.ready,
        backend=status.backend,
        model_name=status.model_name,
        indexed_products=status.indexed_products,
        last_error=status.last_error,
    )


@app.get("/search/reranker/status", response_model=RerankerStatusResponse)
def search_reranker_status() -> RerankerStatusResponse:
    status = reranker.status()
    return RerankerStatusResponse(
        ready=status.ready,
        backend=status.backend,
        model_name=status.model_name,
        last_error=status.last_error,
    )


@app.post("/admin/import/catalog", response_model=ImportResult)
def admin_import_catalog(payload: ImportRequest) -> ImportResult:
    products, result = import_catalog(path=payload.path, replace_existing=payload.replace_existing)
    if not products:
        raise HTTPException(status_code=400, detail="No valid catalog rows were imported")

    if payload.replace_existing:
        repository.replace_products(products)
    else:
        merged = repository.products + products
        repository.replace_products(merged)

    semantic_engine.reset()
    return result


@app.post("/admin/import/events", response_model=ImportResult)
def admin_import_events(payload: ImportRequest) -> ImportResult:
    events, result = import_events(path=payload.path, replace_existing=payload.replace_existing)
    if not events:
        raise HTTPException(status_code=400, detail="No valid event rows were imported")

    if payload.replace_existing:
        repository.replace_events(events)
    else:
        repository.append_events(events)

    return result


@app.post("/events", response_model=Event)
def create_event(payload: EventCreate) -> Event:
    if payload.item_id is not None and repository.get_product(payload.item_id) is None:
        raise HTTPException(status_code=404, detail="Item not found for event")
    return repository.add_event(payload)


@app.get("/users/{user_id}/profile", response_model=UserProfile)
def get_user_profile(user_id: str) -> UserProfile:
    return repository.get_user_profile(user_id)


@app.get("/users/{user_id}/events", response_model=list[Event])
def get_user_events(user_id: str) -> list[Event]:
    return repository.list_user_events(user_id)


@app.get("/metrics/evaluate", response_model=EvaluationSummary)
def metrics_evaluate(
    mode: SearchMode = Query(default="hybrid", description="keyword, semantic or hybrid mode."),
) -> EvaluationSummary:
    return evaluate_search(mode=mode)


@app.get("/metrics/compare", response_model=EvaluationComparisonResponse)
def metrics_compare() -> EvaluationComparisonResponse:
    return compare_search_modes()
