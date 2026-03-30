from dataclasses import dataclass

from app.schemas import EventCreate, SearchMode


@dataclass(frozen=True)
class DemoScenario:
    key: str
    title: str
    summary: str
    query: str
    mode: SearchMode
    user_id: str | None
    goal: str
    steps: list[str]
    events: list[EventCreate]


DEMO_SCENARIOS: list[DemoScenario] = [
    DemoScenario(
        key="typo_recovery",
        title="Исправление Опечатки",
        summary="Показывает, как запрос с ошибкой находит правильный товар через correction layer и синонимы.",
        query="монитр",
        mode="hybrid",
        user_id=None,
        goal="Доказать, что поиск устойчив к опечаткам и не требует точного ввода.",
        steps=[
            "Ввести запрос 'монитр'.",
            "Показать corrected_query = монитор.",
            "Показать, что первым результатом идёт монитор Samsung.",
        ],
        events=[],
    ),
    DemoScenario(
        key="synonym_search",
        title="Синонимы И Разговорные Формы",
        summary="Показывает, как разговорный запрос или сокращение раскрывается до каталожных терминов.",
        query="системник",
        mode="hybrid",
        user_id=None,
        goal="Доказать, что пользователь может искать неформальными словами и всё равно получать релевантный СТЕ.",
        steps=[
            "Запустить поиск по 'системник'.",
            "Показать expanded_terms: системный блок, пк, компьютер.",
            "Показать результат 'Системный блок iRu Office'.",
        ],
        events=[],
    ),
    DemoScenario(
        key="personalization_before_after",
        title="Персонализация До И После",
        summary="Показывает, как история действий пользователя перестраивает выдачу для похожих товаров.",
        query="ноут",
        mode="hybrid",
        user_id="user-3",
        goal="Доказать, что система учитывает пользовательскую историю, а не только текст запроса.",
        steps=[
            "Показать поиск user-3 до взаимодействий.",
            "Применить demo-события click/favorite/purchase для ноутбуков.",
            "Повторить тот же запрос и показать усиление персонализированных reasons.",
        ],
        events=[
            EventCreate(user_id="user-3", event_type="search", query="ноутбук для закупки офиса"),
            EventCreate(user_id="user-3", event_type="click", item_id=6),
            EventCreate(user_id="user-3", event_type="favorite", item_id=6),
            EventCreate(user_id="user-3", event_type="purchase", item_id=1),
        ],
    ),
]


def get_demo_scenarios() -> list[DemoScenario]:
    return DEMO_SCENARIOS


def get_demo_scenario(key: str) -> DemoScenario | None:
    for scenario in DEMO_SCENARIOS:
        if scenario.key == key:
            return scenario
    return None