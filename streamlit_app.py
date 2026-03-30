import pandas as pd
import streamlit as st

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


st.set_page_config(
    page_title="Smart Search Hackathon",
    page_icon="SS",
    layout="wide",
    initial_sidebar_state="expanded",
)


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
        .stAlert,
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
        </style>
        """,
        unsafe_allow_html=True,
    )


def list_user_ids() -> list[str]:
    user_ids = set()
    if hasattr(repository, "user_profiles"):
        user_ids.update(getattr(repository, "user_profiles").keys())
    if hasattr(repository, "events"):
        user_ids.update(event.user_id for event in getattr(repository, "events"))
    user_ids.update({"user-1", "user-2", "user-3"})
    return sorted(user_ids)


def render_reason_pills(reasons: list[str]) -> None:
    html = "".join(f'<span class="reason-pill">{reason}</span>' for reason in reasons)
    st.markdown(html or '<span class="reason-pill">Без пояснений</span>', unsafe_allow_html=True)


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
    summary_cols = st.columns(3)
    summary_cols[0].metric("Найдено", response.total)
    summary_cols[1].metric("Персонализация", "вкл" if response.personalized else "выкл")
    summary_cols[2].metric("Используемый режим", response.mode)

    st.write("Исправленный запрос:", response.corrected_query or "без изменений")
    st.write("Расширение запроса:", ", ".join(response.expanded_terms) if response.expanded_terms else "нет")

    if show_debug:
        with st.expander("Технические детали поиска", expanded=False):
            info_cols = st.columns(3)
            info_cols[0].metric("Semantic", response.semantic_backend or "off")
            info_cols[1].metric("Reranker", response.reranker_backend or "off")
            info_cols[2].metric("Mode", response.mode)

    if response.items:
        for index, item in enumerate(response.items, start=1):
            st.markdown("<div class='result-card'>", unsafe_allow_html=True)
            result_card(item, user_id, response.mode, index, key_prefix=key_prefix)
            st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.warning("Ничего не найдено")

    if compare_modes:
        st.markdown("## Mode Comparison")
        rows = []
        for candidate_mode in ["keyword", "semantic", "hybrid"]:
            candidate = search_products(query=response.query, limit=3, user_id=user_id or None, mode=candidate_mode)
            rows.append(
                {
                    "mode": candidate_mode,
                    "results": candidate.total,
                    "semantic_backend": candidate.semantic_backend or "off",
                    "reranker_backend": candidate.reranker_backend or "off",
                    "top_results": " | ".join(item.product.title for item in candidate.items) or "нет результатов",
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_demo_scenarios_tab() -> None:
    st.markdown("## Умный поиск")
    st.caption("Основной пользовательский экран: вводишь запрос и получаешь итоговую выдачу без ручного выбора технического режима.")

    st.markdown(
        f"<div class='hero-card'><strong>Как это работает:</strong> по умолчанию включён общий smart-search pipeline: correction + synonyms + semantic + rerank. Сейчас в локальном каталоге {repository.count_products()} товаров. После импорта реальных данных этот же экран будет искать уже по ним.</div>",
        unsafe_allow_html=True,
    )

    demo_user_options = ["", *list_user_ids()]
    with st.form("demo_quick_search_form"):
        demo_query = st.text_input("Введите запрос", value=st.session_state.get("demo_query", ""))
        top_cols = st.columns([2, 1])
        demo_limit = top_cols[0].number_input("Сколько результатов показать", min_value=1, max_value=100, value=5, step=1, key="demo-limit")
        show_advanced = top_cols[1].checkbox("Показать расширенные настройки", value=False, key="demo-show-advanced")

        demo_user_id = ""
        demo_mode = "hybrid"
        demo_compare_modes = False
        if show_advanced:
            advanced_cols = st.columns(3)
            demo_user_id = advanced_cols[0].selectbox("Пользователь", options=demo_user_options, index=0, key="demo-user")
            demo_mode = advanced_cols[1].selectbox("Режим для теста", options=["keyword", "semantic", "hybrid"], index=2, key="demo-mode")
            demo_compare_modes = advanced_cols[2].checkbox("Сравнить режимы", value=False, key="demo-compare")
        demo_submitted = st.form_submit_button("Искать")

    if demo_submitted:
        st.session_state["demo_query"] = demo_query
        st.session_state["last_query"] = demo_query
        demo_response = search_products(query=demo_query, limit=demo_limit, user_id=demo_user_id or None, mode=demo_mode)
        render_search_response(
            response=demo_response,
            user_id=demo_user_id or None,
            compare_modes=demo_compare_modes,
            key_prefix="demo",
            show_debug=show_advanced,
        )

    st.markdown("## Готовые сценарии")
    st.caption("Ниже только демонстрационные пресеты для показа жюри. В реальном пользовательском интерфейсе этот блок не обязателен.")

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

        st.info(f"Demo-запрос сценария: {scenario.query}")

        with st.container(border=True):
            st.markdown(f"### {scenario.title}")
            st.write(scenario.summary)
            st.write("Цель:", scenario.goal)
            st.write("Шаги:")
            for index, step in enumerate(scenario.steps, start=1):
                st.write(f"{index}. {step}")

        control_cols = st.columns(4)
        if control_cols[0].button("Загрузить сценарий", key=f"load-scenario-{scenario.key}"):
            apply_demo_scenario(scenario.key)
            st.session_state["demo_query"] = scenario.query
            st.success("Сценарий загружен в поле быстрого поиска")
        if control_cols[1].button("Применить demo-события", key=f"apply-events-{scenario.key}"):
            st.success(run_demo_events(scenario.key))
        if control_cols[2].button("Сбросить demo state", key=f"reset-state-{scenario.key}"):
            repository.reset_demo_state()
            semantic_engine.reset()
            st.success("Demo state сброшен к исходному состоянию")
        if control_cols[3].button("Открыть профиль", key=f"open-profile-{scenario.key}"):
            st.session_state["selected_user_id"] = scenario.user_id or "user-1"
            st.info("Профиль выбран во вкладке Profiles")

        baseline_response = search_products(query=scenario.query, limit=5, user_id=None, mode=scenario.mode)
        personalized_response = search_products(query=scenario.query, limit=5, user_id=scenario.user_id, mode=scenario.mode) if scenario.user_id else None

        compare_cols = st.columns(2)
        with compare_cols[0]:
            st.markdown("### Базовый поиск")
            st.write(f"Query: {scenario.query}")
            st.write(f"Mode: {scenario.mode}")
            baseline_rows = [
                {"rank": index + 1, "title": item.product.title, "score": item.score}
                for index, item in enumerate(baseline_response.items)
            ]
            st.dataframe(pd.DataFrame(baseline_rows), use_container_width=True, hide_index=True)

        with compare_cols[1]:
            st.markdown("### Персонализированный поиск")
            if personalized_response is None:
                st.info("Для этого сценария персонализация не используется")
            else:
                st.write(f"User: {scenario.user_id}")
                personalized_rows = [
                    {"rank": index + 1, "title": item.product.title, "score": item.score}
                    for index, item in enumerate(personalized_response.items)
                ]
                st.dataframe(pd.DataFrame(personalized_rows), use_container_width=True, hide_index=True)


def result_card(item, user_id: str | None, mode: str, rank: int, key_prefix: str = "search") -> None:
    product = item.product
    st.markdown(f"### {rank}. {product.title}")
    cols = st.columns(4)
    cols[0].metric("Score", f"{item.score:.3f}")
    cols[1].metric("SKU", product.sku)
    cols[2].metric("Категория", product.category)
    cols[3].metric("Цена", f"{product.price:,.0f}".replace(",", " "))
    st.caption(product.description or "Без описания")
    if product.tags:
        st.write("Теги:", ", ".join(product.tags))
    render_reason_pills(item.reasons)

    action_cols = st.columns(4)
    if action_cols[0].button("Click", key=f"{key_prefix}-click-{mode}-{user_id}-{product.id}-{rank}"):
        repository.add_event(EventCreate(user_id=user_id or "guest-demo", event_type="click", item_id=product.id))
        st.success(f"Событие click добавлено для {product.title}")
    if action_cols[1].button("Favorite", key=f"{key_prefix}-favorite-{mode}-{user_id}-{product.id}-{rank}"):
        repository.add_event(EventCreate(user_id=user_id or "guest-demo", event_type="favorite", item_id=product.id))
        st.success(f"Событие favorite добавлено для {product.title}")
    if action_cols[2].button("Purchase", key=f"{key_prefix}-purchase-{mode}-{user_id}-{product.id}-{rank}"):
        repository.add_event(EventCreate(user_id=user_id or "guest-demo", event_type="purchase", item_id=product.id))
        st.success(f"Событие purchase добавлено для {product.title}")
    if action_cols[3].button("Open Profile", key=f"{key_prefix}-profile-{mode}-{user_id}-{product.id}-{rank}"):
        st.session_state["selected_user_id"] = user_id or "guest-demo"
        st.info("Выбранный пользователь откроется во вкладке Profiles")

    st.divider()


def render_search_tab() -> None:
    st.markdown("## Search Studio")
    st.markdown(
        "<div class='hero-card'><strong>Лаборатория:</strong> этот экран оставлен для тестов и сравнения режимов. На продуктовом интерфейсе пользователю обычно не показывают выбор keyword или semantic.</div>",
        unsafe_allow_html=True,
    )

    options = ["", *list_user_ids()]
    with st.form("search_form"):
        query = st.text_input("Поисковый запрос", value=st.session_state.get("last_query", "ноут для офиса"))
        cols = st.columns(4)
        mode = cols[0].selectbox("Режим", options=["keyword", "semantic", "hybrid"], index=2)
        user_id = cols[1].selectbox("Пользователь", options=options, index=1 if len(options) > 1 else 0)
        limit = cols[2].number_input("Количество результатов", min_value=1, max_value=100, value=5, step=1)
        compare_modes = cols[3].checkbox("Сравнить режимы", value=True)
        submitted = st.form_submit_button("Запустить поиск")

    if not submitted:
        return

    st.session_state["last_query"] = query
    response = search_products(query=query, limit=limit, user_id=user_id or None, mode=mode)
    render_search_response(response=response, user_id=user_id or None, compare_modes=compare_modes, key_prefix="search", show_debug=True)


def render_profiles_tab() -> None:
    st.markdown("## Profiles & Signals")
    users = list_user_ids()
    default_user = st.session_state.get("selected_user_id", users[0] if users else "user-1")
    selected_user = st.selectbox("Пользователь", options=users, index=users.index(default_user) if default_user in users else 0)
    profile = repository.get_user_profile(selected_user)
    events = repository.list_user_events(selected_user)

    metrics = st.columns(3)
    metrics[0].metric("Total events", profile.total_events)
    metrics[1].metric("Avg price", f"{profile.average_price:,.0f}".replace(",", " ") if profile.average_price else "n/a")
    metrics[2].metric("Recent queries", len(profile.recent_queries))

    cols = st.columns(2)
    with cols[0]:
        st.markdown("### Category affinity")
        if profile.category_affinity:
            st.bar_chart(pd.DataFrame({"score": profile.category_affinity}))
        else:
            st.info("Нет данных")
    with cols[1]:
        st.markdown("### Tag affinity")
        if profile.tag_affinity:
            st.bar_chart(pd.DataFrame({"score": dict(list(profile.tag_affinity.items())[:8])}))
        else:
            st.info("Нет данных")

    st.markdown("### Recent queries")
    st.write(profile.recent_queries or ["Пока нет запросов"])

    st.markdown("### Event history")
    if events:
        event_rows = [
            {
                "event_id": event.event_id,
                "timestamp": event.timestamp,
                "event_type": event.event_type,
                "item_id": event.item_id,
                "query": event.query,
            }
            for event in events
        ]
        st.dataframe(pd.DataFrame(event_rows), use_container_width=True, hide_index=True)
    else:
        st.info("У пользователя пока нет событий")


def render_system_tab() -> None:
    st.markdown("## System & Metrics")
    evaluation = evaluate_search()
    comparison = compare_search_modes()
    semantic_status = semantic_engine.status()
    reranker_status = reranker.status()

    top_cols = st.columns(4)
    top_cols[0].metric("Catalog", repository.count_products())
    top_cols[1].metric("Events", repository.count_events())
    top_cols[2].metric("Profiles", repository.count_profiles())
    top_cols[3].metric("Storage", repository.backend_name())

    engine_cols = st.columns(2)
    with engine_cols[0]:
        st.markdown("### Semantic engine")
        st.json(
            {
                "ready": semantic_status.ready,
                "backend": semantic_status.backend,
                "model_name": semantic_status.model_name,
                "indexed_products": semantic_status.indexed_products,
                "last_error": semantic_status.last_error,
            }
        )
    with engine_cols[1]:
        st.markdown("### Reranker")
        st.json(
            {
                "ready": reranker_status.ready,
                "backend": reranker_status.backend,
                "model_name": reranker_status.model_name,
                "last_error": reranker_status.last_error,
            }
        )

    st.markdown("### Evaluation summary")
    metric_cols = st.columns(5)
    metric_cols[0].metric("Hit@3", evaluation.hit_rate_at_3)
    metric_cols[1].metric("MRR@10", evaluation.mrr_at_10)
    metric_cols[2].metric("NDCG@10", evaluation.ndcg_at_10)
    metric_cols[3].metric("Precision@3", evaluation.precision_at_3)
    metric_cols[4].metric("Recall@10", evaluation.recall_at_10)

    st.dataframe(pd.DataFrame([case.model_dump() for case in evaluation.cases]), use_container_width=True, hide_index=True)
    st.markdown("### Mode comparison")
    st.success(f"Лучший режим по NDCG@10: {comparison.best_mode_by_ndcg}")
    st.dataframe(pd.DataFrame([row.model_dump() for row in comparison.rows]), use_container_width=True, hide_index=True)
    st.markdown("### Storage config")
    st.json(
        {
            "storage_backend": repository.backend_name(),
            "database_url": settings.database_url,
            "seed_demo_data": settings.seed_demo_data,
        }
    )


def render_data_ops_tab() -> None:
    st.markdown("## Data Ops")
    st.caption("JSON и CSV можно импортировать прямо из интерфейса в текущее приложение.")

    with st.form("catalog_import_form"):
        catalog_path = st.text_input("Путь к каталогу", value="data/catalog.json")
        replace_catalog = st.checkbox("Заменить существующий каталог", value=True)
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

    with st.form("events_import_form"):
        events_path = st.text_input("Путь к событиям", value="data/sample_events.json")
        replace_events = st.checkbox("Заменить существующие события", value=False)
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

    st.markdown("### Preview synonyms")
    synonym_rows = [
        {"term": key, "variants": ", ".join(values)}
        for key, values in list(get_synonym_map().items())[:20]
    ]
    st.dataframe(pd.DataFrame(synonym_rows), use_container_width=True, hide_index=True)


def main() -> None:
    inject_styles()
    st.markdown(
        """
        <div class="hero-card">
            <h1>Smart Search Hackathon</h1>
            <p>Интерактивная панель умного поиска. Основной экран показывает итоговую выдачу, а технические режимы и сравнение вынесены в отдельную лабораторию.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.sidebar.title("Control Room")
    st.sidebar.caption("Служебная информация")
    st.sidebar.write({"storage": repository.backend_name(), "semantic": semantic_engine.status().backend, "reranker": reranker.status().backend})
    if st.sidebar.button("Reset demo state", key="sidebar-reset-demo"):
        repository.reset_demo_state()
        semantic_engine.reset()
        st.sidebar.success("Demo state reset")
    st.sidebar.caption("Тяжёлые модели можно включать через переменные окружения без изменения кода.")

    tabs = st.tabs(["Поиск", "Лаборатория", "Профили", "Система", "Данные"])
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