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
            "Показать, что в результатах мониторы Samsung, Dell, LG.",
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
            "Показать expanded_terms: системный блок, пк, компьютер, десктоп.",
            "Показать результаты: iRu, HP ProDesk, Lenovo ThinkCentre, Dell OptiPlex.",
        ],
        events=[],
    ),
    DemoScenario(
        key="abbreviation_search",
        title="Аббревиатуры и Жаргон",
        summary="Показывает, как аббревиатуры и жаргонные сокращения раскрываются в полные термины.",
        query="бесперебойник",
        mode="hybrid",
        user_id=None,
        goal="Доказать, что система понимает разговорные сокращения вроде 'бесперебойник' → ИБП.",
        steps=[
            "Ввести запрос 'бесперебойник'.",
            "Показать expanded_terms: ибп, ups, источник бесперебойного питания.",
            "Показать результаты APC Back-UPS 650VA и APC Smart-UPS 1500VA.",
        ],
        events=[],
    ),
    DemoScenario(
        key="personalization_it",
        title="Персонализация: IT-отдел",
        summary="Показывает, как история IT-специалиста влияет на ранжирование — компьютеры и периферия выше.",
        query="для офиса",
        mode="hybrid",
        user_id="user-1",
        goal="Доказать, что у пользователя с IT-профилем компьютерная техника поднимается выше мебели и канцелярии.",
        steps=[
            "Запустить поиск от user-1 (IT-отдел).",
            "Показать, что ноутбуки и ПК идут выше канцелярии.",
            "Сравнить с нейтральным поиском без user_id.",
        ],
        events=[
            EventCreate(user_id="user-1", event_type="search", query="ноутбук для офиса"),
            EventCreate(user_id="user-1", event_type="click", item_id=1),
            EventCreate(user_id="user-1", event_type="click", item_id=35),
            EventCreate(user_id="user-1", event_type="purchase", item_id=1),
            EventCreate(user_id="user-1", event_type="purchase", item_id=56),
        ],
    ),
    DemoScenario(
        key="personalization_aho",
        title="Персонализация: Хозотдел",
        summary="Показывает, как история хозотдела поднимает канцелярию и мебель выше техники.",
        query="для офиса",
        mode="hybrid",
        user_id="user-2",
        goal="Доказать, что тот же запрос даёт разные результаты для разных пользователей.",
        steps=[
            "Запустить тот же запрос 'для офиса' от user-2 (АХО).",
            "Показать, что бумага, мебель и хозтовары идут выше ноутбуков.",
            "Акцентировать разницу с user-1.",
        ],
        events=[
            EventCreate(user_id="user-2", event_type="search", query="бумага для офиса"),
            EventCreate(user_id="user-2", event_type="click", item_id=68),
            EventCreate(user_id="user-2", event_type="purchase", item_id=68),
            EventCreate(user_id="user-2", event_type="purchase", item_id=43),
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