from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.evaluation_compare import compare_search_modes
from app.evaluation_v2 import evaluate_search
from app.ingestion import import_catalog, import_events
from app.repository import repository
from app.reranker import reranker
from app.schemas import CatalogItem, CatalogStats, CategorySummary, EvaluationComparisonResponse, EvaluationSummary, Event, EventCreate, HealthResponse, ImportRequest, ImportResult, PortalOverview, Product, ProductInsights, RerankerStatusResponse, SearchMode, SearchResponse, SearchSessionSummary, SearchSuggestion, SemanticStatusResponse, StorageStatusResponse, UserAccount, UserAccountUpdate, UserDashboard, UserLoginRequest, UserProductRecord, UserProfile, UserSummary
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
    """Warm the typo vocabulary before first search; keep semantic init in background."""
    import asyncio
    await asyncio.to_thread(warm_up)
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _startup_semantic_init)


def _startup_semantic_init():
    """Initialize semantic index in background thread."""
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
            "/portal/overview",
            "/catalog/items",
            "/search?q=ноутбук&user_id=user-1&mode=hybrid",
            "/search/synonyms",
            "/search/semantic/status",
            "/search/reranker/status",
            "/storage/status",
            "/admin/import/catalog",
            "/admin/import/events",
            "/events",
            "/users",
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


def _catalog_stats() -> CatalogStats:
    return CatalogStats(
        products_count=repository.count_products(),
        profiles_count=repository.count_profiles(),
        categories_count=repository.count_categories(),
        events_count=repository.count_events(),
    )


def _user_summary_rows(rows: list[dict]) -> list[UserSummary]:
    return [UserSummary(**row) for row in rows]


@app.get("/portal/overview", response_model=PortalOverview)
def portal_overview(
    limit_categories: int = Query(default=8, ge=1, le=24),
    limit_users: int = Query(default=6, ge=1, le=24),
) -> PortalOverview:
    return PortalOverview(
        stats=_catalog_stats(),
        featured_categories=[
            CategorySummary(category=category, count=count)
            for category, count in repository.get_all_categories(limit=limit_categories)
        ],
        featured_users=_user_summary_rows(repository.list_users(limit=limit_users)),
    )


@app.get("/storage/status", response_model=StorageStatusResponse)
def storage_status() -> StorageStatusResponse:
    return StorageStatusResponse(
        backend=repository.backend_name(),
        database_url=settings.database_url,
        seed_demo_data=settings.seed_demo_data,
    )


@app.get("/catalog/items", response_model=list[CatalogItem])
def list_items(
    category: str | None = Query(default=None, description="Filter catalog by category."),
    q: str | None = Query(default=None, description="Filter catalog by title substring."),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10_000),
) -> list[CatalogItem]:
    products = repository.list_products(category=category, query=q, limit=limit, offset=offset)
    product_ids = [product.id for product in products]
    popularity = repository.get_products_popularity(product_ids)
    prices = repository.get_products_prices(product_ids)
    return [
        CatalogItem(
            product=product,
            insights=ProductInsights(
                product_id=product.id,
                contracts_count=popularity.get(product.id, 0),
                average_price=prices.get(product.id),
            ),
        )
        for product in products
    ]


