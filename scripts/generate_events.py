"""Generate realistic user events for personalization demo."""
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)

# User profiles with distinct preferences
USER_PROFILES = {
    "user-1": {
        "name": "IT-отдел",
        "preferred_categories": ["ноутбуки", "компьютеры", "периферия", "сетевое оборудование"],
        "preferred_ids": [1, 2, 3, 5, 8, 35, 36, 37, 56, 57, 58, 60, 62, 85, 86, 87, 92],
        "search_queries": [
            "ноутбук для офиса", "системный блок", "клавиатура мышь комплект",
            "монитор 27", "роутер wifi", "ибп для компьютера", "веб-камера hd",
            "гарнитура для видеозвонков", "сервер dell", "коммутатор 8 портов",
            "ноут lenovo", "мини-пк", "патч-корд", "внешний ssd",
        ],
    },
    "user-2": {
        "name": "АХО (хозотдел)",
        "preferred_categories": ["канцелярия", "хозтовары", "мебель", "освещение"],
        "preferred_ids": [43, 45, 46, 49, 50, 51, 68, 69, 71, 73, 75, 76, 78, 80, 82, 83, 117, 118, 121, 122, 123, 124, 125, 126, 127, 130],
        "search_queries": [
            "бумага а4", "канцтовары", "офисное кресло", "стол письменный",
            "мыло жидкое", "полотенца бумажные", "корзина для мусора",
            "светильник офисный", "лампочки led", "кулер для воды",
            "шкаф для документов", "вешалка напольная", "лоток для бумаг",
            "ручки шариковые", "файлы а4", "стеллаж металлический",
        ],
    },
    "user-3": {
        "name": "Бухгалтерия",
        "preferred_categories": ["оргтехника", "расходные материалы", "программное обеспечение", "канцелярия"],
        "preferred_ids": [13, 14, 15, 18, 19, 22, 24, 25, 27, 68, 75, 78, 111, 113, 114, 116, 159, 160, 161, 162],
        "search_queries": [
            "мфу лазерное", "картридж hp", "бумага для принтера",
            "1с бухгалтерия", "калькулятор настольный", "шредер",
            "сканер планшетный", "принтер для офиса", "тонер brother",
            "папка регистратор", "ламинатор", "плёнка для ламинирования",
            "антивирус касперский", "лицензия office",
        ],
    },
    "user-4": {
        "name": "Руководство",
        "preferred_categories": ["ноутбуки", "мониторы", "мебель", "проекторы", "смартфоны", "планшеты"],
        "preferred_ids": [4, 9, 12, 30, 34, 44, 47, 101, 102, 105, 109, 128, 148, 151, 157, 168],
        "search_queries": [
            "ноутбук премиум", "монитор 4k", "кресло руководителя",
            "проектор для конференц-зала", "интерактивная панель",
            "конференц-телефон", "кофемашина", "кондиционер",
            "ноутбук thinkpad", "планшет apple", "смартфон samsung",
            "внешний ssd samsung", "стол угловой",
        ],
    },
    "user-5": {
        "name": "Безопасность и связь",
        "preferred_categories": ["безопасность", "сетевое оборудование", "телефония", "спецодежда"],
        "preferred_ids": [85, 88, 89, 91, 93, 94, 106, 107, 108, 110, 131, 132, 133, 134, 135, 136, 137, 138, 139, 140, 163, 165, 170],
        "search_queries": [
            "камера видеонаблюдения", "видеорегистратор", "скуд контроллер",
            "считыватель карт", "рация", "ip телефон", "огнетушитель",
            "аптечка первой помощи", "жилет сигнальный", "халат рабочий",
            "кабель-канал", "серверный шкаф", "ибп серверный",
            "коммутатор 24 порта", "точка доступа wifi",
        ],
    },
}

BASE_TIME = datetime(2026, 3, 1, 9, 0, 0)
events = []
event_id_counter = 0


def make_event(user_id, event_type, item_id=None, query=None, ts=None):
    global event_id_counter
    event_id_counter += 1
    e = {"user_id": user_id, "event_type": event_type}
    if item_id is not None:
        e["item_id"] = item_id
    if query is not None:
        e["query"] = query
    return e


for user_id, profile in USER_PROFILES.items():
    queries = profile["search_queries"]
    item_ids = profile["preferred_ids"]

    # Generate search sessions (each user has ~15-20 sessions)
    for session_idx in range(random.randint(15, 22)):
        ts = BASE_TIME + timedelta(days=random.randint(0, 28), hours=random.randint(0, 8), minutes=random.randint(0, 59))
        query = random.choice(queries)
        events.append(make_event(user_id, "search", query=query))

        # After search: click 1-3 items
        clicked_items = random.sample(item_ids, min(random.randint(1, 3), len(item_ids)))
        for item_id in clicked_items:
            events.append(make_event(user_id, "click", item_id=item_id))

            # After click: sometimes favorite (30%)
            if random.random() < 0.3:
                events.append(make_event(user_id, "favorite", item_id=item_id))

            # After click: sometimes purchase (20%)
            if random.random() < 0.2:
                events.append(make_event(user_id, "purchase", item_id=item_id))

    # Direct browsing (clicks without searches)
    for _ in range(random.randint(10, 20)):
        item_id = random.choice(item_ids)
        events.append(make_event(user_id, "click", item_id=item_id))
        if random.random() < 0.25:
            events.append(make_event(user_id, "favorite", item_id=item_id))
        if random.random() < 0.15:
            events.append(make_event(user_id, "purchase", item_id=item_id))

    # Dedicated purchases
    purchased = random.sample(item_ids, min(random.randint(4, 8), len(item_ids)))
    for item_id in purchased:
        events.append(make_event(user_id, "purchase", item_id=item_id))

# Shuffle to simulate real timeline
random.shuffle(events)

output_path = Path(__file__).resolve().parent.parent / "data" / "sample_events.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(events, f, ensure_ascii=False, indent=2)

# Stats
from collections import Counter
type_counts = Counter(e["event_type"] for e in events)
user_counts = Counter(e["user_id"] for e in events)
print(f"Generated {len(events)} events -> {output_path}")
print(f"  Types: {dict(type_counts)}")
print(f"  Users: {dict(user_counts)}")
