import pandas as pd
import streamlit as st
import html as html_module

from app.demo_scenarios import get_demo_scenario, get_demo_scenarios
from app.evaluation_compare import compare_search_modes
from app.evaluation import evaluate_search
from app.ingestion import import_catalog, import_events
from app.repository import repository
from app.reranker import reranker
from app.schemas import EventCreate, SearchResponse
from app.search import search_products
from app.semantic import semantic_engine
from app.settings import settings
from app.synonyms import get_synonym_map

# Warm up vocabulary lazily — triggered on first typo-correcting search
# (background thread removed to avoid SQLite concurrency issues)


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

QUICK_EXAMPLES: list[tuple[str, str]] = [
    ("шприц", "Персонализация: аптека vs авто"),
    ("фильтр", "Авто-фильтр vs воздушный"),
    ("ноутбук Lenovo", "Точный запрос по бренду"),
    ("бумага офисная", "Широкий запрос BM25"),
    ("канцтовары", "Семантика + синонимы"),
    ("перчтки", "Автокоррекция опечатки"),
]


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


def render_search_response(response: SearchResponse, user_id: str | None, compare_modes: bool, key_prefix: str, show_debug: bool = False) -> None:
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

    # Category facets
    if response.facets:
        st.markdown("**Категории в результатах:**")
        facet_cols = st.columns(min(len(response.facets), 6))
        for i, facet in enumerate(response.facets[:6]):
            icon = category_icon(facet.category)
            facet_cols[i].markdown(
                f"<div style='text-align:center;padding:6px 8px;border-radius:12px;background:rgba(111,141,134,0.1);font-size:0.82rem'>"
                f"{icon} <b>{facet.category[:28]}</b><br><small>{facet.count} шт</small></div>",
                unsafe_allow_html=True,
            )

    if show_debug:
        with st.expander("Технические детали", expanded=False):
            info_cols = st.columns(4)
            info_cols[0].metric("Semantic", response.semantic_backend or "off")
            info_cols[1].metric("Reranker", response.reranker_backend or "off")
            info_cols[2].metric("Mode", response.mode)
            info_cols[3].metric("Search ms", f"{response.search_time_ms:.1f}")

    if response.items:
        for index, item in enumerate(response.items, start=1):
            result_card(item, user_id, response.mode, index, key_prefix=key_prefix)
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

    example_cols = st.columns(len(QUICK_EXAMPLES))
    for idx, (label, query_val) in enumerate(QUICK_EXAMPLES):
        if example_cols[idx].button(label, key=f"qe-{idx}", use_container_width=True):
            st.session_state["demo_query"] = query_val

    demo_user_options = ["", *list_user_ids()]
    with st.form("demo_quick_search_form"):
        demo_query = st.text_input("Введите запрос", value=st.session_state.get("demo_query", ""))
        top_cols = st.columns([2, 1, 1])
        demo_limit = top_cols[0].number_input("Результатов", min_value=1, max_value=500, value=10, step=1, key="demo-limit")
        show_advanced = top_cols[1].checkbox("Расширенные настройки", value=False, key="demo-show-advanced")
        show_facet_filter = top_cols[2].checkbox("Фильтр по категории", value=False, key="demo-show-facet")

        # Use sidebar-selected user by default
        sidebar_user = st.session_state.get("selected_user_id", "")
        demo_user_id = sidebar_user
        demo_mode = "hybrid"
        demo_compare_modes = False
        demo_category_filter = None
        if show_advanced:
            advanced_cols = st.columns(3)
            default_idx = demo_user_options.index(sidebar_user) if sidebar_user in demo_user_options else 0
            demo_user_id = advanced_cols[0].selectbox("Пользователь", options=demo_user_options, format_func=lambda u: format_user_label(u) if u else "— без персонализации —", index=default_idx, key="demo-user")
            demo_mode = advanced_cols[1].selectbox("Режим", options=["keyword", "semantic", "hybrid"], index=2, key="demo-mode")
            demo_compare_modes = advanced_cols[2].checkbox("Сравнить режимы", value=False, key="demo-compare")
        if show_facet_filter:
            cat_input = st.text_input("Введите часть названия категории для фильтра", value="", key="demo-cat-input")
            if cat_input:
                matching_cats = repository.search_categories(cat_input, limit=10)
                if matching_cats:
                    cat_options = [""] + [c[0] for c in matching_cats]
                    demo_category_filter = st.selectbox(
                        "Фильтр категории",
                        options=cat_options,
                        format_func=lambda c: f"{category_icon(c)} {c} ({next((n for cn, n in matching_cats if cn == c), '')})" if c else "— все категории —",
                        key="demo-cat-filter",
                    ) or None
        demo_submitted = st.form_submit_button("🔎 Искать")

    if sidebar_user and not show_advanced:
        st.info(f"🔍 Поиск от имени: **{format_user_label(sidebar_user)}** (выбран в сайдбаре)")

    if demo_submitted:
        st.session_state["demo_query"] = demo_query
        st.session_state["last_query"] = demo_query
        demo_response = search_products(query=demo_query, limit=demo_limit, user_id=demo_user_id or None, mode=demo_mode, category_filter=demo_category_filter)
        render_search_response(
            response=demo_response,
            user_id=demo_user_id or None,
            compare_modes=demo_compare_modes,
            key_prefix="demo",
            show_debug=show_advanced,
        )

    st.markdown("---")
    st.markdown("## 🎬 Готовые сценарии")
    st.caption("Демо-пресеты для показа жюри. В продакшне этот блок не нужен.")

    scenarios = get_demo_scenarios()
    selected_key = st.session_state.get("selected_demo_scenario", scenarios[0].key if scenarios else "")
    with st.expander("Показать demo-сценарии", expanded=False):
        selected_key = st.radio(
            "Сценарий",
            options=[scenario.key for scenario in scenarios],
            format_func=lambda key: next((scenario.title for scenario in scenarios if scenario.key == key), key),
            index=next((index for index, scenario in enumerate(scenarios) if scenario.key == selected_key), 0) if scenarios else 0,
            horizontal=True,
            label_visibility="collapsed",
        )
        scenario = get_demo_scenario(selected_key)
        if scenario is None:
            st.info("Сценарии недоступны")
            return

        with st.container(border=True):
            st.markdown(f"### {scenario.title}")
            st.caption(scenario.summary)
            st.markdown(f"**Цель:** {scenario.goal}")
            for index, step in enumerate(scenario.steps, start=1):
                st.markdown(f"{index}. {step}")

        control_cols = st.columns(4)
        if control_cols[0].button("▶ Загрузить", key=f"load-scenario-{scenario.key}", use_container_width=True):
            apply_demo_scenario(scenario.key)
            st.session_state["demo_query"] = scenario.query
            st.success("Сценарий загружен в поле поиска выше ↑")
        if control_cols[1].button("📥 События", key=f"apply-events-{scenario.key}", use_container_width=True):
            st.success(run_demo_events(scenario.key))
        if control_cols[2].button("🔄 Сброс", key=f"reset-state-{scenario.key}", use_container_width=True):
            repository.reset_demo_state()
            semantic_engine.reset()
            st.success("Demo state сброшен")
        if control_cols[3].button("👤 Профиль", key=f"open-profile-{scenario.key}", use_container_width=True):
            st.session_state["selected_user_id"] = scenario.user_id or "user-1"
            st.info("Профиль выбран во вкладке Профили")

        baseline_response = search_products(query=scenario.query, limit=5, user_id=None, mode=scenario.mode)
        personalized_response = search_products(query=scenario.query, limit=5, user_id=scenario.user_id, mode=scenario.mode) if scenario.user_id else None

        compare_cols = st.columns(2)
        with compare_cols[0]:
            st.markdown("#### Базовый поиск")
            baseline_rows = [
                {"#": index + 1, "Товар": f"{category_icon(item.product.category)} {item.product.title}", "Категория": item.product.category[:40], "Score": f"{item.score:.1f}"}
                for index, item in enumerate(baseline_response.items)
            ]
            st.dataframe(pd.DataFrame(baseline_rows), width="stretch", hide_index=True)

        with compare_cols[1]:
            st.markdown("#### Персонализированный поиск")
            if personalized_response is None:
                st.info("Персонализация не задана для этого сценария")
            else:
                st.caption(f"Пользователь: {format_user_label(scenario.user_id)}")
                personalized_rows = [
                    {"#": index + 1, "Товар": f"{category_icon(item.product.category)} {item.product.title}", "Категория": item.product.category[:40], "Score": f"{item.score:.1f}"}
                    for index, item in enumerate(personalized_response.items)
                ]
                st.dataframe(pd.DataFrame(personalized_rows), width="stretch", hide_index=True)


