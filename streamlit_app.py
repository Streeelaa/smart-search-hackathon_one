import pandas as pd
import streamlit as st
import html as html_module

from app.demo_scenarios import get_demo_scenario, get_demo_scenarios
from app.evaluation_compare import compare_search_modes
from app.evaluation_v2 import evaluate_search
from app.ingestion import import_catalog, import_events
from app.repository import repository
from app.reranker import reranker
from app.schemas import EventCreate, SearchResponse
from app.search import search_products
from app.semantic import semantic_engine
from app.settings import settings
from app.synonyms import get_synonym_map

# Warm up everything once per Streamlit session
if "_warmup_done" not in st.session_state:
    import threading
    from app.search import warm_up as _warm_up_vocab
    # 1. Build semantic index from cache (fast, no model load)
    try:
        semantic_engine.build_index()
    except Exception:
        pass
    # 2. Load sentence-transformer model in background thread
    _model_thread = threading.Thread(target=semantic_engine._load_model, daemon=True)
    _model_thread.start()
    # 3. Build vocabulary (runs in parallel with model loading)
    _warm_up_vocab()
    # 4. Create category index if missing
    try:
        from app.data_loader import get_db_connection
        _conn = get_db_connection()
        _conn.execute("CREATE INDEX IF NOT EXISTS idx_products_category ON products(category)")
        _conn.close()
    except Exception:
        pass
    # 5. Wait for model to finish loading
    _model_thread.join()
    st.session_state["_warmup_done"] = True


st.set_page_config(
    page_title="Умный поиск — zakupki.mos.ru",
    page_icon="�",
    layout="wide",
    initial_sidebar_state="expanded",
)

CATEGORY_ICONS: dict[str, str] = {
    "ноутбук": "💻", "принтер": "🖨️", "мебель": "🪑", "кресл": "🪑",
    "стол": "🪑", "бумаг": "📄", "канцеляр": "📎", "сервер": "🖥️",
    "проектор": "📽️", "телефон": "📞", "освещен": "💡", "лампа": "💡",
    "светильник": "💡", "хозяйств": "🧹", "безопасност": "🔒",
    "спецодежд": "👷", "одежда": "👕", "халат": "👕", "костюм": "👕",
    "электр": "⚡", "кабель": "⚡", "провод": "⚡",
    "монитор": "🖥️", "мышь": "🖱️", "клавиатур": "⌨️",
    "фильтр": "🔧", "насос": "🔧", "запасн": "🔧",
    "лекарств": "💊", "препарат": "💊", "шприц": "💉",
    "иммунодепресс": "💊", "противоопухол": "💊",
    "перчатк": "🧤", "маска": "😷", "обувь": "👟",
    "учебник": "📚", "тетрадь": "📓", "литератур": "📚",
    "краск": "🎨", "мяч": "⚽", "спорт": "🏃",
    "труб": "🔩", "замок": "🔒", "камер": "📷",
    "масло": "🛢️", "игрушк": "🧸", "питан": "🔌",
}

# Real users from contract data
USER_ROLE_LABELS: dict[str, str] = {
    "7714338609": "🏥 Аптечный склад ДЗМ (фарма)",
    "9701059930": "🚗 Автохозяйство (запчасти)",
    "5051005670": "🏫 Школа (образование)",
    "7701885820": "🏗️ Мосинжпроект (стройка)",
    "9718062105": "🚜 Мосотделстрой (техника)",
}