@app.get("/catalog/items/{item_id}", response_model=Product)
def get_item(item_id: int) -> Product:
    product = repository.get_product(item_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return product


@app.get("/catalog/items/{item_id}/insights", response_model=ProductInsights)
def get_item_insights(item_id: int) -> ProductInsights:
    product = repository.get_product(item_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return ProductInsights(
        product_id=item_id,
        contracts_count=repository.get_product_contract_count(item_id),
        average_price=repository.get_product_avg_price(item_id),
    )


@app.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(min_length=2, description="Search query."),
    limit: int = Query(default=10, ge=1, le=50),
    mode: SearchMode = Query(default="hybrid", description="keyword, semantic or hybrid mode."),
    user_id: str | None = Query(default=None, description="Optional user id for personalized ranking."),
    category: str | None = Query(default=None, description="Filter by category name."),
) -> SearchResponse:
    return search_products(query=q, limit=limit, user_id=user_id, mode=mode, category_filter=category)


@app.get("/catalog/categories", response_model=list[CategorySummary])
def list_categories(
    q: str | None = Query(default=None, description="Filter categories by substring."),
    user_id: str | None = Query(default=None, description="Optional user id to prioritize customer-relevant categories."),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[CategorySummary]:
    """List categories with product counts. Optionally filter by substring."""
    if q:
        cats = repository.search_categories(q, limit=limit, user_id=user_id)
    else:
        cats = repository.get_all_categories(limit=limit, user_id=user_id)
    return [CategorySummary(category=c, count=n) for c, n in cats]


@app.get("/search/suggest", response_model=list[SearchSuggestion])
def search_suggest(
    q: str = Query(min_length=1, description="Partial query for suggestions."),
    limit: int = Query(default=8, ge=1, le=20),
) -> list[SearchSuggestion]:
    """Return search suggestions for categories and product titles."""
    return [SearchSuggestion(**item) for item in repository.suggest_products(q, limit=limit)]


@app.get("/search/disambiguate", response_model=list[CategorySummary])
def search_disambiguate(
    q: str = Query(min_length=2, description="Query that needs category guidance."),
    user_id: str | None = Query(default=None, description="Optional user id to prioritize customer-relevant categories."),
    limit: int = Query(default=6, ge=1, le=12),
) -> list[CategorySummary]:
    return [
        CategorySummary(category=category, count=count)
        for category, count in repository.disambiguate_categories(q, limit=limit, user_id=user_id)
    ]


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


@app.post("/auth/login", response_model=UserAccount)
def auth_login(payload: UserLoginRequest) -> UserAccount:
    try:
        return repository.login_user(payload.user_id, role=payload.role)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/users", response_model=list[UserSummary])
def list_users(
    q: str | None = Query(default=None, description="Filter organizations by id, name or region."),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[UserSummary]:
    rows = repository.search_users(q, limit=limit) if q else repository.list_users(limit=limit)
    return _user_summary_rows(rows)


@app.get("/users/{user_id}/profile", response_model=UserProfile)
def get_user_profile(user_id: str) -> UserProfile:
    return repository.get_user_profile(user_id)


@app.get("/users/{user_id}/account", response_model=UserAccount)
def get_user_account(user_id: str) -> UserAccount:
    try:
        account = repository.get_user_account(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if account is None:
        raise HTTPException(status_code=404, detail="User account not found")
    return account


@app.put("/users/{user_id}/account", response_model=UserAccount)
def update_user_account(user_id: str, payload: UserAccountUpdate) -> UserAccount:
    try:
        return repository.update_user_account(user_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/users/{user_id}/events", response_model=list[Event])
def get_user_events(user_id: str) -> list[Event]:
    return repository.list_user_events(user_id)


@app.get("/users/{user_id}/favorites", response_model=list[UserProductRecord])
def get_user_favorites(
    user_id: str,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[UserProductRecord]:
    try:
        return repository.list_user_favorites(user_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/users/{user_id}/favorites/{item_id}", response_model=UserProductRecord)
def add_user_favorite(user_id: str, item_id: int) -> UserProductRecord:
    if repository.get_product(item_id) is None:
        raise HTTPException(status_code=404, detail="Item not found")
    try:
        return repository.add_favorite(user_id, item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/users/{user_id}/favorites/{item_id}")
def remove_user_favorite(user_id: str, item_id: int) -> dict[str, bool]:
    repository.remove_favorite(user_id, item_id)
    return {"ok": True}


@app.get("/users/{user_id}/history", response_model=list[UserProductRecord])
def get_user_history(
    user_id: str,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[UserProductRecord]:
    return repository.list_view_history(user_id, limit=limit)


@app.get("/users/{user_id}/search-sessions", response_model=list[SearchSessionSummary])
def get_user_search_sessions(
    user_id: str,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[SearchSessionSummary]:
    return repository.list_search_sessions(user_id, limit=limit)


@app.get("/users/{user_id}/dashboard", response_model=UserDashboard)
def get_user_dashboard(
    user_id: str,
    favorites_limit: int = Query(default=8, ge=1, le=24),
    history_limit: int = Query(default=8, ge=1, le=24),
    sessions_limit: int = Query(default=8, ge=1, le=24),
    products_limit: int = Query(default=8, ge=1, le=24),
    categories_limit: int = Query(default=6, ge=1, le=12),
) -> UserDashboard:
    try:
        return repository.get_user_dashboard(
            user_id,
            favorites_limit=favorites_limit,
            history_limit=history_limit,
            sessions_limit=sessions_limit,
            products_limit=products_limit,
            categories_limit=categories_limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/metrics/evaluate", response_model=EvaluationSummary)
def metrics_evaluate(
    mode: SearchMode = Query(default="hybrid", description="keyword, semantic or hybrid mode."),
) -> EvaluationSummary:
    return evaluate_search(mode=mode)


@app.get("/metrics/compare", response_model=EvaluationComparisonResponse)
def metrics_compare() -> EvaluationComparisonResponse:
    return compare_search_modes()