def result_card(item, user_id: str | None, mode: str, rank: int, key_prefix: str = "search") -> None:
    product = item.product
    icon = category_icon(product.category)
    score_color = "#27ae60" if item.score >= 20 else "#e67e22" if item.score >= 10 else "#95a5a6"
    reasons_html = " ".join(f"<code>{html_module.escape(r)}</code>" for r in (item.reasons or []))
    attrs_str = product.attributes.get("raw", "")[:150] if product.attributes else ""
    # Use highlighted title if available
    display_title = item.highlight_title if item.highlight_title else html_module.escape(product.title)

    # Personalization indicator
    pers_badge = ""
    if any("буст" in r for r in (item.reasons or [])):
        pers_badge = '<span style="background:#d4edda;color:#155724;padding:2px 8px;border-radius:8px;font-size:0.75rem;font-weight:600;margin-left:6px">⚡ Персонализировано</span>'

    card_html = f"""
    <div class="product-card">
        <div class="card-header">
            <span class="rank-badge">#{rank}</span>
            <span class="cat-icon">{icon}</span>
            <div class="title-block">
                <strong>{display_title}</strong>{pers_badge}<br>
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
    st.markdown("## 🧪 Search Studio")
    st.markdown(
        "<div class='hero-card'><strong>Лаборатория:</strong> тестирование и сравнение режимов поиска. На продуктовом интерфейсе пользователю этот экран не показывается.</div>",
        unsafe_allow_html=True,
    )

    options = ["", *list_user_ids()]
    with st.form("search_form"):
        query = st.text_input("Поисковый запрос", value=st.session_state.get("last_query", "ноут для офиса"))
        cols = st.columns(4)
        mode = cols[0].selectbox("Режим", options=["keyword", "semantic", "hybrid"], index=2)
        user_id = cols[1].selectbox("Пользователь", options=options, format_func=lambda u: format_user_label(u) if u else "— без —", index=1 if len(options) > 1 else 0)
        limit = cols[2].number_input("Лимит", min_value=1, max_value=500, value=5, step=1)
        compare_modes = cols[3].checkbox("Сравнить режимы", value=True)
        submitted = st.form_submit_button("🔎 Запустить поиск")

    if not submitted:
        return

    st.session_state["last_query"] = query
    response = search_products(query=query, limit=limit, user_id=user_id or None, mode=mode)
    render_search_response(response=response, user_id=user_id or None, compare_modes=compare_modes, key_prefix="search", show_debug=True)


def render_profiles_tab() -> None:
    st.markdown("## 👤 Профили и сигналы")
    users = list_user_ids()
    default_user = st.session_state.get("selected_user_id", users[0] if users else "7714338609")
    selected_user = st.selectbox("Пользователь", options=users, format_func=format_user_label, index=users.index(default_user) if default_user in users else 0)
    profile = repository.get_user_profile(selected_user)

    metrics = st.columns(4)
    metrics[0].metric("Всего контрактов", profile.total_events)
    metrics[1].metric("Средняя цена", format_price(profile.average_price) if profile.average_price else "—")
    metrics[2].metric("Категорий в профиле", len(profile.category_affinity))
    metrics[3].metric("User ID (ИНН)", selected_user)

    st.markdown("### Категории закупок (aффинити)")
    if profile.category_affinity:
        sorted_cats = dict(sorted(profile.category_affinity.items(), key=lambda x: x[1], reverse=True))
        labels = [f"{category_icon(k)} {k[:50]}" for k in sorted_cats]
        values = list(sorted_cats.values())
        st.bar_chart(pd.DataFrame({"аффинити": values}, index=labels))
    else:
        st.info("Нет данных о закупках")


def render_system_tab() -> None:
    st.markdown("## ⚙ Система и метрики")
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
        st.json(
            {
                "ready": semantic_status.ready,
                "backend": semantic_status.backend,
                "model_name": semantic_status.model_name,
                "indexed_products": semantic_status.indexed_products,
                "categories_indexed": semantic_status.categories_indexed,
                "last_error": semantic_status.last_error,
            }
        )
    with engine_cols[1]:
        rr_icon = "🟢" if reranker_status.ready else "🔴"
        st.markdown(f"### {rr_icon} Reranker")
        st.json(
            {
                "ready": reranker_status.ready,
                "backend": reranker_status.backend,
                "model_name": reranker_status.model_name,
                "last_error": reranker_status.last_error,
            }
        )

    st.markdown("### 📈 Evaluation summary")
    metric_cols = st.columns(5)
    metric_cols[0].metric("Hit@3", f"{evaluation.hit_rate_at_3:.2f}")
    metric_cols[1].metric("MRR@10", f"{evaluation.mrr_at_10:.3f}")
    metric_cols[2].metric("NDCG@10", f"{evaluation.ndcg_at_10:.3f}")
    metric_cols[3].metric("Precision@3", f"{evaluation.precision_at_3:.3f}")
    metric_cols[4].metric("Recall@10", f"{evaluation.recall_at_10:.3f}")

    st.dataframe(pd.DataFrame([case.model_dump() for case in evaluation.cases]), width="stretch", hide_index=True)
    st.markdown("### Сравнение режимов")
    st.success(f"Лучший режим по NDCG@10: **{comparison.best_mode_by_ndcg}**")
    st.dataframe(pd.DataFrame([row.model_dump() for row in comparison.rows]), width="stretch", hide_index=True)


def render_data_ops_tab() -> None:
    st.markdown("## 🗂 Данные")
    st.caption("JSON-каталог и события можно импортировать прямо из интерфейса.")

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
    st.dataframe(pd.DataFrame(synonym_rows), width="stretch", hide_index=True)


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

    tabs = st.tabs(["🔍 Поиск", "🧪 Лаборатория", "👤 Профили", "⚙ Система", "🗂 Данные"])
    with tabs[0]:
        render_demo_scenarios_tab()
    with tabs[1]:
        render_search_tab()
    with tabs[2]:
        render_profiles_tab()
    with tabs[3]:
        render_system_tab()
    with tabs[4]:
        render_data_ops_tab()


if __name__ == "__main__":
    main()