def inject_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

        html, body, [class*="css"] {
            font-family: 'IBM Plex Sans', sans-serif;
        }

        .stApp {
            background:
                radial-gradient(circle at top left, rgba(226, 234, 239, 0.85), transparent 28%),
                radial-gradient(circle at top right, rgba(240, 232, 223, 0.88), transparent 24%),
                linear-gradient(180deg, #f4f1eb 0%, #edf1f2 52%, #f6f5f2 100%);
            color: #24323d;
        }

        h1, h2, h3 {
            font-family: 'Space Grotesk', sans-serif;
            letter-spacing: -0.02em;
            color: #1f2a33;
        }

        .hero-card, .result-card {
            border: 1px solid rgba(36, 50, 61, 0.08);
            border-radius: 20px;
            background: rgba(255, 255, 255, 0.82);
            backdrop-filter: blur(8px);
            box-shadow: 0 12px 28px rgba(49, 61, 71, 0.08);
            padding: 1rem 1.2rem;
        }

        .hero-card {
            padding: 1.4rem;
            margin-bottom: 1rem;
        }

        .muted-note {
            color: #5f6d77;
            font-size: 0.95rem;
        }

        .reason-pill {
            display: inline-block;
            margin: 0.15rem 0.35rem 0.15rem 0;
            padding: 0.28rem 0.58rem;
            border-radius: 999px;
            background: #e4ebea;
            color: #31454f;
            font-size: 0.82rem;
        }

        .stButton > button {
            border-radius: 999px;
            border: 1px solid rgba(61, 87, 82, 0.16);
            background: linear-gradient(135deg, #6f8d86 0%, #88a39a 100%) !important;
            color: #fbfdfc !important;
            font-weight: 600;
            box-shadow: 0 8px 18px rgba(76, 99, 94, 0.14);
            transition: transform 0.12s ease, box-shadow 0.12s ease, background 0.12s ease;
        }

        .stButton > button:hover {
            background: linear-gradient(135deg, #65827b 0%, #7f988f 100%) !important;
            color: #ffffff !important;
            border-color: rgba(61, 87, 82, 0.22);
            transform: translateY(-1px);
            box-shadow: 0 12px 24px rgba(76, 99, 94, 0.18);
        }

        .stButton > button:focus,
        .stButton > button:focus-visible {
            color: #ffffff !important;
            border-color: #7f988f;
            box-shadow: 0 0 0 0.2rem rgba(127, 152, 143, 0.18);
            outline: none;
        }

        .stButton > button p {
            color: inherit !important;
        }

        .stFormSubmitButton > button {
            background: linear-gradient(135deg, #6b857d 0%, #829a91 100%) !important;
            color: #ffffff !important;
            border: 1px solid rgba(61, 87, 82, 0.18) !important;
        }

        .stFormSubmitButton > button:hover,
        .stFormSubmitButton > button:focus,
        .stFormSubmitButton > button:focus-visible {
            background: linear-gradient(135deg, #607970 0%, #789087 100%) !important;
            color: #ffffff !important;
        }

        .stTextInput input,
        .stNumberInput input,
        .stSelectbox [data-baseweb="select"] > div,
        .stMultiSelect [data-baseweb="select"] > div {
            background: rgba(255, 255, 255, 0.86);
            border: 1px solid rgba(62, 79, 90, 0.14);
            color: #24323d;
            border-radius: 14px;
        }

        .stNumberInput button {
            background: rgba(255, 255, 255, 0.86) !important;
            border: 1px solid rgba(62, 79, 90, 0.14) !important;
            color: #24323d !important;
        }

        .stSlider [data-baseweb="slider"] {
            padding-top: 0.45rem;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 0.4rem;
        }

        .stTabs [data-baseweb="tab"] {
            color: #5f6d77;
        }

        .stMarkdown,
        .stMarkdown p,
        .stCaption,
        .stText,
        [data-testid="stMetricLabel"],
        [data-testid="stMetricLabel"] p,
        [data-testid="stMetricValue"],
        [data-testid="stMetricValue"] div,
        [data-testid="stCheckbox"] label,
        [data-testid="stCheckbox"] label span,
        [data-testid="stWidgetLabel"],
        [data-testid="stWidgetLabel"] p,
        .stTextInput label,
        .stTextInput label p,
        .stSelectbox label,
        .stSelectbox label p,
        .stSlider label,
        .stSlider label p {
            color: #24323d !important;
        }

        .pipeline-step {
            display: inline-flex; align-items: center; gap: 0.3rem;
            margin: 0.15rem 0.2rem; padding: 0.35rem 0.7rem;
            border-radius: 12px; font-size: 0.85rem; font-weight: 500;
        }
        .pipeline-step.active { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .pipeline-step.inactive { background: #f0f0f0; color: #999; border: 1px solid #e0e0e0; }
        .pipeline-arrow { display: inline-block; color: #aaa; margin: 0 0.1rem; font-size: 0.9rem; }

        .product-card {
            border: 1px solid rgba(36, 50, 61, 0.08); border-radius: 16px;
            background: rgba(255, 255, 255, 0.88); backdrop-filter: blur(8px);
            box-shadow: 0 6px 18px rgba(49, 61, 71, 0.06);
            padding: 1rem 1.2rem; margin-bottom: 0.8rem;
        }
        .product-card:hover { box-shadow: 0 10px 28px rgba(49, 61, 71, 0.12); }
        .product-card .card-header { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.5rem; }
        .product-card .rank-badge {
            background: linear-gradient(135deg, #6f8d86, #88a39a); color: #fff; font-weight: 700;
            width: 32px; height: 32px; border-radius: 50%;
            display: flex; align-items: center; justify-content: center; font-size: 0.85rem; flex-shrink: 0;
        }
        .product-card .cat-icon { font-size: 1.5rem; flex-shrink: 0; }
        .product-card .title-block { flex-grow: 1; }
        .product-card .title-block h4 { margin: 0; font-size: 1.05rem; color: #1f2a33; }
        .product-card .title-block .subtitle { font-size: 0.82rem; color: #7a8a94; }
        .product-card .price-tag {
            font-family: 'Space Grotesk', sans-serif; font-size: 1.15rem;
            font-weight: 700; color: #2d6a4f; white-space: nowrap;
        }
        .product-card .card-body { font-size: 0.9rem; color: #4a5a64; margin-bottom: 0.5rem; }
        .product-card .score-badge {
            background: linear-gradient(135deg, #f0f7ff, #e3effd); border: 1px solid #c2d8f0;
            color: #2c5282; padding: 0.2rem 0.55rem; border-radius: 999px;
            font-size: 0.78rem; font-weight: 600;
        }

        /* Highlight matched terms */
        mark {
            background: rgba(111, 141, 134, 0.25);
            color: inherit;
            padding: 1px 2px;
            border-radius: 3px;
        }

        /* Sidebar: white text on dark background */
        section[data-testid="stSidebar"] {
            background: #1e2a33 !important;
        }
        section[data-testid="stSidebar"] * {
            color: #e8ecef !important;
        }
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] span,
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] div,
        section[data-testid="stSidebar"] small,
        section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
        section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
        section[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
        section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p,
        section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] small {
            color: #d0d6db !important;
        }
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3 {
            color: #ffffff !important;
        }
        section[data-testid="stSidebar"] .stButton > button {
            background: linear-gradient(135deg, #3a5a52 0%, #4a6b62 100%) !important;
            color: #f0f5f3 !important;
            border: 1px solid rgba(255, 255, 255, 0.12) !important;
            pointer-events: auto !important;
            cursor: pointer !important;
            position: relative !important;
            z-index: 1 !important;
        }
        section[data-testid="stSidebar"] .stButton > button:hover {
            background: linear-gradient(135deg, #4a6b62 0%, #5a7b72 100%) !important;
            color: #ffffff !important;
        }
        section[data-testid="stSidebar"] .stButton > button p {
            color: #f0f5f3 !important;
        }
        section[data-testid="stSidebar"] hr {
            border-color: rgba(255, 255, 255, 0.15) !important;
        }

        /* Fix st.success green-on-green: force dark text */
        [data-testid="stAlert"] p,
        [data-testid="stAlert"] strong {
            color: #155724 !important;
        }

        /* Active sidebar user highlight */
        section[data-testid="stSidebar"] .stButton > button[data-active="true"] {
            background: linear-gradient(135deg, #2d6a4f 0%, #3a8a6a 100%) !important;
            border: 2px solid #7cf5b5 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def list_user_ids() -> list[str]:
    """Return demo user IDs + top real users from DB."""
    demo_ids = list(USER_ROLE_LABELS.keys())
    try:
        db_users = repository.list_users(limit=20)
        db_ids = [u["user_id"] for u in db_users if u["user_id"] not in demo_ids]
        return demo_ids + db_ids
    except Exception:
        return demo_ids


def format_user_label(uid: str) -> str:
    if uid in USER_ROLE_LABELS:
        return USER_ROLE_LABELS[uid]
    # Try to get org name from DB
    try:
        profile_info = repository.get_user_profile(uid)
        db_users = repository.list_users(limit=100)
        for u in db_users:
            if u["user_id"] == uid:
                name = u["user_name"][:40]
                return f"🏛 {name} (ИНН {uid})"
    except Exception:
        pass
    return f"🏛 ИНН {uid}"


def category_icon(category: str) -> str:
    cat_lower = category.lower()
    for key, icon in CATEGORY_ICONS.items():
        if key in cat_lower:
            return icon
    return "📦"


def sanitize_attributes(attrs_str: str, max_len: int = 150) -> str:
    """Clean up garbage attribute strings (repeated words/numbers from CSV import)."""
    if not attrs_str:
        return ""
    # Detect repeated patterns: split into words, check if >50% are duplicates
    words = attrs_str.split()
    if len(words) > 4:
        from collections import Counter
        counter = Counter(words)
        most_common_count = counter.most_common(1)[0][1]
        # If the most common word appears in >40% of all words => garbage
        if most_common_count > len(words) * 0.4:
            # Try to extract unique meaningful words (not numbers)
            unique_words = []
            seen = set()
            for w in words:
                w_clean = w.strip(".,;:!?()")
                if w_clean and w_clean not in seen and not _is_garbage_token(w_clean):
                    seen.add(w_clean)
                    unique_words.append(w_clean)
            if unique_words:
                return ", ".join(unique_words[:10])
            return ""
    return attrs_str[:max_len]


def _is_garbage_token(token: str) -> bool:
    """Check if a token is garbage (pure number, repeated pattern)."""
    # Pure numbers like '36', '14.00000', '2.00000'
    try:
        float(token)
        return True
    except ValueError:
        pass
    # Very short or common garbage
    if token.lower() in ("нет", "да", "none", "null", "-"):
        return True
    return False


def format_price(price: float) -> str:
    return f"{price:,.0f} ₽".replace(",", " ")


def render_reason_pills(reasons: list[str]) -> None:
    html = "".join(f'<span class="reason-pill">{reason}</span>' for reason in reasons)
    st.markdown(html or '<span class="reason-pill">Без пояснений</span>', unsafe_allow_html=True)


def render_pipeline(response: SearchResponse) -> None:
    corrected = response.corrected_query and response.corrected_query != response.query
    expanded = bool(response.expanded_terms)
    semantic_on = response.semantic_backend not in (None, "off", "")
    reranked = response.reranker_backend not in (None, "off", "")
    personalized = response.personalized
    steps = [
        ("Коррекция", corrected), ("Синонимы", expanded),
        ("Ключевые слова", True), ("Семантика", semantic_on),
        ("Реранкинг", reranked), ("Персонализация", personalized),
    ]
    parts = []
    for label, active in steps:
        cls = "active" if active else "inactive"
        parts.append(f'<span class="pipeline-step {cls}">{label}</span>')
    html = '<span class="pipeline-arrow">→</span>'.join(parts)
    st.markdown(f"<div style='margin:0.5rem 0'>{html}</div>", unsafe_allow_html=True)


def apply_demo_scenario(scenario_key: str) -> None:
    scenario = get_demo_scenario(scenario_key)
    if scenario is None:
        return
    st.session_state["last_query"] = scenario.query
    st.session_state["selected_user_id"] = scenario.user_id or ""
    st.session_state["selected_demo_scenario"] = scenario.key


def run_demo_events(scenario_key: str) -> str:
    scenario = get_demo_scenario(scenario_key)
    if scenario is None:
        return "Сценарий не найден"
    if not scenario.events:
        return "Для этого сценария нет событий"
    for event in scenario.events:
        repository.add_event(event)
    return f"Применено событий: {len(scenario.events)}"


def render_search_response(response: SearchResponse, user_id: str | None, compare_modes: bool, key_prefix: str, show_debug: bool = False, sort_option: str = "По релевантности") -> None:
    render_pipeline(response)
    summary_cols = st.columns(5)
    summary_cols[0].metric("Найдено", response.total)
    summary_cols[1].metric("Персонализация", "вкл" if response.personalized else "выкл")
    summary_cols[2].metric("Режим", response.mode)
    correction_label = response.corrected_query if response.corrected_query and response.corrected_query != response.query else "—"
    summary_cols[3].metric("Коррекция", correction_label)
    speed_color = "🟢" if response.search_time_ms < 200 else "🟡" if response.search_time_ms < 1000 else "🔴"
    summary_cols[4].metric(f"{speed_color} Скорость", f"{response.search_time_ms:.0f} мс")

    if response.typo_corrected:
        st.info(f"✏️ Автокоррекция: **{response.query}** → **{response.corrected_query}**")

    if response.semantic_backend and "sentence" in response.semantic_backend:
        st.success("🧠 Семантическое расширение: найдены похожие категории через нейросеть")

    if response.expanded_terms:
        expanded_pills = " ".join(f"`{t}`" for t in response.expanded_terms)
        st.markdown(f"**Расширение синонимами:** {expanded_pills}")

    # Category facets — clickable for filtering
    if response.facets:
        st.markdown("**Категории в результатах:**")
        facet_cols = st.columns(min(len(response.facets), 6))
        for i, facet in enumerate(response.facets[:6]):
            icon = category_icon(facet.category)
            with facet_cols[i]:
                if st.button(
                    f"{icon} {facet.category[:28]}\n{facet.count} шт",
                    key=f"{key_prefix}-facet-{i}",
                    use_container_width=True,
                ):
                    # Re-run search with this category filter
                    st.session_state["demo_category_filter"] = facet.category
                    st.session_state["demo_query"] = response.query
                    st.rerun()

    if show_debug:
        with st.expander("Технические детали", expanded=False):
            info_cols = st.columns(4)
            info_cols[0].metric("Semantic", response.semantic_backend or "off")
            info_cols[1].metric("Reranker", response.reranker_backend or "off")
            info_cols[2].metric("Mode", response.mode)
            info_cols[3].metric("Search ms", f"{response.search_time_ms:.1f}")

    if response.items:
        # Fetch popularity/price data for all items at once
        product_ids = [item.product.id for item in response.items]
        popularity_map = repository.get_products_popularity(product_ids)
        prices_map = repository.get_products_prices(product_ids)

        for index, item in enumerate(response.items, start=1):
            pop_count = popularity_map.get(item.product.id, 0)
            avg_price = prices_map.get(item.product.id)
            result_card(item, user_id, response.mode, index, key_prefix=key_prefix,
                       popularity=pop_count, avg_price=avg_price)
    else:
        st.warning("Ничего не найдено. Попробуйте другой запрос.")

    if compare_modes:
        st.markdown("---")
        st.markdown("### Сравнение режимов")
        rows = []
        for candidate_mode in ["keyword", "semantic", "hybrid"]:
            candidate = search_products(query=response.query, limit=3, user_id=user_id or None, mode=candidate_mode)
            rows.append({
                "Режим": candidate_mode.upper(),
                "Найдено": candidate.total,
                "Семантика": candidate.semantic_backend or "off",
                "Реранкер": candidate.reranker_backend or "off",
                "Время": f"{candidate.search_time_ms:.0f} мс",
                "Топ результаты": " | ".join(item.product.title[:40] for item in candidate.items) or "нет",
            })
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def render_demo_scenarios_tab() -> None:
    st.markdown("## 🔍 Умный поиск")
    st.caption("Основной пользовательский экран: вводите запрос и получаете итоговую выдачу без ручного выбора технического режима.")

    st.markdown(
        f"<div class='hero-card'>"
        f"<strong>Как это работает:</strong> Запрос → Автокоррекция опечаток → Лемматизация + синонимы → FTS5 BM25 retrieval → "
        f"Семантическое расширение (sentence-transformers) → Персонализация (контрактная история) → Фасетная фильтрация<br>"
        f"<span style='color:#5f8a7a;font-weight:600'>📦 {repository.count_products():,} товаров (СТЕ) · 👥 {repository.count_profiles():,} организаций · 📂 {repository.count_categories():,} категорий</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # --- Search input (NO form — allows re-typing freely) ---
    demo_query = st.text_input(
        "Введите запрос",
        value=st.session_state.get("demo_query", ""),
        key="demo_query_input",
        placeholder="масло, канцтовары, шприц, ноутбук Lenovo...",
    )

    # --- Live search suggestions ---
    if demo_query and len(demo_query) >= 2 and demo_query != st.session_state.get("_last_searched", ""):
        suggestions = repository.suggest_products(demo_query, limit=6)
        if suggestions:
            st.markdown("**Подсказки:**")
            scols = st.columns(min(len(suggestions), 6))
            for si, sug in enumerate(suggestions):
                with scols[si % len(scols)]:
                    if sug["type"] == "category":
                        icon = category_icon(sug["title"])
                        btn_label = f"{icon} {sug['title'][:30]}\n← категория ({sug['count']})"
                    else:
                        icon = category_icon(sug.get("category", ""))
                        btn_label = f"{icon} {sug['title'][:35]}"
                    if st.button(btn_label, key=f"sug-{si}", use_container_width=True):
                        if sug["type"] == "category":
                            st.session_state["demo_category_filter"] = sug["title"]
                            st.session_state["demo_query"] = demo_query
                        else:
                            st.session_state["demo_query"] = sug["title"][:60]
                        st.rerun()

    # --- Settings row ---
    active_cat_filter = st.session_state.get("demo_category_filter", None)
    if active_cat_filter:
        fcols = st.columns([5, 1])
        fcols[0].info(f"📂 Фильтр по категории: **{active_cat_filter}**")
        if fcols[1].button("✕ Сбросить", key="clear-cat-filter"):
            st.session_state["demo_category_filter"] = None
            st.rerun()

    setting_cols = st.columns([1, 1, 1, 1, 1])
    demo_limit = setting_cols[0].number_input("Результатов", min_value=1, max_value=500, value=10, step=1, key="demo-limit")
    sort_option = setting_cols[1].selectbox("Сортировка", options=["По релевантности", "По популярности", "По цене ↑", "По цене ↓"], index=0, key="demo-sort")
    show_advanced = setting_cols[2].checkbox("Расширенные", value=False, key="demo-show-advanced")
    show_facet_filter = setting_cols[3].checkbox("Фильтр категорий", value=False, key="demo-show-facet")
    search_clicked = setting_cols[4].button("🔎 Искать", key="demo-search-btn", use_container_width=True)

    sidebar_user = st.session_state.get("selected_user_id", "")
    demo_user_id = sidebar_user
    demo_mode = "hybrid"
    demo_compare_modes = False
    demo_category_filter = active_cat_filter

    demo_user_options = ["", *list_user_ids()]
    if show_advanced:
        advanced_cols = st.columns(3)
        default_idx = demo_user_options.index(sidebar_user) if sidebar_user in demo_user_options else 0
        demo_user_id = advanced_cols[0].selectbox("Пользователь", options=demo_user_options, format_func=lambda u: format_user_label(u) if u else "— без персонализации —", index=default_idx, key="demo-user")
        demo_mode = advanced_cols[1].selectbox("Режим", options=["keyword", "semantic", "hybrid"], index=2, key="demo-mode")
        demo_compare_modes = advanced_cols[2].checkbox("Сравнить режимы", value=False, key="demo-compare")
    if show_facet_filter:
        cat_input = st.text_input("Поиск по категориям", value="", key="demo-cat-input", placeholder="канцелярские, масло, фильтр...")
        if cat_input:
            matching_cats = repository.search_categories(cat_input, limit=10)
            if matching_cats:
                cat_options = [""] + [c[0] for c in matching_cats]
                selected_cat = st.selectbox(
                    "Выберите категорию",
                    options=cat_options,
                    format_func=lambda c: f"{category_icon(c)} {c} ({next((n for cn, n in matching_cats if cn == c), '')} шт)" if c else "— все категории —",
                    key="demo-cat-filter",
                )
                if selected_cat:
                    demo_category_filter = selected_cat
            else:
                st.caption("Категории не найдены")

    if sidebar_user and not show_advanced:
        st.info(f"🔍 Поиск от имени: **{format_user_label(sidebar_user)}** (выбран в сайдбаре)")

    # --- Execute search ---
    should_search = search_clicked
    # Also auto-search when there's a pending query from facet/suggestion click
    pending_query = st.session_state.get("demo_query", "")
    if not should_search and active_cat_filter and pending_query:
        should_search = True
        demo_query = pending_query

    if should_search and demo_query:
        st.session_state["demo_query"] = demo_query
        st.session_state["last_query"] = demo_query
        st.session_state["_last_searched"] = demo_query
        demo_response = search_products(query=demo_query, limit=demo_limit, user_id=demo_user_id or None, mode=demo_mode, category_filter=demo_category_filter)

        # --- Apply sorting ---
        if sort_option != "По релевантности" and demo_response.items:
            product_ids = [item.product.id for item in demo_response.items]
            if sort_option == "По популярности":
                popularity = repository.get_products_popularity(product_ids)
                demo_response.items.sort(key=lambda it: popularity.get(it.product.id, 0), reverse=True)
            elif sort_option in ("По цене ↑", "По цене ↓"):
                prices = repository.get_products_prices(product_ids)
                desc = sort_option == "По цене ↓"
                demo_response.items.sort(key=lambda it: prices.get(it.product.id, 0), reverse=desc)

        render_search_response(
            response=demo_response,
            user_id=demo_user_id or None,
            compare_modes=demo_compare_modes,
            key_prefix="demo",
            show_debug=show_advanced,
            sort_option=sort_option,
        )




def result_card(item, user_id: str | None, mode: str, rank: int, key_prefix: str = "search", popularity: int = 0, avg_price: float | None = None) -> None:
    product = item.product
    icon = category_icon(product.category)
    score_color = "#27ae60" if item.score >= 20 else "#e67e22" if item.score >= 10 else "#95a5a6"
    reasons_html = " ".join(f"<code>{html_module.escape(r)}</code>" for r in (item.reasons or []))
    attrs_str = sanitize_attributes(product.attributes.get("raw", "")) if product.attributes else ""
    # Use highlighted title if available
    display_title = item.highlight_title if item.highlight_title else html_module.escape(product.title)

    # Personalization indicator
    pers_badge = ""
    if any("буст" in r for r in (item.reasons or [])):
        pers_badge = '<span style="background:#d4edda;color:#155724;padding:2px 8px;border-radius:8px;font-size:0.75rem;font-weight:600;margin-left:6px">⚡ Персонализировано</span>'

    # Popularity & price badges
    extra_badges = ""
    if popularity > 0:
        extra_badges += f'<span style="background:#e8f4fd;color:#1a5276;padding:2px 8px;border-radius:8px;font-size:0.72rem;font-weight:500;margin-left:4px">📊 {popularity} контрактов</span>'
    if avg_price and avg_price > 0:
        price_str = f"{avg_price:,.0f}".replace(",", " ")
        extra_badges += f'<span style="background:#fef9e7;color:#7d6608;padding:2px 8px;border-radius:8px;font-size:0.72rem;font-weight:500;margin-left:4px">💰 ~{price_str} ₽</span>'

    card_html = f"""
    <div class="product-card">
        <div class="card-header">
            <span class="rank-badge">#{rank}</span>
            <span class="cat-icon">{icon}</span>
            <div class="title-block">
                <strong>{display_title}</strong>{pers_badge}{extra_badges}<br>
                <small style="color:#888">ID {product.id} · {html_module.escape(product.category)}</small>
            </div>
            <span class="score-badge" style="background:{score_color};color:#fff;padding:4px 10px;border-radius:12px;font-weight:700">{item.score:.1f}</span>
        </div>
        <div class="card-body">
            {f'<p style="margin:0 0 4px;font-size:0.85rem;color:#666">{html_module.escape(attrs_str)}</p>' if attrs_str else ''}
            {f'<p style="margin:0">{reasons_html}</p>' if reasons_html else ''}
        </div>
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)


def render_search_tab() -> None:
    st.markdown("## 🧪 Search Studio — Лаборатория")
    st.markdown(
        "<div class='hero-card'><strong>Лаборатория:</strong> сравнение алгоритмов поиска бок о бок. "
        "Введите запрос и увидите как работает каждый из 3 режимов (keyword, semantic, hybrid) с детальным анализом.</div>",
        unsafe_allow_html=True,
    )

    options = ["", *list_user_ids()]
    query = st.text_input("Поисковый запрос", value=st.session_state.get("last_query", "ноут для офиса"), key="lab-query")
    lab_cols = st.columns(3)
    user_id = lab_cols[0].selectbox("Пользователь", options=options, format_func=lambda u: format_user_label(u) if u else "— без —", index=1 if len(options) > 1 else 0, key="lab-user")
    limit = lab_cols[1].number_input("Лимит результатов", min_value=1, max_value=50, value=5, step=1, key="lab-limit")
    run_comparison = lab_cols[2].button("🔬 Сравнить все режимы", use_container_width=True, key="lab-run")

    if not run_comparison:
        st.caption("Нажмите «Сравнить все режимы» для запуска анализа.")
        return

    st.session_state["last_query"] = query

    # Run all 3 modes
    modes = ["keyword", "semantic", "hybrid"]
    results: dict[str, SearchResponse] = {}
    for m in modes:
        results[m] = search_products(query=query, limit=limit, user_id=user_id or None, mode=m)

    # Summary comparison table
    st.markdown("### 📊 Сводная таблица")
    summary_rows = []
    for m in modes:
        r = results[m]
        summary_rows.append({
            "Режим": m.upper(),
            "Найдено": r.total,
            "Семантика": r.semantic_backend or "off",
            "Персонализация": "✅" if r.personalized else "❌",
            "Время (мс)": f"{r.search_time_ms:.0f}",
            "Топ-1": r.items[0].product.title[:50] if r.items else "—",
            "Score топ-1": f"{r.items[0].score:.1f}" if r.items else "—",
        })
    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

    # Speed chart
    st.markdown("### ⏱ Скорость (мс)")
    speed_data = pd.DataFrame({
        "Режим": [m.upper() for m in modes],
        "мс": [results[m].search_time_ms for m in modes],
    }).set_index("Режим")
    st.bar_chart(speed_data)

    # Side-by-side results
    st.markdown("### 🔍 Результаты по режимам")
    result_cols = st.columns(3)
    for ci, m in enumerate(modes):
        with result_cols[ci]:
            r = results[m]
            st.markdown(f"#### {m.upper()}")
            speed_color = "🟢" if r.search_time_ms < 200 else "🟡" if r.search_time_ms < 1000 else "🔴"
            st.caption(f"{speed_color} {r.search_time_ms:.0f} мс · {r.total} результатов · Семантика: {r.semantic_backend or 'off'}")
            render_pipeline(r)
            if r.items:
                rows = [
                    {"#": idx + 1, "Товар": f"{category_icon(it.product.category)} {it.product.title[:45]}", "Score": f"{it.score:.1f}"}
                    for idx, it in enumerate(r.items)
                ]
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            else:
                st.warning("Нет результатов")

    # Overlap analysis
    st.markdown("### 🔄 Анализ пересечений")
    sets = {m: {it.product.id for it in results[m].items} for m in modes}
    overlap_rows = []
    for m1 in modes:
        for m2 in modes:
            if m1 < m2:
                common = sets[m1] & sets[m2]
                overlap_rows.append({
                    "Пара": f"{m1.upper()} ∩ {m2.upper()}",
                    "Общих товаров": len(common),
                    f"Только {m1.upper()}": len(sets[m1] - sets[m2]),
                    f"Только {m2.upper()}": len(sets[m2] - sets[m1]),
                })
    st.dataframe(pd.DataFrame(overlap_rows), use_container_width=True, hide_index=True)


def render_analytics_tab() -> None:
    """Combined analytics tab — lazy loaded sections."""
    st.markdown("## 📊 Аналитика и данные")
    st.caption("Панель разработчика: профили, метрики качества, движки, данные. Каждый раздел загружается только по запросу.")

    section = st.radio(
        "Выберите раздел",
        options=["👤 Профили организаций", "⚙ Система и метрики", "🗂 Данные и синонимы"],
        horizontal=True,
        key="analytics-section",
    )

    if section == "👤 Профили организаций":
        _render_profiles_section()
    elif section == "⚙ Система и метрики":
        if st.button("📈 Загрузить метрики (занимает время)", key="load-metrics"):
            _render_system_section()
        else:
            st.info("Нажмите кнопку выше для загрузки evaluation и сравнения режимов.")
    elif section == "🗂 Данные и синонимы":
        _render_data_section()


def _render_profiles_section() -> None:
    users = list_user_ids()
    default_user = st.session_state.get("selected_user_id", users[0] if users else "7714338609")
    selected_user = st.selectbox("Пользователь", options=users, format_func=format_user_label, index=users.index(default_user) if default_user in users else 0, key="prof-user")
    profile = repository.get_user_profile(selected_user)

    metrics = st.columns(4)
    metrics[0].metric("Всего контрактов", profile.total_events)
    metrics[1].metric("Средняя цена", format_price(profile.average_price) if profile.average_price else "—")
    metrics[2].metric("Категорий в профиле", len(profile.category_affinity))
    metrics[3].metric("User ID (ИНН)", selected_user)

    st.markdown("### Категории закупок (аффинити)")
    if profile.category_affinity:
        sorted_cats = dict(sorted(profile.category_affinity.items(), key=lambda x: x[1], reverse=True))
        labels = [f"{category_icon(k)} {k[:50]}" for k in sorted_cats]
        values = list(sorted_cats.values())
        st.bar_chart(pd.DataFrame({"аффинити": values}, index=labels))
    else:
        st.info("Нет данных о закупках")


def _render_system_section() -> None:
    with st.spinner("Вычисление метрик..."):
        evaluation = evaluate_search()
        comparison = compare_search_modes()
    semantic_status = semantic_engine.status()
    reranker_status = reranker.status()

    top_cols = st.columns(5)
    top_cols[0].metric("📦 Каталог", f"{repository.count_products():,}")
    top_cols[1].metric("📊 События", repository.count_events())
    top_cols[2].metric("👥 Профили", f"{repository.count_profiles():,}")
    top_cols[3].metric("📂 Категории", f"{repository.count_categories():,}")
    top_cols[4].metric("💾 Хранилище", repository.backend_name())

    engine_cols = st.columns(2)
    with engine_cols[0]:
        sem_icon = "🟢" if semantic_status.ready else "🔴"
        st.markdown(f"### {sem_icon} Semantic engine")
        st.json({
            "ready": semantic_status.ready,
            "backend": semantic_status.backend,
            "model_name": semantic_status.model_name,
            "categories_indexed": semantic_status.categories_indexed,
            "last_error": semantic_status.last_error,
        })
    with engine_cols[1]:
        rr_icon = "🟢" if reranker_status.ready else "🔴"
        st.markdown(f"### {rr_icon} Reranker")
        st.json({
            "ready": reranker_status.ready,
            "backend": reranker_status.backend,
            "model_name": reranker_status.model_name,
            "last_error": reranker_status.last_error,
        })

    st.markdown("### 📈 Evaluation summary")
    metric_cols = st.columns(5)
    metric_cols[0].metric("Hit@3", f"{evaluation.hit_rate_at_3:.2f}")
    metric_cols[1].metric("MRR@10", f"{evaluation.mrr_at_10:.3f}")
    metric_cols[2].metric("NDCG@10", f"{evaluation.ndcg_at_10:.3f}")
    metric_cols[3].metric("Precision@3", f"{evaluation.precision_at_3:.3f}")
    metric_cols[4].metric("Recall@10", f"{evaluation.recall_at_10:.3f}")

    with st.expander("Детали по кейсам", expanded=False):
        st.dataframe(pd.DataFrame([case.model_dump() for case in evaluation.cases]), use_container_width=True, hide_index=True)

    st.markdown("### Сравнение режимов")
    st.success(f"Лучший режим по NDCG@10: **{comparison.best_mode_by_ndcg}**")
    st.dataframe(pd.DataFrame([row.model_dump() for row in comparison.rows]), use_container_width=True, hide_index=True)


def _render_data_section() -> None:
    import_cols = st.columns(2)
    with import_cols[0]:
        with st.form("catalog_import_form"):
            st.markdown("#### 📦 Каталог")
            catalog_path = st.text_input("Путь", value="data/catalog.json")
            replace_catalog = st.checkbox("Заменить существующий", value=True)
            import_catalog_submit = st.form_submit_button("Импортировать каталог")

        if import_catalog_submit:
            try:
                products, result = import_catalog(catalog_path, replace_existing=replace_catalog)
                if replace_catalog:
                    repository.replace_products(products)
                else:
                    repository.replace_products(repository.products + products)
                semantic_engine.reset()
                st.success(f"Импортировано товаров: {result.imported_count}")
                st.json(result.model_dump())
            except Exception as exc:
                st.error(str(exc))

    with import_cols[1]:
        with st.form("events_import_form"):
            st.markdown("#### 📊 События")
            events_path = st.text_input("Путь", value="data/sample_events.json")
            replace_events = st.checkbox("Заменить существующие", value=False)
            import_events_submit = st.form_submit_button("Импортировать события")

        if import_events_submit:
            try:
                events, result = import_events(events_path, replace_existing=replace_events)
                if replace_events:
                    repository.replace_events(events)
                else:
                    repository.append_events(events)
                st.success(f"Импортировано событий: {result.imported_count}")
                st.json(result.model_dump())
            except Exception as exc:
                st.error(str(exc))

    st.markdown("### 📖 Синонимы")
    synonym_map = get_synonym_map()
    st.caption(f"Всего групп: {len(synonym_map)}")
    synonym_rows = [
        {"Термин": key, "Варианты": ", ".join(values)}
        for key, values in list(synonym_map.items())[:20]
    ]
    st.dataframe(pd.DataFrame(synonym_rows), use_container_width=True, hide_index=True)


def main() -> None:
    inject_styles()
    st.markdown(
        """
        <div class="hero-card">
            <h1>🔍 Персонализированный умный поиск</h1>
            <p style="font-size:1.1rem;margin-bottom:0.5rem">Портал закупок zakupki.mos.ru</p>
            <div style="display:flex;gap:1rem;flex-wrap:wrap;margin-top:0.5rem">
                <span class="pipeline-step active">Автокоррекция опечаток</span>
                <span class="pipeline-arrow">→</span>
                <span class="pipeline-step active">Лемматизация + синонимы</span>
                <span class="pipeline-arrow">→</span>
                <span class="pipeline-step active">BM25 (FTS5)</span>
                <span class="pipeline-arrow">→</span>
                <span class="pipeline-step active">Семантический поиск</span>
                <span class="pipeline-arrow">→</span>
                <span class="pipeline-step active">Персонализация</span>
                <span class="pipeline-arrow">→</span>
                <span class="pipeline-step active">Фасетная фильтрация</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.sidebar.markdown("### 🏛 Control Room")
    st.sidebar.caption(f"📦 {repository.count_products():,} СТЕ · � {repository.count_profiles():,} организаций · 📂 {repository.count_categories():,} категорий")
    sem_st = semantic_engine.status()
    rr_st = reranker.status()
    sem_icon = "🟢" if sem_st.ready else "🔴"
    st.sidebar.caption(f"🔍 FTS5 BM25 · {sem_icon} Семантика ({sem_st.categories_indexed} кат.) · ✏️ Автокоррекция")

    st.sidebar.markdown("---")
    active_user = st.session_state.get("selected_user_id", "")
    if active_user:
        st.sidebar.markdown(f"**Активный профиль:** {format_user_label(active_user)}")
    else:
        st.sidebar.markdown("Профиль не выбран")

    st.sidebar.markdown("Быстрый профиль:")
    for uid in USER_ROLE_LABELS:
        is_active = (uid == active_user)
        label = f"✅ {USER_ROLE_LABELS[uid]}" if is_active else USER_ROLE_LABELS[uid]
        if st.sidebar.button(label, key=f"sb-{uid}", use_container_width=True):
            if is_active:
                st.session_state["selected_user_id"] = ""
            else:
                st.session_state["selected_user_id"] = uid
            st.rerun()

    if st.sidebar.button("🔄 Сброс demo", key="sidebar-reset-demo", use_container_width=True):
        repository.reset_demo_state()
        semantic_engine.reset()
        st.rerun()

    tabs = st.tabs(["🔍 Поиск", "🧪 Лаборатория", "� Аналитика"])
    with tabs[0]:
        render_demo_scenarios_tab()
    with tabs[1]:
        render_search_tab()
    with tabs[2]:
        render_analytics_tab()


if __name__ == "__main__":
    main()
